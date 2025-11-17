"""
API endpoints для управления пользователями.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_admin_user, require_permission
from src.admin.models.schemas import (
    UserInfo,
    UserListResponse,
    UserSettingsInfo,
    UserUpdate,
)
from src.db.models import AdminUser, User, UserSettings
from src.db.session import get_db_session

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
async def list_users(
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_users"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
):
    """
    Получить список пользователей с пагинацией.
    
    Требует права: can_manage_users
    """
    offset = (page - 1) * page_size
    
    # Базовый запрос
    query = select(User)
    
    # Поиск по username или first_name
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (User.username.ilike(search_pattern))
            | (User.first_name.ilike(search_pattern))
        )
    
    # Общее количество
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0
    
    # Список пользователей
    result = await session.execute(
        query.order_by(User.created_at.desc()).limit(page_size).offset(offset)
    )
    users = result.scalars().all()
    
    # Загружаем настройки для каждого пользователя
    user_list = []
    for user in users:
        # Получаем настройки
        settings_result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        user_settings = settings_result.scalar_one_or_none()
        
        user_info = UserInfo(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            is_admin=user.is_admin,
            created_at=user.created_at,
            updated_at=getattr(user, "updated_at", None),
        )
        
        if user_settings:
            user_info.settings = UserSettingsInfo(
                signature=user_settings.signature,
                default_currency=user_settings.default_currency,
                exchange_rate=float(user_settings.exchange_rate) if user_settings.exchange_rate else None,
                exchange_rate_at=user_settings.exchange_rate_at,
            )
        
        user_list.append(user_info)
    
    total_pages = (total + page_size - 1) // page_size
    
    return UserListResponse(
        users=user_list,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{user_id}", response_model=UserInfo)
async def get_user(
    user_id: int,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_users"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Получить детальную информацию о пользователе.
    
    Требует права: can_manage_users
    """
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с ID {user_id} не найден",
        )
    
    # Получаем настройки
    settings_result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_result.scalar_one_or_none()
    
    user_info = UserInfo(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        is_admin=user.is_admin,
        created_at=user.created_at,
        updated_at=getattr(user, "updated_at", None),
    )
    
    if user_settings:
        user_info.settings = UserSettingsInfo(
            signature=user_settings.signature,
            default_currency=user_settings.default_currency,
            exchange_rate=float(user_settings.exchange_rate) if user_settings.exchange_rate else None,
            exchange_rate_at=user_settings.exchange_rate_at,
        )
    
    return user_info


@router.put("/{user_id}", response_model=UserInfo)
async def update_user(
    user_id: int,
    update: UserUpdate,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_users"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Обновить информацию о пользователе.
    
    Требует права: can_manage_users
    """
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с ID {user_id} не найден",
        )
    
    # Обновляем поля
    if update.first_name is not None:
        user.first_name = update.first_name
    if update.last_name is not None:
        user.last_name = update.last_name
    if update.is_admin is not None:
        user.is_admin = update.is_admin
    
    await session.commit()
    await session.refresh(user)
    
    # Получаем настройки
    settings_result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_result.scalar_one_or_none()
    
    user_info = UserInfo(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        is_admin=user.is_admin,
        created_at=user.created_at,
        updated_at=getattr(user, "updated_at", None),
    )
    
    if user_settings:
        user_info.settings = UserSettingsInfo(
            signature=user_settings.signature,
            default_currency=user_settings.default_currency,
            exchange_rate=float(user_settings.exchange_rate) if user_settings.exchange_rate else None,
            exchange_rate_at=user_settings.exchange_rate_at,
        )
    
    return user_info


@router.post("/{user_id}/make-admin")
async def make_admin(
    user_id: int,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_users"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Назначить пользователя администратором.
    
    Требует права: can_manage_users
    """
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с ID {user_id} не найден",
        )
    
    user.is_admin = True
    
    # Создаем профиль админа, если его нет
    from src.db.models import AdminUser
    admin_result = await session.execute(
        select(AdminUser).where(AdminUser.user_id == user.id)
    )
    admin_profile = admin_result.scalar_one_or_none()
    
    if not admin_profile:
        admin_profile = AdminUser(
            user_id=user.id,
            can_manage_keys=False,  # По умолчанию ограниченные права
            can_view_stats=True,
            can_manage_users=False,
        )
        session.add(admin_profile)
    
    await session.commit()
    
    return {"message": f"Пользователь {user.username or user.first_name} назначен администратором"}


@router.delete("/{user_id}/revoke-admin")
async def revoke_admin(
    user_id: int,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_users"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Отозвать права администратора у пользователя.
    
    Требует права: can_manage_users
    """
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с ID {user_id} не найден",
        )
    
    user.is_admin = False
    
    # Удаляем профиль админа
    from src.db.models import AdminUser
    admin_result = await session.execute(
        select(AdminUser).where(AdminUser.user_id == user.id)
    )
    admin_profile = admin_result.scalar_one_or_none()
    
    if admin_profile:
        await session.delete(admin_profile)
    
    await session.commit()
    
    return {"message": f"Права администратора отозваны у пользователя {user.username or user.first_name}"}


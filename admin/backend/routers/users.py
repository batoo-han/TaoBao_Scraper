# -*- coding: utf-8 -*-
"""
API роутер управления пользователями бота.

Эндпоинты:
- GET / - Список пользователей
- POST / - Создать пользователя
- GET /{user_id} - Детали пользователя
- DELETE /{user_id} - Удалить пользователя
- PUT /{user_id}/settings - Обновить настройки
- PUT /{user_id}/limits - Обновить лимиты
- POST /{user_id}/whitelist - Добавить в белый список
- DELETE /{user_id}/whitelist - Удалить из белого списка
- POST /{user_id}/blacklist - Добавить в чёрный список (блокировка)
- DELETE /{user_id}/blacklist - Удалить из чёрного списка (разблокировка)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from admin.backend.database import get_db_session
from admin.backend.auth.dependencies import get_current_active_user, require_admin, CurrentUser
from admin.backend.models.user import (
    BotUserResponse,
    BotUserListResponse,
    BotUserCreate,
    BotUserSettingsUpdate,
    BotUserLimitsUpdate,
    BotUserSettingsResponse,
    BotUserLimitsResponse,
    BotUserAccessStatus,
)
from datetime import date
from src.db.models import (
    User,
    UserSettings,
    RateLimitUser,
    RequestStats,
    AccessControl,
    AccessListEntry,
    ListType,
    EntryType,
)

router = APIRouter()
logger = logging.getLogger("admin.routers.users")


async def get_user_access_status(
    db: AsyncSession,
    user_id: int,
    username: Optional[str],
) -> BotUserAccessStatus:
    """Получает статус пользователя в списках доступа."""
    
    # Получаем access_control с eager loading связанных entries
    result = await db.execute(
        select(AccessControl)
        .where(AccessControl.id == 1)
        .options(selectinload(AccessControl.entries))
    )
    access_control = result.scalar_one_or_none()
    
    if not access_control:
        return BotUserAccessStatus()
    
    in_whitelist = False
    whitelist_type = None
    in_blacklist = False
    blacklist_type = None
    
    # Проверяем белый список
    for entry in access_control.entries:
        if entry.list_type == ListType.WHITELIST:
            if entry.entry_type == EntryType.ID and entry.value == str(user_id):
                in_whitelist = True
                whitelist_type = "id"
            elif entry.entry_type == EntryType.USERNAME and username and entry.value.lower() == username.lower():
                in_whitelist = True
                whitelist_type = "username"
        elif entry.list_type == ListType.BLACKLIST:
            if entry.entry_type == EntryType.ID and entry.value == str(user_id):
                in_blacklist = True
                blacklist_type = "id"
            elif entry.entry_type == EntryType.USERNAME and username and entry.value.lower() == username.lower():
                in_blacklist = True
                blacklist_type = "username"
    
    return BotUserAccessStatus(
        in_whitelist=in_whitelist,
        in_blacklist=in_blacklist,
        whitelist_type=whitelist_type,
        blacklist_type=blacklist_type,
    )


async def get_user_stats(db: AsyncSession, user_id: int) -> tuple[int, float, Optional[str]]:
    """Получает статистику пользователя (всего запросов, стоимость, время последнего)."""
    
    # Всего запросов и стоимость
    result = await db.execute(
        select(
            func.count(RequestStats.id),
            func.coalesce(func.sum(RequestStats.total_cost), 0.0),
            func.max(RequestStats.request_time),
        ).where(RequestStats.user_id == user_id)
    )
    row = result.one()
    
    return row[0], float(row[1]), row[2]


@router.get("/", response_model=BotUserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Элементов на странице"),
    search: Optional[str] = Query(None, description="Поиск по ID или username"),
    in_whitelist: Optional[bool] = Query(None, description="Фильтр по белому списку"),
    in_blacklist: Optional[bool] = Query(None, description="Фильтр по чёрному списку"),
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение списка пользователей бота с пагинацией и фильтрами.
    """
    # Базовый запрос
    query = select(User)
    count_query = select(func.count(User.user_id))
    
    # Поиск
    if search:
        search_filter = or_(
            User.user_id == int(search) if search.isdigit() else False,
            User.username.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    
    # Общее количество
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Пагинация
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).order_by(User.created_at.desc())
    
    # Выполняем запрос
    result = await db.execute(query)
    users = result.scalars().all()
    
    # Формируем ответ
    items = []
    for user in users:
        # Загружаем настройки
        settings_result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == user.user_id)
        )
        settings = settings_result.scalar_one_or_none()
        
        # Загружаем лимиты
        limits_result = await db.execute(
            select(RateLimitUser).where(RateLimitUser.user_id == user.user_id)
        )
        limits = limits_result.scalar_one_or_none()
        
        # Статус доступа
        access_status = await get_user_access_status(db, user.user_id, user.username)
        
        # Фильтруем по спискам доступа если указано
        if in_whitelist is not None and access_status.in_whitelist != in_whitelist:
            continue
        if in_blacklist is not None and access_status.in_blacklist != in_blacklist:
            continue
        
        # Статистика
        total_requests, total_cost, last_request_at = await get_user_stats(db, user.user_id)
        
        items.append(BotUserResponse(
            user_id=user.user_id,
            username=user.username,
            created_at=user.created_at,
            settings=BotUserSettingsResponse.model_validate(settings) if settings else None,
            limits=BotUserLimitsResponse.model_validate(limits) if limits else None,
            access=access_status,
            total_requests=total_requests,
            total_cost=total_cost,
            last_request_at=last_request_at,
        ))
    
    pages = (total + per_page - 1) // per_page if total > 0 else 1
    
    return BotUserListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.post("/", response_model=BotUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: BotUserCreate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Создание нового пользователя бота.
    
    Требует права администратора.
    """
    # Проверяем, что пользователь с таким ID не существует
    result = await db.execute(
        select(User).where(User.user_id == data.user_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Пользователь с ID {data.user_id} уже существует",
        )
    
    # Создаём пользователя
    user = User(
        user_id=data.user_id,
        username=data.username,
        created_at=date.today(),
    )
    db.add(user)
    
    # Создаём настройки по умолчанию
    settings = UserSettings(user_id=data.user_id)
    db.add(settings)
    
    await db.commit()
    await db.refresh(user)
    
    logger.info(f"Создан пользователь бота {data.user_id} админом {current_user.username}")
    
    # Формируем ответ
    access_status = await get_user_access_status(db, user.user_id, user.username)
    
    return BotUserResponse(
        user_id=user.user_id,
        username=user.username,
        created_at=user.created_at,
        settings=BotUserSettingsResponse.model_validate(settings),
        limits=None,
        access=access_status,
        total_requests=0,
        total_cost=0.0,
        last_request_at=None,
    )


@router.get("/{user_id}", response_model=BotUserResponse)
async def get_user(
    user_id: int,
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение детальной информации о пользователе бота.
    """
    # Загружаем пользователя
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Загружаем настройки
    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = settings_result.scalar_one_or_none()
    
    # Загружаем лимиты
    limits_result = await db.execute(
        select(RateLimitUser).where(RateLimitUser.user_id == user_id)
    )
    limits = limits_result.scalar_one_or_none()
    
    # Статус доступа
    access_status = await get_user_access_status(db, user_id, user.username)
    
    # Статистика
    total_requests, total_cost, last_request_at = await get_user_stats(db, user_id)
    
    return BotUserResponse(
        user_id=user.user_id,
        username=user.username,
        created_at=user.created_at,
        settings=BotUserSettingsResponse.model_validate(settings) if settings else None,
        limits=BotUserLimitsResponse.model_validate(limits) if limits else None,
        access=access_status,
        total_requests=total_requests,
        total_cost=total_cost,
        last_request_at=last_request_at,
    )


@router.put("/{user_id}/settings", response_model=BotUserSettingsResponse)
async def update_user_settings(
    user_id: int,
    data: BotUserSettingsUpdate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление настроек пользователя бота.
    
    Требует права администратора.
    """
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Загружаем или создаём настройки
    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = settings_result.scalar_one_or_none()
    
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.add(settings)
    
    # Обновляем поля
    if data.signature is not None:
        settings.signature = data.signature
    if data.default_currency is not None:
        settings.default_currency = data.default_currency
    if data.exchange_rate is not None:
        settings.exchange_rate = data.exchange_rate
    if data.price_mode is not None:
        settings.price_mode = data.price_mode
    
    await db.commit()
    await db.refresh(settings)
    
    logger.info(f"Обновлены настройки пользователя {user_id} админом {current_user.username}")
    
    return BotUserSettingsResponse.model_validate(settings)


@router.put("/{user_id}/limits", response_model=BotUserSettingsResponse)
async def update_user_limits(
    user_id: int,
    data: BotUserLimitsUpdate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление индивидуальных лимитов пользователя бота.
    
    Требует права администратора.
    """
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Загружаем или создаём настройки
    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = settings_result.scalar_one_or_none()
    
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.add(settings)
    
    # Обновляем лимиты (0 означает безлимит = None)
    if data.daily_limit is not None:
        settings.daily_limit = data.daily_limit if data.daily_limit > 0 else None
    if data.monthly_limit is not None:
        settings.monthly_limit = data.monthly_limit if data.monthly_limit > 0 else None
    
    await db.commit()
    await db.refresh(settings)
    
    logger.info(f"Обновлены лимиты пользователя {user_id} админом {current_user.username}")
    
    return BotUserSettingsResponse.model_validate(settings)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Удаление пользователя бота.
    
    Удаляет пользователя и все связанные данные (настройки, лимиты, статистика).
    Требует права администратора.
    """
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Удаляем пользователя (каскадно удалятся связанные записи)
    await db.delete(user)
    await db.commit()
    
    logger.info(f"Удалён пользователь бота {user_id} админом {current_user.username}")


@router.post("/{user_id}/whitelist", response_model=BotUserAccessStatus)
async def add_to_whitelist(
    user_id: int,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Добавление пользователя в белый список.
    
    Добавляет по Telegram ID. Требует права администратора.
    """
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Получаем или создаём access_control
    result = await db.execute(
        select(AccessControl)
        .where(AccessControl.id == 1)
        .options(selectinload(AccessControl.entries))
    )
    access_control = result.scalar_one_or_none()
    
    if not access_control:
        access_control = AccessControl(id=1)
        db.add(access_control)
        await db.flush()
    
    # Проверяем, нет ли уже в белом списке
    for entry in access_control.entries:
        if (entry.list_type == ListType.WHITELIST 
            and entry.entry_type == EntryType.ID 
            and entry.value == str(user_id)):
            # Уже в списке
            return await get_user_access_status(db, user_id, user.username)
    
    # Добавляем запись
    new_entry = AccessListEntry(
        access_control_id=access_control.id,
        list_type=ListType.WHITELIST,
        entry_type=EntryType.ID,
        value=str(user_id),
    )
    db.add(new_entry)
    await db.commit()
    
    logger.info(f"Пользователь {user_id} добавлен в белый список админом {current_user.username}")
    
    return await get_user_access_status(db, user_id, user.username)


@router.delete("/{user_id}/whitelist", response_model=BotUserAccessStatus)
async def remove_from_whitelist(
    user_id: int,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Удаление пользователя из белого списка.
    
    Требует права администратора.
    """
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Удаляем записи из белого списка (по ID и username)
    await db.execute(
        select(AccessListEntry).where(
            and_(
                AccessListEntry.list_type == ListType.WHITELIST,
                or_(
                    and_(AccessListEntry.entry_type == EntryType.ID, AccessListEntry.value == str(user_id)),
                    and_(
                        AccessListEntry.entry_type == EntryType.USERNAME,
                        AccessListEntry.value == user.username if user.username else ""
                    ),
                )
            )
        )
    )
    
    # Выполняем удаление
    result = await db.execute(
        select(AccessListEntry).where(
            and_(
                AccessListEntry.list_type == ListType.WHITELIST,
                or_(
                    and_(AccessListEntry.entry_type == EntryType.ID, AccessListEntry.value == str(user_id)),
                    and_(
                        AccessListEntry.entry_type == EntryType.USERNAME,
                        AccessListEntry.value == (user.username if user.username else "")
                    ),
                )
            )
        )
    )
    entries = result.scalars().all()
    
    for entry in entries:
        await db.delete(entry)
    
    await db.commit()
    
    logger.info(f"Пользователь {user_id} удалён из белого списка админом {current_user.username}")
    
    return await get_user_access_status(db, user_id, user.username)


@router.post("/{user_id}/blacklist", response_model=BotUserAccessStatus)
async def add_to_blacklist(
    user_id: int,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Добавление пользователя в чёрный список (блокировка).
    
    Добавляет по Telegram ID. Требует права администратора.
    """
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Получаем или создаём access_control
    result = await db.execute(
        select(AccessControl)
        .where(AccessControl.id == 1)
        .options(selectinload(AccessControl.entries))
    )
    access_control = result.scalar_one_or_none()
    
    if not access_control:
        access_control = AccessControl(id=1)
        db.add(access_control)
        await db.flush()
    
    # Проверяем, нет ли уже в чёрном списке
    for entry in access_control.entries:
        if (entry.list_type == ListType.BLACKLIST 
            and entry.entry_type == EntryType.ID 
            and entry.value == str(user_id)):
            # Уже в списке
            return await get_user_access_status(db, user_id, user.username)
    
    # Добавляем запись
    new_entry = AccessListEntry(
        access_control_id=access_control.id,
        list_type=ListType.BLACKLIST,
        entry_type=EntryType.ID,
        value=str(user_id),
    )
    db.add(new_entry)
    await db.commit()
    
    logger.info(f"Пользователь {user_id} добавлен в чёрный список (заблокирован) админом {current_user.username}")
    
    return await get_user_access_status(db, user_id, user.username)


@router.delete("/{user_id}/blacklist", response_model=BotUserAccessStatus)
async def remove_from_blacklist(
    user_id: int,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Удаление пользователя из чёрного списка (разблокировка).
    
    Требует права администратора.
    """
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Удаляем записи из чёрного списка (по ID и username)
    result = await db.execute(
        select(AccessListEntry).where(
            and_(
                AccessListEntry.list_type == ListType.BLACKLIST,
                or_(
                    and_(AccessListEntry.entry_type == EntryType.ID, AccessListEntry.value == str(user_id)),
                    and_(
                        AccessListEntry.entry_type == EntryType.USERNAME,
                        AccessListEntry.value == (user.username if user.username else "")
                    ),
                )
            )
        )
    )
    entries = result.scalars().all()
    
    for entry in entries:
        await db.delete(entry)
    
    await db.commit()
    
    logger.info(f"Пользователь {user_id} удалён из чёрного списка (разблокирован) админом {current_user.username}")
    
    return await get_user_access_status(db, user_id, user.username)

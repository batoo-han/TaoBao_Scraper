"""
API endpoints для аутентификации в админ-панели.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_admin_user
from src.admin.models.schemas import AdminUserInfo, LoginRequest, LoginResponse
from src.admin.services.auth_service import AuthService
from src.db.models import AdminUser
from src.db.session import get_async_session, get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Вход в админ-панель.
    
    Возвращает JWT токен для дальнейшей аутентификации.
    """
    auth_service = AuthService(session)
    
    # Аутентифицируем пользователя
    user = await auth_service.authenticate_user(
        login_data.username,
        login_data.password
    )
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
        )
    
    # Получаем профиль админа
    from sqlalchemy import select
    result = await session.execute(
        select(AdminUser).where(AdminUser.user_id == user.id)
    )
    admin_user = result.scalar_one_or_none()
    
    if admin_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Профиль админа не найден",
        )
    
    # Создаем JWT токен
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id)}
    )
    
    return LoginResponse(
        access_token=access_token,
        user=AdminUserInfo(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            can_manage_keys=admin_user.can_manage_keys,
            can_view_stats=admin_user.can_view_stats,
            can_manage_users=admin_user.can_manage_users,
        )
    )


@router.get("/me", response_model=AdminUserInfo)
async def get_current_user(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Получить информацию о текущем администраторе."""
    from sqlalchemy import select
    from src.db.models import User
    
    result = await session.execute(
        select(User).where(User.id == admin_user.user_id)
    )
    user = result.scalar_one()
    
    return AdminUserInfo(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        can_manage_keys=admin_user.can_manage_keys,
        can_view_stats=admin_user.can_view_stats,
        can_manage_users=admin_user.can_manage_users,
    )


@router.post("/logout")
async def logout():
    """
    Выход из админ-панели.
    
    Примечание: В случае JWT токенов, выход реализуется на клиенте
    (удаление токена). Сервер не хранит сессии.
    """
    return {"message": "Успешный выход"}


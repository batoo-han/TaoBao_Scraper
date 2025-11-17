"""
Зависимости FastAPI для админ-панели.

Включает проверку аутентификации и прав доступа.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.models import AdminUser, User
from src.db.session import get_async_session, get_db_session

# Схемы безопасности для JWT токенов
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

# Секретный ключ для JWT
JWT_SECRET_KEY = settings.ADMIN_JWT_SECRET
JWT_ALGORITHM = "HS256"


async def _resolve_admin_user_by_token(token: str, session: AsyncSession) -> AdminUser:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Невалидный токен",
            )
        # Конвертируем строку в int (JWT хранит sub как строку)
        user_id = int(user_id_str)
    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
        )
    
    # Проверяем, что пользователь существует и является админом
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещен",
        )
    
    # Получаем профиль админа
    result = await session.execute(
        select(AdminUser).where(AdminUser.user_id == user.id)
    )
    admin_user = result.scalar_one_or_none()
    
    if admin_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Профиль админа не найден",
        )
    
    return admin_user


async def get_current_admin_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminUser:
    """
    Проверяет JWT токен из заголовка Authorization и возвращает текущего админа.
    """
    token = credentials.credentials
    return await _resolve_admin_user_by_token(token, session)


async def get_current_admin_user_optional_token(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(optional_security)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminUser:
    """
    Поддерживает авторизацию через заголовок Authorization или query-параметр token.
    Используется для SSE эндпоинтов, где невозможно передать заголовки.
    """
    token: Optional[str] = credentials.credentials if credentials else None
    if not token:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется токен авторизации",
        )

    return await _resolve_admin_user_by_token(token, session)


def require_permission(permission: str):
    """
    Декоратор для проверки конкретного права доступа.
    
    Args:
        permission: Название права ('can_manage_keys', 'can_view_stats', 'can_manage_users')
    """
    async def permission_checker(
        admin_user: Annotated[AdminUser, Depends(get_current_admin_user)]
    ) -> AdminUser:
        if not getattr(admin_user, permission, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Недостаточно прав: требуется {permission}",
            )
        return admin_user
    
    return permission_checker


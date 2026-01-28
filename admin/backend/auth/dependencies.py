# -*- coding: utf-8 -*-
"""
FastAPI зависимости для авторизации в админ-панели.

Предоставляет зависимости для:
- Получения текущего пользователя из JWT токена
- Проверки активности пользователя
- Проверки роли администратора
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from admin.backend.auth.jwt import verify_token
from admin.backend.database import get_db_session
from src.db.models import AdminUser

# Константы ролей (теперь храним как строки в БД)
ROLE_ADMIN = "admin"
ROLE_USER = "user"

# Схема авторизации Bearer token
oauth2_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    """
    Контекст текущего авторизованного пользователя.
    
    Содержит данные пользователя из БД и информацию из токена.
    """
    def __init__(
        self,
        user: AdminUser,
        token_data: dict,
    ):
        self.user = user
        self.token_data = token_data
    
    @property
    def id(self) -> int:
        return self.user.id
    
    @property
    def username(self) -> str:
        return self.user.username
    
    @property
    def role(self) -> str:
        """Возвращает роль пользователя (строка: 'admin' или 'user')."""
        return self.user.role
    
    @property
    def is_admin(self) -> bool:
        """Проверяет, является ли пользователь администратором."""
        return self.user.role == ROLE_ADMIN
    
    @property
    def telegram_id(self) -> Optional[int]:
        return self.user.telegram_id
    
    @property
    def display_name(self) -> str:
        return self.user.display_name or self.user.username


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
    """
    Получает текущего пользователя из JWT токена.
    
    Извлекает токен из заголовка Authorization: Bearer <token>,
    проверяет его и загружает пользователя из БД.
    
    Args:
        credentials: HTTP credentials из заголовка Authorization
        db: Сессия базы данных
        
    Returns:
        CurrentUser с данными пользователя
        
    Raises:
        HTTPException 401: Если токен отсутствует или невалидный
        HTTPException 401: Если пользователь не найден в БД
    """
    # Проверяем наличие токена
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Проверяем токен
    token_data = verify_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или истёкший токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверяем тип токена
    if token_data.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный тип токена",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Получаем user_id из токена
    user_id = token_data.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен не содержит информацию о пользователе",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Загружаем пользователя из БД
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный ID пользователя в токене",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id_int)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return CurrentUser(user=user, token_data=token_data)


async def get_current_active_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Проверяет, что текущий пользователь активен.
    
    Args:
        current_user: Текущий пользователь из get_current_user
        
    Returns:
        CurrentUser если пользователь активен
        
    Raises:
        HTTPException 403: Если пользователь деактивирован
    """
    if not current_user.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован",
        )
    
    return current_user


async def require_admin(
    current_user: CurrentUser = Depends(get_current_active_user),
) -> CurrentUser:
    """
    Проверяет, что текущий пользователь является администратором.
    
    Используется для защиты эндпоинтов, доступных только админам.
    
    Args:
        current_user: Текущий активный пользователь
        
    Returns:
        CurrentUser если пользователь — админ
        
    Raises:
        HTTPException 403: Если пользователь не админ
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    
    return current_user


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme),
) -> Optional[dict]:
    """
    Опционально получает данные из токена (без загрузки из БД).
    
    Не выбрасывает исключение если токен отсутствует.
    Используется для публичных эндпоинтов с опциональной авторизацией.
    
    Args:
        credentials: HTTP credentials из заголовка Authorization
        
    Returns:
        Данные токена или None
    """
    if credentials is None:
        return None
    
    token_data = verify_token(credentials.credentials)
    return token_data

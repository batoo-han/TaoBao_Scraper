"""
Сервис аутентификации для админ-панели.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.models import AdminUser, User

# Контекст для хеширования паролей
# Используем argon2 как основной алгоритм (без ограничения 72 байта)
# bcrypt оставляем как fallback для совместимости
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    default="argon2",
    deprecated="auto",
    argon2__memory_cost=65536,  # 64 MB
    argon2__time_cost=3,  # 3 итерации
    argon2__parallelism=4,  # 4 потока
)

# JWT настройки
JWT_SECRET_KEY = settings.ADMIN_JWT_SECRET
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


class AuthService:
    """Сервис для аутентификации админов."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Проверяет пароль.
        
        Использует Argon2 (без ограничения длины) или bcrypt (fallback).
        """
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        Хеширует пароль.
        
        Использует Argon2 по умолчанию (без ограничения 72 байта).
        Bcrypt используется только как fallback для старых хешей.
        """
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Создает JWT токен."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Аутентифицирует пользователя по admin_username и паролю.
        
        Примечание: В текущей версии пароли админов хранятся в поле `notes` таблицы `admin_users`.
        В будущем это нужно заменить на отдельную таблицу с хешированными паролями.
        
        Args:
            username: Имя пользователя для входа (admin_username из AdminUser)
            password: Пароль админа
            
        Returns:
            User если аутентификация успешна, иначе None
        """
        # Ищем админа по admin_username
        result = await self.session.execute(
            select(AdminUser).where(AdminUser.admin_username == username)
        )
        admin_user = result.scalar_one_or_none()
        
        if admin_user is None:
            return None
        
        # Получаем пользователя
        result = await self.session.execute(
            select(User).where(User.id == admin_user.user_id)
        )
        user = result.scalar_one_or_none()
        
        if user is None or not user.is_admin:
            return None
        
        # Временная реализация: пароль хранится в notes (для MVP)
        # TODO: Создать отдельную таблицу admin_passwords с хешированными паролями
        stored_password_hash = admin_user.notes
        
        if not stored_password_hash:
            return None
        
        # Проверяем пароль
        if not self.verify_password(password, stored_password_hash):
            return None
        
        return user
    
    async def set_admin_password(self, user_id: int, password: str, admin_username: Optional[str] = None) -> None:
        """
        Устанавливает пароль и имя пользователя для админа.
        
        Args:
            user_id: ID пользователя
            password: Новый пароль (будет захеширован)
            admin_username: Имя пользователя для входа (если указано, будет обновлено)
        """
        result = await self.session.execute(
            select(AdminUser).where(AdminUser.user_id == user_id)
        )
        admin_user = result.scalar_one_or_none()
        
        if admin_user is None:
            raise ValueError(f"Admin user {user_id} not found")
        
        # Обновляем имя пользователя, если указано
        if admin_username:
            admin_user.admin_username = admin_username
        
        # Хешируем пароль и сохраняем в notes (временное решение)
        # TODO: Переместить в отдельную таблицу
        admin_user.notes = self.get_password_hash(password)
        await self.session.flush()


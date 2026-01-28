# -*- coding: utf-8 -*-
"""
JWT токены для аутентификации в админ-панели.

Реализует:
- Генерация access и refresh токенов
- Валидация токенов
- Хэширование паролей (bcrypt)
- Хэширование refresh токенов (SHA-256)
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from admin.backend.config import admin_settings

# Контекст для хэширования паролей.
#
# ВАЖНО (практика для Windows/.venv):
# На Windows у связки passlib + bcrypt периодически возникают проблемы совместимости
# версий (например, ошибка вида "module 'bcrypt' has no attribute '__about__'").
# Чтобы админка запускалась стабильно без плясок с бинарными зависимостями,
# используем PBKDF2-SHA256 (не требует пакета `bcrypt`).
#
# Это безопасный и широко поддерживаемый алгоритм для хэширования паролей.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
    pbkdf2_sha256__default_rounds=310_000,  # сбалансировано для 2026 года
)


def hash_password(password: str) -> str:
    """
    Хэширует пароль безопасным образом.
    
    Используем PBKDF2-SHA256, чтобы:
    - корректно обрабатывать любые длины паролей,
    - избежать проблем совместимости `bcrypt` на Windows,
    - сохранять хорошую криптостойкость.
    
    Args:
        password: Пароль в открытом виде
        
    Returns:
        Хэш пароля
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие пароля хэшу.
    
    Args:
        plain_password: Пароль в открытом виде
        hashed_password: Хэш пароля
        
    Returns:
        True если пароль верный, False иначе
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def hash_token(token: str) -> str:
    """
    Хэширует токен с использованием SHA-256.
    
    Используется для хранения refresh токенов в БД.
    
    Args:
        token: Токен в открытом виде
        
    Returns:
        SHA-256 хэш токена
    """
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token_string(length: int = 32) -> str:
    """
    Генерирует криптографически безопасную случайную строку.
    
    Args:
        length: Длина строки в байтах (результат будет в 2 раза длиннее в hex)
        
    Returns:
        Случайная hex-строка
    """
    return secrets.token_hex(length)


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Создаёт JWT access token.
    
    Args:
        data: Данные для включения в токен (обычно user_id, username, role)
        expires_delta: Время жизни токена (по умолчанию из настроек)
        
    Returns:
        JWT access token
    """
    to_encode = data.copy()
    
    # Время истечения
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=admin_settings.ADMIN_JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        admin_settings.ADMIN_JWT_SECRET,
        algorithm=admin_settings.ADMIN_JWT_ALGORITHM,
    )
    
    return encoded_jwt


def create_refresh_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, str, datetime]:
    """
    Создаёт refresh token.
    
    Refresh token — это случайная строка, хэш которой хранится в БД.
    
    Args:
        user_id: ID пользователя
        expires_delta: Время жизни токена (по умолчанию из настроек)
        
    Returns:
        Кортеж (token, token_hash, expires_at)
    """
    # Генерируем случайный токен
    token = generate_token_string(32)
    token_hash = hash_token(token)
    
    # Время истечения (naive UTC для совместимости с PostgreSQL TIMESTAMP WITHOUT TIME ZONE)
    if expires_delta:
        expires_at = datetime.utcnow() + expires_delta
    else:
        expires_at = datetime.utcnow() + timedelta(
            days=admin_settings.ADMIN_JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )
    
    return token, token_hash, expires_at


def verify_token(token: str) -> Optional[dict[str, Any]]:
    """
    Проверяет и декодирует JWT токен.
    
    Args:
        token: JWT токен
        
    Returns:
        Декодированные данные токена или None если токен невалидный
    """
    try:
        payload = jwt.decode(
            token,
            admin_settings.ADMIN_JWT_SECRET,
            algorithms=[admin_settings.ADMIN_JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        return None


def decode_token_unsafe(token: str) -> Optional[dict[str, Any]]:
    """
    Декодирует JWT токен без проверки подписи и срока действия.
    
    Используется для получения информации из истёкшего токена.
    ВНИМАНИЕ: Не использовать для аутентификации!
    
    Args:
        token: JWT токен
        
    Returns:
        Декодированные данные токена или None при ошибке
    """
    try:
        payload = jwt.decode(
            token,
            admin_settings.ADMIN_JWT_SECRET,
            algorithms=[admin_settings.ADMIN_JWT_ALGORITHM],
            options={"verify_exp": False, "verify_signature": False},
        )
        return payload
    except JWTError:
        return None

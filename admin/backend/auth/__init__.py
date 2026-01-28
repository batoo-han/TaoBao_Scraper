# -*- coding: utf-8 -*-
"""
Модуль аутентификации админ-панели.

Содержит:
- jwt: Генерация и валидация JWT токенов
- telegram: Валидация Telegram Login Widget
- dependencies: FastAPI зависимости для авторизации
"""

from admin.backend.auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_token,
    hash_password,
    verify_password,
    hash_token,
)
from admin.backend.auth.telegram import verify_telegram_auth
from admin.backend.auth.dependencies import (
    get_current_user,
    get_current_active_user,
    require_admin,
)

__all__ = [
    # JWT
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "hash_password",
    "verify_password",
    "hash_token",
    # Telegram
    "verify_telegram_auth",
    # Dependencies
    "get_current_user",
    "get_current_active_user",
    "require_admin",
]

# -*- coding: utf-8 -*-
"""
API роутеры админ-панели.

Содержит:
- auth: Аутентификация
- users: Управление пользователями бота
- stats: Статистика
- settings: Настройки бота
- admin_users: Управление пользователями админки
- access: Контроль доступа
"""

from admin.backend.routers import auth, users, stats, settings, admin_users, access

__all__ = [
    "auth",
    "users",
    "stats",
    "settings",
    "admin_users",
    "access",
]

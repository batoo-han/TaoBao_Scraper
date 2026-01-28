# -*- coding: utf-8 -*-
"""
Pydantic модели (схемы) для админ-панели.

Содержит:
- auth: Схемы аутентификации (логин, токены)
- user: Схемы пользователей бота
- stats: Схемы статистики
- settings: Схемы настроек
"""

from admin.backend.models.auth import (
    LoginRequest,
    LoginResponse,
    TelegramLoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    ChangePasswordRequest,
    AdminUserResponse,
    AdminUserCreate,
    AdminUserUpdate,
)
from admin.backend.models.user import (
    BotUserResponse,
    BotUserListResponse,
    BotUserSettingsUpdate,
    BotUserLimitsUpdate,
    AccessListUpdate,
)
from admin.backend.models.stats import (
    StatsOverview,
    StatsRequestsResponse,
    StatsCostsResponse,
    StatsPlatformsResponse,
    StatsTopUsersResponse,
    StatsPeaksResponse,
)
from admin.backend.models.settings import (
    AdminSettingsResponse,
    AdminSettingsUpdate,
    LLMSettingsResponse,
    LLMSettingsUpdate,
    AccessSettingsResponse,
    AccessSettingsUpdate,
    LimitsSettingsResponse,
    LimitsSettingsUpdate,
)

__all__ = [
    # Auth
    "LoginRequest",
    "LoginResponse",
    "TelegramLoginRequest",
    "RefreshTokenRequest",
    "RefreshTokenResponse",
    "ChangePasswordRequest",
    "AdminUserResponse",
    "AdminUserCreate",
    "AdminUserUpdate",
    # User
    "BotUserResponse",
    "BotUserListResponse",
    "BotUserSettingsUpdate",
    "BotUserLimitsUpdate",
    "AccessListUpdate",
    # Stats
    "StatsOverview",
    "StatsRequestsResponse",
    "StatsCostsResponse",
    "StatsPlatformsResponse",
    "StatsTopUsersResponse",
    "StatsPeaksResponse",
    # Settings
    "AdminSettingsResponse",
    "AdminSettingsUpdate",
    "LLMSettingsResponse",
    "LLMSettingsUpdate",
    "AccessSettingsResponse",
    "AccessSettingsUpdate",
    "LimitsSettingsResponse",
    "LimitsSettingsUpdate",
]

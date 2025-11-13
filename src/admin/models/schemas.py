"""
Pydantic схемы для API админ-панели.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Аутентификация
# ============================================================================

class LoginRequest(BaseModel):
    """Запрос на вход в админ-панель."""
    username: str = Field(..., description="Имя пользователя (Telegram username)")
    password: str = Field(..., description="Пароль админа")


class LoginResponse(BaseModel):
    """Ответ на успешный вход."""
    access_token: str
    token_type: str = "bearer"
    user: "AdminUserInfo"


class AdminUserInfo(BaseModel):
    """Информация об админе."""
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    can_manage_keys: bool
    can_view_stats: bool
    can_manage_users: bool

    class Config:
        from_attributes = True


# ============================================================================
# Настройки приложения
# ============================================================================

class AppSettingsResponse(BaseModel):
    """Текущие настройки приложения."""
    active_llm_vendor: str
    llm_config: Dict[str, Any]
    consent_text: str
    app_config: Dict[str, Any]
    stored_app_config: Dict[str, Any] = Field(default_factory=dict)
    platforms_config: Dict[str, Any]
    pending_restart_config: Dict[str, Any] = Field(default_factory=dict)
    restart_required: bool = False
    updated_at: datetime


class LLMProviderUpdate(BaseModel):
    """Обновление активного LLM провайдера."""
    vendor: Literal["yandex", "openai", "proxiapi"]
    config: Optional[Dict[str, Any]] = None


class ConsentTextUpdate(BaseModel):
    """Обновление текста согласия."""
    text: str = Field(..., min_length=10, description="Текст согласия на обработку ПД")


class AppConfigUpdate(BaseModel):
    """Обновление настроек приложения."""
    config: Dict[str, Any] = Field(..., description="Словарь с настройками для обновления")


class AppConfigUpdateResponse(BaseModel):
    """Результат обновления настроек приложения."""
    settings: AppSettingsResponse
    applied_keys: List[str] = Field(default_factory=list)
    pending_restart_keys: List[str] = Field(default_factory=list)
    message: Optional[str] = None


class LLMPromptConfig(BaseModel):
    """Настройки промпта для LLM."""
    prompt_template: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="Температура генерации (0.0-1.0)")
    max_tokens: Optional[int] = Field(None, ge=1, le=10000, description="Максимальное количество токенов")


class PlatformConfigUpdate(BaseModel):
    """Обновление настройки платформы."""
    platform: Literal["taobao", "pinduoduo", "szwego", "1688"]
    enabled: bool


# ============================================================================
# LLM Провайдеры
# ============================================================================

class ProviderField(BaseModel):
    """Описание поля конфигурации провайдера."""
    key: str
    label: str
    type: Literal["text", "password", "number", "select"] = "text"
    required: bool = False
    placeholder: Optional[str] = None
    help: Optional[str] = None
    secret: bool = False
    choices: Optional[List[str]] = None


class ProviderInfo(BaseModel):
    """Информация о провайдере."""
    vendor: str
    name: str
    is_active: bool
    config: Dict[str, Any]
    config_fields: List[ProviderField]
    filled_fields: Dict[str, bool] = Field(default_factory=dict)
    missing_required_fields: List[str] = Field(default_factory=list)
    config_ready: bool = False


class ProviderConfigUpdate(BaseModel):
    """Запрос на обновление настроек провайдера."""
    activate: bool = False
    config: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Статистика
# ============================================================================

class StatsOverview(BaseModel):
    """Общая статистика."""
    total_users: int
    active_users_30d: int
    total_requests: int
    total_tokens: int
    active_provider: str
    cache_hit_rate: float
    requests_today: int
    requests_this_week: int
    requests_this_month: int


class UserStatsInfo(BaseModel):
    """Статистика по пользователю."""
    user_id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    total_requests: int
    total_tokens: int
    last_request_at: Optional[datetime]


class ProviderStatsInfo(BaseModel):
    """Статистика по провайдеру."""
    vendor: str
    total_requests: int
    total_tokens: int
    unique_users: int
    cache_hits: int
    cache_misses: int


class PlatformStatsInfo(BaseModel):
    """Статистика по платформе (магазину)."""
    platform: str
    enabled: bool
    total_requests: int
    last_request_at: Optional[datetime]


# ============================================================================
# Пользователи
# ============================================================================

class UserSettingsInfo(BaseModel):
    """Настройки пользователя."""
    signature: str
    default_currency: str
    exchange_rate: Optional[float]
    exchange_rate_at: Optional[datetime]


class UserInfo(BaseModel):
    """Информация о пользователе."""
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    language_code: Optional[str]
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime]
    settings: Optional[UserSettingsInfo] = None

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Список пользователей с пагинацией."""
    users: List[UserInfo]
    total: int
    page: int
    page_size: int
    total_pages: int


class UserUpdate(BaseModel):
    """Обновление пользователя."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: Optional[bool] = None


# ============================================================================
# Аудит персональных данных
# ============================================================================

class AuditLogInfo(BaseModel):
    """Запись аудита."""
    id: int
    actor_id: Optional[int]
    actor_username: Optional[str]
    target_user_id: Optional[int]
    target_username: Optional[str]
    action: str
    details: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Список записей аудита с пагинацией."""
    logs: List[AuditLogInfo]
    total: int
    page: int
    page_size: int
    total_pages: int


# -*- coding: utf-8 -*-
"""
Pydantic схемы для настроек бота.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ==================== LLM настройки ====================

class LLMSettingsResponse(BaseModel):
    """Настройки LLM провайдеров."""
    default_llm: str = Field(..., description="Провайдер по умолчанию (yandex/openai/proxyapi)")
    yandex_model: str = Field(..., description="Модель YandexGPT")
    openai_model: str = Field(..., description="Модель OpenAI")
    translate_provider: str = Field(..., description="Провайдер для переводов")
    translate_model: str = Field(..., description="Модель для переводов")
    translate_legacy: bool = Field(..., description="Использовать legacy Yandex Translate")


class LLMSettingsUpdate(BaseModel):
    """Обновление настроек LLM."""
    default_llm: Optional[str] = Field(None, pattern="^(yandex|openai|proxyapi)$")
    yandex_model: Optional[str] = Field(None, max_length=100)
    openai_model: Optional[str] = Field(None, max_length=100)
    translate_provider: Optional[str] = Field(None, pattern="^(yandex|openai|proxyapi)$")
    translate_model: Optional[str] = Field(None, max_length=100)
    translate_legacy: Optional[bool] = Field(None)


# ==================== Настройки доступа ====================

class AccessSettingsResponse(BaseModel):
    """Настройки контроля доступа."""
    whitelist_enabled: bool = Field(..., description="Белый список включен")
    blacklist_enabled: bool = Field(..., description="Чёрный список включен")
    whitelist_count: int = Field(..., description="Записей в белом списке")
    blacklist_count: int = Field(..., description="Записей в чёрном списке")


class AccessSettingsUpdate(BaseModel):
    """Обновление настроек доступа."""
    whitelist_enabled: Optional[bool] = Field(None)
    blacklist_enabled: Optional[bool] = Field(None)


# ==================== Настройки лимитов ====================

class LimitsSettingsResponse(BaseModel):
    """Глобальные настройки лимитов."""
    per_user_daily_limit: Optional[int] = Field(None, description="Дневной лимит на пользователя")
    per_user_monthly_limit: Optional[int] = Field(None, description="Месячный лимит на пользователя")
    total_daily_limit: Optional[int] = Field(None, description="Общий дневной лимит")
    total_monthly_limit: Optional[int] = Field(None, description="Общий месячный лимит")


class LimitsSettingsUpdate(BaseModel):
    """Обновление настроек лимитов."""
    per_user_daily_limit: Optional[int] = Field(None, ge=0, description="0 = безлимит")
    per_user_monthly_limit: Optional[int] = Field(None, ge=0, description="0 = безлимит")
    total_daily_limit: Optional[int] = Field(None, ge=0, description="0 = безлимит")
    total_monthly_limit: Optional[int] = Field(None, ge=0, description="0 = безлимит")


# ==================== Общие настройки ====================

class AdminSettingsResponse(BaseModel):
    """Все глобальные настройки администратора."""
    # LLM
    default_llm: str = Field(...)
    yandex_model: str = Field(...)
    openai_model: str = Field(...)
    translate_provider: str = Field(...)
    translate_model: str = Field(...)
    translate_legacy: bool = Field(...)
    
    # Флаги
    convert_currency: bool = Field(...)
    tmapi_notify_439: bool = Field(...)
    debug_mode: bool = Field(...)
    mock_mode: bool = Field(...)
    
    # Каналы
    forward_channel_id: str = Field(...)
    
    # Лимиты
    per_user_daily_limit: Optional[int] = Field(None)
    per_user_monthly_limit: Optional[int] = Field(None)
    total_daily_limit: Optional[int] = Field(None)
    total_monthly_limit: Optional[int] = Field(None)
    
    class Config:
        from_attributes = True


class AdminSettingsUpdate(BaseModel):
    """Обновление всех глобальных настроек."""
    # LLM
    default_llm: Optional[str] = Field(None, pattern="^(yandex|openai|proxyapi)$")
    yandex_model: Optional[str] = Field(None, max_length=100)
    openai_model: Optional[str] = Field(None, max_length=100)
    translate_provider: Optional[str] = Field(None, pattern="^(yandex|openai|proxyapi)$")
    translate_model: Optional[str] = Field(None, max_length=100)
    translate_legacy: Optional[bool] = Field(None)
    
    # Флаги
    convert_currency: Optional[bool] = Field(None)
    tmapi_notify_439: Optional[bool] = Field(None)
    debug_mode: Optional[bool] = Field(None)
    mock_mode: Optional[bool] = Field(None)
    
    # Каналы
    forward_channel_id: Optional[str] = Field(None, max_length=255)
    
    # Лимиты
    per_user_daily_limit: Optional[int] = Field(None, ge=0)
    per_user_monthly_limit: Optional[int] = Field(None, ge=0)
    total_daily_limit: Optional[int] = Field(None, ge=0)
    total_monthly_limit: Optional[int] = Field(None, ge=0)


class FeatureFlagsResponse(BaseModel):
    """Флаги функций бота."""
    convert_currency: bool = Field(..., description="Конвертировать цены в рубли")
    tmapi_notify_439: bool = Field(..., description="Уведомлять об ошибке TMAPI 439")
    debug_mode: bool = Field(..., description="Режим отладки")
    mock_mode: bool = Field(..., description="Mock режим")
    forward_channel_id: str = Field(..., description="Канал для дублирования постов")


class FeatureFlagsUpdate(BaseModel):
    """Обновление флагов функций."""
    convert_currency: Optional[bool] = Field(None)
    tmapi_notify_439: Optional[bool] = Field(None)
    debug_mode: Optional[bool] = Field(None)
    mock_mode: Optional[bool] = Field(None)
    forward_channel_id: Optional[str] = Field(None, max_length=255)

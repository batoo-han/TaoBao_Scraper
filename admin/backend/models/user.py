# -*- coding: utf-8 -*-
"""
Pydantic схемы для управления пользователями бота.
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ==================== Запросы ====================

class BotUserCreate(BaseModel):
    """Создание нового пользователя бота."""
    user_id: int = Field(..., description="Telegram ID пользователя")
    username: Optional[str] = Field(None, max_length=255, description="Telegram username (без @)")


class BotUserSettingsUpdate(BaseModel):
    """Обновление настроек пользователя бота."""
    signature: Optional[str] = Field(None, max_length=500, description="Подпись для постов")
    default_currency: Optional[str] = Field(None, pattern="^(cny|rub)$", description="Валюта по умолчанию")
    exchange_rate: Optional[float] = Field(None, gt=0, description="Курс обмена")
    price_mode: Optional[str] = Field(None, pattern="^(simple|advanced|)$", description="Режим цен")


class BotUserLimitsUpdate(BaseModel):
    """Обновление лимитов пользователя бота."""
    daily_limit: Optional[int] = Field(None, ge=0, description="Дневной лимит (0 = безлимит)")
    monthly_limit: Optional[int] = Field(None, ge=0, description="Месячный лимит (0 = безлимит)")


class AccessListUpdate(BaseModel):
    """Обновление списков доступа (белый/чёрный)."""
    whitelist_enabled: Optional[bool] = Field(None, description="Включить белый список")
    blacklist_enabled: Optional[bool] = Field(None, description="Включить чёрный список")
    add_whitelist_ids: Optional[List[int]] = Field(None, description="ID для добавления в белый список")
    add_whitelist_usernames: Optional[List[str]] = Field(None, description="Usernames для добавления в белый список")
    remove_whitelist_ids: Optional[List[int]] = Field(None, description="ID для удаления из белого списка")
    remove_whitelist_usernames: Optional[List[str]] = Field(None, description="Usernames для удаления из белого списка")
    add_blacklist_ids: Optional[List[int]] = Field(None, description="ID для добавления в чёрный список")
    add_blacklist_usernames: Optional[List[str]] = Field(None, description="Usernames для добавления в чёрный список")
    remove_blacklist_ids: Optional[List[int]] = Field(None, description="ID для удаления из чёрного списка")
    remove_blacklist_usernames: Optional[List[str]] = Field(None, description="Usernames для удаления из чёрного списка")


# ==================== Ответы ====================

class BotUserSettingsResponse(BaseModel):
    """Настройки пользователя бота."""
    signature: str = Field("", description="Подпись для постов")
    default_currency: str = Field("cny", description="Валюта по умолчанию")
    exchange_rate: Optional[float] = Field(None, description="Курс обмена")
    price_mode: str = Field("", description="Режим цен")
    daily_limit: Optional[int] = Field(None, description="Индивидуальный дневной лимит")
    monthly_limit: Optional[int] = Field(None, description="Индивидуальный месячный лимит")
    
    class Config:
        from_attributes = True


class BotUserLimitsResponse(BaseModel):
    """Лимиты и использование пользователя бота."""
    day_start: Optional[date] = Field(None, description="Начало текущего дня")
    day_count: int = Field(0, description="Запросов за день")
    month_start: Optional[date] = Field(None, description="Начало текущего месяца")
    month_count: int = Field(0, description="Запросов за месяц")
    day_cost: float = Field(0.0, description="Стоимость за день (USD)")
    month_cost: float = Field(0.0, description="Стоимость за месяц (USD)")
    
    class Config:
        from_attributes = True


class BotUserAccessStatus(BaseModel):
    """Статус доступа пользователя бота."""
    in_whitelist: bool = Field(False, description="В белом списке")
    in_blacklist: bool = Field(False, description="В чёрном списке")
    whitelist_type: Optional[str] = Field(None, description="Тип записи в белом списке (id/username)")
    blacklist_type: Optional[str] = Field(None, description="Тип записи в чёрном списке (id/username)")


class BotUserResponse(BaseModel):
    """Полные данные пользователя бота."""
    user_id: int = Field(..., description="Telegram ID")
    username: Optional[str] = Field(None, description="Telegram username")
    created_at: date = Field(..., description="Дата регистрации")
    settings: Optional[BotUserSettingsResponse] = Field(None, description="Настройки")
    limits: Optional[BotUserLimitsResponse] = Field(None, description="Лимиты и использование")
    access: BotUserAccessStatus = Field(..., description="Статус доступа")
    
    # Статистика
    total_requests: int = Field(0, description="Всего запросов")
    total_cost: float = Field(0.0, description="Общая стоимость (USD)")
    last_request_at: Optional[datetime] = Field(None, description="Время последнего запроса")
    
    class Config:
        from_attributes = True


class BotUserListResponse(BaseModel):
    """Список пользователей бота с пагинацией."""
    items: List[BotUserResponse] = Field(..., description="Список пользователей")
    total: int = Field(..., description="Общее количество")
    page: int = Field(..., description="Текущая страница")
    per_page: int = Field(..., description="Элементов на странице")
    pages: int = Field(..., description="Всего страниц")


class AccessListEntry(BaseModel):
    """Запись в списке доступа."""
    entry_type: str = Field(..., description="Тип записи (id/username)")
    value: str = Field(..., description="Значение")


class AccessListsResponse(BaseModel):
    """Текущее состояние списков доступа."""
    whitelist_enabled: bool = Field(..., description="Белый список включен")
    blacklist_enabled: bool = Field(..., description="Чёрный список включен")
    whitelist: List[AccessListEntry] = Field(..., description="Записи белого списка")
    blacklist: List[AccessListEntry] = Field(..., description="Записи чёрного списка")

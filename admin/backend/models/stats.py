# -*- coding: utf-8 -*-
"""
Pydantic схемы для статистики.
"""

from datetime import date as dt_date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ==================== Вспомогательные модели ====================

class TimeSeriesPoint(BaseModel):
    """Точка временного ряда."""
    # ВАЖНО:
    # Поле называется `day`, но сериализуется/принимается как `date`.
    # Это сделано, чтобы избежать конфликта имени поля `date` с типом `date`
    # в Pydantic v2 (иначе может возникать PydanticUserError).
    day: dt_date = Field(..., validation_alias="date", serialization_alias="date", description="Дата")
    value: float = Field(..., description="Значение")


class PlatformStats(BaseModel):
    """Статистика по платформе."""
    platform: str = Field(..., description="Название платформы")
    requests: int = Field(..., description="Количество запросов")
    cost: float = Field(..., description="Стоимость (USD)")
    percentage: float = Field(..., description="Процент от общего")


class TopUser(BaseModel):
    """Топ пользователь по активности."""
    user_id: int = Field(..., description="Telegram ID")
    username: Optional[str] = Field(None, description="Telegram username")
    requests: int = Field(..., description="Количество запросов")
    cost: float = Field(..., description="Стоимость (USD)")


class PeakHour(BaseModel):
    """Пик активности по часам."""
    hour: int = Field(..., ge=0, le=23, description="Час (0-23)")
    requests: int = Field(..., description="Количество запросов")
    avg_requests: float = Field(..., description="Среднее за период")


class RequestLogEntry(BaseModel):
    """Запись лога запроса."""
    id: int = Field(..., description="ID записи")
    user_id: Optional[int] = Field(None, description="Telegram ID")
    username: Optional[str] = Field(None, description="Telegram username")
    request_time: datetime = Field(..., description="Время запроса")
    platform: Optional[str] = Field(None, description="Платформа")
    product_url: Optional[str] = Field(None, description="URL товара")
    duration_ms: Optional[int] = Field(None, description="Время обработки (мс)")
    total_tokens: Optional[int] = Field(None, description="Всего токенов")
    total_cost: Optional[float] = Field(None, description="Стоимость (USD)")
    cache_hits: Optional[int] = Field(None, description="Попадания в кэш")
    
    class Config:
        from_attributes = True


# ==================== Ответы ====================

class StatsOverview(BaseModel):
    """Сводная статистика для Dashboard."""
    
    # Пользователи
    total_users: int = Field(..., description="Всего пользователей")
    active_users_today: int = Field(..., description="Активных сегодня")
    active_users_month: int = Field(..., description="Активных за месяц")
    new_users_today: int = Field(..., description="Новых сегодня")
    new_users_month: int = Field(..., description="Новых за месяц")
    
    # Запросы
    requests_today: int = Field(..., description="Запросов сегодня")
    requests_month: int = Field(..., description="Запросов за месяц")
    requests_total: int = Field(..., description="Всего запросов")
    
    # Расходы
    cost_today: float = Field(..., description="Расходы сегодня (USD)")
    cost_month: float = Field(..., description="Расходы за месяц (USD)")
    cost_total: float = Field(..., description="Общие расходы (USD)")
    
    # Кэш
    cache_hit_rate: float = Field(..., description="Процент попаданий в кэш")
    cache_saved_cost: float = Field(..., description="Сэкономлено на кэше (USD)")
    
    # Лимиты (глобальные)
    daily_limit: Optional[int] = Field(None, description="Дневной лимит")
    daily_used: int = Field(0, description="Использовано сегодня")
    monthly_limit: Optional[int] = Field(None, description="Месячный лимит")
    monthly_used: int = Field(0, description="Использовано за месяц")


class StatsRequestsResponse(BaseModel):
    """Статистика запросов с фильтрами."""
    items: List[RequestLogEntry] = Field(..., description="Список запросов")
    total: int = Field(..., description="Общее количество")
    page: int = Field(..., description="Текущая страница")
    per_page: int = Field(..., description="Элементов на странице")
    pages: int = Field(..., description="Всего страниц")
    
    # Агрегаты для выбранного периода
    total_requests: int = Field(..., description="Всего запросов за период")
    total_cost: float = Field(..., description="Общая стоимость за период")
    total_tokens: int = Field(..., description="Всего токенов за период")
    avg_duration_ms: float = Field(..., description="Среднее время обработки")


class StatsCostsResponse(BaseModel):
    """Статистика расходов по периодам."""
    period_start: dt_date = Field(..., description="Начало периода")
    period_end: dt_date = Field(..., description="Конец периода")
    total_cost: float = Field(..., description="Общая стоимость")
    daily_costs: List[TimeSeriesPoint] = Field(..., description="Расходы по дням")
    by_platform: List[PlatformStats] = Field(..., description="Расходы по платформам")
    avg_cost_per_request: float = Field(..., description="Средняя стоимость запроса")
    avg_cost_per_user: float = Field(..., description="Средняя стоимость на пользователя")


class StatsPlatformsResponse(BaseModel):
    """Статистика по платформам."""
    period_start: dt_date = Field(..., description="Начало периода")
    period_end: dt_date = Field(..., description="Конец периода")
    platforms: List[PlatformStats] = Field(..., description="Статистика по платформам")
    total_requests: int = Field(..., description="Всего запросов")


class StatsTopUsersResponse(BaseModel):
    """Топ активных пользователей."""
    period_start: dt_date = Field(..., description="Начало периода")
    period_end: dt_date = Field(..., description="Конец периода")
    top_users: List[TopUser] = Field(..., description="Топ пользователей")
    limit: int = Field(..., description="Размер топа")


class StatsPeaksResponse(BaseModel):
    """Пики активности."""
    period_start: dt_date = Field(..., description="Начало периода")
    period_end: dt_date = Field(..., description="Конец периода")
    hourly_distribution: List[PeakHour] = Field(..., description="Распределение по часам")
    peak_hour: int = Field(..., description="Час пиковой нагрузки")
    peak_requests: int = Field(..., description="Запросов в пиковый час")
    daily_requests: List[TimeSeriesPoint] = Field(..., description="Запросы по дням")

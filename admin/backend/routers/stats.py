# -*- coding: utf-8 -*-
"""
API роутер статистики.

Эндпоинты:
- GET /overview - Сводная статистика
- GET /requests - Статистика запросов
- GET /costs - Расходы по периодам
- GET /platforms - Статистика по платформам
- GET /users/top - Топ пользователей
- GET /peaks - Пики активности
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, extract

from admin.backend.database import get_db_session
from admin.backend.auth.dependencies import get_current_active_user, CurrentUser
from admin.backend.models.stats import (
    StatsOverview,
    StatsRequestsResponse,
    StatsCostsResponse,
    StatsPlatformsResponse,
    StatsTopUsersResponse,
    StatsPeaksResponse,
    RequestLogEntry,
    TimeSeriesPoint,
    PlatformStats,
    TopUser,
    PeakHour,
)
from src.db.models import (
    User,
    RequestStats,
    RateLimitGlobal,
    AdminSettings as BotAdminSettings,
)

router = APIRouter()
logger = logging.getLogger("admin.routers.stats")


def get_moscow_today() -> date:
    """Возвращает текущую дату по московскому времени."""
    # MSK = UTC+3
    return (datetime.now(timezone.utc) + timedelta(hours=3)).date()


def get_moscow_month_start() -> date:
    """Возвращает первый день текущего месяца по московскому времени."""
    today = get_moscow_today()
    return today.replace(day=1)


@router.get("/overview", response_model=StatsOverview)
async def get_stats_overview(
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение сводной статистики для Dashboard.
    """
    today = get_moscow_today()
    month_start = get_moscow_month_start()
    
    # Всего пользователей
    total_users_result = await db.execute(select(func.count(User.user_id)))
    total_users = total_users_result.scalar() or 0
    
    # Активные пользователи сегодня
    active_today_result = await db.execute(
        select(func.count(func.distinct(RequestStats.user_id)))
        .where(func.date(RequestStats.request_time) == today)
    )
    active_users_today = active_today_result.scalar() or 0
    
    # Активные пользователи за месяц
    active_month_result = await db.execute(
        select(func.count(func.distinct(RequestStats.user_id)))
        .where(func.date(RequestStats.request_time) >= month_start)
    )
    active_users_month = active_month_result.scalar() or 0
    
    # Новые пользователи сегодня
    new_today_result = await db.execute(
        select(func.count(User.user_id))
        .where(User.created_at == today)
    )
    new_users_today = new_today_result.scalar() or 0
    
    # Новые пользователи за месяц
    new_month_result = await db.execute(
        select(func.count(User.user_id))
        .where(User.created_at >= month_start)
    )
    new_users_month = new_month_result.scalar() or 0
    
    # Запросы сегодня
    requests_today_result = await db.execute(
        select(func.count(RequestStats.id))
        .where(func.date(RequestStats.request_time) == today)
    )
    requests_today = requests_today_result.scalar() or 0
    
    # Запросы за месяц
    requests_month_result = await db.execute(
        select(func.count(RequestStats.id))
        .where(func.date(RequestStats.request_time) >= month_start)
    )
    requests_month = requests_month_result.scalar() or 0
    
    # Всего запросов
    requests_total_result = await db.execute(select(func.count(RequestStats.id)))
    requests_total = requests_total_result.scalar() or 0
    
    # Расходы сегодня
    cost_today_result = await db.execute(
        select(func.coalesce(func.sum(RequestStats.total_cost), 0.0))
        .where(func.date(RequestStats.request_time) == today)
    )
    cost_today = float(cost_today_result.scalar() or 0)
    
    # Расходы за месяц
    cost_month_result = await db.execute(
        select(func.coalesce(func.sum(RequestStats.total_cost), 0.0))
        .where(func.date(RequestStats.request_time) >= month_start)
    )
    cost_month = float(cost_month_result.scalar() or 0)
    
    # Общие расходы
    cost_total_result = await db.execute(
        select(func.coalesce(func.sum(RequestStats.total_cost), 0.0))
    )
    cost_total = float(cost_total_result.scalar() or 0)
    
    # Статистика кэша
    cache_result = await db.execute(
        select(
            func.coalesce(func.sum(RequestStats.cache_hits), 0),
            func.coalesce(func.sum(RequestStats.cache_misses), 0),
            func.coalesce(func.sum(RequestStats.cache_saved_cost), 0.0),
        )
    )
    cache_row = cache_result.one()
    cache_hits = cache_row[0] or 0
    cache_misses = cache_row[1] or 0
    cache_total = cache_hits + cache_misses
    cache_hit_rate = (cache_hits / cache_total * 100) if cache_total > 0 else 0.0
    cache_saved_cost = float(cache_row[2] or 0)
    
    # Глобальные лимиты
    limits_result = await db.execute(select(RateLimitGlobal).where(RateLimitGlobal.id == 1))
    rate_limits = limits_result.scalar_one_or_none()
    
    settings_result = await db.execute(select(BotAdminSettings).where(BotAdminSettings.id == 1))
    bot_settings = settings_result.scalar_one_or_none()
    
    daily_limit = bot_settings.total_daily_limit if bot_settings else None
    monthly_limit = bot_settings.total_monthly_limit if bot_settings else None
    daily_used = rate_limits.day_count if rate_limits else 0
    monthly_used = rate_limits.month_count if rate_limits else 0
    
    return StatsOverview(
        total_users=total_users,
        active_users_today=active_users_today,
        active_users_month=active_users_month,
        new_users_today=new_users_today,
        new_users_month=new_users_month,
        requests_today=requests_today,
        requests_month=requests_month,
        requests_total=requests_total,
        cost_today=cost_today,
        cost_month=cost_month,
        cost_total=cost_total,
        cache_hit_rate=round(cache_hit_rate, 2),
        cache_saved_cost=round(cache_saved_cost, 4),
        daily_limit=daily_limit,
        daily_used=daily_used,
        monthly_limit=monthly_limit,
        monthly_used=monthly_used,
    )


@router.get("/requests", response_model=StatsRequestsResponse)
async def get_stats_requests(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    date_from: Optional[date] = Query(None, description="Начало периода"),
    date_to: Optional[date] = Query(None, description="Конец периода"),
    platform: Optional[str] = Query(None, description="Фильтр по платформе"),
    user_id: Optional[int] = Query(None, description="Фильтр по пользователю"),
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение статистики запросов с фильтрами и пагинацией.
    """
    # Базовый запрос
    query = select(RequestStats)
    count_query = select(func.count(RequestStats.id))
    agg_query = select(
        func.count(RequestStats.id),
        func.coalesce(func.sum(RequestStats.total_cost), 0.0),
        func.coalesce(func.sum(RequestStats.total_tokens), 0),
        func.coalesce(func.avg(RequestStats.duration_ms), 0.0),
    )
    
    # Фильтры
    filters = []
    if date_from:
        filters.append(func.date(RequestStats.request_time) >= date_from)
    if date_to:
        filters.append(func.date(RequestStats.request_time) <= date_to)
    if platform:
        filters.append(RequestStats.platform == platform)
    if user_id:
        filters.append(RequestStats.user_id == user_id)
    
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))
        agg_query = agg_query.where(and_(*filters))
    
    # Общее количество
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Агрегаты
    agg_result = await db.execute(agg_query)
    agg_row = agg_result.one()
    total_requests = agg_row[0] or 0
    total_cost = float(agg_row[1] or 0)
    total_tokens = agg_row[2] or 0
    avg_duration_ms = float(agg_row[3] or 0)
    
    # Пагинация
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).order_by(RequestStats.request_time.desc())
    
    # Выполняем запрос
    result = await db.execute(query)
    requests = result.scalars().all()
    
    items = [RequestLogEntry.model_validate(r) for r in requests]
    pages = (total + per_page - 1) // per_page if total > 0 else 1
    
    return StatsRequestsResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        total_requests=total_requests,
        total_cost=round(total_cost, 4),
        total_tokens=total_tokens,
        avg_duration_ms=round(avg_duration_ms, 2),
    )


@router.get("/costs", response_model=StatsCostsResponse)
async def get_stats_costs(
    date_from: Optional[date] = Query(None, description="Начало периода"),
    date_to: Optional[date] = Query(None, description="Конец периода"),
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение статистики расходов по периодам.
    """
    # Значения по умолчанию - последние 30 дней
    if not date_to:
        date_to = get_moscow_today()
    if not date_from:
        date_from = date_to - timedelta(days=30)
    
    # Расходы по дням
    daily_query = (
        select(
            func.date(RequestStats.request_time).label("day"),
            func.coalesce(func.sum(RequestStats.total_cost), 0.0).label("cost"),
        )
        .where(and_(
            func.date(RequestStats.request_time) >= date_from,
            func.date(RequestStats.request_time) <= date_to,
        ))
        .group_by(func.date(RequestStats.request_time))
        .order_by(func.date(RequestStats.request_time))
    )
    
    daily_result = await db.execute(daily_query)
    daily_rows = daily_result.all()
    
    daily_costs = [
        TimeSeriesPoint(date=row.day, value=round(float(row.cost), 4))
        for row in daily_rows
    ]
    
    # Расходы по платформам
    platform_query = (
        select(
            RequestStats.platform,
            func.count(RequestStats.id).label("requests"),
            func.coalesce(func.sum(RequestStats.total_cost), 0.0).label("cost"),
        )
        .where(and_(
            func.date(RequestStats.request_time) >= date_from,
            func.date(RequestStats.request_time) <= date_to,
            RequestStats.platform.isnot(None),
        ))
        .group_by(RequestStats.platform)
    )
    
    platform_result = await db.execute(platform_query)
    platform_rows = platform_result.all()
    
    total_cost = sum(float(row.cost) for row in platform_rows)
    total_requests = sum(row.requests for row in platform_rows)
    
    by_platform = [
        PlatformStats(
            platform=row.platform or "unknown",
            requests=row.requests,
            cost=round(float(row.cost), 4),
            percentage=round(float(row.cost) / total_cost * 100, 2) if total_cost > 0 else 0,
        )
        for row in platform_rows
    ]
    
    # Средние значения
    unique_users_result = await db.execute(
        select(func.count(func.distinct(RequestStats.user_id)))
        .where(and_(
            func.date(RequestStats.request_time) >= date_from,
            func.date(RequestStats.request_time) <= date_to,
        ))
    )
    unique_users = unique_users_result.scalar() or 1
    
    avg_cost_per_request = total_cost / total_requests if total_requests > 0 else 0
    avg_cost_per_user = total_cost / unique_users if unique_users > 0 else 0
    
    return StatsCostsResponse(
        period_start=date_from,
        period_end=date_to,
        total_cost=round(total_cost, 4),
        daily_costs=daily_costs,
        by_platform=by_platform,
        avg_cost_per_request=round(avg_cost_per_request, 6),
        avg_cost_per_user=round(avg_cost_per_user, 4),
    )


@router.get("/platforms", response_model=StatsPlatformsResponse)
async def get_stats_platforms(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение статистики по платформам.
    """
    if not date_to:
        date_to = get_moscow_today()
    if not date_from:
        date_from = date_to - timedelta(days=30)
    
    query = (
        select(
            RequestStats.platform,
            func.count(RequestStats.id).label("requests"),
            func.coalesce(func.sum(RequestStats.total_cost), 0.0).label("cost"),
        )
        .where(and_(
            func.date(RequestStats.request_time) >= date_from,
            func.date(RequestStats.request_time) <= date_to,
        ))
        .group_by(RequestStats.platform)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    total_requests = sum(row.requests for row in rows)
    
    platforms = [
        PlatformStats(
            platform=row.platform or "unknown",
            requests=row.requests,
            cost=round(float(row.cost), 4),
            percentage=round(row.requests / total_requests * 100, 2) if total_requests > 0 else 0,
        )
        for row in rows
    ]
    
    return StatsPlatformsResponse(
        period_start=date_from,
        period_end=date_to,
        platforms=platforms,
        total_requests=total_requests,
    )


@router.get("/users/top", response_model=StatsTopUsersResponse)
async def get_top_users(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение топа активных пользователей.
    """
    if not date_to:
        date_to = get_moscow_today()
    if not date_from:
        date_from = date_to - timedelta(days=30)
    
    query = (
        select(
            RequestStats.user_id,
            RequestStats.username,
            func.count(RequestStats.id).label("requests"),
            func.coalesce(func.sum(RequestStats.total_cost), 0.0).label("cost"),
        )
        .where(and_(
            func.date(RequestStats.request_time) >= date_from,
            func.date(RequestStats.request_time) <= date_to,
            RequestStats.user_id.isnot(None),
        ))
        .group_by(RequestStats.user_id, RequestStats.username)
        .order_by(func.count(RequestStats.id).desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    top_users = [
        TopUser(
            user_id=row.user_id,
            username=row.username,
            requests=row.requests,
            cost=round(float(row.cost), 4),
        )
        for row in rows
    ]
    
    return StatsTopUsersResponse(
        period_start=date_from,
        period_end=date_to,
        top_users=top_users,
        limit=limit,
    )


@router.get("/peaks", response_model=StatsPeaksResponse)
async def get_peaks(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение пиков активности.
    """
    if not date_to:
        date_to = get_moscow_today()
    if not date_from:
        date_from = date_to - timedelta(days=7)
    
    # Распределение по часам
    hourly_query = (
        select(
            extract("hour", RequestStats.request_time).label("hour"),
            func.count(RequestStats.id).label("requests"),
        )
        .where(and_(
            func.date(RequestStats.request_time) >= date_from,
            func.date(RequestStats.request_time) <= date_to,
        ))
        .group_by(extract("hour", RequestStats.request_time))
        .order_by(extract("hour", RequestStats.request_time))
    )
    
    hourly_result = await db.execute(hourly_query)
    hourly_rows = hourly_result.all()
    
    # Количество дней в периоде
    days_count = (date_to - date_from).days + 1
    
    hourly_distribution = [
        PeakHour(
            hour=int(row.hour),
            requests=row.requests,
            avg_requests=round(row.requests / days_count, 2),
        )
        for row in hourly_rows
    ]
    
    # Находим пиковый час
    peak_hour = 0
    peak_requests = 0
    for h in hourly_distribution:
        if h.requests > peak_requests:
            peak_requests = h.requests
            peak_hour = h.hour
    
    # Запросы по дням
    daily_query = (
        select(
            func.date(RequestStats.request_time).label("day"),
            func.count(RequestStats.id).label("requests"),
        )
        .where(and_(
            func.date(RequestStats.request_time) >= date_from,
            func.date(RequestStats.request_time) <= date_to,
        ))
        .group_by(func.date(RequestStats.request_time))
        .order_by(func.date(RequestStats.request_time))
    )
    
    daily_result = await db.execute(daily_query)
    daily_rows = daily_result.all()
    
    daily_requests = [
        TimeSeriesPoint(date=row.day, value=float(row.requests))
        for row in daily_rows
    ]
    
    return StatsPeaksResponse(
        period_start=date_from,
        period_end=date_to,
        hourly_distribution=hourly_distribution,
        peak_hour=peak_hour,
        peak_requests=peak_requests,
        daily_requests=daily_requests,
    )

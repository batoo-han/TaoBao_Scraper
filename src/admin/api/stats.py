"""
API endpoints для статистики использования.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_admin_user
from src.admin.models.schemas import (
    PlatformStatsInfo,
    ProviderStatsInfo,
    StatsOverview,
    UserStatsInfo,
)
from src.db.models import AdminUser, LLMCache, UsageStats, User
from src.db.session import get_db_session
from src.services.app_settings import AppSettingsService

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=StatsOverview)
async def get_stats_overview(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Получить общую статистику использования."""
    # Общее количество пользователей
    total_users_result = await session.execute(
        select(func.count(User.id))
    )
    total_users = total_users_result.scalar() or 0
    
    # Активные пользователи за последние 30 дней
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    active_users_result = await session.execute(
        select(func.count(func.distinct(UsageStats.user_id))).where(
            UsageStats.last_request_at >= thirty_days_ago
        )
    )
    active_users_30d = active_users_result.scalar() or 0
    
    # Общая статистика запросов и токенов
    stats_result = await session.execute(
        select(
            func.sum(UsageStats.total_requests).label("total_requests"),
            func.sum(UsageStats.total_tokens).label("total_tokens"),
        )
    )
    row = stats_result.first()
    total_requests = int(row.total_requests or 0)
    total_tokens = int(row.total_tokens or 0)
    
    # Активный провайдер
    app_settings_service = AppSettingsService(session)
    app_settings = await app_settings_service.get_app_settings()
    active_provider = app_settings.active_llm_vendor
    
    # Статистика кэша
    cache_stats_result = await session.execute(
        select(
            func.count(LLMCache.id).label("total_entries"),
            func.count(LLMCache.id).filter(
                LLMCache.expires_at > datetime.utcnow()
            ).label("active_entries"),
        )
    )
    cache_row = cache_stats_result.first()
    total_cache_entries = cache_row.total_entries or 0
    active_cache_entries = cache_row.active_entries or 0
    cache_hit_rate = (
        (active_cache_entries / total_cache_entries * 100)
        if total_cache_entries > 0
        else 0.0
    )
    
    # Статистика за сегодня
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_stats_result = await session.execute(
        select(func.sum(UsageStats.total_requests)).where(
            UsageStats.last_request_at >= today_start
        )
    )
    requests_today = int(today_stats_result.scalar() or 0)
    
    # Статистика за эту неделю
    week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_stats_result = await session.execute(
        select(func.sum(UsageStats.total_requests)).where(
            UsageStats.last_request_at >= week_start
        )
    )
    requests_this_week = int(week_stats_result.scalar() or 0)
    
    # Статистика за этот месяц
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_stats_result = await session.execute(
        select(func.sum(UsageStats.total_requests)).where(
            UsageStats.last_request_at >= month_start
        )
    )
    requests_this_month = int(month_stats_result.scalar() or 0)
    
    return StatsOverview(
        total_users=total_users,
        active_users_30d=active_users_30d,
        total_requests=total_requests,
        total_tokens=total_tokens,
        active_provider=active_provider,
        cache_hit_rate=round(cache_hit_rate, 2),
        requests_today=requests_today,
        requests_this_week=requests_this_week,
        requests_this_month=requests_this_month,
    )


@router.get("/users", response_model=List[UserStatsInfo])
async def get_users_stats(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Получить статистику по пользователям."""
    result = await session.execute(
        select(
            User.id,
            User.telegram_id,
            User.username,
            User.first_name,
            func.sum(UsageStats.total_requests).label("total_requests"),
            func.sum(UsageStats.total_tokens).label("total_tokens"),
            func.max(UsageStats.last_request_at).label("last_request_at"),
        )
        .outerjoin(UsageStats, User.id == UsageStats.user_id)
        .group_by(User.id, User.telegram_id, User.username, User.first_name)
        .order_by(func.sum(UsageStats.total_requests).desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    
    stats_list = []
    for row in result.all():
        stats_list.append(
            UserStatsInfo(
                user_id=row.id,
                telegram_id=row.telegram_id,
                username=row.username,
                first_name=row.first_name,
                total_requests=int(row.total_requests or 0),
                total_tokens=int(row.total_tokens or 0),
                last_request_at=row.last_request_at,
            )
        )
    
    return stats_list


@router.get("/providers", response_model=List[ProviderStatsInfo])
async def get_providers_stats(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Получить статистику по провайдерам."""
    # Статистика по каждому провайдеру
    result = await session.execute(
        select(
            UsageStats.vendor,
            func.sum(UsageStats.total_requests).label("total_requests"),
            func.sum(UsageStats.total_tokens).label("total_tokens"),
            func.count(func.distinct(UsageStats.user_id)).label("unique_users"),
        )
        .where(UsageStats.vendor.isnot(None))
        .group_by(UsageStats.vendor)
    )
    
    # Статистика кэша
    cache_result = await session.execute(
        select(
            LLMCache.vendor,
            func.count(LLMCache.id).label("cache_entries"),
        )
        .group_by(LLMCache.vendor)
    )
    cache_stats = {row.vendor: row.cache_entries for row in cache_result.all()}
    
    stats_list = []
    for row in result.all():
        vendor = row.vendor
        cache_entries = cache_stats.get(vendor, 0)
        
        # Упрощенная логика: считаем, что все записи кэша - это попадания
        # В реальности нужно отслеживать cache hits/misses отдельно
        cache_hits = cache_entries
        cache_misses = max(0, (row.total_requests or 0) - cache_hits)
        
        stats_list.append(
            ProviderStatsInfo(
                vendor=vendor,
                total_requests=int(row.total_requests or 0),
                total_tokens=int(row.total_tokens or 0),
                unique_users=int(row.unique_users or 0),
                cache_hits=cache_hits,
                cache_misses=cache_misses,
            )
        )
    
    return stats_list


@router.get("/platforms", response_model=List[PlatformStatsInfo])
async def get_platforms_stats(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Получить статистику по платформам (магазинам).
    
    Примечание: В будущем нужно добавить отслеживание платформы в UsageStats
    или создать отдельную таблицу для статистики по платформам.
    """
    from src.services.app_settings import AppSettingsService
    
    # Получаем настройки платформ
    app_settings_service = AppSettingsService(session)
    platforms_config = await app_settings_service.get_platforms_config()
    
    # Пока возвращаем только информацию о включенных/выключенных платформах
    # В будущем можно добавить реальную статистику из БД
    stats_list = []
    for platform, config in platforms_config.items():
        stats_list.append(
            PlatformStatsInfo(
                platform=platform,
                enabled=config.get("enabled", False),
                total_requests=0,  # TODO: добавить отслеживание
                last_request_at=None,  # TODO: добавить отслеживание
            )
        )
    
    return stats_list


"""
Сервис лимитов запросов: суточные и месячные, глобальные и индивидуальные.
Версия для работы с PostgreSQL через SQLAlchemy.
Учёт ведётся по времени Европы/Москвы.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.services.user_settings import UserSettingsService
from src.db.session import get_session
from src.db.models import RateLimitGlobal, RateLimitUser, User


try:
    MSK = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    MSK = timezone(timedelta(hours=3))


def _today_msk() -> date:
    """Возвращает текущую дату в МСК"""
    return datetime.now(MSK).date()


def _add_months(d: date, months: int) -> date:
    """
    Добавляет месяцы к дате, корректируя день на конец месяца.
    """
    from calendar import monthrange
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    last_day = monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _month_period(month_start_str: str) -> tuple[date, date]:
    """
    Возвращает (start_date, end_date) для месяца, где start_date = month_start_str,
    end_date = последний день месяца.
    """
    try:
        start = date.fromisoformat(month_start_str)
    except Exception:
        start = _today_msk().replace(day=1)
    end = _add_months(start, 1) - timedelta(days=1)
    return start, end


@dataclass
class LimitCounters:
    """Счётчики лимитов (для обратной совместимости)"""
    day_start: str
    day_count: int
    month_start: str
    month_count: int
    day_cost: float = 0.0
    month_cost: float = 0.0


class RateLimitService:
    """
    Хранит и проверяет лимиты запросов (работает с PostgreSQL).
    """

    def __init__(self, user_settings_service: UserSettingsService) -> None:
        """
        Инициализация сервиса.
        
        Args:
            user_settings_service: Сервис настроек пользователей
        """
        self.user_settings_service = user_settings_service

    async def _get_or_create_global(self, session: AsyncSession) -> RateLimitGlobal:
        """Получает или создаёт глобальные лимиты (одна запись с id=1)"""
        result = await session.execute(select(RateLimitGlobal).where(RateLimitGlobal.id == 1))
        global_limits = result.scalar_one_or_none()
        
        if global_limits is None:
            today = _today_msk()
            global_limits = RateLimitGlobal(
                id=1,
                day_start=today,
                day_count=0,
                month_start=today.replace(day=1),
                month_count=0,
                day_cost=0.0,
                month_cost=0.0,
            )
            session.add(global_limits)
            await session.flush()
        
        return global_limits

    async def _get_or_create_user_limits(self, session: AsyncSession, user_id: int, created_at: Optional[date] = None) -> RateLimitUser:
        """Получает или создаёт лимиты пользователя (одна запись на пользователя)"""
        result = await session.execute(select(RateLimitUser).where(RateLimitUser.user_id == user_id))
        user_limits = result.scalar_one_or_none()
        
        if user_limits is None:
            today = _today_msk()
            month_start = created_at.replace(day=1) if created_at else today.replace(day=1)
            user_limits = RateLimitUser(
                user_id=user_id,
                day_start=today,
                day_count=0,
                month_start=month_start,
                month_count=0,
                day_cost=0.0,
                month_cost=0.0,
            )
            session.add(user_limits)
            await session.flush()
        
        return user_limits

    async def _reset_if_needed_global(self, session: AsyncSession, global_limits: RateLimitGlobal) -> RateLimitGlobal:
        """Сбрасывает глобальные счётчики, если нужно"""
        today = _today_msk()
        
        # Сброс дня
        if global_limits.day_start != today:
            global_limits.day_start = today
            global_limits.day_count = 0
            global_limits.day_cost = 0.0
        
        # Сброс месяца
        month_start = today.replace(day=1)
        if global_limits.month_start != month_start:
            global_limits.month_start = month_start
            global_limits.month_count = 0
            global_limits.month_cost = 0.0
        
        return global_limits

    async def _reset_if_needed_user(self, session: AsyncSession, user_limits: RateLimitUser, created_at: Optional[date] = None) -> RateLimitUser:
        """Сбрасывает пользовательские счётчики, если нужно"""
        today = _today_msk()
        
        # Сброс дня
        if user_limits.day_start != today:
            user_limits.day_start = today
            user_limits.day_count = 0
            user_limits.day_cost = 0.0
        
        # Сброс месяца
        month_anchor = user_limits.month_start
        while _add_months(month_anchor, 1) <= today:
            month_anchor = _add_months(month_anchor, 1)
        
        if user_limits.month_start != month_anchor:
            user_limits.month_start = month_anchor
            user_limits.month_count = 0
            user_limits.month_cost = 0.0
        
        return user_limits

    def _remaining(self, limit: Optional[int], count: int) -> Optional[int]:
        """Вычисляет остаток лимита"""
        if not limit:
            return None
        return max(limit - count, 0)

    def _build_snapshot(
        self,
        u: RateLimitUser,
        g: RateLimitGlobal,
        per_user_daily: Optional[int],
        per_user_monthly: Optional[int],
        total_daily: Optional[int],
        total_monthly: Optional[int],
        whitelist_enabled: bool,
        is_admin: bool,
    ) -> Dict[str, Any]:
        """Строит snapshot для ответа"""
        if is_admin:
            return {"unlimited": True}

        # Если whitelist выключен — не ограничиваем, но считаем usage
        if not whitelist_enabled:
            per_user_daily = None
            per_user_monthly = None
            total_daily = None
            total_monthly = None

        return {
            "unlimited": False,
            "user": {
                "daily": {
                    "limit": per_user_daily,
                    "count": u.day_count,
                    "remaining": self._remaining(per_user_daily, u.day_count),
                    "cost": u.day_cost,
                    "reset_at": datetime.combine(u.day_start, datetime.min.time(), MSK).replace(hour=23, minute=59, second=59).isoformat(),
                },
                "monthly": {
                    "limit": per_user_monthly,
                    "count": u.month_count,
                    "remaining": self._remaining(per_user_monthly, u.month_count),
                    "cost": u.month_cost,
                    "reset_at": _add_months(u.month_start, 1).isoformat(),
                    "period": _month_period(u.month_start.isoformat()),
                },
            },
            "global": {
                "daily": {
                    "limit": total_daily,
                    "count": g.day_count,
                    "remaining": self._remaining(total_daily, g.day_count),
                    "cost": g.day_cost,
                    "reset_at": datetime.combine(g.day_start, datetime.min.time(), MSK).replace(hour=23, minute=59, second=59).isoformat(),
                },
                "monthly": {
                    "limit": total_monthly,
                    "count": g.month_count,
                    "remaining": self._remaining(total_monthly, g.month_count),
                    "cost": g.month_cost,
                    "reset_at": _add_months(g.month_start, 1).isoformat(),
                    "period": _month_period(g.month_start.isoformat()),
                },
            },
        }

    async def snapshot(
        self,
        user_id: int,
        is_admin: bool,
        user_daily_limit: Optional[int],
        user_monthly_limit: Optional[int],
        created_at: Optional[str],
        whitelist_enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        Возвращает текущие счётчики и остатки без инкремента.
        """
        created_at_date = None
        if created_at:
            try:
                created_at_date = date.fromisoformat(created_at)
            except Exception:
                pass
        
        async for session in get_session():
            g = await self._get_or_create_global(session)
            g = await self._reset_if_needed_global(session, g)
            
            u = await self._get_or_create_user_limits(session, user_id, created_at_date)
            u = await self._reset_if_needed_user(session, u, created_at_date)
            
            await session.commit()
            
            # Получаем лимиты из настроек или админских настроек
            per_user_daily = user_daily_limit if user_daily_limit is not None else getattr(settings, "PER_USER_DAILY_LIMIT", None)
            per_user_monthly = user_monthly_limit if user_monthly_limit is not None else getattr(settings, "PER_USER_MONTHLY_LIMIT", None)
            total_daily = getattr(settings, "TOTAL_DAILY_LIMIT", None)
            total_monthly = getattr(settings, "TOTAL_MONTHLY_LIMIT", None)

            return self._build_snapshot(
                u=u,
                g=g,
                per_user_daily=per_user_daily,
                per_user_monthly=per_user_monthly,
                total_daily=total_daily,
                total_monthly=total_monthly,
                whitelist_enabled=whitelist_enabled,
                is_admin=is_admin,
            )

    async def consume(
        self,
        user_id: int,
        is_admin: bool,
        user_daily_limit: Optional[int],
        user_monthly_limit: Optional[int],
        created_at: Optional[str],
        username: Optional[str] = None,
        whitelist_enabled: bool = True,
        increment: bool = True,
        enforce_limits_override: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Проверяет лимиты, опционально инкрементирует счётчики (increment=True).
        Возвращает словарь с полями allowed, reason, snapshot.
        """
        created_at_date = None
        if created_at:
            try:
                created_at_date = date.fromisoformat(created_at)
            except Exception:
                pass

        if is_admin:
            # Админы не ограничиваются, но usage считаем для метрик
            async for session in get_session():
                g = await self._get_or_create_global(session)
                g = await self._reset_if_needed_global(session, g)
                
                u = await self._get_or_create_user_limits(session, user_id, created_at_date)
                u = await self._reset_if_needed_user(session, u, created_at_date)
                
                if increment:
                    u.day_count += 1
                    u.month_count += 1
                    g.day_count += 1
                    g.month_count += 1
                
                await session.commit()
                return {"allowed": True, "snapshot": {"unlimited": True}}

        async for session in get_session():
            # Применяем отложенные лимиты по username, если есть
            # TODO: реализовать pending_by_username через Redis или отдельную таблицу
            # Пока пропускаем эту логику
            
            g = await self._get_or_create_global(session)
            g = await self._reset_if_needed_global(session, g)
            
            u = await self._get_or_create_user_limits(session, user_id, created_at_date)
            u = await self._reset_if_needed_user(session, u, created_at_date)

            per_user_daily = user_daily_limit if user_daily_limit is not None else getattr(settings, "PER_USER_DAILY_LIMIT", None)
            per_user_monthly = user_monthly_limit if user_monthly_limit is not None else getattr(settings, "PER_USER_MONTHLY_LIMIT", None)
            total_daily = getattr(settings, "TOTAL_DAILY_LIMIT", None)
            total_monthly = getattr(settings, "TOTAL_MONTHLY_LIMIT", None)

            enforce_limits = enforce_limits_override if enforce_limits_override is not None else bool(whitelist_enabled)

            def _exceeded(limit: Optional[int], count: int) -> bool:
                return bool(limit) and count >= limit

            if enforce_limits and _exceeded(per_user_daily, u.day_count):
                snap = self._build_snapshot(
                    u=u, g=g,
                    per_user_daily=per_user_daily,
                    per_user_monthly=per_user_monthly,
                    total_daily=total_daily,
                    total_monthly=total_monthly,
                    whitelist_enabled=whitelist_enabled,
                    is_admin=False,
                )
                return {
                    "allowed": False,
                    "reason": "Превышен дневной лимит пользователя",
                    "snapshot": snap,
                }
            if enforce_limits and _exceeded(per_user_monthly, u.month_count):
                snap = self._build_snapshot(
                    u=u, g=g,
                    per_user_daily=per_user_daily,
                    per_user_monthly=per_user_monthly,
                    total_daily=total_daily,
                    total_monthly=total_monthly,
                    whitelist_enabled=whitelist_enabled,
                    is_admin=False,
                )
                return {
                    "allowed": False,
                    "reason": "Превышен месячный лимит пользователя",
                    "snapshot": snap,
                }
            if enforce_limits and _exceeded(total_daily, g.day_count):
                snap = self._build_snapshot(
                    u=u, g=g,
                    per_user_daily=per_user_daily,
                    per_user_monthly=per_user_monthly,
                    total_daily=total_daily,
                    total_monthly=total_monthly,
                    whitelist_enabled=whitelist_enabled,
                    is_admin=False,
                )
                return {
                    "allowed": False,
                    "reason": "Превышен общий дневной лимит",
                    "snapshot": snap,
                }
            if enforce_limits and _exceeded(total_monthly, g.month_count):
                snap = self._build_snapshot(
                    u=u, g=g,
                    per_user_daily=per_user_daily,
                    per_user_monthly=per_user_monthly,
                    total_daily=total_daily,
                    total_monthly=total_monthly,
                    whitelist_enabled=whitelist_enabled,
                    is_admin=False,
                )
                return {
                    "allowed": False,
                    "reason": "Превышен общий месячный лимит",
                    "snapshot": snap,
                }

            # Инкременты (опционально)
            if increment:
                u.day_count += 1
                u.month_count += 1
                g.day_count += 1
                g.month_count += 1

            await session.commit()

            snap = self._build_snapshot(
                u=u, g=g,
                per_user_daily=per_user_daily,
                per_user_monthly=per_user_monthly,
                total_daily=total_daily,
                total_monthly=total_monthly,
                whitelist_enabled=whitelist_enabled,
                is_admin=False,
            )
            return {
                "allowed": True,
                "snapshot": snap,
            }

    async def commit_success(
        self,
        user_id: int,
        user_daily_limit: Optional[int],
        user_monthly_limit: Optional[int],
        created_at: Optional[str],
        username: Optional[str] = None,
        request_cost: float = 0.0,
        is_admin: bool = False,
        whitelist_enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        Фиксирует успешный запрос: инкремент счётчиков без повторной блокировки.
        """
        created_at_date = None
        if created_at:
            try:
                created_at_date = date.fromisoformat(created_at)
            except Exception:
                pass

        async for session in get_session():
            g = await self._get_or_create_global(session)
            g = await self._reset_if_needed_global(session, g)
            
            u = await self._get_or_create_user_limits(session, user_id, created_at_date)
            u = await self._reset_if_needed_user(session, u, created_at_date)
            
            # Добавляем стоимость к счётчикам (для всех, включая админов)
            if request_cost > 0:
                u.day_cost += request_cost
                u.month_cost += request_cost
                g.day_cost += request_cost
                g.month_cost += request_cost
            
            # Инкрементируем счётчики запросов
            u.day_count += 1
            u.month_count += 1
            g.day_count += 1
            g.month_count += 1
            
            await session.commit()
        
        # Для админов возвращаем unlimited snapshot, но с глобальной статистикой стоимости
        if is_admin:
            async for session in get_session():
                g = await self._get_or_create_global(session)
                await session.commit()
                return {
                    "snapshot": {
                        "unlimited": True,
                        "global": {
                            "daily": {"cost": g.day_cost},
                            "monthly": {"cost": g.month_cost},
                        },
                    }
                }
        
        # Получаем финальный snapshot для обычных пользователей
        per_user_daily = user_daily_limit if user_daily_limit is not None else getattr(settings, "PER_USER_DAILY_LIMIT", None)
        per_user_monthly = user_monthly_limit if user_monthly_limit is not None else getattr(settings, "PER_USER_MONTHLY_LIMIT", None)
        total_daily = getattr(settings, "TOTAL_DAILY_LIMIT", None)
        total_monthly = getattr(settings, "TOTAL_MONTHLY_LIMIT", None)
        
        async for session in get_session():
            g = await self._get_or_create_global(session)
            u = await self._get_or_create_user_limits(session, user_id, created_at_date)
            await session.commit()
            
            snap = self._build_snapshot(
                u=u,
                g=g,
                per_user_daily=per_user_daily,
                per_user_monthly=per_user_monthly,
                total_daily=total_daily,
                total_monthly=total_monthly,
                whitelist_enabled=whitelist_enabled,
                is_admin=False,
            )
            
            return {"snapshot": snap}

    async def get_global_cost_stats(self) -> Dict[str, float]:
        """Возвращает глобальную статистику стоимости"""
        async for session in get_session():
            g = await self._get_or_create_global(session)
            g = await self._reset_if_needed_global(session, g)
            await session.commit()
            return {
                "day_cost": g.day_cost,
                "month_cost": g.month_cost,
            }

    async def set_pending_limits_by_username(self, username: str, daily_limit: Optional[int], monthly_limit: Optional[int]) -> None:
        """Устанавливает отложенные лимиты по username (TODO: реализовать через Redis)"""
        # TODO: реализовать через Redis или отдельную таблицу
        pass

    async def get_pending_limits_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Получает отложенные лимиты по username (TODO: реализовать через Redis)"""
        # TODO: реализовать через Redis или отдельную таблицу
        return None

    async def list_individual_limits(self) -> Dict[str, Any]:
        """Возвращает словарь с активными лимитами по ID"""
        # TODO: реализовать получение всех пользователей из БД
        return {"users": {}, "pending_by_username": {}}

    async def list_limits_full(self) -> Dict[str, Any]:
        """Возвращает все лимиты"""
        # TODO: реализовать получение всех пользователей из БД
        return {"settings": {}, "usage": {}, "pending_by_username": {}}

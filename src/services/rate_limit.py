"""
Сервис лимитов запросов: суточные и месячные, глобальные и индивидуальные.
Учёт ведётся по времени Европы/Москвы.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.config import settings
from src.services.user_settings import UserSettingsService


try:
    MSK = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    # Fallback для окружений без tzdata (Windows). Смещение +3.
    MSK = timezone(timedelta(hours=3))


def _today_msk() -> date:
    return datetime.now(MSK).date()


def _add_months(d: date, months: int) -> date:
    """
    Добавляет месяцы к дате, корректируя день на конец месяца.
    """
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    # Последний день месяца
    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


@dataclass
class LimitCounters:
    day_start: str
    day_count: int
    month_start: str
    month_count: int


class RateLimitService:
    """
    Хранит и проверяет лимиты запросов.
    """

    def __init__(self, user_settings_service: UserSettingsService, storage_file: str = "data/rate_limits.json") -> None:
        self.user_settings_service = user_settings_service
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {"global": {}, "users": {}, "pending_by_username": {}}
        self._load()

    # -------------------- внутренние helpers --------------------
    def _load(self) -> None:
        if not self.storage_file.exists():
            self._data = {"global": {}, "users": {}}
            return
        try:
            with open(self.storage_file, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)
        except Exception:
            self._data = {"global": {}, "users": {}, "pending_by_username": {}}

    def _save(self) -> None:
        with open(self.storage_file, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, indent=2)

    def _ensure_global(self) -> LimitCounters:
        today = _today_msk().isoformat()
        month_start = _today_msk().replace(day=1).isoformat()
        g = self._data.setdefault("global", {})
        if not g:
            g.update({"day_start": today, "day_count": 0, "month_start": month_start, "month_count": 0})
        return LimitCounters(
            day_start=g.get("day_start", today),
            day_count=int(g.get("day_count", 0)),
            month_start=g.get("month_start", month_start),
            month_count=int(g.get("month_count", 0)),
        )

    def _ensure_user(self, user_id: int, created_at: Optional[str]) -> LimitCounters:
        today = _today_msk()
        users = self._data.setdefault("users", {})
        entry = users.get(str(user_id), {})

        # Определяем старт месяца для пользователя
        month_anchor_str = entry.get("month_start") or (created_at or today.replace(day=1).isoformat())
        try:
            month_anchor = date.fromisoformat(month_anchor_str)
        except Exception:
            month_anchor = today.replace(day=1)
        # Прокручиваем, если прошло >= 1 месяца
        while _add_months(month_anchor, 1) <= today:
            month_anchor = _add_months(month_anchor, 1)
            entry["month_count"] = 0

        # Суточный сброс
        day_start_str = entry.get("day_start") or today.isoformat()
        try:
            day_start = date.fromisoformat(day_start_str)
        except Exception:
            day_start = today
        if day_start != today:
            entry["day_count"] = 0
            day_start = today

        # Если месяц сдвинулся — обнуляем месячный счётчик
        if month_anchor_str != month_anchor.isoformat():
            entry["month_count"] = 0

        entry.setdefault("day_count", 0)
        entry.setdefault("month_count", 0)
        entry["day_start"] = day_start.isoformat()
        entry["month_start"] = month_anchor.isoformat()

        users[str(user_id)] = entry
        return LimitCounters(
            day_start=entry["day_start"],
            day_count=int(entry.get("day_count", 0)),
            month_start=entry["month_start"],
            month_count=int(entry.get("month_count", 0)),
        )

    def _reset_global_if_needed(self, counters: LimitCounters) -> LimitCounters:
        today = _today_msk()
        # День
        try:
            day_start = date.fromisoformat(counters.day_start)
        except Exception:
            day_start = today
        if day_start != today:
            counters.day_start = today.isoformat()
            counters.day_count = 0
        # Месяц
        try:
            month_start = date.fromisoformat(counters.month_start)
        except Exception:
            month_start = today.replace(day=1)
        first_day_current_month = today.replace(day=1)
        if month_start != first_day_current_month:
            counters.month_start = first_day_current_month.isoformat()
            counters.month_count = 0
        return counters

    def _write_counters(self, user_id: Optional[int], user: LimitCounters | None, glob: LimitCounters | None) -> None:
        if glob:
            self._data["global"] = asdict(glob)
        if user is not None and user_id is not None:
            self._data.setdefault("users", {})
            self._data["users"][str(user_id)] = asdict(user)
        self._save()

    def _remaining(self, limit: Optional[int], count: int) -> Optional[int]:
        if not limit:
            return None
        return max(limit - count, 0)

    def set_pending_limits_by_username(self, username: str, daily_limit: Optional[int], monthly_limit: Optional[int]) -> None:
        uname = (username or "").lstrip("@").lower()
        if not uname:
            return
        pending = self._data.setdefault("pending_by_username", {})
        pending[uname] = {
            "daily_limit": daily_limit,
            "monthly_limit": monthly_limit,
        }
        self._save()

    def get_pending_limits_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        uname = (username or "").lstrip("@").lower()
        if not uname:
            return None
        return (self._data.get("pending_by_username") or {}).get(uname)

    def list_individual_limits(self) -> Dict[str, Any]:
        """
        Возвращает словарь с активными лимитами по ID и отложенными лимитами по username.
        """
        return {
            "users": self._data.get("users", {}),
            "pending_by_username": self._data.get("pending_by_username", {}),
        }

    def list_limits_full(self) -> Dict[str, Any]:
        """
        Возвращает все лимиты:
        - settings: индивидуальные лимиты из user_settings (daily/monthly), даже если счётчики ещё не создавались
        - usage: счётчики day/month из rate_limits.json
        - pending_by_username: отложенные лимиты по username
        """
        settings_limits = {}
        try:
            cache = getattr(self.user_settings_service, "_settings_cache", {}) or {}
            for uid, us in cache.items():
                settings_limits[str(uid)] = {
                    "daily_limit": getattr(us, "daily_limit", None),
                    "monthly_limit": getattr(us, "monthly_limit", None),
                }
        except Exception:
            settings_limits = {}

        return {
            "settings": settings_limits,
            "usage": self._data.get("users", {}),
            "pending_by_username": self._data.get("pending_by_username", {}),
        }

    # -------------------- публичные методы --------------------
    def snapshot(self, user_id: int, is_admin: bool, user_daily_limit: Optional[int], user_monthly_limit: Optional[int], created_at: Optional[str]) -> Dict[str, Any]:
        """
        Возвращает текущие счётчики и остатки без инкремента.
        """
        if is_admin:
            return {"unlimited": True}
        with self._lock:
            g = self._reset_global_if_needed(self._ensure_global())
            u = self._ensure_user(user_id, created_at)
            self._write_counters(user_id, u, g)

            # Лимиты
            per_user_daily = user_daily_limit or getattr(settings, "PER_USER_DAILY_LIMIT", None)
            per_user_monthly = user_monthly_limit or getattr(settings, "PER_USER_MONTHLY_LIMIT", None)
            total_daily = getattr(settings, "TOTAL_DAILY_LIMIT", None)
            total_monthly = getattr(settings, "TOTAL_MONTHLY_LIMIT", None)

            return {
                "unlimited": False,
                "user": {
                    "daily": {
                        "limit": per_user_daily,
                        "count": u.day_count,
                        "remaining": self._remaining(per_user_daily, u.day_count),
                        "reset_at": datetime.combine(date.fromisoformat(u.day_start), datetime.min.time(), MSK).replace(hour=23, minute=59, second=59).isoformat(),
                    },
                    "monthly": {
                        "limit": per_user_monthly,
                        "count": u.month_count,
                        "remaining": self._remaining(per_user_monthly, u.month_count),
                        "reset_at": _add_months(date.fromisoformat(u.month_start), 1).isoformat(),
                    },
                },
                "global": {
                    "daily": {
                        "limit": total_daily,
                        "count": g.day_count,
                        "remaining": self._remaining(total_daily, g.day_count),
                        "reset_at": datetime.combine(date.fromisoformat(g.day_start), datetime.min.time(), MSK).replace(hour=23, minute=59, second=59).isoformat(),
                    },
                    "monthly": {
                        "limit": total_monthly,
                        "count": g.month_count,
                        "remaining": self._remaining(total_monthly, g.month_count),
                        "reset_at": _add_months(date.fromisoformat(g.month_start), 1).isoformat(),
                    },
                },
            }

    def consume(self, user_id: int, is_admin: bool, user_daily_limit: Optional[int], user_monthly_limit: Optional[int], created_at: Optional[str], username: Optional[str] = None) -> Dict[str, Any]:
        """
        Проверяет лимиты, инкрементирует счётчики. Возвращает словарь с полями allowed, reason, snapshot.
        """
        if is_admin:
            return {"allowed": True, "snapshot": {"unlimited": True}}

        with self._lock:
            # Применяем отложенные лимиты по username, если есть
            if username:
                uname = username.lstrip("@").lower()
                pending = self._data.get("pending_by_username", {}).get(uname)
                if pending:
                    self.user_settings_service.update_limits(
                        user_id,
                        daily_limit=pending.get("daily_limit"),
                        monthly_limit=pending.get("monthly_limit"),
                    )
                    # после применения переносим в обычные user-счётчики
                    self._data.get("pending_by_username", {}).pop(uname, None)

            g = self._reset_global_if_needed(self._ensure_global())
            u = self._ensure_user(user_id, created_at)

            per_user_daily = user_daily_limit or getattr(settings, "PER_USER_DAILY_LIMIT", None)
            per_user_monthly = user_monthly_limit or getattr(settings, "PER_USER_MONTHLY_LIMIT", None)
            total_daily = getattr(settings, "TOTAL_DAILY_LIMIT", None)
            total_monthly = getattr(settings, "TOTAL_MONTHLY_LIMIT", None)

            # Проверки
            def _exceeded(limit: Optional[int], count: int) -> bool:
                return bool(limit) and count >= limit

            if _exceeded(per_user_daily, u.day_count):
                return {
                    "allowed": False,
                    "reason": "Превышен дневной лимит пользователя",
                    "snapshot": self.snapshot(user_id, False, user_daily_limit, user_monthly_limit, created_at),
                }
            if _exceeded(per_user_monthly, u.month_count):
                return {
                    "allowed": False,
                    "reason": "Превышен месячный лимит пользователя",
                    "snapshot": self.snapshot(user_id, False, user_daily_limit, user_monthly_limit, created_at),
                }
            if _exceeded(total_daily, g.day_count):
                return {
                    "allowed": False,
                    "reason": "Превышен общий дневной лимит",
                    "snapshot": self.snapshot(user_id, False, user_daily_limit, user_monthly_limit, created_at),
                }
            if _exceeded(total_monthly, g.month_count):
                return {
                    "allowed": False,
                    "reason": "Превышен общий месячный лимит",
                    "snapshot": self.snapshot(user_id, False, user_daily_limit, user_monthly_limit, created_at),
                }

            # Инкременты
            u.day_count += 1
            u.month_count += 1
            g.day_count += 1
            g.month_count += 1

            self._write_counters(user_id, u, g)

            return {
                "allowed": True,
                "snapshot": self.snapshot(user_id, False, user_daily_limit, user_monthly_limit, created_at),
            }


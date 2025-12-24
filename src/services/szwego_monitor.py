"""
Szwego monitor: контроль актуальности cookies/token и уведомления админу.

Требования:
- Если токен “протух” (по expires или по ответу API), пользователю должны приходить
  понятные сообщения: “Szwego временно недоступен”.
- Админу нужно отправить уведомление, что нужно обновить cookies/token.
- Должна быть фоновая проверка, чтобы узнавать о проблеме без пользовательских запросов.

Мы реализуем “лёгкую” стратегию:
1) Основная проверка — по `expires` у cookie `token` в файле cookies (без сети).
2) Опциональная проверка — реальный API-пинг по `SZWEGO_HEALTHCHECK_URL`.
3) Уведомления админу с анти-спамом (min interval).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aiogram import Bot

from src.core.config import settings
from src.bot import error_handler as error_handler_module
from src.api.szwego_api import SzwegoApiClient

logger = logging.getLogger(__name__)


StatusLevel = Literal["ok", "warn", "bad", "unknown"]


@dataclass(frozen=True)
class SzwegoTokenStatus:
    level: StatusLevel
    token_expires_at: int | None
    seconds_left: int | None
    reason: str


def _read_token_expires_at(path: Path) -> int | None:
    """
    Читает expires cookie `token` из JSON cookies файла.
    Возвращает Unix timestamp (сек) или None.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cookies = raw.get("cookies") if isinstance(raw, dict) else None
        if not isinstance(cookies, list):
            return None
        for c in cookies:
            if not isinstance(c, dict):
                continue
            if (c.get("name") or "") == "token":
                exp = c.get("expires")
                if isinstance(exp, (int, float)) and exp > 0:
                    return int(exp)
        return None
    except Exception:
        return None


def get_szwego_token_status() -> SzwegoTokenStatus:
    """
    Возвращает статус токена Szwego (по expires).
    """
    cookies_file = Path(getattr(settings, "SZWEGO_COOKIES_FILE", "") or "cookies/szwego_cookies.json")
    warn_sec = int(getattr(settings, "SZWEGO_TOKEN_EXPIRY_WARN_SEC", 86400) or 86400)
    grace = int(getattr(settings, "SZWEGO_TOKEN_EXPIRE_GRACE_SEC", 60) or 60)

    if not cookies_file.exists():
        return SzwegoTokenStatus(
            level="bad",
            token_expires_at=None,
            seconds_left=None,
            reason=f"cookies-файл не найден: {cookies_file}",
        )

    exp = _read_token_expires_at(cookies_file)
    if not exp:
        return SzwegoTokenStatus(
            level="unknown",
            token_expires_at=None,
            seconds_left=None,
            reason="не удалось определить expires у cookie token (проверьте формат cookies файла)",
        )

    now = int(time.time())
    left = exp - now

    if left <= grace:
        return SzwegoTokenStatus(level="bad", token_expires_at=exp, seconds_left=left, reason="token истёк (по expires)")

    if left <= warn_sec:
        return SzwegoTokenStatus(level="warn", token_expires_at=exp, seconds_left=left, reason="token скоро истечёт (по expires)")

    return SzwegoTokenStatus(level="ok", token_expires_at=exp, seconds_left=left, reason="ok")


def _format_left(seconds_left: int | None) -> str:
    if seconds_left is None:
        return "неизвестно"
    if seconds_left < 0:
        seconds_left = 0
    hours = seconds_left // 3600
    mins = (seconds_left % 3600) // 60
    return f"{hours}ч {mins}м"


class SzwegoHealthMonitor:
    """
    Фоновый монитор Szwego токена.

    Анти-спам: уведомления админу отправляются не чаще `SZWEGO_ALERT_MIN_INTERVAL_SEC`
    и только при изменении уровня/причины.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._last_alert_ts: float = 0.0
        self._last_alert_fingerprint: str = ""

    async def start(self, bot: Bot) -> None:
        if self._task:
            return
        if not bool(getattr(settings, "SZWEGO_MONITOR_ENABLED", True)):
            return
        self._task = asyncio.create_task(self._run(bot), name="szwego_health_monitor")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except Exception:
            pass
        self._task = None

    async def _run(self, bot: Bot) -> None:
        interval = int(getattr(settings, "SZWEGO_MONITOR_INTERVAL_SEC", 3600) or 3600)
        while True:
            try:
                await self._check_and_notify(bot)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("[SzwegoMonitor] Ошибка фоновой проверки: %s", e)
            await asyncio.sleep(max(60, interval))

    async def _check_and_notify(self, bot: Bot) -> None:
        status = get_szwego_token_status()

        # Опциональный “пинг” API, если задан healthcheck URL
        health_url = (getattr(settings, "SZWEGO_HEALTHCHECK_URL", "") or "").strip()
        if health_url:
            try:
                client = SzwegoApiClient()
                res = await client.fetch_product(health_url)
                if res.get("code") != 200:
                    status = SzwegoTokenStatus(
                        level="bad",
                        token_expires_at=status.token_expires_at,
                        seconds_left=status.seconds_left,
                        reason=f"API healthcheck не прошёл: code={res.get('code')} msg={res.get('msg')}",
                    )
            except Exception as e:
                status = SzwegoTokenStatus(
                    level="bad",
                    token_expires_at=status.token_expires_at,
                    seconds_left=status.seconds_left,
                    reason=f"API healthcheck упал: {e}",
                )

        if status.level == "ok":
            return

        min_interval = int(getattr(settings, "SZWEGO_ALERT_MIN_INTERVAL_SEC", 21600) or 21600)
        now = time.time()
        fingerprint = f"{status.level}|{status.reason}"

        if fingerprint == self._last_alert_fingerprint and (now - self._last_alert_ts) < min_interval:
            return

        self._last_alert_ts = now
        self._last_alert_fingerprint = fingerprint

        text = (
            "⚠️ <b>Szwego: проблема с доступом</b>\n\n"
            f"<b>Статус:</b> {status.level}\n"
            f"<b>Причина:</b> {status.reason}\n"
            f"<b>Осталось до expires:</b> {_format_left(status.seconds_left)}\n\n"
            "Нужно обновить cookies/token в файле:\n"
            f"<code>{getattr(settings, 'SZWEGO_COOKIES_FILE', 'cookies/szwego_cookies.json')}</code>"
        )

        # Отправка админу через общий error_handler (если настроен ADMIN_CHAT_ID)
        await error_handler_module.notify_admin_system(text=text, key="szwego_monitor", bot=bot)



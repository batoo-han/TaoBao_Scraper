"""
Сервис контроля flood-limit для Telegram.

Основные задачи:
1) Запоминать индивидуальную блокировку пользователя (по retry_after).
2) Возвращать оставшееся время блокировки, чтобы показать пользователю.
3) Форматировать время в человекочитаемый формат на русском.
"""

from __future__ import annotations

import re
import time
from typing import Optional

from src.db.redis_client import get_redis_client

# Префикс ключей для хранения индивидуальной блокировки пользователя
_FLOOD_BLOCK_KEY_PREFIX = "tg_flood_block:"

# Регулярка для парсинга "Retry in 18 seconds" / "retry after 18" из текста ошибки
_RETRY_AFTER_PATTERN = re.compile(r"retry(?:\s+after|\s+in)\s+(\d+)", re.IGNORECASE)


def _make_key(user_id: int) -> str:
    """Формирует ключ Redis для конкретного пользователя."""
    return f"{_FLOOD_BLOCK_KEY_PREFIX}{user_id}"


def extract_retry_after(error: Exception) -> Optional[int]:
    """
    Достаёт число секунд retry_after из исключения.

    Порядок попыток:
    1) Атрибут retry_after (если есть у исключения)
    2) Парсинг из текста ошибки через регулярку
    """
    # 1) Атрибут у исключения
    retry_after = getattr(error, "retry_after", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        return int(retry_after)

    # 2) Парсинг текста ошибки
    match = _RETRY_AFTER_PATTERN.search(str(error))
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return None
    return None


def _plural_ru(value: int, one: str, few: str, many: str) -> str:
    """
    Возвращает правильную форму слова для русского языка.

    Пример:
    1 секунда, 2 секунды, 5 секунд, 21 секунда.
    """
    value = abs(int(value))
    if 11 <= (value % 100) <= 19:
        return many
    last = value % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def format_duration_ru(total_seconds: int) -> str:
    """
    Преобразует секунды в человекочитаемый формат на русском.

    Примеры:
    - 18  -> "18 секунд"
    - 98  -> "1 минута 38 секунд"
    - 3605 -> "1 час 5 секунд"
    """
    total_seconds = max(0, int(total_seconds))

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts: list[str] = []
    if hours:
        parts.append(f"{hours} {_plural_ru(hours, 'час', 'часа', 'часов')}")
    if minutes:
        parts.append(f"{minutes} {_plural_ru(minutes, 'минута', 'минуты', 'минут')}")
    if seconds or not parts:
        parts.append(f"{seconds} {_plural_ru(seconds, 'секунда', 'секунды', 'секунд')}")

    return " ".join(parts)


def build_maintenance_message(remaining_seconds: int) -> str:
    """
    Формирует текст сообщения о технических работах для пользователя.
    """
    human_time = format_duration_ru(remaining_seconds)
    return (
        "Сервис находится на техническом обслуживании и будет доступен через "
        f"{human_time}.\n"
        "Приносим Вам извинения за неудобства."
    )


async def set_flood_block(user_id: int, retry_after: int, source: str | None = None) -> bool:
    """
    Сохраняет индивидуальную блокировку пользователя в Redis.

    Возвращает True, если блокировка установлена/обновлена.
    """
    retry_after = max(0, int(retry_after))
    if retry_after <= 0:
        return False

    redis = get_redis_client()
    key = _make_key(user_id)
    now = int(time.time())
    until_ts = now + retry_after

    # Если блокировка уже есть и она дольше текущей — не обновляем
    existing = await redis.get_json(key)
    if existing and isinstance(existing, dict):
        existing_until = int(existing.get("until", 0) or 0)
        if existing_until >= until_ts:
            return False

    payload = {
        "until": until_ts,
        "source": source or "unknown",
        "created_at": now,
    }
    await redis.set_json(key, payload, expire=retry_after)
    return True


async def get_flood_block_remaining(user_id: int) -> int:
    """
    Возвращает количество секунд до окончания блокировки.

    Если блокировка истекла — удаляет ключ и возвращает 0.
    """
    redis = get_redis_client()
    key = _make_key(user_id)
    data = await redis.get_json(key)
    if not data or not isinstance(data, dict):
        return 0

    until_ts = int(data.get("until", 0) or 0)
    now = int(time.time())
    remaining = until_ts - now
    if remaining <= 0:
        await redis.delete(key)
        return 0
    return remaining

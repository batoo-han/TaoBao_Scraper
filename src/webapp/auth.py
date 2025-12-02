"""
Утилиты для валидации запросов Telegram WebApp согласно официальной спецификации.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import parse_qsl


class WebAppAuthError(Exception):
    """
    Исключение при некорректных подписи или структуре initData.
    """


@dataclass(frozen=True)
class WebAppUserContext:
    """
    Контекст авторизованного пользователя, передаваемый в Mimi App.
    """

    user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    raw: Dict[str, Any]

    @property
    def as_dict(self) -> Dict[str, Any]:
        """
        Возвращает сериализуемое представление пользователя.
        """
        return {
            "user_id": self.user_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "username": self.username,
            "language_code": self.language_code,
        }


def _build_check_string(data: Dict[str, str]) -> str:
    """
    Формирует строку для вычисления подписи.
    """
    pairs = [f"{key}={value}" for key, value in sorted(data.items())]
    return "\n".join(pairs)


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 600) -> WebAppUserContext:
    """
    Валидирует initData из Telegram WebApp и возвращает контекст пользователя.
    """
    if not init_data:
        raise WebAppAuthError("initData отсутствует")

    items = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = items.pop("hash", None)
    if not received_hash:
        raise WebAppAuthError("hash отсутствует в initData")

    data_check_string = _build_check_string(items)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_hash, expected_hash):
        raise WebAppAuthError("подпись initData невалидна")

    auth_date_raw = items.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except ValueError as exc:
            raise WebAppAuthError("auth_date повреждена") from exc

        if time.time() - auth_date > max_age_seconds:
            raise WebAppAuthError("initData устарела, попросите пользователя открыть мини-приложение заново")

    user_payload = items.get("user")
    if not user_payload:
        raise WebAppAuthError("данные пользователя отсутствуют в initData")

    try:
        user_dict = json.loads(user_payload)
    except json.JSONDecodeError as exc:
        raise WebAppAuthError("не удалось разобрать user из initData") from exc

    return WebAppUserContext(
        user_id=int(user_dict["id"]),
        first_name=user_dict.get("first_name", ""),
        last_name=user_dict.get("last_name"),
        username=user_dict.get("username"),
        language_code=user_dict.get("language_code"),
        raw=user_dict,
    )


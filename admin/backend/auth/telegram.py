# -*- coding: utf-8 -*-
"""
Валидация Telegram Login Widget.

Реализует проверку данных, полученных от Telegram Login Widget.
https://core.telegram.org/widgets/login
"""

import hashlib
import hmac
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from admin.backend.config import admin_settings


class TelegramAuthData(BaseModel):
    """
    Данные авторизации от Telegram Login Widget.
    
    Все поля кроме hash опциональны, так как Telegram
    отправляет только те, которые есть у пользователя.
    """
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str
    
    @property
    def full_name(self) -> str:
        """Возвращает полное имя пользователя."""
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts) if parts else f"User {self.id}"
    
    @property
    def auth_datetime(self) -> datetime:
        """Возвращает время авторизации как datetime."""
        return datetime.fromtimestamp(self.auth_date, tz=timezone.utc)


def verify_telegram_auth(
    auth_data: dict,
    bot_token: Optional[str] = None,
    max_age_seconds: int = 86400,  # 24 часа
) -> Optional[TelegramAuthData]:
    """
    Проверяет данные авторизации от Telegram Login Widget.
    
    Алгоритм проверки:
    1. Создаём data-check-string из всех полей (кроме hash), отсортированных по алфавиту
    2. Вычисляем secret_key = SHA256(bot_token)
    3. Вычисляем hash = HMAC-SHA256(data-check-string, secret_key)
    4. Сравниваем с переданным hash
    5. Проверяем, что auth_date не старше max_age_seconds
    
    Args:
        auth_data: Словарь с данными от Telegram Login Widget
        bot_token: Токен бота (по умолчанию из настроек)
        max_age_seconds: Максимальный возраст авторизации в секундах
        
    Returns:
        TelegramAuthData если авторизация валидна, None иначе
    """
    # Используем токен из настроек, если не передан
    if bot_token is None:
        bot_token = admin_settings.BOT_TOKEN
    
    if not bot_token:
        return None
    
    # Проверяем наличие обязательных полей
    if "id" not in auth_data or "hash" not in auth_data or "auth_date" not in auth_data:
        return None
    
    received_hash = auth_data.get("hash", "")
    
    # Создаём data-check-string
    # Все поля кроме hash, отсортированные по алфавиту, в формате key=value
    check_items = []
    for key in sorted(auth_data.keys()):
        if key != "hash":
            check_items.append(f"{key}={auth_data[key]}")
    
    data_check_string = "\n".join(check_items)
    
    # Вычисляем secret_key = SHA256(bot_token)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    
    # Вычисляем hash = HMAC-SHA256(data-check-string, secret_key)
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    
    # Сравниваем хэши (constant-time comparison для защиты от timing attacks)
    if not hmac.compare_digest(calculated_hash, received_hash):
        return None
    
    # Проверяем возраст авторизации
    auth_date = int(auth_data.get("auth_date", 0))
    current_time = int(datetime.now(timezone.utc).timestamp())
    
    if current_time - auth_date > max_age_seconds:
        return None
    
    # Создаём и возвращаем объект с данными
    try:
        return TelegramAuthData(
            id=int(auth_data["id"]),
            first_name=auth_data.get("first_name"),
            last_name=auth_data.get("last_name"),
            username=auth_data.get("username"),
            photo_url=auth_data.get("photo_url"),
            auth_date=auth_date,
            hash=received_hash,
        )
    except Exception:
        return None

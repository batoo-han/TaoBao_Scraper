"""
Утилиты для шифрования/дешифрования чувствительных данных.

ВАЖНО:
- Ключ берётся только из .env (через settings) и нигде не хранится в коде.
- Используем симметричное шифрование Fernet (AES + HMAC) из cryptography.
"""

from __future__ import annotations

from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import settings


def _get_fernet() -> Fernet:
    """
    Возвращает объект Fernet на основе ключа из настроек.

    Это отдельная функция, чтобы:
    - централизованно валидировать ключ,
    - иметь единое место для обработки ошибок.
    """
    raw_key = (getattr(settings, "SZWEGO_AUTH_ENCRYPTION_KEY", "") or "").strip()
    if not raw_key:
        raise ValueError("Не задан SZWEGO_AUTH_ENCRYPTION_KEY в .env")
    try:
        return Fernet(raw_key.encode("utf-8"))
    except Exception as exc:
        raise ValueError(
            "Неверный формат SZWEGO_AUTH_ENCRYPTION_KEY. "
            "Ключ должен быть base64-строкой Fernet."
        ) from exc


def encrypt_text(value: Optional[str]) -> Optional[str]:
    """
    Шифрует строку для безопасного хранения в БД.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return ""
    f = _get_fernet()
    token = f.encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(value: Optional[str]) -> Optional[str]:
    """
    Дешифрует строку из БД.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return ""
    f = _get_fernet()
    try:
        data = f.decrypt(value.encode("utf-8"))
        return data.decode("utf-8")
    except InvalidToken:
        raise ValueError("Не удалось расшифровать данные: неверный ключ или повреждённые данные")

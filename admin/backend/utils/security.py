# -*- coding: utf-8 -*-
"""
Утилиты безопасности для админ-панели.

Содержит функции для:
- Санитизации пользовательского ввода
- Валидации данных
- Генерации ключей для rate limiting
"""

import re
import html
from typing import Optional


def sanitize_input(value: str, max_length: int = 255) -> str:
    """
    Санитизирует строку пользовательского ввода.
    
    Защита от XSS и SQL-инъекций:
    - Экранирует HTML специальные символы
    - Удаляет управляющие символы
    - Обрезает до максимальной длины
    
    Args:
        value: Входная строка
        max_length: Максимальная длина результата
        
    Returns:
        Очищенная строка
    """
    if not value:
        return ""
    
    # Удаляем управляющие символы (кроме пробелов и переносов)
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
    
    # Экранируем HTML
    value = html.escape(value, quote=True)
    
    # Обрезаем до максимальной длины
    return value[:max_length]


def validate_email(email: str) -> bool:
    """
    Проверяет корректность email адреса.
    
    Args:
        email: Email для проверки
        
    Returns:
        True если email корректный
    """
    if not email:
        return False
    
    # Простая регулярка для email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def rate_limit_key(prefix: str, identifier: str) -> str:
    """
    Генерирует ключ для rate limiting.
    
    Args:
        prefix: Префикс ключа (например, "login", "api")
        identifier: Идентификатор (IP, user_id, etc.)
        
    Returns:
        Ключ для Redis
    """
    # Очищаем идентификатор от спецсимволов
    safe_id = re.sub(r'[^a-zA-Z0-9:._-]', '', str(identifier))
    return f"ratelimit:{prefix}:{safe_id}"


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """
    Маскирует чувствительные данные для логирования.
    
    Args:
        data: Данные для маскировки
        visible_chars: Количество видимых символов в начале и конце
        
    Returns:
        Замаскированная строка
    """
    if not data or len(data) <= visible_chars * 2:
        return "*" * len(data) if data else ""
    
    return f"{data[:visible_chars]}{'*' * (len(data) - visible_chars * 2)}{data[-visible_chars:]}"


def is_safe_redirect_url(url: str, allowed_hosts: list[str]) -> bool:
    """
    Проверяет, безопасен ли URL для редиректа.
    
    Защита от Open Redirect уязвимости.
    
    Args:
        url: URL для проверки
        allowed_hosts: Список разрешённых хостов
        
    Returns:
        True если URL безопасен
    """
    if not url:
        return False
    
    # Относительные URL разрешены
    if url.startswith('/') and not url.startswith('//'):
        return True
    
    # Проверяем хост
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        return parsed.netloc in allowed_hosts
    except Exception:
        return False


def generate_csrf_token() -> str:
    """
    Генерирует CSRF токен.
    
    Returns:
        Случайный токен
    """
    import secrets
    return secrets.token_urlsafe(32)

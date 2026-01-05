"""
Утилиты для формирования ключей кэша для продуктов.
"""

import hashlib
import json
from typing import Any, Dict


def normalize_api_response_for_cache(api_response: dict) -> dict:
    """
    Нормализует API-ответ для стабильного хеширования.
    Убирает временные/нестабильные поля.
    
    Args:
        api_response: Ответ от API (tmapi/szwego/pinduoduo)
    
    Returns:
        dict: Нормализованный словарь для хеширования
    """
    # Создаем копию, чтобы не изменять исходный объект
    normalized = {}
    
    # Извлекаем data, если есть
    if isinstance(api_response, dict):
        if 'data' in api_response:
            product_data = api_response['data'].copy() if isinstance(api_response['data'], dict) else api_response['data']
        else:
            product_data = api_response.copy()
        
        # Убираем временные/нестабильные поля
        fields_to_remove = [
            'request_id',
            'timestamp',
            '_request_time',
            '_cached_at',
            '_platform',  # Сохраняем в отдельном поле для ключа, но не хешируем
        ]
        
        # Рекурсивно очищаем вложенные словари
        def clean_dict(d: Any) -> Any:
            if isinstance(d, dict):
                cleaned = {}
                for k, v in d.items():
                    if k not in fields_to_remove:
                        cleaned[k] = clean_dict(v)
                return cleaned
            elif isinstance(d, list):
                return [clean_dict(item) for item in d]
            else:
                return d
        
        normalized = clean_dict(product_data)
    
    return normalized


def build_cache_key(api_response: dict, user_settings: dict) -> str:
    """
    Формирует ключ кэша на основе API-ответа и настроек пользователя.
    
    Args:
        api_response: Ответ от API (tmapi/szwego/pinduoduo)
        user_settings: Словарь с настройками пользователя:
            - signature: str - подпись пользователя
            - currency: str - валюта (cny/rub)
            - price_mode: str - режим цен (simple/advanced)
            - exchange_rate: float | None - курс обмена
    
    Returns:
        str: Ключ кэша в формате "cache:product:{hex_hash}"
    """
    # Нормализуем API-ответ
    normalized_api = normalize_api_response_for_cache(api_response)
    
    # Нормализуем настройки пользователя для стабильного хеширования
    normalized_settings = {
        "signature": str(user_settings.get("signature", "")).strip(),
        "currency": str(user_settings.get("currency", "cny")).strip().lower(),
        "price_mode": str(user_settings.get("price_mode", "simple")).strip().lower(),
        "exchange_rate": user_settings.get("exchange_rate"),  # None или float
    }
    
    # Создаем словарь для хеширования
    cache_data = {
        "api_response": normalized_api,
        "user_settings": normalized_settings
    }
    
    # Хешируем
    cache_json = json.dumps(cache_data, sort_keys=True, ensure_ascii=False)
    cache_hash = hashlib.sha256(cache_json.encode('utf-8')).hexdigest()
    
    return f"cache:product:{cache_hash}"

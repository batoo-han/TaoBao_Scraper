"""
Модуль для работы с ценами токенов OpenAI.

Содержит стандартные цены для популярных моделей OpenAI и функции для их получения.
Если цены указаны в настройках вручную, они имеют приоритет.
"""

# Стандартные цены OpenAI в USD за 1 000 000 токенов (на 2024 год)
# Источник: https://openai.com/pricing
STANDARD_OPENAI_PRICING = {
    # GPT-4o models
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "gpt-4o-2024-08-06": {"prompt": 2.50, "completion": 10.00},
    
    # GPT-4 Turbo models
    "gpt-4-turbo": {"prompt": 10.00, "completion": 30.00},
    "gpt-4-turbo-2024-04-09": {"prompt": 10.00, "completion": 30.00},
    
    # GPT-4 models
    "gpt-4": {"prompt": 30.00, "completion": 60.00},
    "gpt-4-32k": {"prompt": 60.00, "completion": 120.00},
    
    # GPT-3.5 models
    "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
    
    # GPT-4.1 models (если существуют)
    "gpt-4.1-mini": {"prompt": 0.15, "completion": 0.60},  # Предположительно как gpt-4o-mini
    
    # O4 models
    "o4-mini": {"prompt": 0.15, "completion": 0.60},  # Предположительно как gpt-4o-mini
    
    # GPT-5 models (цены с официального сайта OpenAI)
    "gpt-5": {"prompt": 3.00, "completion": 12.00},
    "gpt-5-mini": {"prompt": 0.25, "completion": 2.00},  # Официальные цены: $0.25/$2.00 за 1M токенов
    "gpt-5.1": {"prompt": 3.00, "completion": 12.00},
    "gpt-5.1-mini": {"prompt": 0.25, "completion": 2.00},
    "gpt-5.1-nano": {"prompt": 0.10, "completion": 0.40},
}


def get_model_pricing(model_name: str) -> tuple[float, float]:
    """
    Получает стандартные цены для модели OpenAI.
    
    Args:
        model_name: Название модели (например, "gpt-4o-mini")
    
    Returns:
        Tuple (prompt_price_per_1m, completion_price_per_1m) в USD за 1 000 000 токенов
        Если модель не найдена, возвращает (0.0, 0.0)
    """
    normalized = (model_name or "").strip().lower()
    
    # Прямое совпадение
    if normalized in STANDARD_OPENAI_PRICING:
        pricing = STANDARD_OPENAI_PRICING[normalized]
        return pricing["prompt"], pricing["completion"]
    
    # Проверка префиксов для моделей с версиями
    for key, pricing in STANDARD_OPENAI_PRICING.items():
        if normalized.startswith(key.split("-")[0] + "-"):
            # Близкое совпадение (например, gpt-4o-2024-08-06 для gpt-4o)
            return pricing["prompt"], pricing["completion"]
    
    # Если модель не найдена, возвращаем значения по умолчанию
    # (пользователь должен будет указать цены вручную или они возьмутся из ответа API)
    return 0.0, 0.0


def get_effective_pricing(
    model_name: str,
    prompt_price_override: float,
    completion_price_override: float,
) -> tuple[float, float]:
    """
    Получает эффективные цены токенов с учетом переопределений и стандартных значений.
    
    Args:
        model_name: Название модели
        prompt_price_override: Цена за 1 000 000 входных токенов из настроек (0 = автодетекция)
        completion_price_override: Цена за 1 000 000 выходных токенов из настроек (0 = автодетекция)
    
    Returns:
        Tuple (prompt_price_per_1m, completion_price_per_1m) в USD за 1 000 000 токенов
    """
    # Если цены указаны вручную, используем их
    if prompt_price_override > 0 and completion_price_override > 0:
        return prompt_price_override, completion_price_override
    
    # Иначе пытаемся взять стандартные цены для модели
    prompt_price, completion_price = get_model_pricing(model_name)
    
    # Если нашли стандартные цены, используем их
    if prompt_price > 0 or completion_price > 0:
        return prompt_price, completion_price
    
    # Если ничего не найдено, возвращаем 0 (будет использована информация из ответа API или не будет показана стоимость)
    return 0.0, 0.0


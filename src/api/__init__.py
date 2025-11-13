"""
API Package
===========
External API clients (TMAPI, YandexGPT, Yandex.Translate, ExchangeRate).
"""

from .tmapi import TmapiClient
from .yandex_gpt import YandexLLMProvider
from .yandex_translate import YandexTranslateClient
from .exchange_rate import ExchangeRateClient

# Обратная совместимость: алиас для старого имени
YandexGPTClient = YandexLLMProvider

__all__ = [
    'TmapiClient',
    'YandexLLMProvider',
    'YandexGPTClient',  # Алиас для обратной совместимости
    'YandexTranslateClient',
    'ExchangeRateClient'
]


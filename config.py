"""
==============================================================================
TAOBAO SCRAPER BOT - CONFIGURATION
==============================================================================
Управление конфигурацией через переменные окружения.
Использует Pydantic Settings для валидации и загрузки из .env файла.

Author: Your Name
Version: 1.0.0
License: MIT
==============================================================================
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Класс для управления настройками приложения.
    
    Автоматически загружает переменные окружения из файла .env
    с валидацией типов и значений по умолчанию.
    
    Attributes:
        BOT_TOKEN (str): Токен Telegram бота от @BotFather
        TMAPI_TOKEN (str): API ключ для TMAPI (tmapi.top)
        YANDEX_GPT_API_KEY (str): API ключ YandexGPT
        YANDEX_FOLDER_ID (str): ID каталога Yandex Cloud
        EXCHANGE_RATE_API_KEY (str): API ключ для конвертации валют
        GOOGLE_CLOUD_PROJECT (str): Google Cloud Project ID (не используется)
        ADMIN_CHAT_ID (str): Telegram Chat ID админа для уведомлений об ошибках
        YANDEX_GPT_MODEL (str): Модель YandexGPT (yandexgpt-lite или yandexgpt)
        CONVERT_CURRENCY (bool): Включить конвертацию валют
        DEBUG_MODE (bool): Режим отладки с подробными логами
        MOCK_MODE (bool): Mock режим для тестирования без API
        DISABLE_SSL_VERIFY (bool): Отключить проверку SSL (не рекомендуется)
    """
    BOT_TOKEN: str  # Токен Telegram бота
    TMAPI_TOKEN: str  # API ключ для tmapi.top
    YANDEX_GPT_API_KEY: str  # API ключ для YandexGPT
    EXCHANGE_RATE_API_KEY: str  # API ключ для ExchangeRate-API
    YANDEX_FOLDER_ID: str # ID каталога в Yandex.Cloud
    GOOGLE_CLOUD_PROJECT: str = ""  # ID проекта Google Cloud (не используется, оставлено для совместимости)
    ADMIN_CHAT_ID: str = ""  # ID чата администратора для уведомлений об ошибках (необязательно)
    YANDEX_GPT_MODEL: str = "yandexgpt-lite"  # Модель YandexGPT для использования
    CONVERT_CURRENCY: bool = False  # Флаг для включения/отключения конвертации валют
    DEBUG_MODE: bool = False  # Режим отладки - показывать подробные логи в консоли
    MOCK_MODE: bool = False  # Mock режим - использовать данные из result.txt вместо реальных API-запросов к TMAPI
    DISABLE_SSL_VERIFY: bool = False  # Отключить проверку SSL (только если есть проблемы с сертификатами)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

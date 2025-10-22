from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Класс для управления настройками приложения.
    Загружает переменные окружения из файла .env.
    """
    BOT_TOKEN: str  # Токен Telegram бота
    TMAPI_TOKEN: str  # API ключ для tmapi.top
    YANDEX_GPT_API_KEY: str  # API ключ для YandexGPT
    EXCHANGE_RATE_API_KEY: str  # API ключ для ExchangeRate-API
    YANDEX_FOLDER_ID: str # ID каталога в Yandex.Cloud
    GOOGLE_CLOUD_PROJECT: str # ID проекта Google Cloud
    YANDEX_GPT_MODEL: str = "yandexgpt-lite"  # Модель YandexGPT для использования
    CONVERT_CURRENCY: bool = False  # Флаг для включения/отключения конвертации валют
    DEBUG_MODE: bool = False  # Режим отладки (использует result.txt вместо реальных API-запросов к TMAPI)
    DISABLE_SSL_VERIFY: bool = False  # Отключить проверку SSL (только если есть проблемы с сертификатами)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

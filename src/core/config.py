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
        TMAPI_TOKEN (str): API ключ для TMAPI Taobao/Tmall (tmapi.top)
        TMAPI_PINDUODUO_TOKEN (str): API ключ для TMAPI Pinduoduo (tmapi.top)
        TMAPI_RATE_LIMIT (int): Максимальное количество запросов к TMAPI в секунду
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
    TMAPI_TOKEN: str  # API ключ для tmapi.top (Taobao/Tmall)
    TMAPI_PINDUODUO_TOKEN: str = ""  # Не используется (Pinduoduo через веб-скрапинг)
    YANDEX_GPT_API_KEY: str  # API ключ для YandexGPT
    EXCHANGE_RATE_API_KEY: str  # API ключ для ExchangeRate-API
    YANDEX_FOLDER_ID: str # ID каталога в Yandex.Cloud
    GOOGLE_CLOUD_PROJECT: str = ""  # ID проекта Google Cloud (не используется, оставлено для совместимости)
    ADMIN_CHAT_ID: str = ""  # ID чата администратора для уведомлений об ошибках (необязательно)
    TMAPI_BILLING_CHAT_ID: str = ""  # ID чата ответственного за оплату TMAPI для уведомлений об ошибке 439 (необязательно)
    YANDEX_GPT_MODEL: str = "yandexgpt-lite"  # Модель YandexGPT для использования
    TMAPI_RATE_LIMIT: int = 5  # Максимальное количество запросов к TMAPI в секунду (по умолчанию 5)
    CONVERT_CURRENCY: bool = False  # Флаг для включения/отключения конвертации валют
    DEBUG_MODE: bool = False  # Режим отладки - показывать подробные логи в консоли
    MOCK_MODE: bool = False  # Mock режим - использовать данные из result.txt вместо реальных API-запросов к TMAPI
    DISABLE_SSL_VERIFY: bool = False  # Отключить проверку SSL (только если есть проблемы с сертификатами)
    TMAPI_NOTIFY_439: bool = False  # Уведомлять пользователя и админа об ошибке 439 (недостаточно средств на счету TMAPI)

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "taobao_scraper"
    POSTGRES_USER: str = "taobao"
    POSTGRES_PASSWORD: str = "taobao_scraper"
    POSTGRES_SSLMODE: str = "prefer"
    DATABASE_URL: str | None = None  # если задано — используем напрямую (async URL)

    # LLM / приложение (будет храниться и в БД, но нужны дефолты)
    DEFAULT_SIGNATURE: str = "@annabbox"
    DEFAULT_CURRENCY: str = "cny"  # глобальный дефолт
    DEFAULT_LLM_VENDOR: str = "yandex"  # yandex | openai | proxiapi
    LLM_CACHE_TTL_MINUTES: int = 240
    
    # OpenAI настройки
    OPENAI_API_KEY: str = ""  # API ключ OpenAI (необязательно, если не используется)
    OPENAI_MODEL: str = "gpt-4o-mini"  # Модель OpenAI по умолчанию
    
    # ProxiAPI настройки
    PROXIAPI_API_KEY: str = ""  # API ключ ProxiAPI (необязательно, если не используется)
    PROXIAPI_MODEL: str = "gpt-4o-mini"  # Модель ProxiAPI по умолчанию
    
    # Admin Panel настройки
    ADMIN_JWT_SECRET: str = "change-this-secret-key-in-production"  # Секретный ключ для JWT токенов админ-панели
    ADMIN_PANEL_PORT: int = 8004  # Порт для админ-панели

    # Pinduoduo Web Scraping настройки
    PDD_USE_COOKIES: bool = True  # Использовать заранее выданные браузером куки вместо логина
    PDD_USER_AGENT: str = ""  # User-Agent из вашего браузера
    PDD_COUNTRY_CODE: str = ""  # Код страны (например, +86)
    PDD_PHONE_NUMBER: str = ""  # Номер телефона без пробелов
    PDD_LOGIN_MAX_ATTEMPTS: int = 5  # Максимум повторных отправок кода
    PDD_LOGIN_CODE_TIMEOUT_SEC: int = 120  # Секунд до повторной отправки кода
    PDD_COOKIES_FILE: str = "src/pdd_cookies.json"  # Путь к JSON с куки/UA
    # Playwright
    PLAYWRIGHT_PROXY: str = ""  # Формат: http://127.0.0.1:10809 или socks5://127.0.0.1:10808
    PLAYWRIGHT_SLOWMO_MS: int = 100  # Замедление действий при DEBUG для наглядности
    PLAYWRIGHT_PAGE_TIMEOUT_MS: int = 60000  # Таймаут полной загрузки страницы (по умолчанию 60 сек)
    PLAYWRIGHT_USE_MOBILE: bool = False  # Эмулировать мобильное устройство
    PLAYWRIGHT_MOBILE_DEVICE: str = "iPhone 12"  # Название пресета устройства из playwright.devices
    PLAYWRIGHT_LOCALE: str = "zh-CN"  # Локаль для мобильного профиля
    PLAYWRIGHT_TIMEZONE: str = "Asia/Shanghai"  # Таймзона для мобильного профиля
    # Debug вспомогательные опции для Playwright
    PLAYWRIGHT_KEEP_BROWSER_OPEN: bool = False  # Не закрывать браузер в DEBUG_MODE

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra='ignore'  # Игнорировать лишние переменные в .env (на случай устаревших ключей)
    )


# Создаем объект settings из .env
_settings_instance = Settings()

# Экспортируем settings как глобальную переменную
# При загрузке из БД этот объект будет обновлен
settings = _settings_instance


def build_async_db_url() -> str:
    """
    Возвращает async URL для SQLAlchemy.

    Если в .env задан DATABASE_URL, он используется напрямую.
    Иначе собираем URL из отдельных переменных (использует asyncpg).
    """
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    return (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )

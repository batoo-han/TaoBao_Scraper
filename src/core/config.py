"""
==============================================================================
TAOBAO SCRAPER BOT - CONFIGURATION
==============================================================================
Управление конфигурацией через переменные окружения.
Использует Pydantic Settings для валидации и загрузки из .env файла.

Author: Your Name
Version: 3.0.0
License: MIT
==============================================================================
"""

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    # Fallback для старых версий pydantic
    from pydantic import BaseSettings, Field
    SettingsConfigDict = dict


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
        OPENAI_API_KEY (str): API ключ OpenAI для альтернативного провайдера
        OPENAI_BASE_URL (str): Базовый URL для OpenAI или кастомного шлюза
        PROXYAPI_API_KEY (str): API ключ ProxyAPI (openai-совместимый провайдер)
        PROXYAPI_BASE_URL (str): Базовый URL OpenAI-совместимого API ProxyAPI
        YANDEX_FOLDER_ID (str): ID каталога Yandex Cloud
        EXCHANGE_RATE_API_KEY (str): API ключ для конвертации валют
        GOOGLE_CLOUD_PROJECT (str): Google Cloud Project ID (не используется)
        ADMIN_CHAT_ID (str): Telegram Chat ID админа для уведомлений об ошибках
        ADMIN_GROUP_BOT (str): Дополнительные админские Telegram ID через запятую
        YANDEX_GPT_MODEL (str): Модель YandexGPT (yandexgpt-lite или yandexgpt)
        OPENAI_MODEL (str): Основная модель OpenAI (например, gpt-4o-mini)
        OPENAI_FALLBACK_CHAT_MODEL (str): Fallback-модель для Chat Completions, если выбрана gpt-5* (требует Responses API)
        DEFAULT_LLM (str): Имя провайдера LLM (yandex или openai)
        OPENAI_STRATEGY (str): Стратегия работы с OpenAI (legacy или single_pass)
        OPENAI_PROMPT_VARIANT (str): Вариант промпта для OpenAI (shared или compact_v1)
        OPENAI_MAX_OUTPUT_TOKENS (int): Максимум выходных токенов OpenAI при генерации JSON-поста
        OPENAI_SINGLE_PASS_MAX_SKUS (int): Максимум SKU, отправляемых в OpenAI в single_pass
        OPENAI_SINGLE_PASS_MAX_SKU_VALUES (int): Максимум значений в sku_props на один prop
        OPENAI_SINGLE_PASS_MAX_PROP_VALUE_LEN (int): Максимальная длина строкового значения в product_props (остальное обрезается)
        TRANSLATE_PROVIDER (str): Провайдер LLM для переводов и обработки цен
        TRANSLATE_LLM (str): (deprecated) Старая переменная для совместимости
        TRANSLATE_MODEL (str): Конкретная модель переводческого LLM
        TRANSLATE_OPENAI_MODEL (str): (deprecated) имя модели OpenAI для переводов
        TRANSLATE_LEGACY (bool): Использовать ли старый Yandex Translate вместо LLM
        CONVERT_CURRENCY (bool): Включить конвертацию валют
        DEBUG_MODE (bool): Режим отладки с подробными логами
        MOCK_MODE (bool): Mock режим для тестирования без API
        DISABLE_SSL_VERIFY (bool): Отключить проверку SSL (не рекомендуется)
        TMAPI_TIMEOUT (float): Таймаут HTTP-запросов к TMAPI в секундах
    """
    BOT_TOKEN: str  # Токен Telegram бота
    TMAPI_TOKEN: str  # API ключ для tmapi.top (Taobao/Tmall)
    TMAPI_ALI_TOKEN: str = ""  # API ключ TMAPI для 1688 (ali/item_detail*)
    TMAPI_PINDUODUO_TOKEN: str = ""  # Не используется (Pinduoduo через веб-скрапинг)
    YANDEX_GPT_API_KEY: str  # API ключ для YandexGPT
    EXCHANGE_RATE_API_KEY: str  # API ключ для ExchangeRate-API
    OPENAI_API_KEY: str = ""  # API ключ для OpenAI (опционален, может быть dummy при использовании шлюза)
    OPENAI_BASE_URL: str = ""  # Кастомный base URL (например, https://llm-gw.example.com/v1)
    PROXYAPI_API_KEY: str = ""  # API ключ ProxyAPI (https://proxyapi.ru)
    PROXYAPI_BASE_URL: str = "https://api.proxyapi.ru/openai/v1"  # OpenAI-совместимый endpoint ProxyAPI
    PROXYAPI_BILLING_CHAT_ID: str = ""  # Чат для уведомлений о балансе ProxyAPI
    PROXYAPI_NOTIFY_402: bool = False  # Уведомлять о 402 (исчерпан баланс) ProxyAPI
    YANDEX_FOLDER_ID: str # ID каталога в Yandex.Cloud
    GOOGLE_CLOUD_PROJECT: str = ""  # ID проекта Google Cloud (не используется, оставлено для совместимости)
    ADMIN_CHAT_ID: str = ""  # ID чата администратора для уведомлений об ошибках (необязательно)
    ADMIN_GROUP_BOT: str = ""  # Дополнительные админы бота (список Telegram ID через запятую)
    TMAPI_BILLING_CHAT_ID: str = ""  # ID чата ответственного за оплату TMAPI для уведомлений об ошибке 439 (необязательно)
    YANDEX_GPT_MODEL: str = "yandexgpt-lite"  # Модель YandexGPT для использования
    OPENAI_MODEL: str = "gpt-4o-mini"  # Модель OpenAI по умолчанию
    # Responses API используется для всех моделей OpenAI (gpt-4 и gpt-5) согласно документации
    # Если False, используется устаревший Chat Completions API (не рекомендуется)
    OPENAI_USE_RESPONSES_API: bool = True
    # Уровень рассуждений для моделей семейства gpt-5
    # Используется только для gpt-5 моделей, для остальных игнорируется
    # Поддерживаемые значения зависят от модели:
    #   - gpt-5, gpt-5-mini, gpt-5-nano: minimal, low, medium, high
    #   - gpt-5.1, gpt-5.1-mini, gpt-5.1-nano: none, low, medium, high
    #   - gpt-5.2 и выше: none, low, medium, high
    # Если значение не поддерживается моделью, будет автоматически конвертировано
    # Пустое значение = автоматический выбор по умолчанию для модели
    OPENAI_REASONING_EFFORT: str = ""
    # Если указана gpt-5* модель, но Responses API отключён (мы используем Chat Completions),
    # переключаемся на совместимую fallback-модель, чтобы избежать пустых ответов.
    OPENAI_FALLBACK_CHAT_MODEL: str = "gpt-4o-mini"
    DEFAULT_LLM: str = "yandex"  # Провайдер LLM по умолчанию
    # Стратегия работы с OpenAI:
    # - "legacy"      — старое поведение: предварительный перевод + компактные данные
    # - "single_pass" — новый режим: сразу отдаём сырой ответ TMAPI (только нужные поля) в OpenAI
    OPENAI_STRATEGY: str = "single_pass"
    # Вариант промпта для OpenAI (не влияет на YandexGPT/ProxyAPI):
    # - "shared"      — использовать общий промпт POST_GENERATION_PROMPT (длинный, с примерами)
    # - "compact_v1"  — первый компактный промпт OpenAI (очень короткий, может быть «вольным»)
    # - "compact_v2"  — компактный промпт OpenAI с более строгими правилами (рекомендуется)
    OPENAI_PROMPT_VARIANT: str = "compact_v2"
    # Лимит выходных токенов при генерации JSON-поста через OpenAI.
    # Чем меньше — тем дешевле, но слишком низкие значения могут приводить к обрезанному JSON.
    OPENAI_MAX_OUTPUT_TOKENS: int = 2400
    # Ограничения для single_pass, чтобы не раздувать prompt токенами
    OPENAI_SINGLE_PASS_MAX_SKUS: int = 120
    OPENAI_SINGLE_PASS_MAX_SKU_VALUES: int = 60
    OPENAI_SINGLE_PASS_MAX_PROP_VALUE_LEN: int = 220
    TRANSLATE_PROVIDER: str = ""  # Провайдер LLM для переводов (по умолчанию = DEFAULT_LLM)
    TRANSLATE_LLM: str = ""  # Backward compatibility alias
    TRANSLATE_MODEL: str = ""  # Конкретная модель для переводов
    TRANSLATE_OPENAI_MODEL: str = "gpt-4o-mini"  # Legacy-поле для OpenAI моделей
    TRANSLATE_LEGACY: bool = False  # True → использовать Yandex Translate вместо LLM
    PRICE_MODE: str = "simple"  # Режим цен: simple (только максимальная цена) или advanced (перевод и сводка вариантов)
    # Глобальные лимиты (0 или пусто = без ограничений)
    PER_USER_DAILY_LIMIT: int | None = None  # Лимит запросов на пользователя в сутки (МСК)
    PER_USER_MONTHLY_LIMIT: int | None = None  # Лимит запросов на пользователя в месяц (МСК)
    TOTAL_DAILY_LIMIT: int | None = None  # Общий лимит запросов всех пользователей в сутки (МСК)
    TOTAL_MONTHLY_LIMIT: int | None = None  # Общий лимит запросов всех пользователей в месяц (МСК)
    TMAPI_RATE_LIMIT: int = 5  # Максимальное количество запросов к TMAPI в секунду (по умолчанию 5)
    TMAPI_RETRY_ATTEMPTS: int = 3  # Количество повторов для TMAPI при ошибках сети/429/5xx
    TMAPI_RETRY_BACKOFF: float = 0.5  # Базовая задержка перед повтором (сек), экспоненциальный рост
    CONVERT_CURRENCY: bool = False  # Флаг для включения/отключения конвертации валют
    DEFAULT_SIGNATURE: str = ""  # Подпись по умолчанию для постов (пустая - пользователи задают свою)
    DEFAULT_CURRENCY: str = "cny"  # Валюта по умолчанию (cny или rub)
    DEBUG_MODE: bool = False  # Режим отладки - показывать подробные логи в консоли
    MOCK_MODE: bool = False  # Mock режим - использовать данные из result.txt вместо реальных API-запросов к TMAPI
    DISABLE_SSL_VERIFY: bool = False  # Отключить проверку SSL (только если есть проблемы с сертификатами)
    TMAPI_NOTIFY_439: bool = False  # Уведомлять пользователя и админа об ошибке 439 (недостаточно средств на счету TMAPI)

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

    # Таймауты внешних API
    TMAPI_TIMEOUT: float = 30.0  # Таймаут запросов к TMAPI (секунды)

    # Mimi App
    MINI_APP_URL: str = ""  # Публичная ссылка на Mimi App для кнопки в Telegram
    MINI_APP_HOST: str = "0.0.0.0"  # Хост локального сервера Mimi App
    MINI_APP_PORT: int = 8081  # Порт сервера Mimi App
    MINI_APP_BASE_PATH: str = "/mini-app"  # URL-путь Mimi App (используется и для статических файлов)

    # Сообщения по доступу к боту
    ACCESS_SUPPORT_USERNAME: str = ""  # Ник в Telegram (без @), к которому можно обратиться по поводу доступа

    # Канал для дублирования всех постов
    FORWARD_CHANNEL_ID: str = ""  # ID или @username канала, куда дублировать посты

    # Переключатели платформ (True/False, по умолчанию False - платформа выключена)
    ENABLE_TAOBAO: bool = False  # Включить поддержку Taobao
    ENABLE_TMALL: bool = False  # Включить поддержку Tmall
    ENABLE_1688: bool = False  # Включить поддержку 1688
    ENABLE_PINDUODUO: bool = False  # Включить поддержку Pinduoduo
    ENABLE_SZWEGO: bool = False  # Включить поддержку Szwego

    # Szwego (API)
    # Важно: Szwego API работает только с валидными cookies + user-agent.
    # Эти данные хранятся в JSON-файле (НЕ коммитить) и должны периодически обновляться вручную.
    SZWEGO_BASE_URL: str = "https://www.szwego.com"
    SZWEGO_COOKIES_FILE: str = "cookies/szwego_cookies.json"  # Путь к JSON с cookies+UA (см. cookies/szwego_cookies_example.json)
    SZWEGO_TIMEOUT: float = 30.0  # Таймаут запросов к Szwego API (секунды)
    SZWEGO_TRANS_LANG: str = "en"  # transLang для API (обычно "en" или "zh")
    # “Запас” в секундах: считаем токен истёкшим немного заранее, чтобы не ловить граничные состояния
    SZWEGO_TOKEN_EXPIRE_GRACE_SEC: int = 60

    # Мониторинг токена Szwego (фоновые проверки и алерты админу)
    SZWEGO_MONITOR_ENABLED: bool = True
    SZWEGO_MONITOR_INTERVAL_SEC: int = 3600  # раз в час
    SZWEGO_TOKEN_EXPIRY_WARN_SEC: int = 24 * 3600  # предупреждать за 24 часа до expires
    SZWEGO_ALERT_MIN_INTERVAL_SEC: int = 6 * 3600  # не чаще 1 раза в 6 часов (анти-спам)
    # Опционально: URL товара для “пинга” API, если хотите проверять не только expires, но и реальную авторизацию
    SZWEGO_HEALTHCHECK_URL: str = ""

    # Постобработка текста поста через отдельную LLM-модель
    # ВАЖНО:
    # - Если ENABLE_POSTPROCESSING=False, шаг постобработки полностью пропускается.
    # - Для постобработки используется отдельный OpenAI-клиент с компактной моделью
    #   (например, gpt-4o-mini или gpt-4.1-mini), задаваемой через OPENAI_POSTPROCESS_MODEL.
    # - Если модель не указана, используется глобальная OPENAI_MODEL.
    ENABLE_POSTPROCESSING: bool = False
    OPENAI_POSTPROCESS_MODEL: str = ""

    # Генерация хэштегов через отдельную LLM-модель
    # ВАЖНО:
    # - Если ENABLE_HASHTAGS=False, хэштеги не генерируются.
    # - Хэштеги генерируются на основе готового поста (после генерации поста, но до постобработки).
    # - Провайдер задаётся через HASHTAGS_PROVIDER (yandex/openai/proxyapi), если пусто - используется DEFAULT_LLM.
    # - Модель задаётся через HASHTAGS_MODEL, если пусто - используется модель провайдера по умолчанию.
    ENABLE_HASHTAGS: bool = False
    HASHTAGS_PROVIDER: str = ""  # Провайдер для генерации хэштегов (yandex/openai/proxyapi), если пусто - DEFAULT_LLM
    HASHTAGS_MODEL: str = ""  # Модель для генерации хэштегов, если пусто - модель провайдера по умолчанию

    # Настройки цен токенов OpenAI (в USD за 1 000 000 токенов)
    # Если не указаны, будут использоваться стандартные цены OpenAI по модели
    # Можно указать вручную, если используете кастомный шлюз или хотите переопределить цены
    # Пример для gpt-5-mini: OPENAI_PROMPT_PRICE_PER_1M=0.25, OPENAI_COMPLETION_PRICE_PER_1M=2.00
    OPENAI_PROMPT_PRICE_PER_1M: float = 0.0  # Цена за 1M входных токенов (0 = автодетекция из ответа или стандартные цены)
    OPENAI_COMPLETION_PRICE_PER_1M: float = 0.0  # Цена за 1M выходных токенов (0 = автодетекция из ответа или стандартные цены)
    # Настройки цен токенов ProxyAPI (аналогично OpenAI)
    PROXYAPI_PROMPT_PRICE_PER_1M: float = 0.0  # Цена за 1M входных токенов
    PROXYAPI_COMPLETION_PRICE_PER_1M: float = 0.0  # Цена за 1M выходных токенов

    # Database (PostgreSQL)
    POSTGRES_DB: str = "taobao_bot"  # Имя базы данных
    POSTGRES_USER: str = "taobao_user"  # Пользователь PostgreSQL
    POSTGRES_PASSWORD: str = "changeme"  # Пароль PostgreSQL
    POSTGRES_HOST: str = "localhost"  # Хост PostgreSQL (localhost для локальной БД, postgres для Docker)
    POSTGRES_PORT: int = 5432  # Порт PostgreSQL
    DATABASE_URL: str = ""  # Строка подключения к PostgreSQL (формируется автоматически из компонентов)
    DB_POOL_SIZE: int = 10  # Размер пула соединений с БД
    DB_MAX_OVERFLOW: int = 20  # Максимальное переполнение пула соединений
    
    # Redis
    REDIS_URL: str = "redis://:changeme@redis:6379/0"  # Строка подключения к Redis
    REDIS_PASSWORD: str = "changeme"  # Пароль Redis
    REDIS_PORT: int = 6379  # Порт Redis
    REDIS_DB: int = 0  # Номер базы данных Redis
    
    # Настройки кэширования
    CACHE_ENABLED: bool = True  # Включить/выключить кэширование
    CACHE_TTL_SECONDS: int = 3600  # Время жизни кэша в секундах (по умолчанию 1 час)
    CACHE_PREFIX: str = "cache:product"  # Префикс для ключей кэша

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra='ignore'  # Игнорировать лишние переменные в .env (на случай устаревших ключей)
    )
    
    def __init__(self, **kwargs):
        """Инициализация с автоматическим формированием DATABASE_URL"""
        super().__init__(**kwargs)
        # Формируем DATABASE_URL из компонентов, если он не указан явно в .env
        if not self.DATABASE_URL or self.DATABASE_URL.strip() == "":
            from urllib.parse import quote_plus
            encoded_password = quote_plus(self.POSTGRES_PASSWORD)
            self.DATABASE_URL = f"postgresql+asyncpg://{self.POSTGRES_USER}:{encoded_password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


settings = Settings()

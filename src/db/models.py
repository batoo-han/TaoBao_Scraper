"""
SQLAlchemy модели для базы данных.
"""

from datetime import date
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Enum as SQLEnum,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class ListType(str, enum.Enum):
    """Тип списка доступа"""
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"


class EntryType(str, enum.Enum):
    """Тип записи в списке доступа"""
    ID = "id"
    USERNAME = "username"


class User(Base):
    """Таблица пользователей"""
    __tablename__ = "users"
    
    user_id = Column(BigInteger, primary_key=True, comment="Telegram user ID")
    username = Column(String(255), nullable=True, comment="Telegram username (без @)")
    created_at = Column(Date, nullable=False, comment="Дата первой регистрации")
    
    # Связи
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    rate_limits = relationship("RateLimitUser", back_populates="user", cascade="all, delete-orphan")
    szwego_auth = relationship("SzwegoAuth", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserSettings(Base):
    """Настройки пользователей"""
    __tablename__ = "user_settings"
    
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True, comment="Telegram user ID")
    signature = Column(Text, nullable=False, default="", comment="Подпись пользователя для постов")
    default_currency = Column(String(10), nullable=False, default="cny", comment="Валюта по умолчанию (cny/rub)")
    exchange_rate = Column(Float, nullable=True, comment="Курс обмена для рубля")
    price_mode = Column(String(20), nullable=False, default="", comment="Режим цен (simple/advanced/пусто)")
    daily_limit = Column(Integer, nullable=True, comment="Индивидуальный дневной лимит")
    monthly_limit = Column(Integer, nullable=True, comment="Индивидуальный месячный лимит")
    
    # Связь
    user = relationship("User", back_populates="settings")


class AccessControl(Base):
    """Конфигурация контроля доступа (один ряд)"""
    __tablename__ = "access_control"
    
    id = Column(Integer, primary_key=True, default=1)
    whitelist_enabled = Column(Boolean, nullable=False, default=False, comment="Включен ли белый список")
    blacklist_enabled = Column(Boolean, nullable=False, default=False, comment="Включен ли черный список")
    
    # Связь с записями списков
    entries = relationship("AccessListEntry", back_populates="access_control", cascade="all, delete-orphan")


class AccessListEntry(Base):
    """Записи в белых/черных списках"""
    __tablename__ = "access_list_entries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    access_control_id = Column(Integer, ForeignKey("access_control.id", ondelete="CASCADE"), nullable=False)
    list_type = Column(SQLEnum(ListType), nullable=False, comment="Тип списка (whitelist/blacklist)")
    entry_type = Column(SQLEnum(EntryType), nullable=False, comment="Тип записи (id/username)")
    value = Column(String(255), nullable=False, comment="Значение (ID или username)")
    
    # Связь
    access_control = relationship("AccessControl", back_populates="entries")
    
    # Уникальный индекс: одна запись одного типа в одном списке
    __table_args__ = (
        UniqueConstraint("access_control_id", "list_type", "entry_type", "value", name="uq_access_entry"),
    )


class AdminSettings(Base):
    """Глобальные настройки администратора (один ряд)"""
    __tablename__ = "admin_settings"
    
    id = Column(Integer, primary_key=True, default=1)
    default_llm = Column(String(50), nullable=False, default="yandex", comment="Провайдер LLM по умолчанию")
    yandex_model = Column(String(100), nullable=False, default="yandexgpt-lite", comment="Модель YandexGPT")
    openai_model = Column(String(100), nullable=False, default="gpt-4o-mini", comment="Модель OpenAI")
    translate_provider = Column(String(50), nullable=False, default="yandex", comment="Провайдер для переводов")
    translate_model = Column(String(100), nullable=False, default="yandexgpt-lite", comment="Модель для переводов")
    translate_legacy = Column(Boolean, nullable=False, default=False, comment="Использовать старый Yandex Translate")
    convert_currency = Column(Boolean, nullable=False, default=False, comment="Конвертировать валюту")
    tmapi_notify_439 = Column(Boolean, nullable=False, default=False, comment="Уведомлять об ошибке 439 TMAPI")
    debug_mode = Column(Boolean, nullable=False, default=False, comment="Режим отладки")
    mock_mode = Column(Boolean, nullable=False, default=False, comment="Mock режим")
    forward_channel_id = Column(String(255), nullable=False, default="", comment="ID канала для дублирования постов")
    per_user_daily_limit = Column(Integer, nullable=True, comment="Глобальный дневной лимит на пользователя")
    per_user_monthly_limit = Column(Integer, nullable=True, comment="Глобальный месячный лимит на пользователя")
    total_daily_limit = Column(Integer, nullable=True, comment="Общий дневной лимит")
    total_monthly_limit = Column(Integer, nullable=True, comment="Общий месячный лимит")


class SzwegoAuth(Base):
    """Данные авторизации Szwego пользователя"""
    __tablename__ = "szwego_auth"

    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True, comment="Telegram user ID")
    login_enc = Column(Text, nullable=True, comment="Зашифрованный логин")
    password_enc = Column(Text, nullable=True, comment="Зашифрованный пароль")
    cookies_file = Column(Text, nullable=True, comment="Путь к cookies файлу пользователя (для обратной совместимости)")
    user_agent = Column(Text, nullable=True, comment="User-Agent, использованный при авторизации (plaintext, legacy)")
    # Новые поля: предпочтительно храним cookies и UA в БД в зашифрованном виде.
    cookies_encrypted = Column(Text, nullable=True, comment="Зашифрованные cookies SZWEGO (JSON)")
    user_agent_encrypted = Column(Text, nullable=True, comment="Зашифрованный User-Agent")
    last_status = Column(String(50), nullable=True, comment="Последний статус авторизации (success/invalid_credentials/...)")
    last_status_at = Column(DateTime, nullable=True, comment="Время последнего обновления статуса")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="Время создания")
    updated_at = Column(Integer, nullable=True, comment="Unix timestamp последнего обновления")

    # Связь
    user = relationship("User", back_populates="szwego_auth")


class RateLimitGlobal(Base):
    """Глобальные лимиты запросов (один ряд)"""
    __tablename__ = "rate_limits_global"
    
    id = Column(Integer, primary_key=True, default=1)
    day_start = Column(Date, nullable=False, comment="Начало текущего дня (МСК)")
    day_count = Column(Integer, nullable=False, default=0, comment="Количество запросов за день")
    month_start = Column(Date, nullable=False, comment="Начало текущего месяца (МСК)")
    month_count = Column(Integer, nullable=False, default=0, comment="Количество запросов за месяц")
    day_cost = Column(Float, nullable=False, default=0.0, comment="Стоимость запросов за день (USD)")
    month_cost = Column(Float, nullable=False, default=0.0, comment="Стоимость запросов за месяц (USD)")


class RateLimitUser(Base):
    """Пользовательские лимиты запросов"""
    __tablename__ = "rate_limits_users"
    
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True, comment="Telegram user ID")
    day_start = Column(Date, nullable=False, comment="Начало текущего дня (МСК)")
    day_count = Column(Integer, nullable=False, default=0, comment="Количество запросов за день")
    month_start = Column(Date, nullable=False, comment="Начало текущего месяца (МСК)")
    month_count = Column(Integer, nullable=False, default=0, comment="Количество запросов за месяц")
    day_cost = Column(Float, nullable=False, default=0.0, comment="Стоимость запросов за день (USD)")
    month_cost = Column(Float, nullable=False, default=0.0, comment="Стоимость запросов за месяц (USD)")
    
    # Связь
    user = relationship("User", back_populates="rate_limits")


class RequestStats(Base):
    """Статистика запросов пользователей"""
    __tablename__ = "request_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID записи")
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, comment="Telegram user ID")
    username = Column(String(255), nullable=True, comment="Telegram username (без @)")
    request_time = Column(DateTime, nullable=False, comment="Время запроса")
    product_url = Column(Text, nullable=True, comment="URL товара")
    platform = Column(String(50), nullable=True, comment="Платформа (taobao/tmall/pinduoduo/1688/szwego)")
    text_length = Column(Integer, nullable=True, comment="Длина текста сообщения в символах")
    images_count = Column(Integer, nullable=False, default=0, comment="Количество изображений")
    chunks_count = Column(Integer, nullable=True, comment="Количество частей текста")
    duration_ms = Column(Integer, nullable=True, comment="Время обработки в миллисекундах")
    request_id = Column(String(255), nullable=True, comment="Уникальный ID запроса (UUID)")
    
    # Лимиты пользователя
    user_daily_limit = Column(Integer, nullable=True, comment="Дневной лимит пользователя")
    user_daily_count = Column(Integer, nullable=True, comment="Использовано запросов за день")
    user_daily_remaining = Column(Integer, nullable=True, comment="Осталось запросов на день")
    user_monthly_limit = Column(Integer, nullable=True, comment="Месячный лимит пользователя")
    user_monthly_count = Column(Integer, nullable=True, comment="Использовано запросов за месяц")
    user_monthly_remaining = Column(Integer, nullable=True, comment="Осталось запросов на месяц")
    
    # Статистика токенов
    prompt_tokens = Column(Integer, nullable=True, comment="Количество входных токенов")
    completion_tokens = Column(Integer, nullable=True, comment="Количество выходных токенов")
    total_tokens = Column(Integer, nullable=True, comment="Общее количество токенов")
    prompt_cost = Column(Float, nullable=True, comment="Стоимость входных токенов (USD)")
    completion_cost = Column(Float, nullable=True, comment="Стоимость выходных токенов (USD)")
    total_cost = Column(Float, nullable=True, comment="Общая стоимость токенов (USD)")
    
    # Глобальная стоимость
    global_daily_cost = Column(Float, nullable=True, comment="Общая стоимость запросов за день (USD)")
    global_monthly_cost = Column(Float, nullable=True, comment="Общая стоимость запросов за месяц (USD)")
    
    # Статистика Redis кэша
    cache_hits = Column(Integer, nullable=True, default=0, comment="Количество попаданий в кэш (cache hits)")
    cache_misses = Column(Integer, nullable=True, default=0, comment="Количество промахов кэша (cache misses)")
    cache_saved_tokens = Column(Integer, nullable=True, comment="Сэкономлено токенов благодаря кэшу")
    cache_saved_cost = Column(Float, nullable=True, comment="Сэкономлено денег благодаря кэшу (USD)")
    cache_saved_time_ms = Column(Integer, nullable=True, comment="Сэкономлено времени благодаря кэшу (мс)")
    
    # Метаданные
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="Время создания записи")
    
    # Связь (опционально)
    # user = relationship("User", back_populates="request_stats")

# -*- coding: utf-8 -*-
"""
Конфигурация админ-панели.

Настройки загружаются из переменных окружения.
Использует Pydantic Settings для валидации.
"""

from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    """
    Настройки админ-панели.
    
    Переменные окружения с префиксом ADMIN_ или без.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    
    # === Основные настройки ===
    
    # Название приложения
    APP_NAME: str = "Taobao Bot Admin"
    APP_VERSION: str = "1.0.0"
    
    # Режим отладки
    DEBUG: bool = False
    
    # === Сервер ===
    
    # Хост и порт
    ADMIN_HOST: str = "0.0.0.0"
    ADMIN_PORT: int = 8082
    
    # CORS разрешённые домены (через запятую)
    ADMIN_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    
    # === База данных ===
    
    # ВАЖНО:
    # В основном проекте используются переменные POSTGRES_*.
    # Чтобы админка заводилась «из коробки», поддерживаем оба варианта:
    # - DATABASE_URL (если задан явно)
    # - либо сборка из POSTGRES_HOST/DB/USER/PASSWORD/PORT
    DATABASE_URL: str = ""
    
    POSTGRES_HOST: str = "localhost"
    POSTGRES_DB: str = "taobao_bot"
    POSTGRES_USER: str = "taobao_user"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_PORT: int = 5432
    
    # Настройки пула соединений
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    
    # === JWT аутентификация ===
    
    # Секретный ключ для подписи JWT токенов (ОБЯЗАТЕЛЬНО сменить в продакшене!)
    ADMIN_JWT_SECRET: str = "CHANGE_ME_IN_PRODUCTION_super_secret_key_32_chars"
    
    # Алгоритм подписи
    ADMIN_JWT_ALGORITHM: str = "HS256"
    
    # Время жизни access token в минутах
    ADMIN_JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    
    # Время жизни refresh token в днях
    ADMIN_JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # === Telegram ===
    
    # Токен бота для валидации Telegram Login Widget
    BOT_TOKEN: str = ""
    
    # ID администратора бота (для автоматического создания первого админа)
    ADMIN_CHAT_ID: str = ""
    
    # === Безопасность ===
    
    # Максимальное количество неудачных попыток входа
    ADMIN_MAX_LOGIN_ATTEMPTS: int = 5
    
    # Время блокировки после превышения попыток (минуты)
    ADMIN_LOGIN_LOCKOUT_MINUTES: int = 15
    
    # Максимальное количество активных сессий на пользователя
    ADMIN_MAX_SESSIONS_PER_USER: int = 5
    
    # === Логирование ===
    
    # Уровень логирования
    ADMIN_LOG_LEVEL: str = "INFO"
    
    # Файл логов
    ADMIN_LOG_FILE: str = "logs/admin.log"
    
    # Максимальный размер файла логов (МБ)
    ADMIN_LOG_MAX_SIZE_MB: int = 50
    
    # Количество резервных файлов логов
    ADMIN_LOG_BACKUP_COUNT: int = 3
    
    @property
    def cors_origins_list(self) -> list[str]:
        """Возвращает список разрешённых CORS origins."""
        return [origin.strip() for origin in self.ADMIN_CORS_ORIGINS.split(",") if origin.strip()]
    
    @property
    def admin_chat_id_int(self) -> Optional[int]:
        """Возвращает ADMIN_CHAT_ID как int или None."""
        try:
            return int(self.ADMIN_CHAT_ID) if self.ADMIN_CHAT_ID else None
        except ValueError:
            return None
    
    @property
    def database_url(self) -> str:
        """
        Возвращает итоговый URL подключения к PostgreSQL.
        
        Приоритет:
        1) DATABASE_URL (если задан)
        2) Сборка из POSTGRES_* (совместимо с текущим .env проекта)
        
        Примечание:
        - Пароль/логин кодируются через URL-encoding, чтобы спецсимволы
          (например, `@`, `&`, `:`) не ломали строку подключения.
        - Если пароль в .env записан в кавычках, мы их убираем.
        """
        if self.DATABASE_URL and self.DATABASE_URL.strip():
            return self.DATABASE_URL.strip()
        
        user = (self.POSTGRES_USER or "").strip().strip('"').strip("'")
        password_raw = (self.POSTGRES_PASSWORD or "").strip()
        password_raw = password_raw.strip('"').strip("'")
        
        user_enc = quote_plus(user)
        password_enc = quote_plus(password_raw)
        
        host = (self.POSTGRES_HOST or "localhost").strip()
        db = (self.POSTGRES_DB or "").strip()
        port = int(self.POSTGRES_PORT or 5432)
        
        return f"postgresql+asyncpg://{user_enc}:{password_enc}@{host}:{port}/{db}"


@lru_cache()
def get_admin_settings() -> AdminSettings:
    """
    Получает singleton экземпляр настроек.
    
    Кэшируется для производительности.
    """
    return AdminSettings()


# Глобальный экземпляр настроек
admin_settings = get_admin_settings()

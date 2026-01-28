# -*- coding: utf-8 -*-
"""
Модуль работы с базой данных для админ-панели.

Использует те же модели и настройки, что и основной бот.
Предоставляет асинхронные сессии для FastAPI.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from admin.backend.config import admin_settings

logger = logging.getLogger(__name__)

# Создаём асинхронный движок.
# Берём URL из настроек, приоритетно поддерживая POSTGRES_* переменные.
engine = create_async_engine(
    admin_settings.database_url,
    echo=admin_settings.DEBUG,
    pool_size=admin_settings.DB_POOL_SIZE,
    max_overflow=admin_settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Проверка соединения перед использованием
)

# Фабрика асинхронных сессий
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии БД в FastAPI.
    
    Использует контекстный менеджер для автоматического закрытия сессии.
    
    Yields:
        AsyncSession: Асинхронная сессия SQLAlchemy
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Ошибка в сессии БД: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Инициализация подключения к БД.
    
    Проверяет доступность базы данных при старте приложения.
    """
    try:
        async with engine.begin() as conn:
            # Простая проверка подключения
            await conn.execute(text("SELECT 1"))
        logger.info("Подключение к базе данных установлено")
    except Exception as e:
        logger.error(f"Не удалось подключиться к базе данных: {e}")
        raise


async def close_db() -> None:
    """
    Закрытие подключения к БД.
    
    Вызывается при остановке приложения.
    """
    await engine.dispose()
    logger.info("Подключение к базе данных закрыто")

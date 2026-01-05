"""
Управление сессиями и подключениями к базе данных PostgreSQL.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator

from src.core.config import settings
from src.db.models import Base


class DatabaseSession:
    """Класс для управления сессиями БД"""
    
    def __init__(self):
        self.engine = None
        self.async_session_maker = None
    
    def initialize(self):
        """Инициализация подключения к БД"""
        # Создаём движок с пулом соединений
        self.engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,  # Проверка соединений перед использованием
            echo=settings.DEBUG_MODE,  # Логировать SQL запросы в DEBUG режиме
        )
        
        # Создаём фабрику сессий
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    
    async def close(self):
        """Закрытие подключения к БД"""
        if self.engine:
            await self.engine.dispose()


# Глобальный экземпляр для управления сессиями
_db_session = DatabaseSession()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии БД.
    
    Yields:
        AsyncSession: Сессия базы данных
    """
    if not _db_session.async_session_maker:
        _db_session.initialize()
    
    async with _db_session.async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Инициализация БД: создание всех таблиц.
    Вызывается при старте приложения.
    """
    if not _db_session.engine:
        _db_session.initialize()
    
    async with _db_session.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """
    Закрытие подключений к БД.
    Вызывается при остановке приложения.
    """
    await _db_session.close()


def get_engine():
    """Получить движок БД (для миграций Alembic)"""
    if not _db_session.engine:
        _db_session.initialize()
    return _db_session.engine

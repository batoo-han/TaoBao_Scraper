"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import build_async_db_url, settings
from .models import Base  # noqa: F401  # ensure models are imported for metadata


DATABASE_URL = build_async_db_url()

_connect_args = {}
sslmode = (getattr(settings, "POSTGRES_SSLMODE", "") or "").strip().lower()
if sslmode == "disable":
    _connect_args["ssl"] = False
elif sslmode in {"require", "verify-ca", "verify-full"}:
    _connect_args["ssl"] = True
# Для значений prefer/allow или пустых ничего не передаем (используется настройка по умолчанию asyncpg)

async_engine = create_async_engine(
    DATABASE_URL,
    echo=settings.DEBUG_MODE,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

async_session_factory = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession with commit/rollback handling."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Для использования в FastAPI Depends
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    Dependency для FastAPI, возвращает сессию БД.
    
    FastAPI автоматически обрабатывает async generators через Depends.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()



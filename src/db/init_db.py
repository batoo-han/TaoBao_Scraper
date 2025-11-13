"""
Утилита для инициализации базы данных.
Создаёт все таблицы согласно моделям SQLAlchemy.
"""

import asyncio
import logging
from sqlalchemy import text

from src.db.base import Base
from src.db.session import async_engine

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """
    Создаёт все таблицы в базе данных согласно моделям.
    
    Внимание: Используйте Alembic для миграций в продакшене!
    Эта функция полезна только для первоначальной настройки или тестирования.
    """
    try:
        async with async_engine.begin() as conn:
            # Проверяем подключение
            await conn.execute(text("SELECT 1"))
            logger.info("✅ Подключение к БД успешно")
            
            # Создаём все таблицы
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Таблицы созданы успешно")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации БД: {e}")
        raise


async def check_db_connection() -> bool:
    """
    Проверяет подключение к базе данных.
    
    Returns:
        bool: True если подключение успешно, False иначе
    """
    try:
        async with async_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД: {e}")
        return False


if __name__ == "__main__":
    """
    Запуск инициализации БД из командной строки.
    
    Использование:
        python -m src.db.init_db
    """
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_db())


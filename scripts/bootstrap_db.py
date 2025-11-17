"""
Комплексный скрипт для первоначальной настройки базы данных.
Выполняет все необходимые шаги для подготовки БД к работе.

Использование:
    python scripts/bootstrap_db.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.init_db import check_db_connection, init_db
from src.db.session import get_async_session
from src.services.app_settings import AppSettingsService
from src.core.config import settings

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def bootstrap() -> None:
    """
    Выполняет полную инициализацию БД:
    1. Проверяет подключение
    2. Создаёт таблицы (если их нет)
    3. Инициализирует AppSettings
    """
    logger.info("🚀 Начало инициализации базы данных...")
    
    # Шаг 1: Проверка подключения
    logger.info("📡 Проверка подключения к БД...")
    if not await check_db_connection():
        logger.error("❌ Не удалось подключиться к БД. Проверьте настройки в .env")
        sys.exit(1)
    logger.info("✅ Подключение к БД успешно")
    
    # Шаг 2: Создание таблиц
    logger.info("📦 Создание таблиц...")
    try:
        await init_db()
        logger.info("✅ Таблицы созданы")
    except Exception as e:
        error_str = str(e)
        if "permission denied" in error_str.lower() or "insufficientprivilege" in error_str.lower():
            logger.error("❌ Ошибка прав доступа к БД!")
            logger.error("")
            logger.error("=" * 60)
            logger.error("РЕШЕНИЕ: Выдайте права пользователю PostgreSQL")
            logger.error("=" * 60)
            logger.error("")
            logger.error("Вариант 1: Выполните SQL скрипт (от имени суперпользователя):")
            logger.error(f"  psql -U postgres -d {settings.POSTGRES_DB} -f scripts/fix_db_permissions.sql")
            logger.error("")
            logger.error("Вариант 2: Или используйте PowerShell скрипт:")
            logger.error("  powershell -ExecutionPolicy Bypass -File scripts/fix_db_permissions.ps1")
            logger.error("")
            logger.error("Вариант 3: Выполните вручную через pgAdmin:")
            logger.error(f"  GRANT ALL ON SCHEMA public TO {settings.POSTGRES_USER};")
            logger.error(f"  GRANT CREATE ON SCHEMA public TO {settings.POSTGRES_USER};")
            logger.error(f"  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {settings.POSTGRES_USER};")
            logger.error("")
            sys.exit(1)
        else:
            logger.warning(f"⚠️  Ошибка при создании таблиц (возможно, они уже существуют): {e}")
            logger.info("ℹ️  Продолжаем...")
    
    # Шаг 3: Инициализация AppSettings
    logger.info("⚙️  Инициализация настроек приложения...")
    try:
        async with get_async_session() as session:
            app_service = AppSettingsService(session)
            app_settings = await app_service.get_app_settings()
            
            if not app_settings.active_llm_vendor:
                await app_service.set_provider(
                    vendor=settings.DEFAULT_LLM_VENDOR,
                    config={}
                )
                logger.info(f"✅ Установлен провайдер по умолчанию: {settings.DEFAULT_LLM_VENDOR}")
            else:
                logger.info(f"ℹ️  Активный провайдер: {app_settings.active_llm_vendor}")
            
            await session.commit()
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации настроек: {e}")
        sys.exit(1)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ Инициализация БД завершена успешно!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📝 Следующие шаги:")
    logger.info("   1. Убедитесь, что API ключи настроены в .env")
    logger.info("   2. При необходимости создайте миграции Alembic:")
    logger.info("      alembic revision --autogenerate -m 'Initial schema'")
    logger.info("   3. Запустите бота: python main.py")
    logger.info("")


if __name__ == "__main__":
    try:
        asyncio.run(bootstrap())
    except KeyboardInterrupt:
        logger.info("\n⚠️  Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


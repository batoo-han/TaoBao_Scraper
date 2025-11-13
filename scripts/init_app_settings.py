"""
Скрипт для первоначальной настройки AppSettings в базе данных.
Создаёт запись с дефолтными настройками приложения.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import settings
from src.db.session import get_async_session
from src.services.app_settings import AppSettingsService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_app_settings() -> None:
    """
    Инициализирует AppSettings с дефолтными значениями.
    Если запись уже существует, обновляет только активного провайдера (если не задан).
    """
    async with get_async_session() as session:
        app_service = AppSettingsService(session)
        
        # Получаем или создаём настройки
        app_settings = await app_service.get_app_settings()
        
        # Если провайдер не задан, устанавливаем дефолтный
        if not app_settings.active_llm_vendor:
            await app_service.set_provider(
                vendor=settings.DEFAULT_LLM_VENDOR,
                config={}
            )
            logger.info(f"✅ Установлен провайдер по умолчанию: {settings.DEFAULT_LLM_VENDOR}")
        else:
            logger.info(f"ℹ️  Активный провайдер уже установлен: {app_settings.active_llm_vendor}")
        
        # Если текст согласия пустой, можно установить дефолтный (опционально)
        if not app_settings.consent_text:
            # Здесь можно добавить дефолтный текст согласия
            logger.info("ℹ️  Текст согласия не задан (можно установить через админку)")
        
        await session.commit()
        logger.info("✅ Настройки приложения инициализированы")


if __name__ == "__main__":
    """
    Запуск инициализации настроек из командной строки.
    
    Использование:
        python scripts/init_app_settings.py
    """
    try:
        asyncio.run(init_app_settings())
        logger.info("✅ Инициализация завершена успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации: {e}")
        sys.exit(1)


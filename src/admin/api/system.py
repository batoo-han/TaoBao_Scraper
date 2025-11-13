"""
Системные операции админ-панели (перезагрузка сервисов и т.д.).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from src.admin.dependencies import require_permission
from src.core.restart_manager import restart_manager
from src.db.models import AdminUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


@router.post("/restart")
async def restart_services(
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
):
    """
    Инициирует перезапуск бота и админ-панели.

    Запускает скрипт перезапуска и ждет некоторое время, чтобы убедиться,
    что скрипт успешно запустился.
    """
    try:
        # Запускаем перезапуск
        await restart_manager.schedule_restart()
        
        # Ждем немного, чтобы скрипт успел запуститься
        await asyncio.sleep(2)
        
        logger.info("Перезапуск сервисов инициирован через API")
        
        return {
            "success": True,
            "message": "Перезапуск инициирован. Сервисы будут перезапущены в течение 10-15 секунд. Страница автоматически обновится."
        }
    except Exception as e:
        logger.error("Ошибка при инициировании перезапуска: %s", e, exc_info=True)
        return {
            "success": False,
            "message": f"Ошибка при инициировании перезапуска: {str(e)}"
        }


"""
Системные операции админ-панели (перезагрузка сервисов и т.д.).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.admin.dependencies import require_permission
from src.core.restart_manager import restart_manager
from src.db.models import AdminUser

router = APIRouter(prefix="/system", tags=["system"])


@router.post("/restart")
async def restart_services(
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
):
    """
    Инициирует перезапуск бота и админ-панели.

    Возвращает немедленный ответ, а фактический перезапуск запускается в фоне.
    """
    await restart_manager.schedule_restart()
    return {
        "message": "Перезапуск инициирован. Сервисы будут перезапущены в течение нескольких секунд."
    }


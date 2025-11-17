"""
API endpoint для перезагрузки настроек из БД.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_admin_user, require_permission
from src.core.config_manager import config_manager
from src.db.models import AdminUser
from src.db.session import get_db_session

router = APIRouter(prefix="/config", tags=["config"])


@router.post("/reload")
async def reload_config(
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
):
    """
    Перезагрузить настройки из БД и применить их налету.
    
    Требует права: can_manage_keys
    """
    try:
        await config_manager.load_from_db()
        return {
            "status": "success",
            "message": "Настройки перезагружены из БД и применены налету",
            "db_config_loaded": config_manager.db_config_loaded,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка перезагрузки настроек: {str(e)}",
        )


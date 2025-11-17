"""
API endpoints для управления настройками приложения.
"""

from __future__ import annotations

from typing import Annotated, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_admin_user, require_permission
from src.admin.models.schemas import (
    AppConfigUpdate,
    AppConfigUpdateResponse,
    AppSettingsResponse,
    ConsentTextUpdate,
    LLMPromptConfig,
    LLMProviderUpdate,
    PlatformConfigUpdate,
)
from src.core.config_manager import config_manager
from src.db.models import AdminUser
from src.db.session import get_db_session
from src.services.app_settings import AppSettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


def _build_settings_response(settings_obj) -> AppSettingsResponse:
    runtime_config = config_manager.get_runtime_cache()
    pending_config = settings_obj.pending_restart_config or {}
    effective_config: Dict[str, Any] = dict(runtime_config)
    effective_config.update(pending_config)

    stored_config = settings_obj.app_config or {}

    return AppSettingsResponse(
        active_llm_vendor=settings_obj.active_llm_vendor,
        llm_config=settings_obj.llm_config or {},
        consent_text=settings_obj.consent_text or "",
        app_config=effective_config,
        stored_app_config=stored_config,
        platforms_config=settings_obj.platforms_config or {},
        pending_restart_config=pending_config,
        restart_required=config_manager.is_restart_required(),
        updated_at=settings_obj.updated_at,
    )


@router.get("", response_model=AppSettingsResponse)
async def get_app_settings(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Получить текущие настройки приложения."""
    service = AppSettingsService(session)
    settings_obj = await service.get_app_settings()

    return _build_settings_response(settings_obj)


@router.put("/llm-provider", response_model=AppSettingsResponse)
async def update_llm_provider(
    update: LLMProviderUpdate,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Изменить активного LLM провайдера.

    Требует права: can_manage_keys
    """
    service = AppSettingsService(session)

    try:
        settings_obj = await service.set_provider(update.vendor, update.config or {})
        await config_manager.refresh_runtime_cache()

        return _build_settings_response(settings_obj)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/consent-text", response_model=AppSettingsResponse)
async def update_consent_text(
    update: ConsentTextUpdate,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Обновить текст согласия на обработку персональных данных (ФЗ-152).

    Требует права: can_manage_keys
    """
    service = AppSettingsService(session)

    settings_obj = await service.update_consent_text(update.text)

    return _build_settings_response(settings_obj)


@router.put("/app-config", response_model=AppConfigUpdateResponse)
async def update_app_config(
    update: AppConfigUpdate,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Обновить настройки приложения (BOT_TOKEN, API ключи и т.д.).

    Настройки сохраняются в БД и применяются налету через ConfigManager. Для ключей,
    требующих перезапуска, значение попадёт в pending_restart_config.
    """
    result = await config_manager.update_settings_batch(update.config)

    service = AppSettingsService(session)
    settings_obj = await service.get_app_settings()

    message_parts = []
    if result["applied"]:
        message_parts.append(
            "Применены сразу: " + ", ".join(result["applied"])
        )
    if result["pending_restart"]:
        message_parts.append(
            "Требуют перезапуска: " + ", ".join(result["pending_restart"])
        )
    message = ". ".join(message_parts) if message_parts else "Настройки обновлены"

    return AppConfigUpdateResponse(
        settings=_build_settings_response(settings_obj),
        applied_keys=result["applied"],
        pending_restart_keys=result["pending_restart"],
        message=message,
    )


@router.get("/llm-prompt", response_model=LLMPromptConfig)
async def get_llm_prompt_config(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Получить настройки промпта для LLM."""
    service = AppSettingsService(session)
    config = await service.get_llm_prompt_config()

    return LLMPromptConfig(**config)


@router.put("/llm-prompt", response_model=AppSettingsResponse)
async def update_llm_prompt_config(
    update: LLMPromptConfig,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Обновить настройки промпта для LLM (промпт, температура, макс. токенов).

    Требует права: can_manage_keys
    """
    service = AppSettingsService(session)

    settings_obj = await service.update_llm_prompt_config(
        prompt_template=update.prompt_template,
        temperature=update.temperature,
        max_tokens=update.max_tokens,
    )

    return _build_settings_response(settings_obj)


@router.get("/platforms", response_model=Dict[str, Any])
async def get_platforms_config(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Получить настройки платформ (магазинов)."""
    service = AppSettingsService(session)
    config = await service.get_platforms_config()
    return config


@router.put("/platforms", response_model=AppSettingsResponse)
async def update_platform_config(
    update: PlatformConfigUpdate,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Включить/выключить платформу (магазин).

    Требует права: can_manage_keys
    """
    service = AppSettingsService(session)

    try:
        settings_obj = await service.update_platform_config(update.platform, update.enabled)

        return _build_settings_response(settings_obj)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


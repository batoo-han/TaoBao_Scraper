"""
API endpoints для управления LLM провайдерами.
"""

from __future__ import annotations

from typing import Annotated, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_admin_user, require_permission
from src.admin.models.schemas import (
    AppConfigUpdateResponse,
    AppSettingsResponse,
    ProviderConfigUpdate,
    ProviderField,
    ProviderInfo,
)
from src.core.config_manager import config_manager
from src.db.models import AdminUser
from src.db.session import get_db_session
from src.services.app_settings import AppSettingsService

router = APIRouter(prefix="/providers", tags=["providers"])

PROVIDER_SETTINGS_MAP: Dict[str, Dict[str, str]] = {
    "yandex": {
        "api_key": "YANDEX_GPT_API_KEY",
        "folder_id": "YANDEX_FOLDER_ID",
        "model": "YANDEX_GPT_MODEL",
    },
    "openai": {
        "api_key": "OPENAI_API_KEY",
        "model": "OPENAI_MODEL",
    },
    "proxiapi": {
        "api_key": "PROXIAPI_API_KEY",
        "model": "PROXIAPI_MODEL",
    },
}

PROVIDER_FIELD_DEFS: Dict[str, List[ProviderField]] = {
    "yandex": [
        ProviderField(
            key="api_key",
            label="API ключ",
            type="password",
            required=True,
            help="API ключ YandexGPT из Yandex Cloud",
            secret=True,
        ),
        ProviderField(
            key="folder_id",
            label="Yandex Folder ID",
            type="text",
            required=True,
            help="Идентификатор каталога в Yandex Cloud",
        ),
        ProviderField(
            key="model",
            label="Модель",
            type="text",
            placeholder="yandexgpt-lite",
            help="Название модели YandexGPT",
        ),
    ],
    "openai": [
        ProviderField(
            key="api_key",
            label="API ключ",
            type="password",
            required=True,
            help="API ключ OpenAI",
            secret=True,
        ),
        ProviderField(
            key="model",
            label="Модель",
            type="text",
            placeholder="gpt-4o-mini",
            help="ID модели OpenAI",
        ),
    ],
    "proxiapi": [
        ProviderField(
            key="api_key",
            label="API ключ",
            type="password",
            required=True,
            help="API ключ ProxiAPI",
            secret=True,
        ),
        ProviderField(
            key="model",
            label="Модель",
            type="text",
            placeholder="gpt-4o-mini",
            help="Модель, предоставляемая ProxiAPI",
        ),
    ],
}


MASKED_SECRET = "••••••"


def _mask_secret(value: Any) -> str:
    if not value:
        return ""
    return MASKED_SECRET


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


@router.get("", response_model=List[ProviderInfo])
async def list_providers(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Получить список всех доступных LLM провайдеров."""
    service = AppSettingsService(session)
    app_settings = await service.get_app_settings()
    runtime = config_manager.get_runtime_cache()
    pending = app_settings.pending_restart_config or {}
    runtime_with_pending: Dict[str, Any] = dict(runtime)
    runtime_with_pending.update(pending)

    providers: List[ProviderInfo] = []
    for vendor, fields in PROVIDER_FIELD_DEFS.items():
        config_values: Dict[str, Any] = {}
        filled_fields: Dict[str, bool] = {}
        missing_required: List[str] = []
        for field in fields:
            env_key = PROVIDER_SETTINGS_MAP[vendor].get(field.key)
            if env_key:
                raw_value = runtime_with_pending.get(env_key)
                if field.secret:
                    config_values[field.key] = _mask_secret(raw_value)
                else:
                    config_values[field.key] = raw_value or ""
                has_value = bool(raw_value)
                filled_fields[field.key] = has_value
                if field.required and not has_value:
                    missing_required.append(field.key)
            else:
                filled_fields[field.key] = False

        if vendor == app_settings.active_llm_vendor:
            for key, value in (app_settings.llm_config or {}).items():
                if key not in config_values and value is not None:
                    config_values[key] = value

        providers.append(
            ProviderInfo(
                vendor=vendor,
                name={
                    "yandex": "YandexGPT",
                    "openai": "OpenAI",
                    "proxiapi": "ProxiAPI",
                }.get(vendor, vendor.title()),
                is_active=app_settings.active_llm_vendor == vendor,
                config=config_values,
                config_fields=fields,
                filled_fields=filled_fields,
                missing_required_fields=missing_required,
                config_ready=len(missing_required) == 0,
            )
        )

    return providers


@router.get("/{vendor}/config", response_model=dict)
async def get_provider_config(
    vendor: str,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Получить конфигурацию конкретного провайдера.
    
    Требует права: can_manage_keys
    """
    service = AppSettingsService(session)
    app_settings = await service.get_app_settings()
    
    if vendor not in ["yandex", "openai", "proxiapi"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестный провайдер: {vendor}",
        )
    
    # Возвращаем конфигурацию из app_settings или дефолтную
    config = {}
    if vendor == "yandex":
        config = {
            "api_key": "***" if settings.YANDEX_GPT_API_KEY else None,
            "folder_id": settings.YANDEX_FOLDER_ID,
            "model": settings.YANDEX_GPT_MODEL,
        }
    elif vendor == "openai":
        config = {
            "api_key": "***" if settings.OPENAI_API_KEY else None,
            "model": settings.OPENAI_MODEL,
        }
    elif vendor == "proxiapi":
        config = {
            "api_key": "***" if settings.PROXIAPI_API_KEY else None,
            "model": settings.PROXIAPI_MODEL,
        }
    
    # Добавляем конфигурацию из БД, если есть
    if app_settings.active_llm_vendor == vendor:
        config.update(app_settings.llm_config)
    
    return config


@router.put("/{vendor}", response_model=AppConfigUpdateResponse)
async def update_provider_config(
    vendor: str,
    payload: ProviderConfigUpdate,
    admin_user: Annotated[AdminUser, Depends(require_permission("can_manage_keys"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Обновить конфигурацию провайдера и при необходимости активировать его.
    """
    vendor = vendor.lower()
    if vendor not in PROVIDER_SETTINGS_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестный провайдер: {vendor}",
        )

    mapped_updates: Dict[str, Any] = {}
    for field_key, env_key in PROVIDER_SETTINGS_MAP[vendor].items():
        if field_key in payload.config:
            value = payload.config[field_key]
            if value is not None and value != "":
                mapped_updates[env_key] = value

    result = {"applied": [], "pending_restart": [], "runtime": {}, "pending_config": {}}
    if mapped_updates:
        result = await config_manager.update_settings_batch(mapped_updates)

    service = AppSettingsService(session)
    settings_obj = await service.get_app_settings()

    runtime_snapshot = config_manager.get_runtime_cache()
    pending_snapshot = settings_obj.pending_restart_config or {}
    runtime_with_pending: Dict[str, Any] = dict(runtime_snapshot)
    runtime_with_pending.update(pending_snapshot)

    if payload.activate:
        missing_for_activation: List[str] = []
        for field in PROVIDER_FIELD_DEFS[vendor]:
            if not field.required:
                continue
            env_key = PROVIDER_SETTINGS_MAP[vendor].get(field.key)
            if not env_key:
                continue
            candidate_value = payload.config.get(field.key)
            runtime_value = runtime_with_pending.get(env_key)
            has_value = bool(candidate_value) or bool(runtime_value)
            if not has_value:
                missing_for_activation.append(field.label or field.key)

        if missing_for_activation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для активации заполните поля: " + ", ".join(missing_for_activation),
            )

        settings_obj = await service.set_provider(vendor, payload.config or {})
        await config_manager.refresh_runtime_cache()
    else:
        # Обновляем объект настроек, чтобы захватить изменения app_config
        settings_obj = await service.get_app_settings()

    message_parts = []
    if result["applied"]:
        message_parts.append("Применены: " + ", ".join(result["applied"]))
    if result["pending_restart"]:
        message_parts.append("Требуют перезапуска: " + ", ".join(result["pending_restart"]))
    if payload.activate:
        message_parts.append(f"Активирован провайдер {vendor}")
    message = ". ".join(message_parts) if message_parts else "Настройки провайдера обновлены"

    return AppConfigUpdateResponse(
        settings=_build_settings_response(settings_obj),
        applied_keys=result["applied"],
        pending_restart_keys=result["pending_restart"],
        message=message,
    )


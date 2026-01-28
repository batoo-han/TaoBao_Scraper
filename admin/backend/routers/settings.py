# -*- coding: utf-8 -*-
"""
API роутер настроек бота.

Эндпоинты:
- GET /admin - Получить все настройки
- PUT /admin - Обновить все настройки
- GET /llm - Настройки LLM
- PUT /llm - Обновить настройки LLM
- GET /limits - Настройки лимитов
- PUT /limits - Обновить настройки лимитов
- GET /flags - Флаги функций
- PUT /flags - Обновить флаги
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from admin.backend.database import get_db_session
from admin.backend.auth.dependencies import require_admin, CurrentUser
from admin.backend.models.settings import (
    AdminSettingsResponse,
    AdminSettingsUpdate,
    LLMSettingsResponse,
    LLMSettingsUpdate,
    LimitsSettingsResponse,
    LimitsSettingsUpdate,
    FeatureFlagsResponse,
    FeatureFlagsUpdate,
)
from src.db.models import AdminSettings as BotAdminSettings, AdminActionLog

router = APIRouter()
logger = logging.getLogger("admin.routers.settings")


async def get_or_create_settings(db: AsyncSession) -> BotAdminSettings:
    """Получает или создаёт запись настроек."""
    result = await db.execute(
        select(BotAdminSettings).where(BotAdminSettings.id == 1)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = BotAdminSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    return settings


async def log_settings_change(
    db: AsyncSession,
    user_id: int,
    action: str,
    details: str,
    request: Request,
):
    """Логирует изменение настроек."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("User-Agent", "unknown")
    
    log_entry = AdminActionLog(
        user_id=user_id,
        action=action,
        target_type="settings",
        details=details,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(log_entry)


@router.get("/admin", response_model=AdminSettingsResponse)
async def get_admin_settings(
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение всех глобальных настроек бота.
    
    Требует права администратора.
    """
    settings = await get_or_create_settings(db)
    return AdminSettingsResponse.model_validate(settings)


@router.put("/admin", response_model=AdminSettingsResponse)
async def update_admin_settings(
    request: Request,
    data: AdminSettingsUpdate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление всех глобальных настроек бота.
    
    Требует права администратора.
    """
    settings = await get_or_create_settings(db)
    
    # Собираем изменения для лога
    changes = []
    
    # LLM настройки
    if data.default_llm is not None and data.default_llm != settings.default_llm:
        changes.append(f"default_llm: {settings.default_llm} -> {data.default_llm}")
        settings.default_llm = data.default_llm
    if data.yandex_model is not None and data.yandex_model != settings.yandex_model:
        changes.append(f"yandex_model: {settings.yandex_model} -> {data.yandex_model}")
        settings.yandex_model = data.yandex_model
    if data.openai_model is not None and data.openai_model != settings.openai_model:
        changes.append(f"openai_model: {settings.openai_model} -> {data.openai_model}")
        settings.openai_model = data.openai_model
    if data.translate_provider is not None and data.translate_provider != settings.translate_provider:
        changes.append(f"translate_provider: {settings.translate_provider} -> {data.translate_provider}")
        settings.translate_provider = data.translate_provider
    if data.translate_model is not None and data.translate_model != settings.translate_model:
        changes.append(f"translate_model: {settings.translate_model} -> {data.translate_model}")
        settings.translate_model = data.translate_model
    if data.translate_legacy is not None and data.translate_legacy != settings.translate_legacy:
        changes.append(f"translate_legacy: {settings.translate_legacy} -> {data.translate_legacy}")
        settings.translate_legacy = data.translate_legacy
    
    # Флаги
    if data.convert_currency is not None and data.convert_currency != settings.convert_currency:
        changes.append(f"convert_currency: {settings.convert_currency} -> {data.convert_currency}")
        settings.convert_currency = data.convert_currency
    if data.tmapi_notify_439 is not None and data.tmapi_notify_439 != settings.tmapi_notify_439:
        changes.append(f"tmapi_notify_439: {settings.tmapi_notify_439} -> {data.tmapi_notify_439}")
        settings.tmapi_notify_439 = data.tmapi_notify_439
    if data.debug_mode is not None and data.debug_mode != settings.debug_mode:
        changes.append(f"debug_mode: {settings.debug_mode} -> {data.debug_mode}")
        settings.debug_mode = data.debug_mode
    if data.mock_mode is not None and data.mock_mode != settings.mock_mode:
        changes.append(f"mock_mode: {settings.mock_mode} -> {data.mock_mode}")
        settings.mock_mode = data.mock_mode
    if data.forward_channel_id is not None and data.forward_channel_id != settings.forward_channel_id:
        changes.append(f"forward_channel_id: '{settings.forward_channel_id}' -> '{data.forward_channel_id}'")
        settings.forward_channel_id = data.forward_channel_id
    
    # Лимиты (0 означает None)
    if data.per_user_daily_limit is not None:
        new_val = data.per_user_daily_limit if data.per_user_daily_limit > 0 else None
        if new_val != settings.per_user_daily_limit:
            changes.append(f"per_user_daily_limit: {settings.per_user_daily_limit} -> {new_val}")
            settings.per_user_daily_limit = new_val
    if data.per_user_monthly_limit is not None:
        new_val = data.per_user_monthly_limit if data.per_user_monthly_limit > 0 else None
        if new_val != settings.per_user_monthly_limit:
            changes.append(f"per_user_monthly_limit: {settings.per_user_monthly_limit} -> {new_val}")
            settings.per_user_monthly_limit = new_val
    if data.total_daily_limit is not None:
        new_val = data.total_daily_limit if data.total_daily_limit > 0 else None
        if new_val != settings.total_daily_limit:
            changes.append(f"total_daily_limit: {settings.total_daily_limit} -> {new_val}")
            settings.total_daily_limit = new_val
    if data.total_monthly_limit is not None:
        new_val = data.total_monthly_limit if data.total_monthly_limit > 0 else None
        if new_val != settings.total_monthly_limit:
            changes.append(f"total_monthly_limit: {settings.total_monthly_limit} -> {new_val}")
            settings.total_monthly_limit = new_val
    
    if changes:
        await log_settings_change(
            db, current_user.id, "update_settings",
            "; ".join(changes), request
        )
        logger.info(f"Настройки обновлены админом {current_user.username}: {'; '.join(changes)}")
    
    await db.commit()
    await db.refresh(settings)
    
    return AdminSettingsResponse.model_validate(settings)


@router.get("/llm", response_model=LLMSettingsResponse)
async def get_llm_settings(
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение настроек LLM провайдеров.
    """
    settings = await get_or_create_settings(db)
    return LLMSettingsResponse(
        default_llm=settings.default_llm,
        yandex_model=settings.yandex_model,
        openai_model=settings.openai_model,
        translate_provider=settings.translate_provider,
        translate_model=settings.translate_model,
        translate_legacy=settings.translate_legacy,
    )


@router.put("/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(
    request: Request,
    data: LLMSettingsUpdate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление настроек LLM провайдеров.
    """
    settings = await get_or_create_settings(db)
    changes = []
    
    if data.default_llm is not None:
        changes.append(f"default_llm: {settings.default_llm} -> {data.default_llm}")
        settings.default_llm = data.default_llm
    if data.yandex_model is not None:
        changes.append(f"yandex_model: {settings.yandex_model} -> {data.yandex_model}")
        settings.yandex_model = data.yandex_model
    if data.openai_model is not None:
        changes.append(f"openai_model: {settings.openai_model} -> {data.openai_model}")
        settings.openai_model = data.openai_model
    if data.translate_provider is not None:
        changes.append(f"translate_provider: {settings.translate_provider} -> {data.translate_provider}")
        settings.translate_provider = data.translate_provider
    if data.translate_model is not None:
        changes.append(f"translate_model: {settings.translate_model} -> {data.translate_model}")
        settings.translate_model = data.translate_model
    if data.translate_legacy is not None:
        changes.append(f"translate_legacy: {settings.translate_legacy} -> {data.translate_legacy}")
        settings.translate_legacy = data.translate_legacy
    
    if changes:
        await log_settings_change(db, current_user.id, "update_llm_settings", "; ".join(changes), request)
        logger.info(f"LLM настройки обновлены админом {current_user.username}")
    
    await db.commit()
    await db.refresh(settings)
    
    return LLMSettingsResponse(
        default_llm=settings.default_llm,
        yandex_model=settings.yandex_model,
        openai_model=settings.openai_model,
        translate_provider=settings.translate_provider,
        translate_model=settings.translate_model,
        translate_legacy=settings.translate_legacy,
    )


@router.get("/limits", response_model=LimitsSettingsResponse)
async def get_limits_settings(
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение настроек глобальных лимитов.
    """
    settings = await get_or_create_settings(db)
    return LimitsSettingsResponse(
        per_user_daily_limit=settings.per_user_daily_limit,
        per_user_monthly_limit=settings.per_user_monthly_limit,
        total_daily_limit=settings.total_daily_limit,
        total_monthly_limit=settings.total_monthly_limit,
    )


@router.put("/limits", response_model=LimitsSettingsResponse)
async def update_limits_settings(
    request: Request,
    data: LimitsSettingsUpdate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление настроек глобальных лимитов.
    """
    settings = await get_or_create_settings(db)
    changes = []
    
    if data.per_user_daily_limit is not None:
        new_val = data.per_user_daily_limit if data.per_user_daily_limit > 0 else None
        changes.append(f"per_user_daily_limit: {settings.per_user_daily_limit} -> {new_val}")
        settings.per_user_daily_limit = new_val
    if data.per_user_monthly_limit is not None:
        new_val = data.per_user_monthly_limit if data.per_user_monthly_limit > 0 else None
        changes.append(f"per_user_monthly_limit: {settings.per_user_monthly_limit} -> {new_val}")
        settings.per_user_monthly_limit = new_val
    if data.total_daily_limit is not None:
        new_val = data.total_daily_limit if data.total_daily_limit > 0 else None
        changes.append(f"total_daily_limit: {settings.total_daily_limit} -> {new_val}")
        settings.total_daily_limit = new_val
    if data.total_monthly_limit is not None:
        new_val = data.total_monthly_limit if data.total_monthly_limit > 0 else None
        changes.append(f"total_monthly_limit: {settings.total_monthly_limit} -> {new_val}")
        settings.total_monthly_limit = new_val
    
    if changes:
        await log_settings_change(db, current_user.id, "update_limits_settings", "; ".join(changes), request)
        logger.info(f"Лимиты обновлены админом {current_user.username}")
    
    await db.commit()
    await db.refresh(settings)
    
    return LimitsSettingsResponse(
        per_user_daily_limit=settings.per_user_daily_limit,
        per_user_monthly_limit=settings.per_user_monthly_limit,
        total_daily_limit=settings.total_daily_limit,
        total_monthly_limit=settings.total_monthly_limit,
    )


@router.get("/flags", response_model=FeatureFlagsResponse)
async def get_feature_flags(
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение флагов функций бота.
    """
    settings = await get_or_create_settings(db)
    return FeatureFlagsResponse(
        convert_currency=settings.convert_currency,
        tmapi_notify_439=settings.tmapi_notify_439,
        debug_mode=settings.debug_mode,
        mock_mode=settings.mock_mode,
        forward_channel_id=settings.forward_channel_id,
    )


@router.put("/flags", response_model=FeatureFlagsResponse)
async def update_feature_flags(
    request: Request,
    data: FeatureFlagsUpdate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление флагов функций бота.
    """
    settings = await get_or_create_settings(db)
    changes = []
    
    if data.convert_currency is not None:
        changes.append(f"convert_currency: {settings.convert_currency} -> {data.convert_currency}")
        settings.convert_currency = data.convert_currency
    if data.tmapi_notify_439 is not None:
        changes.append(f"tmapi_notify_439: {settings.tmapi_notify_439} -> {data.tmapi_notify_439}")
        settings.tmapi_notify_439 = data.tmapi_notify_439
    if data.debug_mode is not None:
        changes.append(f"debug_mode: {settings.debug_mode} -> {data.debug_mode}")
        settings.debug_mode = data.debug_mode
    if data.mock_mode is not None:
        changes.append(f"mock_mode: {settings.mock_mode} -> {data.mock_mode}")
        settings.mock_mode = data.mock_mode
    if data.forward_channel_id is not None:
        changes.append(f"forward_channel_id: '{settings.forward_channel_id}' -> '{data.forward_channel_id}'")
        settings.forward_channel_id = data.forward_channel_id
    
    if changes:
        await log_settings_change(db, current_user.id, "update_feature_flags", "; ".join(changes), request)
        logger.info(f"Флаги обновлены админом {current_user.username}")
    
    await db.commit()
    await db.refresh(settings)
    
    return FeatureFlagsResponse(
        convert_currency=settings.convert_currency,
        tmapi_notify_439=settings.tmapi_notify_439,
        debug_mode=settings.debug_mode,
        mock_mode=settings.mock_mode,
        forward_channel_id=settings.forward_channel_id,
    )

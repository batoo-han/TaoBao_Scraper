# -*- coding: utf-8 -*-
"""
API роутер контроля доступа.

Эндпоинты:
- GET / - Получить текущие списки доступа
- PUT / - Обновить списки доступа
- POST /whitelist - Добавить в белый список
- DELETE /whitelist - Удалить из белого списка
- POST /blacklist - Добавить в чёрный список
- DELETE /blacklist - Удалить из чёрного списка
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from admin.backend.database import get_db_session
from admin.backend.auth.dependencies import require_admin, CurrentUser
from admin.backend.models.user import AccessListUpdate, AccessListEntry, AccessListsResponse
from src.db.models import AccessControl, AccessListEntry as DBAccessListEntry, ListType, EntryType, AdminActionLog

router = APIRouter()
logger = logging.getLogger("admin.routers.access")


async def get_or_create_access_control(db: AsyncSession) -> AccessControl:
    """Получает или создаёт запись контроля доступа."""
    result = await db.execute(select(AccessControl).where(AccessControl.id == 1))
    access_control = result.scalar_one_or_none()
    
    if not access_control:
        access_control = AccessControl(id=1)
        db.add(access_control)
        await db.commit()
        await db.refresh(access_control)
    
    return access_control


async def log_access_action(
    db: AsyncSession,
    user_id: int,
    action: str,
    details: str,
    request: Request,
):
    """Логирует действие с контролем доступа."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("User-Agent", "unknown")
    
    log_entry = AdminActionLog(
        user_id=user_id,
        action=action,
        target_type="access_control",
        details=details,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(log_entry)


@router.get("/", response_model=AccessListsResponse)
async def get_access_lists(
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение текущего состояния списков доступа.
    
    Требует права администратора.
    """
    access_control = await get_or_create_access_control(db)
    
    # Загружаем записи
    result = await db.execute(
        select(DBAccessListEntry).where(DBAccessListEntry.access_control_id == 1)
    )
    entries = result.scalars().all()
    
    whitelist = []
    blacklist = []
    
    for entry in entries:
        item = AccessListEntry(
            entry_type=entry.entry_type.value,
            value=entry.value,
        )
        if entry.list_type == ListType.WHITELIST:
            whitelist.append(item)
        else:
            blacklist.append(item)
    
    return AccessListsResponse(
        whitelist_enabled=access_control.whitelist_enabled,
        blacklist_enabled=access_control.blacklist_enabled,
        whitelist=whitelist,
        blacklist=blacklist,
    )


@router.put("/", response_model=AccessListsResponse)
async def update_access_lists(
    request: Request,
    data: AccessListUpdate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление списков доступа.
    
    Позволяет включать/выключать списки и добавлять/удалять записи.
    Требует права администратора.
    """
    access_control = await get_or_create_access_control(db)
    changes = []
    
    # Обновляем флаги
    if data.whitelist_enabled is not None and data.whitelist_enabled != access_control.whitelist_enabled:
        changes.append(f"whitelist_enabled: {access_control.whitelist_enabled} -> {data.whitelist_enabled}")
        access_control.whitelist_enabled = data.whitelist_enabled
    
    if data.blacklist_enabled is not None and data.blacklist_enabled != access_control.blacklist_enabled:
        changes.append(f"blacklist_enabled: {access_control.blacklist_enabled} -> {data.blacklist_enabled}")
        access_control.blacklist_enabled = data.blacklist_enabled
    
    # Добавляем в белый список
    if data.add_whitelist_ids:
        for user_id in data.add_whitelist_ids:
            # Проверяем, нет ли уже такой записи
            existing = await db.execute(
                select(DBAccessListEntry).where(
                    DBAccessListEntry.access_control_id == 1,
                    DBAccessListEntry.list_type == ListType.WHITELIST,
                    DBAccessListEntry.entry_type == EntryType.ID,
                    DBAccessListEntry.value == str(user_id),
                )
            )
            if not existing.scalar_one_or_none():
                entry = DBAccessListEntry(
                    access_control_id=1,
                    list_type=ListType.WHITELIST,
                    entry_type=EntryType.ID,
                    value=str(user_id),
                )
                db.add(entry)
                changes.append(f"whitelist +id:{user_id}")
    
    if data.add_whitelist_usernames:
        for username in data.add_whitelist_usernames:
            username = username.lstrip("@")
            existing = await db.execute(
                select(DBAccessListEntry).where(
                    DBAccessListEntry.access_control_id == 1,
                    DBAccessListEntry.list_type == ListType.WHITELIST,
                    DBAccessListEntry.entry_type == EntryType.USERNAME,
                    DBAccessListEntry.value == username,
                )
            )
            if not existing.scalar_one_or_none():
                entry = DBAccessListEntry(
                    access_control_id=1,
                    list_type=ListType.WHITELIST,
                    entry_type=EntryType.USERNAME,
                    value=username,
                )
                db.add(entry)
                changes.append(f"whitelist +username:{username}")
    
    # Удаляем из белого списка
    if data.remove_whitelist_ids:
        for user_id in data.remove_whitelist_ids:
            await db.execute(
                delete(DBAccessListEntry).where(
                    DBAccessListEntry.access_control_id == 1,
                    DBAccessListEntry.list_type == ListType.WHITELIST,
                    DBAccessListEntry.entry_type == EntryType.ID,
                    DBAccessListEntry.value == str(user_id),
                )
            )
            changes.append(f"whitelist -id:{user_id}")
    
    if data.remove_whitelist_usernames:
        for username in data.remove_whitelist_usernames:
            username = username.lstrip("@")
            await db.execute(
                delete(DBAccessListEntry).where(
                    DBAccessListEntry.access_control_id == 1,
                    DBAccessListEntry.list_type == ListType.WHITELIST,
                    DBAccessListEntry.entry_type == EntryType.USERNAME,
                    DBAccessListEntry.value == username,
                )
            )
            changes.append(f"whitelist -username:{username}")
    
    # Добавляем в чёрный список
    if data.add_blacklist_ids:
        for user_id in data.add_blacklist_ids:
            existing = await db.execute(
                select(DBAccessListEntry).where(
                    DBAccessListEntry.access_control_id == 1,
                    DBAccessListEntry.list_type == ListType.BLACKLIST,
                    DBAccessListEntry.entry_type == EntryType.ID,
                    DBAccessListEntry.value == str(user_id),
                )
            )
            if not existing.scalar_one_or_none():
                entry = DBAccessListEntry(
                    access_control_id=1,
                    list_type=ListType.BLACKLIST,
                    entry_type=EntryType.ID,
                    value=str(user_id),
                )
                db.add(entry)
                changes.append(f"blacklist +id:{user_id}")
    
    if data.add_blacklist_usernames:
        for username in data.add_blacklist_usernames:
            username = username.lstrip("@")
            existing = await db.execute(
                select(DBAccessListEntry).where(
                    DBAccessListEntry.access_control_id == 1,
                    DBAccessListEntry.list_type == ListType.BLACKLIST,
                    DBAccessListEntry.entry_type == EntryType.USERNAME,
                    DBAccessListEntry.value == username,
                )
            )
            if not existing.scalar_one_or_none():
                entry = DBAccessListEntry(
                    access_control_id=1,
                    list_type=ListType.BLACKLIST,
                    entry_type=EntryType.USERNAME,
                    value=username,
                )
                db.add(entry)
                changes.append(f"blacklist +username:{username}")
    
    # Удаляем из чёрного списка
    if data.remove_blacklist_ids:
        for user_id in data.remove_blacklist_ids:
            await db.execute(
                delete(DBAccessListEntry).where(
                    DBAccessListEntry.access_control_id == 1,
                    DBAccessListEntry.list_type == ListType.BLACKLIST,
                    DBAccessListEntry.entry_type == EntryType.ID,
                    DBAccessListEntry.value == str(user_id),
                )
            )
            changes.append(f"blacklist -id:{user_id}")
    
    if data.remove_blacklist_usernames:
        for username in data.remove_blacklist_usernames:
            username = username.lstrip("@")
            await db.execute(
                delete(DBAccessListEntry).where(
                    DBAccessListEntry.access_control_id == 1,
                    DBAccessListEntry.list_type == ListType.BLACKLIST,
                    DBAccessListEntry.entry_type == EntryType.USERNAME,
                    DBAccessListEntry.value == username,
                )
            )
            changes.append(f"blacklist -username:{username}")
    
    if changes:
        await log_access_action(db, current_user.id, "update_access_lists", "; ".join(changes), request)
        logger.info(f"Списки доступа обновлены админом {current_user.username}: {'; '.join(changes)}")
    
    await db.commit()
    
    # Возвращаем обновлённое состояние
    return await get_access_lists(current_user, db)

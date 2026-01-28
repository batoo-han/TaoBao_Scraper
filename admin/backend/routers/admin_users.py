# -*- coding: utf-8 -*-
"""
API роутер управления пользователями админки.

Эндпоинты:
- GET / - Список пользователей админки
- POST / - Создать пользователя
- GET /{id} - Получить пользователя
- PUT /{id} - Обновить пользователя
- DELETE /{id} - Удалить пользователя
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from admin.backend.database import get_db_session
from admin.backend.auth.dependencies import require_admin, CurrentUser
from admin.backend.auth.jwt import hash_password
from admin.backend.models.auth import (
    AdminUserResponse,
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserListResponse,
)
from src.db.models import AdminUser, AdminActionLog

router = APIRouter()
logger = logging.getLogger("admin.routers.admin_users")


async def log_admin_action(
    db: AsyncSession,
    user_id: int,
    action: str,
    target_id: str,
    details: str,
    request: Request,
):
    """Логирует действие с пользователем админки."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("User-Agent", "unknown")
    
    log_entry = AdminActionLog(
        user_id=user_id,
        action=action,
        target_type="admin_user",
        target_id=target_id,
        details=details,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(log_entry)


@router.get("/", response_model=AdminUserListResponse)
async def list_admin_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Поиск по username или email"),
    role: Optional[str] = Query(None, description="Фильтр по роли (admin/user)"),
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение списка пользователей админки.
    
    Требует права администратора.
    """
    # Базовый запрос
    query = select(AdminUser)
    count_query = select(func.count(AdminUser.id))
    
    # Фильтры
    if search:
        search_filter = AdminUser.username.ilike(f"%{search}%") | AdminUser.email.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    
    if role:
        query = query.where(AdminUser.role == role)
        count_query = count_query.where(AdminUser.role == role)
    
    # Общее количество
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Пагинация
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).order_by(AdminUser.created_at.desc())
    
    # Выполняем запрос
    result = await db.execute(query)
    users = result.scalars().all()
    
    items = [AdminUserResponse.model_validate(u) for u in users]
    pages = (total + per_page - 1) // per_page if total > 0 else 1
    
    return AdminUserListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.post("/", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    request: Request,
    data: AdminUserCreate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Создание нового пользователя админки.
    
    Требует права администратора.
    """
    # Проверяем уникальность username
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким логином уже существует",
        )
    
    # Проверяем уникальность telegram_id
    if data.telegram_id:
        result = await db.execute(
            select(AdminUser).where(AdminUser.telegram_id == data.telegram_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким Telegram ID уже существует",
            )
    
    # Проверяем, что есть хотя бы один способ входа
    if not data.password and not data.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо указать пароль или Telegram ID",
        )
    
    # Создаём пользователя
    user = AdminUser(
        username=data.username,
        password_hash=hash_password(data.password) if data.password else None,
        email=data.email,
        display_name=data.display_name,
        telegram_id=data.telegram_id,
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Логируем создание
    await log_admin_action(
        db, current_user.id, "create_admin_user",
        str(user.id), f"Создан пользователь {user.username} с ролью {user.role}",
        request
    )
    await db.commit()
    
    logger.info(f"Создан пользователь админки {user.username} админом {current_user.username}")
    
    return AdminUserResponse.model_validate(user)


@router.get("/{user_id}", response_model=AdminUserResponse)
async def get_admin_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получение информации о пользователе админки.
    
    Требует права администратора.
    """
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    return AdminUserResponse.model_validate(user)


@router.put("/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(
    user_id: int,
    request: Request,
    data: AdminUserUpdate,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление пользователя админки.
    
    Требует права администратора.
    """
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Нельзя изменять самого себя (роль и активность)
    if user_id == current_user.id:
        if data.role is not None and data.role != current_user.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя изменить собственную роль",
            )
        if data.is_active is not None and not data.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя деактивировать собственный аккаунт",
            )
    
    # Собираем изменения
    changes = []
    
    if data.email is not None and data.email != user.email:
        changes.append(f"email: {user.email} -> {data.email}")
        user.email = data.email
    
    if data.display_name is not None and data.display_name != user.display_name:
        changes.append(f"display_name: {user.display_name} -> {data.display_name}")
        user.display_name = data.display_name
    
    if data.telegram_id is not None:
        # Проверяем уникальность
        if data.telegram_id != user.telegram_id:
            existing = await db.execute(
                select(AdminUser).where(
                    AdminUser.telegram_id == data.telegram_id,
                    AdminUser.id != user_id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Этот Telegram ID уже привязан к другому пользователю",
                )
            changes.append(f"telegram_id: {user.telegram_id} -> {data.telegram_id}")
            user.telegram_id = data.telegram_id
    
    if data.role is not None and data.role != user.role:
        changes.append(f"role: {user.role} -> {data.role}")
        user.role = data.role
    
    if data.is_active is not None and data.is_active != user.is_active:
        changes.append(f"is_active: {user.is_active} -> {data.is_active}")
        user.is_active = data.is_active
    
    if data.password:
        changes.append("password: changed")
        user.password_hash = hash_password(data.password)
    
    if changes:
        await log_admin_action(
            db, current_user.id, "update_admin_user",
            str(user_id), "; ".join(changes), request
        )
        logger.info(f"Обновлён пользователь админки {user.username} админом {current_user.username}: {'; '.join(changes)}")
    
    await db.commit()
    await db.refresh(user)
    
    return AdminUserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_user(
    user_id: int,
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Удаление пользователя админки.
    
    Требует права администратора.
    Нельзя удалить самого себя.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить собственный аккаунт",
        )
    
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    username = user.username
    
    # Логируем удаление
    await log_admin_action(
        db, current_user.id, "delete_admin_user",
        str(user_id), f"Удалён пользователь {username}", request
    )
    
    await db.delete(user)
    await db.commit()
    
    logger.info(f"Удалён пользователь админки {username} админом {current_user.username}")

# -*- coding: utf-8 -*-
"""
API роутер аутентификации.

Эндпоинты:
- POST /login - Вход по логину/паролю
- POST /telegram - Вход через Telegram Login Widget
- POST /refresh - Обновление токенов
- POST /logout - Выход
- POST /change-password - Смена пароля
- GET /me - Текущий пользователь
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from admin.backend.database import get_db_session
from admin.backend.config import admin_settings
from admin.backend.auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_password,
    hash_password,
    hash_token,
)
from admin.backend.auth.telegram import verify_telegram_auth, TelegramAuthData
from admin.backend.auth.dependencies import get_current_active_user, CurrentUser
from admin.backend.models.auth import (
    LoginRequest,
    LoginResponse,
    TelegramLoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    ChangePasswordRequest,
    AdminUserResponse,
)
from src.db.models import AdminUser, AdminSession, AdminActionLog

router = APIRouter()
logger = logging.getLogger("admin.routers.auth")


def get_client_info(request: Request) -> tuple[str, str]:
    """Извлекает IP и User-Agent из запроса."""
    # Получаем реальный IP (учитываем прокси)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    
    user_agent = request.headers.get("User-Agent", "unknown")
    return ip, user_agent


async def log_action(
    db: AsyncSession,
    user_id: int,
    action: str,
    ip: str,
    user_agent: str,
    target_type: str = None,
    target_id: str = None,
    details: str = None,
):
    """Записывает действие в журнал аудита."""
    log_entry = AdminActionLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(log_entry)
    await db.commit()


async def create_session_and_tokens(
    db: AsyncSession,
    user: AdminUser,
    ip: str,
    user_agent: str,
) -> tuple[str, str, int]:
    """
    Создаёт сессию и токены для пользователя.
    
    Returns:
        Кортеж (access_token, refresh_token, expires_in)
    """
    # Ограничиваем количество активных сессий
    result = await db.execute(
        select(AdminSession)
        .where(AdminSession.user_id == user.id)
        .where(AdminSession.expires_at > datetime.utcnow())
        .order_by(AdminSession.created_at.asc())
    )
    active_sessions = result.scalars().all()
    
    # Удаляем старые сессии если превышен лимит
    if len(active_sessions) >= admin_settings.ADMIN_MAX_SESSIONS_PER_USER:
        sessions_to_delete = active_sessions[:len(active_sessions) - admin_settings.ADMIN_MAX_SESSIONS_PER_USER + 1]
        for session in sessions_to_delete:
            await db.delete(session)
    
    # Создаём access token (role теперь всегда строка)
    access_token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    })
    
    # Создаём refresh token
    refresh_token, token_hash, expires_at = create_refresh_token(user.id)
    
    # Сохраняем сессию
    session = AdminSession(
        user_id=user.id,
        token_hash=token_hash,
        ip_address=ip,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    db.add(session)
    
    # Обновляем last_login
    user.last_login = datetime.utcnow()
    
    await db.commit()
    
    expires_in = admin_settings.ADMIN_JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    return access_token, refresh_token, expires_in


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Вход по логину и паролю.
    
    Возвращает JWT access token и refresh token.
    """
    ip, user_agent = get_client_info(request)
    
    # Ищем пользователя
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == data.username)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        logger.warning(f"Попытка входа с несуществующим логином: {data.username}, IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    
    # Проверяем активность
    if not user.is_active:
        logger.warning(f"Попытка входа в деактивированный аккаунт: {data.username}, IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован",
        )
    
    # Проверяем пароль
    if not user.password_hash or not verify_password(data.password, user.password_hash):
        logger.warning(f"Неверный пароль для пользователя: {data.username}, IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    
    # Создаём сессию и токены
    access_token, refresh_token, expires_in = await create_session_and_tokens(
        db, user, ip, user_agent
    )
    
    # Логируем вход
    await log_action(db, user.id, "login", ip, user_agent)
    logger.info(f"Успешный вход: {user.username}, IP: {ip}")
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=AdminUserResponse.model_validate(user),
    )


@router.post("/telegram", response_model=LoginResponse)
async def telegram_login(
    request: Request,
    data: TelegramLoginRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Вход через Telegram Login Widget.
    
    Проверяет подпись данных от Telegram и авторизует пользователя.
    """
    ip, user_agent = get_client_info(request)
    
    # Проверяем данные от Telegram
    auth_data = verify_telegram_auth(data.model_dump())
    if auth_data is None:
        logger.warning(f"Невалидные данные Telegram Login Widget, IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидные данные авторизации Telegram",
        )
    
    # Ищем пользователя по telegram_id
    result = await db.execute(
        select(AdminUser).where(AdminUser.telegram_id == auth_data.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        logger.warning(f"Telegram ID {auth_data.id} не привязан к аккаунту, IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram аккаунт не привязан к пользователю админки",
        )
    
    # Проверяем активность
    if not user.is_active:
        logger.warning(f"Попытка входа в деактивированный аккаунт через Telegram: {user.username}, IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован",
        )
    
    # Обновляем display_name из Telegram если не задано
    if not user.display_name and auth_data.full_name:
        user.display_name = auth_data.full_name
    
    # Создаём сессию и токены
    access_token, refresh_token, expires_in = await create_session_and_tokens(
        db, user, ip, user_agent
    )
    
    # Логируем вход
    await log_action(db, user.id, "login_telegram", ip, user_agent)
    logger.info(f"Успешный вход через Telegram: {user.username}, IP: {ip}")
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=AdminUserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_tokens(
    request: Request,
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Обновление токенов по refresh token.
    
    Инвалидирует старый refresh token и выдаёт новую пару токенов.
    """
    ip, user_agent = get_client_info(request)
    
    # Ищем сессию по хэшу токена
    token_hash = hash_token(data.refresh_token)
    result = await db.execute(
        select(AdminSession)
        .where(AdminSession.token_hash == token_hash)
        .where(AdminSession.expires_at > datetime.utcnow())
    )
    session = result.scalar_one_or_none()
    
    if not session:
        logger.warning(f"Невалидный или истёкший refresh token, IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или истёкший refresh token",
        )
    
    # Загружаем пользователя
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == session.user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        await db.delete(session)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или деактивирован",
        )
    
    # Удаляем старую сессию
    await db.delete(session)
    
    # Создаём новые токены (role теперь всегда строка)
    access_token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    })
    
    new_refresh_token, new_token_hash, expires_at = create_refresh_token(user.id)
    
    # Создаём новую сессию
    new_session = AdminSession(
        user_id=user.id,
        token_hash=new_token_hash,
        ip_address=ip,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    db.add(new_session)
    await db.commit()
    
    expires_in = admin_settings.ADMIN_JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    
    return RefreshTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Выход из системы.
    
    Инвалидирует текущую сессию (refresh token).
    """
    ip, user_agent = get_client_info(request)
    
    # Удаляем все сессии пользователя с этого IP/UA
    # (в реальности лучше передавать refresh_token в теле запроса)
    await db.execute(
        delete(AdminSession)
        .where(AdminSession.user_id == current_user.id)
        .where(AdminSession.ip_address == ip)
    )
    await db.commit()
    
    # Логируем выход
    await log_action(db, current_user.id, "logout", ip, user_agent)
    logger.info(f"Выход пользователя: {current_user.username}, IP: {ip}")
    
    return {"status": "ok", "message": "Выход выполнен успешно"}


@router.post("/change-password")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Смена пароля текущего пользователя.
    """
    ip, user_agent = get_client_info(request)
    
    # Проверяем текущий пароль
    if not current_user.user.password_hash or not verify_password(
        data.current_password, current_user.user.password_hash
    ):
        logger.warning(f"Неверный текущий пароль при смене: {current_user.username}, IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный текущий пароль",
        )
    
    # Обновляем пароль
    current_user.user.password_hash = hash_password(data.new_password)
    await db.commit()
    
    # Логируем смену пароля
    await log_action(db, current_user.id, "change_password", ip, user_agent)
    logger.info(f"Смена пароля: {current_user.username}, IP: {ip}")
    
    return {"status": "ok", "message": "Пароль успешно изменён"}


@router.get("/me", response_model=AdminUserResponse)
async def get_current_user_info(
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    Получение информации о текущем пользователе.
    """
    return AdminUserResponse.model_validate(current_user.user)

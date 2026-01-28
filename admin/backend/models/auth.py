# -*- coding: utf-8 -*-
"""
Pydantic схемы для аутентификации в админ-панели.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, EmailStr, field_validator

# Типы ролей как строки (соответствует хранению в БД)
AdminRoleType = Literal["admin", "user"]


# ==================== Запросы ====================

class LoginRequest(BaseModel):
    """Запрос на вход по логину/паролю."""
    username: str = Field(..., min_length=3, max_length=255, description="Логин пользователя")
    password: str = Field(..., min_length=6, max_length=255, description="Пароль")


class TelegramLoginRequest(BaseModel):
    """Запрос на вход через Telegram Login Widget."""
    id: int = Field(..., description="Telegram ID пользователя")
    first_name: Optional[str] = Field(None, max_length=255, description="Имя")
    last_name: Optional[str] = Field(None, max_length=255, description="Фамилия")
    username: Optional[str] = Field(None, max_length=255, description="Username")
    photo_url: Optional[str] = Field(None, max_length=512, description="URL аватара")
    auth_date: int = Field(..., description="Время авторизации (Unix timestamp)")
    hash: str = Field(..., description="Хэш для проверки подлинности")


class RefreshTokenRequest(BaseModel):
    """Запрос на обновление токенов."""
    refresh_token: str = Field(..., description="Refresh token")


class ChangePasswordRequest(BaseModel):
    """Запрос на смену пароля."""
    current_password: str = Field(..., min_length=6, max_length=255, description="Текущий пароль")
    new_password: str = Field(..., min_length=6, max_length=255, description="Новый пароль")


class AdminUserCreate(BaseModel):
    """Запрос на создание пользователя админки."""
    username: str = Field(..., min_length=3, max_length=255, description="Логин")
    password: Optional[str] = Field(None, min_length=6, max_length=255, description="Пароль (опционально если есть telegram_id)")
    email: Optional[EmailStr] = Field(None, description="Email")
    display_name: Optional[str] = Field(None, max_length=255, description="Отображаемое имя")
    telegram_id: Optional[int] = Field(None, description="Telegram ID для входа через Telegram")
    role: AdminRoleType = Field("user", description="Роль пользователя (admin/user)")


class AdminUserUpdate(BaseModel):
    """Запрос на обновление пользователя админки."""
    email: Optional[EmailStr] = Field(None, description="Email")
    display_name: Optional[str] = Field(None, max_length=255, description="Отображаемое имя")
    telegram_id: Optional[int] = Field(None, description="Telegram ID")
    role: Optional[AdminRoleType] = Field(None, description="Роль пользователя (admin/user)")
    is_active: Optional[bool] = Field(None, description="Активен ли аккаунт")
    password: Optional[str] = Field(None, min_length=6, max_length=255, description="Новый пароль")


# ==================== Ответы ====================

class LoginResponse(BaseModel):
    """Ответ на успешный вход."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Refresh token для обновления")
    token_type: str = Field("bearer", description="Тип токена")
    expires_in: int = Field(..., description="Время жизни access token в секундах")
    user: "AdminUserResponse" = Field(..., description="Данные пользователя")


class RefreshTokenResponse(BaseModel):
    """Ответ на обновление токенов."""
    access_token: str = Field(..., description="Новый JWT access token")
    refresh_token: str = Field(..., description="Новый refresh token")
    token_type: str = Field("bearer", description="Тип токена")
    expires_in: int = Field(..., description="Время жизни access token в секундах")


class AdminUserResponse(BaseModel):
    """Данные пользователя админки."""
    id: int = Field(..., description="ID пользователя")
    username: str = Field(..., description="Логин")
    email: Optional[str] = Field(None, description="Email")
    display_name: Optional[str] = Field(None, description="Отображаемое имя")
    telegram_id: Optional[int] = Field(None, description="Telegram ID")
    role: str = Field(..., description="Роль (admin/user)")
    is_active: bool = Field(..., description="Активен ли аккаунт")
    created_at: datetime = Field(..., description="Время создания")
    last_login: Optional[datetime] = Field(None, description="Время последнего входа")
    
    @field_validator('role', mode='before')
    @classmethod
    def normalize_role(cls, v):
        """Нормализует роль к нижнему регистру."""
        if v is None:
            return "user"
        # Если это enum, берём value, иначе приводим к строке
        role_str = v.value if hasattr(v, 'value') else str(v)
        return role_str.lower()
    
    class Config:
        from_attributes = True


class AdminUserListResponse(BaseModel):
    """Список пользователей админки."""
    items: list[AdminUserResponse] = Field(..., description="Список пользователей")
    total: int = Field(..., description="Общее количество")
    page: int = Field(..., description="Текущая страница")
    per_page: int = Field(..., description="Элементов на странице")
    pages: int = Field(..., description="Всего страниц")


# Обновляем forward references
LoginResponse.model_rebuild()

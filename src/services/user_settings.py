"""
Сервис для управления настройками пользователей.
Версия для работы с PostgreSQL через SQLAlchemy.
"""

from typing import Optional
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.session import get_session
from src.db.models import User, UserSettings as UserSettingsModel


try:
    MSK = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    MSK = timezone(timedelta(hours=3))


@dataclass
class UserSettings:
    """Настройки пользователя (dataclass для обратной совместимости)"""
    signature: str = ""  # Полная подпись пользователя (если пустая, не добавляется в пост)
    default_currency: str = "cny"  # cny или rub
    exchange_rate: Optional[float] = None  # Курс обмена для рубля
    price_mode: str = ""  # Режим цен: simple или advanced ("" → брать из глобального settings)
    created_at: str = ""  # Дата первой регистрации пользователя (ISO, МСК)
    daily_limit: Optional[int] = None  # Индивидуальный дневной лимит (None → глобальный/без ограничения)
    monthly_limit: Optional[int] = None  # Индивидуальный месячный лимит (None → глобальный/без ограничения)


def _date_to_iso(d: date) -> str:
    """Конвертирует date в ISO строку"""
    return d.isoformat() if d else ""


def _iso_to_date(s: str) -> date:
    """Конвертирует ISO строку в date"""
    try:
        return date.fromisoformat(s)
    except Exception:
        return date.today()


def _model_to_dataclass(model: UserSettingsModel, user_model: Optional[User] = None) -> UserSettings:
    """Конвертирует модель БД в dataclass"""
    return UserSettings(
        signature=model.signature or "",
        default_currency=model.default_currency or "cny",
        exchange_rate=model.exchange_rate,
        price_mode=model.price_mode or "",
        created_at=_date_to_iso(user_model.created_at) if user_model else "",
        daily_limit=model.daily_limit,
        monthly_limit=model.monthly_limit,
    )


class UserSettingsService:
    """Сервис для работы с настройками пользователей (работает с PostgreSQL)"""
    
    def __init__(self):
        """Инициализация сервиса (без параметров, так как используется БД)"""
        pass

    async def _ensure_user(self, session: AsyncSession, user_id: int, username: Optional[str] = None) -> User:
        """Создаёт пользователя, если его нет"""
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        
        if user is None:
            now_msk = datetime.now(MSK).date()
            user = User(user_id=user_id, username=username, created_at=now_msk)
            session.add(user)
            await session.flush()
        elif username and user.username != username:
            user.username = username
        
        return user

    async def _get_or_create_settings(self, session: AsyncSession, user_id: int, username: Optional[str] = None) -> tuple[UserSettingsModel, User]:
        """Получает или создаёт настройки пользователя"""
        user = await self._ensure_user(session, user_id, username)
        
        result = await session.execute(select(UserSettingsModel).where(UserSettingsModel.user_id == user_id))
        user_settings = result.scalar_one_or_none()
        
        if user_settings is None:
            # Создаём настройки по умолчанию
            default_signature = getattr(settings, 'DEFAULT_SIGNATURE', '')
            default_currency = getattr(settings, 'DEFAULT_CURRENCY', 'cny')
            default_price_mode = (getattr(settings, 'PRICE_MODE', 'simple') or 'simple').strip().lower()
            
            user_settings = UserSettingsModel(
                user_id=user_id,
                signature=default_signature,
                default_currency=default_currency,
                price_mode=default_price_mode,
            )
            session.add(user_settings)
            await session.flush()
        
        return user_settings, user

    async def get_settings(self, user_id: int, username: Optional[str] = None) -> UserSettings:
        """
        Получает настройки пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            username: Telegram username (опционально, для обновления)
            
        Returns:
            UserSettings: Настройки пользователя (создаются с дефолтами, если не существуют)
        """
        async for session in get_session():
            user_settings_model, user_model = await self._get_or_create_settings(session, user_id, username)
            await session.commit()
            return _model_to_dataclass(user_settings_model, user_model)

    async def update_signature(self, user_id: int, signature: str, username: Optional[str] = None) -> UserSettings:
        """Обновляет подпись пользователя"""
        async for session in get_session():
            user_settings, user = await self._get_or_create_settings(session, user_id, username)
            user_settings.signature = signature.strip()
            await session.commit()
            return _model_to_dataclass(user_settings, user)

    async def update_currency(self, user_id: int, currency: str, username: Optional[str] = None) -> UserSettings:
        """Обновляет валюту пользователя"""
        async for session in get_session():
            user_settings, user = await self._get_or_create_settings(session, user_id, username)
            currency_lower = currency.lower()
            user_settings.default_currency = currency_lower
            
            # Если переключились на CNY, сбрасываем курс
            if currency_lower == "cny":
                user_settings.exchange_rate = None
            
            await session.commit()
            return _model_to_dataclass(user_settings, user)

    async def update_exchange_rate(self, user_id: int, rate: float, username: Optional[str] = None) -> UserSettings:
        """Обновляет курс обмена для пользователя"""
        async for session in get_session():
            user_settings, user = await self._get_or_create_settings(session, user_id, username)
            user_settings.exchange_rate = rate
            await session.commit()
            return _model_to_dataclass(user_settings, user)

    async def update_price_mode(self, user_id: int, price_mode: str, username: Optional[str] = None) -> UserSettings:
        """Обновляет режим цен для пользователя"""
        async for session in get_session():
            user_settings, user = await self._get_or_create_settings(session, user_id, username)
            normalized = (price_mode or "").strip().lower()
            if normalized not in {"simple", "advanced"}:
                normalized = ""
            user_settings.price_mode = normalized
            await session.commit()
            return _model_to_dataclass(user_settings, user)

    async def update_limits(self, user_id: int, daily_limit: int | None = None, monthly_limit: int | None = None, username: Optional[str] = None) -> UserSettings:
        """Обновляет индивидуальные лимиты пользователя"""
        def _norm(val):
            if val is None:
                return None
            try:
                iv = int(val)
                return iv if iv > 0 else None
            except Exception:
                return None
        
        async for session in get_session():
            user_settings, user = await self._get_or_create_settings(session, user_id, username)
            if daily_limit is not None:
                user_settings.daily_limit = _norm(daily_limit)
            if monthly_limit is not None:
                user_settings.monthly_limit = _norm(monthly_limit)
            await session.commit()
            return _model_to_dataclass(user_settings, user)


# Глобальный экземпляр сервиса
_DEFAULT_SERVICE = UserSettingsService()


def get_user_settings_service() -> UserSettingsService:
    """
    Возвращает общий экземпляр сервиса настроек пользователей для повторного использования.
    """
    return _DEFAULT_SERVICE

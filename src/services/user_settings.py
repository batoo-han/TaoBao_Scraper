<<<<<<< HEAD
"""
Сервис для управления настройками пользователей.
Хранит настройки в JSON файле для простоты (без БД).
"""

import json
import os
from typing import Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from src.core.config import settings


@dataclass
class UserSettings:
    """Настройки пользователя"""
    signature: str = "@annabbox"
    default_currency: str = "cny"  # cny или rub
    exchange_rate: Optional[float] = None  # Курс обмена для рубля


class UserSettingsService:
    """Сервис для работы с настройками пользователей"""
    
    def __init__(self, storage_file: str = "data/user_settings.json"):
        """
        Инициализация сервиса.
        
        Args:
            storage_file: Путь к файлу для хранения настроек
        """
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        self._settings_cache: dict[int, UserSettings] = {}
        self._load_settings()
    
    def _load_settings(self) -> None:
        """Загружает настройки из файла"""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for user_id_str, settings_dict in data.items():
                        user_id = int(user_id_str)
                        # Обрабатываем exchange_rate: если None или null, устанавливаем None
                        if 'exchange_rate' in settings_dict:
                            rate = settings_dict['exchange_rate']
                            if rate is None or (isinstance(rate, str) and rate.lower() == 'null'):
                                settings_dict['exchange_rate'] = None
                            else:
                                try:
                                    settings_dict['exchange_rate'] = float(rate)
                                except (ValueError, TypeError):
                                    settings_dict['exchange_rate'] = None
                        self._settings_cache[user_id] = UserSettings(**settings_dict)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                # Если файл повреждён, начинаем с пустого кэша
                if hasattr(settings, 'DEBUG_MODE') and settings.DEBUG_MODE:
                    print(f"[UserSettings] Ошибка загрузки настроек: {e}")
                self._settings_cache = {}
        else:
            self._settings_cache = {}
    
    def _save_settings(self) -> None:
        """Сохраняет настройки в файл"""
        data = {}
        for user_id, user_settings in self._settings_cache.items():
            data[str(user_id)] = asdict(user_settings)
        
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            if hasattr(settings, 'DEBUG_MODE') and settings.DEBUG_MODE:
                print(f"[UserSettings] Ошибка сохранения настроек: {e}")
    
    def get_settings(self, user_id: int) -> UserSettings:
        """
        Получает настройки пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            UserSettings: Настройки пользователя (создаются с дефолтами, если не существуют)
        """
        if user_id not in self._settings_cache:
            # Создаём настройки по умолчанию
            default_signature = getattr(settings, 'DEFAULT_SIGNATURE', '@annabbox')
            default_currency = getattr(settings, 'DEFAULT_CURRENCY', 'cny')
            self._settings_cache[user_id] = UserSettings(
                signature=default_signature,
                default_currency=default_currency
            )
            self._save_settings()
        
        return self._settings_cache[user_id]
    
    def update_signature(self, user_id: int, signature: str) -> UserSettings:
        """
        Обновляет подпись пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            signature: Новая подпись
            
        Returns:
            UserSettings: Обновлённые настройки
        """
        settings_obj = self.get_settings(user_id)
        settings_obj.signature = signature.strip()
        self._save_settings()
        return settings_obj
    
    def update_currency(self, user_id: int, currency: str) -> UserSettings:
        """
        Обновляет валюту пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            currency: Новая валюта (cny или rub)
            
        Returns:
            UserSettings: Обновлённые настройки
        """
        settings_obj = self.get_settings(user_id)
        currency_lower = currency.lower()
        settings_obj.default_currency = currency_lower
        
        # Если переключились на CNY, сбрасываем курс
        if currency_lower == "cny":
            settings_obj.exchange_rate = None
        
        self._save_settings()
        return settings_obj
    
    def update_exchange_rate(self, user_id: int, rate: float) -> UserSettings:
        """
        Обновляет курс обмена для пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            rate: Курс обмена (1 юань = rate рублей)
            
        Returns:
            UserSettings: Обновлённые настройки
        """
        settings_obj = self.get_settings(user_id)
        settings_obj.exchange_rate = rate
        self._save_settings()
        return settings_obj
=======
"""Service layer for managing user profiles and personalization."""

from __future__ import annotations

from typing import Optional
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.models import User, UserSettings, UsageStats


class UserSettingsService:
    """Encapsulates DB operations for user profiles and settings."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = None,
    ) -> User:
        """Fetch an existing user or create a new one with defaults."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if user:
            # Update profile data if changed
            updates = {}
            if username is not None and user.username != username:
                updates["username"] = username
            if first_name is not None and user.first_name != first_name:
                updates["first_name"] = first_name
            if last_name is not None and user.last_name != last_name:
                updates["last_name"] = last_name
            if language_code is not None and user.language_code != language_code:
                updates["language_code"] = language_code
            if updates:
                await self.session.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(**updates)
                )
                await self.session.flush()
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            is_admin=False,
        )
        self.session.add(user)
        await self.session.flush()

        # Create default settings row
        user_settings = UserSettings(
            user_id=user.id,
            signature=settings.DEFAULT_SIGNATURE,
            default_currency=settings.DEFAULT_CURRENCY,
            preferences={},
        )
        self.session.add(user_settings)
        await self.session.flush()

        # Initialize usage stats
        stats = UsageStats(user_id=user.id, total_requests=0, total_tokens=0)
        self.session.add(stats)
        await self.session.flush()

        return user

    async def get_settings(self, user_id: int) -> UserSettings:
        """Return user settings (expects row to exist)."""
        result = await self.session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        settings_row = result.scalar_one_or_none()
        if settings_row is None:
            # Create defaults on the fly (should seldom happen)
            settings_row = UserSettings(
                user_id=user_id,
                signature=settings.DEFAULT_SIGNATURE,
                default_currency=settings.DEFAULT_CURRENCY,
                preferences={},
            )
            self.session.add(settings_row)
            await self.session.flush()
        return settings_row

    async def update_signature(self, user_id: int, signature: str) -> UserSettings:
        """Update the user's post signature."""
        settings_row = await self.get_settings(user_id)
        settings_row.signature = signature.strip()
        await self.session.flush()
        return settings_row

    async def update_currency(self, user_id: int, currency: str) -> UserSettings:
        """Update default currency and reset exchange rate if switching back to CNY."""
        currency = currency.lower()
        settings_row = await self.get_settings(user_id)
        settings_row.default_currency = currency
        if currency == "cny":
            settings_row.exchange_rate = None
            settings_row.exchange_rate_at = None
        await self.session.flush()
        return settings_row

    async def update_exchange_rate(self, user_id: int, rate: float) -> UserSettings:
        """Set the exchange rate for users who choose RUB as default currency."""
        settings_row = await self.get_settings(user_id)
        settings_row.exchange_rate = rate
        settings_row.exchange_rate_at = datetime.utcnow()
        await self.session.flush()
        return settings_row

    async def record_usage(self, user_id: Optional[int], vendor: str, tokens: int = 0) -> None:
        """Increment usage counters."""
        stmt = select(UsageStats).where(
            UsageStats.user_id == user_id,
            UsageStats.vendor == vendor,
        )
        result = await self.session.execute(stmt)
        stats = result.scalar_one_or_none()

        if stats is None:
            stats = UsageStats(
                user_id=user_id,
                vendor=vendor,
                total_requests=1,
                total_tokens=tokens,
                last_request_at=datetime.utcnow(),
            )
            self.session.add(stats)
        else:
            stats.total_requests += 1
            stats.total_tokens += tokens
            stats.last_request_at = datetime.utcnow()

        await self.session.flush()

>>>>>>> ea50f5eeb9953ad571713ef3461bd36d187f61e9


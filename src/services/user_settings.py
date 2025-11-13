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



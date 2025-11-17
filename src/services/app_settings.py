"""Service for global (admin-managed) application settings."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.models import AppSettings

SUPPORTED_VENDORS = {"yandex", "openai", "proxiapi"}
SUPPORTED_PLATFORMS = {"taobao", "pinduoduo", "szwego", "1688"}


class AppSettingsService:
    """Read/write access to AppSettings."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_app_settings(self) -> AppSettings:
        """Ensure app settings row exists and return it."""
        result = await self.session.execute(select(AppSettings).limit(1))
        app_settings = result.scalar_one_or_none()
        if app_settings:
            return app_settings

        # Создаем настройки по умолчанию
        default_platforms = {
            "taobao": {"enabled": True},
            "pinduoduo": {"enabled": True},
            "szwego": {"enabled": False},
            "1688": {"enabled": False},
        }
        
        app_settings = AppSettings(
            id=1,
            active_llm_vendor=settings.DEFAULT_LLM_VENDOR,
            llm_config={},
            consent_text="",
            app_config={},
            platforms_config=default_platforms,
            pending_restart_config={},
            updated_at=datetime.utcnow(),
        )
        self.session.add(app_settings)
        await self.session.flush()
        return app_settings

    async def set_provider(self, vendor: str, config: Dict[str, Any]) -> AppSettings:
        """Change active LLM vendor and update its config."""
        vendor = vendor.lower()
        if vendor not in SUPPORTED_VENDORS:
            raise ValueError(f"Unsupported vendor '{vendor}'")

        app_settings = await self.get_app_settings()
        app_settings.active_llm_vendor = vendor
        app_settings.llm_config = config or {}
        app_settings.updated_at = datetime.utcnow()
        await self.session.flush()
        return app_settings

    async def update_consent_text(self, text: str) -> AppSettings:
        """Persist consent text (ФЗ-152)."""
        app_settings = await self.get_app_settings()
        app_settings.consent_text = text
        app_settings.updated_at = datetime.utcnow()
        await self.session.flush()
        return app_settings

    async def get_app_config(self) -> Dict[str, Any]:
        """Получить все настройки приложения из app_config."""
        app_settings = await self.get_app_settings()
        return app_settings.app_config or {}

    async def update_app_config(self, config: Dict[str, Any]) -> AppSettings:
        """
        Обновить настройки приложения.
        
        Args:
            config: Словарь с настройками (будет объединен с существующими)
        """
        app_settings = await self.get_app_settings()
        current_config = dict(app_settings.app_config or {})
        current_config.update(config)
        app_settings.app_config = current_config
        app_settings.updated_at = datetime.utcnow()
        await self.session.flush()
        return app_settings

    async def get_platforms_config(self) -> Dict[str, Any]:
        """Получить настройки платформ (магазинов)."""
        app_settings = await self.get_app_settings()
        if not app_settings.platforms_config:
            # Возвращаем настройки по умолчанию
            return {
                "taobao": {"enabled": True},
                "pinduoduo": {"enabled": True},
                "szwego": {"enabled": False},
                "1688": {"enabled": False},
            }
        return app_settings.platforms_config

    async def update_platform_config(self, platform: str, enabled: bool) -> AppSettings:
        """
        Включить/выключить платформу.
        
        Args:
            platform: Название платформы (taobao, pinduoduo, szwego, 1688)
            enabled: Включена ли платформа
        """
        platform = platform.lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform '{platform}'")

        app_settings = await self.get_app_settings()
        platforms_config = dict(app_settings.platforms_config or {})
        platform_config = dict(platforms_config.get(platform, {}))
        platform_config["enabled"] = enabled
        platforms_config[platform] = platform_config
        app_settings.platforms_config = platforms_config
        app_settings.updated_at = datetime.utcnow()
        await self.session.flush()
        return app_settings

    async def add_pending_restart_config(self, updates: Dict[str, Any]) -> AppSettings:
        """Сохранить настройки, требующие перезапуска."""
        app_settings = await self.get_app_settings()
        pending_config = dict(app_settings.pending_restart_config or {})
        pending_config.update(updates)
        app_settings.pending_restart_config = pending_config
        app_settings.updated_at = datetime.utcnow()
        await self.session.flush()
        return app_settings

    async def clear_pending_restart_keys(self, keys: List[str]) -> AppSettings:
        """Удалить ключи настроек из списка ожидающих перезапуска."""
        app_settings = await self.get_app_settings()
        pending_config = dict(app_settings.pending_restart_config or {})
        for key in keys:
            pending_config.pop(key, None)
        app_settings.pending_restart_config = pending_config
        app_settings.updated_at = datetime.utcnow()
        await self.session.flush()
        return app_settings

    async def get_pending_restart_config(self) -> Dict[str, Any]:
        """Получить настройки, ожидающие перезапуска для применения."""
        app_settings = await self.get_app_settings()
        return dict(app_settings.pending_restart_config or {})

    async def get_llm_prompt_config(self) -> Dict[str, Any]:
        """Получить настройки промпта для LLM (промпт, температура, макс. токенов)."""
        app_settings = await self.get_app_settings()
        llm_config = app_settings.llm_config or {}
        return {
            "prompt_template": llm_config.get("prompt_template", ""),
            "temperature": llm_config.get("temperature", 0.05),
            "max_tokens": llm_config.get("max_tokens", 900),
        }

    async def update_llm_prompt_config(
        self, 
        prompt_template: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AppSettings:
        """
        Обновить настройки промпта для LLM.
        
        Args:
            prompt_template: Шаблон промпта
            temperature: Температура генерации (0.0-1.0)
            max_tokens: Максимальное количество токенов
        """
        app_settings = await self.get_app_settings()
        if not app_settings.llm_config:
            app_settings.llm_config = {}
        
        if prompt_template is not None:
            app_settings.llm_config["prompt_template"] = prompt_template
        if temperature is not None:
            app_settings.llm_config["temperature"] = temperature
        if max_tokens is not None:
            app_settings.llm_config["max_tokens"] = max_tokens
        
        app_settings.updated_at = datetime.utcnow()
        await self.session.flush()
        return app_settings

"""LLM provider manager with caching and usage tracking."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.llm.base import LLMResult
from src.api.yandex_gpt import YandexLLMProvider
from src.api.openai_client import OpenAILLMProvider
from src.api.proxiapi_client import ProxiapiLLMProvider
from src.db.models import LLMCache
from .app_settings import AppSettingsService, SUPPORTED_VENDORS
from .user_settings import UserSettingsService
from src.core.config import settings


class UnsupportedProviderError(RuntimeError):
    """Raised when an unsupported vendor is requested."""


class LLMProviderManager:
    """Coordinates provider selection, caching, and usage statistics."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.app_settings_service = AppSettingsService(session)
        self.user_settings_service = UserSettingsService(session)

    async def _get_vendor_and_config(self) -> tuple[str, Dict[str, Any]]:
        app_settings = await self.app_settings_service.get_app_settings()
        return app_settings.active_llm_vendor, app_settings.llm_config or {}

    async def _select_provider(self, vendor: str, config: Dict[str, Any]):
        vendor = vendor.lower()
        if vendor not in SUPPORTED_VENDORS:
            raise UnsupportedProviderError(f"Vendor '{vendor}' is not supported")

        if vendor == "yandex":
            return YandexLLMProvider()
        if vendor == "openai":
            api_key = config.get("api_key") or settings.OPENAI_API_KEY
            model = config.get("model") or settings.OPENAI_MODEL
            return OpenAILLMProvider(api_key=api_key, model=model)
        if vendor == "proxiapi":
            api_key = config.get("api_key") or settings.PROXIAPI_API_KEY
            model = config.get("model") or settings.PROXIAPI_MODEL
            return ProxiapiLLMProvider(api_key=api_key, model=model)
        raise UnsupportedProviderError(f"Vendor '{vendor}' is not supported")

    async def _get_cached(self, vendor: str, cache_key: str) -> Optional[Dict[str, Any]]:
        stmt = select(LLMCache).where(
            LLMCache.vendor == vendor,
            LLMCache.cache_key == cache_key,
        )
        result = await self.session.execute(stmt)
        cache_entry = result.scalar_one_or_none()
        if not cache_entry:
            return None
        if cache_entry.expires_at and cache_entry.expires_at < datetime.utcnow():
            await self.session.execute(
                delete(LLMCache).where(LLMCache.id == cache_entry.id)
            )
            await self.session.flush()
            return None
        return cache_entry.response_payload

    async def _store_cache(self, vendor: str, cache_key: str, payload: Dict[str, Any], response: Dict[str, Any]) -> None:
        ttl_minutes = settings.LLM_CACHE_TTL_MINUTES if hasattr(settings, "LLM_CACHE_TTL_MINUTES") else 240
        expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes) if ttl_minutes > 0 else None
        cache_entry = LLMCache(
            vendor=vendor,
            cache_key=cache_key,
            request_payload=payload,
            response_payload=response,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        self.session.add(cache_entry)
        await self.session.flush()

    async def generate(self, user_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        """Main entrypoint for obtaining post content from configured provider."""
        vendor, config = await self._get_vendor_and_config()
        provider = await self._select_provider(vendor, config)
        cache_key = provider.build_cache_key(payload)

        cached = await self._get_cached(provider.vendor, cache_key)
        if cached is not None:
            await self.user_settings_service.record_usage(user_id, provider.vendor, tokens=0)
            return cached

        result: LLMResult = await provider.generate(payload)

        await self._store_cache(provider.vendor, cache_key, payload, result.data)
        await self.user_settings_service.record_usage(
            user_id,
            provider.vendor,
            tokens=result.tokens_used or 0,
        )
        return result.data



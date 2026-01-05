"""
Сервис для управления глобальными настройками администратора.
Версия для работы с PostgreSQL через SQLAlchemy.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import llm_provider
from src.core.config import settings
from src.db.session import get_session
from src.db.models import AdminSettings as AdminSettingsModel


def _normalize_provider(raw: str | None) -> str:
    """
    Приводит название провайдера к допустимому виду.
    Допустимые значения: yandex, openai, proxyapi.
    """
    value = (raw or "yandex").strip().lower()
    return value if value in {"yandex", "openai", "proxyapi"} else "yandex"


def _normalize_channel_id(raw: str | int | None) -> str:
    """
    Нормализует идентификатор канала (ID или @username).
    Пустая строка означает отключённую рассылку.
    """
    if raw is None:
        return ""
    value = str(raw).strip()
    if not value:
        return ""
    if value.startswith("@"):
        return value
    if value.lstrip("-").isdigit():
        try:
            return str(int(value))
        except Exception:
            return value
    return value


@dataclass
class AdminSettings:
    """
    Модель настроек, доступных админу (dataclass для обратной совместимости).
    """
    default_llm: str = "yandex"
    yandex_model: str = "yandexgpt-lite"
    openai_model: str = "gpt-4o-mini"
    translate_provider: str = "yandex"
    translate_model: str = "yandexgpt-lite"
    translate_legacy: bool = False
    convert_currency: bool = False
    tmapi_notify_439: bool = False
    debug_mode: bool = False
    mock_mode: bool = False
    forward_channel_id: str = ""
    per_user_daily_limit: int | None = None
    per_user_monthly_limit: int | None = None
    total_daily_limit: int | None = None
    total_monthly_limit: int | None = None


def _model_to_dataclass(model: AdminSettingsModel) -> AdminSettings:
    """Конвертирует модель БД в dataclass"""
    return AdminSettings(
        default_llm=model.default_llm or "yandex",
        yandex_model=model.yandex_model or "yandexgpt-lite",
        openai_model=model.openai_model or "gpt-4o-mini",
        translate_provider=model.translate_provider or "yandex",
        translate_model=model.translate_model or "yandexgpt-lite",
        translate_legacy=model.translate_legacy,
        convert_currency=model.convert_currency,
        tmapi_notify_439=model.tmapi_notify_439,
        debug_mode=model.debug_mode,
        mock_mode=model.mock_mode,
        forward_channel_id=model.forward_channel_id or "",
        per_user_daily_limit=model.per_user_daily_limit,
        per_user_monthly_limit=model.per_user_monthly_limit,
        total_daily_limit=model.total_daily_limit,
        total_monthly_limit=model.total_monthly_limit,
    )


class AdminSettingsService:
    """
    Сервис для управления глобальными настройками администратора (работает с PostgreSQL).
    """

    def __init__(self):
        """Инициализация сервиса (без параметров, так как используется БД)"""
        pass

    async def _get_or_create_settings(self, session: AsyncSession) -> AdminSettingsModel:
        """Получает или создаёт настройки администратора"""
        result = await session.execute(select(AdminSettingsModel).where(AdminSettingsModel.id == 1))
        admin_settings = result.scalar_one_or_none()
        
        if admin_settings is None:
            admin_settings = AdminSettingsModel(id=1)
            # Инициализируем forward_channel_id из .env, если он указан
            if not admin_settings.forward_channel_id:
                env_forward_channel_id = getattr(settings, "FORWARD_CHANNEL_ID", "") or ""
                if env_forward_channel_id:
                    admin_settings.forward_channel_id = _normalize_channel_id(env_forward_channel_id)
            session.add(admin_settings)
            await session.commit()
            await session.refresh(admin_settings)
        else:
            # Если запись существует, но forward_channel_id пустой, инициализируем из .env
            if not admin_settings.forward_channel_id:
                env_forward_channel_id = getattr(settings, "FORWARD_CHANNEL_ID", "") or ""
                if env_forward_channel_id:
                    admin_settings.forward_channel_id = _normalize_channel_id(env_forward_channel_id)
                    await session.commit()
                    await session.refresh(admin_settings)
        
        return admin_settings

    async def get_settings(self) -> AdminSettings:
        """Получает текущие настройки администратора"""
        async for session in get_session():
            model = await self._get_or_create_settings(session)
            return _model_to_dataclass(model)

    async def get_payload(self) -> Dict[str, Any]:
        """
        Возвращает сериализуемое представление для Mimi App.
        """
        admin_settings = await self.get_settings()
        return asdict(admin_settings)

    async def apply_to_runtime(self) -> None:
        """
        Применяет текущие настройки к объекту settings и обнуляет кэши клиентов.
        """
        admin_settings = await self.get_settings()
        
        settings.DEFAULT_LLM = admin_settings.default_llm
        settings.YANDEX_GPT_MODEL = admin_settings.yandex_model
        settings.OPENAI_MODEL = admin_settings.openai_model
        settings.TRANSLATE_PROVIDER = admin_settings.translate_provider
        settings.TRANSLATE_MODEL = admin_settings.translate_model
        settings.TRANSLATE_LEGACY = admin_settings.translate_legacy
        settings.CONVERT_CURRENCY = admin_settings.convert_currency
        settings.TMAPI_NOTIFY_439 = admin_settings.tmapi_notify_439
        settings.DEBUG_MODE = admin_settings.debug_mode
        settings.MOCK_MODE = admin_settings.mock_mode
        settings.FORWARD_CHANNEL_ID = admin_settings.forward_channel_id
        settings.PER_USER_DAILY_LIMIT = admin_settings.per_user_daily_limit
        settings.PER_USER_MONTHLY_LIMIT = admin_settings.per_user_monthly_limit
        settings.TOTAL_DAILY_LIMIT = admin_settings.total_daily_limit
        settings.TOTAL_MONTHLY_LIMIT = admin_settings.total_monthly_limit

        # Сбрасываем кэши, чтобы новые настройки вступили в силу немедленно
        llm_provider.reset_llm_cache()
        llm_provider.reset_translation_cache()

    async def update_llm_block(
        self,
        *,
        default_llm: str,
        yandex_model: str,
        openai_model: str,
        translate_provider: str,
        translate_model: str,
        translate_legacy: bool,
    ) -> AdminSettings:
        """
        Обновляет настройки провайдеров и моделей.
        """
        provider = _normalize_provider(default_llm)
        translate = _normalize_provider(translate_provider)

        updated = await self.update_settings(
            default_llm=provider,
            yandex_model=yandex_model.strip() or None,
            openai_model=openai_model.strip() or None,
            translate_provider=translate,
            translate_model=translate_model.strip() or None,
            translate_legacy=bool(translate_legacy),
        )
        await self.apply_to_runtime()
        return updated

    async def update_feature_flags(
        self,
        *,
        convert_currency: bool,
        tmapi_notify_439: bool,
        debug_mode: bool,
        mock_mode: bool,
        forward_channel_id: str | int | None,
        per_user_daily_limit: int | None = None,
        per_user_monthly_limit: int | None = None,
        total_daily_limit: int | None = None,
        total_monthly_limit: int | None = None,
    ) -> AdminSettings:
        """
        Переключает рабочие опции бота.
        """
        def _norm_limit(val: int | str | None) -> int | None:
            if val in (None, "", 0, "0"):
                return None
            try:
                iv = int(val)
                return iv if iv > 0 else None
            except Exception:
                return None

        updated = await self.update_settings(
            convert_currency=bool(convert_currency),
            tmapi_notify_439=bool(tmapi_notify_439),
            debug_mode=bool(debug_mode),
            mock_mode=bool(mock_mode),
            forward_channel_id=_normalize_channel_id(forward_channel_id),
            per_user_daily_limit=_norm_limit(per_user_daily_limit),
            per_user_monthly_limit=_norm_limit(per_user_monthly_limit),
            total_daily_limit=_norm_limit(total_daily_limit),
            total_monthly_limit=_norm_limit(total_monthly_limit),
        )
        await self.apply_to_runtime()
        return updated

    async def update_settings(self, **kwargs) -> AdminSettings:
        """
        Обновляет настройки администратора.
        
        Args:
            **kwargs: Параметры для обновления (любые поля из AdminSettings)
        
        Returns:
            AdminSettings: Обновлённые настройки
        """
        async for session in get_session():
            model = await self._get_or_create_settings(session)
            
            # Обновляем поля, если они переданы
            if "default_llm" in kwargs:
                model.default_llm = kwargs["default_llm"]
            if "yandex_model" in kwargs:
                model.yandex_model = kwargs["yandex_model"]
            if "openai_model" in kwargs:
                model.openai_model = kwargs["openai_model"]
            if "translate_provider" in kwargs:
                model.translate_provider = kwargs["translate_provider"]
            if "translate_model" in kwargs:
                model.translate_model = kwargs["translate_model"]
            if "translate_legacy" in kwargs:
                model.translate_legacy = bool(kwargs["translate_legacy"])
            if "convert_currency" in kwargs:
                model.convert_currency = bool(kwargs["convert_currency"])
            if "tmapi_notify_439" in kwargs:
                model.tmapi_notify_439 = bool(kwargs["tmapi_notify_439"])
            if "debug_mode" in kwargs:
                model.debug_mode = bool(kwargs["debug_mode"])
            if "mock_mode" in kwargs:
                model.mock_mode = bool(kwargs["mock_mode"])
            if "forward_channel_id" in kwargs:
                model.forward_channel_id = kwargs["forward_channel_id"] or ""
            if "per_user_daily_limit" in kwargs:
                val = kwargs["per_user_daily_limit"]
                model.per_user_daily_limit = int(val) if val is not None and int(val) > 0 else None
            if "per_user_monthly_limit" in kwargs:
                val = kwargs["per_user_monthly_limit"]
                model.per_user_monthly_limit = int(val) if val is not None and int(val) > 0 else None
            if "total_daily_limit" in kwargs:
                val = kwargs["total_daily_limit"]
                model.total_daily_limit = int(val) if val is not None and int(val) > 0 else None
            if "total_monthly_limit" in kwargs:
                val = kwargs["total_monthly_limit"]
                model.total_monthly_limit = int(val) if val is not None and int(val) > 0 else None
            
            await session.commit()
            return _model_to_dataclass(model)


# Глобальный экземпляр сервиса
admin_settings_service = AdminSettingsService()

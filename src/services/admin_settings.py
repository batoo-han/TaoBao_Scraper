"""
Сервис для управления глобальными параметрами бота, доступными администратору через Mimi App.
Хранит настройки в JSON файле и синхронно обновляет объект settings для горячего применения.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Any, Dict

from src.api import llm_provider
from src.core.config import settings


def _normalize_provider(raw: str | None) -> str:
    """
    Приводит название провайдера к допустимому виду.
    Допустимые значения: yandex, openai, proxyapi.
    """
    value = (raw or "yandex").strip().lower()
    return value if value in {"yandex", "openai", "proxyapi"} else "yandex"


@dataclass
class AdminSettings:
    """
    Модель настроек, доступных админу.
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


class AdminSettingsService:
    """
    Управляет настройками администратора и синхронизирует их с рантаймом.
    """

    def __init__(self, storage_file: str = "data/admin_settings.json") -> None:
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._data = AdminSettings(
            default_llm=_normalize_provider(getattr(settings, "DEFAULT_LLM", "yandex")),
            yandex_model=getattr(settings, "YANDEX_GPT_MODEL", "yandexgpt-lite"),
            openai_model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
            translate_provider=_normalize_provider(
                getattr(settings, "TRANSLATE_PROVIDER", "") or getattr(settings, "DEFAULT_LLM", "yandex")
            ),
            translate_model=getattr(settings, "TRANSLATE_MODEL", "") or getattr(
                settings, "YANDEX_GPT_MODEL", "yandexgpt-lite"
            ),
            translate_legacy=getattr(settings, "TRANSLATE_LEGACY", False),
            convert_currency=getattr(settings, "CONVERT_CURRENCY", False),
            tmapi_notify_439=getattr(settings, "TMAPI_NOTIFY_439", False),
            debug_mode=getattr(settings, "DEBUG_MODE", False),
            mock_mode=getattr(settings, "MOCK_MODE", False),
        )
        self._load_from_disk()
        self.apply_to_runtime()

    def _load_from_disk(self) -> None:
        """
        Пробует загрузить сохранённые настройки.
        """
        if not self.storage_file.exists():
            return

        try:
            with open(self.storage_file, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return

        updated = replace(self._data, **{k: payload.get(k, getattr(self._data, k)) for k in asdict(self._data)})
        updated.default_llm = _normalize_provider(payload.get("default_llm", updated.default_llm))
        updated.translate_provider = _normalize_provider(payload.get("translate_provider", updated.translate_provider))
        self._data = updated

    def _save_to_disk(self) -> None:
        """
        Сохраняет настройки на диск.
        """
        with open(self.storage_file, "w", encoding="utf-8") as fh:
            json.dump(asdict(self._data), fh, ensure_ascii=False, indent=2)

    def apply_to_runtime(self) -> None:
        """
        Применяет текущие настройки к объекту settings и обнуляет кэши клиентов.
        """
        settings.DEFAULT_LLM = self._data.default_llm
        settings.YANDEX_GPT_MODEL = self._data.yandex_model
        settings.OPENAI_MODEL = self._data.openai_model
        settings.TRANSLATE_PROVIDER = self._data.translate_provider
        settings.TRANSLATE_MODEL = self._data.translate_model
        settings.TRANSLATE_LEGACY = self._data.translate_legacy
        settings.CONVERT_CURRENCY = self._data.convert_currency
        settings.TMAPI_NOTIFY_439 = self._data.tmapi_notify_439
        settings.DEBUG_MODE = self._data.debug_mode
        settings.MOCK_MODE = self._data.mock_mode

        # Сбрасываем кэши, чтобы новые настройки вступили в силу немедленно
        llm_provider.reset_llm_cache()
        llm_provider.reset_translation_cache()

    def get_settings(self) -> AdminSettings:
        """
        Возвращает копию текущих настроек.
        """
        return replace(self._data)

    def get_payload(self) -> Dict[str, Any]:
        """
        Возвращает сериализуемое представление для Mimi App.
        """
        return asdict(self._data)

    def update_llm_block(
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

        with self._lock:
            self._data.default_llm = provider
            self._data.yandex_model = yandex_model.strip() or self._data.yandex_model
            self._data.openai_model = openai_model.strip() or self._data.openai_model
            self._data.translate_provider = translate
            self._data.translate_model = translate_model.strip() or self._data.translate_model
            self._data.translate_legacy = bool(translate_legacy)
            self._save_to_disk()
            self.apply_to_runtime()
            return replace(self._data)

    def update_feature_flags(
        self,
        *,
        convert_currency: bool,
        tmapi_notify_439: bool,
        debug_mode: bool,
        mock_mode: bool,
    ) -> AdminSettings:
        """
        Переключает рабочие опции бота.
        """
        with self._lock:
            self._data.convert_currency = bool(convert_currency)
            self._data.tmapi_notify_439 = bool(tmapi_notify_439)
            self._data.debug_mode = bool(debug_mode)
            self._data.mock_mode = bool(mock_mode)
            self._save_to_disk()
            self.apply_to_runtime()
            return replace(self._data)


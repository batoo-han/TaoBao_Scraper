"""
Фабрика для выбора LLM-провайдера в зависимости от настроек.
Позволяет переключаться между YandexGPT и OpenAI через переменную DEFAULT_LLM.
"""

from functools import lru_cache
from typing import Literal

from src.core.config import settings
from src.api.yandex_gpt import YandexGPTClient
from src.api.yandex_translate import YandexTranslateClient
from src.api.openai_client import OpenAIClient

ProviderName = Literal["yandex", "openai"]


def _normalize_provider(provider_raw: str | None) -> ProviderName:
    """
    Приводит значение DEFAULT_LLM к поддерживаемому виду.
    """
    provider = (provider_raw or "yandex").strip().lower()
    if provider not in {"yandex", "openai"}:
        if settings.DEBUG_MODE:
            print(f"[LLM] Неизвестный провайдер '{provider}'. Используем YandexGPT.")
        provider = "yandex"
    return provider  # type: ignore[return-value]


@lru_cache(maxsize=1)
def _build_client():
    """
    Создаёт и кэширует экземпляр клиента выбранного провайдера.
    """
    provider = _normalize_provider(settings.DEFAULT_LLM)

    if provider == "openai":
        return OpenAIClient()
    return YandexGPTClient()


def get_llm_client():
    """
    Возвращает инициализированный клиент LLM в соответствии с настройками.
    """
    return _build_client()


@lru_cache(maxsize=1)
def _build_translation_client():
    """
    Возвращает клиент для перевода/предобработки цен.
    """
    preferred = (
        settings.TRANSLATE_PROVIDER
        or settings.TRANSLATE_LLM  # fallback для старого названия переменной
        or settings.DEFAULT_LLM
    )
    provider = _normalize_provider(preferred)

    if provider == "openai":
        model_name = (
            settings.TRANSLATE_MODEL
            or settings.TRANSLATE_OPENAI_MODEL
            or settings.OPENAI_MODEL
            or ""
        ).strip()
        return OpenAIClient(model_name=model_name or None)

    # Yandex-провайдер по умолчанию использует YandexGPT; при необходимости можно
    # переключиться на старый переводчик через TRANSLATE_LEGACY=1 (см. ниже).
    legacy_flag = getattr(settings, "TRANSLATE_LEGACY", False)
    if legacy_flag:
        return YandexTranslateClient()

    model_name = (settings.TRANSLATE_MODEL or settings.YANDEX_GPT_MODEL or "").strip()
    return YandexGPTClient(model_name=model_name or None)


def get_translation_client():
    """
    Возвращает клиент перевода согласно настройкам.
    """
    return _build_translation_client()


def reset_llm_cache() -> None:
    """
    Сбрасывает кэши клиентов LLM, чтобы подхватить новые настройки во время работы бота.
    """
    _build_client.cache_clear()


def reset_translation_cache() -> None:
    """
    Сбрасывает кэш переводческого клиента после переключения провайдера или модели.
    """
    _build_translation_client.cache_clear()

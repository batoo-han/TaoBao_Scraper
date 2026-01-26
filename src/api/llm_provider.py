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
from src.api.proxyapi_client import ProxyAPIClient

ProviderName = Literal["yandex", "openai", "proxyapi"]


def _normalize_provider(provider_raw: str | None) -> ProviderName:
    """
    Приводит значение DEFAULT_LLM к поддерживаемому виду.
    """
    provider = (provider_raw or "yandex").strip().lower()
    if provider not in {"yandex", "openai", "proxyapi"}:
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
    if provider == "proxyapi":
        return ProxyAPIClient()
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
    if provider == "proxyapi":
        model_name = (settings.TRANSLATE_MODEL or settings.OPENAI_MODEL or "").strip()
        return ProxyAPIClient(model_name=model_name or None)

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


@lru_cache(maxsize=1)
def _build_postprocess_client():
    """
    Возвращает клиент LLM, используемый ТОЛЬКО для постобработки готового поста.

    ВАЖНО:
    - Постобработка включается флагом ENABLE_POSTPROCESSING.
    - Для постобработки всегда используем OpenAI (минимальную/дешёвую модель),
      независимо от основного DEFAULT_LLM.
    - При любой ошибке инициализации (нет ключа, некорректная модель и т.п.)
      возвращаем None, чтобы основной пайплайн не падал.
    """
    enabled = bool(getattr(settings, "ENABLE_POSTPROCESSING", False))
    if not enabled:
        return None

    # Модель для постобработки: отдельная, компактная (mini), если указана.
    # Если не задана, используем глобальную OPENAI_MODEL (как фолбэк).
    model_name = (
        getattr(settings, "OPENAI_POSTPROCESS_MODEL", "")  # отдельная модель для постобработки
        or getattr(settings, "OPENAI_MODEL", "")           # общая модель OpenAI
    ).strip()

    try:
        # Если модель не указана, передаём None — OpenAIClient подставит значение по умолчанию.
        return OpenAIClient(model_name=model_name or None)
    except Exception:
        # В режиме DEBUG выдаём понятное сообщение, но не ломаем основной сценарий.
        if settings.DEBUG_MODE:
            print("[LLM] Не удалось инициализировать OpenAI-клиент для постобработки. "
                  "Постобработка будет отключена для этого запуска.")
        return None


def get_postprocess_client():
    """
    Возвращает клиент LLM, настроенный для постобработки текста поста.

    Может вернуть None, если:
    - постобработка отключена (ENABLE_POSTPROCESSING=False),
    - не удалось инициализировать OpenAIClient (нет ключа, неверная конфигурация и т.п.).
    """
    return _build_postprocess_client()


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


@lru_cache(maxsize=1)
def _build_hashtags_client():
    """
    Возвращает клиент LLM, используемый ТОЛЬКО для генерации хэштегов на основе готового поста.

    ВАЖНО:
    - Генерация хэштегов включается флагом ENABLE_HASHTAGS.
    - Провайдер задаётся через HASHTAGS_PROVIDER (yandex/openai/proxyapi), если пусто - используется DEFAULT_LLM.
    - Модель задаётся через HASHTAGS_MODEL, если пусто - используется модель провайдера по умолчанию.
    - При любой ошибке инициализации (нет ключа, некорректная модель и т.п.)
      возвращаем None, чтобы основной пайплайн не падал.
    """
    enabled = bool(getattr(settings, "ENABLE_HASHTAGS", False))
    if not enabled:
        return None

    # Определяем провайдер: если HASHTAGS_PROVIDER не указан, используем DEFAULT_LLM
    provider_raw = (getattr(settings, "HASHTAGS_PROVIDER", "") or "").strip()
    if provider_raw:
        provider = _normalize_provider(provider_raw)
    else:
        provider = _normalize_provider(settings.DEFAULT_LLM)

    # Определяем модель: если HASHTAGS_MODEL не указана, используем модель провайдера по умолчанию
    model_name = (getattr(settings, "HASHTAGS_MODEL", "") or "").strip()

    try:
        if provider == "openai":
            if not model_name:
                model_name = settings.OPENAI_MODEL or ""
            return OpenAIClient(model_name=model_name or None)
        if provider == "proxyapi":
            if not model_name:
                model_name = settings.OPENAI_MODEL or ""
            return ProxyAPIClient(model_name=model_name or None)
        
        # YandexGPT
        if not model_name:
            model_name = settings.YANDEX_GPT_MODEL or ""
        return YandexGPTClient(model_name=model_name or None)
    except Exception:
        # В режиме DEBUG выдаём понятное сообщение, но не ломаем основной сценарий.
        if settings.DEBUG_MODE:
            print("[LLM] Не удалось инициализировать клиент для генерации хэштегов. "
                  "Генерация хэштегов будет отключена для этого запуска.")
        return None


def get_hashtags_client():
    """
    Возвращает клиент LLM, настроенный для генерации хэштегов на основе готового поста.

    Может вернуть None, если:
    - генерация хэштегов отключена (ENABLE_HASHTAGS=False),
    - не удалось инициализировать клиент (нет ключа, неверная конфигурация и т.п.).
    """
    return _build_hashtags_client()


def reset_hashtags_cache() -> None:
    """
    Сбрасывает кэш клиента генерации хэштегов после переключения провайдера или модели.
    """
    _build_hashtags_client.cache_clear()
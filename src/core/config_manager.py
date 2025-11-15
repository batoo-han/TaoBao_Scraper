"""
Менеджер конфигурации с поддержкой загрузки и динамического применения настроек из БД.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Set

from src.core.config import Settings, settings
from src.db.session import get_async_session
from src.services.app_settings import AppSettingsService
from src.services.runtime_settings import RuntimeSettingsService

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Централизованный менеджер конфигурации.

    • Формирует runtime-таблицу настроек из значений .env и постоянных значений из БД.
    • Поддерживает обновление настроек налету (runtime_settings) и фиксацию изменений,
      требующих перезапуска (pending_restart_config).
    • Обновляет глобальный объект settings, чтобы остальной код продолжал использовать
      привычный интерфейс (settings.SOME_KEY).
    """

    RESTART_REQUIRED_KEYS: Set[str] = {
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_SSLMODE",
        "ADMIN_PANEL_PORT",
        "ADMIN_JWT_SECRET",
        "BOT_TOKEN",
        "YANDEX_VISION_API_KEY",
        "YANDEX_VISION_FOLDER_ID",
        "YANDEX_VISION_MODEL",
    }

    def __init__(self) -> None:
        self._defaults = Settings().model_dump()
        self._runtime_cache: Dict[str, Any] = {}
        self._pending_restart_keys: Set[str] = set()
        self._db_config_loaded: bool = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Внутренние утилиты
    # ------------------------------------------------------------------

    def _convert_types(self, values: Dict[str, Any]) -> Dict[str, Any]:
        converted: Dict[str, Any] = {}
        for key, raw_value in values.items():
            if key not in self._defaults:
                continue
            default_value = self._defaults[key]
            target_type = type(default_value)
            try:
                if target_type is bool:
                    if isinstance(raw_value, str):
                        converted[key] = raw_value.lower() in ("true", "1", "yes", "on")
                    else:
                        converted[key] = bool(raw_value)
                elif target_type is int:
                    converted[key] = int(raw_value)
                elif target_type is float:
                    converted[key] = float(raw_value)
                elif target_type in (dict, list):
                    converted[key] = raw_value if raw_value is not None else target_type()
                else:
                    converted[key] = str(raw_value) if raw_value is not None else ""
            except (TypeError, ValueError):
                logger.warning("Не удалось привести %s=%s к типу %s", key, raw_value, target_type)
                converted[key] = default_value
        return converted

    def _apply_to_settings(self, updates: Dict[str, Any]) -> None:
        if not updates:
            return
        import src.core.config as config_module

        config_module.settings = settings.model_copy(update=updates)

    def _requires_restart(self, key: str) -> bool:
        return key in self.RESTART_REQUIRED_KEYS

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Заполняет runtime-таблицу и обновляет глобальный settings."""
        async with self._lock:
            try:
                async with get_async_session() as session:
                    runtime_service = RuntimeSettingsService(session)
                    app_settings_service = AppSettingsService(session)

                    app_settings = await app_settings_service.get_app_settings()
                    runtime_values = await runtime_service.get_all()

                    if not runtime_values:
                        initial_values = dict(self._defaults)
                        overrides = app_settings.app_config or {}
                        initial_values.update(overrides)
                        await runtime_service.set_values(initial_values, source="env")
                        runtime_values = await runtime_service.get_all()

                    pending_config = await app_settings_service.get_pending_restart_config()
                    
                    # Если есть pending настройки, значит перезапуск уже произошел - применяем их и очищаем
                    if pending_config:
                        logger.info(
                            "Обнаружены pending настройки после перезапуска (%d ключей). Применяем и очищаем.",
                            len(pending_config)
                        )
                        # Применяем pending настройки к runtime
                        await runtime_service.set_values(pending_config, source="restart", requires_restart=False)
                        # Очищаем pending_restart_config, так как перезапуск уже выполнен
                        await app_settings_service.clear_pending_restart_keys(list(pending_config.keys()))
                        # Перечитываем runtime_values с учетом примененных настроек
                        runtime_values = await runtime_service.get_all()
                    
                    self._pending_restart_keys = set()

                    self._runtime_cache = self._convert_types(runtime_values)
                    self._apply_to_settings(self._runtime_cache)
                    self._db_config_loaded = True

                    logger.info(
                        "Runtime настройки загружены (%d значений). Pending restart: нет",
                        len(self._runtime_cache),
                    )
            except Exception:
                logger.exception("Ошибка инициализации ConfigManager")
                self._db_config_loaded = False

    async def load_from_db(self) -> None:
        """Совместимость со старым API."""
        await self.initialize()

    async def refresh_runtime_cache(self) -> None:
        """Перечитать runtime-таблицу и обновить глобальный settings."""
        async with self._lock:
            try:
                async with get_async_session() as session:
                    runtime_service = RuntimeSettingsService(session)
                    runtime_values = await runtime_service.get_all()
                    self._runtime_cache = self._convert_types(runtime_values)
                    self._apply_to_settings(self._runtime_cache)
            except Exception:
                logger.exception("Не удалось обновить runtime-кэш настроек")

    async def update_setting(self, key: str, value: Any) -> Dict[str, Any]:
        """Обновить одну настройку."""
        return await self.update_settings_batch({key: value})

    async def update_settings_batch(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет набор настроек.

        Возвращает словарь:
        {
            "applied": [...],          # ключи, примененные сразу
            "pending_restart": [...],  # ключи, ожидающие перезапуска
            "runtime": {...},          # актуальный runtime-кэш
            "pending_config": {...},   # значения, требующие перезапуска
        }
        """
        async with self._lock:
            applied: Set[str] = set()
            pending: Set[str] = set()

            try:
                async with get_async_session() as session:
                    runtime_service = RuntimeSettingsService(session)
                    app_settings_service = AppSettingsService(session)

                    await app_settings_service.update_app_config(config)

                    immediate_updates: Dict[str, Any] = {}
                    restart_updates: Dict[str, Any] = {}

                    for key, value in config.items():
                        if self._requires_restart(key):
                            restart_updates[key] = value
                        else:
                            immediate_updates[key] = value

                    if immediate_updates:
                        await runtime_service.set_values(immediate_updates, source="admin", requires_restart=False)
                        applied.update(immediate_updates.keys())

                    if restart_updates:
                        await app_settings_service.add_pending_restart_config(restart_updates)
                        pending.update(restart_updates.keys())

                    if applied:
                        await app_settings_service.clear_pending_restart_keys(list(applied))

                    pending_config = await app_settings_service.get_pending_restart_config()
                    self._pending_restart_keys = set(pending_config.keys())

                    runtime_values = await runtime_service.get_all()
                    self._runtime_cache = self._convert_types(runtime_values)
                    self._apply_to_settings(self._runtime_cache)

                    return {
                        "applied": sorted(applied),
                        "pending_restart": sorted(pending),
                        "runtime": dict(self._runtime_cache),
                        "pending_config": pending_config,
                    }
            except Exception:
                logger.exception("Ошибка при обновлении настроек: %s", config)

            # Возвращаем частичный результат при ошибке
            return {
                "applied": sorted(applied),
                "pending_restart": sorted(pending or set(config.keys())),
                "runtime": dict(self._runtime_cache),
                "pending_config": {key: config[key] for key in pending},
            }

    def get_runtime_cache(self) -> Dict[str, Any]:
        return dict(self._runtime_cache)

    def get_pending_restart_keys(self) -> Set[str]:
        return set(self._pending_restart_keys)

    def is_restart_required(self) -> bool:
        return bool(self._pending_restart_keys)

    @property
    def db_config_loaded(self) -> bool:
        return self._db_config_loaded


config_manager = ConfigManager()


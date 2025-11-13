"""
Сервис для управления временными (runtime) настройками приложения.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import RuntimeSetting


class RuntimeSettingsService:
    """
    Обеспечивает доступ к таблице runtime_settings, которая хранит
    актуальные настройки, применяемые без перезапуска приложения.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _serialize_value(value: Any) -> Dict[str, Any]:
        """Преобразует Python-значение в JSON-совместимый формат с указанием типа."""
        value_type = type(value).__name__
        if value is None:
            return {"value": None, "type": "none"}
        if isinstance(value, bool):
            return {"value": value, "type": "bool"}
        if isinstance(value, int):
            return {"value": value, "type": "int"}
        if isinstance(value, float):
            return {"value": value, "type": "float"}
        if isinstance(value, (dict, list)):
            return {"value": value, "type": value_type}
        # Преобразуем остальные типы к строке
        return {"value": str(value), "type": "str"}

    @staticmethod
    def _deserialize_value(payload: Dict[str, Any]) -> Any:
        """Преобразует значение из JSON-формата в Python-тип."""
        if not payload:
            return None
        value_type = payload.get("type")
        value = payload.get("value")
        if value_type == "none":
            return None
        if value_type == "bool":
            return bool(value)
        if value_type == "int":
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
        if value_type == "float":
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
        # Для dict/list оставляем как есть
        return value

    async def get_all(self) -> Dict[str, Any]:
        """Возвращает все runtime-настройки как словарь."""
        result = await self.session.execute(select(RuntimeSetting))
        settings = {}
        for row in result.scalars():
            settings[row.key] = self._deserialize_value(row.value)
        return settings

    async def get(self, key: str) -> Any:
        """Получает конкретную настройку."""
        result = await self.session.execute(
            select(RuntimeSetting).where(RuntimeSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        if not setting:
            return None
        return self._deserialize_value(setting.value)

    async def set_value(
        self,
        key: str,
        value: Any,
        source: str = "runtime",
        requires_restart: bool = False,
    ) -> None:
        """Создает или обновляет настройку."""
        payload = self._serialize_value(value)
        stmt = insert(RuntimeSetting).values(
            key=key,
            value=payload,
            source=source,
            requires_restart=requires_restart,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={
                "value": stmt.excluded.value,
                "source": stmt.excluded.source,
                "requires_restart": stmt.excluded.requires_restart,
            },
        )
        await self.session.execute(stmt)

    async def set_values(
        self,
        values: Dict[str, Any],
        source: str = "runtime",
        requires_restart: bool = False,
    ) -> None:
        """Массовое обновление настроек."""
        for key, value in values.items():
            await self.set_value(key, value, source=source, requires_restart=requires_restart)

    async def delete_keys(self, keys: Iterable[str]) -> None:
        """Удаляет указанные настройки из runtime-таблицы."""
        if not keys:
            return
        await self.session.execute(
            delete(RuntimeSetting).where(RuntimeSetting.key.in_(list(keys)))
        )

    async def clear_all(self) -> None:
        """Очищает все runtime-настройки."""
        await self.session.execute(delete(RuntimeSetting))


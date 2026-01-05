"""
Сервис управления доступом к боту (белый и чёрный списки пользователей).
Версия для работы с PostgreSQL через SQLAlchemy.
"""

from __future__ import annotations

from typing import Optional, Tuple
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session
from src.db.models import AccessControl, AccessListEntry, ListType, EntryType


class AccessControlService:
    """
    Сервис для проверки доступа и управления списками пользователей.
    Работает с PostgreSQL через SQLAlchemy.
    """

    def __init__(self):
        """Инициализация сервиса (без параметров, так как используется БД)"""
        pass

    async def _get_config(self, session: AsyncSession) -> AccessControl:
        """Получает или создаёт конфигурацию доступа"""
        result = await session.execute(select(AccessControl).where(AccessControl.id == 1))
        config = result.scalar_one_or_none()
        
        if config is None:
            config = AccessControl(id=1, whitelist_enabled=False, blacklist_enabled=False)
            session.add(config)
            await session.commit()
            await session.refresh(config)
        
        return config

    async def _get_entries(self, session: AsyncSession, list_type: ListType) -> Tuple[list[int], list[str]]:
        """Получает записи списка (IDs и usernames)"""
        result = await session.execute(
            select(AccessListEntry).where(
                AccessListEntry.access_control_id == 1,
                AccessListEntry.list_type == list_type
            )
        )
        entries = result.scalars().all()
        
        ids = []
        usernames = []
        for entry in entries:
            if entry.entry_type == EntryType.ID:
                try:
                    ids.append(int(entry.value))
                except ValueError:
                    pass
            elif entry.entry_type == EntryType.USERNAME:
                usernames.append(entry.value.lower())
        
        return ids, usernames

    async def is_allowed(self, user_id: int, username: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Проверяет, разрешён ли доступ пользователю.

        Логика:
        - если включён белый список и пользователь НЕ в белом — доступ запрещён;
        - затем, если включён чёрный список и пользователь в чёрном — доступ запрещён;
        - во всех остальных случаях доступ разрешён.

        При одновременном включении обоих списков приоритет у чёрного.

        Возвращает пару (allowed, reason), где reason — текстовое пояснение
        причины отказа (или None, если доступ разрешён).
        """
        async for session in get_session():
            config = await self._get_config(session)
            uname = (username or "").lstrip("@").lower()
            
            whitelist_ids, whitelist_usernames = await self._get_entries(session, ListType.WHITELIST)
            blacklist_ids, blacklist_usernames = await self._get_entries(session, ListType.BLACKLIST)
            
            in_white = (user_id in whitelist_ids) or (uname and uname in whitelist_usernames)
            in_black = (user_id in blacklist_ids) or (uname and uname in blacklist_usernames)
            
            # Если включён белый список, но пользователь не найден в белом — запрещаем
            if config.whitelist_enabled and not in_white:
                return False, "Вашему аккаунту не предоставлен доступ."
            
            # Если включён чёрный список и пользователь в нём — запрещаем (приоритет выше)
            if config.blacklist_enabled and in_black:
                return False, "Вашему аккаунту запрещён доступ."
            
            return True, None

    async def set_whitelist_enabled(self, enabled: bool) -> None:
        """Включает или выключает белый список"""
        async for session in get_session():
            config = await self._get_config(session)
            config.whitelist_enabled = bool(enabled)
            await session.commit()
            break

    async def set_blacklist_enabled(self, enabled: bool) -> None:
        """Включает или выключает чёрный список"""
        async for session in get_session():
            config = await self._get_config(session)
            config.blacklist_enabled = bool(enabled)
            await session.commit()
            break

    async def add_to_whitelist(self, ids: list[int], usernames: list[str]) -> None:
        """Добавляет пользователей в белый список"""
        async for session in get_session():
            config = await self._get_config(session)
            
            # Добавляем IDs
            for user_id in ids:
                result = await session.execute(
                    select(AccessListEntry).where(
                        AccessListEntry.access_control_id == 1,
                        AccessListEntry.list_type == ListType.WHITELIST,
                        AccessListEntry.entry_type == EntryType.ID,
                        AccessListEntry.value == str(user_id)
                    )
                )
                if result.scalar_one_or_none() is None:
                    entry = AccessListEntry(
                        access_control_id=1,
                        list_type=ListType.WHITELIST,
                        entry_type=EntryType.ID,
                        value=str(user_id),
                    )
                    session.add(entry)
            
            # Добавляем usernames
            for name in usernames:
                clean = name.lstrip("@").lower()
                if clean:
                    result = await session.execute(
                        select(AccessListEntry).where(
                            AccessListEntry.access_control_id == 1,
                            AccessListEntry.list_type == ListType.WHITELIST,
                            AccessListEntry.entry_type == EntryType.USERNAME,
                            AccessListEntry.value == clean
                        )
                    )
                    if result.scalar_one_or_none() is None:
                        entry = AccessListEntry(
                            access_control_id=1,
                            list_type=ListType.WHITELIST,
                            entry_type=EntryType.USERNAME,
                            value=clean,
                        )
                        session.add(entry)
            
            await session.commit()
            break

    async def remove_from_whitelist(self, ids: list[int], usernames: list[str]) -> None:
        """Удаляет пользователей из белого списка"""
        async for session in get_session():
            # Удаляем IDs
            for user_id in ids:
                await session.execute(
                    delete(AccessListEntry).where(
                        AccessListEntry.access_control_id == 1,
                        AccessListEntry.list_type == ListType.WHITELIST,
                        AccessListEntry.entry_type == EntryType.ID,
                        AccessListEntry.value == str(user_id)
                    )
                )
            
            # Удаляем usernames
            to_remove = {name.lstrip("@").lower() for name in usernames if name.strip()}
            for clean in to_remove:
                await session.execute(
                    delete(AccessListEntry).where(
                        AccessListEntry.access_control_id == 1,
                        AccessListEntry.list_type == ListType.WHITELIST,
                        AccessListEntry.entry_type == EntryType.USERNAME,
                        AccessListEntry.value == clean
                    )
                )
            
            await session.commit()
            break

    async def add_to_blacklist(self, ids: list[int], usernames: list[str]) -> None:
        """Добавляет пользователей в чёрный список"""
        async for session in get_session():
            config = await self._get_config(session)
            
            # Добавляем IDs
            for user_id in ids:
                result = await session.execute(
                    select(AccessListEntry).where(
                        AccessListEntry.access_control_id == 1,
                        AccessListEntry.list_type == ListType.BLACKLIST,
                        AccessListEntry.entry_type == EntryType.ID,
                        AccessListEntry.value == str(user_id)
                    )
                )
                if result.scalar_one_or_none() is None:
                    entry = AccessListEntry(
                        access_control_id=1,
                        list_type=ListType.BLACKLIST,
                        entry_type=EntryType.ID,
                        value=str(user_id),
                    )
                    session.add(entry)
            
            # Добавляем usernames
            for name in usernames:
                clean = name.lstrip("@").lower()
                if clean:
                    result = await session.execute(
                        select(AccessListEntry).where(
                            AccessListEntry.access_control_id == 1,
                            AccessListEntry.list_type == ListType.BLACKLIST,
                            AccessListEntry.entry_type == EntryType.USERNAME,
                            AccessListEntry.value == clean
                        )
                    )
                    if result.scalar_one_or_none() is None:
                        entry = AccessListEntry(
                            access_control_id=1,
                            list_type=ListType.BLACKLIST,
                            entry_type=EntryType.USERNAME,
                            value=clean,
                        )
                        session.add(entry)
            
            await session.commit()
            break

    async def remove_from_blacklist(self, ids: list[int], usernames: list[str]) -> None:
        """Удаляет пользователей из чёрного списка"""
        async for session in get_session():
            # Удаляем IDs
            for user_id in ids:
                await session.execute(
                    delete(AccessListEntry).where(
                        AccessListEntry.access_control_id == 1,
                        AccessListEntry.list_type == ListType.BLACKLIST,
                        AccessListEntry.entry_type == EntryType.ID,
                        AccessListEntry.value == str(user_id)
                    )
                )
            
            # Удаляем usernames
            to_remove = {name.lstrip("@").lower() for name in usernames if name.strip()}
            for clean in to_remove:
                await session.execute(
                    delete(AccessListEntry).where(
                        AccessListEntry.access_control_id == 1,
                        AccessListEntry.list_type == ListType.BLACKLIST,
                        AccessListEntry.entry_type == EntryType.USERNAME,
                        AccessListEntry.value == clean
                    )
                )
            
            await session.commit()
            break

    async def get_summary(self) -> str:
        """Возвращает краткое текстовое описание текущих настроек доступа"""
        async for session in get_session():
            config = await self._get_config(session)
            whitelist_ids, whitelist_usernames = await self._get_entries(session, ListType.WHITELIST)
            blacklist_ids, blacklist_usernames = await self._get_entries(session, ListType.BLACKLIST)
            
            parts: list[str] = []
            parts.append(f"Белый список: {'включён' if config.whitelist_enabled else 'выключен'}")
            parts.append(f"Чёрный список: {'включён' if config.blacklist_enabled else 'выключен'}")
            parts.append(f"Белый список: {len(whitelist_ids)} ID, {len(whitelist_usernames)} username")
            parts.append(f"Чёрный список: {len(blacklist_ids)} ID, {len(blacklist_usernames)} username")
            
            return "\n".join(parts)

    async def dump_lists(self) -> str:
        """Возвращает подробное содержание списков для отображения админу"""
        async for session in get_session():
            config = await self._get_config(session)
            whitelist_ids, whitelist_usernames = await self._get_entries(session, ListType.WHITELIST)
            blacklist_ids, blacklist_usernames = await self._get_entries(session, ListType.BLACKLIST)
            
            lines: list[str] = []
            lines.append("🔐 <b>Текущие списки доступа</b>")
            lines.append("")
            lines.append(f"Белый список включён: <b>{'да' if config.whitelist_enabled else 'нет'}</b>")
            lines.append(f"Чёрный список включён: <b>{'да' if config.blacklist_enabled else 'нет'}</b>")
            lines.append("")
            
            if whitelist_ids or whitelist_usernames:
                lines.append("<b>Белый список</b>:")
                if whitelist_ids:
                    ids_str = ", ".join(str(x) for x in whitelist_ids)
                    lines.append(f"ID: <code>{ids_str}</code>")
                if whitelist_usernames:
                    names_str = ", ".join(f"@{x}" for x in whitelist_usernames)
                    lines.append(f"username: {names_str}")
            else:
                lines.append("<b>Белый список</b>: пусто")
            
            lines.append("")
            
            if blacklist_ids or blacklist_usernames:
                lines.append("<b>Чёрный список</b>:")
                if blacklist_ids:
                    ids_str = ", ".join(str(x) for x in blacklist_ids)
                    lines.append(f"ID: <code>{ids_str}</code>")
                if blacklist_usernames:
                    names_str = ", ".join(f"@{x}" for x in blacklist_usernames)
                    lines.append(f"username: {names_str}")
            else:
                lines.append("<b>Чёрный список</b>: пусто")
            
            return "\n".join(lines)

    async def get_whitelist_enabled(self) -> bool:
        """Возвращает статус включения белого списка (для совместимости с _config.whitelist_enabled)"""
        async for session in get_session():
            config = await self._get_config(session)
            return config.whitelist_enabled

    async def get_blacklist_enabled(self) -> bool:
        """Возвращает статус включения чёрного списка (для совместимости с _config.blacklist_enabled)"""
        async for session in get_session():
            config = await self._get_config(session)
            return config.blacklist_enabled


# Глобальный экземпляр сервиса
access_control_service = AccessControlService()


def is_admin_user(user_id: int, username: Optional[str]) -> bool:
    """
    Проверяет, является ли пользователь администратором бота.

    Источники прав:
        - ADMIN_CHAT_ID
        - ADMIN_GROUP_BOT (список ID через запятую)
    """
    from src.core.config import settings
    
    main_admin_raw = getattr(settings, "ADMIN_CHAT_ID", "") or ""
    main_admin: Optional[int] = None
    if main_admin_raw.strip().isdigit():
        try:
            main_admin = int(main_admin_raw.strip())
        except ValueError:
            main_admin = None

    grouped_raw = getattr(settings, "ADMIN_GROUP_BOT", "") or ""
    extra_ids: set[int] = set()
    for part in grouped_raw.split(","):
        token = part.strip()
        if not token or not token.isdigit():
            continue
        try:
            extra_ids.add(int(token))
        except ValueError:
            continue

    if main_admin is not None and user_id == main_admin:
        return True
    if user_id in extra_ids:
        return True

    return False


def parse_ids_and_usernames(raw: str) -> tuple[list[int], list[str]]:
    """
    Разбирает строку вида "123, @user, 456, user2" на списки ID и username.
    """
    ids: list[int] = []
    names: list[str] = []
    text = raw.replace(";", ",")
    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        if token.startswith("@"):
            token = token[1:]
        if token.isdigit():
            ids.append(int(token))
        else:
            names.append(token.lower())
    return ids, names

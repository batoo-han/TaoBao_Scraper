"""
Сервис управления доступом к боту (белый и чёрный списки пользователей).

Хранит настройки в JSON-файле `data/access_control.json` и предоставляет
удобный интерфейс для проверки прав доступа и изменения списков из бота.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Optional, Tuple

from src.core.config import settings


@dataclass
class AccessControlConfig:
    """
    Конфигурация белого и чёрного списков.

    Атрибуты:
        whitelist_enabled: включён ли белый список
        blacklist_enabled: включён ли чёрный список
        whitelist_ids: список Telegram ID, которым разрешён доступ
        whitelist_usernames: список username (без @), которым разрешён доступ
        blacklist_ids: список Telegram ID, которым запрещён доступ
        blacklist_usernames: список username (без @), которым запрещён доступ
    """

    whitelist_enabled: bool = False
    blacklist_enabled: bool = False
    whitelist_ids: list[int] = None  # type: ignore[assignment]
    whitelist_usernames: list[str] = None  # type: ignore[assignment]
    blacklist_ids: list[int] = None  # type: ignore[assignment]
    blacklist_usernames: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.whitelist_ids is None:
            self.whitelist_ids = []
        if self.whitelist_usernames is None:
            self.whitelist_usernames = []
        if self.blacklist_ids is None:
            self.blacklist_ids = []
        if self.blacklist_usernames is None:
            self.blacklist_usernames = []


class AccessControlService:
    """
    Сервис для проверки доступа и управления списками пользователей.
    """

    def __init__(self, storage_file: str = "data/access_control.json") -> None:
        self.storage_path = Path(storage_file)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = AccessControlConfig()
        self._load()

    # -------------------- работа с файлом --------------------
    def _load(self) -> None:
        """
        Загружает конфигурацию из JSON-файла, если он существует.
        """
        if not self.storage_path.exists():
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            # При ошибке загрузки начинаем с дефолтов
            return

        cfg = AccessControlConfig()
        cfg.whitelist_enabled = bool(raw.get("whitelist_enabled", False))
        cfg.blacklist_enabled = bool(raw.get("blacklist_enabled", False))
        cfg.whitelist_ids = [int(x) for x in raw.get("whitelist_ids", []) if isinstance(x, (int, str)) and str(x).isdigit()]
        cfg.blacklist_ids = [int(x) for x in raw.get("blacklist_ids", []) if isinstance(x, (int, str)) and str(x).isdigit()]

        def _norm_names(values) -> list[str]:
            result: list[str] = []
            for v in values or []:
                if not isinstance(v, str):
                    continue
                name = v.strip()
                if name.startswith("@"):
                    name = name[1:]
                if name:
                    result.append(name.lower())
            return result

        cfg.whitelist_usernames = _norm_names(raw.get("whitelist_usernames", []))
        cfg.blacklist_usernames = _norm_names(raw.get("blacklist_usernames", []))

        self._config = cfg

    def _save(self) -> None:
        """
        Сохраняет текущую конфигурацию в JSON-файл.
        """
        data = asdict(self._config)
        try:
            with self.storage_path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            # Ошибку сохранения не пробрасываем пользователю, но в DEBUG можно логировать
            if getattr(settings, "DEBUG_MODE", False):
                print("[AccessControl] Ошибка сохранения access_control.json")

    # -------------------- проверки доступа --------------------
    def is_allowed(self, user_id: int, username: Optional[str]) -> Tuple[bool, Optional[str]]:
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
        cfg = self._config
        uname = (username or "").lstrip("@").lower()

        in_white = (user_id in cfg.whitelist_ids) or (uname and uname in cfg.whitelist_usernames)
        in_black = (user_id in cfg.blacklist_ids) or (uname and uname in cfg.blacklist_usernames)

        # Если включён белый список, но пользователь не найден в белом — запрещаем
        if cfg.whitelist_enabled and not in_white:
            return False, "Вашему аккаунту не предоставлен доступ."

        # Если включён чёрный список и пользователь в нём — запрещаем (приоритет выше)
        if cfg.blacklist_enabled and in_black:
            return False, "Вашему аккаунту запрещён доступ."

        return True, None

    # -------------------- включение / выключение --------------------
    def set_whitelist_enabled(self, enabled: bool) -> None:
        self._config.whitelist_enabled = bool(enabled)
        self._save()

    def set_blacklist_enabled(self, enabled: bool) -> None:
        self._config.blacklist_enabled = bool(enabled)
        self._save()

    # -------------------- изменение списков --------------------
    def add_to_whitelist(self, ids: list[int], usernames: list[str]) -> None:
        cfg = self._config
        for uid in ids:
            if uid not in cfg.whitelist_ids:
                cfg.whitelist_ids.append(uid)
        for name in usernames:
            clean = name.lstrip("@").lower()
            if clean and clean not in cfg.whitelist_usernames:
                cfg.whitelist_usernames.append(clean)
        self._save()

    def remove_from_whitelist(self, ids: list[int], usernames: list[str]) -> None:
        cfg = self._config
        cfg.whitelist_ids = [uid for uid in cfg.whitelist_ids if uid not in ids]
        to_remove = {name.lstrip("@").lower() for name in usernames if name.strip()}
        cfg.whitelist_usernames = [name for name in cfg.whitelist_usernames if name not in to_remove]
        self._save()

    def add_to_blacklist(self, ids: list[int], usernames: list[str]) -> None:
        cfg = self._config
        for uid in ids:
            if uid not in cfg.blacklist_ids:
                cfg.blacklist_ids.append(uid)
        for name in usernames:
            clean = name.lstrip("@").lower()
            if clean and clean not in cfg.blacklist_usernames:
                cfg.blacklist_usernames.append(clean)
        self._save()

    def remove_from_blacklist(self, ids: list[int], usernames: list[str]) -> None:
        cfg = self._config
        cfg.blacklist_ids = [uid for uid in cfg.blacklist_ids if uid not in ids]
        to_remove = {name.lstrip("@").lower() for name in usernames if name.strip()}
        cfg.blacklist_usernames = [name for name in cfg.blacklist_usernames if name not in to_remove]
        self._save()

    # -------------------- информация для админа --------------------
    def get_summary(self) -> str:
        """
        Возвращает краткое текстовое описание текущих настроек доступа.
        """
        cfg = self._config
        parts: list[str] = []
        parts.append(f"Белый список: {'включён' if cfg.whitelist_enabled else 'выключен'}")
        parts.append(f"Чёрный список: {'включён' if cfg.blacklist_enabled else 'выключен'}")
        parts.append(
            f"Белый список: {len(cfg.whitelist_ids)} ID, {len(cfg.whitelist_usernames)} username"
        )
        parts.append(
            f"Чёрный список: {len(cfg.blacklist_ids)} ID, {len(cfg.blacklist_usernames)} username"
        )
        return "\n".join(parts)

    def dump_lists(self) -> str:
        """
        Возвращает подробное содержание списков для отображения админу.
        """
        cfg = self._config
        lines: list[str] = []
        lines.append("🔐 <b>Текущие списки доступа</b>")
        lines.append("")
        lines.append(f"Белый список включён: <b>{'да' if cfg.whitelist_enabled else 'нет'}</b>")
        lines.append(f"Чёрный список включён: <b>{'да' if cfg.blacklist_enabled else 'нет'}</b>")
        lines.append("")
        if cfg.whitelist_ids or cfg.whitelist_usernames:
            lines.append("<b>Белый список</b>:")
            if cfg.whitelist_ids:
                ids_str = ", ".join(str(x) for x in cfg.whitelist_ids)
                lines.append(f"ID: <code>{ids_str}</code>")
            if cfg.whitelist_usernames:
                names_str = ", ".join(f"@{x}" for x in cfg.whitelist_usernames)
                lines.append(f"username: {names_str}")
        else:
            lines.append("<b>Белый список</b>: пусто")

        lines.append("")

        if cfg.blacklist_ids or cfg.blacklist_usernames:
            lines.append("<b>Чёрный список</b>:")
            if cfg.blacklist_ids:
                ids_str = ", ".join(str(x) for x in cfg.blacklist_ids)
                lines.append(f"ID: <code>{ids_str}</code>")
            if cfg.blacklist_usernames:
                names_str = ", ".join(f"@{x}" for x in cfg.blacklist_usernames)
                lines.append(f"username: {names_str}")
        else:
            lines.append("<b>Чёрный список</b>: пусто")

        return "\n".join(lines)


# Глобальный экземпляр сервиса для использования в боте
access_control_service = AccessControlService()


def is_admin_user(user_id: int, username: Optional[str]) -> bool:
    """
    Проверяет, является ли пользователь администратором бота.

    Источники прав:
        - ADMIN_CHAT_ID
        - ADMIN_GROUP_BOT (список ID через запятую)
    """
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



"""
Единая настройка логирования для бота и админ-панели.
"""

from __future__ import annotations

import logging
import logging.config
import os
import time
from pathlib import Path
from typing import Iterable

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "app.log"
MAX_TOTAL_SIZE = 100 * 1024 * 1024  # 100 МБ
MAX_FILE_AGE_DAYS = 30


class SuppressWatchFilesFilter(logging.Filter):
    """
    Фильтр удаляет шумные сообщения вида «1 change detected»,
    которые возникают при работе hot-reload.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        message = record.getMessage().lower()
        return "change detected" not in message


def setup_logging(level: str = "INFO") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "suppress_watchfiles": {
                "()": "src.core.logging_config.SuppressWatchFilesFilter",
            },
        },
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "short": {
                "format": "%(levelname)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "short",
                "filters": ["suppress_watchfiles"],
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "standard",
                "filename": str(LOG_FILE),
                "maxBytes": 5 * 1024 * 1024,  # 5 МБ на файл
                "backupCount": 20,
                "encoding": "utf-8",
                "delay": True,
                "filters": ["suppress_watchfiles"],
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": level,
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["console", "file"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console", "file"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console", "file"],
                "level": level,
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "handlers": ["file"],
                "level": "WARNING",
                "propagate": False,
            },
            "watchfiles": {
                "handlers": ["console", "file"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(config)
    cleanup_logs()


def cleanup_logs() -> None:
    """Удаляет старые логи и ограничивает общий объём."""
    now = time.time()
    max_age_seconds = MAX_FILE_AGE_DAYS * 24 * 60 * 60

    files = sorted(
        LOG_DIR.glob("app.log*"),
        key=lambda f: f.stat().st_mtime if f.exists() else 0,
        reverse=True,
    )

    total_size = 0
    for file in files:
        try:
            stat = file.stat()
        except FileNotFoundError:
            continue

        # Удаляем слишком старые файлы
        if now - stat.st_mtime > max_age_seconds:
            file.unlink(missing_ok=True)
            continue

        total_size += stat.st_size
        if total_size > MAX_TOTAL_SIZE:
            file.unlink(missing_ok=True)


def list_log_files() -> Iterable[Path]:
    """Возвращает список файлов логов (для загрузки/отображения)."""
    if not LOG_DIR.exists():
        return []
    return LOG_DIR.glob("app.log*")


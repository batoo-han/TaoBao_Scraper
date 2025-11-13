"""
Управление перезапуском сервисов (бот + админ-панель).
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class RestartManager:
    """
    Планировщик перезапуска сервисов.

    Выполняет перезапуск через внешний скрипт scripts/restart_services.py,
    чтобы можно было корректно завершить текущие процессы и поднять новый экземпляр.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._restart_scheduled = False

    async def schedule_restart(self, delay: float = 3.0) -> None:
        """Планирует перезапуск (если ещё не запланирован)."""
        async with self._lock:
            if self._restart_scheduled:
                logger.info("Перезапуск уже запланирован, пропускаем повторный запрос.")
                return
            self._restart_scheduled = True
            asyncio.create_task(self._restart_after_delay(delay))

    async def _restart_after_delay(self, delay: float) -> None:
        await asyncio.sleep(delay)
        try:
            self._invoke_restart_script()
        finally:
            # После запуска скрипта сбрасываем флаг — на случай повторных попыток
            async with self._lock:
                self._restart_scheduled = False

    def _invoke_restart_script(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        script_path = project_root / "scripts" / "restart_services.py"

        if not script_path.exists():
            logger.error("Скрипт перезапуска не найден: %s", script_path)
            return

        cmd = [sys.executable, str(script_path)]
        kwargs = {
            "cwd": str(project_root),
            "env": os.environ.copy(),
        }

        if platform.system() == "Windows":
            # Используем CREATE_NO_WINDOW для скрытия окна консоли
            # CREATE_NEW_PROCESS_GROUP нужен для независимой группы процессов
            CREATE_NO_WINDOW = 0x08000000  # Константа из Windows API
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW  # type: ignore[attr-defined]
            kwargs["creationflags"] = creation_flags
            # Перенаправляем stdout и stderr, чтобы не было видно вывода
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        else:
            kwargs["start_new_session"] = True
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL

        try:
            subprocess.Popen(cmd, **kwargs)
            logger.info("Запущен внешний скрипт перезапуска: %s", script_path)
        except Exception:
            logger.exception("Не удалось запустить скрипт перезапуска")


restart_manager = RestartManager()


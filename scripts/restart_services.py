"""
Скрипт для мягкого перезапуска бота и админ-панели.

1. Ждёт несколько секунд, чтобы API успел вернуть ответ.
2. Завершает текущие процессы (run_all.py, main.py, uvicorn и т.д.).
3. Запускает свежий экземпляр run_all.py.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List

import psutil

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("restart_services")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _find_processes_to_kill(current_pid: int) -> List[psutil.Process]:
    targets = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            name = (proc.info["name"] or "").lower()
            cmdline = proc.info.get("cmdline") or []
            cmdline_str = " ".join(cmdline).lower()

            if "python" not in name and "python" not in cmdline_str:
                continue

            if any(script in cmdline_str for script in ["run_all.py", "main.py", "uvicorn", "run_admin.py"]):
                targets.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return targets


def kill_processes(processes: List[psutil.Process]) -> None:
    for proc in processes:
        try:
            logger.info("Завершаем PID %s (%s)", proc.pid, " ".join(proc.cmdline()[:3]))
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    gone, alive = psutil.wait_procs(processes, timeout=5)
    for proc in alive:
        try:
            logger.info("Принудительное завершение PID %s", proc.pid)
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def start_new_instance() -> None:
    run_all_path = PROJECT_ROOT / "run_all.py"
    if not run_all_path.exists():
        logger.error("Не найден run_all.py по пути %s", run_all_path)
        return

    cmd = [sys.executable, str(run_all_path)]
    kwargs = {
        "cwd": str(PROJECT_ROOT),
        "env": os.environ.copy(),
    }

    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen(cmd, **kwargs)
        logger.info("Новый экземпляр run_all.py запущен")
    except Exception:
        logger.exception("Не удалось запустить run_all.py")


def main() -> None:
    current_pid = os.getpid()
    logger.info("Инициация перезапуска сервисов...")
    time.sleep(3)

    processes = _find_processes_to_kill(current_pid)
    if processes:
        kill_processes(processes)
    else:
        logger.info("Процессы для завершения не найдены (возможно, службы уже остановлены).")

    time.sleep(1)
    start_new_instance()
    logger.info("Перезапуск завершён.")


if __name__ == "__main__":
    main()


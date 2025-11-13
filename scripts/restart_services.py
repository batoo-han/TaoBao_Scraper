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

# Настраиваем логирование в файл
log_file = Path(__file__).resolve().parents[1] / "logs" / "restart.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("restart_services")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _find_processes_to_kill(current_pid: int) -> List[psutil.Process]:
    """
    Находит все процессы, связанные с ботом и админ-панелью.
    Использует ту же логику, что и check_bot_running() в run_all.py.
    """
    targets = []
    project_dir = str(PROJECT_ROOT)
    current_script = str(PROJECT_ROOT / "scripts" / "restart_services.py")
    
    # Системные процессы Windows, которые не нужно завершать
    system_processes = {"conhost.exe", "dwm.exe", "winlogon.exe", "csrss.exe", "smss.exe"}
    
    for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            
            name = (proc.info["name"] or "").lower()
            
            # Пропускаем системные процессы Windows
            if name in system_processes:
                continue
            
            # Пропускаем сам скрипт перезапуска (все его экземпляры)
            cmdline_for_check = " ".join(proc.info.get("cmdline") or []).lower()
            if "restart_services.py" in cmdline_for_check:
                continue
            
            if "python" not in name:
                continue
            
            cmdline = proc.info.get("cmdline") or []
            if not cmdline:
                continue
            
            cmdline_str = " ".join(cmdline)
            cmdline_lower = cmdline_str.lower()
            
            # Ищем процессы run_all.py, main.py или uvicorn
            script_path = None
            script_name = None
            
            if "run_all.py" in cmdline_lower:
                for arg in cmdline:
                    if "run_all.py" in arg.lower():
                        script_path = str(Path(arg).resolve())
                        script_name = "run_all.py"
                        break
            elif "main.py" in cmdline_lower:
                for arg in cmdline:
                    if "main.py" in arg.lower():
                        script_path = str(Path(arg).resolve())
                        script_name = "main.py"
                        break
            elif "uvicorn" in cmdline_lower and "src.admin.main:app" in cmdline_str:
                # Процесс uvicorn для админ-панели
                script_name = "uvicorn"
                script_path = None
                for arg in cmdline:
                    if "admin" in arg.lower() or "uvicorn" in arg.lower():
                        script_path = arg
                        break
            
            # Проверяем, что скрипт находится в директории проекта
            if script_name:
                if script_path:
                    try:
                        script_dir = str(Path(script_path).parent)
                        # Проверяем, что скрипт в директории проекта
                        if project_dir.lower() in script_dir.lower() or script_dir.lower() in project_dir.lower():
                            if script_path != current_script:
                                targets.append(proc)
                    except Exception:
                        # Если не удалось определить путь, но это точно наш процесс
                        if script_name in ["run_all.py", "main.py"]:
                            targets.append(proc)
                else:
                    # Для uvicorn проверяем по содержимому cmdline
                    if "src.admin.main" in cmdline_str or "admin" in cmdline_lower:
                        targets.append(proc)
            
            # Также ищем дочерние процессы multiprocessing
            # (они могут не иметь run_all.py в cmdline, но быть дочерними)
            try:
                parent = proc.parent()
                if parent and parent.pid != current_pid:
                    parent_cmdline = parent.cmdline() if hasattr(parent, 'cmdline') else []
                    parent_cmdline_str = " ".join(parent_cmdline).lower()
                    if "run_all.py" in parent_cmdline_str or "main.py" in parent_cmdline_str:
                        if proc not in targets:
                            targets.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    # Добавляем все дочерние процессы для найденных процессов run_all.py
    additional_targets = []
    for proc in targets:
        try:
            # Для процессов run_all.py ищем все дочерние процессы рекурсивно
            if "run_all.py" in " ".join(proc.cmdline()).lower():
                try:
                    children = proc.children(recursive=True)
                    for child in children:
                        if child.pid != current_pid and child not in targets:
                            additional_targets.append(child)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Объединяем и убираем дубликаты
    all_targets = targets + additional_targets
    seen_pids = set()
    unique_targets = []
    for proc in all_targets:
        try:
            if proc.pid not in seen_pids and proc.pid != current_pid:
                seen_pids.add(proc.pid)
                unique_targets.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    return unique_targets


def kill_processes(processes: List[psutil.Process]) -> None:
    """Завершает процессы мягко, затем принудительно при необходимости."""
    if not processes:
        return
    
    logger.info("Найдено %d процессов для завершения:", len(processes))
    for proc in processes:
        try:
            cmdline_preview = " ".join(proc.cmdline()[:3]) if proc.cmdline() else "unknown"
            logger.info("  - PID %s: %s", proc.pid, cmdline_preview)
        except:
            logger.info("  - PID %s: (не удалось получить информацию)", proc.pid)
    
    # Сортируем: сначала дочерние процессы (те, у которых есть родитель в списке), потом родительские
    process_dict = {proc.pid: proc for proc in processes}
    child_processes = []
    parent_processes = []
    
    for proc in processes:
        try:
            parent = proc.parent()
            if parent and parent.pid in process_dict:
                child_processes.append(proc)
            else:
                parent_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            parent_processes.append(proc)
    
    # Сначала завершаем дочерние, потом родительские
    ordered_processes = child_processes + parent_processes
    
    # Сначала пытаемся мягко завершить все процессы
    for proc in ordered_processes:
        try:
            cmdline_preview = " ".join(proc.cmdline()[:3]) if proc.cmdline() else "unknown"
            logger.info("Завершаем PID %s (%s)", proc.pid, cmdline_preview)
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Ждем завершения с таймаутом
    gone, alive = psutil.wait_procs(ordered_processes, timeout=10)
    
    if gone:
        logger.info("Мягко завершено %d процессов", len(gone))
    
    # Принудительно завершаем оставшиеся
    if alive:
        logger.info("Принудительно завершаем %d процессов", len(alive))
        for proc in alive:
            try:
                logger.info("Принудительное завершение PID %s", proc.pid)
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # Ждем еще немного для принудительно завершенных
        psutil.wait_procs(alive, timeout=5)


def start_new_instance() -> None:
    run_all_path = PROJECT_ROOT / "run_all.py"
    if not run_all_path.exists():
        logger.error("Не найден run_all.py по пути %s", run_all_path)
        raise FileNotFoundError(f"run_all.py не найден: {run_all_path}")

    cmd = [sys.executable, str(run_all_path)]
    logger.info("Команда запуска: %s", " ".join(cmd))
    logger.info("Рабочая директория: %s", PROJECT_ROOT)
    logger.info("Python интерпретатор: %s", sys.executable)
    
    kwargs = {
        "cwd": str(PROJECT_ROOT),
        "env": os.environ.copy(),
    }

    # Перенаправляем вывод в файл лога для отладки
    log_file_path = PROJECT_ROOT / "logs" / "run_all_output.log"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        log_file_handle = open(log_file_path, "a", encoding="utf-8")
    except Exception as e:
        logger.warning("Не удалось открыть файл лога для run_all.py: %s", e)
        log_file_handle = subprocess.DEVNULL

    if os.name == "nt":
        # Используем CREATE_NO_WINDOW для скрытия окна консоли
        CREATE_NO_WINDOW = 0x08000000  # Константа из Windows API
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | CREATE_NO_WINDOW
        kwargs["creationflags"] = creation_flags
        # Перенаправляем stdout и stderr в файл лога
        kwargs["stdout"] = log_file_handle
        kwargs["stderr"] = log_file_handle
    else:
        kwargs["start_new_session"] = True
        kwargs["stdout"] = log_file_handle
        kwargs["stderr"] = log_file_handle

    try:
        process = subprocess.Popen(cmd, **kwargs)
        logger.info("Новый экземпляр run_all.py запущен (PID: %s)", process.pid)
        logger.info("Вывод процесса будет записан в: %s", log_file_path)
    except Exception as e:
        logger.exception("Не удалось запустить run_all.py: %s", e)
        if log_file_handle != subprocess.DEVNULL:
            try:
                log_file_handle.close()
            except:
                pass
        raise


def main() -> None:
    current_pid = os.getpid()
    logger.info("Инициация перезапуска сервисов (PID скрипта: %d)...", current_pid)
    
    # Получаем информацию о родительском процессе для отладки
    try:
        parent = psutil.Process(current_pid).parent()
        if parent:
            parent_cmdline = " ".join(parent.cmdline()[:3]) if parent.cmdline() else "unknown"
            logger.info("Родительский процесс (PID %d): %s", parent.pid, parent_cmdline)
    except Exception:
        pass
    
    time.sleep(3)

    # Находим и завершаем процессы
    logger.info("Поиск процессов для завершения...")
    processes = _find_processes_to_kill(current_pid)
    
    # Исключаем родительский процесс, если это не run_all.py или main.py
    try:
        parent = psutil.Process(current_pid).parent()
        if parent:
            parent_cmdline = " ".join(parent.cmdline() or []).lower()
            # Если родительский процесс - это не run_all.py или main.py, исключаем его из списка
            if "run_all.py" not in parent_cmdline and "main.py" not in parent_cmdline:
                processes = [p for p in processes if p.pid != parent.pid]
                if parent.pid in [p.pid for p in processes]:
                    logger.info("Исключен родительский процесс (PID %d) из списка завершения", parent.pid)
    except Exception:
        pass
    
    # Финальная проверка: исключаем сам скрипт из списка
    processes = [p for p in processes if p.pid != current_pid]
    
    if processes:
        logger.info("Найдено %d процессов для завершения", len(processes))
        kill_processes(processes)
    else:
        logger.info("Процессы для завершения не найдены (возможно, службы уже остановлены).")

    # Дополнительно ожидаем полного завершения всех процессов
    max_attempts = 10
    for attempt in range(max_attempts):
        remaining = _find_processes_to_kill(current_pid)
        if not remaining:
            logger.info("Все процессы успешно завершены.")
            break
        logger.info("Ожидаем завершение %d процессов (попытка %d/%d)...", len(remaining), attempt + 1, max_attempts)
        time.sleep(2)
        
        # Если процессы все еще живы после нескольких попыток, пытаемся принудительно завершить
        if attempt >= 3:
            logger.warning("Процессы все еще активны, пытаемся принудительно завершить...")
            for proc in remaining:
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            time.sleep(1)

    # Финальная проверка
    final_check = _find_processes_to_kill(current_pid)
    if final_check:
        logger.warning("ВНИМАНИЕ: %d процессов все еще активны после всех попыток завершения!", len(final_check))
        for proc in final_check:
            try:
                logger.warning("  - PID %s: %s", proc.pid, " ".join(proc.cmdline()[:3]) if proc.cmdline() else "unknown")
            except:
                pass
    else:
        logger.info("Все процессы успешно завершены, запускаем новый экземпляр...")

    time.sleep(2)  # Дополнительная пауза перед запуском нового экземпляра
    
    try:
        logger.info("Запуск нового экземпляра run_all.py...")
        start_new_instance()
        logger.info("Новый экземпляр запущен успешно.")
    except Exception as e:
        logger.error("ОШИБКА при запуске нового экземпляра: %s", e, exc_info=True)
        raise
    
    logger.info("Перезапуск завершён.")


if __name__ == "__main__":
    main()


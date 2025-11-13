"""
Запуск бота и админ-панели вместе.

Использование:
    python run_all.py
"""

import asyncio
import logging
import multiprocessing
import signal
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.core.logging_config import setup_logging
from src.core.config import settings

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)


def run_bot():
    """Запускает Telegram бота."""
    import asyncio
    from main import main
    
    logger.info("🚀 Запуск Telegram бота...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка бота...")
    except Exception as e:
        logger.error(f"Ошибка в боте: {e}", exc_info=True)


def run_admin():
    """Запускает админ-панель."""
    import uvicorn
    
    logger.info(f"🔧 Запуск админ-панели на порту {settings.ADMIN_PANEL_PORT}...")
    try:
        uvicorn.run(
            "src.admin.main:app",
            host="0.0.0.0",
            port=settings.ADMIN_PANEL_PORT,
            reload=settings.DEBUG_MODE,
            log_level="info",
            log_config=None,
        )
    except KeyboardInterrupt:
        logger.info("Остановка админ-панели...")
    except Exception as e:
        logger.error(f"Ошибка в админ-панели: {e}", exc_info=True)


def check_bot_running():
    """Проверяет, не запущен ли уже бот."""
    try:
        import psutil
        import os
        
        current_pid = os.getpid()
        current_script = os.path.abspath(__file__)
        project_dir = os.path.dirname(current_script)
        found_processes = []
        
        # Ищем процессы Python, которые могут быть ботом
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                if proc.info['pid'] == current_pid:
                    continue
                
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline', [])
                    if not cmdline:
                        continue
                    
                    cmdline_str = ' '.join(cmdline)
                    script_path = None
                    script_name = None
                    
                    # Проверяем, запущен ли main.py или run_all.py
                    if 'main.py' in cmdline_str:
                        # Ищем путь к main.py
                        for arg in cmdline:
                            if 'main.py' in arg:
                                script_path = os.path.abspath(arg)
                                script_name = 'main.py'
                                break
                    elif 'run_all.py' in cmdline_str:
                        # Ищем путь к run_all.py
                        for arg in cmdline:
                            if 'run_all.py' in arg:
                                script_path = os.path.abspath(arg)
                                script_name = 'run_all.py'
                                break
                    
                    # Проверяем, что скрипт находится в директории проекта и это не текущий процесс
                    if script_path and script_name:
                        script_dir = os.path.dirname(script_path)
                        # Проверяем, что скрипт в той же директории проекта
                        try:
                            if os.path.commonpath([script_dir, project_dir]) == project_dir and script_path != current_script:
                                found_processes.append({
                                    'pid': proc.info['pid'],
                                    'script': script_name,
                                    'path': script_path,
                                    'cmdline': cmdline,
                                    'create_time': proc.info.get('create_time', 0)
                                })
                        except ValueError:
                            # Пути на разных дисках (Windows)
                            if script_path != current_script:
                                found_processes.append({
                                    'pid': proc.info['pid'],
                                    'script': script_name,
                                    'path': script_path,
                                    'cmdline': cmdline,
                                    'create_time': proc.info.get('create_time', 0)
                                })
            
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        if found_processes:
            logger.warning(f"⚠️  Обнаружено {len(found_processes)} запущенных процессов бота:")
            for proc_info in found_processes:
                import datetime
                create_time = datetime.datetime.fromtimestamp(proc_info['create_time']) if proc_info['create_time'] else None
                time_str = f" (запущен: {create_time.strftime('%H:%M:%S')})" if create_time else ""
                logger.warning(f"   PID: {proc_info['pid']} - {proc_info['script']}{time_str}")
                logger.warning(f"   Путь: {proc_info['path']}")
                logger.warning(f"   Команда: {' '.join(proc_info['cmdline'][:3])}...")
            return True
        
        return False
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"⚠️  Ошибка при проверке процессов: {e}")
        return False


def main():
    """Запускает бота и админ-панель в отдельных процессах."""
    logger.info("=" * 60)
    logger.info("Запуск Taobao Scraper Bot + Admin Panel")
    logger.info("=" * 60)
    logger.info(f"Порт админ-панели: {settings.ADMIN_PANEL_PORT}")
    logger.info("=" * 60)
    
    # Проверяем, не запущен ли уже бот
    try:
        if check_bot_running():
            logger.error("\n❌ Обнаружен запущенный экземпляр бота. Остановите его перед запуском.")
            logger.error("\n💡 Как остановить:")
            logger.error("   python scripts/find_bot_processes.py --kill")
            logger.error("   Или вручную:")
            logger.error("   Windows: taskkill /F /PID <PID>")
            logger.error("   Linux: kill <PID>")
            return
    except ImportError:
        # psutil не установлен, пропускаем проверку
        logger.warning("⚠️  psutil не установлен, проверка запущенных процессов пропущена")
        logger.warning("   Установите: pip install psutil")
    except Exception as e:
        logger.warning(f"⚠️  Не удалось проверить запущенные процессы: {e}")
    
    # Создаем процессы
    bot_process = multiprocessing.Process(target=run_bot, name="Bot")
    admin_process = multiprocessing.Process(target=run_admin, name="Admin")
    
    # Обработчик сигналов для корректного завершения
    def signal_handler(sig, frame):
        logger.info("\nПолучен сигнал завершения. Останавливаем процессы...")
        bot_process.terminate()
        admin_process.terminate()
        bot_process.join(timeout=5)
        admin_process.join(timeout=5)
        if bot_process.is_alive():
            bot_process.kill()
        if admin_process.is_alive():
            admin_process.kill()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Запускаем процессы
        bot_process.start()
        admin_process.start()
        
        logger.info("✅ Бот и админ-панель запущены!")
        logger.info(f"   Бот: работает (PID: {bot_process.pid})")
        logger.info(f"   Админ-панель: http://localhost:{settings.ADMIN_PANEL_PORT} (PID: {admin_process.pid})")
        logger.info("\nДля остановки нажмите Ctrl+C")
        
        # Ждем завершения процессов
        bot_process.join()
        admin_process.join()
        
    except KeyboardInterrupt:
        logger.info("\nОстановка по запросу пользователя...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        # Завершаем процессы
        if bot_process.is_alive():
            bot_process.terminate()
            bot_process.join(timeout=5)
            if bot_process.is_alive():
                bot_process.kill()
        
        if admin_process.is_alive():
            admin_process.terminate()
            admin_process.join(timeout=5)
            if admin_process.is_alive():
                admin_process.kill()
        
        logger.info("Все процессы остановлены.")


if __name__ == "__main__":
    main()


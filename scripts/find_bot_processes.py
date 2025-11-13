"""
Скрипт для поиска запущенных процессов бота.

Использование:
    python scripts/find_bot_processes.py
    python scripts/find_bot_processes.py --kill  # Завершить найденные процессы
"""

import sys
import os
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import psutil
except ImportError:
    print("❌ Ошибка: psutil не установлен")
    print("   Установите: pip install psutil")
    sys.exit(1)


def find_bot_processes():
    """Находит все запущенные процессы бота."""
    current_pid = os.getpid()
    current_script = os.path.abspath(__file__)
    project_dir = os.path.abspath(project_root)
    found_processes = []
    
    print("=" * 60)
    print("Поиск запущенных процессов бота")
    print("=" * 60)
    print(f"Текущий PID: {current_pid}")
    print(f"Директория проекта: {project_dir}")
    print("=" * 60)
    
    # Ищем процессы Python
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'cwd']):
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
                
                # Проверяем main.py
                if 'main.py' in cmdline_str:
                    for arg in cmdline:
                        if 'main.py' in arg:
                            script_path = os.path.abspath(arg)
                            script_name = 'main.py'
                            break
                
                # Проверяем run_all.py
                elif 'run_all.py' in cmdline_str:
                    for arg in cmdline:
                        if 'run_all.py' in arg:
                            script_path = os.path.abspath(arg)
                            script_name = 'run_all.py'
                            break
                
                # Проверяем, что скрипт находится в директории проекта
                if script_path and script_name:
                    script_dir = os.path.dirname(script_path)
                    if os.path.commonpath([script_dir, project_dir]) == project_dir:
                        # Проверяем, что это не текущий скрипт
                        if script_path != current_script:
                            import datetime
                            create_time = datetime.datetime.fromtimestamp(proc.info['create_time']) if proc.info.get('create_time') else None
                            
                            found_processes.append({
                                'pid': proc.info['pid'],
                                'script': script_name,
                                'path': script_path,
                                'cmdline': cmdline,
                                'create_time': create_time,
                                'cwd': proc.info.get('cwd', 'N/A')
                            })
        
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return found_processes


def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Поиск и завершение процессов бота')
    parser.add_argument('--kill', action='store_true', help='Завершить найденные процессы')
    args = parser.parse_args()
    
    found_processes = find_bot_processes()
    
    if not found_processes:
        print("\n✅ Запущенных процессов бота не найдено")
        return
    
    print(f"\n⚠️  Найдено {len(found_processes)} запущенных процессов бота:\n")
    
    for i, proc_info in enumerate(found_processes, 1):
        print(f"{i}. PID: {proc_info['pid']} - {proc_info['script']}")
        if proc_info['create_time']:
            print(f"   Запущен: {proc_info['create_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Путь: {proc_info['path']}")
        print(f"   Рабочая директория: {proc_info['cwd']}")
        print(f"   Команда: {' '.join(proc_info['cmdline'][:5])}...")
        print()
    
    if args.kill:
        print("=" * 60)
        confirm = input(f"⚠️  Завершить {len(found_processes)} процесс(ов)? (yes/no): ").strip().lower()
        if confirm in ['yes', 'y', 'да', 'д']:
            for proc_info in found_processes:
                try:
                    proc = psutil.Process(proc_info['pid'])
                    proc.terminate()
                    print(f"✅ Процесс {proc_info['pid']} ({proc_info['script']}) завершен")
                except psutil.NoSuchProcess:
                    print(f"⚠️  Процесс {proc_info['pid']} уже завершен")
                except psutil.AccessDenied:
                    print(f"❌ Нет прав для завершения процесса {proc_info['pid']}")
                except Exception as e:
                    print(f"❌ Ошибка при завершении процесса {proc_info['pid']}: {e}")
        else:
            print("Отменено")
    else:
        print("=" * 60)
        print("💡 Для завершения процессов используйте:")
        print("   python scripts/find_bot_processes.py --kill")
        print("\n   Или вручную:")
        for proc_info in found_processes:
            print(f"   taskkill /F /PID {proc_info['pid']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


"""
Скрипт для запуска миграций Alembic.
Использование: python scripts/migrate_db.py [upgrade|downgrade|current|history] [revision]
"""

import sys
import os
import asyncio
from pathlib import Path

# Добавляем корневую директорию в путь
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

# Устанавливаем переменную окружения для DATABASE_URL перед импортом settings
from src.core.config import settings
os.environ["DATABASE_URL"] = settings.DATABASE_URL

from alembic.config import Config
from alembic import command

def run_migration(command_name: str, revision: str = None):
    """Запускает команду Alembic"""
    alembic_cfg = Config(str(PROJECT_DIR / "alembic.ini"))
    
    if command_name == "upgrade":
        revision = revision or "head"
        command.upgrade(alembic_cfg, revision)
    elif command_name == "downgrade":
        if not revision:
            print("Для downgrade требуется указать ревизию")
            sys.exit(1)
        command.downgrade(alembic_cfg, revision)
    elif command_name == "current":
        command.current(alembic_cfg)
    elif command_name == "history":
        command.history(alembic_cfg)
    else:
        print(f"Неизвестная команда: {command_name}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python scripts/migrate_db.py <command> [revision]")
        print("Команды:")
        print("  upgrade [revision]  - применить миграции (по умолчанию head)")
        print("  downgrade [revision] - откатить миграции")
        print("  current            - показать текущую ревизию")
        print("  history            - показать историю миграций")
        sys.exit(1)
    
    command_name = sys.argv[1]
    revision = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        # Показываем параметры подключения
        print(f"Подключение к БД: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")
        print(f"Запуск миграции: {command_name} {revision or '(head)'}")
        
        # Запускаем миграцию (Alembic сам управляет подключением к БД)
        run_migration(command_name, revision)
        print(f"OK: Команда '{command_name}' выполнена успешно")
    except Exception as e:
        print(f"ERROR: Ошибка при выполнении миграции: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

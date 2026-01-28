# -*- coding: utf-8 -*-
"""
Одноразовый скрипт для починки enum-типа adminrole в PostgreSQL.

Проблема:
- В БД тип enum adminrole имеет значения 'ADMIN', 'USER' (верхний регистр).
- В ORM и API используются значения 'admin', 'user' (строчные).
- Это приводит к ошибкам вида:
  'admin' is not among the defined enum values. Enum name: adminrole. Possible values: ADMIN, USER

Решение:
- Переименовать значения enum в БД на строчные:
    ALTER TYPE adminrole RENAME VALUE 'ADMIN' TO 'admin';
    ALTER TYPE adminrole RENAME VALUE 'USER' TO 'user';

Скрипт безопасно пытается выполнить эти команды.
Если значения уже переименованы, будет выведено предупреждение, но ошибка не критична.

Запускать из корня проекта:

    .\\.venv\\Scripts\\Activate.ps1
    python scripts/fix_adminrole_enum.py
"""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import text

# Добавляем корень проекта в sys.path, чтобы импортировать пакет admin
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from admin.backend.database import engine  # noqa: E402


async def fix_enum_values() -> None:
    async with engine.begin() as conn:
        print("Проверка и переименование enum adminrole...")
        for old, new in (("ADMIN", "admin"), ("USER", "user")):
            try:
                await conn.execute(
                    text(f"ALTER TYPE adminrole RENAME VALUE '{old}' TO '{new}'")
                )
                print(f"Значение '{old}' переименовано в '{new}'.")
            except Exception as e:  # noqa: BLE001
                # Если значение уже переименовано или команда не применима,
                # выводим сообщение и продолжаем.
                print(f"Не удалось переименовать '{old}' -> '{new}': {e}")

    print("Готово. Перезапустите админ-панель (uvicorn).")


if __name__ == "__main__":
    asyncio.run(fix_enum_values())


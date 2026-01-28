# -*- coding: utf-8 -*-
r"""
Скрипт для конвертации колонки role из PostgreSQL enum в VARCHAR.

Запуск из корня проекта:
    .\.venv\Scripts\Activate.ps1
    python scripts/fix_admin_role.py
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

# Добавляем корень проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from admin.backend.database import async_session_factory  # noqa: E402


async def fix_roles() -> None:
    """
    Конвертирует колонку role из enum в VARCHAR(20).
    Это устраняет все проблемы с маппингом между Python и PostgreSQL enum.
    """
    print("=== Конвертация колонки role в VARCHAR ===")
    
    async with async_session_factory() as session:
        # Смотрим текущее состояние
        result = await session.execute(
            text("SELECT id, username, role::text FROM admin_users")
        )
        rows = result.fetchall()
        
        if not rows:
            print("Таблица admin_users пуста.")
        else:
            print(f"Найдено пользователей: {len(rows)}")
            for row in rows:
                print(f"  ID={row.id}, username={row.username}, role={row.role}")
        
        # Конвертируем колонку role из enum в varchar
        print("\nИзменяем тип колонки role на VARCHAR(20)...")
        
        # 1. Преобразуем enum -> text -> varchar
        await session.execute(text("""
            ALTER TABLE admin_users 
            ALTER COLUMN role TYPE VARCHAR(20) 
            USING role::text
        """))
        
        # 2. Устанавливаем значение по умолчанию
        await session.execute(text("""
            ALTER TABLE admin_users 
            ALTER COLUMN role SET DEFAULT 'user'
        """))
        
        await session.commit()
        print("Тип колонки успешно изменён.")
        
        # Проверяем результат
        result = await session.execute(
            text("SELECT id, username, role FROM admin_users")
        )
        rows = result.fetchall()
        
        print("\nПосле конвертации:")
        for row in rows:
            print(f"  ID={row.id}, username={row.username}, role={row.role}")
        
        # Удаляем старый enum тип (опционально)
        try:
            await session.execute(text("DROP TYPE IF EXISTS adminrole"))
            await session.commit()
            print("\nСтарый тип adminrole удалён.")
        except Exception as e:
            print(f"\nНе удалось удалить тип adminrole: {e}")
        
        print("\nГотово!")


if __name__ == "__main__":
    asyncio.run(fix_roles())

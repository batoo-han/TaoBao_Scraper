"""
Скрипт для проверки созданных таблиц в БД
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.session import get_session
from sqlalchemy import text

async def main():
    async for session in get_session():
        result = await session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        
        print(f"\nНайдено таблиц: {len(tables)}\n")
        for table in tables:
            print(f"  - {table}")
        break

if __name__ == "__main__":
    asyncio.run(main())

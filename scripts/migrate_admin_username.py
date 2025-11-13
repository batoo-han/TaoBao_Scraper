"""
Скрипт для миграции: добавление admin_username существующим админам.

Использование:
    python scripts/migrate_admin_username.py
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.models import AdminUser, User
from src.db.session import get_async_session
from sqlalchemy import select, text


async def migrate_admin_username():
    """Добавляет поле admin_username существующим админам."""
    print("=" * 60)
    print("Миграция: добавление admin_username")
    print("=" * 60)
    
    async with get_async_session() as session:
        # Проверяем, существует ли колонка
        try:
            result = await session.execute(
                text("SELECT column_name FROM information_schema.columns "
                     "WHERE table_name = 'admin_users' AND column_name = 'admin_username'")
            )
            column_exists = result.scalar_one_or_none() is not None
            
            if not column_exists:
                print("\n📝 Добавляем колонку admin_username...")
                await session.execute(
                    text("ALTER TABLE admin_users ADD COLUMN admin_username VARCHAR(64)")
                )
                await session.execute(
                    text("CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_username ON admin_users(admin_username)")
                )
                # Устанавливаем временные имена для существующих записей
                await session.execute(
                    text("UPDATE admin_users SET admin_username = 'admin_' || user_id::text WHERE admin_username IS NULL")
                )
                await session.commit()
                print("✅ Колонка добавлена, временные имена установлены")
            else:
                print("✅ Колонка admin_username уже существует")
        except Exception as e:
            print(f"⚠️  Ошибка при проверке/добавлении колонки: {e}")
            print("   Возможно, нужно запустить миграцию Alembic вручную")
            await session.rollback()
            return
        
        # Находим админов с временным именем (admin_*) или NULL
        result = await session.execute(
            select(AdminUser).where(
                (AdminUser.admin_username.is_(None)) |
                (AdminUser.admin_username.like('admin_%'))
            )
        )
        admins_to_update = result.scalars().all()
        
        if not admins_to_update:
            print("\n✅ Все админы уже имеют правильное имя пользователя")
            return
        
        print(f"\n📋 Найдено {len(admins_to_update)} админов для обновления")
        print("   (админы с временными именами типа 'admin_2')")
        
        for admin in admins_to_update:
            # Получаем пользователя
            result = await session.execute(
                select(User).where(User.id == admin.user_id)
            )
            user = result.scalar_one()
            
            # Предлагаем имя пользователя
            default_username = user.username or f"admin_{user.telegram_id}" or "admin"
            print(f"\nАдмин: {user.username or user.first_name} (Telegram ID: {user.telegram_id})")
            username = input(f"Введите имя пользователя для входа [по умолчанию: {default_username}]: ").strip()
            
            if not username:
                username = default_username
            
            # Проверяем уникальность
            result = await session.execute(
                select(AdminUser).where(AdminUser.admin_username == username)
            )
            existing = result.scalar_one_or_none()
            
            if existing and existing.id != admin.id:
                print(f"❌ Имя пользователя '{username}' уже занято. Пропускаем...")
                continue
            
            # Обновляем
            admin.admin_username = username
            print(f"✅ Установлено имя пользователя: {username}")
        
        await session.commit()
        
        print("\n" + "=" * 60)
        print("✅ Миграция завершена!")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(migrate_admin_username())
    except KeyboardInterrupt:
        print("\n\n❌ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


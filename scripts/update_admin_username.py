"""
Скрипт для обновления имени пользователя существующего админа.

Использование:
    python scripts/update_admin_username.py
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.models import AdminUser, User
from src.db.session import get_async_session
from sqlalchemy import select


async def update_admin_username():
    """Обновляет имя пользователя для существующего админа."""
    print("=" * 60)
    print("Обновление имени пользователя администратора")
    print("=" * 60)
    print("\n💡 Важно:")
    print("   - Telegram ID можно узнать через бота @userinfobot")
    print("   - Имя пользователя для входа может быть любым (например: admin)")
    print("=" * 60)
    
    # Запрашиваем Telegram ID
    telegram_id_input = input("\n📱 Введите Telegram ID администратора (только цифры): ").strip()
    if not telegram_id_input.isdigit():
        print("❌ Ошибка: Telegram ID должен быть числом (например: 123456789)")
        print("   Получить Telegram ID можно через бота @userinfobot в Telegram")
        return
    
    telegram_id = int(telegram_id_input)
    
    async with get_async_session() as session:
        # Ищем пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_admin:
            print(f"\n❌ Пользователь с Telegram ID {telegram_id} не найден или не является администратором.")
            return
        
        # Получаем профиль админа
        result = await session.execute(
            select(AdminUser).where(AdminUser.user_id == user.id)
        )
        admin_user = result.scalar_one_or_none()
        
        if not admin_user:
            print(f"\n❌ Профиль администратора не найден.")
            return
        
        print(f"\n✅ Найден администратор: {user.username or user.first_name}")
        print(f"   Текущее имя пользователя: {admin_user.admin_username}")
        
        # Запрашиваем новое имя
        print("\n" + "-" * 60)
        print("🔐 Обновление имени пользователя")
        print("-" * 60)
        new_username = input("👤 Введите новое имя пользователя (например: admin): ").strip()
        if not new_username:
            print("❌ Ошибка: Имя пользователя не может быть пустым")
            return
        
        # Проверяем, что имя пользователя не является числом
        if new_username.isdigit():
            print("⚠️  Внимание: Имя пользователя не должно быть числом!")
            print("   Это поле для текстового имени (например: admin, manager, root)")
            confirm = input("   Продолжить? (y/n): ").strip().lower()
            if confirm != 'y':
                return
        
        # Проверяем, не занято ли имя
        if new_username != admin_user.admin_username:
            result = await session.execute(
                select(AdminUser).where(AdminUser.admin_username == new_username)
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"❌ Ошибка: Имя пользователя '{new_username}' уже занято")
                return
        
        # Обновляем
        admin_user.admin_username = new_username
        await session.commit()
        
        print("\n" + "=" * 60)
        print("✅ Имя пользователя успешно обновлено!")
        print("=" * 60)
        print(f"   Новое имя пользователя: {new_username}")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(update_admin_username())
    except KeyboardInterrupt:
        print("\n\n❌ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


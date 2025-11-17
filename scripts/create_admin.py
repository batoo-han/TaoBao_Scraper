"""
Скрипт для создания администратора.

Использование:
    python scripts/create_admin.py
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.admin.services.auth_service import AuthService
from src.core.config import settings
from src.db.models import AdminUser, User
from src.db.session import get_async_session
from sqlalchemy import select


async def create_admin():
    """Создает администратора для админ-панели."""
    print("=" * 60)
    print("Создание администратора для админ-панели")
    print("=" * 60)
    print("\n💡 Важно:")
    print("   - Пользователь должен сначала отправить /start боту")
    print("   - Telegram ID можно узнать через бота @userinfobot")
    print("   - Имя пользователя для входа может быть любым (например: admin)")
    print("=" * 60)
    
    # Запрашиваем данные
    telegram_id_input = input("\n📱 Введите Telegram ID пользователя (только цифры): ").strip()
    if not telegram_id_input.isdigit():
        print("❌ Ошибка: Telegram ID должен быть числом (например: 123456789)")
        print("   Получить Telegram ID можно через бота @userinfobot в Telegram")
        return
    
    telegram_id = int(telegram_id_input)
    
    # Запрашиваем имя пользователя для входа
    print("\n" + "-" * 60)
    print("🔐 Настройка входа в админ-панель")
    print("-" * 60)
    admin_username = input("👤 Введите имя пользователя для входа (например: admin): ").strip()
    if not admin_username:
        print("❌ Ошибка: Имя пользователя не может быть пустым")
        return
    
    # Проверяем, что имя пользователя не является числом (чтобы не путать с Telegram ID)
    if admin_username.isdigit():
        print("⚠️  Внимание: Имя пользователя не должно быть числом!")
        print("   Это поле для текстового имени (например: admin, manager, root)")
        confirm = input("   Продолжить? (y/n): ").strip().lower()
        if confirm != 'y':
            return
    
    # Проверяем, не занято ли имя пользователя
    async with get_async_session() as check_session:
        from sqlalchemy import select
        result = await check_session.execute(
            select(AdminUser).where(AdminUser.admin_username == admin_username)
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"❌ Ошибка: Имя пользователя '{admin_username}' уже занято")
            return
        await check_session.commit()
    
    password = input("🔑 Введите пароль для админа (минимум 6 символов): ").strip()
    if len(password) < 6:
        print("❌ Ошибка: Пароль должен быть не менее 6 символов")
        return
    
    confirm_password = input("🔑 Подтвердите пароль: ").strip()
    
    if password != confirm_password:
        print("❌ Ошибка: Пароли не совпадают")
        return
    
    async with get_async_session() as session:
        # Ищем пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"\n❌ Пользователь с Telegram ID {telegram_id} не найден в базе данных.")
            print("   Сначала пользователь должен взаимодействовать с ботом (отправить /start).")
            return
        
        print(f"\n✅ Найден пользователь:")
        print(f"   Имя: {user.first_name or 'Не указано'}")
        print(f"   Username: @{user.username}" if user.username else "   Username: Не указан")
        print(f"   Telegram ID: {user.telegram_id}")
        print(f"   ID в БД: {user.id}")
        
        # Делаем админом
        user.is_admin = True
        
        # Проверяем, есть ли уже профиль админа
        result = await session.execute(
            select(AdminUser).where(AdminUser.user_id == user.id)
        )
        admin_user = result.scalar_one_or_none()
        
        if admin_user:
            print("⚠️  Профиль админа уже существует. Обновляем имя пользователя и пароль...")
            # Обновляем имя пользователя даже если профиль существует
            admin_user.admin_username = admin_username
        else:
            print("📝 Создаем профиль админа...")
            admin_user = AdminUser(
                user_id=user.id,
                admin_username=admin_username,
                can_manage_keys=True,
                can_view_stats=True,
                can_manage_users=True,
            )
            session.add(admin_user)
            await session.flush()
        
        # Устанавливаем имя пользователя и пароль
        auth_service = AuthService(session)
        await auth_service.set_admin_password(user.id, password, admin_username=admin_username)
        
        await session.commit()
        
        print("\n" + "=" * 60)
        print("✅ Администратор успешно создан!")
        print("=" * 60)
        print(f"   Пользователь: {user.username or user.first_name}")
        print(f"   Telegram ID: {user.telegram_id}")
        print(f"   Имя пользователя для входа: {admin_user.admin_username}")
        print(f"   Права:")
        print(f"     - Управление ключами: ✅")
        print(f"     - Просмотр статистики: ✅")
        print(f"     - Управление пользователями: ✅")
        print("\n💡 Теперь вы можете войти в админ-панель:")
        print(f"   http://localhost:{settings.ADMIN_PANEL_PORT}")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(create_admin())
    except KeyboardInterrupt:
        print("\n\n❌ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


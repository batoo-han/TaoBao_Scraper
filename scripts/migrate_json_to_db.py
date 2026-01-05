"""
Скрипт для миграции данных из JSON файлов в PostgreSQL.
Использование: python scripts/migrate_json_to_db.py [--backup-dir BACKUP_DIR]
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from typing import Optional
import argparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.session import get_session, init_db
from src.db.models import (
    User,
    UserSettings,
    AccessControl,
    AccessListEntry,
    AdminSettings,
    RateLimitGlobal,
    RateLimitUser,
)
from src.db.models import ListType, EntryType


try:
    MSK = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    MSK = timezone(timedelta(hours=3))


def parse_date(date_str: str) -> date:
    """Парсит дату из строки ISO формата"""
    try:
        return date.fromisoformat(date_str)
    except Exception:
        return date.today()


async def migrate_users_and_settings(data_dir: Path, session: AsyncSession):
    """Миграция пользователей и их настроек"""
    user_settings_file = data_dir / "user_settings.json"
    
    if not user_settings_file.exists():
        print(f"  ⚠️  Файл {user_settings_file} не найден, пропускаем...")
        return 0
    
    print(f"  📖 Читаем {user_settings_file}...")
    with open(user_settings_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    count = 0
    for user_id_str, settings_dict in data.items():
        user_id = int(user_id_str)
        
        # Создаём или обновляем пользователя
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        
        created_at = parse_date(settings_dict.get("created_at", date.today().isoformat()))
        username = settings_dict.get("username")  # Может не быть в JSON
        
        if user is None:
            user = User(user_id=user_id, username=username, created_at=created_at)
            session.add(user)
        else:
            user.created_at = created_at
            if username:
                user.username = username
        
        # Создаём или обновляем настройки
        result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        user_settings = result.scalar_one_or_none()
        
        if user_settings is None:
            user_settings = UserSettings(
                user_id=user_id,
                signature=settings_dict.get("signature", ""),
                default_currency=settings_dict.get("default_currency", "cny"),
                exchange_rate=settings_dict.get("exchange_rate"),
                price_mode=settings_dict.get("price_mode", ""),
                daily_limit=settings_dict.get("daily_limit"),
                monthly_limit=settings_dict.get("monthly_limit"),
            )
            session.add(user_settings)
        else:
            user_settings.signature = settings_dict.get("signature", "")
            user_settings.default_currency = settings_dict.get("default_currency", "cny")
            user_settings.exchange_rate = settings_dict.get("exchange_rate")
            user_settings.price_mode = settings_dict.get("price_mode", "")
            user_settings.daily_limit = settings_dict.get("daily_limit")
            user_settings.monthly_limit = settings_dict.get("monthly_limit")
        
        count += 1
    
    await session.commit()
    print(f"  ✅ Мигрировано пользователей: {count}")
    return count


async def migrate_access_control(data_dir: Path, session: AsyncSession):
    """Миграция настроек контроля доступа"""
    access_control_file = data_dir / "access_control.json"
    
    if not access_control_file.exists():
        print(f"  ⚠️  Файл {access_control_file} не найден, создаём по умолчанию...")
        access_control = AccessControl(id=1, whitelist_enabled=False, blacklist_enabled=False)
        session.add(access_control)
        await session.commit()
        return 0
    
    print(f"  📖 Читаем {access_control_file}...")
    with open(access_control_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Получаем или создаём конфигурацию доступа
    result = await session.execute(select(AccessControl).where(AccessControl.id == 1))
    access_control = result.scalar_one_or_none()
    
    whitelist_enabled = bool(data.get("whitelist_enabled", False))
    blacklist_enabled = bool(data.get("blacklist_enabled", False))
    
    if access_control is None:
        access_control = AccessControl(id=1, whitelist_enabled=whitelist_enabled, blacklist_enabled=blacklist_enabled)
        session.add(access_control)
    else:
        access_control.whitelist_enabled = whitelist_enabled
        access_control.blacklist_enabled = blacklist_enabled
    
    await session.flush()  # Чтобы получить ID для связанных записей
    
    # Удаляем старые записи
    await session.execute(
        delete(AccessListEntry).where(AccessListEntry.access_control_id == 1)
    )
    
    # Добавляем записи whitelist IDs
    for user_id in data.get("whitelist_ids", []):
        entry = AccessListEntry(
            access_control_id=1,
            list_type=ListType.WHITELIST,
            entry_type=EntryType.ID,
            value=str(user_id),
        )
        session.add(entry)
    
    # Добавляем записи whitelist usernames
    for username in data.get("whitelist_usernames", []):
        entry = AccessListEntry(
            access_control_id=1,
            list_type=ListType.WHITELIST,
            entry_type=EntryType.USERNAME,
            value=username,
        )
        session.add(entry)
    
    # Добавляем записи blacklist IDs
    for user_id in data.get("blacklist_ids", []):
        entry = AccessListEntry(
            access_control_id=1,
            list_type=ListType.BLACKLIST,
            entry_type=EntryType.ID,
            value=str(user_id),
        )
        session.add(entry)
    
    # Добавляем записи blacklist usernames
    for username in data.get("blacklist_usernames", []):
        entry = AccessListEntry(
            access_control_id=1,
            list_type=ListType.BLACKLIST,
            entry_type=EntryType.USERNAME,
            value=username,
        )
        session.add(entry)
    
    await session.commit()
    count = (
        len(data.get("whitelist_ids", []))
        + len(data.get("whitelist_usernames", []))
        + len(data.get("blacklist_ids", []))
        + len(data.get("blacklist_usernames", []))
    )
    print(f"  ✅ Мигрировано записей доступа: {count}")
    return count


async def migrate_admin_settings(data_dir: Path, session: AsyncSession):
    """Миграция глобальных настроек администратора"""
    admin_settings_file = data_dir / "admin_settings.json"
    
    if not admin_settings_file.exists():
        print(f"  ⚠️  Файл {admin_settings_file} не найден, создаём по умолчанию...")
        admin_settings = AdminSettings(id=1)
        session.add(admin_settings)
        await session.commit()
        return 0
    
    print(f"  📖 Читаем {admin_settings_file}...")
    with open(admin_settings_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    result = await session.execute(select(AdminSettings).where(AdminSettings.id == 1))
    admin_settings = result.scalar_one_or_none()
    
    if admin_settings is None:
        admin_settings = AdminSettings(
            id=1,
            default_llm=data.get("default_llm", "yandex"),
            yandex_model=data.get("yandex_model", "yandexgpt-lite"),
            openai_model=data.get("openai_model", "gpt-4o-mini"),
            translate_provider=data.get("translate_provider", "yandex"),
            translate_model=data.get("translate_model", "yandexgpt-lite"),
            translate_legacy=bool(data.get("translate_legacy", False)),
            convert_currency=bool(data.get("convert_currency", False)),
            tmapi_notify_439=bool(data.get("tmapi_notify_439", False)),
            debug_mode=bool(data.get("debug_mode", False)),
            mock_mode=bool(data.get("mock_mode", False)),
            forward_channel_id=data.get("forward_channel_id", ""),
            per_user_daily_limit=data.get("per_user_daily_limit"),
            per_user_monthly_limit=data.get("per_user_monthly_limit"),
            total_daily_limit=data.get("total_daily_limit"),
            total_monthly_limit=data.get("total_monthly_limit"),
        )
        session.add(admin_settings)
    else:
        admin_settings.default_llm = data.get("default_llm", "yandex")
        admin_settings.yandex_model = data.get("yandex_model", "yandexgpt-lite")
        admin_settings.openai_model = data.get("openai_model", "gpt-4o-mini")
        admin_settings.translate_provider = data.get("translate_provider", "yandex")
        admin_settings.translate_model = data.get("translate_model", "yandexgpt-lite")
        admin_settings.translate_legacy = bool(data.get("translate_legacy", False))
        admin_settings.convert_currency = bool(data.get("convert_currency", False))
        admin_settings.tmapi_notify_439 = bool(data.get("tmapi_notify_439", False))
        admin_settings.debug_mode = bool(data.get("debug_mode", False))
        admin_settings.mock_mode = bool(data.get("mock_mode", False))
        admin_settings.forward_channel_id = data.get("forward_channel_id", "")
        admin_settings.per_user_daily_limit = data.get("per_user_daily_limit")
        admin_settings.per_user_monthly_limit = data.get("per_user_monthly_limit")
        admin_settings.total_daily_limit = data.get("total_daily_limit")
        admin_settings.total_monthly_limit = data.get("total_monthly_limit")
    
    await session.commit()
    print(f"  ✅ Мигрированы настройки администратора")
    return 1


async def migrate_rate_limits(data_dir: Path, session: AsyncSession):
    """Миграция лимитов запросов"""
    rate_limits_file = data_dir / "rate_limits.json"
    
    if not rate_limits_file.exists():
        print(f"  ⚠️  Файл {rate_limits_file} не найден, создаём по умолчанию...")
        today = datetime.now(MSK).date()
        global_limits = RateLimitGlobal(
            id=1,
            day_start=today,
            month_start=today.replace(day=1),
        )
        session.add(global_limits)
        await session.commit()
        return 0
    
    print(f"  📖 Читаем {rate_limits_file}...")
    with open(rate_limits_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Миграция глобальных лимитов
    global_data = data.get("global", {})
    result = await session.execute(select(RateLimitGlobal).where(RateLimitGlobal.id == 1))
    global_limits = result.scalar_one_or_none()
    
    if global_limits is None:
        global_limits = RateLimitGlobal(
            id=1,
            day_start=parse_date(global_data.get("day_start", date.today().isoformat())),
            day_count=int(global_data.get("day_count", 0)),
            month_start=parse_date(global_data.get("month_start", date.today().replace(day=1).isoformat())),
            month_count=int(global_data.get("month_count", 0)),
            day_cost=float(global_data.get("day_cost", 0.0)),
            month_cost=float(global_data.get("month_cost", 0.0)),
        )
        session.add(global_limits)
    else:
        global_limits.day_start = parse_date(global_data.get("day_start", date.today().isoformat()))
        global_limits.day_count = int(global_data.get("day_count", 0))
        global_limits.month_start = parse_date(global_data.get("month_start", date.today().replace(day=1).isoformat()))
        global_limits.month_count = int(global_data.get("month_count", 0))
        global_limits.day_cost = float(global_data.get("day_cost", 0.0))
        global_limits.month_cost = float(global_data.get("month_cost", 0.0))
    
    await session.flush()
    
    # Миграция пользовательских лимитов
    users_data = data.get("users", {})
    count = 0
    for user_id_str, user_data in users_data.items():
        user_id = int(user_id_str)
        
        # Проверяем, что пользователь существует
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            # Создаём пользователя если его нет
            user = User(user_id=user_id, created_at=date.today())
            session.add(user)
            await session.flush()
        
        result = await session.execute(select(RateLimitUser).where(RateLimitUser.user_id == user_id))
        user_limits = result.scalar_one_or_none()
        
        if user_limits is None:
            user_limits = RateLimitUser(
                user_id=user_id,
                day_start=parse_date(user_data.get("day_start", date.today().isoformat())),
                day_count=int(user_data.get("day_count", 0)),
                month_start=parse_date(user_data.get("month_start", date.today().replace(day=1).isoformat())),
                month_count=int(user_data.get("month_count", 0)),
                day_cost=float(user_data.get("day_cost", 0.0)),
                month_cost=float(user_data.get("month_cost", 0.0)),
            )
            session.add(user_limits)
        else:
            user_limits.day_start = parse_date(user_data.get("day_start", date.today().isoformat()))
            user_limits.day_count = int(user_data.get("day_count", 0))
            user_limits.month_start = parse_date(user_data.get("month_start", date.today().replace(day=1).isoformat()))
            user_limits.month_count = int(user_data.get("month_count", 0))
            user_limits.day_cost = float(user_data.get("day_cost", 0.0))
            user_limits.month_cost = float(user_data.get("month_cost", 0.0))
        
        count += 1
    
    await session.commit()
    print(f"  ✅ Мигрировано пользовательских лимитов: {count}")
    return count


async def backup_json_files(data_dir: Path, backup_dir: Path):
    """Создание резервной копии JSON файлов"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    json_files = [
        "user_settings.json",
        "access_control.json",
        "admin_settings.json",
        "rate_limits.json",
    ]
    
    backed_up = []
    for filename in json_files:
        src_file = data_dir / filename
        if src_file.exists():
            backup_file = backup_dir / filename
            import shutil
            shutil.copy2(src_file, backup_file)
            backed_up.append(filename)
    
    return backed_up


async def main():
    parser = argparse.ArgumentParser(description="Миграция данных из JSON в PostgreSQL")
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Директория с JSON файлами (по умолчанию: data)",
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        default="data/backup_before_migration",
        help="Директория для резервных копий (по умолчанию: data/backup_before_migration)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Не создавать резервные копии JSON файлов",
    )
    
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir)
    backup_dir = Path(args.backup_dir)
    
    if not data_dir.exists():
        print(f"❌ Директория {data_dir} не существует!")
        sys.exit(1)
    
    print("🔄 Начинаем миграцию данных из JSON в PostgreSQL...")
    print(f"   Директория с данными: {data_dir}")
    
    # Создаём резервные копии
    if not args.no_backup:
        print(f"\n📦 Создаём резервные копии JSON файлов в {backup_dir}...")
        backed_up = await backup_json_files(data_dir, backup_dir)
        if backed_up:
            print(f"  ✅ Созданы резервные копии: {', '.join(backed_up)}")
        else:
            print("  ⚠️  JSON файлы не найдены для резервного копирования")
    
    # Инициализируем БД
    await init_db()
    
    # Выполняем миграцию
    async for session in get_session():
        print("\n📊 Начинаем миграцию данных...")
        
        try:
            await migrate_users_and_settings(data_dir, session)
            await migrate_access_control(data_dir, session)
            await migrate_admin_settings(data_dir, session)
            await migrate_rate_limits(data_dir, session)
            
            print("\n✅ Миграция данных завершена успешно!")
            
        except Exception as e:
            print(f"\n❌ Ошибка при миграции: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        break


if __name__ == "__main__":
    asyncio.run(main())

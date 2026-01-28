# -*- coding: utf-8 -*-
r"""
Скрипт для создания первого администратора админ-панели.

Запускать из корня проекта (где находится папка admin/ и .env):

    .\\.venv\\Scripts\\Activate.ps1        # для PowerShell (Windows)
    python scripts/create_first_admin.py

Скрипт:
- использует те же настройки БД, что и основное приложение (POSTGRES_*)
- создаёт пользователя с ролью ADMIN в таблице admin_users
"""

import asyncio
import sys
from getpass import getpass
from pathlib import Path

from sqlalchemy import select

# ------------------------------------------------------------------------------
# ВАЖНО:
# При запуске `python scripts/create_first_admin.py` Python добавляет в sys.path
# папку `scripts/`, а НЕ корень проекта. Поэтому пакет `admin` может не
# импортироваться. Добавляем корень проекта вручную.
# ------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from admin.backend.database import async_session_factory  # noqa: E402
from admin.backend.auth.jwt import hash_password  # noqa: E402
from src.db.models import AdminUser  # noqa: E402


async def create_admin() -> None:
    """
    Создаёт первого администратора в таблице admin_users.

    Логин и пароль запрашиваются из консоли.
    """
    print("=== Создание первого администратора админ-панели ===")

    username = input("Логин (username): ").strip()
    if not username:
        print("Логин не может быть пустым.")
        return

    display_name = input("Отображаемое имя (можно оставить пустым): ").strip() or None

    # Ввод пароля без отображения
    password = getpass("Пароль: ")
    password_confirm = getpass("Повторите пароль: ")

    if not password:
        print("Пароль не может быть пустым.")
        return

    if password != password_confirm:
        print("Пароли не совпадают. Администратор не создан.")
        return

    async with async_session_factory() as session:
        # Проверяем, нет ли уже такого пользователя
        result = await session.execute(
            select(AdminUser).where(AdminUser.username == username)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Пользователь с логином '{username}' уже существует.")
            return

        admin_user = AdminUser(
            username=username,
            password_hash=hash_password(password),
            role="admin",  # Роль теперь хранится как строка
            display_name=display_name,
            is_active=True,
        )

        session.add(admin_user)
        await session.commit()

        print(
            f"Администратор успешно создан.\n"
            f"Логин: {username}\n"
            f"Роль: {admin_user.role}"
        )


if __name__ == "__main__":
    asyncio.run(create_admin())


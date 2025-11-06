#!/usr/bin/env python3
"""
Портативный экспортёр cookies Chrome (Windows и macOS)

- Показывает понятное предупреждение/резюме действий
- Спрашивает подтверждение перед началом
- Переиспользует существующую логику извлечения и фильтрации cookies
- Сохраняет результирующий JSON на рабочий стол пользователя

Сборка (примеры PyInstaller):
  Windows:
    py -m pip install -r scripts/requirements-export.txt pyinstaller
    py -m PyInstaller --onefile --name CookieExporter scripts/cookie_exporter_app.py

  macOS:
    python3 -m pip install -r scripts/requirements-export.txt pyinstaller
    python3 -m PyInstaller --onefile --name CookieExporter scripts/cookie_exporter_app.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def get_desktop_path() -> Path:
    home = Path.home()
    desktop = home / "Desktop"
    return desktop if desktop.exists() else home


def prompt_save_location(default_dir: Path, default_filename: str) -> Path:
    print()
    print("Место сохранения:")
    dir_input = input(f"  Папка (Enter по умолчанию: {default_dir}): ").strip()
    save_dir = Path(dir_input) if dir_input else default_dir

    # Создадим папку при необходимости после подтверждения
    if not save_dir.exists():
        ans = input(f"  Папка не существует. Создать '{save_dir}'? [y/N]: ").strip().lower()
        if ans in ("y", "yes"):
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"  ❌ Не удалось создать папку: {e}")
                sys.exit(1)
        else:
            print("  Отменено пользователем.")
            sys.exit(0)

    name_input = input(f"  Имя файла (Enter по умолчанию: {default_filename}): ").strip()
    filename = name_input if name_input else default_filename
    if not filename.lower().endswith(".json"):
        filename += ".json"

    out_path = save_dir / filename
    if out_path.exists():
        ans = input(f"  Файл '{out_path}' уже существует. Перезаписать? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("  Отменено пользователем.")
            sys.exit(0)

    return out_path


def confirm_or_exit() -> None:
    print("=" * 70)
    print("ЭКСПОРТЁР COOKIES (Windows и macOS)")
    print("=" * 70)
    print()
    print("Программа выполнит следующие действия:")
    print("  1) Запустит Chrome через WebDriver")
    print("  2) Откроет https://mobile.yangkeduo.com/")
    print("  3) Извлечёт cookies из браузера")
    print("  4) Отфильтрует по релевантным доменам")
    print("  5) Сохранит JSON с cookies на рабочий стол")
    print()
    ans = input("Продолжить? [y/N]: ").strip().lower()
    if ans not in ("y", "yes"):  # default is No
        print("Отменено пользователем.")
        sys.exit(0)


def main() -> None:
    # Lazy import to keep the entrypoint light for PyInstaller analysis
    from scripts.export_chrome_cookies import (
        get_chrome_cookies,
        filter_cookies_by_domain,
        convert_selenium_cookies_to_pdd_format,
    )

    confirm_or_exit()

    target_url = "https://mobile.yangkeduo.com/"
    target_domains = [
        "mobile.yangkeduo.com",
        "yangkeduo.com",
        "pinduoduo.com",
        "szwego.com",
    ]

    selenium_cookies, user_agent = get_chrome_cookies(target_url)

    print(f"\n🔍 Фильтрую cookies по доменам: {', '.join(target_domains)}...")
    filtered = filter_cookies_by_domain(selenium_cookies, target_domains)
    if not filtered:
        print("⚠️  После фильтрации cookies не найдены. Сохраняю все cookies...")
        filtered = selenium_cookies

    payload = convert_selenium_cookies_to_pdd_format(filtered, user_agent, target_url)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_dir = get_desktop_path()
    default_name = f"chrome_cookies_{timestamp}.json"
    out_file = prompt_save_location(default_dir, default_name)

    with out_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 70)
    print("✅ Готово!")
    print("=" * 70)
    print(f"📁 Файл сохранён на рабочем столе: {out_file}")
    print(f"🍪 Cookies: {len(payload['cookies'])}")
    print(f"🌐 User-Agent: {payload['user_agent'][:80]}...")
    print(f"📅 Сохранено: {payload['saved_at']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)



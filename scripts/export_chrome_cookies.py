#!/usr/bin/env python3
"""
==============================================================================
ЭКСПОРТ COOKIES CHROME ДЛЯ Pinduoduo
==============================================================================
Скрипт для быстрого копирования всех cookies для mobile.yangkeduo.com
из Chrome и сохранения их в формате pdd_cookies.json.

Требования:
- Python 3.11+
- selenium: pip install selenium
- webdriver-manager: pip install webdriver-manager

Использование:
    python scripts/export_chrome_cookies.py

Автор: TaoBao Scraper Bot
Версия: 1.0.0
==============================================================================
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("❌ Ошибка: Не установлены необходимые библиотеки.")
    print("Установите их командой:")
    print("  pip install selenium webdriver-manager")
    sys.exit(1)


def get_chrome_cookies(target_url: str = "https://mobile.yangkeduo.com/") -> tuple[List[Dict[str, Any]], str]:
    """
    Извлекает cookies из Chrome для указанного URL.
    
    Args:
        target_url: URL для получения cookies
        
    Returns:
        tuple: (список cookies, user_agent)
    """
    print("🚀 Запуск Chrome...")
    
    # Настройка Chrome options
    chrome_options = Options()
    # Не используем headless, чтобы можно было видеть процесс
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # ВАЖНО: Если хотите использовать существующий профиль Chrome с уже авторизованными cookies,
    # раскомментируйте следующие строки и укажите путь к вашему профилю Chrome:
    # ⚠️ ВАЖНО: Chrome должен быть ЗАКРЫТ перед запуском скрипта!
    # import os
    # user_profile = os.path.expanduser("~")
    # chrome_options.add_argument(f"--user-data-dir={user_profile}/AppData/Local/Google/Chrome/User Data")
    # chrome_options.add_argument("--profile-directory=Default")
    # Или для Linux/Mac:
    # chrome_options.add_argument(f"--user-data-dir={user_profile}/.config/google-chrome")
    # chrome_options.add_argument("--profile-directory=Default")
    
    try:
        # Автоматическая установка ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print(f"📖 Открываю {target_url}...")
        driver.get(target_url)
        
        # Ждём загрузки страницы (можно увеличить timeout)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            print("⚠️  Страница загружена, но возможно не полностью")
        
        # Получаем cookies
        print("🍪 Извлекаю cookies...")
        selenium_cookies = driver.get_cookies()
        
        # Получаем user agent
        user_agent = driver.execute_script("return navigator.userAgent;")
        
        # Закрываем браузер
        driver.quit()
        
        print(f"✅ Найдено {len(selenium_cookies)} cookies")
        
        return selenium_cookies, user_agent
        
    except Exception as e:
        print(f"❌ Ошибка при работе с Chrome: {e}")
        print("\n💡 Возможные решения:")
        print("1. Убедитесь, что Chrome установлен")
        print("2. Проверьте, что Chrome не запущен (закройте все окна)")
        print("3. Попробуйте запустить скрипт от имени администратора")
        raise


def convert_selenium_cookies_to_pdd_format(selenium_cookies: List[Dict], user_agent: str, url: str) -> Dict[str, Any]:
    """
    Конвертирует cookies из формата Selenium в формат pdd_cookies.json.
    
    Args:
        selenium_cookies: Список cookies из Selenium
        user_agent: User-Agent браузера
        url: URL, для которого получены cookies
        
    Returns:
        dict: Структура в формате pdd_cookies.json
    """
    pdd_cookies = []
    
    for cookie in selenium_cookies:
        # Конвертируем expires (timestamp в секундах -> ISO string)
        expires = cookie.get('expires')
        expires_str = ""
        if expires:
            try:
                # Если expires - это timestamp
                if isinstance(expires, (int, float)):
                    expires_str = datetime.fromtimestamp(expires).isoformat() + "Z"
                elif isinstance(expires, str):
                    expires_str = expires
            except Exception:
                expires_str = ""
        
        # Конвертируем sameSite
        same_site = cookie.get('sameSite', '')
        if same_site:
            # Chrome использует 'None', 'Lax', 'Strict' или ''
            if same_site.lower() == 'none':
                same_site = 'None'
            elif same_site.lower() == 'lax':
                same_site = 'Lax'
            elif same_site.lower() == 'strict':
                same_site = 'Strict'
        else:
            same_site = ""
        
        pdd_cookie = {
            "name": cookie.get('name', ''),
            "value": cookie.get('value', ''),
            "domain": cookie.get('domain', ''),
            "path": cookie.get('path', '/'),
            "expires": expires_str,
            "httpOnly": cookie.get('httpOnly', False),
            "secure": cookie.get('secure', False),
            "sameSite": same_site
        }
        
        pdd_cookies.append(pdd_cookie)
    
    # Формируем итоговую структуру
    result = {
        "cookies": pdd_cookies,
        "user_agent": user_agent,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "url": url
    }
    
    return result


def filter_cookies_by_domain(cookies: List[Dict], target_domains: List[str]) -> List[Dict]:
    """
    Фильтрует cookies по доменам.
    
    Args:
        cookies: Список cookies
        target_domains: Список доменов для фильтрации
        
    Returns:
        list: Отфильтрованный список cookies
    """
    filtered = []
    for cookie in cookies:
        domain = cookie.get('domain', '')
        # Проверяем, совпадает ли домен или является поддоменом
        for target_domain in target_domains:
            if domain == target_domain or domain.endswith('.' + target_domain):
                filtered.append(cookie)
                break
    return filtered


def main():
    """Основная функция скрипта."""
    print("=" * 70)
    print("EXPORT CHROME COOKIES FOR Pinduoduo")
    print("=" * 70)
    print()
    
    # URL для получения cookies
    target_url = "https://mobile.yangkeduo.com/"
    
    # Домены для фильтрации (опционально, можно оставить все)
    target_domains = [
        "mobile.yangkeduo.com",
        "yangkeduo.com",
        "pinduoduo.com",
        "szwego.com"
    ]
    
    try:
        # Получаем cookies из Chrome
        selenium_cookies, user_agent = get_chrome_cookies(target_url)
        
        # Фильтруем cookies по доменам (опционально)
        print(f"🔍 Фильтрую cookies по доменам: {', '.join(target_domains)}...")
        filtered_cookies = filter_cookies_by_domain(selenium_cookies, target_domains)
        
        if not filtered_cookies:
            print("⚠️  После фильтрации cookies не найдены. Сохраняю все cookies...")
            filtered_cookies = selenium_cookies
        
        print(f"✅ Отфильтровано {len(filtered_cookies)} cookies")
        
        # Конвертируем в формат pdd_cookies.json
        print("🔄 Конвертирую в формат pdd_cookies.json...")
        pdd_format = convert_selenium_cookies_to_pdd_format(
            filtered_cookies,
            user_agent,
            target_url
        )
        
        # Определяем путь для сохранения файла (в той же папке, где скрипт)
        script_dir = Path(__file__).parent.absolute()
        output_file = script_dir / "chrome_cookies.json"
        
        # Альтернатива: сохранить в src/ для прямого использования
        # output_file = script_dir.parent / "src" / "chrome_cookies.json"
        
        # Сохраняем в файл
        print(f"💾 Сохраняю в {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(pdd_format, f, indent=2, ensure_ascii=False)
        
        print()
        print("=" * 70)
        print("✅ ГОТОВО!")
        print("=" * 70)
        print(f"📁 Файл сохранён: {output_file}")
        print(f"🍪 Cookies: {len(pdd_format['cookies'])}")
        print(f"🌐 User-Agent: {pdd_format['user_agent'][:80]}...")
        print(f"📅 Сохранено: {pdd_format['saved_at']}")
        print()
        print("💡 Теперь вы можете скопировать содержимое в src/pdd_cookies.json")
        print("   или использовать chrome_cookies.json напрямую (измените путь в .env)")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


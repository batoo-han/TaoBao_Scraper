import asyncio
from typing import List, Dict, Any
from urllib.parse import urlparse

from src.core.config import settings
import json
import os
import random


DESKTOP_UA_POOL = [
    # Современные десктопные UA (Chrome/Edge/Yandex)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 YaBrowser/25.8.0.0 Safari/537.36",
]

MOBILE_UA_POOL = [
    # iPhone Safari / Chrome iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/121.0.0.0 Mobile/15E148 Safari/604.1",
    # Android Chrome
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
]


def _parse_cookie_header(cookie_header: str) -> List[Dict[str, Any]]:
    """
    Преобразует строку Cookie из DevTools в список cookie-объектов Playwright.
    """
    cookies = []
    if not cookie_header:
        return cookies
    # Определяем домены для установки cookies
    domains = [
        ".yangkeduo.com",
        "mobile.yangkeduo.com",
    ]
    for part in cookie_header.split(";"):
        if not part.strip() or "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        name = name.strip()
        value = value.strip()
        # Устанавливаем cookie на оба домена для надёжности
        for domain in domains:
            cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": "/",
                "httpOnly": False,
                "secure": True,
            })
    return cookies


def _build_cookie_header(cookies: List[Dict[str, Any]]) -> str:
    """Собирает cookieHeader из списка кук Playwright."""
    if not cookies:
        return ""
    pairs = []
    # Берём только ключевые домены PDD
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if name and value:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


class PinduoduoWebScraper:
    """
    Веб-скрапер Pinduoduo (mobile.yangkeduo.com) на базе Playwright.
    Использует заранее выданные куки и User-Agent (если указаны в конфиге),
    либо пытается открыть страницу и дождаться элементов.
    """

    def __init__(self):
        # Изначально берём из .env
        self.user_agent = settings.PDD_USER_AGENT.strip() if settings.PDD_USER_AGENT else None
        self.cookie_header = settings.PDD_COOKIE_HEADER.strip() if settings.PDD_COOKIE_HEADER else None
        # Пытаемся перегрузить из внешнего JSON (если есть)
        self._load_from_json_if_present()

    def _load_from_json_if_present(self) -> None:
        path = settings.PDD_COOKIES_FILE
        try:
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # cookieHeader имеет приоритет над массивом cookies
                header = (data.get("cookieHeader") or "").strip()
                if header:
                    self.cookie_header = header
                ua = (data.get("userAgent") or "").strip()
                if ua:
                    self.user_agent = ua
        except Exception:
            # Тихо игнорируем проблемы файла — останемся на .env
            pass

    def _ensure_user_agent(self, is_mobile: bool, debug: bool) -> None:
        """Если UA не задан, выбираем случайный из пула под профиль."""
        if self.user_agent and self.user_agent.strip():
            if debug:
                print(f"[DEBUG] Используем заданный User-Agent: {self.user_agent[:120]}")
            return
        pool = MOBILE_UA_POOL if is_mobile else DESKTOP_UA_POOL
        self.user_agent = random.choice(pool)
        if debug:
            print(f"[DEBUG] Выбран случайный User-Agent: {self.user_agent[:120]}")

    async def _save_cookies(self, context) -> None:
        """Сохраняет текущие куки в JSON (cookieHeader)."""
        try:
            cookies = await context.cookies()
            header = _build_cookie_header(cookies)
            if not header:
                return
            path = settings.PDD_COOKIES_FILE or "src/pdd_cookies.json"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {"cookieHeader": header}
            # Сохраним и userAgent если он задан
            if self.user_agent:
                data["userAgent"] = self.user_agent
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    async def _human_pause(self, a: float = 0.2, b: float = 0.8):
        await asyncio.sleep(random.uniform(a, b))

    async def _mouse_wiggle(self, page, steps: int = 10):
        try:
            box = await page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
            x = random.randint(10, max(11, box['w'] - 10))
            y = random.randint(10, max(11, box['h'] - 10))
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            for _ in range(steps):
                dx = random.randint(-30, 30)
                dy = random.randint(-20, 20)
                x = max(1, min(box['w'] - 1, x + dx))
                y = max(1, min(box['h'] - 1, y + dy))
                await page.mouse.move(x, y, steps=random.randint(2, 6))
                await self._human_pause(0.05, 0.2)
        except Exception:
            pass

    async def _ensure_logged_in(self, context, page) -> bool:
        """
        Если нет cookie_header — пробуем полуавтоматический login по номеру телефона.
        Возвращает True, если после попыток появился PDDAccessToken в cookies.
        """
        debug = getattr(settings, 'DEBUG_MODE', False)
        # Проверяем конфиг для телефона
        if not settings.PDD_COUNTRY_CODE or not settings.PDD_PHONE_NUMBER:
            if debug:
                print("[PDD][LOGIN] Не указан код страны/телефон — пропускаем авто-логин")
            return False

        login_url = "https://mobile.yangkeduo.com/login.html"
        try:
            await page.goto(login_url, wait_until="networkidle")
            await self._mouse_wiggle(page)
            await self._human_pause()

            # Шаг 1. Нажимаем элемент, открывающий форму ввода телефона
            # /html/body/div[1]/div/div[1]/div[2]/div
            try:
                open_form_btn = await page.wait_for_selector("xpath=/html/body/div[1]/div/div[1]/div[2]/div", timeout=8000)
                if open_form_btn:
                    await self._mouse_wiggle(page, steps=5)
                    await open_form_btn.click()
                    await self._human_pause(0.3, 0.8)
                    if debug:
                        print("[PDD][LOGIN] Клик по кнопке перехода к форме ввода телефона выполнен")
            except Exception as e:
                if debug:
                    print(f"[PDD][LOGIN] Не удалось нажать кнопку перехода к форме: {e}")

            # XPaths формы из ТЗ
            xpath_country = "xpath=/html/body/div[1]/div/div[2]/div/form/div[2]/div/input"
            xpath_phone = "xpath=/html/body/div[1]/div/div[2]/div/form/div[2]/input"
            xpath_send = "xpath=/html/body/div[1]/div/div[2]/div/form/div[3]/div"

            # Шаг 2. Ввод кода страны
            try:
                el_country = await page.wait_for_selector(xpath_country, timeout=8000)
                await el_country.click()
                await self._human_pause()
                await el_country.fill(str(settings.PDD_COUNTRY_CODE))
                await self._human_pause()
            except Exception as e:
                if debug:
                    print(f"[PDD][LOGIN] Не удалось ввести код страны: {e}")

            # Шаг 3. Ввод телефона
            try:
                el_phone = await page.wait_for_selector(xpath_phone, timeout=8000)
                await el_phone.click()
                await self._human_pause()
                await el_phone.fill(str(settings.PDD_PHONE_NUMBER))
                await self._human_pause()
            except Exception as e:
                if debug:
                    print(f"[PDD][LOGIN] Не удалось ввести телефон: {e}")

            # Шаг 4. Отправляем код и ждём токен в cookies
            max_attempts = max(1, int(settings.PDD_LOGIN_MAX_ATTEMPTS))
            timeout_sec = max(30, int(settings.PDD_LOGIN_CODE_TIMEOUT_SEC))

            for attempt in range(1, max_attempts + 1):
                try:
                    btn = await page.wait_for_selector(xpath_send, timeout=6000)
                    await self._mouse_wiggle(page, steps=6)
                    await btn.click()
                    if debug:
                        print(f"[PDD][LOGIN] Отправка кода, попытка {attempt}/{max_attempts}")
                except Exception as e:
                    if debug:
                        print(f"[PDD][LOGIN] Не удалось нажать отправку кода: {e}")

                ok = await self._wait_for_access_token(context, timeout_sec)
                if ok:
                    if debug:
                        print("[PDD][LOGIN] PDDAccessToken обнаружен в cookies")
                    await self._save_cookies(context)
                    return True
                if debug:
                    print("[PDD][LOGIN] Токен не появился, пробуем ещё раз…")
            return False
        except Exception as e:
            if debug:
                print(f"[PDD][LOGIN] Ошибка при входе: {e}")
            return False

    async def _wait_for_access_token(self, context, timeout_sec: int) -> bool:
        """
        Ожидает появления PDDAccessToken в cookies контекста.
        """
        end = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < end:
            try:
                cookies = await context.cookies()
                if any(c.get('name') == 'PDDAccessToken' for c in cookies):
                    return True
            except Exception:
                pass
            await asyncio.sleep(1)
        return False

    async def fetch_product(self, url: str) -> Dict[str, Any]:
        """
        Открывает страницу товара и извлекает: описание и список изображений.
        Возвращает данные в формате {code,msg,data} совместимом с остальным пайплайном.
        """
        from playwright.async_api import async_playwright

        # Результат по умолчанию
        result: Dict[str, Any] = {"code": 200, "msg": "success", "data": {}}

        debug = getattr(settings, 'DEBUG_MODE', False)
        html_source = None
        async with async_playwright() as p:
            headless = not bool(getattr(settings, 'DEBUG_MODE', False))
            slow_mo = int(getattr(settings, 'PLAYWRIGHT_SLOWMO_MS', 0)) if getattr(settings, 'DEBUG_MODE', False) else 0
            launch_kwargs = {"headless": headless}
            if slow_mo:
                launch_kwargs["slow_mo"] = slow_mo
            # Прокси на уровне браузера
            if getattr(settings, 'PLAYWRIGHT_PROXY', "").strip():
                launch_kwargs["proxy"] = {"server": settings.PLAYWRIGHT_PROXY.strip()}
                if debug:
                    print(f"[DEBUG] Playwright proxy: {settings.PLAYWRIGHT_PROXY.strip()}")

            browser = await p.chromium.launch(**launch_kwargs)
            # Подбор UA под профиль
            is_mobile = bool(getattr(settings, 'PLAYWRIGHT_USE_MOBILE', False))
            self._ensure_user_agent(is_mobile, debug)

            context = None
            # Выбор режима: мобильный или обычный
            if is_mobile:
                device_name = getattr(settings, 'PLAYWRIGHT_MOBILE_DEVICE', 'iPhone 12')
                try:
                    device = p.devices.get(device_name) or p.devices['iPhone 12']
                except Exception:
                    device = p.devices['iPhone 12']
                device_kwargs = {
                    **device,
                    "locale": getattr(settings, 'PLAYWRIGHT_LOCALE', 'zh-CN'),
                    "timezone_id": getattr(settings, 'PLAYWRIGHT_TIMEZONE', 'Asia/Shanghai'),
                    "permissions": device.get("permissions", []),
                    "extra_http_headers": {
                        "Accept-Language": "zh-CN,zh;q=0.9",
                    },
                    "user_agent": self.user_agent,
                }
                context = await browser.new_context(**device_kwargs)
            else:
                context_args = {
                    "locale": getattr(settings, 'PLAYWRIGHT_LOCALE', 'zh-CN'),
                    "timezone_id": getattr(settings, 'PLAYWRIGHT_TIMEZONE', 'Asia/Shanghai'),
                    "extra_http_headers": {"Accept-Language": "zh-CN,zh;q=0.9"},
                    "user_agent": self.user_agent,
                }
                context = await browser.new_context(**context_args)

            # 1) Пытаемся использовать куки, если они есть (из заголовка/файла)
            have_preset_cookies = False
            if self.cookie_header:
                cookies = _parse_cookie_header(self.cookie_header)
                if cookies:
                    try:
                        await context.add_cookies(cookies)
                        have_preset_cookies = True
                        if debug:
                            print("[DEBUG] Заданы предустановленные cookies из заголовка/файла")
                    except Exception as e:
                        if debug:
                            print(f"[DEBUG] Ошибка при выставлении cookies: {e}")

            page = await context.new_page()
            try:
                page.set_default_timeout(45000)
                page.set_default_navigation_timeout(45000)
            except Exception:
                pass

            # 2) Если кук нет — пробуем войти через login.html
            if not have_preset_cookies:
                if debug:
                    print("[DEBUG] Куки отсутствуют — запускаем процедуру логина")
                logged = await self._ensure_logged_in(context, page)
                if debug:
                    print(f"[DEBUG] Результат авто-логина: {logged}")

            # 3) Переходим на страницу товара
            try:
                if debug:
                    print(f"[DEBUG] Переход на страницу товара: {url}")
                await page.goto(url, wait_until="networkidle")
                html_source = await page.content()
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Ошибка при загрузке страницы: {e}")
                result['code'] = 500
                result['msg'] = f'Ошибка Playwright: {e}'
                await context.close()
                await browser.close()
                return result

            # 4) Проверяем наличие ключевого контейнера. Если его нет — куки невалидны, пробуем логин и повтор.
            try:
                container = await page.wait_for_selector("xpath=//*[@id=\"main\"]/div/div[2]/div[1]/div/div", timeout=5000)
            except Exception:
                container = None
            if not container:
                if debug:
                    print("[DEBUG] Ключевой контейнер не найден — пытаемся залогиниться и повторить")
                logged = await self._ensure_logged_in(context, page)
                if debug:
                    print(f"[DEBUG] Результат авто-логина после проверки контейнера: {logged}")
                try:
                    await page.goto(url, wait_until="networkidle")
                    html_source = await page.content()
                    container = await page.wait_for_selector("xpath=//*[@id=\"main\"]/div/div[2]/div[1]/div/div", timeout=8000)
                except Exception as e:
                    if debug:
                        print(f"[DEBUG] Повторная попытка после логина не удалась: {e}")

            # Извлекаем описание
            description = ""
            try:
                await page.wait_for_selector("xpath=/html/body/div[4]/div/div[2]/div[6]/div/span/span/span", timeout=5000)
                desc_el = await page.query_selector("xpath=/html/body/div[4]/div/div[2]/div[6]/div/span/span/span")
                if desc_el:
                    description = await desc_el.text_content()
                if description:
                    description = description.strip()
                if debug:
                    print(f"[DEBUG] Описание: {description}")
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Не удалось получить описание: {e}")
            # Извлекаем изображения из контейнера галереи
            main_images: List[str] = []
            try:
                img_elements = []
                if container:
                    img_elements = await page.query_selector_all("xpath=//*[@id=\"main\"]/div/div[2]/div[1]/div/div//img")
                    if debug:
                        print(f"[DEBUG] Нашли контейнер, img элементов: {len(img_elements)}")
                for img in img_elements:
                    src = await img.get_attribute("src")
                    if src and src not in main_images:
                        main_images.append(src)
                if debug:
                    print(f"[DEBUG] main_imgs: {main_images}")
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Не удалось получить фотографии: {e}")
            # Заголовок товара (если получится)
            title = ""
            try:
                title_el = await page.query_selector("xpath=/html/body/div[4]/div/div[2]/div[1]//h1 | //h2 | //strong")
                if title_el:
                    t = await title_el.text_content()
                    if t:
                        title = t.strip()
                if debug:
                    print(f"[DEBUG] Заголовок: {title}")
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Не удалось получить заголовок: {e}")

            await context.close()
            await browser.close()
            if debug and html_source:
                print(f"[DEBUG] HTML (начало): {html_source[:600]}")
        result["data"] = {
            "item_id": None,
            "title": title or "",
            "price": "",
            "price_info": {"price": ""},
            "product_props": [],
            "main_imgs": main_images,
            "detail_imgs": [],
            "details": description or "",
            "shop_info": {},
            "is_item_onsale": True,
            "sku_props": [],
            "skus": [],
            "promotions": None,
            "side_sales_tip": "",
        }
        if debug:
            print(f"[DEBUG] Финальный словарь result['data']: {result['data']}")
        return result



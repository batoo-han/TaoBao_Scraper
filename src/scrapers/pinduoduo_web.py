import asyncio
from typing import List, Dict, Any
from urllib.parse import urlparse

from src.core.config import settings
import json
import os
import random
from io import BytesIO

import httpx
from PIL import Image


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


def _cookies_header_to_array(cookie_header: str) -> List[Dict[str, Any]]:
    """Преобразует cookieHeader в список куки-объектов."""
    if not cookie_header:
        return []
    domains = [".yangkeduo.com", "mobile.yangkeduo.com"]
    out = []
    for part in cookie_header.split(";"):
        if not part.strip() or "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        name = name.strip()
        value = value.strip()
        for domain in domains:
            out.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": "/",
                "httpOnly": False,
                "secure": True,
            })
    return out


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
    затем открывает страницу, ждёт полной загрузки и извлекает данные строго по селекторам из ТЗ.
    """

    def __init__(self):
        # Загружаем только из файла JSON (и UA из .env при наличии)
        self.user_agent = settings.PDD_USER_AGENT.strip() if settings.PDD_USER_AGENT else None
        self.cookie_header = None
        # Пытаемся загрузить из внешнего JSON (если есть)
        self._load_from_json_if_present()

    def _normalize_cookies(self, cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Приводит cookies из JSON к формату Playwright: корректные типы и значения.
        - expires: float в секундах Unix (если строка/пусто — удаляем поле)
        - path: по умолчанию "/"
        - secure: True
        - sameSite: удаляем или приводим к допустимым значениям ('Strict'|'Lax'|'None')
        - domain: оставляем как есть
        """
        normalized: List[Dict[str, Any]] = []
        for c in cookies or []:
            if not c or not c.get("name") or c.get("value") is None:
                continue
            n = dict(c)
            # expires → float или удаляем
            if "expires" in n:
                try:
                    if n["expires"] in ("", None):
                        n.pop("expires", None)
                    elif isinstance(n["expires"], str):
                        n["expires"] = float(n["expires"])  # может бросить ValueError
                    else:
                        # пусть будет как есть если это число
                        float(n["expires"])  # проверка
                except Exception:
                    n.pop("expires", None)
            # path по умолчанию
            if not n.get("path"):
                n["path"] = "/"
            # secure по умолчанию
            if n.get("secure") is None:
                n["secure"] = True
            # Нормализуем sameSite → допускаются только Strict|Lax|None
            if 'sameSite' in n:
                try:
                    v = n.get('sameSite')
                    if isinstance(v, str):
                        vl = v.strip().lower()
                        if vl in ('strict', 'lax', 'none'):
                            n['sameSite'] = vl.capitalize()
                        else:
                            n.pop('sameSite', None)
                    else:
                        n.pop('sameSite', None)
                except Exception:
                    n.pop('sameSite', None)
            normalized.append(n)
        return normalized

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
                # Сохраним массив cookies если он присутствует (альтернативный формат)
                cookies = data.get("cookies")
                if isinstance(cookies, list) and cookies:
                    # Преобразуем массив cookie-объектов в cookieHeader как fallback
                    try:
                        pairs = []
                        for c in cookies:
                            name = c.get("name")
                            value = c.get("value")
                            if name and value:
                                pairs.append(f"{name}={value}")
                        if pairs and not header:
                            self.cookie_header = "; ".join(pairs)
                    except Exception:
                        pass
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

    async def _human_pause(self, a: float = 0.2, b: float = 0.8):
        await asyncio.sleep(random.uniform(a, b))

    async def fetch_product(self, url: str) -> Dict[str, Any]:
        """
        Открывает страницу товара и извлекает: заголовок, описание, цену, изображения.
        Возвращает {code,msg,data} для дальнейшей обработки пайплайном.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            if getattr(settings, 'DEBUG_MODE', False):
                print("[PDD][INIT] Playwright не установлен. Установите зависимости и браузер:")
                print("[PDD][INIT] pip install -r requirements.txt && python -m playwright install chromium")
            raise RuntimeError("Playwright is not installed. Install deps and run 'python -m playwright install chromium'.") from e

        # Результат по умолчанию
        result: Dict[str, Any] = {"code": 200, "msg": "success", "data": {}}

        debug = getattr(settings, 'DEBUG_MODE', False)
        html_source = None
        # Нормализуем URL: добавим схему при её отсутствии
        full_url = url
        if not (url.startswith("http://") or url.startswith("https://")):
            full_url = f"https://{url}"
            if debug:
                print(f"[DEBUG] Нормализуем URL без схемы → {full_url}")
        async with async_playwright() as p:
            # В DEBUG всегда показываем окно браузера
            headless = False if getattr(settings, 'DEBUG_MODE', False) else True
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

            # 1) Пытаемся использовать куки из файла JSON
            have_preset_cookies = False
            try:
                path = settings.PDD_COOKIES_FILE
                if path and os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # приоритет: cookies (массив), затем cookieHeader
                    file_cookies = data.get("cookies")
                    if isinstance(file_cookies, list) and file_cookies:
                        norm = self._normalize_cookies(file_cookies)
                        await context.add_cookies(norm)
                        have_preset_cookies = True
                        if debug:
                            print(f"[DEBUG] Загружены cookies из массива cookies в JSON: {len(norm)} шт.")
                    elif (data.get("cookieHeader") or "").strip():
                        arr = _cookies_header_to_array((data.get("cookieHeader") or "").strip())
                        if arr:
                            await context.add_cookies(arr)
                            have_preset_cookies = True
                            if debug:
                                print(f"[DEBUG] Загружены cookies из cookieHeader в JSON: {len(arr)} шт.")
                    else:
                        if debug:
                            print("[DEBUG] Файл JSON найден, но cookies отсутствуют")
                else:
                    if debug:
                        print("[DEBUG] Файл cookies JSON не найден — перейдём к логину")
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Не удалось загрузить cookies из JSON: {e}")

            page = await context.new_page()
            try:
                to = int(getattr(settings, 'PLAYWRIGHT_PAGE_TIMEOUT_MS', 60000))
                page.set_default_timeout(to)
                page.set_default_navigation_timeout(to)
            except Exception:
                pass

            # 2) Если кук нет — не логинимся. Используем только предустановленные куки.
            if not have_preset_cookies:
                if debug:
                    print("[DEBUG] Куки отсутствуют — прерываем (только предустановленные куки допускаются)")
                await context.close()
                await browser.close()
                result['code'] = 401
                result['msg'] = 'PDD cookies missing. Provide cookies in src/pdd_cookies.json.'
                return result

            # 3) Переходим на страницу товара
            try:
                if debug:
                    print(f"[DEBUG] Переход на страницу товара: {full_url}")
                # Сначала минимум DOM, затем полная загрузка и сетевой простои
                await page.goto(full_url, wait_until="domcontentloaded")
                try:
                    to = int(getattr(settings, 'PLAYWRIGHT_PAGE_TIMEOUT_MS', 60000))
                    await page.wait_for_load_state("load", timeout=to)
                    await page.wait_for_load_state("networkidle", timeout=to)
                except Exception:
                    pass
                await self._human_pause(0.8, 1.6)
                html_source = await page.content()
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Ошибка при загрузке страницы: {e}")
                result['code'] = 500
                result['msg'] = f'Ошибка Playwright: {e}'
                # В DEBUG не закрываем браузер; вне DEBUG — по настройке
                if debug:
                    pass
                elif not getattr(settings, 'PLAYWRIGHT_KEEP_BROWSER_OPEN', False):
                    await context.close()
                    await browser.close()
                return result

            # 4) Проверяем наличие ключевого контейнера (не критично, просто для логов)
            try:
                container = await page.wait_for_selector("xpath=//*[@id=\"main\"]/div/div[2]/div[1]/div/div", timeout=5000)
            except Exception:
                container = None
            if not container and debug:
                print("[DEBUG] Ключевой контейнер не найден — продолжаем извлечение по селекторам из ТЗ")

            # Извлекаем элементы строго по правилам ТЗ
            # 1) Название товара: span.tLYIg_Ju.enable-select → взять самый длинный текст (>20 символов), обходя вложенные элементы
            title = ""
            try:
                js_get_title = """
                    () => {
                      const nodes = Array.from(document.querySelectorAll('span.tLYIg_Ju.enable-select'));
                      let best = '';
                      const getText = (el) => {
                        if (!el) return '';
                        // Собираем весь видимый текст, включая вложенные узлы
                        let t = el.innerText || '';
                        return (t || '').trim();
                      };
                      for (const n of nodes) {
                        const t = getText(n);
                        if (t && t.length > best.length) best = t;
                      }
                      // Фильтр на длину > 20 символов, если есть
                      if (best.length >= 20) return best;
                      return best; // вернём лучшее, даже если короче
                    }
                """
                title_candidate = await page.evaluate(js_get_title)
                if isinstance(title_candidate, str):
                    title = title_candidate.strip()
                if debug:
                    print(f"[DEBUG] Title(span.tLYIg_Ju.enable-select): {title}")
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Ошибка извлечения title по классу: {e}")

            # 2) Дополнительное описание: div.jvsKAdEs → собрать aria-label из внутренних контейнеров
            extra_desc = ""
            try:
                js_get_extra = """
                    () => {
                      const root = document.querySelector('div.jvsKAdEs');
                      if (!root) return '';
                      const withAria = Array.from(root.querySelectorAll('[aria-label]'));
                      const parts = withAria
                        .map(el => (el.getAttribute('aria-label') || '').trim())
                        .filter(Boolean);
                      return parts.join(' ').trim();
                    }
                """
                extra_candidate = await page.evaluate(js_get_extra)
                if isinstance(extra_candidate, str):
                    extra_desc = extra_candidate.strip()
                if debug:
                    print(f"[DEBUG] Extra(desc aria-label in jvsKAdEs): {extra_desc}")
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Ошибка извлечения дополнительного описания: {e}")

            # 3) Цена: span.kxqW0mMz → собрать текст всех потомков по порядку; сверить с div.YocHfP4N
            price = ""
            try:
                # Ждём появления контейнера цены, т.к. он может рендериться позже
                try:
                    await page.wait_for_selector('span.kxqW0mMz', timeout=7000)
                except Exception:
                    pass
                js_get_price = """
                    () => {
                      const selectors = [
                        'span.kxqW0mMz',
                        'div.kxqW0mMz',
                        'span[class*="kxqW0mMz"]',
                        'div[class*="kxqW0mMz"]'
                      ];
                      const textFromEl = (el) => {
                        if (!el) return '';
                        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                        let buf = '';
                        let n;
                        while ((n = walker.nextNode())) {
                          const t = (n.nodeValue || '').trim();
                          if (t) buf += t;
                        }
                        return buf.trim();
                      };
                      const getNumeric = (s) => {
                        if (!s) return '';
                        const m = s.replace(/\s+/g,'').match(/\d+(?:\.\d+)?/);
                        return m ? m[0] : '';
                      };
                      for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (!el) continue;
                        const raw = textFromEl(el);
                        const num = getNumeric(raw);
                        if (num) return num;
                      }
                      // Как fallback: ищем ближайший элемент к символу '¥' и читаем числа рядом
                      const y = document.querySelector('div.YocHfP4N, span.YocHfP4N, [class*="YocHfP4N"]');
                      if (y) {
                        const t = textFromEl(y);
                        const m = (t || '').replace(/\s+/g,'').match(/\d+(?:\.\d+)?/);
                        if (m) return m[0];
                      }
                      // Универсальный fallback: сначала ищем родителя с набором вложенных span с font-size (составная цена)
                      const composedParents = Array.from(document.querySelectorAll('span,div')).filter(el => el.querySelector('span[style*="font-size"], div[style*="font-size"]'));
                      for (const p of composedParents) {
                        const txt = textFromEl(p).replace(/\s+/g,'');
                        if (!txt) continue;
                        // Ищем число с точкой, например 19.9
                        const m = txt.match(/\d+\.\d{1,2}/);
                        if (m) return m[0];
                      }
                      // Универсальный fallback: выбираем самый «крупный» видимый элемент-носитель числа
                      const all = Array.from(document.querySelectorAll('span,div'));
                      let best = {size: 0, val: ''};
                      for (const el of all) {
                        if (!(el instanceof HTMLElement)) continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        const txt = textFromEl(el);
                        if (!txt) continue;
                        const m = txt.replace(/\s+/g,'').match(/\d+(?:\.\d+)?/);
                        if (!m) continue;
                        const fs = parseFloat(getComputedStyle(el).fontSize) || 0;
                        // Повышаем вес, если рядом есть символ валюты
                        const around = (el.parentElement ? el.parentElement.innerText || '' : '') + (el.previousElementSibling ? el.previousElementSibling.innerText || '' : '');
                        const bonus = /¥|￥/.test(around) ? 2 : 0;
                        const score = fs + bonus;
                        if (score > best.size) {
                          best = {size: score, val: m[0]};
                        }
                      }
                      if (best.val) return best.val;
                      return '';
                    }
                """
                price_candidate = await page.evaluate(js_get_price)
                if isinstance(price_candidate, str):
                    price = price_candidate.strip()
                # сверка с div.YocHfP4N (не критично, просто лог)
                try:
                    js_check_div = """
                        () => {
                          const d = document.querySelector('div.YocHfP4N');
                          if (!d) return '';
                          return (d.innerText || '').trim();
                        }
                    """
                    price2 = await page.evaluate(js_check_div)
                    if debug:
                        print(f"[DEBUG] Price(span.kxqW0mMz): {price} | div.YocHfP4N: {price2}")
                except Exception:
                    pass
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Ошибка извлечения цены: {e}")

            # 4) Изображения: главное и дополнительные
            main_images: List[str] = []
            try:
                # «Умная» медленная прокрутка: более плавные шаги + прокрутка к целевым узлам
                try:
                    async def get_lazy_img_count() -> int:
                        try:
                            return await page.evaluate(
                                '() => document.querySelectorAll(`img.pdd-lazy-image.loaded[role="img"][aria-label="查看图片"]`).length'
                            )
                        except Exception:
                            return 0

                    # Первая медленная прокрутка вниз шагами
                    last_count = await get_lazy_img_count()
                    stable_rounds = 0
                    for _ in range(2):  # два прохода цикла: вниз-вверх-вниз
                        # вниз малыми шагами (0.5 высоты вьюпорта)
                        for _ in range(28):
                            await page.evaluate("() => window.scrollBy(0, Math.floor(window.innerHeight * 0.5))")
                            await self._human_pause(0.45, 0.95)
                            new_count = await get_lazy_img_count()
                            if new_count > last_count:
                                last_count = new_count
                                stable_rounds = 0
                            else:
                                stable_rounds += 1
                            # если несколько шагов без прироста — небольшая задержка для догрузки
                            if stable_rounds >= 3:
                                await self._human_pause(0.8, 1.4)
                                stable_rounds = 0
                        # вверх
                        await page.evaluate("() => window.scrollTo(0, 0)")
                        await self._human_pause(0.8, 1.5)

                    # Прокрутка к каждому целевому элементу по координате, чтобы триггерить lazy-load
                    try:
                        positions = await page.evaluate(
                            '() => Array.from(document.querySelectorAll(`img.pdd-lazy-image[role=\'img\'][aria-label=\'查看图片\'], [aria-label=\'商品大图\'] img, [aria-label=\'商品大图\']`)).map(el => (el.getBoundingClientRect().top + window.scrollY))'
                        )
                        if isinstance(positions, list) and positions:
                            positions = sorted(set(int(p) for p in positions if p is not None))
                            for y in positions:
                                await page.evaluate(f"(y) => window.scrollTo(0, Math.max(0, y - 120))", y)
                                await self._human_pause(0.5, 1.1)
                                # короткая задержка на догрузку сетей
                                try:
                                    await page.wait_for_load_state("networkidle", timeout=1500)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    # финальный проход вниз ограниченным числом шагов и по стабильности
                    stable_rounds = 0
                    last_count = await get_lazy_img_count()
                    for _ in range(40):
                        await page.evaluate("() => window.scrollBy(0, Math.floor(window.innerHeight * 0.5))")
                        await self._human_pause(0.5, 1.0)
                        new_count = await get_lazy_img_count()
                        if new_count > last_count:
                            last_count = new_count
                            stable_rounds = 0
                        else:
                            stable_rounds += 1
                        if stable_rounds >= 6:
                            break
                except Exception:
                    pass

                # Главное: aria-label="商品大图" или заданный XPath
                main_src = None
                try:
                    main_src = await page.evaluate("() => { const el = document.querySelector('[aria-label=\"商品大图\"] img, [aria-label=\"商品大图\"]'); return el ? (el.getAttribute('src') || el.getAttribute('data-src') || '') : '' }")
                except Exception:
                    main_src = None
                if not main_src:
                    try:
                        el = await page.query_selector('xpath=/html/body/div[4]/div/div[1]/div[1]/div/div[2]/img')
                        if el:
                            main_src = await el.get_attribute('src') or await el.get_attribute('data-src')
                    except Exception:
                        pass
                if main_src:
                    main_src = main_src.strip()
                    # Сокращаем pddpic ссылки у главного изображения: убираем query-параметры
                    try:
                        pu = urlparse(main_src)
                        host = (pu.hostname or '').lower()
                        if host.endswith('pddpic.com'):
                            main_src = f"{pu.scheme}://{pu.netloc}{pu.path}"
                    except Exception:
                        pass
                    if main_src and main_src not in main_images:
                        main_images.append(main_src)
                # Дополнительные: img.pdd-lazy-image.loaded[role="img"][aria-label="查看图片"],
                # где data-src не начинается с https://promotion
                js_extra_imgs = """
                    () => {
                      const arr = Array.from(document.querySelectorAll('img.pdd-lazy-image.loaded[role="img"][aria-label="查看图片"]'));
                      const urls = [];
                      for (const img of arr) {
                        const ds = (img.getAttribute('data-src') || '').trim();
                        const s = (img.getAttribute('src') || '').trim();
                        const candidate = ds || s;
                        if (!candidate) continue;
                        if (candidate.startsWith('https://promotion')) continue;
                        urls.push(candidate);
                      }
                      return Array.from(new Set(urls));
                    }
                """
                extra_imgs = await page.evaluate(js_extra_imgs)
                if isinstance(extra_imgs, list):
                    for u in extra_imgs:
                        if not isinstance(u, str):
                            continue
                        s = u.strip()
                        if not s:
                            continue
                        # Сокращаем pddpic ссылки: убираем query-параметры
                        try:
                            pu = urlparse(s)
                            host = (pu.hostname or '').lower()
                            if host.endswith('pddpic.com'):
                                s = f"{pu.scheme}://{pu.netloc}{pu.path}"
                        except Exception:
                            pass
                        if s not in main_images:
                            main_images.append(s)
                # Фильтрация изображений только по разрешению (>=500x500)
                async def _passes_filters(client: httpx.AsyncClient, url: str) -> bool:
                    try:
                        pu = urlparse(url)
                        host = (pu.hostname or '').lower()
                        # Для доменов pddpic.com допускаем доверительную проверку по параметрам URL
                        if host.endswith('pddpic.com'):
                            # Если в пути есть imageView2 и указан w>=500 — считаем подходящим без загрузки
                            if '/imageView2/2/w/' in url or '/imageMogr2/thumbnail/' in url:
                                try:
                                    # Простая эвристика по числу после w/
                                    import re
                                    m = re.search(r"/w/(\d+)", url)
                                    if m and int(m.group(1)) >= 500:
                                        return True
                                except Exception:
                                    pass
                            # Иначе продолжаем обычную проверку
                        # Проверка размеров изображения: скачиваем и проверяем геометрию
                        rr = await client.get(url, timeout=25)
                        content = rr.content
                        if not content:
                            return False
                        try:
                            im = Image.open(BytesIO(content))
                            w, h = im.size
                            if w < 500 or h < 500:
                                return False
                        except Exception:
                            # Если не смогли распарсить, но домен pddpic.com и известные параметры — примем
                            if host.endswith('pddpic.com'):
                                return True
                            return False
                        return True
                    except Exception:
                        return False

                filtered_images: List[str] = []
                try:
                    # Добавим заголовки для успешной отдачи изображений (UA/Referer/Accept)
                    default_headers = {
                        "User-Agent": self.user_agent or DESKTOP_UA_POOL[0],
                        "Referer": full_url,
                        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9",
                    }
                    async with httpx.AsyncClient(follow_redirects=True, headers=default_headers) as client:
                        tasks = [
                            _passes_filters(client, u) for u in main_images
                        ]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        for u, ok in zip(main_images, results):
                            if isinstance(ok, bool) and ok:
                                filtered_images.append(u)
                    main_images = filtered_images
                except Exception:
                    pass
                if debug:
                    print(f"[DEBUG] Собраны изображения после фильтрации: {len(main_images)}")
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Не удалось получить фотографии: {e}")

            # 5) Дополнительно пробуем старое описание (fallback), если extra пуст
            description = extra_desc
            if not description:
                try:
                    await page.wait_for_selector("xpath=/html/body/div[4]/div/div[2]/div[6]/div/span/span/span", timeout=3000)
                    desc_el = await page.query_selector("xpath=/html/body/div[4]/div/div[2]/div[6]/div/span/span/span")
                    if desc_el:
                        fallback = await desc_el.text_content()
                        if fallback:
                            description = fallback.strip()
                except Exception:
                    pass
            if debug:
                print(f"[DEBUG] Итоговое описание: {description}")

            # Закрытие браузера: оставляем открытым при отладке, если включено
            if debug:
                print("[DEBUG] Окно браузера оставлено открытым (DEBUG_MODE=True)")
            elif not getattr(settings, 'PLAYWRIGHT_KEEP_BROWSER_OPEN', False):
                await context.close()
                await browser.close()
            if debug and html_source:
                print(f"[DEBUG] HTML (начало): {html_source[:600]}")
        # Извлекаем product_id из URL (goods_id=...)
        product_id = None
        try:
            parsed = urlparse(full_url)
            from urllib.parse import parse_qs
            q = parse_qs(parsed.query)
            for key in ["goods_id", "id", "item_id", "goodsId"]:
                if key in q:
                    pid = q[key][0]
                    if pid and pid.isdigit():
                        product_id = pid
                        break
        except Exception:
            product_id = None

        # Разносим изображения: первая — main_imgs, остальные — detail_imgs
        split_main_imgs: List[str] = []
        split_detail_imgs: List[str] = []
        if main_images:
            split_main_imgs = [main_images[0]]
            if len(main_images) > 1:
                split_detail_imgs = main_images[1:]
        # Собираем минимальный JSON по ТЗ
        pdd_minimal = {
        "url": full_url,
        "product_id": product_id or "",
        "description": (title or "") + (" " + description if description else ""),
        "images": split_main_imgs + split_detail_imgs,
        "price": price or "",
        }

        result["data"] = {
            "url": full_url,
            "item_id": product_id,
            "title": title or "",
            "price": price or "",
            "price_info": {"price": price or ""},
            "product_props": [],
            "main_imgs": split_main_imgs,
            "detail_imgs": split_detail_imgs,
            "details": description or "",
            "shop_info": {},
            "is_item_onsale": True,
            "sku_props": [],
            "skus": [],
            "promotions": None,
            "side_sales_tip": "",
            # Добавляем минимальный вид для дальнейшей цепочки
            "pdd_minimal": pdd_minimal,
        }
        if debug:
            print(f"[DEBUG] Финальный словарь result['data']: {result['data']}")
        return result



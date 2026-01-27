"""
==============================================================================
SZWEGO API CLIENT - Получение данных товара через API Szwego
==============================================================================
Задача этого модуля — аккуратно интегрировать уже найденный рабочий подход из
проекта `szwego_scraper` в наш бот:

- Авторизация: НЕ через логин/пароль в боте, а через заранее подготовленные cookies
  и user-agent (их придётся периодически обновлять вручную и загружать на сервер).
- Источник данных: API эндпоинт `/commodity/view`.
- Возврат: приводим данные к формату `product_data`, который ожидает наш `Scraper`.

Почему так:
- Этот API намного стабильнее и дешевле по ресурсам, чем браузерный скрапинг.
- В cookies обычно есть критичная cookie `token` (по сути — "токен"), которую
  Szwego использует для авторизации.

Важно:
- Файл cookies содержит секреты. Его НЕЛЬЗЯ коммитить.
- Путь к файлу настраивается через `SZWEGO_COOKIES_FILE`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs
import time

import httpx

from src.core.config import settings
from src.utils.url_parser import Platform

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SzwegoCredentials:
    """
    Данные авторизации для API-запросов Szwego.

    - cookies: словарь `имя_cookie -> значение_cookie`
    - user_agent: User-Agent браузера, из которого были экспортированы cookies
    """

    cookies: dict[str, str]
    user_agent: str
    token_expires_at: int | None  # Unix timestamp (секунды) или None, если неизвестно


class SzwegoApiError(RuntimeError):
    """Ошибка работы с API Szwego (сеть, авторизация, формат ответа)."""


class SzwegoApiClient:
    """
    Асинхронный клиент для Szwego API.

    Основной метод: `fetch_product(url)` → отдаёт структуру `{"code","msg","data"}`
    совместимую со стандартным пайплайном `Scraper.scrape_product()`.
    """

    def __init__(
        self,
        cookies_file: str | Path | None = None,
        cookies_payload: dict | None = None,
        user_agent: str | None = None,
        base_url: str | None = None,
        timeout_sec: float | None = None,
        trans_lang: str | None = None,
    ) -> None:
        self.base_url = (base_url or getattr(settings, "SZWEGO_BASE_URL", "") or "https://www.szwego.com").rstrip("/")
        self.timeout_sec = float(timeout_sec or getattr(settings, "SZWEGO_TIMEOUT", 30.0) or 30.0)
        self.trans_lang = (trans_lang or getattr(settings, "SZWEGO_TRANS_LANG", "") or "en").strip() or "en"

        # Приоритет: cookies_payload/user_agent (из БД) → cookies_file (legacy).
        if cookies_payload and user_agent:
            self._creds = self._parse_cookies_and_user_agent(cookies_payload, user_agent)
        else:
            self.cookies_file = Path(
                cookies_file
                or getattr(settings, "SZWEGO_COOKIES_FILE", "")
                or "cookies/szwego_cookies.json"
            )
            self._creds = self._load_cookies_and_user_agent(self.cookies_file)

    # ---------------------------------------------------------------------
    # Загрузка cookies/UA
    # ---------------------------------------------------------------------
    @staticmethod
    def _parse_cookies_and_user_agent(cookies_payload: dict, user_agent: str) -> SzwegoCredentials:
        """
        Парсит cookies и user-agent из готового payload (из БД).

        Формат cookies_payload (как в szwego_auth.save_session):
        {
          "cookies": [ { "name": "...", "value": "...", ... }, ... ],
          "user_agent": "...",
          "saved_at": ...,
          "url": ...
        }
        """
        cookies_list = cookies_payload.get("cookies", [])
        if not isinstance(cookies_list, list):
            raise SzwegoApiError("cookies_payload должен содержать список cookies")

        cookies: dict[str, str] = {}
        token_expires_at: int | None = None
        for c in cookies_list:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "").strip()
            value = str(c.get("value") or "").strip()
            if name and value:
                cookies[name] = value
            if name == "token":
                try:
                    raw_expires = c.get("expires")
                    if raw_expires:
                        token_expires_at = int(raw_expires)
                except (ValueError, TypeError):
                    pass

        if not cookies:
            raise SzwegoApiError("Не найдено ни одного валидного cookie в cookies_payload")

        return SzwegoCredentials(
            cookies=cookies,
            user_agent=user_agent.strip(),
            token_expires_at=token_expires_at,
        )

    @staticmethod
    def _load_cookies_and_user_agent(path: Path) -> SzwegoCredentials:
        """
        Загружает cookies и user-agent из json-файла.

        Поддерживаемый формат (как в `szwego_scraper`):
        {
          "cookies": [ { "name": "...", "value": "...", ... }, ... ],
          "user_agent": "...",
          ...
        }

        Также допускаем "сырой" список cookies (list[dict]) — но без user-agent.
        """
        if not path.exists():
            raise SzwegoApiError(
                f"Файл cookies для Szwego не найден: {path}. "
                f"Укажите корректный путь в SZWEGO_COOKIES_FILE и загрузите актуальные cookies."
            )

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise SzwegoApiError(f"Не удалось прочитать cookies-файл {path}: {e}") from e

        cookies_list: list[dict[str, Any]]
        user_agent = ""
        if isinstance(raw, dict) and isinstance(raw.get("cookies"), list):
            cookies_list = raw["cookies"]
            user_agent = str(raw.get("user_agent") or "").strip().strip("'\"")
        elif isinstance(raw, list):
            cookies_list = raw
        else:
            raise SzwegoApiError(
                f"Неподдерживаемый формат cookies-файла {path}. "
                f"Ожидали dict с ключом 'cookies' или list."
            )

        cookies: dict[str, str] = {}
        token_expires_at: int | None = None
        for c in cookies_list:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "").strip()
            value = str(c.get("value") or "").strip()
            if name and value:
                cookies[name] = value
            # Пытаемся извлечь expires конкретно для token (это показатель “протухания”).
            if name == "token":
                try:
                    raw_expires = c.get("expires")
                    # В экспортируемых cookies обычно Unix timestamp (секунды)
                    if isinstance(raw_expires, (int, float)) and raw_expires > 0:
                        token_expires_at = int(raw_expires)
                except Exception:
                    pass

        if not user_agent:
            # Важно: user-agent лучше сохранять вместе с cookies, чтобы запросы были «похожи» на браузер.
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        # Подсказка по типичным проблемам
        critical = ["JSESSIONID", "token"]
        missing = [k for k in critical if k not in cookies]
        if missing:
            logger.warning(
                "[Szwego] В cookies отсутствуют критичные значения: %s. "
                "API может вернуть ошибку авторизации. Обновите cookies/UA.",
                ", ".join(missing),
            )

        return SzwegoCredentials(cookies=cookies, user_agent=user_agent, token_expires_at=token_expires_at)

    def _fail_fast_if_token_expired(self) -> None:
        """
        Fail-fast по expires, без сетевого запроса.

        Важно: expires — это эвристика. Иногда токен “умирает” раньше.
        Поэтому дополнительно ловим ошибки авторизации по ответу API.
        """
        exp = self._creds.token_expires_at
        if not exp:
            return
        now = int(time.time())
        # Небольшой запас, чтобы не ловить граничные случаи на секундах
        grace = int(getattr(settings, "SZWEGO_TOKEN_EXPIRE_GRACE_SEC", 60) or 60)
        if now >= exp - grace:
            raise SzwegoApiError(
                "Токен Szwego протух или истёк (по expires). "
                "Нужно обновить cookies/token и перезапустить бота."
            )

    # ---------------------------------------------------------------------
    # URL parsing
    # ---------------------------------------------------------------------
    @staticmethod
    def extract_product_ids_from_url(url: str) -> tuple[str, str] | None:
        """
        Извлекает `shop_id` и `goods_id` из URL товара Szwego.

        Типичный формат:
        - https://www.szwego.com/static/index.html#/theme_detail/<shop_id>/<goods_id>
        - https://a2018....szwego.com/static/index.html#/theme_detail/<shop_id>/<goods_id>

        Также встречается формат “pc_home/shop_detail”, который является ссылкой на магазин/альбом:
        - https://www.szwego.com/static/index.html?link_type=pc_home&shop_id=...#/shop_detail/<album_id>
        В таком URL нет `goods_id`, поэтому это НЕ ссылка на конкретный товар.
        """
        try:
            parsed = urlparse(url)

            # 1) Основной сценарий: theme_detail обычно живёт в fragment (#/theme_detail/...)
            fragment = (parsed.fragment or "").strip()
            if "theme_detail/" in fragment:
                tail = fragment.split("theme_detail/", 1)[1]
                tail = tail.split("?", 1)[0].split("#", 1)[0].strip()
                parts = [p for p in tail.split("/") if p]
                if len(parts) >= 2:
                    return parts[0], parts[1]

            # Иногда theme_detail может встретиться в полном URL как строка
            if "theme_detail/" in url:
                tail = url.split("theme_detail/", 1)[1]
                tail = tail.split("?", 1)[0].split("#", 1)[0].strip()
                parts = [p for p in tail.split("/") if p]
                if len(parts) >= 2:
                    return parts[0], parts[1]

            # 2) Псевдо-сценарий shop_detail: это ссылка на магазин/альбом (goods_id отсутствует)
            if "shop_detail/" in fragment or "shop_detail/" in url:
                return None

            # Fallback через regex (оба ID часто начинаются с "_")
            m = re.search(r"theme_detail/(_[A-Za-z0-9_-]+)/(_[A-Za-z0-9_-]+)", url)
            if m:
                return m.group(1), m.group(2)
            return None
        except Exception:
            return None

    # ---------------------------------------------------------------------
    # HTTP helpers
    # ---------------------------------------------------------------------
    def _build_headers(self) -> dict[str, str]:
        """
        Заголовки максимально близкие к тем, что использует `szwego_scraper`.
        Это снижает шанс блокировок и странных ответов.
        """
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "dnt": "1",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
            "user-agent": self._creds.user_agent,
            "wego-channel": "net",
            "wego-staging": "0",
            "x-kl-ajax-request": "Ajax_Request",
            "x-wg-language": "zh",
        }

    def _build_client(self) -> httpx.AsyncClient:
        # Важно: follow_redirects=True — иногда полезно, если API пробует редиректить на логин.
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_sec,
            follow_redirects=True,
            headers=self._build_headers(),
            cookies=self._creds.cookies,
        )

    # ---------------------------------------------------------------------
    # API calls
    # ---------------------------------------------------------------------
    async def fetch_product_details(self, album_id: str, item_id: str) -> dict[str, Any]:
        """
        Вызов API `/commodity/view`.

        Параметры:
        - targetAlbumId: ID альбома (в URL это shop_id)
        - itemId: ID товара (goods_id)
        """
        endpoint = "/commodity/view"
        params = {"targetAlbumId": album_id, "itemId": item_id, "transLang": self.trans_lang}

        # Быстрая проверка по expires, чтобы не тратить время на сеть
        self._fail_fast_if_token_expired()

        async with self._build_client() as client:
            try:
                r = await client.get(endpoint, params=params)
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise SzwegoApiError(f"Szwego API вернул HTTP {e.response.status_code} для {endpoint}") from e
            except httpx.RequestError as e:
                raise SzwegoApiError(f"Сетевая ошибка при запросе Szwego API: {e}") from e

            try:
                data = r.json()
            except Exception as e:
                raise SzwegoApiError(f"Не удалось распарсить JSON ответа Szwego API: {e}") from e

        # По образцу `szwego_scraper`: success=True и errcode=0 — успех
        if data.get("success") and data.get("errcode") == 0:
            return data

        errmsg = data.get("errmsg") or data.get("msg") or "Неизвестная ошибка"
        # Если сервер явно сообщает об авторизации — считаем, что токен/куки протухли.
        # Точные формулировки могут меняться, поэтому делаем мягкий матч по ключевым словам.
        try:
            low = str(errmsg).lower()
            if any(k in low for k in ["token", "login", "auth", "session", "unauthor", "权限", "登录"]):
                raise SzwegoApiError(
                    f"Szwego API отклонил авторизацию: {errmsg}. "
                    f"Скорее всего, cookies/token протухли — нужно обновить."
                )
        except SzwegoApiError:
            raise
        except Exception:
            pass
        raise SzwegoApiError(
            f"Szwego API вернул ошибку: {errmsg}. "
            f"Частая причина: устарели cookies (token/JSESSIONID) или не совпадает User-Agent."
        )

    # ---------------------------------------------------------------------
    # Adapter: Szwego -> product_data
    # ---------------------------------------------------------------------
    @staticmethod
    def _as_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            s = str(value).strip().replace(",", ".")
            if not s:
                return None
            return float(s)
        except Exception:
            return None

    @staticmethod
    def _dedupe_urls(urls: Any) -> list[str]:
        if not isinstance(urls, list):
            return []
        out: list[str] = []
        seen = set()
        for u in urls:
            if not isinstance(u, str):
                continue
            u = u.strip()
            if not u.startswith("http"):
                continue
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    def _commodity_to_product_data(self, commodity: dict[str, Any], album_id: str, original_url: str) -> dict[str, Any]:
        """
        Приводит `commodity` из `/commodity/view` к нашему `product_data`.
        Делаем минимально необходимый набор полей, чтобы весь дальнейший пайплайн работал стабильно.
        """
        goods_id = str(commodity.get("goods_id") or commodity.get("selfGoodsId") or "").strip()
        title = str(commodity.get("title") or "").strip()

        # Цена: пробуем основные поля (по логике из `szwego_scraper`)
        price = None
        price_arr = commodity.get("priceArr")
        if isinstance(price_arr, list) and price_arr:
            if isinstance(price_arr[0], dict):
                price = self._as_float(price_arr[0].get("value"))
        if price is None:
            price = self._as_float(commodity.get("itemNamePrice"))
        if price is None:
            price = self._as_float(commodity.get("optimaPrice"))
        if price is None:
            price = self._as_float(commodity.get("itemPrice"))

        # Изображения: imgsSrc предпочтительнее (обычно оригиналы)
        images = self._dedupe_urls(commodity.get("imgsSrc") or []) or self._dedupe_urls(commodity.get("imgs") or [])

        # Важно: в нашем пайплайне поле `details` используется как текст описания товара.
        # В API у Szwego часто есть только "title" (который в реальности может быть многострочным описанием).
        details = title

        product_data: dict[str, Any] = {
            "_platform": Platform.SZWEGO,
            "title": title,
            "details": details,
            "price": price if price is not None else "",
            "price_info": {"price": price} if price is not None else {},
            "main_imgs": images,
            "detail_imgs": images,
            "skus": [],  # В API-формате Szwego SKU обычно нет — оставляем пустым списком
            "product_url": original_url,
            # Доп. поля (не обязательны, но полезны в отладке/логах)
            "szwego": {
                "shop_id": album_id,
                "goods_id": goods_id,
                "shop_name": commodity.get("shop_name", ""),
                "mark_code": commodity.get("mark_code", ""),
                "tags": commodity.get("tags", []),
                "link": commodity.get("link", ""),
            },
        }
        return product_data

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    async def fetch_product(self, url: str) -> dict[str, Any]:
        """
        Высокоуровневый метод для `Scraper.scrape_product`.
        Возвращает структуру, совместимую с тем, как мы обрабатываем TMAPI/PDD:
        {"code": 200/..., "msg": "...", "data": product_data}
        """
        ids = self.extract_product_ids_from_url(url)
        if not ids:
            # Улучшаем диагностику: shop_detail — это не конкретный товар
            try:
                parsed = urlparse(url)
                fragment = (parsed.fragment or "")
                fragment_l = fragment.lower()
                query = parse_qs(parsed.query or "")
                if "shop_detail/" in fragment or "shop_detail/" in url:
                    shop_id = (query.get("shop_id") or [""])[0]
                    msg = (
                        "Ссылка выглядит как страница магазина/альбома (shop_detail), а не конкретного товара.\n"
                        "Для парсинга товара нужна ссылка вида:\n"
                        "  https://www.szwego.com/static/index.html#/theme_detail/SHOP_ID/GOODS_ID\n"
                    )
                    if shop_id:
                        msg += f"\nПодсказка: в вашей ссылке shop_id={shop_id}"
                    return {"code": 400, "msg": msg, "data": {}}

                # Частая ошибка: ссылка обрезана/неполная (например, '#/theme_det' вместо '#/theme_detail/.../...').
                if "theme_det" in fragment_l and "theme_detail" not in fragment_l:
                    msg = (
                        "Похоже, ссылка на товар обрезана/неполная (в конце '#/theme_det').\n"
                        "Нужна полная ссылка на товар вида:\n"
                        "  https://www.szwego.com/static/index.html#/theme_detail/SHOP_ID/GOODS_ID\n"
                    )
                    shop_id = (query.get("shop_id") or [""])[0]
                    if shop_id:
                        msg += f"\nПодсказка: в вашей ссылке shop_id={shop_id}"
                    return {"code": 400, "msg": msg, "data": {}}
            except Exception:
                pass

            return {"code": 400, "msg": "Не удалось извлечь shop_id и goods_id из URL Szwego", "data": {}}

        album_id, item_id = ids

        try:
            raw = await self.fetch_product_details(album_id=album_id, item_id=item_id)
            commodity = (raw.get("result") or {}).get("commodity") or {}
            if not isinstance(commodity, dict) or not commodity:
                return {"code": 502, "msg": "Szwego API вернул пустой объект товара", "data": {}}

            product_data = self._commodity_to_product_data(commodity, album_id=album_id, original_url=url)
            return {"code": 200, "msg": "success", "data": product_data}
        except SzwegoApiError as e:
            logger.error("[Szwego] Ошибка API: %s", e)
            return {"code": 401, "msg": str(e), "data": {}}




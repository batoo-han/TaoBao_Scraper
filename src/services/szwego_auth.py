"""
Сервис авторизации Szwego с локальным решением слайдер-капчи.

Основная идея:
- Пользователь вводит логин/пароль через Telegram-бота.
- Мы выполняем вход в браузере (Playwright), решаем слайдер-капчу,
  затем сохраняем cookies + user-agent в JSON файл.
- Эти cookies используются для API-запросов Szwego.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

from src.core.config import settings
from src.db.session import get_session
from src.db.models import User, SzwegoAuth
from src.utils.crypto import encrypt_text, decrypt_text
from src.services.slider_captcha_solver import find_slider_offset

logger = logging.getLogger(__name__)


@dataclass
class SzwegoAuthResult:
    """
    Результат попытки авторизации.
    """

    success: bool
    message: str
    cookies_path: Optional[str] = None
    user_agent: Optional[str] = None
    status_code: Optional[str] = None  # machine-readable статус для логики бота/уведомлений


async def notify_szwego_admin(
    status_code: str,
    user_id: int,
    username: Optional[str],
    details: str = "",
) -> None:
    """
    Отправляет уведомление админу о результате авторизации SZWEGO.

    Args:
        status_code: Код статуса (success/invalid_credentials/captcha_failed/service_unavailable/unknown_error)
        user_id: ID пользователя Telegram
        username: Username пользователя (опционально)
        details: Дополнительные детали (сообщение об ошибке, stacktrace и т.п.)
    """
    mode = (getattr(settings, "SZWEGO_ADMIN_NOTIFY_MODE", "") or "errors").strip().lower()
    if mode == "none":
        return

    # Для режима "errors" отправляем только неудачные попытки.
    if mode == "errors" and status_code == "success":
        return

    # Определяем chat_id для уведомлений (используем ADMIN_CHAT_ID).
    chat_id_raw = (getattr(settings, "ADMIN_CHAT_ID", "") or "").strip()
    if not chat_id_raw:
        logger.debug("SZWEGO admin notify: не задан ADMIN_CHAT_ID, пропускаем уведомление")
        return

    try:
        chat_id = int(chat_id_raw)
    except (ValueError, TypeError):
        logger.warning("SZWEGO admin notify: неверный формат chat_id '%s'", chat_id_raw)
        return

    # Формируем сообщение для админа.
    user_info = f"user_id={user_id}"
    if username:
        user_info += f" (@{username})"

    if status_code == "success":
        text = (
            f"✅ <b>SZWEGO авторизация успешна</b>\n\n"
            f"Пользователь: {user_info}\n"
            f"Время: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
            f"Cookies и User-Agent обновлены."
        )
    else:
        status_names = {
            "invalid_credentials": "Неверные учётные данные",
            "captcha_failed": "Не удалось пройти капчу",
            "service_unavailable": "SZWEGO недоступен",
            "unknown_error": "Неизвестная ошибка",
        }
        status_name = status_names.get(status_code, status_code)
        text = (
            f"❌ <b>SZWEGO авторизация неудачна</b>\n\n"
            f"Пользователь: {user_info}\n"
            f"Тип ошибки: {status_name}\n"
            f"Время: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
        )
        if details:
            # Ограничиваем длину details, чтобы не перегружать сообщение.
            details_short = details[:500] + "..." if len(details) > 500 else details
            text += f"\n\nДетали:\n<code>{details_short}</code>"

    # Отправляем через aiogram Bot (если доступен).
    try:
        from aiogram import Bot
        bot = Bot(token=settings.BOT_TOKEN)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        await bot.session.close()
    except Exception as exc:
        logger.error("Не удалось отправить уведомление админу о SZWEGO авторизации: %s", exc)


class SzwegoAuthService:
    """
    Сервис для хранения и обновления авторизационных данных Szwego.
    """

    def __init__(self) -> None:
        self.cookies_dir = Path(
            getattr(settings, "SZWEGO_AUTH_COOKIES_DIR", "") or "cookies/szwego_users"
        )

    async def _ensure_user(self, session, user_id: int, username: Optional[str]) -> User:
        """
        Гарантирует наличие пользователя в БД (для FK).
        """
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            # Используем текущую дату, если пользователь ещё не создан.
            from datetime import datetime
            from zoneinfo import ZoneInfo

            try:
                msk = ZoneInfo("Europe/Moscow")
                now_msk = datetime.now(msk).date()
            except Exception:
                now_msk = datetime.utcnow().date()
            user = User(user_id=user_id, username=username or None, created_at=now_msk)
            session.add(user)
            await session.flush()
        elif username and user.username != username:
            user.username = username
        return user

    async def get_auth(self, user_id: int) -> Optional[SzwegoAuth]:
        """
        Возвращает модель авторизации пользователя (если есть).
        """
        from sqlalchemy import select

        async for session in get_session():
            result = await session.execute(select(SzwegoAuth).where(SzwegoAuth.user_id == user_id))
            return result.scalar_one_or_none()

    async def get_user_cookies_file(self, user_id: int) -> Optional[str]:
        """
        Возвращает путь к cookies файлу, если он есть и существует.
        """
        auth = await self.get_auth(user_id)
        if not auth or not auth.cookies_file:
            return None
        path = Path(auth.cookies_file)
        if path.exists():
            return str(path)
        return None

    async def get_user_session(self, user_id: int) -> tuple[Optional[dict], Optional[str]]:
        """
        Возвращает расшифрованные cookies (в виде dict payload) и User-Agent.

        Приоритет:
        1) cookies_encrypted / user_agent_encrypted (новый формат, в БД);
        2) legacy: cookies_file + user_agent (читаем JSON из файла).
        """
        auth = await self.get_auth(user_id)
        if not auth:
            return None, None

        # Новый формат: данные целиком в БД.
        if auth.cookies_encrypted or auth.user_agent_encrypted:
            try:
                cookies_payload: Optional[dict] = None
                if auth.cookies_encrypted:
                    decrypted = decrypt_text(auth.cookies_encrypted)
                    cookies_payload = json.loads(decrypted)
                ua: Optional[str] = None
                if auth.user_agent_encrypted:
                    ua = decrypt_text(auth.user_agent_encrypted)
                return cookies_payload, ua
            except Exception as exc:
                logger.error("Ошибка при расшифровке cookies/UA из БД для user_id=%s: %s", user_id, exc)

        # Legacy-режим: читаем файл cookies и UA в открытом виде.
        if auth.cookies_file and auth.user_agent:
            path = Path(auth.cookies_file)
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    return payload, auth.user_agent
                except Exception as exc:
                    logger.error("Ошибка при чтении legacy cookies файла %s: %s", path, exc)

        return None, None

    async def get_user_credentials(self, user_id: int) -> tuple[Optional[str], Optional[str]]:
        """
        Возвращает логин и пароль пользователя (в расшифрованном виде).
        """
        auth = await self.get_auth(user_id)
        if not auth:
            return None, None
        login = decrypt_text(auth.login_enc) if auth.login_enc else None
        password = decrypt_text(auth.password_enc) if auth.password_enc else None
        return login, password

    async def save_credentials(
        self,
        *,
        user_id: int,
        username: Optional[str],
        login: str,
        password: str,
    ) -> None:
        """
        Сохраняет зашифрованные логин/пароль пользователя SZWEGO (без запуска авторизации).
        """
        from sqlalchemy import select

        async for session in get_session():
            await self._ensure_user(session, user_id, username)

            result = await session.execute(select(SzwegoAuth).where(SzwegoAuth.user_id == user_id))
            auth = result.scalar_one_or_none()
            if auth is None:
                auth = SzwegoAuth(user_id=user_id)
                session.add(auth)

            auth.login_enc = encrypt_text(login)
            auth.password_enc = encrypt_text(password)
            # При обновлении логина/пароля не трогаем текущую сессию/статус.
            auth.updated_at = int(time.time())
            await session.commit()

    async def save_session(
        self,
        *,
        user_id: int,
        username: Optional[str],
        login: str,
        password: str,
        cookies_payload: dict,
        user_agent: str,
        status: str = "success",
    ) -> None:
        """
        Сохраняет зашифрованные логин/пароль, cookies и User-Agent + статус авторизации.

        cookies_payload — это полный JSON-пакет (как мы пишем в файл): {
            \"cookies\": [...],
            \"user_agent\": \"...\",
            \"saved_at\": ...,
            \"url\": ...
        }
        """
        from sqlalchemy import select
        from datetime import datetime

        async for session in get_session():
            user = await self._ensure_user(session, user_id, username)
            _ = user  # для читаемости, возможно пригодится в будущем

            result = await session.execute(select(SzwegoAuth).where(SzwegoAuth.user_id == user_id))
            auth = result.scalar_one_or_none()
            if auth is None:
                auth = SzwegoAuth(user_id=user_id)
                session.add(auth)

            # Логин/пароль всегда обновляем актуальными значениями.
            auth.login_enc = encrypt_text(login)
            auth.password_enc = encrypt_text(password)

            # Новый формат хранения: зашифрованный JSON с cookies и UA.
            auth.cookies_encrypted = encrypt_text(json.dumps(cookies_payload, ensure_ascii=False))
            auth.user_agent_encrypted = encrypt_text(user_agent)

            # Поддерживаем legacy-поля для обратной совместимости (если где-то ещё используется путь к файлу).
            auth.user_agent = user_agent

            # Статус авторизации.
            auth.last_status = status
            auth.last_status_at = datetime.utcnow()
            auth.updated_at = int(time.time())

            await session.commit()

    async def update_status(
        self,
        *,
        user_id: int,
        username: Optional[str],
        status: str,
    ) -> None:
        """
        Обновляет только статус авторизации Szwego (без изменения cookies/UA).
        """
        from sqlalchemy import select
        from datetime import datetime

        async for session in get_session():
            await self._ensure_user(session, user_id, username)

            result = await session.execute(select(SzwegoAuth).where(SzwegoAuth.user_id == user_id))
            auth = result.scalar_one_or_none()
            if auth is None:
                auth = SzwegoAuth(user_id=user_id)
                session.add(auth)

            auth.last_status = status
            auth.last_status_at = datetime.utcnow()
            auth.updated_at = int(time.time())

            await session.commit()

    def _build_cookies_path(self, user_id: int) -> Path:
        """
        Формирует путь к cookies файлу пользователя.
        """
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        return self.cookies_dir / f"szwego_{user_id}.json"

    async def authorize_user(
        self,
        *,
        user_id: int,
        username: Optional[str],
        login: str,
        password: str,
        save_to_db: bool = True,
        debug_dump_dir: str | None = None,
    ) -> SzwegoAuthResult:
        """
        Авторизация пользователя через Playwright + локальная капча.
        """
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            return SzwegoAuthResult(
                False,
                f"Playwright не установлен или недоступен: {exc}",
            )
        login = (login or "").strip()
        password = (password or "").strip()
        if not login or not password:
            return SzwegoAuthResult(False, "Логин и пароль обязательны.")
        if not (getattr(settings, "SZWEGO_AUTH_ENCRYPTION_KEY", "") or "").strip():
            return SzwegoAuthResult(
                False,
                "Не задан SZWEGO_AUTH_ENCRYPTION_KEY в .env. "
                "Сначала настройте ключ шифрования.",
            )

        #raw_login_url = getattr(settings, "SZWEGO_LOGIN_URL", "") or "https://www.szwego.com/static/index.html?link_type=pc_login#/password_login"
        raw_login_url = "https://www.szwego.com/static/index.html?link_type=pc_login#/password_login"
        login_url = self._normalize_url(raw_login_url)
        page_timeout = int(getattr(settings, "PLAYWRIGHT_PAGE_TIMEOUT_MS", 60000) or 60000)
        auth_timeout = int(getattr(settings, "SZWEGO_AUTH_TIMEOUT_SEC", 120) or 120)
        max_captcha_attempts = int(getattr(settings, "SZWEGO_CAPTCHA_MAX_ATTEMPTS", 3) or 3)

        try:
            async with async_playwright() as p:
                browser = await self._launch_browser(p)

                # Подбираем User-Agent для авторизации.
                # При первой авторизации выбираем случайный UA из пула,
                # при последующих — можем переиспользовать сохранённый из БД (если он есть).
                user_agent_override: Optional[str] = None
                # Получаем пул UA (если не задан в .env, используется дефолтное значение из конфига)
                ua_pool_raw = getattr(settings, "SZWEGO_UA_POOL", "") or ""
                ua_pool_raw = ua_pool_raw.strip()
                if ua_pool_raw:
                    # Строка вида "ua1,ua2,ua3" → список.
                    candidates = [ua.strip() for ua in ua_pool_raw.split(",") if ua.strip()]
                    if candidates:
                        user_agent_override = random.choice(candidates)

                context_kwargs: dict = {
                    "locale": getattr(settings, "PLAYWRIGHT_LOCALE", "zh-CN"),
                    "timezone_id": getattr(settings, "PLAYWRIGHT_TIMEZONE", "Asia/Shanghai"),
                }
                if user_agent_override:
                    context_kwargs["user_agent"] = user_agent_override

                context = await browser.new_context(**context_kwargs)
                page = await context.new_page()
                page.set_default_timeout(page_timeout)
                
                # Обработка диалогов браузера (permission prompts) - автоматически отклоняем
                def handle_dialog(dialog):
                    logger.info("Обнаружен диалог браузера: %s, автоматически отклоняем", dialog.type)
                    dialog.dismiss()
                
                page.on("dialog", handle_dialog)

                logger.info("Открываем страницу логина: %s", login_url)
                await page.goto(login_url, wait_until="domcontentloaded")
                logger.info("Страница загружена, текущий URL: %s", page.url)
                await self._debug_dump(page, debug_dump_dir, "after_goto")
                
                await self._fill_credentials(page, login, password)
                logger.info("Форма заполнена и отправлена, текущий URL: %s", page.url)
                await self._debug_dump(page, debug_dump_dir, "after_fill")
                
                # Ждём появления капчи после отправки формы
                logger.info("Ждём появления капчи (3 сек)...")
                await asyncio.sleep(3)
                logger.info("Текущий URL после ожидания: %s", page.url)
                
                # Делаем скриншот перед проверкой капчи
                await self._debug_dump(page, debug_dump_dir, "before_captcha_check")
                
                # Диагностика: выводим все iframe на странице
                try:
                    frames = page.frames
                    logger.info("Найдено iframe на странице: %d", len(frames))
                    for i, frame in enumerate(frames):
                        try:
                            frame_url = frame.url
                            frame_name = frame.name or "(без имени)"
                            logger.info("  iframe[%d]: name=%s, url=%s", i, frame_name, frame_url)
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("Не удалось получить список iframe: %s", e)

                # Добавляем скрипт для перехвата селекторов в iframe с капчей
                captcha_frame = await self._find_captcha_frame(page)
                if captcha_frame:
                    logger.info("Добавляем скрипт для перехвата селекторов в iframe с капчей")
                    try:
                        await captcha_frame.evaluate("""
                            (function() {
                                window.captchaSelectors = {
                                    clicked: [],
                                    hovered: [],
                                    dragged: []
                                };
                                
                                function getSelector(element) {
                                    if (!element) return null;
                                    if (element.id) return '#' + element.id;
                                    if (element.className) {
                                        const classes = element.className.split(' ').filter(c => c).join('.');
                                        if (classes) return '.' + classes;
                                    }
                                    return element.tagName.toLowerCase();
                                }
                                
                                document.addEventListener('click', function(e) {
                                    const selector = getSelector(e.target);
                                    window.captchaSelectors.clicked.push({
                                        selector: selector,
                                        id: e.target.id || '',
                                        className: e.target.className || '',
                                        tagName: e.target.tagName,
                                        timestamp: Date.now()
                                    });
                                    console.log('[CAPTCHA SELECTOR] Clicked:', selector, e.target.id, e.target.className);
                                }, true);
                                
                                let dragStartElement = null;
                                document.addEventListener('mousedown', function(e) {
                                    dragStartElement = e.target;
                                    const selector = getSelector(e.target);
                                    window.captchaSelectors.dragged.push({
                                        action: 'mousedown',
                                        selector: selector,
                                        id: e.target.id || '',
                                        className: e.target.className || '',
                                        timestamp: Date.now()
                                    });
                                    console.log('[CAPTCHA SELECTOR] MouseDown:', selector, e.target.id);
                                }, true);
                                
                                document.addEventListener('mouseup', function(e) {
                                    if (dragStartElement) {
                                        const selector = getSelector(e.target);
                                        window.captchaSelectors.dragged.push({
                                            action: 'mouseup',
                                            selector: selector,
                                            id: e.target.id || '',
                                            className: e.target.className || '',
                                            timestamp: Date.now()
                                        });
                                        console.log('[CAPTCHA SELECTOR] MouseUp:', selector);
                                        dragStartElement = null;
                                    }
                                }, true);
                                
                                console.log('[CAPTCHA SELECTOR] Script injected');
                            })();
                        """)
                        logger.info("✅ Скрипт для перехвата селекторов добавлен")
                        print("[CAPTCHA] ✅ Скрипт для перехвата селекторов добавлен. Двигайте ползунок вручную!")
                    except Exception as e:
                        logger.warning("Не удалось добавить скрипт: %s", e)

                # Если капча появилась — пытаемся решить.
                # Дополнительно обрабатываем ситуацию, когда popup-фрейм капчи
                # (cap_union_new_show) так и не загрузился: в этом случае даём паузу
                # и повторно нажимаем "Войти" до N раз.
                max_submit_retries = int(getattr(settings, "SZWEGO_CAPTCHA_RESUBMIT_MAX", 5) or 5)
                solved = False
                for submit_attempt in range(max_submit_retries):
                    solved = await self._solve_captcha_if_needed(
                        page,
                        max_captcha_attempts,
                        debug_dir=debug_dump_dir,
                    )
                    if solved:
                        break

                    # Проверяем, есть ли настоящий popup-фрейм капчи.
                    has_real_captcha = await self._has_real_captcha_frame(page)
                    if has_real_captcha:
                        # Настоящая капча была, но мы её не смогли решить — выходим
                        # в общий обработчик ошибки ниже.
                        break

                    # Реальный popup-фрейм не появился (видим только шаблон drag_ele или ничего) —
                    # считаем, что капча не догрузилась. Ждём 20–40 сек и повторно жмём "Войти".
                    wait_sec = random.uniform(20.0, 40.0)
                    logger.info(
                        "Фрейм капчи не загрузился (нет cap_union_new_show). Ждём %.1f сек и повторно нажимаем кнопку входа (попытка %d/%d).",
                        wait_sec,
                        submit_attempt + 1,
                        max_submit_retries,
                    )
                    await asyncio.sleep(wait_sec)

                    try:
                        submit_selector = (
                            getattr(settings, "SZWEGO_LOGIN_SUBMIT_SELECTOR", "") or "div.app-login__btn"
                        )
                        await page.wait_for_selector(submit_selector, state="visible", timeout=5000)
                        await page.click(submit_selector)
                        logger.info("Повторно нажали кнопку входа.")
                    except Exception as click_exc:
                        logger.warning("Не удалось повторно нажать кнопку входа: %s", click_exc)
                        break

                if not solved:
                    # Получаем перехваченные селекторы
                    captcha_frame = await self._find_captcha_frame(page)
                    if captcha_frame:
                        try:
                            selectors = await captcha_frame.evaluate("() => window.captchaSelectors || null")
                            if selectors:
                                logger.info("=== ПЕРЕХВАЧЕННЫЕ СЕЛЕКТОРЫ ===")
                                logger.info("Клики: %s", selectors.get("clicked", []))
                                logger.info("Drag: %s", selectors.get("dragged", []))
                                print("\n[CAPTCHA SELECTOR] === ПЕРЕХВАЧЕННЫЕ СЕЛЕКТОРЫ ===")
                                print(f"Клики: {selectors.get('clicked', [])}")
                                print(f"Drag: {selectors.get('dragged', [])}")

                                # Сохраняем в файл
                                if debug_dump_dir:
                                    debug_path = Path(debug_dump_dir)
                                    debug_path.mkdir(parents=True, exist_ok=True)
                                    selectors_file = debug_path / "captcha_selectors.json"
                                    selectors_file.write_text(
                                        json.dumps(selectors, indent=2, ensure_ascii=False),
                                        encoding="utf-8",
                                    )
                                    logger.info("Селекторы сохранены в %s", selectors_file)
                                    print(f"[CAPTCHA SELECTOR] Сохранено в {selectors_file}")
                        except Exception as e:
                            logger.warning("Не удалось получить селекторы: %s", e)

                    # Если DEBUG_MODE, оставляем браузер открытым для ручного тестирования
                    debug_mode = bool(getattr(settings, "DEBUG_MODE", False))
                    if debug_mode:
                        logger.info("Браузер остаётся открытым 30 сек для ручного тестирования")
                        print("[CAPTCHA] Браузер открыт 30 сек. Двигайте ползунок вручную!")
                        await asyncio.sleep(30)
                        # Получаем селекторы после ручного взаимодействия
                        captcha_frame = await self._find_captcha_frame(page)
                        if captcha_frame:
                            try:
                                selectors = await captcha_frame.evaluate("() => window.captchaSelectors || null")
                                if selectors:
                                    print("\n[CAPTCHA SELECTOR] === СЕЛЕКТОРЫ ПОСЛЕ РУЧНОГО ВЗАИМОДЕЙСТВИЯ ===")
                                    print(f"Клики: {selectors.get('clicked', [])}")
                                    print(f"Drag: {selectors.get('dragged', [])}")

                                    # Сохраняем обновлённые селекторы
                                    if debug_dump_dir:
                                        debug_path = Path(debug_dump_dir)
                                        selectors_file = debug_path / "captcha_selectors_manual.json"
                                        selectors_file.write_text(
                                            json.dumps(selectors, indent=2, ensure_ascii=False),
                                            encoding="utf-8",
                                        )
                                        print(f"[CAPTCHA SELECTOR] Сохранено в {selectors_file}")
                            except Exception as e:
                                logger.warning("Не удалось получить селекторы после ручного взаимодействия: %s", e)

                    await self._debug_dump(page, debug_dump_dir, "captcha_failed")
                    if not debug_mode:
                        await browser.close()
                    result = SzwegoAuthResult(
                        False,
                        "Не удалось решить капчу. Проверьте логи для селекторов.",
                        status_code="captcha_failed",
                    )
                    # Обновляем статус в БД и уведомляем админа.
                    if save_to_db:
                        await self.update_status(user_id=user_id, username=username, status="captcha_failed")
                    await notify_szwego_admin(
                        status_code="captcha_failed",
                        user_id=user_id,
                        username=username,
                        details=result.message,
                    )
                    return result

                # Дожидаемся успешного входа.
                ok = await self._wait_login_success(page, auth_timeout)
                if not ok:
                    await self._debug_dump(page, debug_dump_dir, "login_not_confirmed")
                    await browser.close()
                    result = SzwegoAuthResult(
                        False,
                        "Авторизация не подтверждена. Проверьте логин и пароль.",
                        status_code="invalid_credentials",
                    )
                    # Обновляем статус в БД и уведомляем админа.
                    if save_to_db:
                        await self.update_status(user_id=user_id, username=username, status="invalid_credentials")
                    await notify_szwego_admin(
                        status_code="invalid_credentials",
                        user_id=user_id,
                        username=username,
                        details=result.message,
                    )
                    return result

                # Получаем cookies и user-agent.
                cookies = await context.cookies()
                user_agent = await page.evaluate("() => navigator.userAgent")

                # Проверяем наличие обязательных cookies как признак успешного входа
                required_raw = (getattr(settings, "SZWEGO_AUTH_REQUIRED_COOKIES", "") or "").strip()
                required = [c.strip() for c in required_raw.split(",") if c.strip()]
                if required:
                    names = {c.get("name") for c in cookies if isinstance(c, dict)}
                    if not all(name in names for name in required):
                        await self._debug_dump(page, debug_dump_dir, "cookies_missing")
                        await browser.close()
                        result = SzwegoAuthResult(
                            False,
                            "Авторизация не подтверждена: отсутствуют обязательные cookies.",
                            status_code="unknown_error",
                        )
                        if save_to_db:
                            await self.update_status(user_id=user_id, username=username, status="unknown_error")
                        await notify_szwego_admin(
                            status_code="unknown_error",
                            user_id=user_id,
                            username=username,
                            details=result.message,
                        )
                        return result

                cookies_path = self._build_cookies_path(user_id)
                payload = {
                    "cookies": cookies,
                    "user_agent": user_agent,
                    "saved_at": int(time.time()),
                    "url": login_url,
                }
                cookies_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

                # Сохраняем в БД (если нужно).
                if save_to_db:
                    await self.save_session(
                        user_id=user_id,
                        username=username,
                        login=login,
                        password=password,
                        cookies_payload=payload,
                        user_agent=user_agent,
                        status="success",
                    )

                if not getattr(settings, "PLAYWRIGHT_KEEP_BROWSER_OPEN", False):
                    await browser.close()

                result = SzwegoAuthResult(
                    True,
                    "Авторизация успешна. Cookies сохранены.",
                    str(cookies_path),
                    user_agent,
                    status_code="success",
                )
                # Уведомляем админа об успехе (если режим "all").
                await notify_szwego_admin(
                    status_code="success",
                    user_id=user_id,
                    username=username,
                    details="",
                )
                return result
        except Exception as exc:
            if "page" in locals():
                await self._debug_dump(page, debug_dump_dir, "exception")
            logger.error("Ошибка авторизации Szwego: %s", exc, exc_info=True)
            # Пытаемся классифицировать тип ошибки
            msg = str(exc).lower()
            if "timeout" in msg or "timed out" in msg:
                code = "service_unavailable"
            elif "network" in msg or "dns" in msg:
                code = "service_unavailable"
            else:
                code = "unknown_error"
            result = SzwegoAuthResult(False, f"Ошибка авторизации: {exc}", status_code=code)
            # Обновляем статус в БД и уведомляем админа.
            if save_to_db:
                await self.update_status(user_id=user_id, username=username, status=code)
            await notify_szwego_admin(
                status_code=code,
                user_id=user_id,
                username=username,
                details=str(exc),
            )
            return result

    async def _launch_browser(self, p):
        """
        Запускает браузер с безопасными параметрами.

        Логика выбора режима:
        - на серверах без DISPLAY всегда headless (игнорируем настройки, чтобы не упасть);
        - иначе используем настройку SZWEGO_PLAYWRIGHT_HEADLESS;
        - при DEBUG_MODE и PLAYWRIGHT_KEEP_BROWSER_OPEN можно временно выключать headless.
        """
        debug_mode = bool(getattr(settings, "DEBUG_MODE", False))
        no_display = os.name != "nt" and not os.environ.get("DISPLAY")

        if no_display:
            headless = True
        else:
            # Явная настройка из .env, по умолчанию True.
            headless = bool(getattr(settings, "SZWEGO_PLAYWRIGHT_HEADLESS", True))
            # В режиме отладки, если нужно наблюдать браузер, можно принудительно выключить headless.
            if debug_mode and bool(getattr(settings, "PLAYWRIGHT_KEEP_BROWSER_OPEN", False)):
                headless = False
        slow_mo = int(getattr(settings, "PLAYWRIGHT_SLOWMO_MS", 0)) if debug_mode else 0

        chromium_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--no-zygote",
            "--single-process",
        ]
        launch_kwargs = {"headless": headless, "args": chromium_args, "chromium_sandbox": False}
        if slow_mo:
            launch_kwargs["slow_mo"] = slow_mo
        if getattr(settings, "PLAYWRIGHT_PROXY", "").strip():
            launch_kwargs["proxy"] = {"server": settings.PLAYWRIGHT_PROXY.strip()}
        return await p.chromium.launch(**launch_kwargs)

    @staticmethod
    def _normalize_url(value: str) -> str:
        """
        Нормализует URL из .env: убирает кавычки и лишние пробелы.
        """
        value = (value or "").strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1].strip()
        return value

    async def _fill_credentials(self, page: Page, login: str, password: str) -> None:
        """
        Заполняет логин и пароль на странице входа.
        """
        login_selector = getattr(settings, "SZWEGO_LOGIN_USERNAME_SELECTOR", "") or "input[type='text']"
        password_selector = getattr(settings, "SZWEGO_LOGIN_PASSWORD_SELECTOR", "") or "input[type='password']"
        submit_selector = getattr(settings, "SZWEGO_LOGIN_SUBMIT_SELECTOR", "") or "button[type='submit']"

        logger.info("Заполняем форму логина. Селекторы: login=%s, password=%s, submit=%s", login_selector, password_selector, submit_selector)
        
        try:
            await page.wait_for_selector(login_selector, state="visible", timeout=15000)
            logger.info("Поле логина найдено, заполняем")
            await page.fill(login_selector, login)
        except Exception as e:
            logger.error("Не удалось найти/заполнить поле логина: %s", e)
            raise

        try:
            await page.wait_for_selector(password_selector, state="visible", timeout=15000)
            logger.info("Поле пароля найдено, заполняем")
            await page.fill(password_selector, password)
        except Exception as e:
            logger.error("Не удалось найти/заполнить поле пароля: %s", e)
            raise

        await asyncio.sleep(random.uniform(0.2, 0.6))
        
        try:
            await page.wait_for_selector(submit_selector, state="visible", timeout=5000)
            logger.info("Кнопка отправки найдена, кликаем")
            await page.click(submit_selector)
            logger.info("Форма отправлена")
        except Exception as e:
            logger.error("Не удалось найти/кликнуть кнопку отправки: %s", e)
            raise

    async def _wait_login_success(self, page: Page, timeout_sec: int) -> bool:
        """
        Ожидает подтверждения успешного входа.
        """
        success_selector = getattr(settings, "SZWEGO_LOGIN_SUCCESS_SELECTOR", "") or ""
        success_url_part = getattr(settings, "SZWEGO_LOGIN_SUCCESS_URL_PART", "") or ""

        # Если явные настройки не заданы, включаем безопасные эвристики:
        # - переход на страницу альбома (#/album_home) после логина
        # - можно будет дополнить по мере накопления практики
        default_success_parts: list[str] = []
        if not success_selector and not success_url_part:
            default_success_parts = ["#/album_home", "album_home"]

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if success_selector:
                try:
                    if await page.locator(success_selector).first.is_visible():
                        return True
                except Exception:
                    pass
            current_url = page.url or ""
            if success_url_part and success_url_part in current_url:
                return True
            # Эвристика по URL, если не задано явно
            for part in default_success_parts:
                if part and part in current_url:
                    logger.info("Успешный вход определён по URL: %s (совпало с '%s')", current_url, part)
                    return True
            await asyncio.sleep(0.5)
        return False

    async def _solve_captcha_if_needed(self, page: Page, max_attempts: int, debug_dir: str | None = None) -> bool:
        """
        Проверяет наличие слайдер-капчи и решает её, если она появилась.
        """
        captcha_container = getattr(settings, "SZWEGO_CAPTCHA_CONTAINER_SELECTOR", "") or ""
        if not captcha_container:
            # Если контейнер не задан, просто считаем, что капчи нет.
            logger.info("SZWEGO_CAPTCHA_CONTAINER_SELECTOR не задан, пропускаем проверку капчи")
            return True

        logger.info("Проверяем наличие капчи (контейнер: %s)", captcha_container)
        print(f"[CAPTCHA] Проверяем наличие капчи (контейнер: {captcha_container})")
        
        # Пробуем найти капчу с несколькими попытками (она может появляться с задержкой)
        visible = False
        for check_attempt in range(3):
            try:
                root, container = await self._get_captcha_context(page)
                _ = root  # root нужен для совместимости с frame_locator
                # Проверяем наличие элемента в DOM (attached), а не видимость
                try:
                    await container.first.wait_for(state="attached", timeout=3000)
                    # Проверяем count для уверенности
                    count = await container.count()
                    visible = count > 0
                    if visible:
                        logger.info("Капча найдена в DOM (попытка проверки %d/3, count=%d)", check_attempt + 1, count)
                        print(f"[CAPTCHA] ✅ Капча найдена в DOM (попытка {check_attempt + 1}/3, count={count})")
                        break
                except Exception:
                    # Если не удалось проверить через wait_for, пробуем count
                    count = await container.count()
                    visible = count > 0
                    if visible:
                        logger.info("Капча найдена через count (попытка %d/3, count=%d)", check_attempt + 1, count)
                        print(f"[CAPTCHA] ✅ Капча найдена через count (попытка {check_attempt + 1}/3, count={count})")
                        break
            except Exception as e:
                logger.debug("Попытка %d/3: капча не найдена: %s", check_attempt + 1, e)
                print(f"[CAPTCHA] Попытка {check_attempt + 1}/3: капча не найдена: {e}")
                if check_attempt < 2:
                    await asyncio.sleep(1)
        
        if not visible:
            # Пробуем найти капчу по заголовку окна (title содержит "验证码")
            # Сначала проверяем основную страницу
            try:
                title = await page.title()
                if "验证码" in title or "captcha" in title.lower():
                    logger.info("Обнаружен заголовок капчи в title основной страницы: %s", title)
                    print(f"[CAPTCHA] ✅ Обнаружен заголовок капчи в title: {title}")
                    visible = True
            except Exception:
                pass
            
            # Если не нашли на основной странице, проверяем все iframe
            if not visible:
                try:
                    frames = page.frames
                    for frame in frames:
                        try:
                            frame_title = await frame.title()
                            if "验证码" in frame_title or "captcha" in frame_title.lower():
                                logger.info("Обнаружен заголовок капчи в iframe: %s (URL: %s)", frame_title, frame.url)
                                print(f"[CAPTCHA] ✅ Обнаружен заголовок капчи в iframe: {frame_title}")
                                visible = True
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug("Ошибка при проверке заголовков iframe: %s", e)
        
        if not visible:
            logger.info("Капча не видна после всех проверок, считаем что её нет")
            if debug_dir:
                await self._debug_dump(page, debug_dir, "captcha_not_visible")
            return True

        logger.info("Капча обнаружена, начинаем решение (макс. попыток: %d)", max_attempts)
        for attempt in range(max_attempts):
            logger.info("Попытка решения капчи: %d/%d", attempt + 1, max_attempts)
            ok = await self._solve_slider_captcha(page, debug_dir=debug_dir)
            if ok:
                logger.info("Капча решена успешно на попытке %d", attempt + 1)
                return True
            if attempt < max_attempts - 1:
                wait_time = random.uniform(0.8, 1.4)
                logger.info("Попытка не удалась, ждём %.1f сек перед следующей", wait_time)
                await asyncio.sleep(wait_time)
        logger.error("Не удалось решить капчу за %d попыток", max_attempts)
        return False

    async def _find_captcha_frame(self, page: Page):
        """
        Находит iframe с капчей.

        ВАЖНО (по реальным трассам Szwego/Tencent):
        - Фрейм `.../template/drag_ele.html` — это “шаблон”, а реальная капча часто живёт во вложенном iframe
          `cap_union_new_show` (qcloud.com) с именем `tcaptcha_iframe`.
        - Поэтому искать “по title=验证码” недостаточно — нужно приоритизировать фрейм,
          в котором реально присутствуют элементы (`#slideBgWrap`, `#slideBg`, `#slideBlock`, drag*).

        Возвращает Frame или None.
        """
        try:
            frames = page.frames
            logger.info("Ищем iframe с капчей среди %d фреймов", len(frames))
            
            # 1) Самый надёжный признак — наличие DOM-элементов капчи в конкретном фрейме.
            # Считаем “очки” и выбираем лучший фрейм.
            best_frame = None
            best_score = -1

            for frame in frames:
                try:
                    url = (frame.url or "")
                    name = (getattr(frame, "name", "") or "")

                    # Быстрые признаки по URL/имени
                    score = 0
                    if "cap_union_new_show" in url:
                        score += 50
                    if name == "tcaptcha_iframe":
                        score += 40
                    if "turing.captcha" in url:
                        score += 10

                    # Тяжёлые признаки по DOM (count)
                    # count() не требует visibility и хорошо работает даже если элементы hidden.
                    try:
                        if await frame.locator("#slideBgWrap").count() > 0:
                            score += 40
                        if await frame.locator("#slideBg").count() > 0:
                            score += 15
                        if await frame.locator("#slideBlock").count() > 0:
                            score += 20
                        if await frame.locator("#tcaptcha_drag_thumb").count() > 0:
                            score += 20
                        if await frame.locator("#tcaptcha_drag_button").count() > 0:
                            score += 10
                        if await frame.locator("[id*='drag'], [class*='drag']").count() > 0:
                            score += 5
                    except Exception:
                        # На некоторых фреймах доступ к DOM может быть ограничен — просто пропускаем DOM-скоринг
                        pass

                    if score > best_score:
                        best_score = score
                        best_frame = frame
                except Exception:
                    continue

            if best_frame and best_score >= 30:
                try:
                    t = await best_frame.title()
                except Exception:
                    t = ""
                logger.info(
                    "Выбран фрейм капчи по скорингу: score=%d, name=%s, url=%s, title=%s",
                    best_score,
                    getattr(best_frame, "name", "") or "",
                    best_frame.url,
                    t,
                )
                return best_frame

            for frame in frames:
                try:
                    frame_url = frame.url
                    # Проверяем URL iframe (должен содержать turing.captcha)
                    if "turing.captcha" in frame_url or "captcha" in frame_url.lower():
                        logger.info("Найден iframe с капчей по URL: %s", frame_url)
                        # Проверяем заголовок iframe
                        try:
                            frame_title = await frame.title()
                            if "验证码" in frame_title or "captcha" in frame_title.lower() or not frame_title:
                                logger.info("Подтверждено: iframe с заголовком '%s'", frame_title)
                                return frame
                        except Exception:
                            # Если не удалось получить title, но URL подходит - используем его
                            logger.info("Не удалось получить title, но URL подходит")
                            return frame
                except Exception as e:
                    logger.debug("Ошибка при проверке iframe: %s", e)
                    continue
            
            # Если не нашли по URL, пробуем найти по заголовку во всех iframe
            logger.info("Не найдено по URL, ищем по заголовку во всех iframe")
            for frame in frames:
                try:
                    frame_title = await frame.title()
                    if "验证码" in frame_title:
                        logger.info("Найден iframe с капчей по заголовку: %s (URL: %s)", frame_title, frame.url)
                        return frame
                except Exception:
                    continue
            
            logger.warning("Не удалось найти iframe с капчей")
            return None
        except Exception as e:
            logger.error("Ошибка при поиске iframe с капчей: %s", e)
            return None

    async def _get_captcha_context(self, page: Page):
        """
        Возвращает корневой контекст (страница или фрейм) и локатор контейнера капчи.
        Автоматически находит iframe с капчей, если она там находится.
        """
        container_selector = getattr(settings, "SZWEGO_CAPTCHA_CONTAINER_SELECTOR", "") or ""
        frame_selector = getattr(settings, "SZWEGO_CAPTCHA_FRAME_SELECTOR", "") or ""
        
        # Если явно указан селектор iframe - используем его
        if frame_selector:
            try:
                logger.info("Используем явно указанный iframe селектор: %s", frame_selector)
                root = page.frame_locator(frame_selector)
                iframe_locator = root.locator(container_selector).first
                # Не требуем visible: в Tencent капча часто держит элементы hidden, но они уже доступны для скриншота.
                await iframe_locator.wait_for(state="attached", timeout=5000)
                logger.info("Капча найдена в указанном iframe")
                return root, iframe_locator
            except Exception as e:
                logger.warning("Не удалось найти капчу в указанном iframe %s: %s", frame_selector, e)
        
        # Пробуем найти iframe с капчей автоматически
        captcha_frame = await self._find_captcha_frame(page)
        if captcha_frame:
            logger.info("Используем найденный iframe с капчей, работаем напрямую с Frame")
            # Работаем напрямую с Frame - не проверяем видимость, только наличие в DOM
            try:
                locator = captcha_frame.locator(container_selector).first
                # Проверяем, что элемент существует в DOM (attached), даже если он hidden
                await locator.wait_for(state="attached", timeout=5000)
                logger.info("Капча найдена через прямой доступ к Frame (элемент в DOM)")
                # Возвращаем Frame для работы
                return captcha_frame, locator
            except Exception as e:
                logger.warning("Не удалось найти капчу через прямой доступ к Frame: %s", e)
                # Пробуем без проверки состояния - просто проверяем наличие
                try:
                    count = await captcha_frame.locator(container_selector).count()
                    if count > 0:
                        logger.info("Элемент найден в Frame (count=%d), продолжаем без проверки видимости", count)
                        locator = captcha_frame.locator(container_selector).first
                        return captcha_frame, locator
                except Exception as e2:
                    logger.error("Не удалось найти капчу даже через count: %s", e2)
        
        # Сначала пробуем найти на основной странице
        try:
            main_page_locator = page.locator(container_selector).first
            if await main_page_locator.is_visible(timeout=2000):
                logger.info("Капча найдена на основной странице (не в iframe)")
                return page, main_page_locator
        except Exception:
            pass
        
        # Если ничего не найдено, возвращаем основную страницу
        logger.warning("Используем основную страницу для поиска капчи (возможно, капча не найдена)")
        return page, page.locator(container_selector).first

    async def _solve_slider_captcha(self, page: Page, debug_dir: str | None = None) -> bool:
        """
        Решает слайдер-капчу: находит смещение и «тянет» ползунок.
        """
        try:
            root, _ = await self._get_captcha_context(page)
            
            # Определяем, работаем ли мы с Frame или с page/frame_locator
            is_frame = hasattr(root, 'url') and hasattr(root, 'locator') and not hasattr(root, 'goto')
            if is_frame:
                logger.info("Работаем напрямую с Frame объектом")
                captcha_frame = root
            else:
                captcha_frame = None

            bg_selector = getattr(settings, "SZWEGO_CAPTCHA_BG_SELECTOR", "") or ""
            piece_selector = getattr(settings, "SZWEGO_CAPTCHA_PIECE_SELECTOR", "") or ""
            slider_selector = getattr(settings, "SZWEGO_CAPTCHA_SLIDER_SELECTOR", "") or ""

            logger.info(
                "Начинаем решение капчи. Селекторы: bg=%s, piece=%s, slider=%s",
                bg_selector,
                piece_selector,
                slider_selector,
            )
            print(
                f"[CAPTCHA] Начинаем решение капчи. Селекторы: bg={bg_selector}, piece={piece_selector}, slider={slider_selector}"
            )

            if not (bg_selector and piece_selector and slider_selector):
                error_msg = "Не все селекторы капчи заданы в .env"
                logger.error(error_msg)
                print(f"[CAPTCHA ERROR] {error_msg}")
                return False

            # Диагностика: проверяем, что контейнер найден и выводим его содержимое
            container_selector = getattr(settings, "SZWEGO_CAPTCHA_CONTAINER_SELECTOR", "") or ""
            if container_selector:
                try:
                    container_locator = root.locator(container_selector).first
                    container_count = await container_locator.count()
                    logger.info("Контейнер капчи найден: count=%d", container_count)
                    if container_count > 0:
                        # Пробуем получить HTML контейнера для диагностики
                        try:
                            container_html = await container_locator.inner_html()
                            logger.debug("HTML контейнера (первые 500 символов): %s", container_html[:500])
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("Не удалось проверить контейнер: %s", e)
            
            # Добавляем небольшую задержку для загрузки динамических элементов
            await asyncio.sleep(1)
            
            bg_locator = root.locator(bg_selector).first
            piece_locator = root.locator(piece_selector).first
            slider_locator = root.locator(slider_selector).first
            
            # Пробуем альтернативные селекторы, если основные не работают
            # Для ползунка может быть несколько вариантов
            slider_alt_selectors = [
                slider_selector,
                "#tcaptcha_drag_button",  # Контейнер ползунка
                ".tc-drag-thumb",
                "[id*='drag']",
            ]

            # Ждём появления элементов капчи в DOM (attached), даже если они hidden
            # Элементы могут загружаться динамически, поэтому пробуем несколько раз
            # Для скорости достаточно 3 попыток с короткими паузами.
            max_wait_attempts = 3
            elements_found = False
            final_slider_locator = slider_locator
            
            for wait_attempt in range(max_wait_attempts):
                try:
                    # Проверяем наличие элементов через count (быстрее, чем wait_for)
                    bg_count = await bg_locator.count()
                    piece_count = await piece_locator.count()
                    slider_count = await slider_locator.count()
                    
                    logger.info("Попытка %d/%d: bg=%d, piece=%d, slider=%d", wait_attempt + 1, max_wait_attempts, bg_count, piece_count, slider_count)
                    
                    # Если ползунок не найден, пробуем альтернативные селекторы
                    if slider_count == 0 and wait_attempt >= 2:
                        logger.info("Ползунок не найден, пробуем альтернативные селекторы...")
                        for alt_sel in slider_alt_selectors:
                            if alt_sel == slider_selector:
                                continue
                            try:
                                alt_locator = root.locator(alt_sel).first
                                alt_count = await alt_locator.count()
                                if alt_count > 0:
                                    logger.info("Найден ползунок через альтернативный селектор: %s (count=%d)", alt_sel, alt_count)
                                    final_slider_locator = alt_locator
                                    slider_count = alt_count
                                    break
                            except Exception:
                                continue
                    
                    if bg_count > 0 and piece_count > 0 and slider_count > 0:
                        logger.info("Все элементы капчи найдены в DOM")
                        print(f"[CAPTCHA] ✅ Все элементы капчи найдены в DOM (попытка {wait_attempt + 1}/{max_wait_attempts})")
                        elements_found = True
                        break
                    
                    # Если не все найдены, ждём немного и пробуем снова
                    if wait_attempt < max_wait_attempts - 1:
                        await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug("Ошибка при проверке элементов (попытка %d): %s", wait_attempt + 1, e)
                    if wait_attempt < max_wait_attempts - 1:
                        await asyncio.sleep(0.5)
            
            if not elements_found:
                # Последняя попытка через wait_for
                try:
                    logger.info("Последняя попытка через wait_for...")
                    await bg_locator.wait_for(state="attached", timeout=5000)
                    await piece_locator.wait_for(state="attached", timeout=5000)
                    await final_slider_locator.wait_for(state="attached", timeout=5000)
                    elements_found = True
                    logger.info("Элементы найдены через wait_for")
                except Exception as e:
                    error_msg = f"Не удалось найти элементы капчи после {max_wait_attempts} попыток: {e}"
                    logger.error(error_msg)
                    print(f"[CAPTCHA ERROR] {error_msg}")
                    
                    # Диагностика: выводим что найдено
                    try:
                        bg_count = await bg_locator.count()
                        piece_count = await piece_locator.count()
                        slider_count = await final_slider_locator.count()
                        logger.error("Финальная проверка: bg=%d, piece=%d, slider=%d", bg_count, piece_count, slider_count)
                        print(f"[CAPTCHA ERROR] Финальная проверка: bg={bg_count}, piece={piece_count}, slider={slider_count}")
                        
                        # Пробуем найти все элементы с похожими селекторами
                        try:
                            all_bg = await root.locator("[id*='slide'], [id*='bg'], [class*='bg']").count()
                            all_piece = await root.locator("[id*='slide'], [id*='block'], [class*='jpp']").count()
                            all_slider = await root.locator("[id*='drag'], [class*='drag']").count()
                            logger.info("Похожие элементы: bg-like=%d, piece-like=%d, slider-like=%d", all_bg, all_piece, all_slider)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    
                    if debug_dir:
                        await self._debug_dump(page, debug_dir, "captcha_elements_not_found")
                    return False
            
            # Используем найденный селектор ползунка
            slider_locator = final_slider_locator

            # Снимаем скриншоты элементов
            try:
                bg_bytes = await bg_locator.screenshot()
                piece_bytes = await piece_locator.screenshot()
                logger.info("Скриншоты элементов капчи получены: bg=%d байт, piece=%d байт", len(bg_bytes), len(piece_bytes))
                
                # Сохраняем скриншоты элементов для диагностики
                if debug_dir:
                    debug_path = Path(debug_dir)
                    debug_path.mkdir(parents=True, exist_ok=True)
                    (debug_path / "captcha_bg.png").write_bytes(bg_bytes)
                    (debug_path / "captcha_piece.png").write_bytes(piece_bytes)
            except Exception as e:
                logger.error("Ошибка при получении скриншотов элементов капчи: %s", e)
                return False

            from io import BytesIO
            from PIL import Image

            try:
                bg_img = Image.open(BytesIO(bg_bytes))
                piece_img = Image.open(BytesIO(piece_bytes))
                logger.info("Изображения загружены: bg=%dx%d, piece=%dx%d", bg_img.width, bg_img.height, piece_img.width, piece_img.height)
            except Exception as e:
                logger.error("Ошибка при открытии изображений: %s", e)
                return False

            # Начальная позиция ползунка относительно фона: слайдер всегда стартует слева,
            # «дырка» в капче находится правее, поэтому можем ограничить поиск по X.
            slider_box = await slider_locator.bounding_box()
            bg_box = await bg_locator.bounding_box()
            if not slider_box or not bg_box:
                logger.error("Не удалось получить координаты элементов: slider_box=%s, bg_box=%s", slider_box, bg_box)
                return False

            start_offset_x = max(0.0, slider_box["x"] - bg_box["x"])
            # Не ищем левее стартовой позиции и не за пределами фона.
            min_x = int(start_offset_x)
            max_x = int(bg_box["width"] - piece_img.width)

            match = find_slider_offset(
                bg_img,
                piece_img,
                min_confidence=0.15,
                min_x=min_x,
                max_x=max_x,
            )
            if not match:
                logger.warning("Не удалось найти смещение для капчи (алгоритм вернул None)")
                if debug_dir:
                    await self._debug_dump(page, debug_dir, "captcha_no_match")
                return False

            logger.info("Найдено смещение: offset_x=%d, confidence=%.2f", match.offset_x, match.confidence)
            print(f"[CAPTCHA] ✅ Найдено смещение: offset_x={match.offset_x}, confidence={match.confidence:.2f}")

            # Координаты ползунка на странице (мы уже получили slider_box/bg_box выше).
            try:
                logger.info("Координаты (относительно контекста): slider=%s, bg=%s", slider_box, bg_box)
                
                # Если работаем с Frame, нужно получить координаты ИМЕННО того iframe, который соответствует captcha_frame.
                iframe_offset_x = 0.0
                iframe_offset_y = 0.0
                if captcha_frame:
                    try:
                        iframe_element = await self._find_iframe_element_for_frame(page, captcha_frame)
                        if iframe_element:
                            iframe_box = await iframe_element.bounding_box()
                            if iframe_box:
                                iframe_offset_x = float(iframe_box["x"])
                                iframe_offset_y = float(iframe_box["y"])
                                logger.info(
                                    "Найден iframe для captcha_frame: offset=(%.1f, %.1f)", iframe_offset_x, iframe_offset_y
                                )
                    except Exception as e:
                        logger.warning("Не удалось получить координаты iframe для captcha_frame: %s", e)
                
                # Базовые координаты старта (центр ползунка)
                start_x = float(slider_box["x"] + slider_box["width"] / 2 + iframe_offset_x)
                start_y = float(slider_box["y"] + slider_box["height"] / 2 + iframe_offset_y)

                # Делаем несколько вариантов drag вокруг найденного offset_x:
                #   0 (как есть), ±6, ±12 пикселей. Этого достаточно, чтобы «подстроиться» под форму дырки.
                candidate_deltas = [0, -6, 6, -12, 12]
                logger.info(
                    "Будем пробовать несколько вариантов смещения: base_offset=%d, deltas=%s",
                    match.offset_x,
                    candidate_deltas,
                )

                for idx, delta in enumerate(candidate_deltas, start=1):
                    used_offset = match.offset_x + delta
                    # Не выходим за границы фона
                    used_offset = max(0, min(int(bg_box["width"] - piece_img.width), int(used_offset)))
                    logger.info(
                        "Вариант drag %d: base_offset=%d, delta=%d, used_offset=%d",
                        idx,
                        match.offset_x,
                        delta,
                        used_offset,
                    )

                    # Цель по X/Y (координаты страницы)
                    target_x = float(bg_box["x"] + used_offset + piece_img.width / 2 + iframe_offset_x)
                    target_y = start_y  # Y не меняется при горизонтальном drag

                    # В Playwright mouse живёт на Page, а не на Frame.
                    # Для iframe считаем координаты в системе фрейма и переводим в координаты страницы через (iframe_offset_x, iframe_offset_y).
                    if captcha_frame:
                        frame_start_x = float(slider_box["x"] + slider_box["width"] / 2)
                        frame_start_y = float(slider_box["y"] + slider_box["height"] / 2)
                        frame_target_x = float(bg_box["x"] + used_offset + piece_img.width / 2)
                        frame_target_y = float(slider_box["y"] + slider_box["height"] / 2)
                        logger.info(
                            "Начинаем drag в iframe (вариант %d): start=(%.1f, %.1f) -> target=(%.1f, %.1f)",
                            idx,
                            frame_start_x,
                            frame_start_y,
                            frame_target_x,
                            frame_target_y,
                        )
                        print(
                            f"[CAPTCHA] 🎯 Вариант {idx}: drag в iframe start=({frame_start_x:.1f}, {frame_start_y:.1f}) -> target=({frame_target_x:.1f}, {frame_target_y:.1f})"
                        )
                        await self._human_drag_in_iframe(
                            page,
                            iframe_offset_x,
                            iframe_offset_y,
                            frame_start_x,
                            frame_start_y,
                            frame_target_x,
                            frame_target_y,
                        )
                    else:
                        logger.info(
                            "Начинаем drag на странице (вариант %d): start=(%.1f, %.1f) -> target=(%.1f, %.1f)",
                            idx,
                            start_x,
                            start_y,
                            target_x,
                            target_y,
                        )
                        print(
                            f"[CAPTCHA] 🎯 Вариант {idx}: drag на странице start=({start_x:.1f}, {start_y:.1f}) -> target=({target_x:.1f}, {target_y:.1f})"
                        )
                        await self._human_drag(page, start_x, start_y, target_x, target_y)

                    logger.info("Drag завершён (вариант %d)", idx)
                    print(f"[CAPTCHA] ✅ Drag завершён (вариант {idx})")

                    # Сохраняем скриншот каждого варианта только в DEBUG_MODE (иначе сильно тормозит)
                    if debug_dir and bool(getattr(settings, "DEBUG_MODE", False)):
                        await self._debug_dump(page, debug_dir, f"captcha_drag_variant_{idx}")

                    # Небольшая пауза и НАДЁЖНАЯ проверка: капча реально исчезла?
                    await asyncio.sleep(0.35)
                    still_present = await self._is_captcha_still_present(page)
                    logger.info(
                        "После drag варианта %d капча всё ещё на экране: %s",
                        idx,
                        "да" if still_present else "нет",
                    )
                    if not still_present:
                        logger.info("Капча исчезла после варианта %d — считаем, что она решена.", idx)
                        print(f"[CAPTCHA] ✅ Капча исчезла после варианта {idx}")
                        return True
            except Exception as e:
                logger.error("Ошибка при получении координат или выполнении drag: %s", e)
                return False

            # Если мы дошли до этого места и ни один вариант drag не привёл к исчезновению контейнера,
            # считаем, что капчу решить не удалось (она по-прежнему на экране).
            logger.info("После всех вариантов drag капча по-прежнему видна — считаем, что она не решена.")
            return False
        except Exception as e:
            logger.error("Ошибка при решении капчи: %s", e, exc_info=True)
            if debug_dir:
                await self._debug_dump(page, debug_dir, "captcha_exception")
            return False

    async def _human_drag(self, page: Page, start_x: float, start_y: float, end_x: float, end_y: float) -> None:
        """
        Человеко-подобный drag: движение с небольшими шагами и рандомным шумом.
        Работает с основной страницей.
        """
        await page.mouse.move(start_x, start_y)
        await page.mouse.down()

        steps = random.randint(18, 28)
        for step in range(1, steps + 1):
            t = step / steps
            # Плавная кривая ускорения/замедления
            ease = t * t * (3 - 2 * t)
            x = start_x + (end_x - start_x) * ease + random.uniform(-1.2, 1.2)
            y = start_y + (end_y - start_y) * ease + random.uniform(-0.8, 0.8)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.01, 0.03))

        await page.mouse.up()
    
    async def _human_drag_in_iframe(
        self,
        page: "Page",
        iframe_offset_x: float,
        iframe_offset_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> None:
        """
        Человеко-подобный drag внутри iframe.

        В Playwright у `Frame` нет `mouse`, мышь доступна только через `Page.mouse`.
        Поэтому двигаем `Page.mouse`, а координаты iframe-кон텐츠 переводим в координаты страницы
        через (iframe_offset_x, iframe_offset_y).
        """
        px0 = start_x + iframe_offset_x
        py0 = start_y + iframe_offset_y
        px1 = end_x + iframe_offset_x
        py1 = end_y + iframe_offset_y
        await page.mouse.move(px0, py0)
        await page.mouse.down()
        steps = random.randint(18, 28)
        for step in range(1, steps + 1):
            t = step / steps
            ease = t * t * (3 - 2 * t)
            x = px0 + (px1 - px0) * ease + random.uniform(-1.2, 1.2)
            y = py0 + (py1 - py0) * ease + random.uniform(-0.8, 0.8)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.01, 0.03))
        await page.mouse.up()

    async def _find_iframe_element_for_frame(self, page: "Page", target_frame) -> Optional[object]:
        """
        Находит DOM-элемент `<iframe>`, который соответствует `target_frame` (по content_frame().url).
        Нужен, чтобы корректно переводить координаты из фрейма в координаты страницы.
        """
        try:
            if not target_frame:
                return None
            target_url = (getattr(target_frame, "url", "") or "").strip()
            if not target_url:
                return None
            iframes = await page.query_selector_all("iframe")
            for el in iframes:
                try:
                    fr = await el.content_frame()
                    if not fr:
                        continue
                    if (fr.url or "").strip() == target_url:
                        return el
                except Exception:
                    continue
            return None
        except Exception:
            return None

    async def _has_real_captcha_frame(self, page: "Page") -> bool:
        """
        Проверяет, загружен ли настоящий popup-фрейм капчи (cap_union_new_show),
        в отличие от шаблонного iframe drag_ele.html.
        """
        try:
            for fr in page.frames:
                url = (fr.url or "").lower()
                if "cap_union_new_show" in url:
                    return True
        except Exception:
            pass
        return False

    async def _is_captcha_still_present(self, page: "Page") -> bool:
        """
        Надёжная проверка: “капча ещё на экране?”.

        Почему нельзя полагаться только на `#slideBgWrap.count()` в одном старом фрейме:
        - Tencent капча иногда перезагружает/переинициализирует iframe после drag
        - старый Frame остаётся в памяти, а актуальная капча уже в новом Frame
        - в итоге `.count()` в старом фрейме даёт 0 → ложное “капча исчезла”
        """
        try:
            for fr in page.frames:
                try:
                    title = ""
                    try:
                        title = await fr.title()
                    except Exception:
                        title = ""
                    url = (fr.url or "").lower()
                    looks_like_captcha = ("cap_union_new_show" in url) or ("turing.captcha" in url) or ("验证码" in (title or ""))
                    if not looks_like_captcha:
                        continue

                    # Достаточно любого сильного признака, что капча ещё активна
                    if await fr.locator("#tcaptcha_drag_thumb").count() > 0:
                        return True
                    if await fr.locator("#tcaptcha_drag_button").count() > 0:
                        return True
                    if await fr.locator("#slideBlock").count() > 0:
                        return True
                    if await fr.locator("#slideBgWrap").count() > 0:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    async def _debug_dump(self, page: Page, debug_dir: str | None, label: str) -> None:
        """
        Сохраняет скриншот и URL для диагностики.
        """
        if not debug_dir:
            return
        try:
            path = Path(debug_dir)
            path.mkdir(parents=True, exist_ok=True)
            screenshot_path = path / f"{label}.png"
            url_path = path / f"{label}.url.txt"
            # Важно: full_page + ожидание шрифтов на Szwego может “подвисать” на десятки секунд.
            # Для отладки капчи достаточно видимой области и короткого timeout.
            await page.screenshot(path=str(screenshot_path), full_page=False, timeout=8000)
            url_path.write_text(page.url or "", encoding="utf-8")
        except Exception:
            pass


_DEFAULT_AUTH_SERVICE = SzwegoAuthService()


def get_szwego_auth_service() -> SzwegoAuthService:
    """
    Возвращает общий экземпляр сервиса для повторного использования.
    """
    return _DEFAULT_AUTH_SERVICE

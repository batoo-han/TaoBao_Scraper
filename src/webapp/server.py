"""
HTTP-сервер Mimi App: отдаёт статические файлы и REST API для управления настройками.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from aiohttp import web

from src.core.config import settings
from src.services.admin_settings import AdminSettingsService
from src.services.user_settings import get_user_settings_service, UserSettingsService
from src.services.access_control import access_control_service
from src.webapp.auth import WebAppAuthError, WebAppUserContext, validate_init_data

logger = logging.getLogger(__name__)


class MiniAppServer:
    """
    Лёгкий aiohttp-сервер для Telegram Mini App.
    """

    def __init__(
        self,
        *,
        bot_token: str,
        host: str,
        port: int,
        base_path: str,
        static_dir: Path | None = None,
        user_settings_service: UserSettingsService | None = None,
        admin_settings_service: AdminSettingsService | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.host = host or "0.0.0.0"
        self.port = port or 8081
        self.base_path = base_path.rstrip("/") or "/mini-app"
        self.static_dir = static_dir or Path(__file__).parent / "static"
        self.user_settings_service = user_settings_service or get_user_settings_service()
        self.admin_settings_service = admin_settings_service or AdminSettingsService()

        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

        # Отключаем access-логирование для healthcheck запросов
        self._setup_logging_filter()
        self._register_routes()

    # region web server bootstrap ------------------------------------------------
    def _setup_logging_filter(self) -> None:
        """
        Настраивает фильтрацию access-логов для healthcheck запросов.
        Healthcheck запросы не должны засорять логи.
        """
        access_logger = logging.getLogger("aiohttp.access")
        
        # Создаём фильтр, который исключает healthcheck запросы
        class HealthCheckFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                """
                Исключает healthcheck запросы из access-логов.
                Проверяет путь запроса в различных форматах логов aiohttp.
                
                aiohttp форматирует логи как:
                "127.0.0.1 [09/Dec/2025:16:04:32 +0300] "GET /mini-app/health HTTP/1.1" 200 194"
                """
                try:
                    # Получаем отформатированное сообщение
                    if hasattr(record, "getMessage"):
                        msg_str = record.getMessage()
                    else:
                        msg_str = str(record.msg)
                        if record.args:
                            msg_str = msg_str % record.args
                    
                    # Исключаем записи, содержащие /health в пути запроса
                    if "/health" in msg_str:
                        return False
                except Exception:
                    # В случае ошибки не фильтруем запись
                    pass
                
                return True
        
        # Применяем фильтр к access logger
        access_logger.addFilter(HealthCheckFilter())
    
    def _register_routes(self) -> None:
        """
        Настраивает эндпоинты сервера.
        """
        prefix = self.base_path
        self._app.router.add_get(f"{prefix}", self.handle_index)
        self._app.router.add_get(f"{prefix}/", self.handle_index)
        self._app.router.add_get(f"{prefix}/health", self.handle_health)

        self._app.router.add_get(f"{prefix}/api/config", self.handle_get_config)
        self._app.router.add_post(f"{prefix}/api/user", self.handle_update_user)
        self._app.router.add_post(f"{prefix}/api/admin/llm", self.handle_update_admin_llm)
        self._app.router.add_post(f"{prefix}/api/admin/options", self.handle_update_admin_flags)
        self._app.router.add_get(f"{prefix}/api/admin/access", self.handle_get_access_rules)
        self._app.router.add_post(f"{prefix}/api/admin/access", self.handle_update_access_rules)

        static_root = self.static_dir.resolve()
        self._app.router.add_static(f"{prefix}/assets", path=static_root, show_index=False)

    async def start(self) -> None:
        """
        Запускает HTTP-сервер Mimi App.
        """
        if self._runner:
            return

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info(
            "Mimi App запущена по адресу http://%s:%s%s (укажите публичный reverse-proxy для Telegram)",
            self.host,
            self.port,
            self.base_path,
        )

    async def stop(self) -> None:
        """
        Останавливает HTTP-сервер Mimi App.
        """
        if not self._runner:
            return
        await self._runner.cleanup()
        self._runner = None
        self._site = None

    # endregion -----------------------------------------------------------------

    # region helpers ------------------------------------------------------------
    def _is_admin(self, user_id: int) -> bool:
        """
        Проверяет, является ли пользователь администратором.
        """
        admin_id = (getattr(settings, "ADMIN_CHAT_ID", "") or "").strip()
        if not admin_id:
            return False
        try:
            return int(admin_id) == int(user_id)
        except ValueError:
            return False

    def _extract_user(self, request: web.Request) -> WebAppUserContext:
        """
        Валидирует initData из заголовка запроса.
        """
        init_data = (
            request.headers.get("X-Telegram-Init-Data")
            or request.headers.get("x-telegram-init-data")
            or request.query.get("initData")
        )
        if not init_data:
            raise WebAppAuthError("Заголовок X-Telegram-Init-Data обязателен для API Mimi App")
        return validate_init_data(init_data, self.bot_token)

    def _serialize_user_settings(self, user_id: int) -> Dict[str, Any]:
        """
        Преобразует пользовательские настройки к JSON-формату.
        """
        settings_obj = self.user_settings_service.get_settings(user_id)
        return {
            "signature": settings_obj.signature,
            "default_currency": settings_obj.default_currency,
            "exchange_rate": settings_obj.exchange_rate,
            "price_mode": settings_obj.price_mode,
            "daily_limit": settings_obj.daily_limit,
            "monthly_limit": settings_obj.monthly_limit,
        }

    # endregion -----------------------------------------------------------------

    # region route handlers -----------------------------------------------------
    async def handle_index(self, request: web.Request) -> web.StreamResponse:
        """
        Отдаёт основную HTML-страницу Mimi App.
        """
        index_file = self.static_dir / "index.html"
        return web.FileResponse(index_file)

    async def handle_health(self, request: web.Request) -> web.Response:
        """
        Простой healthcheck для мониторинга.
        """
        return web.json_response({"status": "ok"})

    async def handle_get_config(self, request: web.Request) -> web.Response:
        """
        Возвращает агрегированную конфигурацию для Mimi App.
        """
        try:
            user_ctx = self._extract_user(request)
        except WebAppAuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)

        user_payload = self._serialize_user_settings(user_ctx.user_id)
        result: Dict[str, Any] = {
            "user": {
                "profile": user_ctx.as_dict,
                "settings": user_payload,
            },
            "capabilities": {
                "allowed_currencies": ["cny", "rub"],
                "allowed_price_modes": ["simple", "advanced"],
                "allowed_limits": True,
            },
        }

        if self._is_admin(user_ctx.user_id):
            result["role"] = "admin"
            result["admin"] = {
                "settings": self.admin_settings_service.get_payload(),
            }
        else:
            result["role"] = "user"

        return web.json_response(result)

    async def handle_update_user(self, request: web.Request) -> web.Response:
        """
        Обновляет настройки конкретного пользователя.
        """
        try:
            user_ctx = self._extract_user(request)
        except WebAppAuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Неверный JSON"}, status=400)

        target_user_id = user_ctx.user_id
        if user_ctx.user_id and (payload.get("user_id") is not None):
            # Админ может менять любого пользователя
            if not self._is_admin(user_ctx.user_id):
                return web.json_response({"error": "Недостаточно прав для изменения другого пользователя"}, status=403)
            try:
                target_user_id = int(payload.get("user_id"))
            except Exception:
                return web.json_response({"error": "user_id должен быть числом"}, status=400)

        signature = (payload.get("signature") or "").strip()
        currency = (payload.get("currency") or "").lower()
        exchange_rate = payload.get("exchange_rate")
        price_mode = (payload.get("price_mode") or "").strip().lower()
        daily_limit = payload.get("daily_limit")
        monthly_limit = payload.get("monthly_limit")

        if signature and len(signature) > 64:
            return web.json_response({"error": "Подпись не должна превышать 64 символа"}, status=400)

        if signature:
            self.user_settings_service.update_signature(target_user_id, signature)

        if currency:
            if currency not in {"cny", "rub"}:
                return web.json_response({"error": "Доступны только валюты CNY или RUB"}, status=400)
            self.user_settings_service.update_currency(target_user_id, currency)

        if exchange_rate is not None:
            try:
                rate_value = float(exchange_rate)
                if rate_value <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return web.json_response({"error": "Курс должен быть положительным числом"}, status=400)
            self.user_settings_service.update_exchange_rate(target_user_id, rate_value)

        if price_mode:
            if price_mode not in {"simple", "advanced", "inherit"}:
                return web.json_response({"error": "Режим цен должен быть simple, advanced или inherit"}, status=400)
            normalized = "" if price_mode == "inherit" else price_mode
            self.user_settings_service.update_price_mode(target_user_id, normalized)

        if daily_limit is not None or monthly_limit is not None:
            if not self._is_admin(user_ctx.user_id):
                return web.json_response({"error": "Изменять лимиты может только админ"}, status=403)
            def _norm(val):
                if val in (None, ""):
                    return None
                try:
                    iv = int(val)
                    return iv if iv > 0 else None
                except Exception:
                    return None
            dl = _norm(daily_limit)
            ml = _norm(monthly_limit)
            if daily_limit not in (None, "") and dl is None:
                return web.json_response({"error": "daily_limit должен быть положительным числом"}, status=400)
            if monthly_limit not in (None, "") and ml is None:
                return web.json_response({"error": "monthly_limit должен быть положительным числом"}, status=400)
            self.user_settings_service.update_limits(target_user_id, dl, ml)

        updated = self._serialize_user_settings(target_user_id)
        return web.json_response({"status": "ok", "settings": updated})

    async def handle_update_admin_llm(self, request: web.Request) -> web.Response:
        """
        Обновляет настройки провайдеров LLM.
        """
        try:
            user_ctx = self._extract_user(request)
        except WebAppAuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)

        if not self._is_admin(user_ctx.user_id):
            return web.json_response({"error": "Недостаточно прав"}, status=403)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Неверный JSON"}, status=400)

        required_fields = ["default_llm", "yandex_model", "openai_model", "translate_provider", "translate_model"]
        if any(field not in payload for field in required_fields):
            return web.json_response({"error": "Заполните все поля LLM"}, status=400)

        translate_legacy = bool(payload.get("translate_legacy"))
        updated = self.admin_settings_service.update_llm_block(
            default_llm=payload["default_llm"],
            yandex_model=payload["yandex_model"],
            openai_model=payload["openai_model"],
            translate_provider=payload["translate_provider"],
            translate_model=payload["translate_model"],
            translate_legacy=translate_legacy,
        )

        logger.info(
            "Админ %s переключил LLM: default=%s, translate=%s",
            user_ctx.user_id,
            updated.default_llm,
            updated.translate_provider,
        )

        return web.json_response({"status": "ok", "admin_settings": as_dict(updated)})

    async def handle_update_admin_flags(self, request: web.Request) -> web.Response:
        """
        Обновляет рабочие флаги бота.
        """
        try:
            user_ctx = self._extract_user(request)
        except WebAppAuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)

        if not self._is_admin(user_ctx.user_id):
            return web.json_response({"error": "Недостаточно прав"}, status=403)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Неверный JSON"}, status=400)

        forward_channel_id = (payload.get("forward_channel_id") or "").strip()
        if len(forward_channel_id) > 128:
            return web.json_response({"error": "ID канала не должен превышать 128 символов"}, status=400)

        updated = self.admin_settings_service.update_feature_flags(
            convert_currency=bool(payload.get("convert_currency")),
            tmapi_notify_439=bool(payload.get("tmapi_notify_439")),
            debug_mode=bool(payload.get("debug_mode")),
            mock_mode=bool(payload.get("mock_mode")),
            forward_channel_id=forward_channel_id,
            per_user_daily_limit=payload.get("per_user_daily_limit"),
            per_user_monthly_limit=payload.get("per_user_monthly_limit"),
            total_daily_limit=payload.get("total_daily_limit"),
            total_monthly_limit=payload.get("total_monthly_limit"),
        )

        logger.info(
            "Админ %s обновил флаги: convert_currency=%s, notify_439=%s, debug=%s, mock=%s",
            user_ctx.user_id,
            updated.convert_currency,
            updated.tmapi_notify_439,
            updated.debug_mode,
            updated.mock_mode,
        )

        return web.json_response({"status": "ok", "admin_settings": as_dict(updated)})

    async def handle_get_access_rules(self, request: web.Request) -> web.Response:
        """
        Возвращает текущее состояние белого/чёрного списков для Mimi App.
        """
        try:
            user_ctx = self._extract_user(request)
        except WebAppAuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)

        if not self._is_admin(user_ctx.user_id):
            return web.json_response({"error": "Недостаточно прав"}, status=403)

        # Используем текстовый дамп + структурные данные
        summary = access_control_service.get_summary()
        full_dump = access_control_service.dump_lists()

        return web.json_response(
            {
                "status": "ok",
                "summary": summary,
                "details_html": full_dump,
            }
        )

    async def handle_update_access_rules(self, request: web.Request) -> web.Response:
        """
        Обновляет настройки доступа (включение/выключение списков и их содержимого).

        Ожидаемый JSON:
        {
            "whitelist_enabled": bool,
            "blacklist_enabled": bool,
            "add_whitelist_ids": [int],
            "add_whitelist_usernames": [str],
            "remove_whitelist_ids": [int],
            "remove_whitelist_usernames": [str],
            "add_blacklist_ids": [int],
            "add_blacklist_usernames": [str],
            "remove_blacklist_ids": [int],
            "remove_blacklist_usernames": [str]
        }
        Все поля опциональны.
        """
        try:
            user_ctx = self._extract_user(request)
        except WebAppAuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)

        if not self._is_admin(user_ctx.user_id):
            return web.json_response({"error": "Недостаточно прав"}, status=403)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Неверный JSON"}, status=400)

        # Включение/выключение списков
        if "whitelist_enabled" in payload:
            access_control_service.set_whitelist_enabled(bool(payload["whitelist_enabled"]))
        if "blacklist_enabled" in payload:
            access_control_service.set_blacklist_enabled(bool(payload["blacklist_enabled"]))

        # Утилита для безопасного чтения списков из JSON
        def _get_list(name: str) -> list:
            value = payload.get(name) or []
            return value if isinstance(value, list) else []

        # Белый список
        add_w_ids = [int(x) for x in _get_list("add_whitelist_ids") if str(x).isdigit()]
        add_w_names = [str(x).lstrip("@") for x in _get_list("add_whitelist_usernames") if str(x).strip()]
        if add_w_ids or add_w_names:
            access_control_service.add_to_whitelist(add_w_ids, add_w_names)

        rem_w_ids = [int(x) for x in _get_list("remove_whitelist_ids") if str(x).isdigit()]
        rem_w_names = [str(x).lstrip("@") for x in _get_list("remove_whitelist_usernames") if str(x).strip()]
        if rem_w_ids or rem_w_names:
            access_control_service.remove_from_whitelist(rem_w_ids, rem_w_names)

        # Чёрный список
        add_b_ids = [int(x) for x in _get_list("add_blacklist_ids") if str(x).isdigit()]
        add_b_names = [str(x).lstrip("@") for x in _get_list("add_blacklist_usernames") if str(x).strip()]
        if add_b_ids or add_b_names:
            access_control_service.add_to_blacklist(add_b_ids, add_b_names)

        rem_b_ids = [int(x) for x in _get_list("remove_blacklist_ids") if str(x).isdigit()]
        rem_b_names = [str(x).lstrip("@") for x in _get_list("remove_blacklist_usernames") if str(x).strip()]
        if rem_b_ids or rem_b_names:
            access_control_service.remove_from_blacklist(rem_b_ids, rem_b_names)

        logger.info("Админ %s обновил правила доступа через Mimi App", user_ctx.user_id)

        summary = access_control_service.get_summary()
        full_dump = access_control_service.dump_lists()
        return web.json_response(
            {
                "status": "ok",
                "summary": summary,
                "details_html": full_dump,
            }
        )

    # endregion -----------------------------------------------------------------


def as_dict(settings_obj: Any) -> Dict[str, Any]:
    """
    Универсальная утилита для преобразования dataclass в словарь.
    """
    if hasattr(settings_obj, "__dataclass_fields__"):
        from dataclasses import asdict as dataclasses_asdict

        return dataclasses_asdict(settings_obj)
    if isinstance(settings_obj, dict):
        return settings_obj
    raise TypeError("Поддерживаются только dataclass или dict")


"""
Сервис для управления настройками пользователей.
Хранит настройки в JSON файле для простоты (без БД).
"""

import json
import os
from typing import Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from src.core.config import settings


@dataclass
class UserSettings:
    """Настройки пользователя"""
    signature: str = "@annabbox"
    default_currency: str = "cny"  # cny или rub
    exchange_rate: Optional[float] = None  # Курс обмена для рубля
    price_mode: str = ""  # Режим цен: simple или advanced ("" → брать из глобального settings)
    created_at: str = ""  # Дата первой регистрации пользователя (ISO, МСК)
    daily_limit: Optional[int] = None  # Индивидуальный дневной лимит (None → глобальный/без ограничения)
    monthly_limit: Optional[int] = None  # Индивидуальный месячный лимит (None → глобальный/без ограничения)


class UserSettingsService:
    """Сервис для работы с настройками пользователей"""
    
    def __init__(self, storage_file: str = "data/user_settings.json"):
        """
        Инициализация сервиса.
        
        Args:
            storage_file: Путь к файлу для хранения настроек
        """
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        self._settings_cache: dict[int, UserSettings] = {}
        self._load_settings()
    
    def _load_settings(self) -> None:
        """Загружает настройки из файла"""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for user_id_str, settings_dict in data.items():
                        user_id = int(user_id_str)
                        # Обрабатываем exchange_rate: если None или null, устанавливаем None
                        if 'exchange_rate' in settings_dict:
                            rate = settings_dict['exchange_rate']
                            if rate is None or (isinstance(rate, str) and rate.lower() == 'null'):
                                settings_dict['exchange_rate'] = None
                            else:
                                try:
                                    settings_dict['exchange_rate'] = float(rate)
                                except (ValueError, TypeError):
                                    settings_dict['exchange_rate'] = None
                        # Валидируем режим цен
                        pm = (settings_dict.get('price_mode') or '').strip().lower()
                        if pm not in {'simple', 'advanced', ''}:
                            pm = ''
                        settings_dict['price_mode'] = pm

                        # Валидируем дату создания
                        created_at = (settings_dict.get('created_at') or '').strip()
                        settings_dict['created_at'] = created_at

                        # Валидируем лимиты
                        def _normalize_limit(val):
                            try:
                                iv = int(val)
                                return iv if iv > 0 else None
                            except Exception:
                                return None
                        settings_dict['daily_limit'] = _normalize_limit(settings_dict.get('daily_limit'))
                        settings_dict['monthly_limit'] = _normalize_limit(settings_dict.get('monthly_limit'))

                        self._settings_cache[user_id] = UserSettings(**settings_dict)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                # Если файл повреждён, начинаем с пустого кэша
                if hasattr(settings, 'DEBUG_MODE') and settings.DEBUG_MODE:
                    print(f"[UserSettings] Ошибка загрузки настроек: {e}")
                self._settings_cache = {}
        else:
            self._settings_cache = {}
    
    def _save_settings(self) -> None:
        """Сохраняет настройки в файл"""
        data = {}
        for user_id, user_settings in self._settings_cache.items():
            data[str(user_id)] = asdict(user_settings)
        
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            if hasattr(settings, 'DEBUG_MODE') and settings.DEBUG_MODE:
                print(f"[UserSettings] Ошибка сохранения настроек: {e}")
    
    def get_settings(self, user_id: int) -> UserSettings:
        """
        Получает настройки пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            UserSettings: Настройки пользователя (создаются с дефолтами, если не существуют)
        """
        if user_id not in self._settings_cache:
            # Создаём настройки по умолчанию
            default_signature = getattr(settings, 'DEFAULT_SIGNATURE', '@annabbox')
            default_currency = getattr(settings, 'DEFAULT_CURRENCY', 'cny')
            default_price_mode = (getattr(settings, 'PRICE_MODE', 'simple') or 'simple').strip().lower()
            try:
                now_msk = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
            except ZoneInfoNotFoundError:
                now_msk = datetime.now(timezone(timedelta(hours=3))).date().isoformat()
            self._settings_cache[user_id] = UserSettings(
                signature=default_signature,
                default_currency=default_currency,
                price_mode=default_price_mode,
                created_at=now_msk
            )
            self._save_settings()
        else:
            # Обновляем устаревшие записи: создан, но без created_at
            settings_obj = self._settings_cache[user_id]
            if not getattr(settings_obj, "created_at", ""):
                try:
                    settings_obj.created_at = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
                except ZoneInfoNotFoundError:
                    settings_obj.created_at = datetime.now(timezone(timedelta(hours=3))).date().isoformat()
                self._save_settings()
        
        return self._settings_cache[user_id]
    
    def update_signature(self, user_id: int, signature: str) -> UserSettings:
        """
        Обновляет подпись пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            signature: Новая подпись
            
        Returns:
            UserSettings: Обновлённые настройки
        """
        settings_obj = self.get_settings(user_id)
        settings_obj.signature = signature.strip()
        self._save_settings()
        return settings_obj
    
    def update_currency(self, user_id: int, currency: str) -> UserSettings:
        """
        Обновляет валюту пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            currency: Новая валюта (cny или rub)
            
        Returns:
            UserSettings: Обновлённые настройки
        """
        settings_obj = self.get_settings(user_id)
        currency_lower = currency.lower()
        settings_obj.default_currency = currency_lower
        
        # Если переключились на CNY, сбрасываем курс
        if currency_lower == "cny":
            settings_obj.exchange_rate = None
        
        self._save_settings()
        return settings_obj
    
    def update_exchange_rate(self, user_id: int, rate: float) -> UserSettings:
        """
        Обновляет курс обмена для пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            rate: Курс обмена (1 юань = rate рублей)
            
        Returns:
            UserSettings: Обновлённые настройки
        """
        settings_obj = self.get_settings(user_id)
        settings_obj.exchange_rate = rate
        self._save_settings()
        return settings_obj

    def update_price_mode(self, user_id: int, price_mode: str) -> UserSettings:
        """
        Обновляет режим цен для пользователя.
        """
        normalized = (price_mode or "").strip().lower()
        if normalized not in {"simple", "advanced"}:
            normalized = ""
        settings_obj = self.get_settings(user_id)
        settings_obj.price_mode = normalized
        self._save_settings()
        return settings_obj

    def update_limits(self, user_id: int, daily_limit: int | None = None, monthly_limit: int | None = None) -> UserSettings:
        """
        Обновляет индивидуальные лимиты пользователя.
        """
        def _norm(val):
            if val is None:
                return None
            try:
                iv = int(val)
                return iv if iv > 0 else None
            except Exception:
                return None
        settings_obj = self.get_settings(user_id)
        if daily_limit is not None:
            settings_obj.daily_limit = _norm(daily_limit)
        if monthly_limit is not None:
            settings_obj.monthly_limit = _norm(monthly_limit)
        self._save_settings()
        return settings_obj

    def update_price_mode(self, user_id: int, price_mode: str) -> UserSettings:
        """
        Обновляет режим цен для пользователя.
        """
        normalized = (price_mode or "").strip().lower()
        if normalized not in {"simple", "advanced"}:
            normalized = ""
        settings_obj = self.get_settings(user_id)
        settings_obj.price_mode = normalized
        self._save_settings()
        return settings_obj


# Глобальный экземпляр сервиса, чтобы все компоненты (бот и мини-приложение) работали с одними данными
_DEFAULT_SERVICE = UserSettingsService()


def get_user_settings_service() -> UserSettingsService:
    """
    Возвращает общий экземпляр сервиса настроек пользователей для повторного использования.
    """
    return _DEFAULT_SERVICE

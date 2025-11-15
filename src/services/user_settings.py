"""
Сервис для управления настройками пользователей.
Хранит настройки в JSON файле для простоты (без БД).
"""

import json
import os
from typing import Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from src.core.config import settings


@dataclass
class UserSettings:
    """Настройки пользователя"""
    signature: str = "@annabbox"
    default_currency: str = "cny"  # cny или rub
    exchange_rate: Optional[float] = None  # Курс обмена для рубля


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
            self._settings_cache[user_id] = UserSettings(
                signature=default_signature,
                default_currency=default_currency
            )
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


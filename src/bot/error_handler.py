"""
Модуль для обработки ошибок в production режиме.
Обеспечивает дружественные сообщения для пользователей и детальные уведомления для админов.
"""

import logging
import traceback
import os
from datetime import datetime
from typing import Optional
from logging.handlers import RotatingFileHandler
from aiogram import Bot
from aiogram.types import Message

from src.core.config import settings

# Настройка логирования с ротацией
# Максимум 100 МБ на файл, храним 3 файла (итого ~300 МБ / ~3 месяца)
LOG_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, 'bot_errors.log'),
    maxBytes=100 * 1024 * 1024,  # 100 МБ
    backupCount=2,  # Храним текущий + 2 старых файла
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Настраиваем root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Класс для централизованной обработки ошибок"""
    
    # Дружественные сообщения для пользователей
    USER_MESSAGES = {
        'api_error': (
            "😔 Извините, произошла ошибка при получении данных о товаре.\n\n"
            "Возможные причины:\n"
            "• товар недоступен или удалён\n"
            "• временные проблемы с сервисом\n\n"
            "Пожалуйста, попробуйте:\n"
            "1️⃣ Проверить, что ссылка ведёт на доступный товар\n"
            "2️⃣ Повторить попытку через несколько минут\n\n"
            "Наша команда уже уведомлена о проблеме и работает над её устранением. 🛠️"
        ),
        'proxyapi_balance': (
            "⚠️ Баланс ProxyAPI исчерпан.\n\n"
            "Пожалуйста, пополните счёт в личном кабинете ProxyAPI и повторите запрос."
        ),
        'network_error': (
            "😔 Извините, возникли проблемы с подключением к сервису.\n\n"
            "Пожалуйста, попробуйте повторить запрос через 1-2 минуты.\n\n"
            "Наша команда уже уведомлена о проблеме и работает над её устранением. 🛠️"
        ),
        'parsing_error': (
            "😔 Извините, не удалось обработать информацию о товаре.\n\n"
            "Возможные причины:\n"
            "• нестандартная структура страницы товара\n"
            "• неполные данные от продавца\n\n"
            "Пожалуйста, попробуйте другой товар или повторите попытку позже.\n\n"
            "Наша команда уже уведомлена о проблеме. 🛠️"
        ),
        'llm_error': (
            "😔 Извините, произошла ошибка при генерации описания товара.\n\n"
            "Это временная проблема с нашим сервисом генерации текстов.\n\n"
            "Пожалуйста, попробуйте повторить запрос через несколько минут.\n\n"
            "Наша команда уже уведомлена о проблеме и работает над её устранением. 🛠️"
        ),
        'telegram_error': (
            "😔 Извините, возникла проблема при отправке сообщения.\n\n"
            "Возможные причины:\n"
            "• слишком большие изображения\n"
            "• временные ограничения Telegram\n\n"
            "Попробуйте повторить запрос.\n\n"
            "Наша команда уже уведомлена о проблеме. 🛠️"
        ),
        'unknown_error': (
            "😔 Извините, произошла непредвиденная ошибка.\n\n"
            "Мы уже получили информацию о проблеме и работаем над её устранением.\n\n"
            "Пожалуйста, попробуйте:\n"
            "1️⃣ Повторить запрос через несколько минут\n"
            "2️⃣ Попробовать другой товар\n\n"
            "Приносим извинения за неудобства! 🙏"
        )
    }
    
    def __init__(self, bot: Bot, admin_chat_id: Optional[str] = None):
        """
        Инициализация обработчика ошибок.
        
        Args:
            bot: Экземпляр aiogram Bot для отправки уведомлений
            admin_chat_id: ID чата администратора для уведомлений об ошибках
        """
        self.bot = bot
        # Преобразуем admin_chat_id в int если это строка с числом
        if admin_chat_id:
            try:
                self.admin_chat_id = int(admin_chat_id) if isinstance(admin_chat_id, str) else admin_chat_id
            except (ValueError, TypeError):
                logger.warning(f"Invalid ADMIN_CHAT_ID format: {admin_chat_id}. Expected numeric string or int.")
                self.admin_chat_id = None
        else:
            self.admin_chat_id = None
        # Канал для уведомлений о балансе ProxyAPI (аналог TMAPI billing chat)
        raw_proxy_chat = getattr(settings, "PROXYAPI_BILLING_CHAT_ID", "") or ""
        try:
            self.proxy_billing_chat_id = int(raw_proxy_chat) if raw_proxy_chat else None
        except (ValueError, TypeError):
            logger.warning(f"Invalid PROXYAPI_BILLING_CHAT_ID format: {raw_proxy_chat}. Expected numeric string or int.")
            self.proxy_billing_chat_id = None
        self.proxy_notify_402 = bool(getattr(settings, "PROXYAPI_NOTIFY_402", False))
        
    async def handle_error(
        self,
        error: Exception,
        user_message: Message,
        context: str = "",
        error_type: str = "unknown_error",
        request_id: str | None = None,
    ) -> None:
        """
        Обрабатывает ошибку: логирует, уведомляет админа, отправляет дружественное сообщение пользователю.
        
        Args:
            error: Исключение, которое произошло
            user_message: Сообщение пользователя, вызвавшее ошибку
            context: Дополнительный контекст (например, URL товара)
            error_type: Тип ошибки для выбора сообщения пользователю
        """
        # Получаем полный traceback
        tb = traceback.format_exc()
        
        # Формируем информацию об ошибке для логов
        error_info = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_message.from_user.id,
            'username': user_message.from_user.username,
            'chat_id': user_message.chat.id,
            'message_text': user_message.text,
            'error_type': error_type,
            'error_class': error.__class__.__name__,
            'error_message': str(error),
            'context': context,
            'request_id': request_id,
            'traceback': tb
        }
        
        # Логируем ошибку
        logger.error(
            json.dumps(
                {
                    "event": "error",
                    "user_id": user_message.from_user.id,
                    "chat_id": user_message.chat.id,
                    "username": user_message.from_user.username or "unknown",
                    "error_type": error_type,
                    "error_class": error.__class__.__name__,
                    "error_message": str(error),
                    "context": context,
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
        )
        
        # Отправляем дружественное сообщение пользователю
        user_friendly_message = self.USER_MESSAGES.get(error_type, self.USER_MESSAGES['unknown_error'])
        if request_id:
            user_friendly_message += f"\n\nID запроса: <code>{request_id}</code>"
        try:
            await user_message.answer(user_friendly_message)
        except Exception as send_error:
            logger.error(f"Failed to send error message to user: {send_error}")
        
        # Уведомляем администратора
        await self._notify_admin(error_info)
    
    async def _notify_admin(self, error_info: dict) -> None:
        """
        Отправляет уведомление администратору о произошедшей ошибке.
        
        Args:
            error_info: Словарь с информацией об ошибке
        """
        if not self.admin_chat_id:
            logger.warning("Admin chat ID not configured, skipping admin notification")
            return
        
        # Проверяем, является ли это ошибкой TMAPI или ProxyAPI для дополнительных пояснений
        error_message = error_info['error_message']
        tmapi_explanation = self._get_tmapi_error_explanation(error_message)
        proxyapi_explanation = self._get_proxyapi_error_explanation(error_message)
        
        # Формируем красивое сообщение для админа
        admin_message = (
            "🚨 <b>ОШИБКА В БОТЕ</b> 🚨\n\n"
            f"⏰ <b>Время:</b> {error_info['timestamp']}\n"
            f"👤 <b>Пользователь:</b> {error_info['user_id']} "
            f"(@{error_info['username'] or 'unknown'})\n"
            f"💬 <b>Чат:</b> {error_info['chat_id']}\n"
            f"📝 <b>Сообщение:</b> <code>{error_info['message_text'][:100]}</code>\n\n"
            f"❗ <b>Тип ошибки:</b> {error_info['error_type']}\n"
            f"🐛 <b>Класс:</b> <code>{error_info['error_class']}</code>\n"
            f"📄 <b>Описание:</b> <code>{error_info['error_message'][:200]}</code>\n"
        )
        if error_info.get('request_id'):
            admin_message += f"\n🪪 <b>Request ID:</b> <code>{error_info['request_id']}</code>\n"
        
        # Добавляем пояснения для ошибок TMAPI
        if tmapi_explanation:
            admin_message += f"\n💡 <b>Пояснение TMAPI:</b> {tmapi_explanation}\n"
        if proxyapi_explanation:
            admin_message += f"\n💡 <b>Пояснение ProxyAPI:</b> {proxyapi_explanation}\n"
        
        if error_info['context']:
            admin_message += f"\n🔗 <b>Контекст:</b> <code>{error_info['context'][:100]}</code>\n"
        
        # Отправляем traceback отдельным сообщением (если не слишком длинный)
        traceback_preview = error_info['traceback'][:3000]
        
        try:
            await self.bot.send_message(
                chat_id=self.admin_chat_id,
                text=admin_message,
                parse_mode="HTML"
            )
            
            # Отправляем traceback
            await self.bot.send_message(
                chat_id=self.admin_chat_id,
                text=f"<b>Traceback:</b>\n<pre>{traceback_preview}</pre>",
                parse_mode="HTML"
            )
            logger.info(f"Admin notification sent successfully to chat_id: {self.admin_chat_id}")
        except Exception as e:
            error_msg = str(e)
            # Более понятные сообщения об ошибках
            if "chat not found" in error_msg.lower() or "chat_id" in error_msg.lower():
                logger.error(
                    f"Failed to send admin notification: chat not found. "
                    f"Chat ID: {self.admin_chat_id}. "
                    f"Возможные причины:\n"
                    f"1. Бот не был добавлен в чат/не запущен с этим пользователем\n"
                    f"2. ADMIN_CHAT_ID указан неправильно (должен быть числом)\n"
                    f"3. Используется user_id вместо chat_id (для личных чатов они совпадают)\n"
                    f"4. Бот заблокирован пользователем"
                )
            else:
                logger.error(f"Failed to send admin notification: {e}")

        # Дополнительное уведомление ответственному за ProxyAPI (если включено)
        if proxyapi_explanation and self.proxy_notify_402 and self.proxy_billing_chat_id:
            try:
                await self.bot.send_message(
                    chat_id=self.proxy_billing_chat_id,
                    text=f"⚠️ ProxyAPI: {proxyapi_explanation}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление о балансе ProxyAPI: {e}")
    
    @staticmethod
    def _get_tmapi_error_explanation(error_message: str) -> str:
        """
        Возвращает пояснение об ошибке TMAPI согласно документации.
        https://tmapi.top/docs/taobao-tmall/item-detail/get-item-detail-by-id/
        
        Args:
            error_message: Сообщение об ошибке
            
        Returns:
            Пояснение об ошибке или пустая строка
        """
        error_lower = error_message.lower()
        
        # HTTP коды ошибок TMAPI согласно документации
        if '417' in error_message or 'expectation failed' in error_lower:
            return "HTTP 417: Не удалось получить данные. Пожалуйста, попробуйте ещё раз или обратитесь в службу поддержки."
        elif '422' in error_message:
            return "HTTP 422: Ошибка параметра. Проверьте формат запроса."
        elif '439' in error_message:
            return "HTTP 439: Срок действия подписки истёк или на счету недостаточно средств."
        elif '499' in error_message:
            return "HTTP 499: Попробуйте ещё раз или увеличьте время ожидания запроса до 60 секунд."
        elif '500' in error_message:
            return "HTTP 500: Произошла непредвиденная ошибка. Пожалуйста, обратитесь в службу поддержки."
        elif '503' in error_message:
            return "HTTP 503: Превышен лимит одновременных запросов к API. Пожалуйста, уменьшите количество запросов."
        elif 'tmapi' in error_lower:
            return "Ошибка TMAPI - проверьте токен API, баланс и лимиты в консоли TMAPI."
        
        return ""
    
    @staticmethod
    def _get_proxyapi_error_explanation(error_message: str) -> str:
        """
        Возвращает пояснение об ошибке ProxyAPI (например, 402 insufficient balance).
        """
        error_lower = (error_message or "").lower()
        if "insufficient balance" in error_lower or "error code: 402" in error_lower or "402" in error_lower:
            return "HTTP 402: недостаточно средств на счёте ProxyAPI. Пополните баланс в личном кабинете."
        return ""
    
    @staticmethod
    def classify_error(error: Exception, context: str = "") -> str:
        """
        Классифицирует ошибку для выбора подходящего сообщения пользователю.
        
        Args:
            error: Исключение
            context: Контекст (например, где произошла ошибка)
            
        Returns:
            Тип ошибки (ключ для USER_MESSAGES)
        """
        error_class = error.__class__.__name__
        error_message = str(error).lower()
        
        # Специальный кейс: ProxyAPI закончился баланс
        if "insufficient balance" in error_message or "error code: 402" in error_message or "proxyapi" in error_message:
            return 'proxyapi_balance'
        
        # API ошибки
        if any(keyword in error_message for keyword in ['api', 'tmapi', 'proxyapi', '400', '401', '402', '403', '404', '417', '422', '439', '499', '500', '502', '503']):
            return 'api_error'
        
        # Сетевые ошибки
        if any(keyword in error_class.lower() for keyword in ['timeout', 'connection', 'network', 'httpx']):
            return 'network_error'
        
        # Ошибки парсинга
        if any(keyword in error_class.lower() for keyword in ['parse', 'json', 'keyerror', 'valueerror', 'attributeerror']):
            return 'parsing_error'
        
        # Ошибки LLM
        if any(keyword in context.lower() for keyword in ['yandexgpt', 'llm', 'generation']):
            return 'llm_error'
        
        # Ошибки Telegram
        if any(keyword in error_class.lower() for keyword in ['telegram', 'aiogram', 'media']):
            return 'telegram_error'
        
        # Неизвестная ошибка
        return 'unknown_error'


# Глобальный обработчик (будет инициализирован в autoparse.py)
error_handler: Optional[ErrorHandler] = None


async def _test_admin_chat(bot: Bot, chat_id: int) -> bool:
    """
    Проверяет доступность чата администратора, отправляя тестовое сообщение.
    
    Args:
        bot: Экземпляр aiogram Bot
        chat_id: ID чата для проверки
        
    Returns:
        True если чат доступен, False иначе
    """
    try:
        await bot.send_message(
            chat_id=chat_id,
            text="✅ Обработчик ошибок инициализирован. Уведомления включены.",
            parse_mode="HTML"
        )
        return True
    except Exception as e:
        logger.warning(
            f"Не удалось отправить тестовое сообщение в ADMIN_CHAT_ID={chat_id}: {e}. "
            f"Уведомления об ошибках могут не работать. "
            f"Убедитесь, что:\n"
            f"1. Бот запущен и добавлен в чат/написан вам\n"
            f"2. ADMIN_CHAT_ID указан правильно (число)\n"
            f"3. Для личного чата используйте ваш user_id (можно узнать у @userinfobot)"
        )
        return False


def init_error_handler(bot: Bot, admin_chat_id: Optional[str] = None) -> ErrorHandler:
    """
    Инициализирует глобальный обработчик ошибок.
    
    Args:
        bot: Экземпляр aiogram Bot
        admin_chat_id: ID чата администратора
        
    Returns:
        Экземпляр ErrorHandler
    """
    global error_handler
    error_handler = ErrorHandler(bot, admin_chat_id)
    
    # Проверяем доступность чата админа (если задан)
    if error_handler.admin_chat_id:
        # Используем asyncio.run_coroutine_threadsafe или просто логируем, что проверка будет при первой ошибке
        logger.info(f"Admin chat ID configured: {error_handler.admin_chat_id}. Test notification will be sent on first error.")
    
    return error_handler


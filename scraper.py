from tmapi import TmapiClient
from yandex_gpt import YandexGPTClient
from exchange_rate import ExchangeRateClient
from yandex_translate import YandexTranslateClient
from config import settings

class Scraper:
    """
    Класс-оркестратор для сбора информации о товаре, его обработки и генерации поста.
    """
    def __init__(self):
        self.tmapi_client = TmapiClient()  # Клиент для tmapi.top
        self.yandex_gpt_client = YandexGPTClient()  # Клиент для YandexGPT
        self.exchange_rate_client = ExchangeRateClient()  # Клиент для ExchangeRate-API
        self.yandex_translate_client = YandexTranslateClient()  # Клиент для Yandex.Translate

    async def scrape_product(self, url: str):
        """
        Собирает информацию о товаре по URL, генерирует структурированный контент
        и формирует финальный пост.

        Args:
            url (str): URL товара для скрапинга.

        Returns:
            tuple: Кортеж, содержащий сгенерированный текст поста (str) и список URL изображений (list).
        """
        # Получаем данные о товаре через tmapi.top
        api_response = await self.tmapi_client.get_product_info(url)
        
        # TMAPI возвращает структуру: {"code": 200, "msg": "success", "data": {...}}
        # Извлекаем данные о товаре из поля "data"
        if isinstance(api_response, dict) and 'data' in api_response:
            product_data = api_response['data']
        else:
            product_data = api_response
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Данные товара получены: {product_data.get('title', 'N/A')[:50]}...")
        
        exchange_rate = None
        # Если включена конвертация валют, получаем курс
        if settings.CONVERT_CURRENCY:
            exchange_rate = await self.exchange_rate_client.get_exchange_rate()

        # Генерируем структурированный контент с помощью YandexGPT
        # LLM вернет JSON с: title, description, characteristics, hashtags
        llm_content = await self.yandex_gpt_client.generate_post_content(product_data)
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] LLM контент получен: {llm_content.get('title', 'N/A')}")
        
        # Формируем финальный пост из структурированных данных
        post_text = self._build_post_text(
            llm_content=llm_content,
            product_data=product_data,
            exchange_rate=exchange_rate
        )
        
        # Получаем список URL изображений из данных о товаре (все фото)
        image_urls = product_data.get('main_imgs', [])

        return post_text, image_urls
    
    def _format_size_range(self, sizes_str: str) -> str:
        """
        Форматирует размерный ряд. Если размеры последовательные, возвращает диапазон.
        
        Args:
            sizes_str: Строка с размерами (например "S, M, L" или "XS, S, M, L, XL")
        
        Returns:
            str: Отформатированная строка размеров
        """
        # Стандартные размеры в порядке
        standard_sizes = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        
        # Разбиваем строку на части и очищаем
        sizes = [s.strip().upper() for s in sizes_str.replace(',', ' ').split()]
        
        # Проверяем, все ли размеры стандартные
        if all(s in standard_sizes for s in sizes):
            # Получаем индексы
            indices = [standard_sizes.index(s) for s in sizes]
            
            # Проверяем последовательность (без пропусков)
            if len(indices) > 1 and indices == list(range(min(indices), max(indices) + 1)):
                # Возвращаем диапазон
                return f"{sizes[0]}-{sizes[-1]}"
        
        # Возвращаем как есть
        return sizes_str
    
    def _build_post_text(self, llm_content: dict, product_data: dict, exchange_rate: float = None) -> str:
        """
        Формирует финальный текст поста из структурированных данных LLM и данных API.
        Использует HTML разметку для Telegram.

        Args:
            llm_content (dict): Структурированный контент от YandexGPT
            product_data (dict): Данные о товаре от TMAPI
            exchange_rate (float, optional): Курс обмена CNY в RUB

        Returns:
            str: Отформатированный текст поста в HTML
        """
        # Извлекаем данные из LLM ответа
        title = llm_content.get('title', 'Товар')
        description = llm_content.get('description', '')
        main_characteristics = llm_content.get('main_characteristics', {})
        additional_info = llm_content.get('additional_info', {})
        hashtags = llm_content.get('hashtags', [])
        emoji = llm_content.get('emoji', '')
        
        # Извлекаем данные напрямую из API
        price = product_data.get('price_info', {}).get('price', 'N/A')
        product_url = product_data.get('product_url', '')
        
        # Начинаем формировать пост
        post_parts = []
        
        # Заголовок с эмодзи (жирным шрифтом)
        title_line = f"{emoji} " if emoji else ""
        title_line += f"<b>{title}</b>"
        post_parts.append(title_line)
        post_parts.append("")
        
        # Описание в виде цитаты
        if description:
            post_parts.append(f"<blockquote>{description}</blockquote>")
            post_parts.append("")
        
        # Основные характеристики
        if main_characteristics:
            for key, value in main_characteristics.items():
                # Форматируем размеры если это размеры
                if 'размер' in key.lower() and isinstance(value, str):
                    value = self._format_size_range(value)
                
                if isinstance(value, list):
                    # Если значение - список (например, цвета)
                    post_parts.append(f"<b>{key}:</b>")
                    for item in value:
                        post_parts.append(f"  • {item}")
                    post_parts.append("")
                else:
                    # Если значение - строка
                    post_parts.append(f"<b>{key}:</b> {value}")
        
        # Дополнительная информация (только если есть)
        if additional_info:
            for key, value in additional_info.items():
                # Пропускаем пустые значения
                if value and str(value).strip():
                    post_parts.append(f"<b>{key}:</b> {value}")
            
            # Добавляем пустую строку только если были доп. данные
            if any(v and str(v).strip() for v in additional_info.values()):
                post_parts.append("")
        
        # Если были характеристики, добавляем отступ перед ценой
        if main_characteristics or additional_info:
            if not post_parts[-1] == "":
                post_parts.append("")
        
        # Цена с эмодзи (жирным)
        price_text = f"💰 <b>Цена:</b> {price} юаней"
        if exchange_rate and settings.CONVERT_CURRENCY:
            try:
                rub_price = float(price) * exchange_rate
                price_text += f" (~{rub_price:.2f} ₽)"
            except (ValueError, TypeError):
                pass
        price_text += " + доставка"
        post_parts.append(price_text)
        post_parts.append("")
        
        # Призыв к действию
        post_parts.append("📝 Для заказа пишите @annabbox или в комментариях 🛍️")
        post_parts.append("")
        
        # Хэштеги
        if hashtags:
            hashtag_text = " ".join([f"#{tag}" for tag in hashtags])
            post_parts.append(hashtag_text)
            post_parts.append("")
        
        # Ссылка на товар
        if product_url:
            post_parts.append(f'<a href="{product_url}">Ссылка</a>')
        
        return "\n".join(post_parts)

"""
==============================================================================
URL PARSER - Определение платформы и извлечение ID товара
==============================================================================
Модуль для анализа URL товаров и определения платформы (Taobao/Tmall/Pinduoduo).
Извлекает item_id из URL для прямых API запросов.

Author: Your Name
Version: 1.0.0
License: MIT
==============================================================================
"""

import re
from urllib.parse import urlparse, parse_qs
from typing import Tuple, Optional


class Platform:
    """Константы для платформ электронной коммерции"""
    TAOBAO = "taobao"
    TMALL = "tmall"
    ALI1688 = "1688"
    PINDUODUO = "pinduoduo"
    SZWEGO = "szwego"
    UNKNOWN = "unknown"


class URLParser:
    """
    Парсер URL для определения платформы и извлечения ID товара.
    
    Поддерживаемые платформы:
    - Taobao (淘宝)
    - Tmall (天猫)
    - Pinduoduo (拼多多)
    """
    
    # Паттерны доменов для каждой платформы
    TAOBAO_DOMAINS = [
        "item.taobao.com",
        "a.m.taobao.com",
        "market.m.taobao.com",
        "h5.m.taobao.com",
        "s.click.taobao.com",
        "uland.taobao.com",
        "tb.cn"
    ]
    
    TMALL_DOMAINS = [
        "detail.tmall.com",
        "detail.m.tmall.com"
    ]

    ALI1688_DOMAINS = [
        "1688.com",
        "detail.1688.com",
        "detail.m.1688.com",  # Мобильная версия detail страницы
        "m.1688.com",
        "winport.m.1688.com"
    ]
    
    PINDUODUO_DOMAINS = [
        "mobile.yangkeduo.com",
        "yangkeduo.com",
        "pinduoduo.com",
        "pdd.com"
    ]
    
    SZWEGO_DOMAINS = [
        "szwego.com",
        "szwego.app",
        "clothes.szwego.app",
        "bags.szwego.app",
        "luxury.szwego.app"
    ]
    
    @staticmethod
    def detect_platform(url: str) -> str:
        """
        Определяет платформу по URL.
        
        Args:
            url: URL товара
            
        Returns:
            str: Название платформы (taobao/tmall/pinduoduo/unknown)
        """
        try:
            # Парсим URL
            parsed = urlparse(url if url.startswith('http') else f'https://{url}')
            domain = parsed.netloc.lower()
            
            # Убираем www. и m. префиксы для проверки
            domain_clean = domain.replace('www.', '').replace('m.', '')
            
            # Проверяем Taobao
            for taobao_domain in URLParser.TAOBAO_DOMAINS:
                if taobao_domain in domain or domain_clean.endswith('.taobao.com'):
                    return Platform.TAOBAO
            
            # Проверяем Tmall
            for tmall_domain in URLParser.TMALL_DOMAINS:
                if tmall_domain in domain or domain_clean.endswith('.tmall.com'):
                    return Platform.TMALL

            # Проверяем 1688
            for ali_domain in URLParser.ALI1688_DOMAINS:
                if ali_domain in domain or domain_clean.endswith('.1688.com'):
                    return Platform.ALI1688
            
            # Проверяем Pinduoduo
            for pdd_domain in URLParser.PINDUODUO_DOMAINS:
                if pdd_domain in domain:
                    return Platform.PINDUODUO
            
            # Проверяем Szwego
            for szwego_domain in URLParser.SZWEGO_DOMAINS:
                if szwego_domain in domain:
                    return Platform.SZWEGO
            
            return Platform.UNKNOWN
            
        except Exception:
            return Platform.UNKNOWN
    
    @staticmethod
    def extract_pinduoduo_id(url: str) -> Optional[str]:
        """
        Извлекает item_id из URL Pinduoduo.
        
        Поддерживаемые форматы:
        - https://mobile.yangkeduo.com/goods.html?goods_id=123456789
        - https://yangkeduo.com/goods.html?goods_id=123456789
        - https://example.com/page?id=123456789
        
        Args:
            url: URL товара Pinduoduo
            
        Returns:
            Optional[str]: ID товара или None если не найден
        """
        try:
            # Парсим URL
            parsed = urlparse(url)
            
            # Пытаемся найти в query параметрах
            query_params = parse_qs(parsed.query)
            
            # Возможные названия параметра ID
            possible_id_params = ['goods_id', 'id', 'item_id', 'goodsId']
            
            for param in possible_id_params:
                if param in query_params:
                    item_id = query_params[param][0]
                    # Проверяем что это число
                    if item_id.isdigit():
                        return item_id
            
            # Пытаемся найти ID в пути URL (например: /goods/123456789)
            path_parts = parsed.path.split('/')
            for part in path_parts:
                if part.isdigit() and len(part) >= 8:  # ID обычно длинный
                    return part
            
            return None
            
        except Exception:
            return None
    
    @staticmethod
    def extract_1688_id(url: str) -> Optional[str]:
        """
        Извлекает offer_id из URL 1688.
        
        Поддерживаемые форматы:
        - https://detail.1688.com/offer/978544643627.html?offerId=978544643627&hotSaleSkuId=...
        - https://detail.1688.com/offer/978544643627.html
        - https://m.1688.com/offer/978544643627.html
        - http://detail.m.1688.com/page/index.htm?offerId=1000507489165
        
        Args:
            url: URL товара 1688
            
        Returns:
            Optional[str]: ID товара (offer_id) или None если не найден
        """
        try:
            # Парсим URL
            parsed = urlparse(url if url.startswith('http') else f'https://{url}')
            
            # Ищем паттерн /offer/{id}.html в пути
            # Пример: /offer/978544643627.html
            match = re.search(r'/offer/(\d+)\.html', parsed.path)
            if match:
                offer_id = match.group(1)
                if offer_id.isdigit():
                    return offer_id
            
            # Если не нашли в пути, проверяем query параметры
            query_params = parse_qs(parsed.query)
            if 'offerId' in query_params:
                offer_id = query_params['offerId'][0]
                if offer_id.isdigit():
                    return offer_id
            
            return None
            
        except Exception:
            return None
    
    @staticmethod
    def extract_szwego_id(url: str) -> Optional[str]:
        """
        Извлекает item_id из URL Szwego.
        
        Поддерживаемые форматы (предположительно):
        - https://clothes.szwego.app/product/123456789
        - https://bags.szwego.app/item?id=123456789
        - https://szwego.com/product/123456789
        
        Args:
            url: URL товара Szwego
            
        Returns:
            Optional[str]: ID товара или None если не найден
        """
        try:
            # Парсим URL
            parsed = urlparse(url if url.startswith('http') else f'https://{url}')
            
            # Пытаемся найти в query параметрах
            query_params = parse_qs(parsed.query)
            
            # Возможные названия параметра ID
            possible_id_params = ['id', 'item_id', 'product_id', 'goods_id', 'itemId', 'productId']
            
            for param in possible_id_params:
                if param in query_params:
                    item_id = query_params[param][0]
                    # Проверяем что это число или строка с цифрами
                    if item_id.isdigit() or (isinstance(item_id, str) and any(c.isdigit() for c in item_id)):
                        return item_id.strip()
            
            # Пытаемся найти ID в пути URL (например: /product/123456789 или /item/123456789)
            path_parts = parsed.path.split('/')
            for part in path_parts:
                if part and (part.isdigit() or (len(part) >= 6 and any(c.isdigit() for c in part))):
                    # Если часть пути похожа на ID (содержит цифры и достаточно длинная)
                    return part.strip()
            
            return None
            
        except Exception:
            return None
    
    @staticmethod
    def normalize_1688_url(url: str) -> Optional[str]:
        """
        Нормализует URL 1688 до формата: https://detail.1688.com/offer/{id}.html
        
        Извлекает ID товара из любого формата URL 1688 и формирует правильный URL.
        Обрабатывает случаи:
        - detail.m.1688.com -> detail.1688.com
        - m.1688.com -> detail.1688.com
        - любые форматы с offerId в query параметрах
        
        Args:
            url: URL товара 1688 (любой формат)
            
        Returns:
            Optional[str]: Нормализованный URL или None если ID не найден
        """
        # Заменяем detail.m.1688.com на detail.1688.com перед обработкой
        # Это нужно для корректной работы с ссылками типа:
        # http://detail.m.1688.com/page/index.htm?offerId=1000507489165
        normalized_input = url.replace("detail.m.1688.com", "detail.1688.com")
        
        offer_id = URLParser.extract_1688_id(normalized_input)
        if offer_id:
            return f"https://detail.1688.com/offer/{offer_id}.html"
        return None
    
    @staticmethod
    def parse_url(url: str) -> Tuple[str, Optional[str]]:
        """
        Комплексный анализ URL - определяет платформу и извлекает ID.
        
        Args:
            url: URL товара
            
        Returns:
            Tuple[str, Optional[str]]: (platform, item_id)
            - platform: название платформы (taobao/tmall/1688/pinduoduo/szwego/unknown)
            - item_id: ID товара (для Pinduoduo, 1688, Szwego), None для Taobao/Tmall
        """
        platform = URLParser.detect_platform(url)
        
        # Для Pinduoduo извлекаем ID
        if platform == Platform.PINDUODUO:
            item_id = URLParser.extract_pinduoduo_id(url)
            return platform, item_id
        
        # Для 1688 извлекаем ID для нормализации URL
        if platform == Platform.ALI1688:
            item_id = URLParser.extract_1688_id(url)
            return platform, item_id
        
        # Для Szwego извлекаем ID (если есть в URL)
        if platform == Platform.SZWEGO:
            item_id = URLParser.extract_szwego_id(url)
            return platform, item_id
        
        # Для Taobao/Tmall ID не нужен (передаём весь URL в API)
        return platform, None


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
    PINDUODUO = "pinduoduo"
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
    
    PINDUODUO_DOMAINS = [
        "mobile.yangkeduo.com",
        "yangkeduo.com",
        "pinduoduo.com",
        "pdd.com"
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
            
            # Проверяем Pinduoduo
            for pdd_domain in URLParser.PINDUODUO_DOMAINS:
                if pdd_domain in domain:
                    return Platform.PINDUODUO
            
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
    def parse_url(url: str) -> Tuple[str, Optional[str]]:
        """
        Комплексный анализ URL - определяет платформу и извлекает ID.
        
        Args:
            url: URL товара
            
        Returns:
            Tuple[str, Optional[str]]: (platform, item_id)
            - platform: название платформы (taobao/tmall/pinduoduo/unknown)
            - item_id: ID товара (только для Pinduoduo, для Taobao/Tmall None)
        """
        platform = URLParser.detect_platform(url)
        
        # Для Pinduoduo извлекаем ID
        if platform == Platform.PINDUODUO:
            item_id = URLParser.extract_pinduoduo_id(url)
            return platform, item_id
        
        # Для Taobao/Tmall ID не нужен (передаём весь URL в API)
        return platform, None


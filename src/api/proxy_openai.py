from typing import Dict, Any, List
from openai import OpenAI
from src.core.config import settings


class ProxyOpenAIClient:
    def __init__(self) -> None:
        if not settings.PROXYAPI_OPENAI_API_KEY:
            raise ValueError("PROXYAPI_OPENAI_API_KEY is not set")
        self.client = OpenAI(
            api_key=settings.PROXYAPI_OPENAI_API_KEY,
            base_url=settings.PROXYAPI_OPENAI_BASE_URL or "https://api.proxyapi.ru/openai/v1",
        )
        self.model = settings.PROXYAPI_OPENAI_MODEL or "gpt-4o"

    async def analyze_pinduoduo_html(self, html: str, image_urls: List[str], product_url: str = "") -> Dict[str, Any]:
        # В Responses API нет async SDK, вызываем синхронно внутри async контекста (короткий вызов)
        import re
        from datetime import datetime
        
        debug = getattr(settings, 'DEBUG_MODE', False)
        if debug:
            print(f"[OpenAI] База: {settings.PROXYAPI_OPENAI_BASE_URL}, модель: {self.model}")
            print(f"[OpenAI] HTML длина: {len(html)} символов, изображений: {len(image_urls)}")

        # Пытаемся извлечь цену из HTML заранее (для включения в промпт)
        price_from_html = ""
        try:
            # Ищем цену в различных форматах
            price_patterns = [
                r'"price"[:\s]*"?(\d+\.?\d*)"?',
                r'"sale_price"[:\s]*"?(\d+\.?\d*)"?',
                r'price[:\s]*"?(\d+\.?\d*)"?',
                r'¥\s*(\d+\.?\d*)',
                r'(\d+\.?\d*)\s*元',
            ]
            for pattern in price_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    price_from_html = match.group(1)
                    if debug:
                        print(f"[ProxyOpenAI] Извлечена цена из HTML: {price_from_html}")
                    break
        except Exception:
            pass

        # Инструкции для модели
        instructions = (
            "Ты — помощник для извлечения структурированной информации о товаре с Pinduoduo из HTML-страницы.\n\n"
            "ТРЕБОВАНИЯ:\n"
            "- НИЧЕГО НЕ ПРИДУМЫВАТЬ. Использовать только явный текст из HTML.\n"
            "- Название ОБЯЗАТЕЛЬНО перевести на русский (бренд оставлять как в оригинале).\n"
            "- В описании УПОМИНАТЬ тип товара, если он явно указан в HTML (в тексте описания, без отдельной строки 'Тип товара').\n"
            "- Динамические характеристики: если это жидкость/косметика с объёмом — указывать 'Состав' и 'Объём'; если одежда/обувь — 'Цвета', 'Материалы', 'Размеры'. Не выводить неуместные поля.\n"
            "- Цена должна быть реальной (из HTML), не придумывать.\n"
            "- Массив images вернуть РОВНО таким, как передан (разрешено удалить явные логотипы/баннеры, если это очевидно из URL).\n"
            "- Единицы измерения для объёма писать по-русски: 'мл' вместо 'ml'.\n\n"
            "ЗАДАЧИ:\n"
            "1) Извлеки из HTML:\n"
            "   - Название товара (переведи на русский, сохраняя бренд)\n"
            "   - Тип товара (включи в текст описания, без отдельной строки)\n"
            "   - Описание товара (кратко, 2-5 предложений, только факты из HTML)\n"
            "   - Цену товара\n"
            "   - Характеристики: цвет, состав/материалы, объём/размер\n\n"
            "2) Используй переданный список изображений как images (не фильтровать, кроме явной рекламы/логотипов).\n\n"
            "3) Верни строго JSON со структурой:\n"
            '{\n'
            '  "title": "Название (русский)",\n'
            '  "description": "Описание с типом товара (русский)",\n'
            '  "price": "Цена",\n'
            '  "color": ["массив цветов"],\n'
            '  "materials": "Состав или материалы (если уместно)",\n'
            '  "volume": "Объём (если уместно, в мл)",\n'
            '  "main_characteristics": {"ключ": "значение"},\n'
            '  "additional_info": {"ключ": "значение"},\n'
            '  "hashtags": ["список хэштегов"],\n'
            '  "emoji": "эмодзи",\n'
            '  "images": ["URL" ...]\n'
            '}\n\n'
            "ВАЖНО: переводить на русский, не добавлять очевидности, не придумывать значения. Не выводить строку 'Тип товара'.\n"
        )

        # Формируем единый input для Responses API
        price_info = f"\nПОДСКАЗКА о цене из HTML: {price_from_html}\n" if price_from_html else ""
        user_content = (
            instructions +
            price_info +
            "\n\n=== HTML СТРАНИЦЫ (первые 200KB) ===\n" + html[:200000] +
            "\n\n=== КАНДИДАТЫ ИЗОБРАЖЕНИЙ ===\n" + "\n".join(image_urls[:100]) +
            "\n\nЗадача: извлеки РЕАЛЬНУЮ информацию о товаре из HTML, определи тип товара по главному изображению, "
            "отбери все относящиеся к товару фото, и верни валидный JSON без пояснений."
        )

        if debug:
            print(f"[ProxyOpenAI] Отправляем промпт (первые 1000 символов):")
            print(f"{user_content[:1000]}...")
            print(f"[ProxyOpenAI] Полный промпт длина: {len(user_content)} символов")

        try:
            resp = self.client.responses.create(
                model=self.model,
                input=user_content,
            )
        except Exception as e:
            if debug:
                print(f"[ProxyOpenAI] Ошибка при запросе: {type(e).__name__}: {e}")
            # Пробрасываем дальше, чтобы верхний слой мог отреагировать (в т.ч. на 402 Payment Required)
            raise

        if debug:
            print(f"[ProxyOpenAI] Ответ получен. Тип: {type(resp)}")
            print(f"[ProxyOpenAI] Атрибуты resp: {[a for a in dir(resp) if not a.startswith('_')]}")

        # Responses API возвращает контент в resp.output_text
        text = None
        try:
            text = resp.output_text  # type: ignore[attr-defined]
            if debug:
                print(f"[ProxyOpenAI] Найден output_text: {text[:200] if text else 'None'}...")
        except AttributeError:
            if debug:
                print(f"[ProxyOpenAI] output_text не найден. Пробуем другие варианты...")
            # Попробуем generic доступ
            try:
                text = resp.choices[0].message.content  # type: ignore[attr-defined,index]
                if debug:
                    print(f"[ProxyOpenAI] Найден через choices[0].message.content")
            except Exception as e:
                if debug:
                    print(f"[ProxyOpenAI] choices не сработало: {e}")
                # Пробуем найти в __dict__
                try:
                    if hasattr(resp, '__dict__'):
                        resp_dict = resp.__dict__
                        if debug:
                            print(f"[ProxyOpenAI] resp.__dict__ ключи: {list(resp_dict.keys())}")
                        for key in ['output_text', 'output', 'text', 'content', 'response', 'message']:
                            if key in resp_dict:
                                text = resp_dict[key]
                                if debug:
                                    print(f"[ProxyOpenAI] Нашли текст в поле '{key}'")
                                break
                except Exception as e2:
                    if debug:
                        print(f"[ProxyOpenAI] Ошибка при поиске в __dict__: {e2}")

        if not text:
            if debug:
                print(f"[ProxyOpenAI] ⚠️ Не удалось извлечь текст из ответа!")
            text = "{}"

        if debug:
            print(f"[ProxyOpenAI] Извлечённый текст (первые 1000 символов):")
            print(f"{text[:1000]}...")
            print(f"[ProxyOpenAI] Полная длина текста: {len(text)} символов")

        import json
        try:
            # Пробуем найти JSON в тексте (может быть обёрнут в markdown код-блок)
            text_clean = text.strip()
            if text_clean.startswith("```"):
                # Убираем ```json и закрывающие ```
                lines = text_clean.split("\n")
                text_clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
                text_clean = text_clean.replace("```json", "").replace("```", "").strip()
                if debug:
                    print(f"[ProxyOpenAI] Убрали markdown блоки. Новый текст (первые 200 символов): {text_clean[:200]}...")

            data = json.loads(text_clean)
            if isinstance(data, dict):
                if debug:
                    print(f"[ProxyOpenAI] ✅ Успешно распарсили JSON. Ключи: {list(data.keys())}")
                    for key, value in data.items():
                        print(f"[ProxyOpenAI]   {key}: {str(value)[:100] if value else 'None'}...")
                return data
        except json.JSONDecodeError as e:
            if debug:
                print(f"[ProxyOpenAI] ❌ Ошибка парсинга JSON: {e}")
                text_clean_fallback = text_clean if 'text_clean' in locals() else text
                print(f"[ProxyOpenAI] Проблемный текст (первые 500 символов): {text_clean_fallback[:500]}")
        except Exception as e:
            if debug:
                print(f"[ProxyOpenAI] ❌ Другая ошибка при парсинге: {type(e).__name__}: {e}")
        # Фоллбек пустая структура (соответствует новому формату)
        return {
            "url": product_url or "",
            "product_id": None,
            "title": "",
            "description": "",
            "price": "",
            "volume": "",
            "color": [],
            "materials": "",
            "main_characteristics": {},
            "additional_info": {},
            "hashtags": [],
            "emoji": "",
            "images": [],
            "scraped_at": datetime.now().isoformat(),
            "success": False,
            "error": "Не удалось распарсить ответ OpenAI",
        }



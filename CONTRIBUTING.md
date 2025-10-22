# Руководство по внесению вклада 🤝

Спасибо за интерес к проекту! Мы приветствуем любой вклад в развитие Taobao Scraper Bot.

---

## 📋 Как помочь проекту

### 🐛 Сообщить об ошибке

1. Проверьте что ошибка ещё не [зарепорчена](https://github.com/your-username/TaoBao_Scraper_2/issues)
2. Создайте новый Issue с шаблоном "Bug Report"
3. Опишите:
   - Что вы делали
   - Что ожидали увидеть
   - Что получили на самом деле
   - Версию Python, ОС
   - Логи ошибок

### 💡 Предложить улучшение

1. Создайте Issue с шаблоном "Feature Request"
2. Опишите:
   - Зачем нужна эта функция
   - Как она должна работать
   - Альтернативные варианты

### 📝 Улучшить документацию

Документация всегда может быть лучше! Pull Requests с улучшениями приветствуются.

---

## 🔧 Процесс разработки

### 1. Fork и клонирование

```bash
# Fork репозитория на GitHub, затем:
git clone https://github.com/your-username/TaoBao_Scraper_2.git
cd TaoBao_Scraper_2

# Добавьте upstream
git remote add upstream https://github.com/original-username/TaoBao_Scraper_2.git
```

### 2. Создание ветки

```bash
# Обновите main
git checkout main
git pull upstream main

# Создайте feature branch
git checkout -b feature/amazing-feature
```

**Naming conventions:**
- `feature/` - новая функциональность
- `fix/` - исправление бага
- `docs/` - изменения документации
- `refactor/` - рефакторинг кода

### 3. Разработка

```bash
# Настройте окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Установите зависимости
pip install -r requirements.txt

# Создайте .env
cp .env.example .env
# Заполните API ключи для тестирования
```

### 4. Коммиты

Используйте [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: add support for AliExpress"
git commit -m "fix: resolve SSL certificate error"
git commit -m "docs: update deployment guide"
```

**Типы коммитов:**
- `feat:` - новая функциональность
- `fix:` - исправление бага
- `docs:` - документация
- `style:` - форматирование
- `refactor:` - рефакторинг
- `test:` - тесты
- `chore:` - обслуживание

### 5. Push и Pull Request

```bash
# Push в ваш fork
git push origin feature/amazing-feature

# Создайте Pull Request на GitHub
```

**В описании PR укажите:**
- Что изменилось
- Зачем это нужно
- Как протестировать
- Ссылку на Issue (если есть)

---

## 📐 Стандарты кода

### Python Style Guide

Следуйте [PEP 8](https://pep8.org/):

```python
# ✅ Хорошо
def process_product_data(product_id: str) -> dict:
    """Обрабатывает данные о товаре."""
    result = fetch_data(product_id)
    return result

# ❌ Плохо
def processProductData(productId):
    result=fetch_data(productId)
    return result
```

### Документирование

Все функции должны иметь docstrings:

```python
def generate_post(data: dict, options: dict = None) -> str:
    """
    Генерирует пост из данных о товаре.
    
    Args:
        data: Данные о товаре от TMAPI
        options: Дополнительные опции (необязательно)
    
    Returns:
        Отформатированный текст поста
    
    Raises:
        ValueError: Если data невалидны
    """
    pass
```

### Типизация

Используйте type hints где возможно:

```python
from typing import Dict, List, Optional

async def fetch_products(
    urls: List[str],
    timeout: Optional[int] = 30
) -> Dict[str, dict]:
    pass
```

---

## 🧪 Тестирование

### Ручное тестирование

1. Используйте `DEBUG_MODE=True` для тестирования без API
2. Проверьте все изменённые функции
3. Убедитесь что бот запускается без ошибок

### Будущее: Автоматические тесты

Планируется добавить pytest. Пример:

```python
def test_post_formatting():
    """Тест форматирования поста."""
    data = {...}
    post = format_post(data)
    assert "**" in post  # Проверяем жирный текст
    assert "<blockquote>" in post  # Проверяем цитату
```

---

## 📦 Зависимости

### Добавление новой зависимости

1. Добавьте в `requirements.txt`
2. Обновите документацию
3. Укажите зачем нужна зависимость в PR

### Обновление зависимостей

```bash
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt
```

---

## 📝 Документация

### Структура docs/

```
docs/
├── SERVICES_SETUP.md    # Настройка API сервисов
├── DEPLOYMENT.md        # Развёртывание
├── ARCHITECTURE.md      # Архитектура
├── FAQ.md               # Частые вопросы
└── ...
```

### При добавлении новой функции

1. Обновите README.md
2. Добавьте в соответствующий .md файл
3. Обновите FAQ.md если нужно

---

## 🚫 Что НЕ принимается

- ❌ Коммиты API ключей или .env файлов
- ❌ Код без комментариев для сложной логики
- ❌ Изменения без описания в PR
- ❌ Нарушение PEP 8 без веских причин
- ❌ Breaking changes без обсуждения

---

## ✅ Checklist перед PR

- [ ] Код следует PEP 8
- [ ] Добавлены docstrings
- [ ] Обновлена документация
- [ ] Проведено ручное тестирование
- [ ] Нет API ключей в коде
- [ ] Коммиты следуют Conventional Commits
- [ ] PR описание заполнено

---

## 🎯 Приоритетные задачи

Смотрите Issues с метками:
- `good first issue` - для новичков
- `help wanted` - нужна помощь
- `enhancement` - улучшения
- `bug` - баги

---

## 💬 Вопросы?

- 📖 Проверьте [FAQ](docs/FAQ.md)
- 💬 Спросите в [Issues](https://github.com/your-username/TaoBao_Scraper_2/issues)
- 📧 Напишите maintainer'у

---

## 📜 Лицензия

Внося вклад, вы соглашаетесь что ваш код будет распространяться под лицензией MIT.

---

<p align="center">
  <b>Спасибо за ваш вклад! 🙏</b>
</p>


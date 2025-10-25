# 🔄 Руководство по миграции на версию 2.0

## Обзор изменений

В версии 2.0 проект был полностью реорганизован для улучшения масштабируемости и поддерживаемости.

### ⚠️ Критические изменения (Breaking Changes)

#### 1. Структура файлов изменилась

**Старая структура:**
```
TaoBao_Scraper_2/
├── autoparse.py
├── bot_handler.py
├── scraper.py
├── tmapi.py
├── config.py
└── ...
```

**Новая структура:**
```
TaoBao_Scraper_2/
├── main.py                    # ← Было autoparse.py
├── src/
│   ├── bot/
│   │   ├── handlers.py        # ← Было bot_handler.py
│   │   └── error_handler.py
│   ├── api/
│   │   ├── tmapi.py
│   │   ├── yandex_gpt.py
│   │   └── ...
│   ├── core/
│   │   ├── scraper.py
│   │   └── config.py
│   └── utils/
│       └── url_parser.py
└── ...
```

#### 2. Точка входа переименована

- **Старое:** `autoparse.py`
- **Новое:** `main.py`

#### 3. Импорты изменились

**Старые импорты:**
```python
from config import settings
from scraper import Scraper
from tmapi import TmapiClient
```

**Новые импорты:**
```python
from src.core.config import settings
from src.core.scraper import Scraper
from src.api.tmapi import TmapiClient
```

---

## 🚀 Как мигрировать

### Вариант 1: Чистое обновление (рекомендуется)

Если вы используете Docker (рекомендуется), изменения прозрачны:

```bash
# 1. Остановите контейнер
docker-compose down

# 2. Получите новую версию
git pull origin main

# 3. Пересоберите образ (важно!)
docker-compose up -d --build

# 4. Проверьте логи
docker-compose logs -f --tail=50
```

**✅ Готово!** Всё работает с новой структурой.

---

### Вариант 2: Локальная установка

Если вы запускаете бота локально (не Docker):

#### Шаг 1: Обновите код

```bash
git pull origin main
```

#### Шаг 2: Переустановите зависимости (опционально)

```bash
pip install -r requirements.txt --upgrade
```

#### Шаг 3: Обновите команду запуска

**Старая команда:**
```bash
python autoparse.py
```

**Новая команда:**
```bash
python main.py
```

#### Шаг 4: Обновите systemd service (если используется)

Если у вас есть systemd service файл:

```ini
# /etc/systemd/system/taobao-bot.service

[Service]
# Старое
ExecStart=/usr/bin/python3 /path/to/autoparse.py

# Новое ↓
ExecStart=/usr/bin/python3 /path/to/main.py
```

Перезагрузите service:
```bash
sudo systemctl daemon-reload
sudo systemctl restart taobao-bot
```

---

## ❓ FAQ по миграции

### Q: Нужно ли обновлять .env файл?

**A:** Нет, `.env` файл остался без изменений. Все ключи API и настройки такие же.

### Q: Будут ли работать мои кастомные модификации?

**A:** Зависит от того, что вы изменили:
- **Изменения в `.env`** → Работают без изменений
- **Изменения в коде** → Нужно обновить импорты
- **Кастомные модули** → Нужно перенести в `src/`

### Q: Можно ли откатиться на старую версию?

**A:** Да:

```bash
# Откат на предыдущую версию
git checkout HEAD~1

# Или на конкретный коммит
git checkout <commit-hash>

# Пересоберите Docker
docker-compose up -d --build
```

### Q: Мои логи будут потеряны?

**A:** Нет, файл `bot_errors.log` остался в том же месте. Логи сохранятся.

### Q: Изменился ли функционал?

**A:** Нет, функционал идентичен. Изменилась только внутренняя структура кода.

---

## 🛠️ Миграция кастомных модификаций

### Если вы добавляли свои обработчики в bot_handler.py

**Старый путь:** `bot_handler.py`  
**Новый путь:** `src/bot/handlers.py`

**Миграция:**
1. Откройте `src/bot/handlers.py`
2. Добавьте свои обработчики
3. Обновите импорты, если использовали другие модули

**Пример:**
```python
# Ваш кастомный handler
@router.message(F.text == "/custom")
async def custom_handler(message: Message):
    # Обновите импорты
    from src.core.scraper import Scraper  # ← Было: from scraper import Scraper
    # ... ваш код
```

### Если вы модифицировали scraper.py

**Старый путь:** `scraper.py`  
**Новый путь:** `src/core/scraper.py`

**Миграция:**
1. Откройте `src/core/scraper.py`
2. Перенесите свои изменения
3. Обновите импорты:

```python
# Было:
from tmapi import TmapiClient
from config import settings

# Стало:
from src.api.tmapi import TmapiClient
from src.core.config import settings
```

### Если вы добавили новые файлы

Поместите их в соответствующую папку:

- **API клиенты** → `src/api/`
- **Обработчики бота** → `src/bot/`
- **Бизнес-логика** → `src/core/`
- **Утилиты** → `src/utils/`

**Не забудьте обновить импорты!**

---

## 📊 Checklist миграции

Используйте этот checklist для проверки:

- [ ] Остановил старый контейнер/процесс
- [ ] Получил новую версию (`git pull`)
- [ ] Пересобрал Docker образ (`--build`) или обновил зависимости
- [ ] Обновил команду запуска (`main.py` вместо `autoparse.py`)
- [ ] Проверил логи на наличие ошибок
- [ ] Отправил тестовую ссылку боту
- [ ] Убедился, что бот отвечает корректно
- [ ] (Опционально) Перенёс кастомные модификации
- [ ] (Опционально) Обновил systemd service

---

## 🚨 Возможные проблемы

### Проблема: `ModuleNotFoundError: No module named 'src'`

**Причина:** Старый Python кэш или запуск не из корня проекта

**Решение:**
```bash
# Удалите кэш
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Запустите из корня проекта
cd /path/to/TaoBao_Scraper_2
python main.py
```

### Проблема: `ImportError: cannot import name 'settings'`

**Причина:** Циклический импорт

**Решение:** Используйте прямые импорты:

```python
# ❌ Неправильно
from src.core import settings

# ✅ Правильно
from src.core.config import settings
```

### Проблема: Docker не видит изменения

**Причина:** Старый образ не пересобрался

**Решение:**
```bash
# Полная пересборка
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## 📞 Поддержка

Если у вас возникли проблемы с миграцией:

1. Проверьте [Issues на GitHub](https://github.com/batoo-han/TaoBao_Scraper/issues)
2. Просмотрите логи: `docker-compose logs -f`
3. Откатитесь на предыдущую версию (см. FAQ)
4. Создайте новый Issue с описанием проблемы

---

## 🎯 Преимущества новой структуры

После миграции вы получите:

- ✅ **Чистый корень проекта** - только важные файлы
- ✅ **Логичная организация** - легко найти нужный код
- ✅ **Масштабируемость** - просто добавлять новые функции
- ✅ **Стандартность** - привычная структура для Python проектов
- ✅ **Лучшая поддержка IDE** - автодополнение и навигация

---

## 📚 Дополнительные ресурсы

- [**PROJECT_STRUCTURE.md**](PROJECT_STRUCTURE.md) - Подробное описание новой структуры
- [**ARCHITECTURE.md**](ARCHITECTURE.md) - Архитектура проекта
- [**QUICK_START.md**](QUICK_START.md) - Быстрый старт с нуля

---

**Дата миграции:** 2025-10-25  
**Версия:** 2.0.0  
**Breaking Changes:** Да


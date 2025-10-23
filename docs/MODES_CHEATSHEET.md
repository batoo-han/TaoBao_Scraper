# 🚀 Шпаргалка по режимам

## Быстрая настройка

### 🎯 Диагностика проблем (реальные запросы + логи)

```env
DEBUG_MODE=True
MOCK_MODE=False
```

Перезапустите бота и смотрите подробные логи!

---

### 🏭 Production (для пользователей)

```env
DEBUG_MODE=False
MOCK_MODE=False
```

---

### 🧪 Тестирование (без API запросов)

```env
DEBUG_MODE=False
MOCK_MODE=True
```

---

### 🔬 Разработка (тестовые данные + логи)

```env
DEBUG_MODE=True
MOCK_MODE=True
```

---

## Таблица режимов

| Режим | DEBUG | MOCK | API | Логи |
|-------|-------|------|-----|------|
| **Production** | ❌ | ❌ | ✅ | ❌ |
| **Development** ⭐ | ✅ | ❌ | ✅ | ✅ |
| **Testing** | ❌ | ✅ | ❌ | ❌ |
| **Mock Debug** | ✅ | ✅ | ❌ | ✅ |

---

## Что делает каждый флаг

**`DEBUG_MODE`**
- ✅ `True` - показывать подробные логи
- ❌ `False` - минимальный вывод

**`MOCK_MODE`**
- ✅ `True` - читать из `result.txt` и `result55.txt`
- ❌ `False` - реальные запросы к TMAPI API

---

## 📖 Подробная документация

- `docs/DEBUG_AND_MOCK_MODES.md` - полное описание режимов
- `DEBUG_INSTRUCTIONS.md` - инструкция по отладке


# 🚀 Процесс обновления проекта на сервере

## 📋 Оглавление

1. [Стандартный процесс обновления](#стандартный-процесс-обновления)
2. [Когда нужна пересборка](#когда-нужна-пересборка)
3. [Оптимизированные команды](#оптимизированные-команды)
4. [Автоматизация через alias](#автоматизация-через-alias)
5. [Автоматизация через скрипт](#автоматизация-через-скрипт)
6. [Полезные команды](#полезные-команды)
7. [Troubleshooting](#troubleshooting)

---

## 📦 Стандартный процесс обновления

### Базовый процесс:

```bash
# 1. Зайти в директорию проекта на сервере
cd ~/TaoBao_Scraper

# 2. Остановить контейнер
sudo docker-compose down

# 3. Получить изменения с GitHub
git pull

# 4. Пересобрать и запустить
sudo docker-compose up -d --build

# 5. Проверить логи
sudo docker-compose logs -f
```

---

## 🔄 Когда нужна пересборка

### ✅ ОБЯЗАТЕЛЬНО пересобирать (`--build`):

1. **Изменения в `.py` файлах** (весь код Python)
   - `autoparse.py`
   - `bot_handler.py`
   - `scraper.py`
   - `error_handler.py`
   - `yandex_gpt.py`
   - и т.д.

2. **Изменения в `requirements.txt`**
   - Добавление новых библиотек
   - Обновление версий зависимостей

3. **Изменения в `Dockerfile`**
   - Изменение базового образа
   - Добавление системных зависимостей
   - Изменение структуры сборки

### 🔄 МОЖНО БЕЗ ПЕРЕСБОРКИ (просто перезапуск):

1. **Изменения в `.env` файле**
   ```bash
   sudo docker-compose down
   sudo docker-compose up -d
   ```

2. **Изменения в `docker-compose.yml`** (только настройки, не build)
   ```bash
   sudo docker-compose down
   sudo docker-compose up -d
   ```

---

## ⚡ Оптимизированные команды

### 🎯 Вариант 1: Быстрое обновление (рекомендуется для ежедневной работы)

```bash
cd ~/TaoBao_Scraper && \
git pull && \
sudo docker-compose up -d --build && \
sudo docker-compose logs -f --tail=50
```

**Что делает:**
- `git pull` - получает изменения с GitHub
- `--build` - пересобирает ТОЛЬКО если есть изменения
- `--tail=50` - показывает последние 50 строк логов
- `-f` - следит за логами в реальном времени

**Время выполнения:** ~10-30 секунд (зависит от изменений)

---

### 🎯 Вариант 2: С полной очисткой кэша (если что-то не работает)

```bash
cd ~/TaoBao_Scraper && \
git pull && \
sudo docker-compose down && \
sudo docker-compose build --no-cache && \
sudo docker-compose up -d && \
sudo docker-compose logs -f
```

**Когда использовать:**
- Что-то сломалось после обновления
- Изменения не применяются
- После обновления `requirements.txt`
- После изменения базового образа в `Dockerfile`

**Время выполнения:** ~2-5 минут (полная пересборка)

---

### 🎯 Вариант 3: Только перезапуск (для изменений в .env)

```bash
cd ~/TaoBao_Scraper && \
sudo docker-compose restart && \
sudo docker-compose logs -f --tail=30
```

**Когда использовать:**
- Изменили переменные окружения в `.env`
- Не было изменений в коде
- Нужно просто перезапустить бота

**Время выполнения:** ~5-10 секунд

---

## 🔧 Docker Layer Caching

Docker использует **кэширование слоёв** для ускорения сборки:

```dockerfile
# Dockerfile
COPY requirements.txt .         # ← Если не изменился, берет из кэша
RUN pip install ...             # ← Кэш! Быстро! (~5 секунд)

COPY *.py ./                    # ← Если изменился - пересобирает (~10 секунд)
```

**Это значит:**
- ✅ Изменили только `.py` файлы → пересборка **быстрая** (~10-15 секунд)
- ✅ Изменили `requirements.txt` → пересборка **средняя** (~1-2 минуты)
- ✅ Изменили `Dockerfile` → пересборка **полная** (~2-5 минут)

---

## 🤖 Автоматизация через alias

### Создание alias для быстрого обновления:

```bash
# Добавить в ~/.bashrc
echo 'alias update-bot="cd ~/TaoBao_Scraper && git pull && sudo docker-compose up -d --build && sudo docker-compose logs -f --tail=50"' >> ~/.bashrc

# Применить изменения
source ~/.bashrc
```

### Использование:

```bash
# Теперь просто одна команда:
update-bot
```

### Дополнительные полезные alias:

```bash
# Добавить все сразу
cat >> ~/.bashrc << 'EOF'

# TaoBao Scraper Bot aliases
alias update-bot="cd ~/TaoBao_Scraper && git pull && sudo docker-compose up -d --build && sudo docker-compose logs -f --tail=50"
alias bot-logs="cd ~/TaoBao_Scraper && sudo docker-compose logs -f --tail=100"
alias bot-status="cd ~/TaoBao_Scraper && sudo docker-compose ps"
alias bot-restart="cd ~/TaoBao_Scraper && sudo docker-compose restart && sudo docker-compose logs -f --tail=30"
alias bot-rebuild="cd ~/TaoBao_Scraper && git pull && sudo docker-compose down && sudo docker-compose build --no-cache && sudo docker-compose up -d"

EOF

# Применить
source ~/.bashrc
```

**Использование:**
- `update-bot` - обновить и перезапустить
- `bot-logs` - посмотреть логи
- `bot-status` - статус контейнера
- `bot-restart` - перезапустить
- `bot-rebuild` - полная пересборка

---

## 📝 Автоматизация через скрипт

### Создание скрипта обновления:

```bash
# Создать файл
nano ~/update-taobao.sh
```

**Вставить содержимое:**

```bash
#!/bin/bash

# ==============================================================================
# TaoBao Scraper Bot - Скрипт обновления
# ==============================================================================

set -e  # Остановить при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_DIR="$HOME/TaoBao_Scraper"

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   🔄 Обновление TaoBao Scraper Bot${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}\n"

# Проверка существования директории
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ Директория $PROJECT_DIR не найдена!${NC}"
    exit 1
fi

cd "$PROJECT_DIR"

# Проверка изменений
echo -e "${YELLOW}📥 Проверка изменений на GitHub...${NC}"
git fetch origin

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})

if [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "${GREEN}✅ Нет новых изменений${NC}"
    read -p "Пересобрать и перезапустить в любом случае? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Отменено${NC}"
        exit 0
    fi
else
    echo -e "${GREEN}✅ Найдены новые изменения${NC}"
fi

# Получение изменений
echo -e "\n${YELLOW}📥 Получение изменений с GitHub...${NC}"
git pull

# Проверка изменений в requirements.txt или Dockerfile
FULL_REBUILD=false
if git diff HEAD@{1} --name-only | grep -q "requirements.txt\|Dockerfile"; then
    echo -e "${YELLOW}⚠️  Обнаружены изменения в requirements.txt или Dockerfile${NC}"
    echo -e "${YELLOW}   Требуется полная пересборка...${NC}"
    FULL_REBUILD=true
fi

# Остановка контейнера
echo -e "\n${YELLOW}🛑 Остановка контейнера...${NC}"
sudo docker-compose down

# Пересборка
if [ "$FULL_REBUILD" = true ]; then
    echo -e "\n${YELLOW}🔨 Полная пересборка (--no-cache)...${NC}"
    sudo docker-compose build --no-cache
else
    echo -e "\n${YELLOW}🔨 Быстрая пересборка...${NC}"
    sudo docker-compose build
fi

# Запуск
echo -e "\n${YELLOW}🚀 Запуск контейнера...${NC}"
sudo docker-compose up -d

# Ожидание запуска
echo -e "\n${YELLOW}⏳ Ожидание запуска (5 секунд)...${NC}"
sleep 5

# Проверка статуса
echo -e "\n${YELLOW}📊 Статус контейнера:${NC}"
sudo docker-compose ps

# Логи
echo -e "\n${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   ✅ Обновление завершено!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}\n"
echo -e "${BLUE}📋 Последние логи (Ctrl+C для выхода):${NC}\n"
sudo docker-compose logs -f --tail=50
```

**Сделать исполняемым:**

```bash
chmod +x ~/update-taobao.sh
```

**Использование:**

```bash
~/update-taobao.sh
```

**Что делает скрипт:**
- ✅ Проверяет наличие изменений на GitHub
- ✅ Спрашивает подтверждение если изменений нет
- ✅ Автоматически определяет нужна ли полная пересборка
- ✅ Показывает цветной вывод
- ✅ Проверяет статус после запуска
- ✅ Показывает логи

---

## 🛠️ Полезные команды

### Управление контейнером:

```bash
# Посмотреть статус контейнера
sudo docker-compose ps

# Посмотреть логи в реальном времени
sudo docker-compose logs -f

# Посмотреть последние N строк логов
sudo docker-compose logs --tail=100

# Посмотреть логи за последний час
sudo docker-compose logs --since=1h

# Перезапустить без пересборки
sudo docker-compose restart

# Остановить
sudo docker-compose stop

# Запустить (если остановлен)
sudo docker-compose start

# Остановить и удалить контейнер
sudo docker-compose down

# Войти в контейнер (для отладки)
sudo docker exec -it taobao-scraper-bot bash
```

### Работа с Git:

```bash
# Посмотреть статус
git status

# Посмотреть историю коммитов
git log --oneline -10

# Посмотреть изменения в конкретном файле
git diff filename.py

# Отменить локальные изменения
git checkout -- filename.py

# Обновить с GitHub
git pull

# Посмотреть удалённые ветки
git branch -r
```

### Мониторинг:

```bash
# Использование ресурсов контейнером
sudo docker stats taobao-scraper-bot

# Размер образа
sudo docker images | grep taobao

# Информация о контейнере
sudo docker inspect taobao-scraper-bot
```

---

## 🔧 Troubleshooting

### Проблема: "Your local changes would be overwritten by merge"

**Причина:** На сервере есть незакоммиченные изменения

**Решение 1** (сохранить изменения):
```bash
git stash
git pull
git stash pop
```

**Решение 2** (отменить изменения):
```bash
git checkout -- .
git pull
```

---

### Проблема: Контейнер не запускается после обновления

**Решение:**
```bash
# Полная очистка и пересборка
sudo docker-compose down
sudo docker rm -f taobao-scraper-bot
sudo docker rmi -f $(sudo docker images | grep taobao | awk '{print $3}')
sudo docker-compose build --no-cache
sudo docker-compose up -d
sudo docker-compose logs -f
```

---

### Проблема: Изменения в коде не применяются

**Причина:** Docker использует кэш

**Решение:**
```bash
sudo docker-compose build --no-cache
sudo docker-compose up -d --force-recreate
```

---

### Проблема: "Permission denied" при работе с Docker

**Решение:** Добавить пользователя в группу docker
```bash
sudo usermod -aG docker $USER
```

Затем выйти и зайти заново в SSH.

---

### Проблема: Мало места на диске

**Решение:** Очистить неиспользуемые образы и контейнеры
```bash
# Посмотреть использование места
sudo docker system df

# Очистить неиспользуемые ресурсы (БЕЗОПАСНО для других контейнеров)
sudo docker system prune -f

# Удалить неиспользуемые образы
sudo docker image prune -a -f

# Удалить неиспользуемые volumes (ОСТОРОЖНО!)
sudo docker volume prune -f
```

---

## 📊 Типичные сценарии

### Сценарий 1: Исправил баг в коде

```bash
# Локально: закоммитил и запушил в GitHub
git add .
git commit -m "Fix bug in scraper"
git push

# На сервере: обновление
cd ~/TaoBao_Scraper
git pull
sudo docker-compose up -d --build
sudo docker-compose logs -f --tail=30
```

**Время:** ~15-30 секунд

---

### Сценарий 2: Добавил новую библиотеку в requirements.txt

```bash
# Локально: обновил requirements.txt, закоммитил
git add requirements.txt
git commit -m "Add new dependency"
git push

# На сервере: полная пересборка
cd ~/TaoBao_Scraper
git pull
sudo docker-compose down
sudo docker-compose build --no-cache
sudo docker-compose up -d
sudo docker-compose logs -f
```

**Время:** ~2-3 минуты

---

### Сценарий 3: Изменил переменные окружения (.env)

```bash
# На сервере: редактировать .env
cd ~/TaoBao_Scraper
nano .env  # или vim .env

# Перезапустить
sudo docker-compose restart
sudo docker-compose logs -f --tail=20
```

**Время:** ~10 секунд

---

### Сценарий 4: Что-то сломалось, нужно откатиться

```bash
# Посмотреть историю коммитов
cd ~/TaoBao_Scraper
git log --oneline -10

# Откатиться на предыдущий коммит (например, abc1234)
git reset --hard abc1234

# Пересобрать
sudo docker-compose down
sudo docker-compose build --no-cache
sudo docker-compose up -d

# Позже вернуться обратно
git reset --hard origin/main
```

---

## ✅ Чек-лист обновления

- [ ] Зайти на сервер: `ssh user@server`
- [ ] Перейти в директорию: `cd ~/TaoBao_Scraper`
- [ ] Получить изменения: `git pull`
- [ ] Пересобрать: `sudo docker-compose up -d --build`
- [ ] Проверить логи: `sudo docker-compose logs -f --tail=50`
- [ ] Проверить статус: `sudo docker-compose ps`
- [ ] Протестировать бота в Telegram
- [ ] Убедиться что нет ошибок в логах

---

**Дата создания:** 2025-10-24  
**Версия:** 1.0  
**Автор:** TaoBao Scraper Team


# 🚀 CI/CD Pipeline - Руководство по настройке

## Обзор

В проекте настроен полностью автоматизированный CI/CD pipeline через GitHub Actions, который обеспечивает:

- ✅ **Автоматическую проверку кода** при каждом коммите
- 🐳 **Сборку и публикацию Docker образов** в GitHub Container Registry
- 🚀 **Автоматический деплой** на production сервер
- 🔒 **Сканирование безопасности** кода и зависимостей
- 📦 **Автоматические обновления** зависимостей через Dependabot

---

## 📋 Структура Pipeline

```
.github/
├── workflows/
│   ├── ci.yml              # Проверка качества кода
│   ├── docker-publish.yml  # Сборка и публикация Docker
│   ├── deploy.yml          # Автоматический деплой
│   └── security.yml        # Сканирование безопасности
└── dependabot.yml          # Автообновление зависимостей
```

---

## 🔄 Workflow процессы

### 1. CI - Проверка качества кода

**Триггеры:**
- Push в ветки `main` и `develop`
- Pull Request в `main` и `develop`

**Что проверяется:**
- Форматирование кода (Black, isort)
- Линтинг (flake8)
- Синтаксис Python файлов
- Валидация Docker Compose конфигурации

**Время выполнения:** ~2-3 минуты

---

### 2. Docker - Сборка и публикация

**Триггеры:**
- Push в ветку `main`
- Создание тега `v*.*.*`
- Ручной запуск через workflow_dispatch

**Что происходит:**
1. Сборка Docker образа для `linux/amd64` и `linux/arm64`
2. Публикация в GitHub Container Registry (ghcr.io)
3. Создание тегов:
   - `latest` - для main ветки
   - `v1.2.3` - для тегов версий
   - `main-abc1234` - SHA коммита

**Время выполнения:** ~5-7 минут

**Результат:**
```
ghcr.io/your-username/taobao-scraper:latest
ghcr.io/your-username/taobao-scraper:main-abc1234
```

---

### 3. Deploy - Автоматический деплой

**Триггеры:**
- Успешное завершение "Docker - Build and Push" для `main`
- Ручной запуск с выбором окружения (production/staging)

**Что происходит:**
1. Подключение к серверу по SSH
2. Создание backup `.env` файла
3. Pull нового Docker образа
4. Остановка старого контейнера
5. Запуск нового контейнера
6. Проверка статуса и логов
7. Очистка старых образов

**Время выполнения:** ~2-3 минуты

---

### 4. Security - Сканирование безопасности

**Триггеры:**
- Push в `main` и `develop`
- Каждый понедельник в 09:00 UTC (расписание)
- Ручной запуск

**Что проверяется:**
- Уязвимости в Python зависимостях (Safety, pip-audit)
- Проблемы безопасности в коде (Bandit)
- Уязвимости в Docker образе (Trivy)

**Время выполнения:** ~3-4 минуты

---

## 🔐 Настройка GitHub Secrets

### Шаг 1: Перейдите в настройки репозитория

```
GitHub Repository → Settings → Secrets and variables → Actions
```

### Шаг 2: Добавьте необходимые секреты

Нажмите **"New repository secret"** и добавьте следующие секреты:

#### Обязательные для деплоя:

| Название | Описание | Пример |
|----------|----------|--------|
| `SERVER_HOST` | IP адрес или домен вашего сервера | `192.168.1.100` или `server.example.com` |
| `SERVER_USER` | SSH пользователь на сервере | `ubuntu` или `root` |
| `SSH_PRIVATE_KEY` | Приватный SSH ключ для доступа | Содержимое `~/.ssh/id_rsa` |
| `SERVER_PORT` | Порт SSH (опционально, по умолчанию 22) | `22` |
| `DEPLOY_PATH` | Путь к директории на сервере | `/opt/taobao-scraper` |

#### Опционально (для других реестров):

| Название | Описание |
|----------|----------|
| `DOCKER_USERNAME` | Username в Docker Hub |
| `DOCKER_PASSWORD` | Token доступа в Docker Hub |

---

## 🖥️ Настройка Production сервера

### Шаг 1: Установите Docker на сервере

```bash
# Обновите систему
sudo apt update && sudo apt upgrade -y

# Установите Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установите Docker Compose
sudo apt install docker-compose-plugin -y

# Добавьте пользователя в группу docker
sudo usermod -aG docker $USER
```

### Шаг 2: Создайте SSH ключ для GitHub Actions

```bash
# На вашем локальном компьютере
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions

# Скопируйте публичный ключ на сервер
ssh-copy-id -i ~/.ssh/github_actions.pub user@your-server

# Содержимое приватного ключа добавьте в GitHub Secrets
cat ~/.ssh/github_actions
```

### Шаг 3: Подготовьте директорию на сервере

```bash
# Подключитесь к серверу
ssh user@your-server

# Создайте директорию для приложения
sudo mkdir -p /opt/taobao-scraper
sudo chown -R $USER:$USER /opt/taobao-scraper
cd /opt/taobao-scraper

# Инициализируйте Git (опционально)
git init
git remote add origin https://github.com/your-username/TaoBao_Scraper_2.git
git pull origin main

# Или создайте docker-compose.yml вручную
nano docker-compose.yml
```

### Шаг 4: Создайте docker-compose.yml на сервере

```yaml
version: '3.8'

services:
  taobao-bot:
    image: ghcr.io/your-username/taobao-scraper:latest
    container_name: taobao-scraper-bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - TZ=Europe/Moscow
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Шаг 5: Создайте .env файл на сервере

```bash
cd /opt/taobao-scraper
nano .env
```

Добавьте ваши реальные токены:

```env
# Telegram Bot
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# TMAPI
TMAPI_TOKEN=your_tmapi_token_here

# Yandex Cloud
YANDEX_GPT_API_KEY=your_yandex_api_key
YANDEX_FOLDER_ID=b1gxxxxxxxxxxxxxxxxx
YANDEX_GPT_MODEL=yandexgpt-lite

# Exchange Rate (опционально)
EXCHANGE_RATE_API_KEY=your_exchange_rate_key

# Настройки
CONVERT_CURRENCY=False
DEBUG_MODE=False
DISABLE_SSL_VERIFY=False
```

### Шаг 6: Настройте права доступа

```bash
# Защитите .env файл
chmod 600 .env

# Проверьте что Docker работает
docker --version
docker compose version

# Залогиньтесь в GitHub Container Registry
echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u your-username --password-stdin
```

---

## 🚀 Первый деплой

### Вариант 1: Автоматический деплой

```bash
# На локальной машине
git add .github/
git commit -m "feat: Add CI/CD pipeline"
git push origin main

# Pipeline автоматически:
# 1. Проверит код (CI)
# 2. Соберет Docker образ
# 3. Опубликует в GHCR
# 4. Задеплоит на сервер
```

### Вариант 2: Ручной деплой через GitHub UI

1. Перейдите в **Actions** tab
2. Выберите workflow **"Deploy - Auto Deploy to Server"**
3. Нажмите **"Run workflow"**
4. Выберите окружение (production/staging)
5. Нажмите **"Run workflow"**

### Вариант 3: Первый запуск вручную на сервере

```bash
# Подключитесь к серверу
ssh user@your-server
cd /opt/taobao-scraper

# Запустите контейнер
docker compose up -d

# Проверьте логи
docker compose logs -f taobao-bot

# Проверьте статус
docker compose ps
```

---

## 📊 Мониторинг и проверка

### Просмотр логов на сервере

```bash
# Последние 100 строк логов
docker compose logs --tail=100 taobao-bot

# Следить за логами в реальном времени
docker compose logs -f taobao-bot

# Логи с временными метками
docker compose logs -t taobao-bot
```

### Проверка статуса

```bash
# Статус контейнеров
docker compose ps

# Использование ресурсов
docker stats taobao-scraper-bot

# Проверка что бот работает
docker compose exec taobao-bot ps aux
```

### Просмотр workflow в GitHub

1. Перейдите в **Actions** tab в GitHub
2. Выберите нужный workflow
3. Просмотрите детали выполнения
4. Скачайте artifacts (отчеты безопасности)

---

## 🔄 Обновление приложения

### Автоматическое обновление

При каждом push в `main`:
1. ✅ Код проверяется автоматически
2. 🐳 Собирается новый Docker образ
3. 📦 Публикуется в GHCR
4. 🚀 Автоматически деплоится на сервер

**Ничего делать не нужно!** 🎉

### Ручное обновление на сервере

```bash
ssh user@your-server
cd /opt/taobao-scraper

# Получите последний образ
docker pull ghcr.io/your-username/taobao-scraper:latest

# Перезапустите контейнер
docker compose down
docker compose up -d

# Проверьте логи
docker compose logs -f taobao-bot
```

### Откат к предыдущей версии

```bash
# Используйте конкретный тег версии
docker pull ghcr.io/your-username/taobao-scraper:v1.0.0

# Обновите docker-compose.yml чтобы использовать нужный тег
nano docker-compose.yml
# Измените: image: ghcr.io/your-username/taobao-scraper:v1.0.0

# Перезапустите
docker compose up -d
```

---

## 🏷️ Создание релизов

### Создание версионного релиза

```bash
# Создайте тег
git tag -a v1.0.0 -m "Release version 1.0.0"

# Запушьте тег
git push origin v1.0.0

# GitHub Actions автоматически:
# - Соберет образ с тегами v1.0.0, v1.0, latest
# - Опубликует в GHCR
# - НЕ задеплоит автоматически (только для main branch)
```

### Ручной деплой конкретной версии

```bash
# Через GitHub UI
Actions → Deploy → Run workflow → Выберите branch/tag v1.0.0

# Или на сервере
ssh user@your-server
cd /opt/taobao-scraper
docker pull ghcr.io/your-username/taobao-scraper:v1.0.0
# Обновите docker-compose.yml
docker compose up -d
```

---

## 🔧 Troubleshooting

### Pipeline не запускается

**Проблема:** Workflow не появляется в Actions tab

**Решение:**
```bash
# Проверьте что файлы в правильной директории
ls -la .github/workflows/

# Проверьте синтаксис YAML
# Используйте онлайн валидатор: https://www.yamllint.com/

# Запушьте изменения
git add .github/
git commit -m "fix: Update workflows"
git push origin main
```

### Ошибка при деплое

**Проблема:** SSH connection failed

**Решение:**
```bash
# Проверьте SSH подключение вручную
ssh -i ~/.ssh/github_actions user@your-server

# Проверьте секреты в GitHub
# Settings → Secrets → Проверьте SERVER_HOST, SERVER_USER, SSH_PRIVATE_KEY

# Убедитесь что публичный ключ добавлен на сервер
cat ~/.ssh/github_actions.pub
# Добавьте в ~/.ssh/authorized_keys на сервере
```

**Проблема:** Docker pull failed

**Решение:**
```bash
# На сервере залогиньтесь в GHCR
echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u your-username --password-stdin

# Проверьте что образ существует
docker pull ghcr.io/your-username/taobao-scraper:latest
```

**Проблема:** Container не запускается

**Решение:**
```bash
# Проверьте логи
docker compose logs taobao-bot

# Проверьте .env файл
cat .env

# Проверьте права доступа
ls -la .env

# Запустите в интерактивном режиме для отладки
docker compose run --rm taobao-bot /bin/bash
```

### Docker build failed

**Проблема:** Build fails in GitHub Actions

**Решение:**
1. Проверьте Dockerfile локально:
   ```bash
   docker build -t test .
   ```

2. Проверьте логи в GitHub Actions

3. Убедитесь что все файлы закоммичены:
   ```bash
   git status
   git add requirements.txt Dockerfile docker-compose.yml
   git commit -m "fix: Add missing files"
   git push
   ```

### Dependabot PR не создаются

**Проблема:** Нет автоматических обновлений

**Решение:**
1. Проверьте `.github/dependabot.yml`
2. Убедитесь что Dependabot включен:
   - Settings → Code security and analysis → Dependabot
3. Включите "Dependabot version updates"

---

## 📈 Расширенные настройки

### Добавление уведомлений в Telegram

Создайте `.github/workflows/notify.yml`:

```yaml
name: Telegram Notifications

on:
  workflow_run:
    workflows: ["Deploy - Auto Deploy to Server"]
    types:
      - completed

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
    - name: Send Telegram notification
      uses: appleboy/telegram-action@master
      with:
        to: ${{ secrets.TELEGRAM_CHAT_ID }}
        token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
        message: |
          🚀 Deployment ${{ github.event.workflow_run.conclusion }}
          Repository: ${{ github.repository }}
          Branch: ${{ github.ref }}
          Commit: ${{ github.sha }}
```

### Добавление staging окружения

Обновите `.github/workflows/deploy.yml`, добавьте условие для staging:

```yaml
- name: Deploy to staging
  if: github.ref == 'refs/heads/develop'
  # ... SSH action для staging сервера
```

### Кэширование Docker слоев

Уже настроено в `docker-publish.yml`:
```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

Это ускоряет сборку до 3-5 раз!

---

## ✅ Checklist перед использованием

- [ ] GitHub Secrets настроены (`SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY`)
- [ ] SSH ключ добавлен на сервер
- [ ] Docker установлен на сервере
- [ ] Директория `/opt/taobao-scraper` создана
- [ ] `docker-compose.yml` создан на сервере
- [ ] `.env` файл с токенами создан на сервере
- [ ] Тестовое SSH подключение работает
- [ ] Workflow файлы закоммичены в `.github/workflows/`
- [ ] Первый push в `main` сделан
- [ ] Pipeline запустился в Actions tab
- [ ] Docker образ опубликован в GHCR
- [ ] Бот успешно задеплоен и работает

---

## 📚 Полезные ссылки

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Documentation](https://docs.docker.com/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)

---

## 🎉 Готово!

Теперь у вас есть полностью автоматизированный CI/CD pipeline! Каждый commit в `main` автоматически:

1. ✅ Проверяется на качество кода
2. 🐳 Собирается в Docker образ
3. 📦 Публикуется в GitHub Container Registry
4. 🚀 Деплоится на production сервер
5. ✔️ Проверяется что все работает

**Просто пишите код и пушьте в `main` - все остальное произойдет автоматически!** 🎊


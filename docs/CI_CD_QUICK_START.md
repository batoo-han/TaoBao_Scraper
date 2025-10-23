# 🚀 CI/CD Quick Start - Быстрая настройка

## За 5 минут до автоматического деплоя

### 📋 Что вам понадобится:

- ✅ GitHub репозиторий
- ✅ VPS сервер с Ubuntu/Debian
- ✅ SSH доступ к серверу
- ✅ 5 минут времени

---

## Шаг 1: Создайте SSH ключ (1 минута)

```bash
# На вашем компьютере
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions

# Скопируйте на сервер
ssh-copy-id -i ~/.ssh/github_actions.pub user@your-server.com
```

---

## Шаг 2: Добавьте GitHub Secrets (2 минуты)

Перейдите: **GitHub → Settings → Secrets and variables → Actions → New secret**

Добавьте 3 обязательных секрета:

| Название | Значение |
|----------|----------|
| `SERVER_HOST` | IP вашего сервера (например: `192.168.1.100`) |
| `SERVER_USER` | SSH пользователь (например: `ubuntu`) |
| `SSH_PRIVATE_KEY` | Содержимое файла `~/.ssh/github_actions` |

**Как скопировать приватный ключ:**
```bash
# Linux/Mac
cat ~/.ssh/github_actions | pbcopy  # Mac
cat ~/.ssh/github_actions | xclip   # Linux

# Windows
type %USERPROFILE%\.ssh\github_actions | clip
```

---

## Шаг 3: Настройте сервер (2 минуты)

```bash
# Подключитесь к серверу
ssh user@your-server.com

# Установите Docker (если еще не установлен)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Создайте директорию
mkdir -p /opt/taobao-scraper
cd /opt/taobao-scraper

# Создайте docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  taobao-bot:
    image: ghcr.io/YOUR_GITHUB_USERNAME/taobao-scraper:latest
    container_name: taobao-scraper-bot
    restart: unless-stopped
    env_file: .env
    environment:
      - TZ=Europe/Moscow
EOF

# Создайте .env файл с вашими токенами
nano .env
```

**Содержимое .env:**
```env
BOT_TOKEN=your_bot_token
TMAPI_TOKEN=your_tmapi_token
YANDEX_GPT_API_KEY=your_yandex_key
YANDEX_FOLDER_ID=your_folder_id
YANDEX_GPT_MODEL=yandexgpt-lite
CONVERT_CURRENCY=False
DEBUG_MODE=False
```

---

## Шаг 4: Запустите Pipeline (30 секунд)

```bash
# На вашем компьютере
git add .github/
git commit -m "feat: Add CI/CD pipeline"
git push origin main
```

---

## ✅ Готово!

Перейдите в **GitHub → Actions** и наблюдайте за магией:

1. ⚙️ **CI** - проверка кода (2 мин)
2. 🐳 **Docker Build** - сборка образа (5 мин)  
3. 🚀 **Deploy** - деплой на сервер (2 мин)

**Общее время: ~9 минут** ⏱️

---

## 🎯 Проверка результата

```bash
# На сервере
ssh user@your-server.com
cd /opt/taobao-scraper

# Проверьте статус
docker compose ps

# Смотрите логи
docker compose logs -f taobao-bot
```

Бот должен быть запущен и работать! 🎉

---

## 🔄 Что дальше?

Теперь при каждом `git push origin main`:
- ✅ Автоматическая проверка кода
- 🐳 Сборка нового Docker образа
- 🚀 **Автоматический деплой на сервер**

**Просто пишите код и пушьте - всё происходит автоматически!**

---

## ❓ Проблемы?

### Pipeline не запускается
- Проверьте что файлы в `.github/workflows/` закоммичены
- Проверьте Actions tab в GitHub

### Деплой не работает
- Проверьте GitHub Secrets (правильный ли SSH ключ?)
- Проверьте SSH подключение: `ssh -i ~/.ssh/github_actions user@server`
- Посмотрите логи в Actions → Deploy workflow

### Контейнер не запускается
- Проверьте `.env` файл на сервере
- Посмотрите логи: `docker compose logs taobao-bot`
- Проверьте что токены правильные

---

## 📚 Подробная документация

См. [CI_CD_SETUP.md](CI_CD_SETUP.md) для детального руководства

---

## 🎊 Поздравляем!

Вы настроили production-ready CI/CD pipeline за 5 минут!


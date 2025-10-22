# Настройка GitHub репозитория 🐙

Руководство по подготовке и публикации проекта на GitHub.

---

## 📝 Подготовка к публикации

### 1. Проверка файлов

Убедитесь что следующие файлы на месте:

#### ✅ Обязательные файлы:
- [x] `README.md` - описание проекта
- [x] `LICENSE` - лицензия (MIT)
- [x] `.gitignore` - игнорируемые файлы
- [x] `requirements.txt` - зависимости
- [x] `.env.example` - пример конфигурации
- [x] `CONTRIBUTING.md` - руководство для контрибьюторов

#### ✅ Docker файлы:
- [x] `Dockerfile`
- [x] `docker-compose.yml`
- [x] `.dockerignore`

#### ✅ Документация:
- [x] `docs/SERVICES_SETUP.md`
- [x] `docs/DEPLOYMENT.md`
- [x] `docs/FAQ.md`
- [x] И другие...

### 2. Проверка .gitignore

Убедитесь что `.gitignore` содержит:

```gitignore
# Секреты
.env

# Python
__pycache__/
*.pyc
.venv/

# IDE
.vscode/
.idea/

# Локальные данные
other/
result.txt
test_*.py
```

### 3. Проверка что .env НЕ в репозитории

```bash
# Проверьте что .env НЕ отслеживается
git status

# Если .env показывается, удалите из tracking:
git rm --cached .env
```

---

## 🚀 Создание репозитория

### Вариант 1: Через веб-интерфейс GitHub

1. **Создайте репозиторий:**
   - Откройте [github.com/new](https://github.com/new)
   - Имя: `TaoBao_Scraper_2` (или ваше название)
   - Описание: `Telegram bot for parsing Taobao/Tmall with AI-powered post generation`
   - Visibility: `Public` или `Private`
   - **НЕ** инициализируйте с README (у нас уже есть)
   - Нажмите "Create repository"

2. **Свяжите локальный репозиторий:**
   ```bash
   cd J:\PyProject\TaoBao_Scraper_2
   git init
   git add .
   git commit -m "Initial commit: Taobao Scraper Bot v2.2"
   git branch -M main
   git remote add origin https://github.com/your-username/TaoBao_Scraper_2.git
   git push -u origin main
   ```

### Вариант 2: Через GitHub CLI

```bash
# Установите GitHub CLI: https://cli.github.com/

# Создайте репозиторий и загрузите код
cd J:\PyProject\TaoBao_Scraper_2
git init
git add .
git commit -m "Initial commit: Taobao Scraper Bot v2.2"
gh repo create TaoBao_Scraper_2 --public --source=. --push
```

---

## 🏷️ Настройка репозитория

### 1. Описание и темы

**Description:**
```
AI-powered Telegram bot for parsing Taobao/Tmall and generating beautiful product posts
```

**Topics/Tags:**
- `telegram-bot`
- `taobao`
- `tmall`
- `ai`
- `yandexgpt`
- `python`
- `aiogram`
- `web-scraping`
- `docker`

### 2. README badges

Уже добавлены в README.md:
- Python version
- License
- Docker ready

### 3. GitHub Actions (опционально)

Создайте `.github/workflows/docker-build.yml`:

```yaml
name: Docker Build

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Build Docker image
      run: docker build . --file Dockerfile --tag taobao-bot:latest
```

### 4. Issue templates

Создайте `.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug report
about: Create a report to help us improve
title: '[BUG] '
labels: bug
assignees: ''
---

**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior.

**Expected behavior**
What you expected to happen.

**Environment:**
- Python version:
- OS:
- Docker: Yes/No

**Additional context**
Logs, screenshots, etc.
```

---

## 📦 Создание Release

### 1. Подготовка

```bash
# Убедитесь что всё закоммичено
git status

# Создайте tag
git tag -a v2.2.0 -m "Release v2.2.0: Full documentation and Docker support"
git push origin v2.2.0
```

### 2. Создание Release на GitHub

1. Перейдите в "Releases" → "Create a new release"
2. Выберите tag: `v2.2.0`
3. Название: `v2.2.0 - Production Ready`
4. Описание:

```markdown
## 🎉 Release v2.2.0

### ✨ Features
- AI-powered post generation with YandexGPT
- Support for multiple product images
- HTML formatting in Telegram
- Docker and Docker Compose support
- Comprehensive documentation

### 📚 Documentation
- Complete setup guides
- API services registration instructions
- Deployment guide
- FAQ

### 🐛 Bug Fixes
- SSL certificate handling
- TMAPI integration fixed
- Image processing improvements

### 📦 Installation
See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for details.
```

---

## 🔒 Безопасность

### 1. Secrets в GitHub Actions

Если используете CI/CD:

1. Settings → Secrets and variables → Actions
2. Добавьте secrets:
   - `BOT_TOKEN`
   - `TMAPI_TOKEN`
   - `YANDEX_GPT_API_KEY`
   - И другие...

### 2. Dependabot

Включите Dependabot для автоматического обновления зависимостей:

1. Settings → Security → Code security and analysis
2. Enable "Dependabot alerts"
3. Enable "Dependabot security updates"

### 3. Branch protection

Для `main` ветки:

1. Settings → Branches → Add rule
2. Branch name pattern: `main`
3. Включите:
   - [x] Require pull request before merging
   - [x] Require status checks to pass

---

## 📣 Продвижение проекта

### 1. README badges

Добавьте больше badges:

```markdown
[![Stars](https://img.shields.io/github/stars/your-username/TaoBao_Scraper_2?style=social)](https://github.com/your-username/TaoBao_Scraper_2)
[![Issues](https://img.shields.io/github/issues/your-username/TaoBao_Scraper_2)](https://github.com/your-username/TaoBao_Scraper_2/issues)
[![Docker Pulls](https://img.shields.io/docker/pulls/your-username/taobao-bot)](https://hub.docker.com/r/your-username/taobao-bot)
```

### 2. Опубликуйте на Docker Hub (опционально)

```bash
# Войдите в Docker Hub
docker login

# Соберите образ
docker build -t your-username/taobao-bot:latest .

# Загрузите
docker push your-username/taobao-bot:latest
```

### 3. Добавьте в awesome-lists

Найдите relevant awesome-lists на GitHub и предложите ваш проект.

---

## 🔄 Workflow для обновлений

### Регулярные обновления

```bash
# Создайте ветку
git checkout -b feature/new-feature

# Внесите изменения
# ...

# Коммит и push
git add .
git commit -m "feat: add new feature"
git push origin feature/new-feature

# Создайте Pull Request на GitHub
```

### Hotfix

```bash
git checkout -b hotfix/critical-bug
# Исправьте баг
git add .
git commit -m "fix: critical bug in tmapi client"
git push origin hotfix/critical-bug
# Создайте PR с меткой "urgent"
```

---

## 📊 Analytics

### GitHub Insights

Регулярно проверяйте:
- **Traffic** - кто посещает репозиторий
- **Clones** - сколько раз клонировали
- **Popular content** - какие файлы смотрят
- **Referrers** - откуда приходят

### Star History

Отслеживайте рост популярности:
- [Star History Chart](https://star-history.com/)

---

## ✅ Checklist публикации

- [ ] `.env` не в репозитории
- [ ] `.gitignore` настроен
- [ ] README.md заполнен
- [ ] LICENSE добавлен
- [ ] Документация полная
- [ ] CONTRIBUTING.md готов
- [ ] `.env.example` создан
- [ ] Все секретные данные удалены из кода
- [ ] Тестовые файлы не включены
- [ ] Dockerfile работает
- [ ] docker-compose.yml настроен
- [ ] Создан первый release
- [ ] Описание и topics добавлены

---

## 🎯 После публикации

1. **Поделитесь:**
   - Reddit (r/Python, r/learnpython)
   - Twitter/X
   - Dev.to
   - Хабр (если русскоязычная аудитория)

2. **Мониторьте:**
   - Issues
   - Pull Requests
   - Stars и Forks

3. **Обновляйте:**
   - Регулярные релизы
   - Ответы на Issues
   - Мердж PR

---

<p align="center">
  <b>Удачи с вашим open source проектом! 🚀</b>
</p>


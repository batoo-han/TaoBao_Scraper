# 🔐 GitHub Secrets Setup Guide

## Быстрая настройка секретов для CI/CD

### 1. Создайте SSH ключ

```bash
# На вашем компьютере
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions

# Скопируйте публичный ключ на сервер
ssh-copy-id -i ~/.ssh/github_actions.pub YOUR_USER@YOUR_SERVER_IP
```

### 2. Добавьте секреты в GitHub

**Путь:** `Settings → Secrets and variables → Actions → New repository secret`

#### Обязательные секреты:

**SERVER_HOST**
```
YOUR_SERVER_IP
```
Пример: `192.168.1.100` или `server.example.com`

---

**SERVER_USER**
```
YOUR_SSH_USERNAME
```
Пример: `ubuntu`, `root`, `deploy`

---

**SSH_PRIVATE_KEY**
```bash
# Получите содержимое приватного ключа:
cat ~/.ssh/github_actions

# Скопируйте ВСЁ от "-----BEGIN" до "-----END"
```
Пример:
```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
...
ваш ключ полностью
...
-----END OPENSSH PRIVATE KEY-----
```

---

#### Опциональные секреты:

**SERVER_PORT** (если SSH не на порту 22)
```
22
```

**DEPLOY_PATH** (если путь не `/opt/taobao-scraper`)
```
/opt/taobao-scraper
```

---

### 3. Проверьте SSH подключение

```bash
# Проверьте что подключение работает
ssh -i ~/.ssh/github_actions YOUR_USER@YOUR_SERVER_IP

# Должны подключиться без запроса пароля
```

---

### ✅ Готово!

Теперь можно пушить в `main` и деплой будет работать автоматически!

```bash
git push origin main
```

Отслеживайте прогресс: **GitHub → Actions → Deploy workflow**

---

### ❓ Проблемы?

**SSH подключение не работает:**
```bash
# Проверьте права на файл
chmod 600 ~/.ssh/github_actions

# Проверьте что ключ добавлен на сервер
cat ~/.ssh/github_actions.pub
# Должен быть в ~/.ssh/authorized_keys на сервере
```

**Деплой падает с ошибкой:**
- Проверьте что секреты добавлены правильно (без лишних пробелов)
- Проверьте логи в Actions → Deploy workflow → View logs
- Убедитесь что на сервере установлен Docker

---

### 📚 Подробная документация

См. [CI_CD_SETUP.md](../docs/CI_CD_SETUP.md) для полного руководства


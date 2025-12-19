# ⚡ Быстрое исправление ошибки Permission denied

Если вы получили ошибку:
```
PermissionError: [Errno 13] Permission denied: '/app/logs/bot_errors.log'
```

## 🚀 Быстрое решение (1 команда)

```bash
# Остановите контейнер
docker compose down

# Настройте права автоматически
./scripts/setup_permissions.sh

# Запустите снова
docker compose up -d
```

## 🔧 Ручное решение

```bash
# Остановите контейнер
docker compose down

# Создайте папки
mkdir -p data logs

# Установите владельца (UID 1000 = botuser в контейнере)
sudo chown -R 1000:1000 data logs

# Установите права доступа
sudo chmod -R 755 data logs
sudo find data -type f -name "*.json" -exec chmod 644 {} \;

# Запустите снова
docker compose up -d
```

## ✅ Проверка

```bash
# Проверьте права
ls -ld data logs

# Должно быть:
# drwxr-xr-x ... data
# drwxr-xr-x ... logs

# Проверьте логи
docker compose logs -f taobao-bot
```

**Подробнее:** [DOCKER_PERMISSIONS.md](DOCKER_PERMISSIONS.md)


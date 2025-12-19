# ⚡ Быстрый перенос бота на новый сервер

Краткая инструкция для опытных пользователей.

## 📤 Экспорт со старого сервера

```bash
# На старом сервере
cd /path/to/TaoBao_Scraper

# Автоматический экспорт (рекомендуется)
./scripts/export_data.sh

# Или ручной экспорт
tar -czf bot_backup_$(date +%Y%m%d).tar.gz \
  .env data/ logs/bot_errors.log

# Копирование на локальный компьютер
scp user@old-server:/path/to/TaoBao_Scraper/backups/bot_backup_*.tar.gz ./
```

## 📥 Импорт на новый сервер

```bash
# На новом сервере
cd /opt
git clone <repository-url> taobao-scraper-bot
cd taobao-scraper-bot

# Копирование архива
scp bot_backup_*.tar.gz user@new-server:/opt/taobao-scraper-bot/

# Автоматический импорт (рекомендуется)
./scripts/import_data.sh bot_backup_*.tar.gz

# Или ручной импорт
tar -xzf bot_backup_*.tar.gz
chmod 600 .env
chmod 644 data/*.json

# Настройка прав доступа (ВАЖНО!)
./scripts/setup_permissions.sh

# Запуск
docker-compose up -d
```

## ✅ Проверка

```bash
# Логи
docker-compose logs -f taobao-bot

# Тест в Telegram
# Отправьте /start боту
```

## 📋 Критически важные файлы

- `.env` - все токены
- `data/access_control.json` - списки доступа
- `data/user_settings.json` - настройки пользователей
- `data/rate_limits.json` - лимиты

**Полная инструкция:** [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)

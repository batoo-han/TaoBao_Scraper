# ⚡ Быстрые команды - Шпаргалка

Краткая справка по часто используемым командам для работы с TaoBao Scraper Bot.

---

## 🚀 Обновление бота на сервере

### Стандартное обновление (используйте по умолчанию):

```bash
cd ~/TaoBao_Scraper && git pull && sudo docker-compose up -d --build && sudo docker-compose logs -f --tail=50
```

---

## 📊 Мониторинг

```bash
# Логи в реальном времени
sudo docker-compose logs -f

# Последние 100 строк логов
sudo docker-compose logs --tail=100

# Статус контейнера
sudo docker-compose ps

# Использование ресурсов
sudo docker stats taobao-scraper-bot
```

---

## 🔄 Управление контейнером

```bash
# Перезапуск
sudo docker-compose restart

# Остановка
sudo docker-compose stop

# Запуск
sudo docker-compose start

# Остановка и удаление
sudo docker-compose down

# Полная пересборка (если что-то сломалось)
sudo docker-compose down && sudo docker-compose build --no-cache && sudo docker-compose up -d
```

---

## 🛠️ Troubleshooting

```bash
# Полная очистка и пересборка
sudo docker-compose down
sudo docker rm -f taobao-scraper-bot
sudo docker rmi -f $(sudo docker images | grep taobao | awk '{print $3}')
sudo docker-compose build --no-cache
sudo docker-compose up -d

# Войти в контейнер для отладки
sudo docker exec -it taobao-scraper-bot bash

# Очистка неиспользуемых ресурсов
sudo docker system prune -f
```

---

## 📁 Git

```bash
# Статус
git status

# Обновить с GitHub
git pull

# Отменить локальные изменения
git checkout -- .

# История коммитов
git log --oneline -10
```

---

## 🔐 Команды бота для администраторов

```bash
# В Telegram боте:

/access          # Управление доступом (белый/чёрный список)
/dump_data       # Аварийный экспорт всех настроек в JSON
                 # Выводит user_settings.json и access_control.json
                 # Полезно для резервного копирования перед обновлением
```

---

## 🤖 Alias для автоматизации

Добавьте в `~/.bashrc`:

```bash
# TaoBao Bot aliases
alias update-bot="cd ~/TaoBao_Scraper && git pull && sudo docker-compose up -d --build && sudo docker-compose logs -f --tail=50"
alias bot-logs="cd ~/TaoBao_Scraper && sudo docker-compose logs -f --tail=100"
alias bot-status="cd ~/TaoBao_Scraper && sudo docker-compose ps"
alias bot-restart="cd ~/TaoBao_Scraper && sudo docker-compose restart"
```

Затем: `source ~/.bashrc`

Использование:
- `update-bot` - обновить
- `bot-logs` - логи
- `bot-status` - статус
- `bot-restart` - перезапуск

---

## 📚 Подробная документация

- [update_WORKFLOW.md](UPDATE_WORKFLOW.md) - Полное руководство по обновлению
- [deployment.md](DEPLOYMENT.md) - Развёртывание и настройка
- [services_SETUP.md](SERVICES_SETUP.md) - Настройка API сервисов

---

**Дата создания:** 2025-10-24

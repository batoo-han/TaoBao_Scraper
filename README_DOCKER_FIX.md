# Исправление ошибки KeyError: 'ContainerConfig'

Эта ошибка возникает из-за повреждённого или устаревшего Docker образа/контейнера.

## Быстрое решение

Выполните на сервере следующие команды:

```bash
# 1. Остановите и удалите старые контейнеры
sudo docker-compose down

# 2. Удалите старые контейнеры вручную (если нужно)
sudo docker ps -a | grep taobao-scraper-bot
sudo docker rm -f <CONTAINER_ID>  # замените на ID из предыдущей команды

# 3. Удалите старые образы
sudo docker images | grep taobao
sudo docker rmi -f <IMAGE_ID>  # замените на ID образа

# 4. Очистите систему Docker
sudo docker system prune -f

# 5. Пересоберите образ с нуля (без кэша)
sudo docker-compose build --no-cache --pull

# 6. Запустите контейнер
sudo docker-compose up -d

# 7. Проверьте логи
sudo docker-compose logs -f
```

## Автоматическое исправление

Или используйте готовый скрипт:

```bash
# Сделайте скрипт исполняемым
chmod +x docker-fix.sh

# Запустите скрипт
./docker-fix.sh
```

## Альтернативное решение (если проблема сохраняется)

Если проблема не решается, попробуйте использовать Docker Compose v2:

```bash
# Установите Docker Compose v2 (если не установлен)
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Используйте новую команду
sudo docker compose build --no-cache --pull
sudo docker compose up -d
sudo docker compose logs -f
```

## Проверка версии docker-compose

```bash
docker-compose --version
# Если версия 1.x.x - рекомендуется обновить до 2.x.x
```

## Дополнительная информация

Ошибка `KeyError: 'ContainerConfig'` обычно возникает когда:
- образ контейнера был повреждён при сборке
- несовместимость версий docker-compose (старая версия 1.29.2)
- остатки от предыдущих сборок

Решение - полностью удалить старые контейнеры и образы, затем пересобрать с нуля.
# OpenAI Gateway (Docker) для Taobao Scraper Bot

Этот документ описывает, как развернуть лёгкий прокси‑шлюз для OpenAI на зарубежном сервере с помощью Docker и подключить его к боту.

## Архитектура

- каталог `openai_gateway/` в репозитории содержит мини‑приложение на FastAPI;
- Docker‑контейнер слушает порт `8080` на зарубежном сервере и проксирует запросы `/v1/*` → `https://api.openai.com/v1/*`;
- настоящий `OPENAI_API_KEY` хранится **только** на зарубежном сервере в `.env`;
- бот в РФ обращается к шлюзу по HTTPS (`https://llm-gw.example.com/v1`) и авторизуется через заголовок `X-Gateway-Token`.

## Развёртывание шлюза на зарубежном сервере (быстрый старт)

1. Скопируйте папку `openai_gateway/` на зарубежный сервер (например через `git clone` того же репозитория).

2. Создайте `.env` на основе `.env.example`:

   ```bash
   cd openai_gateway
   cp .env.example .env
   nano .env
   ```

   Укажите реальные значения:

   ```env
   OPENAI_API_KEY=sk-...            # реальный ключ OpenAI
   GATEWAY_TOKEN=super-secret       # общий токен между шлюзом и ботом
   OPENAI_BASE_URL=https://api.openai.com/v1
   ```

3. Соберите и запустите контейнер шлюза:

   ```bash
   cd openai_gateway
   docker-compose build
   docker-compose up -d
   ```

4. Проверьте health‑эндпоинт на зарубежном сервере:

   ```bash
   curl http://127.0.0.1:8080/health
   # ответ: {"status":"ok"}
   ```

5. Настройте внешнее HTTPS‑доступное имя (например `https://llm-gw.example.com`) через nginx / Caddy / Traefik или через уже существующий XRay:

   - внешний reverse‑proxy принимает TLS;
   - внутренний upstream — `127.0.0.1:8080`;
   - при желании можно ограничить доступ по IP‑адресу сервера, где крутится бот.

## Подключение бота к шлюзу

На российском сервере, в `.env` бота добавьте:

```env
OPENAI_BASE_URL=https://llm-gw.example.com/v1
OPENAI_GATEWAY_TOKEN=super-secret   # тот же, что в GATEWAY_TOKEN на шлюзе
```

В коде бота `OpenAIClient` использует эти переменные:

- `OPENAI_BASE_URL` перенастраивает базовый URL клиента OpenAI на ваш шлюз;
- `OPENAI_GATEWAY_TOKEN` добавляется в заголовок `X-Gateway-Token` для авторизации на шлюзе.

Если `OPENAI_BASE_URL` пустой — клиент работает напрямую с `https://api.openai.com/v1` (для локальной разработки за пределами РФ).

## Безопасность

- **никогда** не храните реальный `OPENAI_API_KEY` в `.env` бота — он нужен только шлюзу;
- токен `GATEWAY_TOKEN`/`OPENAI_GATEWAY_TOKEN` должен быть достаточно длинным и случайным;
- желательно ограничить доступ к шлюзу по IP (firewall / nginx `allow`/`deny`), чтобы не превратить его в общий открытый прокси;
- логи шлюза не должны печатать полный ключ OpenAI.

## Обновление шлюза

При изменении кода прокси на зарубежном сервере достаточно выполнить:

```bash
cd openai_gateway
git pull          # если используете git
docker-compose build --no-cache
docker-compose up -d
```

Бот в РФ при этом перезапускать не нужно, если URL и токен не менялись.

---

## Подробный сценарий с nginx + HTTPS

Ниже — пример, как развернуть **nginx + openai-gateway** на одном сервере с общим `docker-compose.yml`.

### Структура каталогов

```text
/opt/taobao-bot/
  docker-compose.yml        # общий docker-compose для nginx + шлюза
  openai_gateway/           # папка шлюза (этот проект)
    app.py
    Dockerfile
    requirements.txt
    .env
  nginx/
    nginx.conf              # конфигурация nginx
    logs/                   # директория для логов nginx
```

### Пример docker-compose.yml (nginx + gateway)

```yaml
version: "3.9"

services:
  openai-gateway:
    build:
      context: ./openai_gateway
      dockerfile: Dockerfile
    container_name: openai-gateway
    restart: unless-stopped
    env_file:
      - ./openai_gateway/.env
    expose:
      - "8080"
    networks:
      - llm_net

  nginx:
    image: nginx:alpine
    container_name: openai-gateway-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - ./nginx/logs:/var/log/nginx
    depends_on:
      - openai-gateway
    networks:
      - llm_net

networks:
  llm_net:
    driver: bridge
```

### Пример nginx.conf

```nginx
user  nginx;
worker_processes  auto;

events {
    worker_connections  1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    sendfile        on;
    keepalive_timeout  65;

    access_log  /var/log/nginx/access.log;
    error_log   /var/log/nginx/error.log warn;

    upstream openai_gateway_upstream {
        server openai-gateway:8080;
    }

    server {
        listen 80;
        server_name llm-gw.example.com;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name llm-gw.example.com;

        ssl_certificate     /etc/letsencrypt/live/llm-gw.example.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/llm-gw.example.com/privkey.pem;

        ssl_protocols       TLSv1.2 TLSv1.3;
        ssl_ciphers         HIGH:!aNULL:!MD5;

        location /health {
            proxy_pass http://openai_gateway_upstream/health;
            proxy_set_header Host $host;
        }

        location /v1/ {
            proxy_pass http://openai_gateway_upstream$request_uri;
            proxy_http_version 1.1;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_buffering off;
        }
    }
}
```

### Сценарий развертывания

1. Выдайте сертификат Let’s Encrypt для домена `llm-gw.example.com` (вне Docker или через отдельный контейнер certbot).
2. Скопируйте папки `openai_gateway/` и `nginx/` и файл `docker-compose.yml` на зарубежный сервер в каталог `/opt/taobao-bot/`.
3. Убедитесь, что пути к сертификатам в `nginx.conf` совпадают с фактическим расположением (`/etc/letsencrypt/...`).
4. Запустите:

   ```bash
   cd /opt/taobao-bot
   docker-compose build
   docker-compose up -d
   ```

5. Проверьте:

   ```bash
   curl https://llm-gw.example.com/health -k
   ```

6. После этого на российском сервере просто используйте:

   ```env
   OPENAI_BASE_URL=https://llm-gw.example.com/v1
   OPENAI_GATEWAY_TOKEN=super-secret
   ```




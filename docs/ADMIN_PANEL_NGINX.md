# Настройка админ-панели через Nginx на Ubuntu Server

> **Версия:** 1.0.0  
> **Дата:** 2025-11-12

---

## 📋 Содержание

1. [Требования](#требования)
2. [Установка Nginx](#установка-nginx)
3. [Настройка Nginx](#настройка-nginx)
4. [SSL сертификат (Let's Encrypt)](#ssl-сертификат-lets-encrypt)
5. [Запуск приложения](#запуск-приложения)
6. [Проверка работы](#проверка-работы)
7. [Troubleshooting](#troubleshooting)

---

## Требования

- Ubuntu Server 20.04+ или 22.04+
- Python 3.11+
- PostgreSQL (уже настроен)
- Доменное имя (для SSL) или IP адрес
- Права sudo

---

## Установка Nginx

```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем Nginx
sudo apt install -y nginx

# Проверяем статус
sudo systemctl status nginx

# Включаем автозапуск
sudo systemctl enable nginx
```

---

## Настройка Nginx

### 1. Создаем конфигурационный файл

```bash
sudo nano /etc/nginx/sites-available/taobao-admin
```

### 2. Конфигурация для HTTP (без SSL)

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Замените на ваш домен или IP

    # Логи
    access_log /var/log/nginx/taobao-admin-access.log;
    error_log /var/log/nginx/taobao-admin-error.log;

    # Максимальный размер загружаемых файлов
    client_max_body_size 10M;

    # Проксирование на админ-панель (порт 8004)
    location / {
        proxy_pass http://127.0.0.1:8004;
        proxy_http_version 1.1;
        
        # Заголовки для корректной работы
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Статические файлы (опционально, если нужно кеширование)
    location /static/ {
        proxy_pass http://127.0.0.1:8004/static/;
        proxy_cache_valid 200 1h;
        add_header Cache-Control "public, immutable";
    }

    # API endpoints
    location /api/ {
        proxy_pass http://127.0.0.1:8004/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 3. Конфигурация для HTTPS (с SSL)

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Редирект на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL сертификаты (будут созданы через certbot)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # SSL настройки (современные и безопасные)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # HSTS (опционально)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Логи
    access_log /var/log/nginx/taobao-admin-access.log;
    error_log /var/log/nginx/taobao-admin-error.log;

    # Максимальный размер загружаемых файлов
    client_max_body_size 10M;

    # Проксирование на админ-панель
    location / {
        proxy_pass http://127.0.0.1:8004;
        proxy_http_version 1.1;
        
        # Заголовки
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Статические файлы
    location /static/ {
        proxy_pass http://127.0.0.1:8004/static/;
        proxy_cache_valid 200 1h;
        add_header Cache-Control "public, immutable";
    }

    # API endpoints
    location /api/ {
        proxy_pass http://127.0.0.1:8004/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 4. Активируем конфигурацию

```bash
# Создаем символическую ссылку
sudo ln -s /etc/nginx/sites-available/taobao-admin /etc/nginx/sites-enabled/

# Проверяем конфигурацию
sudo nginx -t

# Если все OK, перезагружаем Nginx
sudo systemctl reload nginx
```

---

## SSL сертификат (Let's Encrypt)

### 1. Установка Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 2. Получение сертификата

```bash
# Замените your-domain.com на ваш домен
sudo certbot --nginx -d your-domain.com

# Следуйте инструкциям:
# - Введите email для уведомлений
# - Согласитесь с условиями
# - Выберите редирект на HTTPS (рекомендуется)
```

### 3. Автоматическое обновление

Certbot автоматически настроит cron для обновления сертификатов. Проверить можно:

```bash
sudo certbot renew --dry-run
```

---

## Запуск приложения

### Вариант 1: Через systemd (рекомендуется)

#### 1. Создаем service файл

```bash
sudo nano /etc/systemd/system/taobao-scraper.service
```

#### 2. Содержимое service файла

```ini
[Unit]
Description=Taobao Scraper Bot + Admin Panel
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=youruser  # Замените на вашего пользователя
Group=youruser
WorkingDirectory=/path/to/TaoBao_Scraper_2
Environment="PATH=/path/to/TaoBao_Scraper_2/.venv/bin"
ExecStart=/path/to/TaoBao_Scraper_2/.venv/bin/python /path/to/TaoBao_Scraper_2/run_all.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Ограничения ресурсов (опционально)
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

#### 3. Активируем и запускаем

```bash
# Перезагружаем systemd
sudo systemctl daemon-reload

# Включаем автозапуск
sudo systemctl enable taobao-scraper

# Запускаем
sudo systemctl start taobao-scraper

# Проверяем статус
sudo systemctl status taobao-scraper
```

### Вариант 2: Через screen/tmux (для тестирования)

```bash
# Установка screen (если нет)
sudo apt install -y screen

# Создаем сессию
screen -S taobao-scraper

# Активируем виртуальное окружение
cd /path/to/TaoBao_Scraper_2
source .venv/bin/activate

# Запускаем
python run_all.py

# Отключаемся: Ctrl+A, затем D
# Подключаемся обратно: screen -r taobao-scraper
```

### Вариант 3: Через Docker Compose

Если используете Docker, добавьте в `docker-compose.yml`:

```yaml
services:
  bot:
    # ... существующая конфигурация бота ...
  
  admin:
    build: .
    command: python run_admin.py
    ports:
      - "8004:8004"
    environment:
      - ADMIN_PANEL_PORT=8004
    depends_on:
      - db
    # ... остальные настройки ...
```

---

## Проверка работы

### 1. Проверка портов

```bash
# Проверяем, что админ-панель слушает на порту 8004
sudo netstat -tlnp | grep 8004
# или
sudo ss -tlnp | grep 8004
```

### 2. Проверка Nginx

```bash
# Статус
sudo systemctl status nginx

# Логи
sudo tail -f /var/log/nginx/taobao-admin-access.log
sudo tail -f /var/log/nginx/taobao-admin-error.log
```

### 3. Проверка приложения

```bash
# Логи systemd
sudo journalctl -u taobao-scraper -f

# Или если через screen
screen -r taobao-scraper
```

### 4. Тестирование в браузере

- **HTTP:** http://your-domain.com или http://your-ip
- **HTTPS:** https://your-domain.com
- **API документация:** https://your-domain.com/docs
- **ReDoc:** https://your-domain.com/redoc

---

## Troubleshooting

### Проблема: 502 Bad Gateway

**Причина:** Админ-панель не запущена или недоступна на порту 8004.

**Решение:**
```bash
# Проверяем статус
sudo systemctl status taobao-scraper

# Проверяем порт
sudo netstat -tlnp | grep 8004

# Перезапускаем
sudo systemctl restart taobao-scraper
```

### Проблема: 404 Not Found

**Причина:** Неправильный путь в Nginx конфигурации.

**Решение:**
```bash
# Проверяем конфигурацию
sudo nginx -t

# Проверяем, что файл активирован
ls -la /etc/nginx/sites-enabled/taobao-admin

# Перезагружаем Nginx
sudo systemctl reload nginx
```

### Проблема: SSL сертификат не работает

**Причина:** Домен не указывает на сервер или firewall блокирует порт 443.

**Решение:**
```bash
# Проверяем DNS
nslookup your-domain.com

# Проверяем firewall
sudo ufw status
sudo ufw allow 443/tcp

# Проверяем сертификат
sudo certbot certificates
```

### Проблема: CORS ошибки

**Причина:** Nginx не передает правильные заголовки.

**Решение:** Убедитесь, что в конфигурации Nginx есть все необходимые `proxy_set_header` директивы (см. конфигурацию выше).

### Проблема: WebSocket не работает

**Причина:** Nginx не настроен для WebSocket.

**Решение:** Убедитесь, что в конфигурации есть:
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

---

## Безопасность

### 1. Firewall

```bash
# Разрешаем только необходимые порты
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 2. Ограничение доступа по IP (опционально)

Если нужно ограничить доступ к админ-панели только с определенных IP:

```nginx
location / {
    allow 192.168.1.0/24;  # Ваша локальная сеть
    allow 1.2.3.4;          # Ваш IP
    deny all;
    
    proxy_pass http://127.0.0.1:8004;
    # ... остальные настройки ...
}
```

### 3. Базовая аутентификация (опционально)

```bash
# Устанавливаем утилиту
sudo apt install -y apache2-utils

# Создаем файл с паролями
sudo htpasswd -c /etc/nginx/.htpasswd admin

# Добавляем в конфигурацию Nginx
location / {
    auth_basic "Admin Panel";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    proxy_pass http://127.0.0.1:8004;
    # ... остальные настройки ...
}
```

---

## Мониторинг

### Логи Nginx

```bash
# Доступы
sudo tail -f /var/log/nginx/taobao-admin-access.log

# Ошибки
sudo tail -f /var/log/nginx/taobao-admin-error.log
```

### Логи приложения

```bash
# Systemd
sudo journalctl -u taobao-scraper -f

# Или через screen
screen -r taobao-scraper
```

---

## Обновление

```bash
# Останавливаем
sudo systemctl stop taobao-scraper

# Обновляем код
cd /path/to/TaoBao_Scraper_2
git pull
source .venv/bin/activate
pip install -r requirements.txt

# Запускаем
sudo systemctl start taobao-scraper
```

---

## Полезные команды

```bash
# Перезапуск Nginx
sudo systemctl restart nginx

# Перезапуск приложения
sudo systemctl restart taobao-scraper

# Проверка конфигурации Nginx
sudo nginx -t

# Обновление SSL сертификата
sudo certbot renew

# Просмотр логов
sudo journalctl -u taobao-scraper -n 100
```

---

**Последнее обновление:** 2025-11-12


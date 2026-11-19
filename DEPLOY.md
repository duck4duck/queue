# 🚀 Инструкция по деплою проекта Queue Management API

Данное руководство описывает шаги по развертыванию сервиса на сервере (VPS/VDS на базе Ubuntu/Debian).

---

## 🛠 Стек технологий

- **Backend**: Python 3.12, FastAPI, Uvicorn, SQLAlchemy (asyncpg), Pydantic v2
- **База данных**: PostgreSQL 15 Alpine
- **Кэш / Очереди / Сессии**: Redis 7 Alpine
- **Миграции БД**: Alembic
- **Контейнеризация**: Docker, Docker Compose
- **Reverse Proxy**: Nginx (поддержка REST API, статики и WebSockets)

---

## 📋 1. Подготовка сервера

### Обновление пакетов и установка Docker
Подключитесь к вашему серверу по SSH и выполните:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw

# Установка Docker и Docker Compose plugin
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```
*(После добавления пользователя в группу `docker` переподключитесь по SSH).*

### Настройка файрвола (UFW)
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```
*(Порты PostgreSQL `5432` и Redis `6379` наружу открывать не требуется — они доступны только на localhost / во внутренней сети Docker).*

---

## 📦 2. Установка и запуск проекта

### Шаг 1. Клонирование репозитория
```bash
git clone https://github.com/duck4duck/queue.git /opt/queue
cd /opt/queue
```

### Шаг 2. Настройка переменных окружения
Создайте боевой файл `.env` на основе примера:
```bash
cp .env.example .env
nano .env
```

Обязательно замените:
- `DB_PASSWORD` — надежный пароль к PostgreSQL
- `REDIS_PASSWORD` — надежный пароль к Redis
- `CORS_ORIGINS` — домены вашего фронтенда (например, `https://queue.example.com,https://web.telegram.org`)
- `DEBUG=false` — отключить режим отладки в production

### Шаг 3. Запуск сервисов

#### Вариант A. Стандартный запуск (если порт 8000 проксируется внешним Nginx или Cloudflare):
```bash
docker compose up -d --build
```

#### Вариант B. Полный production-стек (включая контейнер Nginx на портах 80/443):
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Шаг 4. Применение миграций базы данных
После запуска контейнеров примените миграции Alembic:
```bash
docker compose exec app alembic upgrade head
```

---

## 🔒 3. Настройка SSL / HTTPS (Let's Encrypt)

Если вы используете Nginx на хост-системе:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Если вы используете Nginx из `docker-compose.prod.yml`:
1. Убедитесь, что DNS-запись домена указывает на IP вашего сервера.
2. Запустите получение сертификата через certbot:
```bash
docker compose -f docker-compose.prod.yml run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
  -d your-domain.com --email admin@your-domain.com --agree-tos --no-eff-email" nginx
```

---

## 🔍 4. Полезные команды сопровождения

### Просмотр логов
```bash
# Логи приложения в реальном времени
docker compose logs -f app

# Логи базы данных
docker compose logs -f db

# Логи Redis
docker compose logs -f redis
```

### Проверка статуса контейнеров и Health Check
```bash
docker compose ps
curl http://localhost:8000/health
```

### Резервное копирование базы данных PostgreSQL
```bash
# Создание бэкапа
docker compose exec -T db pg_dump -U myapp_user myapp_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановление из бэкапа
docker compose exec -T db psql -U myapp_user myapp_db < backup_filename.sql
```

### Обновление проекта до последней версии
```bash
git pull origin master
docker compose up -d --build
docker compose exec app alembic upgrade head
```

### Запуск инструментов разработки (pgAdmin / Redis Insight)
Если вам временно понадобился доступ к веб-панелям:
```bash
docker compose --profile dev up -d
```
После завершения диагностики выключите их:
```bash
docker compose --profile dev down
```

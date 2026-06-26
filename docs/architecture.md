# Блок 5 — Техническая архитектура

> Версия 2.0 — 26.06.2026  
> Стек выровнен по Nura: всё пишется в коде, никаких внешних платных сервисов.

---

## Структура репозитория

```
dreif/
├── audium_app/
│   ├── api/
│   │   ├── main.py           # FastAPI app, CORS, Sentry, startup
│   │   ├── routes/
│   │   │   ├── web.py        # авторизация, профиль, протокол
│   │   │   ├── audio.py      # GET /audio/{track_id} с проверкой подписки
│   │   │   └── payment.py    # ЮKassa создание платежа + webhook
│   │   └── deps.py           # get_current_user, rate limiter
│   ├── bot/
│   │   ├── main.py           # aiogram Dispatcher + RedisStorage
│   │   ├── handlers/         # start, auth_link, reminders, payment
│   │   └── middlewares/      # ThrottlingMiddleware
│   ├── core/
│   │   ├── config.py         # pydantic-settings → .env
│   │   ├── models.py         # SQLAlchemy 2.0 DeclarativeBase
│   │   ├── schemas/          # Pydantic схемы на каждой границе
│   │   ├── repositories/     # user.py, payment.py, session_log.py
│   │   └── services/         # subscription.py, audio.py
│   └── docker-compose.yml
├── frontend/
│   ├── index.html            # лендинг — vanilla HTML/CSS/JS
│   ├── app/
│   │   ├── index.html        # приложение (плеер, протокол, история)
│   │   ├── app.js
│   │   └── app.css
│   ├── manifest.json
│   ├── service-worker.js
│   └── theme.css             # CSS переменные (цвета бренда)
├── audio/                    # треки .mp3 — не публичная директория
│   ├── sleep_01.mp3
│   └── ...
└── nginx/
    └── audium.conf
```

**Принцип:** фронтенд — статика, раздаётся Nginx напрямую. API проксируется. Один `docker compose up` — всё работает.

---

## Общая схема

```
Браузер пользователя
    │
    ├─► Nginx ──► /           → frontend/index.html (лендинг)
    │            /app/        → frontend/app/ (PWA приложение)
    │            /api/        → FastAPI :8000
    │            /audio/      → FastAPI :8000 (с проверкой подписки)
    │
    └─► Telegram Login Widget ──► POST /api/auth/telegram
                                        │
                              httpOnly cookie (session_id)
                                        │
                              ┌─────────┼──────────┐
                         [PostgreSQL] [Redis]  [ЮKassa webhook]
```

---

## Стек — полностью из кода, без внешних сервисов

| Слой | Технология | Откуда берём |
|------|-----------|-------------|
| Фронтенд | Vanilla HTML/CSS/JS | Как в Nura — без фреймворков, без бандлера |
| PWA | manifest.json + service worker | Паттерн из Nura |
| Backend | FastAPI 0.115 + Python 3.11 | Как в Nura |
| ORM | SQLAlchemy 2.0 async + asyncpg | Как в Nura |
| Миграции | Alembic | Как в Nura |
| Валидация | Pydantic 2 + pydantic-settings | Как в Nura |
| Telegram bot | aiogram 3.13 | Как в Nura |
| Bot FSM | Redis 7 (RedisStorage) | Как в Nura |
| Rate limiting | slowapi | Как в Nura |
| Auth | Telegram Login Widget → httpOnly cookie | Безопаснее чем в Nura |
| Платежи | yookassa 3.1 + HMAC webhook | Как в Nura (уже отлажено) |
| База данных | PostgreSQL 16 | Как в Nura |
| Деплой | Docker Compose + Nginx | Как в Nura |
| VPS | Российский хостинг (Selectel / Timeweb) | 152-ФЗ |
| Аудио | /audio/ директория на VPS | FileResponse, не CDN |
| Мониторинг | Sentry SDK | Как в Nura |

**Не берём из Nura:** AI-слой, WeasyPrint, Celery, faster-whisper, видео-ассемблер, sqladmin (на старте не нужно).

---

## Docker Compose (4 контейнера вместо 6 у Nura)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck: pg_isready

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes: [redis_data:/data]

  api:
    build: .
    command: uvicorn audium_app.api.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ports: ["127.0.0.1:8000:8000"]   # наружу только через Nginx
    volumes:
      - ./audio:/app/audio:ro        # аудиофайлы (read-only)
    depends_on: [postgres, redis]

  bot:
    build: .
    command: python -m audium_app.bot.main
    depends_on: [postgres, redis]
```

Celery добавляется в V2 если понадобятся scheduled-рассылки.

---

## Nginx конфиг

```nginx
server {
    listen 443 ssl;
    server_name audium.ru;

    # Лендинг и статика
    root /var/www/audium;
    index index.html;

    # PWA — SPA fallback
    location /app/ {
        try_files $uri $uri/ /app/index.html;
        add_header Cache-Control "no-cache";
    }

    # manifest и service worker — без кэша
    location ~* (manifest\.json|service-worker\.js)$ {
        add_header Cache-Control "no-cache";
    }

    # API и аудио — в FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /audio/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        # Range requests для перемотки аудио
        proxy_set_header Range $http_range;
    }

    # Let's Encrypt
    ssl_certificate /etc/letsencrypt/live/audium.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/audium.ru/privkey.pem;
}

server {
    listen 80;
    server_name audium.ru;
    return 301 https://$host$request_uri;
}
```

---

## Схема базы данных

```sql
users
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  telegram_id           BIGINT UNIQUE NOT NULL
  subscription_status   VARCHAR DEFAULT 'trial'   -- trial / active / expired
  trial_started_at      TIMESTAMP DEFAULT now()
  subscription_until    TIMESTAMP
  web_session_id        UUID
  web_session_expires   TIMESTAMP
  pd_consent_at         TIMESTAMP NOT NULL         -- согласие обязательно
  created_at            TIMESTAMP DEFAULT now()

sessions_log
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID REFERENCES users(id) ON DELETE CASCADE
  track_id              VARCHAR NOT NULL
  category              VARCHAR NOT NULL           -- sleep/focus/stress/recovery
  state_before          JSONB                      -- анкета до
  state_after           JSONB                      -- оценка после
  duration_sec          INTEGER
  played_at             TIMESTAMP DEFAULT now()

payments
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID REFERENCES users(id) ON DELETE CASCADE
  yukassa_payment_id    VARCHAR UNIQUE NOT NULL
  amount_kopecks        INTEGER NOT NULL
  period                VARCHAR NOT NULL           -- month / year
  status                VARCHAR DEFAULT 'pending'  -- pending/succeeded/cancelled
  created_at            TIMESTAMP DEFAULT now()
```

---

## Авторизация — Telegram Login Widget

```
1. Пользователь на лендинге нажимает «Начать»
2. Telegram Login Widget открывает окно авторизации
3. После подтверждения Telegram отправляет данные на:
   POST /api/auth/telegram
   { id, first_name, username, hash, auth_date }
4. Backend верифицирует hash (HMAC-SHA256 с bot token)
5. Создаёт или находит User по telegram_id
6. Генерирует session_id (UUID), сохраняет в users
7. Устанавливает httpOnly cookie: session_id, Max-Age=7776000 (90 дней)
8. Редирект в /app/
```

```python
import hmac, hashlib

def verify_telegram_auth(data: dict, bot_token: str) -> bool:
    check_hash = data.pop('hash')
    data_string = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()))
    secret = hashlib.sha256(bot_token.encode()).digest()
    calculated = hmac.new(secret, data_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, check_hash)
```

---

## Защита аудио

```python
@router.get("/audio/{track_id}")
async def stream_audio(track_id: str, user: User = Depends(get_current_user)):
    if not has_access(user):
        raise HTTPException(403)
    file_path = f"/app/audio/{track_id}.mp3"
    if not os.path.exists(file_path):
        raise HTTPException(404)
    return FileResponse(file_path, media_type="audio/mpeg")
    # FileResponse поддерживает Range requests → перемотка работает
```

---

## ЮKassa вебхук

```python
@router.post("/webhook/yukassa")
async def yukassa_webhook(request: Request):
    body = await request.body()
    # Верификация подписи — обязательно
    signature = request.headers.get("X-YooMoney-Signature")
    if not verify_yukassa_signature(body, signature, settings.yukassa_secret):
        raise HTTPException(400)

    event = await request.json()
    if event["event"] == "payment.succeeded":
        payment_id = event["object"]["id"]
        await payment_service.activate_subscription(payment_id)
```

---

## Триал-логика

```python
from datetime import datetime, timedelta, timezone

def has_access(user: User) -> bool:
    now = datetime.now(timezone.utc)
    if user.subscription_status == 'active' and user.subscription_until:
        return user.subscription_until > now
    if user.subscription_status == 'trial' and user.trial_started_at:
        return user.trial_started_at + timedelta(days=3) > now
    return False
```

---

## PWA

```json
// manifest.json
{
  "name": "Audium",
  "short_name": "Audium",
  "start_url": "/app/",
  "display": "standalone",
  "background_color": "#0B1623",
  "theme_color": "#0B1623",
  "icons": [
    {"src": "/icons/192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

```javascript
// service-worker.js — минимальный
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
```

---

## Порядок разработки

| # | Что | Результат |
|---|-----|----------|
| 1 | Структура проекта, Docker Compose, Alembic, модели | Проект запускается локально |
| 2 | Telegram Login Widget + httpOnly cookie | Можно войти |
| 3 | Триал-логика + middleware проверки доступа | Закрытый контент |
| 4 | Лендинг (frontend/index.html) | Есть куда вести трафик |
| 5 | Аудиоплеер + протокол (анкета → трек → оценка) | Продукт работает |
| 6 | ЮKassa + webhook | Можно платить |
| 7 | Telegram-бот (напоминания, конверсия на день 3) | Удержание |
| 8 | PWA manifest + service worker | Установка на экран |
| 9 | Nginx + деплой на VPS | Продакшн |

---

## Что НЕ строить на MVP

- Celery / Beat — напоминания через aiogram scheduler или простой cron
- Административная панель — прямые SQL-запросы на старте
- Биометрическая интеграция (Oura/AW)
- Микросервисы
- CDN / Object Storage (добавить когда нагрузка превысит VPS)

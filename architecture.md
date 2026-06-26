# Блок 5 — Техническая архитектура пейвола

> Версия 1.0 — 26.06.2026

---

## Общая схема

```
[Лендинг] → [Telegram Login Widget] → [FastAPI Backend]
                                              │
                          ┌───────────────────┼───────────────────┐
                          │                   │                   │
                   [PostgreSQL]        [Yandex Cloud        [ЮKassa
                   users + subs        Object Storage]      Webhooks]
                                       аудио + CDN
                                              │
                                    [Audio Player]
                                    защищённые URL
```

---

## No-code vs кастомная разработка

**No-code (Tilda + Memberspace и пр.) — не подходит.** Причины:
- Западные membership-инструменты не интегрируются с ЮKassa
- Telegram Login Widget в no-code конструктор встроить нельзя нормально
- Защита аудио через подписанные CDN-URL требует серверной логики

**Решение: полупользовательская разработка.**
- Лендинг: статичный HTML/CSS или Tilda **только для маркетинговой части** (до кнопки «Начать»)
- Всё после авторизации — кастомный FastAPI backend
- Один монолитный сервис на MVP, не микросервисы

---

## Стек технологий

| Слой | Технология | Обоснование |
|------|-----------|-------------|
| Backend | FastAPI (Python) | Быстро, async, уже знакомо по Nura |
| База данных | PostgreSQL | Надёжно, транзакции, уже в Nura |
| Хостинг данных | Yandex Cloud / VK Cloud / Selectel | Серверы в РФ — требование 152-ФЗ |
| Аудио-хранилище | Yandex Cloud Object Storage | S3-совместимый, CDN поверх, в РФ |
| CDN | Yandex Cloud CDN или Selectel CDN | Российские PoP-точки, быстро для РФ |
| Платежи | ЮKassa | СБП + карты Мир, вебхуки |
| Auth | Telegram Login Widget | Решено в блоке 4 |
| Сессия | httpOnly cookie, 90 дней | Не localStorage |
| Деплой | Docker + VPS или Yandex Cloud serverless | На старте — VPS |

---

## Схема базы данных (минимальная)

```sql
users
  id                    UUID PRIMARY KEY
  telegram_id           BIGINT UNIQUE NOT NULL
  subscription_status   ENUM('trial', 'active', 'expired', 'cancelled')
  trial_started_at      TIMESTAMP
  subscription_until    TIMESTAMP
  web_session_id        UUID
  web_session_expires   TIMESTAMP
  pd_consent_at         TIMESTAMP    -- согласие на обработку ПД
  created_at            TIMESTAMP DEFAULT now()

sessions_log           -- история прослушиваний для протокола
  id                   UUID PRIMARY KEY
  user_id              UUID REFERENCES users(id)
  track_id             VARCHAR
  category             ENUM('sleep', 'focus', 'stress', 'recovery')
  state_before         JSONB        -- анкета до сессии (1-3 вопроса)
  state_after          JSONB        -- оценка после
  duration_sec         INTEGER
  played_at            TIMESTAMP

payments
  id                   UUID PRIMARY KEY
  user_id              UUID REFERENCES users(id)
  yukassa_payment_id   VARCHAR UNIQUE
  amount               INTEGER      -- в копейках
  period               ENUM('month', 'year')
  status               ENUM('pending', 'succeeded', 'cancelled')
  created_at           TIMESTAMP
```

---

## Защита аудио — подписанные URL

Аудиофайлы **не должны быть публичными**. Схема доступа:

```
Пользователь открывает плеер
    ↓
Frontend запрашивает: GET /api/audio/url?track_id=sleep_01
    ↓
Backend проверяет: subscription_status == 'active' или в триале?
    ↓
Да → генерирует подписанный URL с TTL 1 час
    → возвращает URL
    ↓
Frontend воспроизводит напрямую с CDN (не через бэкенд)
```

**Подписанный URL (Yandex Cloud Object Storage):**
```python
import boto3
from datetime import datetime, timedelta

s3 = boto3.client('s3', endpoint_url='https://storage.yandexcloud.net', ...)

def get_signed_audio_url(track_key: str) -> str:
    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': 'dreif-audio', 'Key': track_key},
        ExpiresIn=3600  # 1 час
    )
```

Аудио грузится напрямую с CDN — бэкенд не является посредником в стриминге. Масштабируется бесплатно.

---

## Логика ЮKassa — вебхук

```
Пользователь нажал «Начать подписку»
    ↓
Backend создаёт payment в ЮKassa API
    → возвращает payment_url (страница оплаты ЮKassa)
    ↓
Пользователь оплачивает через СБП или карту Мир
    ↓
ЮKassa отправляет POST на: /api/webhook/yukassa
    ↓
Backend проверяет подпись вебхука (HMAC)
    ↓
Если payment.status == 'succeeded':
    → обновляет users SET subscription_status='active',
      subscription_until = now() + 30 days (или 365)
    → Telegram-бот отправляет сообщение: «Подписка активирована»
```

**Важно:** всегда верифицировать подпись вебхука от ЮKassa — иначе кто угодно может послать фейковый «оплачено».

---

## Triал-логика

```python
# При регистрации через Telegram
user.subscription_status = 'trial'
user.trial_started_at = now()

# Проверка доступа
def has_access(user: User) -> bool:
    if user.subscription_status == 'active':
        return user.subscription_until > now()
    if user.subscription_status == 'trial':
        return user.trial_started_at + timedelta(days=3) > now()
    return False
```

---

## PWA (Progressive Web App)

Минимальная реализация — 1 день работы поверх готового сайта.

**manifest.json:**
```json
{
  "name": "Дрейф",
  "short_name": "Дрейф",
  "start_url": "/app",
  "display": "standalone",
  "background_color": "#0B1623",
  "theme_color": "#0B1623",
  "icons": [
    {"src": "/icons/192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

**Service Worker — только для установки (не для кэша аудио):**
```javascript
// sw.js — минимальный, только регистрация
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
```

**Web Push (опционально на старте):**
- Android: работает без установки на главный экран
- iOS: только после «Добавить на главный экран» (с iOS 16.4)
- На MVP можно пропустить — Telegram-бот закрывает эту задачу надёжнее

---

## Порядок разработки

| # | Что | Зачем сначала |
|---|-----|--------------|
| 1 | FastAPI проект, БД, модели | Основа всего |
| 2 | Telegram Login Widget + сессия в cookie | Без auth нет продукта |
| 3 | Триал-логика + проверка доступа | Нужна до аудио |
| 4 | Yandex Cloud Object Storage + подписанные URL | Защита аудио |
| 5 | Аудио-плеер с протоколом (анкета → трек → оценка) | Сам продукт |
| 6 | ЮKassa интеграция + вебхук | Монетизация |
| 7 | Telegram-бот (напоминания, конверсия) | Удержание |
| 8 | PWA manifest | Добавить на главный экран |

---

## Что НЕ строить на MVP

- Собственный стриминг-сервер (CDN справится)
- Мобильное приложение (PWA достаточно)
- Биометрическая интеграция (Oura/AW) — отложено
- Административная панель — на старте хватит прямых SQL-запросов
- Микросервисы — один монолит, деплоить проще

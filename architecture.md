# Блок 5 — Техническая архитектура пейвола

> Версия 1.0 — 26.06.2026

---

## Общая схема

```
[Лендинг Tilda] → [Telegram Login Widget] → [FastAPI Backend на VPS]
                                                      │
                                       ┌──────────────┼──────────────┐
                                       │              │              │
                                [PostgreSQL]    [/app/audio/]   [ЮKassa
                                users/subs/     треки лежат     Webhooks]
                                payments        здесь же
                                       │
                               [Audio endpoint]
                               GET /audio/{id}
                               проверка подписки → FileResponse
```

**Аудио на том же VPS** — 15–20 треков = 1–2 ГБ, VPS справляется.
Переезд на Object Storage + CDN делается за один день когда придёт реальная нагрузка.

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
| Лендинг | Tilda | Быстро, не нужен разработчик, Telegram-кнопка вставляется как HTML-блок |
| Приложение (фронт) | Jinja2 + HTMX | FastAPI сам отдаёт HTML, минимум JS, один сервис |
| Backend | FastAPI (Python) | Async, знакомо по Nura, автодокументация |
| База данных | PostgreSQL | Надёжно, транзакции, уже в Nura |
| Аудио-хранилище | VPS (тот же сервер) | 15–20 треков = 1–2 ГБ, лишний сервис не нужен |
| Аудио-раздача | FastAPI FileResponse | Проверка подписки перед отдачей файла |
| Платежи | ЮKassa | СБП + карты Мир, вебхуки |
| Auth | Telegram Login Widget | Решено в блоке 4 |
| Сессия | httpOnly cookie, 90 дней | Не localStorage |
| Деплой | Docker + VPS в РФ | Selectel / Timeweb / Reg.ru — 152-ФЗ |
| V2: аудио при росте | Yandex Cloud Object Storage + CDN | Переезд за 1 день когда придёт нагрузка |

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

## Защита аудио — раздача через FastAPI

Аудиофайлы лежат в `/app/audio/` — вне публичной директории. Доступ только через endpoint с проверкой подписки:

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
import os

router = APIRouter()

@router.get("/audio/{track_id}")
async def stream_audio(
    track_id: str,
    user: User = Depends(get_current_user)
):
    if not has_access(user):
        raise HTTPException(status_code=403, detail="Subscription required")

    file_path = f"/app/audio/{track_id}.mp3"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404)

    # FileResponse поддерживает HTTP Range requests — перемотка работает
    return FileResponse(file_path, media_type="audio/mpeg")
```

**HTTP Range requests** (нужны для перемотки в аудиоплеере) FastAPI поддерживает через `FileResponse` из коробки.

**V2 при росте нагрузки:** файлы переезжают в Yandex Cloud Object Storage, endpoint генерирует подписанный URL вместо FileResponse. Изменение в одном месте, один день работы.

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

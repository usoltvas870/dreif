# Блок 6 — Биллинг и подписочная логика

> Версия 1.0 — 26.06.2026

---

## Подход к recurring на MVP — без автосписания

Настоящий автоплатёж (сохранённая карта → автосписание) сложнее в разработке и требует дополнительного соглашения с ЮKassa. Для MVP используем **ручное продление с проактивными напоминаниями через бота**.

Пользователь платит один раз → получает 30 или 365 дней → бот напоминает заранее → пользователь платит снова.

Это работает: большинство российских небольших подписочных сервисов живут именно так на старте. Теряем ~10–15% тех кто не заметил уведомление, но избегаем сложности на MVP.

**V2:** реализуем автоплатёж через `payment_method_id` (ЮKassa поддерживает сохранение карты).

---

## Жизненный цикл подписки

```
Регистрация
    ↓
trial (3 дня, полный доступ)
    ↓ истёк без оплаты         ↓ оплатил
expired (нет доступа)        active
                                ↓
                        день 27 (месяц) или день 355 (год)
                                ↓
                        expiring — бот отправляет напоминание
                                ↓ оплатил             ↓ не оплатил
                              active               expired
```

**Статусы в БД:** `trial` → `active` → `expiring` → `expired`

---

## Настройка ЮKassa

### Что нужно сделать один раз

1. Зарегистрировать магазин на yookassa.ru
2. Подключить способы оплаты: банковская карта, СБП, Mir Pay
3. Получить `shop_id` и `secret_key` → в `.env`
4. Настроить webhook URL в личном кабинете ЮKassa:
   `https://audium.ru/webhook/yukassa`
5. Включить уведомления о событиях: `payment.succeeded`, `payment.canceled`

```env
YUKASSA_SHOP_ID=123456
YUKASSA_SECRET_KEY=live_xxxxxxxxxxxx
YUKASSA_WEBHOOK_SECRET=xxxxxxxxxxxx
```

---

## Создание платежа

```python
from yookassa import Configuration, Payment
import uuid

Configuration.account_id = settings.yukassa_shop_id
Configuration.secret_key = settings.yukassa_secret_key

def create_payment(user_id: str, period: str) -> dict:
    amount = 49000 if period == 'month' else 349000  # копейки

    payment = Payment.create({
        "amount": {
            "value": str(amount / 100),  # ЮKassa принимает рубли с копейками
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://audium.ru/app/?payment=success"
        },
        "capture": True,
        "description": f"Audium — {'месяц' if period == 'month' else 'год'}",
        "metadata": {
            "user_id": user_id,
            "period": period
        }
    }, uuid.uuid4())  # idempotency_key

    return {
        "payment_id": payment.id,
        "payment_url": payment.confirmation.confirmation_url
    }
```

---

## Обработка вебхука

```python
import hmac, hashlib, json

@router.post("/webhook/yukassa")
async def yukassa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()

    # Верификация подписи (обязательно — иначе фейковые «оплаты» возможны)
    signature = request.headers.get("X-YooMoney-Signature", "")
    expected = hmac.new(
        settings.yukassa_webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(400, "Invalid signature")

    event = json.loads(body)

    if event["event"] == "payment.succeeded":
        payment_obj = event["object"]
        user_id = payment_obj["metadata"]["user_id"]
        period = payment_obj["metadata"]["period"]
        yukassa_id = payment_obj["id"]

        await payment_service.activate(
            db=db,
            user_id=user_id,
            yukassa_payment_id=yukassa_id,
            period=period
        )

    elif event["event"] == "payment.canceled":
        # Логируем, пользователю ничего не меняем (доступ по триалу или текущей подписке)
        pass

    return {"status": "ok"}
```

---

## Активация подписки

```python
from datetime import datetime, timedelta, timezone

async def activate(db, user_id: str, yukassa_payment_id: str, period: str):
    now = datetime.now(timezone.utc)
    days = 30 if period == 'month' else 365

    # Сохраняем платёж
    payment = Payment(
        user_id=user_id,
        yukassa_payment_id=yukassa_payment_id,
        amount_kopecks=49000 if period == 'month' else 349000,
        period=period,
        status='succeeded'
    )
    db.add(payment)

    # Обновляем пользователя
    user = await user_repo.get(db, user_id)

    # Если у пользователя есть активная подписка — продлеваем от её окончания
    if user.subscription_status == 'active' and user.subscription_until > now:
        new_until = user.subscription_until + timedelta(days=days)
    else:
        new_until = now + timedelta(days=days)

    user.subscription_status = 'active'
    user.subscription_until = new_until
    await db.commit()

    # Уведомление в Telegram
    await bot.send_message(
        user.telegram_id,
        f"✓ Подписка активирована до {new_until.strftime('%d.%m.%Y')}. "
        f"Хороших сессий."
    )
```

---

## Напоминания о продлении (Telegram-бот)

Запускаем через простой cron внутри Docker или `apscheduler` без Celery:

```python
# audium_app/core/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=10, minute=0)
async def check_expiring_subscriptions():
    """Запускается каждый день в 10:00 МСК"""
    async with get_db_session() as db:
        expiring_users = await user_repo.get_expiring_soon(db, days=3)
        for user in expiring_users:
            days_left = (user.subscription_until - datetime.now(timezone.utc)).days
            await bot.send_message(
                user.telegram_id,
                f"Подписка истекает через {days_left} дня.\n\n"
                f"Продолжить: /pay"
            )
```

```python
# В репозитории
async def get_expiring_soon(self, db, days: int):
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=days)
    return await db.execute(
        select(User).where(
            User.subscription_status == 'active',
            User.subscription_until <= deadline,
            User.subscription_until > now
        )
    )
```

---

## Конверсия из триала — день 3

Отдельная задача планировщика:

```python
@scheduler.scheduled_job('cron', hour=18, minute=0)
async def trial_conversion():
    """18:00 МСК — лучшее время для конверсионного сообщения"""
    async with get_db_session() as db:
        expiring_trials = await user_repo.get_expiring_trials(db)
        for user in expiring_trials:
            await bot.send_message(
                user.telegram_id,
                "Три ночи позади.\n\n"
                "Если почувствовал разницу — продолжи.\n"
                "Если нет — не плати. Всё честно.\n\n"
                "Месяц — 490 ₽\n"
                "Год — 3 490 ₽ (экономия 40%)\n\n"
                "Оплата через СБП:",
                reply_markup=payment_keyboard()  # инлайн-кнопки Месяц / Год
            )
```

---

## Downgrade истёкших подписок

```python
@scheduler.scheduled_job('cron', hour=2, minute=0)
async def downgrade_expired():
    """2:00 ночи — тихо переводим истёкшие подписки"""
    async with get_db_session() as db:
        await db.execute(
            update(User)
            .where(
                User.subscription_status == 'active',
                User.subscription_until < datetime.now(timezone.utc)
            )
            .values(subscription_status='expired')
        )
        await db.commit()
```

---

## Возвраты

По российскому законодательству (ЗоЗПП) цифровые услуги невозвратны если пользователь уже воспользовался сервисом. Достаточно это прописать в оферте.

Если возврат всё же нужен (goodwill) — через ЮKassa API:

```python
from yookassa import Refund

Refund.create({
    "payment_id": yukassa_payment_id,
    "amount": {
        "value": "490.00",
        "currency": "RUB"
    }
})
```

**Политика на старте:** возвраты рассматриваем вручную в первые 24 часа после оплаты, если пользователь не открывал ни одной сессии. Автоматики не нужно.

---

## Что добавить в V2

| Фича | Когда | Зачем |
|------|-------|-------|
| Автоплатёж (сохранённая карта) | После 100+ подписчиков | Снизить churn от тех кто забыл продлить |
| СБП recurring | Когда ЮKassa стабилизирует API | Альтернатива карте |
| Промокоды | После первых отзывов | Инфлюенсер-кампании |
| Реферальная программа | V2 | Органический рост |

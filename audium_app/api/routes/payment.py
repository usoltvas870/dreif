import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audium_app.core.config import settings
from audium_app.core.database import get_db
from audium_app.core.models import Payment, User
from audium_app.api.deps import get_current_user
from audium_app.core.services.subscription import activate_subscription

router = APIRouter()

PRICES = {
    "month": 49000,   # kopecks
    "year": 349000,
}


class CreatePaymentRequest(BaseModel):
    period: str  # month / year


@router.post("/payment/create")
async def create_payment(
    body: CreatePaymentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.period not in PRICES:
        raise HTTPException(status_code=400, detail="Invalid period")

    try:
        from yookassa import Configuration, Payment as YKPayment
        Configuration.account_id = settings.yukassa_shop_id
        Configuration.secret_key = settings.yukassa_secret_key

        amount_kopecks = PRICES[body.period]
        amount_rubles = f"{amount_kopecks / 100:.2f}"

        payment = YKPayment.create({
            "amount": {"value": amount_rubles, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": f"{settings.app_base_url}/app/"},
            "capture": True,
            "description": f"Audium подписка — {body.period}",
            "metadata": {"user_id": str(user.id), "period": body.period},
        })

        db_payment = Payment(
            user_id=user.id,
            yukassa_payment_id=payment.id,
            amount_kopecks=amount_kopecks,
            period=body.period,
            status="pending",
        )
        db.add(db_payment)
        await db.commit()

        return {"confirmation_url": payment.confirmation.confirmation_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def verify_yukassa_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    calculated = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, signature)


@router.post("/webhook/yukassa")
async def yukassa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-YooMoney-Signature")

    if not verify_yukassa_signature(body, signature, settings.yukassa_webhook_secret):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(body)
    if event.get("event") == "payment.succeeded":
        payment_id = event["object"]["id"]
        await activate_subscription(payment_id, db)

    return {"ok": True}

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audium_app.core.models import Payment, User


async def activate_subscription(yukassa_payment_id: str, db: AsyncSession) -> None:
    result = await db.execute(select(Payment).where(Payment.yukassa_payment_id == yukassa_payment_id))
    payment = result.scalar_one_or_none()
    if not payment or payment.status == "succeeded":
        return

    payment.status = "succeeded"

    user_result = await db.execute(select(User).where(User.id == payment.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        await db.commit()
        return

    now = datetime.now(timezone.utc)
    base = max(now, user.subscription_until or now)
    delta = timedelta(days=30) if payment.period == "month" else timedelta(days=365)

    user.subscription_status = "active"
    user.subscription_until = base + delta

    await db.commit()

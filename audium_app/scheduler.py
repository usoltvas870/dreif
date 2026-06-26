import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from audium_app.core.config import settings
from audium_app.core.database import AsyncSessionLocal
from audium_app.core.models import User

logger = logging.getLogger(__name__)


async def downgrade_expired_subscriptions() -> None:
    """Mark expired active subscriptions as expired."""
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(User).where(
                User.subscription_status == "active",
                User.subscription_until < now,
            )
        )
        users = result.scalars().all()
        for user in users:
            user.subscription_status = "expired"
            logger.info(f"Expired subscription for user {user.telegram_id}")
        await db.commit()


async def downgrade_expired_trials() -> None:
    """Mark expired trials as expired."""
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=3)
        result = await db.execute(
            select(User).where(
                User.subscription_status == "trial",
                User.trial_started_at < cutoff,
            )
        )
        users = result.scalars().all()
        for user in users:
            user.subscription_status = "expired"
            logger.info(f"Expired trial for user {user.telegram_id}")
        await db.commit()


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(downgrade_expired_subscriptions, "cron", hour=2, minute=0)
    scheduler.add_job(downgrade_expired_trials, "cron", hour=2, minute=5)
    scheduler.start()
    return scheduler

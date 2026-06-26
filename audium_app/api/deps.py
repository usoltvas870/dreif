import uuid
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audium_app.core.database import get_db
from audium_app.core.models import User


async def get_current_user(
    session_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid session")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User).where(
            User.web_session_id == sid,
            User.web_session_expires > now,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Session expired")
    return user


def has_access(user: User) -> bool:
    now = datetime.now(timezone.utc)
    if user.subscription_status == "active" and user.subscription_until:
        return user.subscription_until > now
    if user.subscription_status == "trial" and user.trial_started_at:
        from datetime import timedelta
        return user.trial_started_at + timedelta(days=3) > now
    return False

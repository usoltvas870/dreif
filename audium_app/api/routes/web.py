import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audium_app.core.config import settings
from audium_app.core.database import get_db
from audium_app.core.models import User
from audium_app.api.deps import get_current_user

router = APIRouter()

SESSION_TTL_DAYS = 90


class TelegramAuthData(BaseModel):
    id: int
    first_name: str | None = None
    username: str | None = None
    auth_date: int
    hash: str
    source: str | None = None


def verify_telegram_auth(data: dict, bot_token: str) -> bool:
    check_hash = data.pop("hash", "")
    data_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hashlib.sha256(bot_token.encode()).digest()
    calculated = hmac.new(secret, data_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, check_hash)


@router.post("/auth/telegram")
async def auth_telegram(
    payload: TelegramAuthData,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    auth_data = payload.model_dump(exclude_none=False)
    source = auth_data.pop("source", None)

    if not verify_telegram_auth(auth_data, settings.telegram_bot_token):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth data")

    result = await db.execute(select(User).where(User.telegram_id == payload.id))
    user = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    session_id = uuid.uuid4()
    session_expires = now + timedelta(days=SESSION_TTL_DAYS)

    if not user:
        user = User(
            telegram_id=payload.id,
            subscription_status="trial",
            trial_started_at=now,
            pd_consent_at=now,
            web_session_id=session_id,
            web_session_expires=session_expires,
            source=source,
        )
        db.add(user)
    else:
        user.web_session_id = session_id
        user.web_session_expires = session_expires

    await db.commit()

    response.set_cookie(
        key="session_id",
        value=str(session_id),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_TTL_DAYS * 86400,
        path="/",
    )
    return {"ok": True}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("session_id")
    return {"ok": True}


@router.get("/profile")
async def profile(user: User = Depends(get_current_user)):
    return {
        "subscription_status": user.subscription_status,
        "trial_started_at": user.trial_started_at.isoformat(),
        "subscription_until": user.subscription_until.isoformat() if user.subscription_until else None,
    }

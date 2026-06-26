import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from audium_app.core.config import settings
from audium_app.api.routes import web, audio, payment

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Audium API", docs_url=None if not settings.debug else "/docs")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_base_url],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(web.router, prefix="/api")
app.include_router(audio.router, prefix="/audio")
app.include_router(payment.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}

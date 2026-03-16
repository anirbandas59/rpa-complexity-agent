"""
FastAPI application for RPA Complexity Assessment Agent.

Main entry point for the API server. Sets up routes, middleware, exception
handlers, and lifespan events.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.db.redis_store import close_store, init_store
from api.limiter import limiter
from api.middleware.auth import verify_api_key
from api.middleware.error_handler import register_exception_handlers
from api.middleware.request_id import RequestIdMiddleware
from api.routes import assessment, health
from config.logging_config import get_logger, setup_logging
from config.settings import get_settings

logger = get_logger("api.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown event handler.

    Startup:
    - Set up logging
    - Connect to Redis session store

    Shutdown:
    - Close Redis connection
    """
    setup_logging()
    logger.info("RPA Complexity Assessment Agent API starting")

    await init_store()

    yield

    await close_store()
    logger.info("API shutting down")


_settings = get_settings()
_is_production = _settings.environment == "production"
app = FastAPI(
    title="RPA Complexity Assessment Agent",
    description="AI-powered RPA process complexity assessment",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

# ── Request-ID tracing (before CORS so ID is present throughout the stack) ────
app.add_middleware(RequestIdMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ── Exception handlers ────────────────────────────────────────────────────────
register_exception_handlers(app)

# ── Routers ───────────────────────────────────────────────────────────────────
# health routes (/api/health, /api/version) are public — no auth dependency
app.include_router(health.router)
# assessment routes require a valid X-API-Key header
app.include_router(
    assessment.router,
    dependencies=[Depends(verify_api_key)],
)

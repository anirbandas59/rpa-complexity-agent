"""
FastAPI application for RPA Complexity Assessment Agent.

Main entry point for the API server. Sets up routes, middleware, exception
handlers, and lifespan events.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.limiter import limiter
from api.middleware.auth import verify_api_key
from api.middleware.error_handler import register_exception_handlers
from api.routes import assessment, health
from config.logging_config import get_logger, setup_logging
from config.settings import get_settings

logger = get_logger("api.startup")

DB_PATH = "data/sessions.db"

_TTL_INTERVAL = 30 * 60  # seconds between cleanup runs
_SESSION_TTL = 86_400  # seconds — delete sessions older than 24 hours


async def _ttl_cleanup_loop() -> None:
    """Background task: delete sessions older than SESSION_TTL every TTL_INTERVAL."""
    while True:
        await asyncio.sleep(_TTL_INTERVAL)
        cutoff = time.time() - _SESSION_TTL
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
                await db.commit()
            logger.debug("TTL cleanup: deleted sessions older than 24 h")
        except Exception as exc:
            logger.warning(f"TTL cleanup error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown event handler.

    Startup:
    - Set up logging
    - Create SQLite sessions DB and table
    - Start TTL cleanup background task

    Shutdown:
    - Cancel TTL task
    """
    # Startup
    setup_logging()
    logger.info("RPA Complexity Assessment Agent API starting")

    # Ensure data/ directory exists
    Path("data").mkdir(exist_ok=True)

    # Initialise SQLite session store
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id  TEXT PRIMARY KEY,
                status      TEXT,
                created_at  REAL,
                result_json TEXT,
                errors      TEXT,
                output_excel TEXT,
                output_pdf   TEXT
            )
            """)
        await db.commit()
    logger.info(f"Session DB initialised at {DB_PATH}")

    # Start TTL cleanup loop
    cleanup_task = asyncio.create_task(_ttl_cleanup_loop())

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("API shutting down")


app = FastAPI(
    title="RPA Complexity Assessment Agent",
    description="AI-powered RPA process complexity assessment",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
_settings = get_settings()
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

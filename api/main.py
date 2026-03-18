"""
FastAPI application for RPA Complexity Assessment Agent.

Main entry point for the API server. Sets up routes, middleware, exception
handlers, and lifespan events.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.error_handler import register_exception_handlers
from api.routes import assessment, health
from config.logging_config import get_logger, setup_logging

logger = get_logger("api.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown event handler.

    Startup:
    - Set up logging
    - Log initialization

    Shutdown:
    - Log shutdown
    """
    # Startup
    setup_logging()
    logger.info("RPA Complexity Assessment Agent API starting")
    yield
    # Shutdown
    logger.info("API shutting down")


app = FastAPI(
    title="RPA Complexity Assessment Agent",
    description="AI-powered RPA process complexity assessment",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
register_exception_handlers(app)

# Include routers
app.include_router(health.router)
app.include_router(assessment.router)

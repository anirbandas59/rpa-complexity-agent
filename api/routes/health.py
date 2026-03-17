"""
Health check endpoints for the RPA Complexity Assessment API.

Provides system health status, version information, and LLM provider details.
"""

import time
import logging
from fastapi import APIRouter
from llm.manager import LLMManager
from config.settings import get_settings

logger = logging.getLogger("rpa_agent.api.health")

router = APIRouter(prefix="/api", tags=["health"])

# Track API startup time
_start_time = time.time()


@router.get("/health")
async def health_check():
    """
    Get API and LLM health status.

    Returns:
        dict: status, version, uptime_seconds, llm_provider, llm_model, llm_healthy

    Never raises — catches all exceptions and returns status="degraded" if LLM check fails.
    """
    uptime = time.time() - _start_time
    settings = get_settings()

    try:
        manager = LLMManager.create_default()
        health = manager.health_check()
        llm_healthy = health.get("healthy", False)
        llm_provider = health.get("provider", "unknown")
        llm_model = health.get("model", "unknown")
    except Exception as e:
        logger.warning(f"LLM health check failed: {e}")
        llm_healthy = False
        llm_provider = settings.default_llm_provider
        llm_model = settings.default_llm_model

    return {
        "status": "healthy" if llm_healthy else "degraded",
        "version": "0.1.0",
        "uptime_seconds": uptime,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_healthy": llm_healthy,
    }


@router.get("/version")
async def version_info():
    """
    Get API version and agent information.

    Returns:
        dict: version, phase, agents list
    """
    return {
        "version": "0.1.0",
        "phase": "Phase 8 — API & Frontend",
        "agents": [
            "document_intelligence",
            "process_analysis",
            "complexity_assessment",
            "effort_estimation",
        ],
    }

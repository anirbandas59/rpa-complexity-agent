"""
Request-ID tracing middleware.

Reads X-Request-ID from incoming headers or generates a UUID4.
Stores the ID in request.state and echoes it back in the response header.
Also injects the ID into every log record emitted during the request via
a logging.Filter attached to the root "rpa_agent" logger.
"""

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class _RequestIdFilter(logging.Filter):
    """Inject request_id into log records from a context variable."""

    def __init__(self) -> None:
        super().__init__()
        self._current_id: str | None = None

    def set(self, request_id: str | None) -> None:
        self._current_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = self._current_id  # type: ignore[attr-defined]
        return True


# Module-level filter — shared across all requests (thread-unsafe for multi-thread,
# but Uvicorn async workers are single-threaded per worker process, so this is fine).
_filter = _RequestIdFilter()
logging.getLogger("rpa_agent").addFilter(_filter)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that assigns a request ID to every HTTP request.

    Priority: X-Request-ID header > generated UUID4 (first 8 chars).
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        _filter.set(request_id)
        try:
            response: Response = await call_next(request)  # type: ignore[operator]
        finally:
            _filter.set(None)

        response.headers["X-Request-ID"] = request_id
        return response

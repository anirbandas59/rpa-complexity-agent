"""Shared SlowAPI rate-limiter instance.

Import this module in both api/main.py (to attach to app.state and register
middleware) and in route modules (to apply the @limiter.limit decorator).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

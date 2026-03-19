# Production Readiness Assessment — `rpa-complexity-agent`

## ✅ What's Already in Good Shape

| Area | Status |
| --- | --- |
| **Docker** | Multi-service [docker-compose.yml](file:///home/anirban/workspace/projects/rpa-complexity-agent/docker-compose.yml), non-root user, health checks, layer caching |
| **API security** | `X-API-Key` auth, CORS whitelist, rate limiting via SlowAPI |
| **Error handling** | Global exception handlers with typed HTTP responses |
| **Structured logging** | Namespaced `rpa_agent.*` loggers, file + stdout output |
| **Settings validation** | Pydantic validators ensure required API keys are present at boot |
| **Test suite** | 34 unit test files + 2 integration tests, async-aware pytest config |
| **Session TTL** | Background task auto-cleans stale SQLite sessions every 30 min |

---

## 🔴 High Priority

### 1. Add a CI/CD Pipeline

There are **no GitHub Actions / GitLab CI / etc.** workflows. This is the single biggest gap.

A minimal pipeline should:

- Lint (`ruff check .`) and type-check (`mypy .`)
- Run unit tests: `uv run pytest -m "not integration"`
- Build both Docker images
- (Optionally) push images to a registry and deploy

```yaml
# .github/workflows/ci.yml  (starter example)
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run mypy .
      - run: uv run pytest -m "not integration" --tb=short
  docker:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build
```

### 2. Pin the UV Version in Dockerfiles

Both Dockerfiles copy `uv` from `ghcr.io/astral-sh/uv:latest`, meaning builds are **non-reproducible**. Pin to a specific tag:

```diff
-COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
+COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /usr/local/bin/uv
```

### 3. Enforce `API_SECRET_KEY` in Production

[api/middleware/auth.py](file:///home/anirban/workspace/projects/rpa-complexity-agent/api/middleware/auth.py) silently skips auth when `API_SECRET_KEY` is empty. In production, an empty key means **zero authentication**. Options:

- **App-level guard** – add a startup check that fails if `API_SECRET_KEY` is empty and an `ENVIRONMENT` env var is `production`.
- **Infrastructure-level** – ensure your deployment system always injects the key.

### 4. Replace SQLite with a Proper Store

`aiosqlite` and a local file ([data/sessions.db](file:///home/anirban/workspace/projects/rpa-complexity-agent/data/sessions.db)) works for single-instance dev, but **is not suitable for production** because:

- SQLite doesn't support concurrent writers well.
- The file is inside the container, so data is lost on restarts unless volume-mounted.
- Scaling to multiple API replicas is impossible.

**Options**: Redis (sessions are short-lived TTL data, perfect fit), or PostgreSQL if you need relational queries.

---

## 🟡 Medium Priority

### 5. Add JSON Structured Logging

The current formatter produces human-readable log lines. For production, **JSON logs** are far easier to ingest into log aggregation platforms (Datadog, Loki, CloudWatch):

```python
# config/logging_config.py  — swap formatter
import json, logging

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "exc": self.formatException(record.exc_info) if record.exc_info else None,
        })
```

You can toggle between human and JSON format using an env var (e.g., `LOG_FORMAT=json`).

### 6. Add Uvicorn Worker Configuration

The current `CMD` starts a **single uvicorn process**. For production, use `--workers` or run behind `gunicorn`:

```diff
-CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
+CMD ["uv", "run", "uvicorn", "api.main:app", \
+     "--host", "0.0.0.0", "--port", "8000", \
+     "--workers", "4", "--timeout-keep-alive", "120"]
```

> [!WARNING]
> If you add workers, the in-process TTL cleanup task only runs in one worker. This is another reason to move session management to Redis.

### 7. Add Request-ID Tracing

Add a middleware that generates / forwards a `X-Request-ID` header and includes it in every log line. This makes debugging production issues dramatically easier.

### 8. Tighten Dependency Version Ranges

[pyproject.toml](file:///home/anirban/workspace/projects/rpa-complexity-agent/pyproject.toml) uses very open lower-bound constraints (`>=`). In production, [uv.lock](file:///home/anirban/workspace/projects/rpa-complexity-agent/uv.lock) pins you, but adding **upper bounds** or using `~=` (compatible release) prevents surprise breaking changes:

```diff
-"fastapi>=0.104.0",
+"fastapi>=0.104.0,<1.0",
```

### 9. Add a Reverse Proxy / TLS Termination

[docker-compose.yml](file:///home/anirban/workspace/projects/rpa-complexity-agent/docker-compose.yml) exposes raw HTTP on ports `8000` and `8501`. In production you need:

- An **nginx** or **Traefik** container (or cloud load balancer) for TLS termination
- The Streamlit and API ports should **not** be directly exposed to the internet

### 10. Add a Frontend Health Check

The frontend service in [docker-compose.yml](file:///home/anirban/workspace/projects/rpa-complexity-agent/docker-compose.yml) has no `healthcheck` block (unlike the API service). Add one:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

## 🟢 Low Priority / Polish

### 11. File Upload Size Limits

Confirm that the API enforces a maximum upload size. FastAPI delegates this to the ASGI server — add `--limit-max-body-size` to uvicorn, or use a `Content-Length` check middleware.

### 12. Disable OpenAPI Docs in Production

The `/docs` and `/openapi.json` endpoints are public by default. In production:

```python
app = FastAPI(
    ...,
    docs_url=None if os.getenv("ENVIRONMENT") == "production" else "/docs",
    redoc_url=None if os.getenv("ENVIRONMENT") == "production" else "/redoc",
)
```

### 13. Add Docker Image Labels & Multi-Stage Build

Add OCI labels and consider a multi-stage build to shrink the final image:

```dockerfile
LABEL org.opencontainers.image.source="https://github.com/your-org/rpa-complexity-agent"
LABEL org.opencontainers.image.version="0.1.0"
```

### 14. Log Rotation

[logging_config.py](file:///home/anirban/workspace/projects/rpa-complexity-agent/config/logging_config.py) uses a plain `FileHandler`. Switch to `RotatingFileHandler` to prevent log files from growing unbounded:

```python
file_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=10_000_000, backupCount=5
)
```

### 15. Add `CODEOWNERS` and Branch Protection

If this is a team repo, add a `CODEOWNERS` file and enable branch protection rules (require PR reviews + passing CI before merge).

---

## Summary Checklist

| # | Item | Priority | Effort |
| -- | -- | -- | -- |
| 1 | CI/CD pipeline | 🔴 High | ~1 hour |
| 2 | Pin UV version in Dockerfiles | 🔴 High | 5 min |
| 3 | Enforce `API_SECRET_KEY` in prod | 🔴 High | 15 min |
| 4 | Replace SQLite with Redis/Postgres | 🔴 High | ~2–4 hours |
| 5 | JSON structured logging | 🟡 Medium | 30 min |
| 6 | Uvicorn workers | 🟡 Medium | 10 min |
| 7 | Request-ID tracing middleware | 🟡 Medium | 30 min |
| 8 | Tighten dependency version ranges | 🟡 Medium | 15 min |
| 9 | Reverse proxy / TLS | 🟡 Medium | ~1 hour |
| 10 | Frontend health check in Compose | 🟡 Medium | 5 min |
| 11 | File upload size limit | 🟢 Low | 10 min |
| 12 | Disable OpenAPI docs in prod | 🟢 Low | 5 min |
| 13 | Docker image labels | 🟢 Low | 5 min |
| 14 | Log rotation | 🟢 Low | 10 min |
| 15 | CODEOWNERS + branch protection | 🟢 Low | 10 min |

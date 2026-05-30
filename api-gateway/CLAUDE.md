# CLAUDE.md — api-gateway (M1)

## Role

All client requests enter through this gateway. Authenticates (JWT), authorizes (RBAC), rate-limits (Redis token bucket), audits, and reverse-proxies to backend microservices.

## Directory structure

```
api-gateway/
├── Dockerfile              # Multi-stage: builder compiles deps, runtime slim image
├── pyproject.toml
├── app/
│   ├── main.py             # FastAPI app, middleware pipeline, catch-all proxy
│   ├── config.py           # Env-based config: JWT secret, Redis URL, backend service URLs, rate limits
│   ├── middleware/
│   │   ├── auth.py         # JWT Bearer extraction, decoding, injects request.state.user
│   │   ├── rbac.py         # 4 roles × 6 operations, group-scoped enforcement
│   │   ├── rate_limit.py   # Token bucket: per-user, per-IP, per-endpoint-type
│   │   └── audit.py        # Publishes structured audit events to Redis Pub/Sub
│   ├── routing/
│   │   ├── registry.py     # Path → backend URL mapping (e.g. /api/auth/* → user-service)
│   │   └── proxy.py        # httpx async proxy with retry (exponential backoff) + streaming
│   ├── errors/handlers.py  # Unified error response format
│   └── utils/
│       ├── jwt_utils.py    # JWT decode helper
│       └── request_id.py   # X-Request-ID per-request tracing
```

## Middleware pipeline

```
Request → RequestID → CORS → RateLimit → JWT Auth → RBAC → Audit → Proxy → Backend
```

## Key dependencies

- FastAPI + Uvicorn (web)
- httpx (reverse proxy to backends)
- python-jose (JWT)
- redis (rate limit, token blacklist, audit pub/sub)
- structlog (structured logging)
- `policyai-shared` (local path `../shared`)

## Configuration

Env vars set in docker-compose or manual start. Manual start requires explicit localhost URLs (Docker container names won't resolve):

```bash
API_GATEWAY_REDIS_URL="redis://:password@localhost:6379/0"
API_GATEWAY_USER_SERVICE_URL="http://localhost:8007"
# ... one per backend
```

## Run / test

```bash
# Manual start (with all localhost endpoints):
API_GATEWAY_REDIS_URL="redis://:<pass>@localhost:6379/0" ... \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Docker build:
docker build --build-arg SERVICE_DIR=api-gateway -t policyai-api-gateway:latest -f api-gateway/Dockerfile .

# Tests
pytest --tb=short
mypy . --strict
ruff check .
```

## Integration points

- **user-service** — `/api/auth/*`, `/api/admin/*`, internal user lookup
- **document-service** — `/api/projects/*/documents/*`
- **kb-service** — `/api/projects/*/search*`
- **orchestration-service** — `/api/tasks/*`
- **citation-service** — `/api/projects/*/citations*`
- **output-service** — `/api/output/*`, `/api/preview/*`
- **Redis** — rate limit buckets, token blacklist, audit pub/sub

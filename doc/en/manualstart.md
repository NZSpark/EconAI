# EconAI Development Environment Manual Startup Guide

> Version: v1.2 | Date: 2026-05-23

---

## 1. Prerequisites

### Installed Software

| Software | Minimum Version | Purpose |
|----------|----------------|---------|
| Python | 3.12+ | Backend runtime |
| uv | 0.5+ | Python package management |
| Node.js | 18+ | Frontend runtime |
| npm | 9+ | Frontend package management |
| Docker | 24.0+ | Infrastructure containers (PostgreSQL/Redis/Milvus/MinIO) |
| Docker Compose | 2.20+ | Orchestrate infrastructure containers |

### ARM Mac (Apple Silicon) Notes

On M1/M2/M3/M4 chip Macs, the official Milvus image has known compatibility issues. This project has been verified working through the following adjustments:

- **Do not mount custom `milvus.yaml`** (let Milvus standalone use built-in default config, avoiding cluster/standalone port conflicts)
- **MinIO credentials unified as `minioadmin`** (Milvus defaults to trusting `minioadmin` username/password)
- **Milvus health check `start_period` extended to 90s** (slower initialization on ARM)

### Install Dependencies

```bash
cd /Users/onetreehill/EconAI

# Install Python dependencies for each backend service
for dir in api-gateway services/*/; do
    echo "=== Installing deps for $dir ==="
    (cd "$dir" && uv sync)
done

# Install frontend dependencies
cd frontend && npm install
```

---

## 2. Startup Order

### Dependency Review

```
Wave 1: Infrastructure (Docker)
        postgres + redis + etcd + minio + milvus

Wave 2: No business dependency services (parallel)
        user-service (8007) + llm-router (8004) + citation-service (8005)

Wave 3: Data processing services
        document-service (8001) + output-service (8006)

Wave 4: Knowledge base service
        kb-service (8002)

Wave 5: Core orchestration
        orchestration-service (8003)

Wave 6: Entry layer
        api-gateway (8000)

Final Wave: Frontend
        frontend (5173)
```

### Step-by-step Startup

#### Step 1: Infrastructure (Terminal 1)

```bash
cd /Users/onetreehill/EconAI
docker compose up -d postgres redis etcd minio minio-init milvus

# Wait for all infrastructure to be ready (Milvus may need 90s+ on ARM)
docker compose ps | grep -E "postgres|redis|milvus|minio" | grep -v "minio-init"
# All should show "healthy"
```

> **Note**: The `minio-init` container stops automatically after execution (`restart: "no"`), don't worry about its Exited status.

#### Step 2: Independent Services (Terminals 2, 3, 4)

```bash
# Terminal 2: user-service
cd /Users/onetreehill/EconAI/services/user-service
uv run uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload

# Terminal 3: llm-router
cd /Users/onetreehill/EconAI/services/llm-router
uv run uvicorn llm_router.app:app --host 0.0.0.0 --port 8004 --reload

# Terminal 4: citation-service
cd /Users/onetreehill/EconAI/services/citation-service
uv run uvicorn citation_service.app:app --host 0.0.0.0 --port 8005 --reload
```

#### Step 3: Data Processing Services (Terminals 5, 6)

```bash
# Terminal 5: document-service + Celery worker
cd /Users/onetreehill/EconAI/services/document-service
uv run uvicorn document_service.app:app --host 0.0.0.0 --port 8001 --reload
# Open another terminal tab for Celery worker:
cd /Users/onetreehill/EconAI/services/document-service
uv run celery -A document_service.celery_app worker --loglevel=INFO --concurrency=2 --queues=document

# Terminal 6: output-service
cd /Users/onetreehill/EconAI/services/output-service
uv run uvicorn output_service.app:app --host 0.0.0.0 --port 8006 --reload
```

#### Step 4: Knowledge Base Service (Terminal 7)

```bash
cd /Users/onetreehill/EconAI/services/kb-service
uv run uvicorn kb_service.app:app --host 0.0.0.0 --port 8002 --reload
```

#### Step 5: Orchestration Service (Terminal 8)

```bash
cd /Users/onetreehill/EconAI/services/orchestration-service
uv run uvicorn orchestration_service.app:app --host 0.0.0.0 --port 8003 --reload
# Celery Agent worker (another tab):
cd /Users/onetreehill/EconAI/services/orchestration-service
uv run celery -A orchestration_service.celery_app worker --loglevel=INFO --concurrency=4 --queues=orchestration
```

#### Step 6: API Gateway (Terminal 9)

**Important**: When manually starting the api-gateway, you must explicitly pass the Redis password and localhost addresses for all backend services. Default Docker container names (e.g., `http://user-service:8007`) only work in Docker Compose environments.

```bash
cd /Users/onetreehill/EconAI/api-gateway
API_GATEWAY_REDIS_URL="redis://:econai_redis_change_me@localhost:6379/0" \
  API_GATEWAY_USER_SERVICE_URL="http://localhost:8007" \
  API_GATEWAY_DOCUMENT_SERVICE_URL="http://localhost:8001" \
  API_GATEWAY_KB_SERVICE_URL="http://localhost:8002" \
  API_GATEWAY_ORCHESTRATION_SERVICE_URL="http://localhost:8003" \
  API_GATEWAY_CITATION_SERVICE_URL="http://localhost:8005" \
  API_GATEWAY_OUTPUT_SERVICE_URL="http://localhost:8006" \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> If you modified `REDIS_PASSWORD` in `.env`, replace `econai_redis_change_me` in the URL above with your actual password.

#### Step 7: Frontend (Terminal 10)

```bash
cd /Users/onetreehill/EconAI/frontend
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## 3. Module Path Quick Reference

| Service | Directory | uvicorn Module Path | Port | Special Startup Parameters |
|---------|-----------|---------------------|------|---------------------------|
| API Gateway | `api-gateway/` | `app.main:app` | 8000 | Needs Redis URL + all backend localhost addresses |
| Document Service | `services/document-service/` | `document_service.app:app` | 8001 | Also needs Celery worker |
| KB Service | `services/kb-service/` | `kb_service.app:app` | 8002 | Depends on Milvus being ready first |
| Orchestration | `services/orchestration-service/` | `orchestration_service.app:app` | 8003 | Also needs Celery worker |
| LLM Router | `services/llm-router/` | `llm_router.app:app` | 8004 | — |
| Citation Service | `services/citation-service/` | `citation_service.app:app` | 8005 | — |
| Output Service | `services/output-service/` | `output_service.app:app` | 8006 | — |
| User Service | `services/user-service/` | `app.main:app` | 8007 | — |

---

## 4. Verification

```bash
# One-click verification script
for port in 8000 8001 8002 8003 8004 8005 8006 8007; do
  echo -n "port $port: "
  curl -s http://localhost:$port/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','FAIL'), '-', d.get('service','?'))" 2>/dev/null || echo "FAIL"
done

# Frontend
open http://localhost:5173
```

Expected: all return `healthy` or `ok`.

---

## 5. FAQ

### Port Already in Use

```bash
lsof -ti:8000 | xargs kill -9   # Replace port number
```

### Database Connection Failed

Verify PostgreSQL is up and healthy:
```bash
docker compose ps postgres
docker exec econai-postgres pg_isready -U econai
```

### Celery Worker Cannot Connect to Redis

```bash
docker exec econai-redis redis-cli -a $(grep REDIS_PASSWORD .env | cut -d= -f2) ping
```

### Claude API Not Configured

If not using Claude API, the LLM Router will fall back to local LLM. Ensure in `.env`:
```bash
LOCAL_LLM_ENDPOINT=http://localhost:8000/v1   # vLLM/Ollama address
```

If using Ollama as a Claude-compatible proxy, also configure:
```bash
ANTHROPIC_API_BASE_URL=http://host.docker.internal:11434
```

> Note: Inside Docker containers, `localhost` points to the container itself. To access host services from containers, use `host.docker.internal`.

### Frontend API Requests Blocked by CORS

The frontend Vite dev server has proxy configured — `/api` requests are proxied to `localhost:8000`. Ensure the API gateway is running on port 8000.

### Milvus Won't Start (Common on ARM Mac)

**Symptom**: `docker compose ps milvus` shows `Exited (134)` or repeated restarts

**Root Cause**: Custom `milvus.yaml` conflicts with `milvus run standalone`, cluster mode port configuration causes multiple components (rootcoord, datacoord, querycoord) to compete for the same port.

**Solution** (already applied in `docker-compose.yml`):

1. Don't mount custom `milvus.yaml` (let Milvus use built-in standalone defaults)
2. MinIO access key unified with environment variables as `minioadmin`
3. Health check `start_period` at least 90s

Verification:
```bash
# Confirm host port 19530 is not occupied by a stale process
lsof -i :19530
# If occupied, kill the stale process
lsof -ti:19530 | xargs kill -9

# Rebuild Milvus
docker compose stop milvus
docker compose rm -f milvus
docker volume rm econai_milvus-data   # Clear old data (optional)
docker compose up -d milvus
# Wait ~90s
docker compose ps milvus
```

### api-gateway /health Returns SYS_INTERNAL_ERROR

**Symptom**: `curl http://localhost:8000/health` returns Redis `Authentication required` error

**Root Cause**: api-gateway's default `redis_url = "redis://localhost:6379/0"` has no password, but Docker Redis has `requirepass` auth enabled.

**Solution**: Set environment variable at startup:
```bash
API_GATEWAY_REDIS_URL="redis://:${REDIS_PASSWORD}:<your-password>@localhost:6379/0"
```
(Default password in `.env` `REDIS_PASSWORD`)

### minio-init Keeps Restarting

**Symptom**: `minio-init` container gets re-launched by Docker after successful exit

**Root Cause**: `minio-init` inherited `*common-service`'s `restart: unless-stopped`, Docker keeps restarting after script exits successfully.

**Solution** (already applied in `docker-compose.yml`): Override with `restart: "no"` on the `minio-init` service.

### Frontend Login Failed

**Symptom**: Enter admin/Admin@123456 on frontend, prompt shows `Backend service for /api/auth/login is unavailable`

**Possible Causes**:

1. **api-gateway backend address wrong** — user sees `HTTP 503`:
   - Check api-gateway logs for `Failed to proxy to http://user-service:8007: [Errno 8] nodename nor servname provided`
   - **Fix**: Restart api-gateway with all `localhost` addresses (see Step 6 full startup command)

2. **api-gateway Redis not connected** — user sees `HTTP 500` and logs have `Authentication required`:
   - **Fix**: Set `API_GATEWAY_REDIS_URL` with password

3. **Audit log write failed** — user sees `HTTP 500` and logs have `DatatypeMismatchError` or `UndefinedColumnError`:
   - If `column "resource_id" is of type uuid`: confirm `audit_log` model and DB schema are both fixed (already applied in code)
   - If `column users.ldap_dn does not exist`: run `docker exec econai-postgres psql -U econai -d econai -c "ALTER TABLE users ADD COLUMN IF NOT EXISTS ldap_dn VARCHAR(255);"`

4. **Password hash mismatch** — user sees `AUTH_INVALID_CREDENTIALS`:
   - Regenerate admin password: in `services/user-service` directory run `uv run python3 -c "import bcrypt; print(bcrypt.hashpw(b'Admin@123456', bcrypt.gensalt(rounds=12)).decode())"`
   - Update database: `docker exec econai-postgres psql -U econai -d econai -c "UPDATE users SET hashed_password = '<new hash>' WHERE username = 'admin';"`

---

## 6. Docker Compose Key Configuration Notes

Below are important deviations from defaults (all in `docker-compose.yml`):

```yaml
# minio-init: disable restart (one-time init task)
minio-init:
  restart: "no"     # Overrides *common-service's unless-stopped

# milvus: ARM Mac compatibility config
milvus:
  image: milvusdb/milvus:v2.4.0
  environment:
    # Credentials must match MinIO root user
    MINIO_ACCESS_KEY_ID: ${MINIO_ROOT_USER:-minioadmin}
    MINIO_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD:-minioadmin_change_me}
  # Do not mount custom milvus.yaml (avoids port conflicts)
  volumes:
    - milvus-data:/var/lib/milvus
  healthcheck:
    start_period: 90s    # Extended for slower ARM initialization
```

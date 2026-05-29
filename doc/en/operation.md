# EconAI Operations Manual

> Version: v1.3 | Applicable to EconAI v1.3 Full Deployment

---

## 1. System Architecture Overview

EconAI consists of the following services, deployed on a single server or multiple servers:

| Component | Container Name | Port | Description |
|------|--------|------|------|
| Nginx | `econai-nginx` | 80, 443 | Reverse proxy + TLS termination |
| API Gateway | `econai-api-gateway` | 8000 | JWT authentication/RBAC/rate limiting/audit |
| Document Service | `econai-document-service` | 8001 | Document upload/parsing/chunking/OCR |
| KB Service | `econai-kb-service` | 8002 | Vector indexing/hybrid search |
| Orchestration Service | `econai-orchestration-service` | 8003 | Agent engine/task orchestration |
| LLM Router | `econai-llm-router` | 8004 | LLM routing/adapter |
| Citation Service | `econai-citation-service` | 8005 | Citation resolution/validation/formatting |
| Output Service | `econai-output-service` | 8006 | Multi-format report generation |
| User Service | `econai-user-service` | 8007 | Authentication/RBAC/audit logs |
| PostgreSQL | `econai-postgres` | 5432 | Business data + FTS |
| Redis | `econai-redis` | 6379 | Cache/queue/pub-sub/rate limiting |
| Milvus | `econai-milvus` | 19530 | Vector indexing |
| etcd | `econai-etcd` | 2379 | Milvus metadata coordination |
| MinIO | `econai-minio` | 9000, 9001 | Object storage |
| Celery Worker (Document) | `econai-celery-document` | - | Async document parsing |
| Celery Worker (Orchestration) | `econai-celery-orchestration` | - | Async Agent analysis |
| Celery Beat | `econai-celery-beat` | - | Scheduled task scheduler |
| Prometheus | `econai-prometheus` | 9090 | Metrics collection |
| Grafana | `econai-grafana` | 3000 | Monitoring dashboards |

All services communicate through the `econai-network` bridge network.

---

## 2. Environment Requirements

### Hardware Configuration (Minimum)

| Environment | CPU | Memory | Disk | GPU (Recommended) |
|------|-----|------|------|------------|
| Dev/Test | 4 cores | 16 GB | 100 GB SSD | Not required |
| Production | 8 cores | 32 GB | 500 GB SSD | 1x NVIDIA GPU (local LLM inference) |

### Software Dependencies

- **Docker** 24.0+
- **Docker Compose** 2.20+
- **Host OS**: Ubuntu 22.04+ / CentOS 8+ / macOS 13+
- Optional: NVIDIA Container Toolkit (if using GPU for local LLM inference)

---

## 3. First-Time Deployment

### 3.1 Obtain the Code

```bash
git clone <repository-url> /opt/econai
cd /opt/econai
```

### 3.2 Configure Environment Variables

```bash
# Create .env file from template
cp .env.template .env

# Edit .env, modify the following critical configuration items:
vim .env
```

**Required configuration items to modify:**

| Variable | Description | Notes |
|------|------|----------|
| `POSTGRES_PASSWORD` | Database password | Strong password, at least 16 characters |
| `REDIS_PASSWORD` | Redis password | Strong password |
| `JWT_SECRET` | JWT signing key | At least 32-character random string |
| `MINIO_ROOT_PASSWORD` | MinIO admin password | At least 8 characters |
| `MINIO_SECRET_KEY` | MinIO access key | Strong password |
| `ANTHROPIC_API_KEY` | Claude API key | Can be empty if not using Claude API |
| `DEFAULT_ADMIN_PASSWORD` | Default admin password | Must be changed in production |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password | Strong password |

**Generate secure keys:**

```bash
# Generate 32-character random JWT secret
openssl rand -hex 32

# Generate random password
openssl rand -base64 24
```

### 3.3 Prepare TLS Certificates (Production)

```bash
mkdir -p nginx/ssl

# Self-signed certificate (dev/test only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/econai.key \
  -out nginx/ssl/econai.crt \
  -subj "/CN=localhost"

# For production, use Let's Encrypt or a CA-issued certificate
# certbot certonly --standalone -d your-domain.com
# cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/econai.crt
# cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/econai.key
```

### 3.4 Configure Local LLM (Optional)

EconAI's LLM Router supports two backend providers:

- **Cloud (Anthropic Claude)**: Uses `ClaudeAdapter`, directly calling the Anthropic Messages API
- **Local (vLLM / Ollama / OpenAI compatible)**: Uses `LocalAdapter`, calling via an OpenAI-compatible `/v1/chat/completions` endpoint

#### 3.4.1 Using Ollama (Recommended for Local Development)

**Hardware requirements**: At least 8 GB RAM (7B model), 16 GB+ recommended.

**1. Install Ollama**

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Verify installation
ollama --version
```

**2. Start Ollama and Pull a Model**

```bash
# Start the service (macOS can use GUI or command line)
ollama serve &

# Pull a model (using qwen2.5-coder:7b as an example)
ollama pull qwen2.5-coder:7b

# Verify the model is available
ollama list
curl http://localhost:11434/v1/models
```

**3. Modify EconAI Configuration**

Edit `.env` and set Ollama's OpenAI-compatible endpoint:

```bash
# Modify the following two items in .env
LOCAL_LLM_ENDPOINT=http://localhost:11434/v1
LOCAL_LLM_DEFAULT_MODEL=qwen2.5-coder:7b
```

Edit `services/llm-router/models.yaml` to register the Ollama model and set it as the default local model:

```yaml
# models.yaml
models:
  - id: "auto"
    provider: "auto"
    # ... keep unchanged ...

  - id: "claude-sonnet-4-6"
    provider: "anthropic"
    # ... keep unchanged ...

  - id: "local:qwen2.5-coder:7b"
    provider: "ollama"
    type: "local"
    description: "Qwen2.5-Coder 7B via Ollama"
    capabilities:
      - chat
      - tool_use
      - streaming

default_local: "local:qwen2.5-coder:7b"
default_cloud: "claude-sonnet-4-6"
```

> **Note**: As long as the `provider` field is not `"anthropic"`, it will use `LocalAdapter` (OpenAI-compatible protocol).  
> `LocalAdapter` will automatically strip the `local:` prefix from the model ID before sending it to Ollama.

**4. Verify Connectivity**

```bash
# Check if LLM Router recognizes the new model
curl http://localhost:8004/internal/llm/models | python3 -m json.tool

# Send an actual conversation test
curl -X POST http://localhost:8004/internal/llm/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "sensitivity": "high",
    "messages": [{"role": "user", "content": "Hello, introduce yourself briefly."}],
    "max_tokens": 100,
    "temperature": 0.3
  }'
```

**5. Routing Behavior Explanation**

| `sensitivity` | Routing Target | Corresponding Model |
|---------------|----------|----------|
| `"high"` | Local model (data-sensitive, no external network) | `default_local` |
| `"low"` | Cloud model (strong capabilities, low-sensitivity tasks) | `default_cloud` |

When the cloud model is unreachable, `sensitivity=low` requests will automatically fall back to the local model.

#### 3.4.2 Using vLLM (High-Performance Production)

```bash
# .env
LOCAL_LLM_ENDPOINT=http://<vllm-server-ip>:8000/v1
LOCAL_LLM_DEFAULT_MODEL=qwen3-72b

# Register the model in models.yaml
- id: "local:qwen3-72b"
  provider: "vllm"
  type: "local"
  description: "Qwen3 72B via vLLM"
```

#### 3.4.3 Configure Claude API Custom Endpoint (Ollama Proxy)

If using Ollama's Anthropic-compatible proxy (such as `ollama-proxy`), configure `ANTHROPIC_API_BASE_URL`:

```bash
# .env — when running Ollama on the host
ANTHROPIC_API_BASE_URL=http://host.docker.internal:11434

# .env — when Ollama is on a remote server
ANTHROPIC_API_BASE_URL=http://192.168.1.100:11434
```

> **Important**: Inside Docker containers, `localhost` points to the container itself. To access host services, you must use `host.docker.internal`.

#### 3.4.4 Not Using a Local LLM

If only using the Anthropic Claude API, ensure the following in `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx         # Fill in a valid API Key
LOCAL_LLM_ENDPOINT=                     # Leave empty
```

`CLOUD_LLM_DEFAULT_MODEL` defaults to `claude-sonnet-4-6`.  
Without a local LLM, all `sensitivity=high` requests will fail (recommended to uniformly use `sensitivity=low` on the calling side).

### 3.5 Start Services

```bash
# Build all images
./deploy/deploy.sh build

# Start all services
./deploy/deploy.sh start
```

The first startup initializes in order: PostgreSQL → Redis → etcd + MinIO → Milvus → Microservices → Nginx. The entire process takes approximately 3-5 minutes.

### 3.6 Verify Deployment

```bash
# View all service statuses
./deploy/deploy.sh status

# All services should show "healthy"
# Expected output: 18 containers, all statuses healthy

# Verify API Gateway
curl http://localhost:8000/health
# Expected: {"status":"healthy"}

# Verify User Service
curl http://localhost:8007/health
# Expected: {"status":"healthy"}
```

---

## 4. Daily Operations Commands

### Service Management

```bash
# Start
./deploy/deploy.sh start

# Stop
./deploy/deploy.sh stop

# Restart
./deploy/deploy.sh restart

# View status
./deploy/deploy.sh status

# View logs (all services)
./deploy/deploy.sh logs

# View logs for a specific service
./deploy/deploy.sh logs api-gateway
./deploy/deploy.sh logs orchestration-service

# Rebuild a specific service image and restart
docker compose build --no-cache api-gateway
docker compose up -d api-gateway
```

### Database Management

```bash
# Connect to database
docker exec -it econai-postgres psql -U econai -d econai

# Common queries
SELECT count(*) FROM documents;           -- Total document count
SELECT count(*) FROM analysis_tasks;      -- Total task count
SELECT status, count(*) FROM analysis_tasks GROUP BY status;  -- Task status distribution

# Backup database
docker exec econai-postgres pg_dump -U econai econai > backup_$(date +%Y%m%d).sql

# Restore database
docker exec -i econai-postgres psql -U econai econai < backup_20260101.sql
```

### MinIO File Management

MinIO Console address: `http://<host>:9001`

- Username: `MINIO_ROOT_USER` (default `minioadmin`)
- Password: `MINIO_ROOT_PASSWORD`

Two Buckets: `econai-documents` (original documents), `econai-outputs` (generated report files).

### Viewing Logs

```bash
# Real-time view of all logs
./deploy/deploy.sh logs

# View the last 200 lines
docker compose logs --tail=200 api-gateway

# Filter by time
docker compose logs --since 2026-01-01T00:00:00 orchestration-service

# Export logs
docker compose logs > econai-logs-$(date +%Y%m%d).txt 2>&1
```

Log format is JSON, containing fields such as `timestamp`, `level`, `logger`, `message`, `request_id`.

### Celery Task Management

```bash
# View the document queue
docker exec econai-redis redis-cli -a $REDIS_PASSWORD LLEN document

# View the orchestration queue
docker exec econai-redis redis-cli -a $REDIS_PASSWORD LLEN orchestration

# Clear a queue (use with caution!)
docker exec econai-redis redis-cli -a $REDIS_PASSWORD DEL document
```

---

## 5. Monitoring

### Prometheus Metrics

- Address: `http://<host>:9090`
- API Gateway metrics endpoint: `http://<host>:8000/metrics`
- Each microservice exposes a `/metrics` endpoint
- Data retention period: 30 days

### Grafana Dashboards

- Address: `http://<host>:3000`
- Default username: `admin`
- Default password: `GRAFANA_ADMIN_PASSWORD`

### Key Monitoring Metrics

| Metric | Description | Alert Threshold |
|------|------|----------|
| `http_requests_total` | Total API requests | - |
| `http_request_duration_seconds` | Request latency | P95 > 5s |
| `celery_tasks_total` | Total tasks | - |
| `celery_tasks_failed_total` | Failed task count | > 10/hour |
| `postgres_connections_active` | Active database connections | > 80% max connections |
| `redis_memory_used_bytes` | Redis memory usage | > 80% maxmemory |
| `milvus_search_latency_seconds` | Vector search latency | P95 > 1s |

---

## 6. Backup Strategy

### Data Requiring Backup

| Data | Location | Backup Method | Frequency |
|------|------|----------|------|
| PostgreSQL | Docker Volume `econai-postgres-data` | `pg_dump` | Daily |
| MinIO Files | Docker Volume `econai-minio-data` | `mc mirror` | Daily |
| Redis Data | Docker Volume `econai-redis-data` | AOF file (enabled by default) | Real-time |
| Config Files | `.env`, `nginx/` | Git or file copy | After modification |

### Sample Backup Script

```bash
#!/bin/bash
# Save as /opt/econai/deploy/backup.sh
BACKUP_DIR=/backup/econai
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR/$DATE

# Backup PostgreSQL
docker exec econai-postgres pg_dump -U econai econai > $BACKUP_DIR/$DATE/db.sql

# Backup MinIO
docker run --rm --network econai-network \
  -v $BACKUP_DIR/$DATE:/backup \
  minio/mc:latest \
  mc mirror local/econai-documents /backup/documents

# Backup config
cp .env $BACKUP_DIR/$DATE/.env

# Retain the last 30 days
find $BACKUP_DIR -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;
```

### Restore Steps

```bash
# 1. Stop services
./deploy/deploy.sh stop

# 2. Restore database
docker compose up -d postgres
sleep 10
docker exec -i econai-postgres psql -U econai econai < backup/db.sql

# 3. Restore MinIO files
# Upload via MinIO Console, or use the mc client

# 4. Start services
./deploy/deploy.sh start
```

---

## 7. Scaling and High Availability

### Horizontal Scaling

```bash
# Scale Celery Workers (increase concurrent processing capacity)
docker compose up -d --scale celery-worker-document=3
docker compose up -d --scale celery-worker-orchestration=3
```

### Performance Tuning

Key configuration items (adjust in `.env`):

```bash
# PostgreSQL connection pool
# Adjust based on concurrency, default max_connections=100

# Redis maxmemory
REDIS_MAXMEMORY=4gb                        # Increase cache space

# Celery concurrency
CELERY_WORKER_CONCURRENCY=8               # Adjust based on CPU cores

# Agent timeout
AGENT_TOOL_TIMEOUT_S=120                  # Increase timeout for complex tasks
TASK_TIMEOUT_MINUTES=60                   # Increase for large document analysis

# Search timeout
SEARCH_TIMEOUT_MS=10000                   # Increase for large knowledge bases
```

### Production Environment Notes

- Use an external PostgreSQL cluster instead of a single instance inside a Docker container
- Milvus production deployment should use distributed mode (not standalone)
- Add a load balancer (such as HAProxy) in front of Nginx for gateway-level high availability
- Use ELK/Loki for centralized log collection
- Regularly clean up `llm_usage_logs` and `audit_logs` tables (recommended retention: 6 months)

---

## 8. Troubleshooting

### Service Fails to Start

```bash
# 1. Check port conflicts
ss -tlnp | grep -E "8000|8001|8002|8003|8004|8005|8006|8007|5432|6379"

# 2. Check disk space
df -h

# 3. Check Docker logs
docker compose logs postgres
docker compose logs redis

# 4. Restart
./deploy/deploy.sh restart
```

### Database Connection Failure

```bash
# Check if PostgreSQL is ready
docker exec econai-postgres pg_isready -U econai

# Check connection count
docker exec econai-postgres psql -U econai -c "SELECT count(*) FROM pg_stat_activity;"

# Reset connections
docker compose restart postgres
```

### LLM Call Failure

```bash
# Check LLM Router logs
docker compose logs llm-router

# Check Claude API key
grep ANTHROPIC_API_KEY .env

# Check Claude API custom endpoint (if configured)
grep ANTHROPIC_API_BASE_URL .env

# Check local LLM connectivity (Ollama port 11434, vLLM port 8000)
curl -s http://localhost:11434/v1/models      # Ollama
curl -s http://<llm-server>:8000/v1/models   # vLLM

# Verify LLM Router itself is reachable
curl http://localhost:8004/health

# Verify LLM Router has registered models
curl http://localhost:8004/internal/llm/models

# Enable fallback mode (auto-switch to local LLM when Claude is unreachable)
# Confirm LLM_ROUTER_HOST and LOCAL_LLM_ENDPOINT are configured correctly
```

**Ollama-specific troubleshooting**:

```bash
# Check if Ollama is running
pgrep -a ollama

# Ollama service status (macOS)
launchctl list | grep ollama

# Check if the model is pulled
ollama list

# Restart Ollama
killall ollama && ollama serve &
```

**Local LLM timeout**: If model response is slow, increase `LLM_REQUEST_TIMEOUT_S` in `.env` (default 120 seconds). The first-token latency for a 7B model on CPU can reach 10-30 seconds.

### Task Stuck in Running Status

```bash
# View stuck tasks
docker exec econai-postgres psql -U econai -c \
  "SELECT id, title, status, started_at FROM analysis_tasks WHERE status='running' AND started_at < now() - interval '30 minutes';"

# Manually cancel a task
docker exec econai-postgres psql -U econai -c \
  "UPDATE analysis_tasks SET status='failed', error_message='Manual timeout recovery' WHERE id='<task-id>';"

# Clear old tasks from the Celery queue
docker exec econai-redis redis-cli -a $REDIS_PASSWORD DEL orchestration
```

### Redis Out of Memory

```bash
# Check memory usage
docker exec econai-redis redis-cli -a $REDIS_PASSWORD INFO memory

# Manually purge expired cache
docker exec econai-redis redis-cli -a $REDIS_PASSWORD MEMORY PURGE

# Increase maxmemory (modify .env then restart)
REDIS_MAXMEMORY=4gb
./deploy/deploy.sh restart
```

---

## 9. Security Recommendations

### Required Actions

1. **Change all default passwords**: All passwords in `.env` with `change_me` suffix
2. **JWT Secret**: Use `openssl rand -hex 32` to generate a strong random key
3. **TLS Certificates**: Production must use CA-issued certificates
4. **Firewall**: Only open ports 80/443 to the public; internal service ports (8000-8007, 5432, 6379, etc.) accessible only from the host
5. **API Rate Limiting**: Adjust `RATE_LIMIT_*` parameters based on actual user volume

### Firewall Example (iptables)

```bash
# Allow only local access to internal services
iptables -A INPUT -p tcp --dport 8000:8007 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000:8007 -j DROP
iptables -A INPUT -p tcp --dport 5432 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 5432 -j DROP
```

### Audit Log Retention

The `audit_logs` table retains 6 months by default, adjustable via `AUDIT_LOG_RETENTION_MONTHS`. Periodically archive and clean up expired records.

---

## 10. Version Upgrade

```bash
# 1. Pull new code
git pull origin master

# 2. Check if .env.template has new configuration items
diff .env .env.template

# 3. Rebuild images
./deploy/deploy.sh build

# 4. Rolling restart of services
docker compose up -d --no-deps --build api-gateway
docker compose up -d --no-deps --build document-service
# ... restart one by one in dependency order

# 5. Verify
./deploy/deploy.sh status
curl http://localhost:8000/health
```

---

## 11. Complete Shutdown and Disk Cleanup

The following steps will stop all Docker services and host-level processes, and clean up disk space.

### 11.1 Stop All Services

```bash
# 1. Stop all services managed by Docker Compose
./deploy/deploy.sh stop

# Expected output: 18 containers stopped in sequence and network removed
```

### 11.2 Stop Host-Level Processes

If using Ollama (non-Docker mode):

```bash
# Check if Ollama is running
pgrep -a ollama

# Stop Ollama
killall ollama

# Or via launchctl (macOS)
launchctl unload ~/Library/LaunchAgents/com.ollama.ollama.plist 2>/dev/null
```

If manually started LLM Router (uvicorn):

```bash
# Find and terminate processes occupying port 8004
lsof -i :8004 -P -n -t | xargs kill
```

### 11.3 View Disk Usage

```bash
# View Docker disk usage overview
docker system df

# List all images with sizes
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# List all Docker volumes
docker volume ls
```

### 11.4 Delete Docker Images (Free Disk Space)

> **Note**: After deletion, restarting will require re-pulling images, which needs network access and takes several minutes.

```bash
# Delete a single image
docker rmi <image-name>:<tag>

# Delete all unused images
docker image prune -a

# Delete all images (use with caution!)
docker rmi $(docker images -q)
```

Typical deletable EconAI infrastructure images:

| Image | Size | Description |
|------|------|------|
| `milvusdb/milvus:v2.4.0` | ~2 GB | Milvus vector database |
| `postgres:16-alpine` | ~390 MB | PostgreSQL |
| `quay.io/coreos/etcd:v3.5.5` | ~260 MB | Milvus metadata coordination |
| `minio/minio:latest` | ~230 MB | Object storage |
| `minio/mc:latest` | ~110 MB | MinIO client |
| `redis:7-alpine` | ~60 MB | Redis |

### 11.5 Clean Up Docker Volumes (Optional, Will Delete All Data)

> **Dangerous operation**: Volumes contain databases, vector indexes, and uploaded files. Only execute after confirming data is no longer needed.

```bash
# View EconAI-related volumes
docker volume ls --filter "name=econai"

# Delete all EconAI volumes (data is unrecoverable!)
docker volume rm econai-etcd-data econai-milvus-data \
                econai-minio-data econai-postgres-data \
                econai-redis-data

# Or delete all unused volumes
docker volume prune
```

### 11.6 Complete Cleanup (One-Click)

```bash
# Stop and clean up all EconAI-related resources
./deploy/deploy.sh stop
docker image prune -a --force
docker volume prune --force

# For development environments, execute after confirmation
docker system prune -a --volumes --force
```

### 11.7 Restart

```bash
# If you need to restart the system (images will be pulled automatically)
./deploy/deploy.sh start

# If using Ollama
ollama serve &
ollama pull qwen2.5-coder:7b
```

---

## 12. Configuration Troubleshooting Experience

### 12.1 JWT Secret Mismatch — The pydantic-settings `env_prefix` Trap

**Symptom**: All requests through API Gateway return `401 AUTH_TOKEN_INVALID`, but manual startup works fine.

**Root Cause**: Both `api-gateway/app/config.py` and `user-service/app/config.py` use `pydantic-settings`'s `env_prefix`:

```python
# api-gateway/app/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="API_GATEWAY_")

# user-service/app/config.py
class UserServiceSettings(AppSettings):
    model_config = SettingsConfigDict(env_prefix="USER_SERVICE_")
```

`docker-compose.yml` sets generic variable names without prefixes:

```yaml
# ❌ Wrong — both services' env_prefix will ignore these
- JWT_SECRET=econai_jwt_secret_change_me_min_32_chars
- JWT_ALGORITHM=HS256
```

Both services' `JWT_SECRET` fields fall back to their respective hardcoded default values, which are different, causing JWT tokens signed by user-service to be rejected by api-gateway.

**Fix**: Use prefixed environment variables for each service in `docker-compose.yml`:

```yaml
# ✅ Correct — api-gateway environment variables
- API_GATEWAY_JWT_SECRET=${JWT_SECRET:-econai_jwt_secret_change_me_min_32_chars}
- API_GATEWAY_JWT_ALGORITHM=${JWT_ALGORITHM:-HS256}
- API_GATEWAY_JWT_ACCESS_EXPIRE_MINUTES=${JWT_ACCESS_EXPIRE_MINUTES:-120}
- API_GATEWAY_JWT_REFRESH_EXPIRE_HOURS=${JWT_REFRESH_EXPIRE_HOURS:-24}

# ✅ Correct — user-service environment variables
- USER_SERVICE_JWT_SECRET=${JWT_SECRET:-econai_jwt_secret_change_me_min_32_chars}
- USER_SERVICE_JWT_ALGORITHM=${JWT_ALGORITHM:-HS256}
- USER_SERVICE_JWT_ACCESS_EXPIRE_MINUTES=${JWT_ACCESS_EXPIRE_MINUTES:-120}
- USER_SERVICE_JWT_REFRESH_EXPIRE_HOURS=${JWT_REFRESH_EXPIRE_HOURS:-24}
```

**Verification Method**:

```bash
docker exec econai-api-gateway python -c "from app.config import settings; print(settings.jwt_secret)"
docker exec econai-user-service python -c "from app.config import settings; print(settings.jwt_secret)"
# Both outputs must be identical
```

### 12.2 Ollama Unreachable Inside Container — `localhost` vs `host.docker.internal`

**Symptom**: LLM Router calls to local Ollama return `503 Circuit breaker open for local`, but `curl http://localhost:11434/api/tags` works on the host.

**Root Cause**: `LOCAL_LLM_ENDPOINT` in `docker-compose.yml` or `.env` uses `http://localhost:11434/v1`. Inside the container, `localhost` points to the container itself, not the host.

**Fix**: Change the Ollama endpoint to `host.docker.internal`:

```bash
# .env
LOCAL_LLM_ENDPOINT=http://host.docker.internal:11434/v1
```

```yaml
# docker-compose.yml
- LOCAL_LLM_ENDPOINT=${LOCAL_LLM_ENDPOINT:-http://host.docker.internal:11434/v1}
```

> **Note**: After modifying `.env`, you must use `--force-recreate` to rebuild the container; `restart` will not reload environment variables.  
> ```bash
> docker compose up -d --no-deps --force-recreate llm-router
> ```

### 12.3 Integration Test Data Isolation

**Symptom**: Running the full test suite occasionally produces failures like `assert 404 == 200`, but running the same module's tests individually all pass.

**Root Cause**: `test_integration_flows.py` creates users and projects first, then `test_m8_*` modules assume the database is in a clean state (e.g., `list_users` expects the paginated first page to contain the just-created user), getting polluted by earlier test data.

**Diagnosis**: Check for accumulated orphan test data in the database:

```bash
docker exec econai-postgres psql -U econai -d econai -c \
  "SELECT username FROM users WHERE username LIKE 'lifecycle_%' OR username LIKE 'test%';"
docker exec econai-postgres psql -U econai -d econai -c \
  "SELECT name FROM projects ORDER BY created_at DESC LIMIT 20;"
```

**Cleanup**:

```bash
docker exec econai-postgres psql -U econai -d econai -c \
  "DELETE FROM projects; DELETE FROM users WHERE username != 'admin';"
```

> **Recommendation**: Add a session-level fixture in `conftest.py` to automatically clean up at the start of tests, or adjust pytest execution order (`test_m8_*` runs before `test_integration_flows`).

### 12.4 Recreating Containers vs Restarting Containers

After modifying `docker-compose.yml` or `.env`, `docker compose restart` will **not** reload environment variables. You must use `--force-recreate`:

```bash
# ❌ Ineffective — environment variables are not updated
docker compose restart service-name

# ✅ Correct — recreates the container, environment variables take effect
docker compose up -d --no-deps --force-recreate service-name
```

---

## 13. Dockerfile Build Specifications

All EconAI service Dockerfiles follow a unified build pattern. The following four key elements are hard rules refined after multiple pitfalls and must be followed when modifying Dockerfiles:

### 13.1 Do Not Use BuildKit Bind Mount

```dockerfile
# ❌ Wrong (incompatible with Colima / legacy Docker daemon, hangs immediately)
RUN --mount=type=bind,source=shared,target=/shared ...

# ✅ Correct (universal across all Docker environments)
COPY shared /shared
```

**Reason**: `--mount=type=bind` requires the Docker daemon to have BuildKit enabled. Colima defaults to the legacy builder, and encountering unrecognized `--mount` syntax will hang directly. `COPY` is universal across all environments, and shared only has 8 `.py` files, so the space impact is negligible.

### 13.2 `shared/pyproject.toml` Must Use `where = ["."]`

```toml
# ❌ Wrong (inside container, ".." resolves to /, setuptools scans the entire Linux root filesystem)
[tool.setuptools.packages.find]
where = [".."]
include = ["shared"]

# ✅ Correct (only searches in the directory where pyproject.toml resides, consistent behavior locally and in container)
[tool.setuptools.packages.find]
where = ["."]
include = ["shared"]
```

**Reason**: `where = [".."]` resolves to the project root directory on the host (~20 directories, completes in seconds), but in the container at `/shared/pyproject.toml` it resolves to `/` (root filesystem), causing setuptools to recursively scan tens of thousands of directories like `/proc`, `/sys`, `/usr`, etc., never finishing.

### 13.3 Do Not Use `--only-binary :all:`

```dockerfile
# ❌ Wrong (prohibits all source installations, including your own econai-shared and `uv pip install .`)
RUN uv pip install --only-binary :all: --system .

# ✅ Correct (all dependencies already have ARM64 precompiled wheels)
RUN uv pip install --system .
```

**Reason**: `--only-binary :all:` originated from an earlier temporary workaround when `python-ldap` had no wheel for ARM64. It has since been replaced with pure-Python `ldap3`, and all dependencies have precompiled wheels, eliminating the need for this restriction.

### 13.4 Use `sed` to Convert Relative Paths to Absolute Paths

```dockerfile
# Single-stage service (7 services)
RUN sed -i 's|path = "../../shared"|path = "/shared"|g' pyproject.toml && \
    uv pip install --system .

# api-gateway builder stage
RUN sed -i 's|path = "../shared"|path = "/shared"|g' pyproject.toml && \
    uv pip install --system --no-cache .
```

**Reason**: The `[tool.uv.sources]` in service `pyproject.toml` files use relative paths pointing to shared:
```toml
econai-shared = { path = "../../shared" }
```
`uv pip install .` will forcibly resolve this path. Computing `../../shared` from `/app/` escapes the base directory, and uv errors out directly. Using `sed` to change it to the container absolute path `/shared` allows uv to resolve normally.

---

## 14. Change Log

### v1.3 (2026-05-29) — Document Download and Export Fix Enhancement

**Issues**: Knowledge base document download failed (missing `minio_download` import, blocking I/O calls); task export to Word (.docx) returned `AUTH_TOKEN_MISSING` (frontend `window.open` bypassed axios auth interceptor); API Gateway incorrectly routed `/api/tasks/{id}/export` to orchestration-service (returning JSON metadata instead of binary file); Chinese filenames in `Content-Disposition` header caused latin-1 encoding errors; knowledge base search results displayed `document_id` (UUID) instead of document names.

**Changes**:

| Component | Change Details |
|------|----------|
| `kb-service/bm25.py` | BM25 SQL query added `LEFT JOIN documents` to retrieve `document_title` and `document_filename` |
| `kb-service/hybrid_search.py` | Vector search and BM25 search results now include `document_title` and `document_filename` fields |
| `kb-service/app.py` | Added `_fetch_document_titles()` function: batch queries `original_name` from `documents` table via asyncpg, displaying full filenames (with extension) for search results; updated `_build_result()` to use document name mapping |
| `document-service/app.py` | Added `GET /api/projects/{project_id}/documents/{document_id}/download` download endpoint; fixed bug where `minio_download` was missing from top-level import; changed to `run_in_executor` async MinIO calls; `Content-Disposition` changed to RFC 5987 encoding (`filename*=UTF-8''...`) to support Chinese filenames; `StreamingResponse` changed to `Response` |
| `api-gateway/routing/registry.py` | Added priority routing for `/api/tasks/{id}/export` to `output-service` (file download), instead of `orchestration-service` (JSON metadata) |
| `frontend/api/tasks.ts` | Added `downloadExportFile()`: downloads file via axios (with auth interceptor) as blob and triggers browser download, replacing `window.open()` |
| `frontend/api/documents.ts` | Added `downloadDocumentFile()`: same method for downloading knowledge base document original files |
| `frontend/pages/TaskOutput.tsx` | `handleExport` now uses `downloadExportFile()` |
| `frontend/pages/KnowledgeBase.tsx` | Search results display `highlighted_content` (keyword highlighting); document download button now uses `downloadDocumentFile()` |
| `frontend/api/types.ts` | `SearchResultChunk` added `matched_terms`, `highlighted_content` fields |
| `document-service/tests/test_integration.py` | Added `TestDocumentDownload` class (8 test cases): covering PDF/text/DOCX/XLSX downloads, 404/500 error paths, cross-project isolation, Chinese filenames |

**Impact**: Requires rebuilding `document-service`, `kb-service`, `api-gateway` images and restarting the frontend. No database migration required.

### v1.1 (2026-05-24) — Project Group Member Management Optimization

**Issues**: When system administrators managed members in `/admin/groups`, adding members required manually entering user UUIDs, which was unintuitive; and the member list was not displayed.

**Changes**:

| Component | Change Details |
|------|----------|
| `user-service` | Added `GET /api/admin/groups/{id}/members` to list members (including username/display name/role); added `GET /api/admin/groups/{id}/non-members?q=` to search non-member users |
| Frontend `GroupManagement` | Member management dialog redesigned: search-style `Select` replacing UUID input field; table displaying current member list; support for removing members |
| Tests `test_m8_groups.py` | Added `test_list_members`, `test_list_non_members`, `test_non_members_search` |

**Impact**: Only affects `user-service` and frontend; no database migration or configuration changes required; takes effect after restarting services.

### v1.2 (2026-05-25) — Multi-Format Document Upload and OCR Image Recognition Enhancement

**Issues**: The system only supported uploading and parsing a few common formats such as `.txt`, `.md`, `.csv`, and could not handle the full Microsoft Office document suite or recognize text embedded in images.

**Changes**:

| Component | Change Details |
|------|----------|
| `frontend` | KB integration tests extended to 19 file extensions: PDF, Word (.docx/.doc), Excel (.xlsx/.xls/.csv), PowerPoint (.pptx/.ppt), images (.png/.jpg/.jpeg/.tiff/.bmp), email (.eml), web (.html/.mhtml/.mht), text (.txt/.md) |
| `document-service/image_extractor.py` | **New** shared image extraction + OCR core module, providing five general functions: `ocr_image_bytes`, `extract_images_from_pdf`, `extract_images_from_docx`, `extract_images_from_pptx`, `extract_images_from_html` |
| `document-service/models.py` | `ParsedContent` added `ocr_images` field, recording audit trail for each OCR (page number, image index, OCR text, format, dimensions) |
| `document-service/pdf_parser.py` | Integrated `extract_images_from_pdf` in `parse()`, OCR results auto-appended to corresponding page content |
| `document-service/word_parser.py` | Integrated `extract_images_from_docx` in `parse()`, OCR results appended to document full text |
| `document-service/ppt_parser.py` | Integrated `extract_images_from_pptx` in `parse()`, OCR results appended to corresponding slides |
| `document-service/html_parser.py` | Integrated `extract_images_from_html` in `parse()`, OCR for data-URI embedded images |
| `document-service/ocr_processor.py` | `_run_tesseract()` refactored to delegate to `image_extractor.ocr_image_bytes()`, eliminating code duplication |
| `document-service/pyproject.toml` | Added dependency `pytesseract>=0.3` |
| `document-service/tests/test_image_extraction.py` | **New** 24 test cases covering OCR basic functionality, PDF/DOCX/PPTX/HTML image extraction, parser ocr_images fields, content enhancement verification |

**New Configuration Items**:

| Config Item | Default | Description |
|--------|--------|------|
| `OCR_LANGUAGE` | `chi_sim+eng` | Tesseract OCR language pack (existing, enhanced usage in this release) |

**Impact**: Requires installing `tesseract-ocr` and corresponding language packs (`tesseract-ocr-chi-sim`, `tesseract-ocr`) in the document-service container. The Dockerfile already includes the corresponding `apt-get` installation steps. After upgrading, rebuild the document-service image: `docker compose build --no-cache document-service && docker compose up -d document-service`.

---

## Quick Reference

| Operation | Command |
|------|------|
| Start | `./deploy/deploy.sh start` |
| Stop | `./deploy/deploy.sh stop` |
| Restart | `./deploy/deploy.sh restart` |
| Status | `./deploy/deploy.sh status` |
| Logs | `./deploy/deploy.sh logs [service]` |
| Build | `./deploy/deploy.sh build` |
| View disk usage | `docker system df` |
| Delete all images | `docker rmi $(docker images -q)` |
| Clean up unused resources | `docker system prune -a` |
| Enter PostgreSQL | `docker exec -it econai-postgres psql -U econai` |
| Enter Redis | `docker exec -it econai-redis redis-cli -a <password>` |
| API health check | `curl http://localhost:8000/health` |
| Prometheus | `http://<host>:9090` |
| Grafana | `http://<host>:3000` |
| MinIO Console | `http://<host>:9001` |

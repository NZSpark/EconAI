# CLAUDE.md — celery

## Role

Celery task queue configuration shared by document-service (parse/chunk tasks) and orchestration-service (agent loop tasks). Used in Docker Compose, not for manual native startup (manual mode uses `uv run celery -A ...` directly from each service directory).

## Files

```
celery/
├── celery_app.py     # Celery app factory: broker=Redis DB0, backend=Redis DB1, 2 queues
└── celery_config.py  # Concurrency=4, worker mem limit=512MB, task hard limit=1800s, soft limit=1500s
```

## Queue routing

| Task prefix | Queue | Purpose |
|-------------|-------|---------|
| `econai.document.*` | `document` | Document parsing, chunking |
| `econai.orchestration.*` | `orchestration` | Agent loop task execution |

## Config highlights

```python
worker_concurrency = 4
worker_max_memory_per_child = 512_000   # KB
task_time_limit = 1800                  # 30 min hard limit
task_soft_time_limit = 1500             # 25 min soft limit (for grace)
```

## Docker Compose

Two Celery services defined in `docker-compose.yml`:
- `celery-worker-document` — builds from `services/document-service/Dockerfile`, `--queues=document`
- `celery-worker-orchestration` — builds from `services/orchestration-service/Dockerfile`, `--queues=orchestration`

## Manual start (native, not Docker)

When running natively (not via Docker Compose), Celery workers are started from each service directory:

```bash
cd services/document-service
uv run celery -A document_service.celery_app worker -Q document --concurrency=2

cd services/orchestration-service
uv run celery -A orchestration_service.celery_app worker -Q orchestration --concurrency=4
```

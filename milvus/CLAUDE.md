# CLAUDE.md — milvus

## Role

Milvus standalone configuration for Docker Compose. Used as the vector store backend for kb-service (M3).

## File

```
milvus/
└── milvus.yaml    # Milvus standalone config (etcd + MinIO endpoints)
```

## Config highlights

```yaml
etcd:
  endpoints: etcd:2379
minio:
  address: minio:9000
  accessKeyID: minioadmin
  secretAccessKey: minioadmin_change_me
port: 19530
log_level: info
```

## Docker Compose integration

In `docker-compose.yml`, the Milvus service:
- Image: `milvusdb/milvus:v2.4.0`
- **Note on ARM Mac**: The custom `milvus.yaml` mount is **NOT used** (commented out) because it conflicts with `milvus run standalone` mode. Instead, Milvus uses its built-in default configuration.
- Health check `start_period: 90s` (ARM builds are slower)
- Depends on `etcd` and `minio` (both must be healthy first)

## Ports

| Port | Purpose |
|------|---------|
| 19530 | gRPC client port (kb-service connects here) |
| 9091 | Metrics endpoint |

## Troubleshooting (ARM Mac)

If Milvus fails to start (Exited 134) or restarts continuously:
1. Ensure custom `milvus.yaml` is NOT mounted (let standalone use defaults)
2. MinIO credentials must be `minioadmin` / `minioadmin_change_me`
3. Wait at least 90s for health checks
4. If port 19530 is occupied by a zombie process: `lsof -ti:19530 | xargs kill -9`

## Used by

- `services/kb-service` — connects via gRPC on port 19530
- `docker-compose.yml` — service definition, health checks

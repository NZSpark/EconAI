# EconAI 运维手册

> 版本：v1.0 | 适用于 EconAI v1.0 完整部署

---

## 1. 系统架构概览

EconAI 由以下服务组成，部署在单台或多台服务器上：

| 组件 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| Nginx | `econai-nginx` | 80, 443 | 反向代理 + TLS 终结 |
| API Gateway | `econai-api-gateway` | 8000 | JWT 认证/RBAC/限流/审计 |
| Document Service | `econai-document-service` | 8001 | 文档上传/解析/分块 |
| KB Service | `econai-kb-service` | 8002 | 向量索引/混合检索 |
| Orchestration Service | `econai-orchestration-service` | 8003 | Agent 引擎/任务编排 |
| LLM Router | `econai-llm-router` | 8004 | LLM 路由/适配器 |
| Citation Service | `econai-citation-service` | 8005 | 引用解析/校验/格式化 |
| Output Service | `econai-output-service` | 8006 | 多格式报告生成 |
| User Service | `econai-user-service` | 8007 | 认证/RBAC/审计日志 |
| PostgreSQL | `econai-postgres` | 5432 | 业务数据 + FTS |
| Redis | `econai-redis` | 6379 | 缓存/队列/pub-sub/限流 |
| Milvus | `econai-milvus` | 19530 | 向量索引 |
| etcd | `econai-etcd` | 2379 | Milvus 元数据协调 |
| MinIO | `econai-minio` | 9000, 9001 | 对象存储 |
| Celery Worker (Document) | `econai-celery-document` | - | 异步文档解析 |
| Celery Worker (Orchestration) | `econai-celery-orchestration` | - | 异步 Agent 分析 |
| Celery Beat | `econai-celery-beat` | - | 定时任务调度 |
| Prometheus | `econai-prometheus` | 9090 | 指标采集 |
| Grafana | `econai-grafana` | 3000 | 监控仪表盘 |

所有服务通过 `econai-network` 桥接网络通信。

---

## 2. 环境要求

### 硬件配置（最低）

| 环境 | CPU | 内存 | 磁盘 | GPU（推荐） |
|------|-----|------|------|------------|
| 开发/测试 | 4 核 | 16 GB | 100 GB SSD | 不需要 |
| 生产 | 8 核 | 32 GB | 500 GB SSD | 1x NVIDIA GPU（本地 LLM 推理） |

### 软件依赖

- **Docker** 24.0+
- **Docker Compose** 2.20+
- **宿主机操作系统**：Ubuntu 22.04+ / CentOS 8+ / macOS 13+
- 可选：NVIDIA Container Toolkit（如果使用 GPU 本地 LLM 推理）

---

## 3. 首次部署

### 3.1 获取代码

```bash
git clone <repository-url> /opt/econai
cd /opt/econai
```

### 3.2 配置环境变量

```bash
# 从模板创建 .env 文件
cp .env.template .env

# 编辑 .env，修改以下关键配置项：
vim .env
```

**必须修改的配置项：**

| 变量 | 说明 | 注意事项 |
|------|------|----------|
| `POSTGRES_PASSWORD` | 数据库密码 | 强密码，至少 16 位 |
| `REDIS_PASSWORD` | Redis 密码 | 强密码 |
| `JWT_SECRET` | JWT 签名密钥 | 至少 32 位随机字符串 |
| `MINIO_ROOT_PASSWORD` | MinIO 管理员密码 | 至少 8 位 |
| `MINIO_SECRET_KEY` | MinIO 访问密钥 | 强密码 |
| `ANTHROPIC_API_KEY` | Claude API 密钥 | 如果不使用 Claude API 可为空 |
| `DEFAULT_ADMIN_PASSWORD` | 默认管理员密码 | 生产环境务必修改 |
| `GRAFANA_ADMIN_PASSWORD` | Grafana 管理员密码 | 强密码 |

**生成安全密钥：**

```bash
# 生成 32 位随机 JWT secret
openssl rand -hex 32

# 生成随机密码
openssl rand -base64 24
```

### 3.3 准备 TLS 证书（生产环境）

```bash
mkdir -p nginx/ssl

# 自签证书（仅开发/测试）
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/econai.key \
  -out nginx/ssl/econai.crt \
  -subj "/CN=localhost"

# 生产环境请使用 Let's Encrypt 或机构签发证书
# certbot certonly --standalone -d your-domain.com
# cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/econai.crt
# cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/econai.key
```

### 3.4 配置本地 LLM（可选）

如果使用本地 LLM 推理（vLLM/Ollama），修改 `.env`：

```bash
LOCAL_LLM_ENDPOINT=http://<llm-server-ip>:8000/v1
LOCAL_LLM_DEFAULT_MODEL=qwen3-72b
```

确保本地 LLM 服务器提供 OpenAI-compatible `/v1/chat/completions` 接口。

### 3.5 启动服务

```bash
# 构建所有镜像
./deploy/deploy.sh build

# 启动所有服务
./deploy/deploy.sh start
```

首次启动按顺序初始化：PostgreSQL → Redis → etcd + MinIO → Milvus → 各微服务 → Nginx。整个过程约需 3-5 分钟。

### 3.6 验证部署

```bash
# 查看所有服务状态
./deploy/deploy.sh status

# 所有服务应显示 "healthy"
# 预期输出：18 个容器，状态全部为 healthy

# 验证 API 网关
curl http://localhost:8000/health
# 预期：{"status":"healthy"}

# 验证用户服务
curl http://localhost:8007/health
# 预期：{"status":"healthy"}
```

---

## 4. 日常运维命令

### 服务管理

```bash
# 启动
./deploy/deploy.sh start

# 停止
./deploy/deploy.sh stop

# 重启
./deploy/deploy.sh restart

# 查看状态
./deploy/deploy.sh status

# 查看日志（全部服务）
./deploy/deploy.sh logs

# 查看特定服务日志
./deploy/deploy.sh logs api-gateway
./deploy/deploy.sh logs orchestration-service

# 重建特定服务的镜像并重启
docker compose build --no-cache api-gateway
docker compose up -d api-gateway
```

### 数据库管理

```bash
# 连接数据库
docker exec -it econai-postgres psql -U econai -d econai

# 常用查询
SELECT count(*) FROM documents;           -- 文档总数
SELECT count(*) FROM analysis_tasks;      -- 任务总数
SELECT status, count(*) FROM analysis_tasks GROUP BY status;  -- 任务状态分布

# 备份数据库
docker exec econai-postgres pg_dump -U econai econai > backup_$(date +%Y%m%d).sql

# 恢复数据库
docker exec -i econai-postgres psql -U econai econai < backup_20260101.sql
```

### MinIO 文件管理

MinIO Console 地址：`http://<host>:9001`

- 用户名：`MINIO_ROOT_USER`（默认 `minioadmin`）
- 密码：`MINIO_ROOT_PASSWORD`

两个 Bucket：`econai-documents`（原始文档）、`econai-outputs`（生成的报告文件）。

### 日志查看

```bash
# 实时查看所有日志
./deploy/deploy.sh logs

# 查看最近 200 行
docker compose logs --tail=200 api-gateway

# 按时间过滤
docker compose logs --since 2026-01-01T00:00:00 orchestration-service

# 导出日志
docker compose logs > econai-logs-$(date +%Y%m%d).txt 2>&1
```

日志格式为 JSON，包含 `timestamp`、`level`、`logger`、`message`、`request_id` 等字段。

### Celery 任务管理

```bash
# 查看 document 队列
docker exec econai-redis redis-cli -a $REDIS_PASSWORD LLEN document

# 查看 orchestration 队列
docker exec econai-redis redis-cli -a $REDIS_PASSWORD LLEN orchestration

# 清空队列（谨慎！）
docker exec econai-redis redis-cli -a $REDIS_PASSWORD DEL document
```

---

## 5. 监控

### Prometheus 指标

- 地址：`http://<host>:9090`
- API Gateway 指标端点：`http://<host>:8000/metrics`
- 每个微服务暴露 `/metrics` 端点
- 数据保留期：30 天

### Grafana 仪表盘

- 地址：`http://<host>:3000`
- 默认用户名：`admin`
- 默认密码：`GRAFANA_ADMIN_PASSWORD`

### 关键监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| `http_requests_total` | API 请求总数 | - |
| `http_request_duration_seconds` | 请求延迟 | P95 > 5s |
| `celery_tasks_total` | 任务总数 | - |
| `celery_tasks_failed_total` | 失败任务数 | > 10/小时 |
| `postgres_connections_active` | 活跃数据库连接 | > 80% 最大连接数 |
| `redis_memory_used_bytes` | Redis 内存使用 | > 80% maxmemory |
| `milvus_search_latency_seconds` | 向量检索延迟 | P95 > 1s |

---

## 6. 备份策略

### 需要备份的数据

| 数据 | 位置 | 备份方式 | 频率 |
|------|------|----------|------|
| PostgreSQL | Docker Volume `econai-postgres-data` | `pg_dump` | 每日 |
| MinIO 文件 | Docker Volume `econai-minio-data` | `mc mirror` | 每日 |
| Redis 数据 | Docker Volume `econai-redis-data` | AOF 文件（默认开启） | 实时 |
| 配置文件 | `.env`、`nginx/` | Git 或文件复制 | 修改后 |

### 备份脚本示例

```bash
#!/bin/bash
# 保存为 /opt/econai/deploy/backup.sh
BACKUP_DIR=/backup/econai
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR/$DATE

# 备份 PostgreSQL
docker exec econai-postgres pg_dump -U econai econai > $BACKUP_DIR/$DATE/db.sql

# 备份 MinIO
docker run --rm --network econai-network \
  -v $BACKUP_DIR/$DATE:/backup \
  minio/mc:latest \
  mc mirror local/econai-documents /backup/documents

# 备份配置
cp .env $BACKUP_DIR/$DATE/.env

# 保留最近 30 天
find $BACKUP_DIR -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;
```

### 恢复步骤

```bash
# 1. 停止服务
./deploy/deploy.sh stop

# 2. 恢复数据库
docker compose up -d postgres
sleep 10
docker exec -i econai-postgres psql -U econai econai < backup/db.sql

# 3. 恢复 MinIO 文件
# 通过 MinIO Console 上传，或使用 mc 客户端

# 4. 启动服务
./deploy/deploy.sh start
```

---

## 7. 扩容与高可用

### 水平扩容

```bash
# 扩容 Celery Worker（增加并发处理能力）
docker compose up -d --scale celery-worker-document=3
docker compose up -d --scale celery-worker-orchestration=3
```

### 性能调优

关键配置项（`.env` 中调整）：

```bash
# PostgreSQL 连接池
# 根据并发量调整，默认 max_connections=100

# Redis maxmemory
REDIS_MAXMEMORY=4gb                        # 增大缓存空间

# Celery 并发数
CELERY_WORKER_CONCURRENCY=8               # 根据 CPU 核数调整

# Agent 超时
AGENT_TOOL_TIMEOUT_S=120                  # 复杂任务增大超时
TASK_TIMEOUT_MINUTES=60                   # 大文档分析增大

# 检索超时
SEARCH_TIMEOUT_MS=10000                   # 大规模知识库增大
```

### 生产环境注意事项

- 使用外部 PostgreSQL 集群代替 Docker 容器内的单实例
- Milvus 生产部署使用分布式模式（非 standalone）
- Nginx 前加负载均衡器（如 HAProxy）实现网关层高可用
- 日志使用 ELK/Loki 集中收集
- 定期清理 `llm_usage_logs` 和 `audit_logs` 表（建议保留 6 个月）

---

## 8. 故障处理

### 服务无法启动

```bash
# 1. 检查端口占用
ss -tlnp | grep -E "8000|8001|8002|8003|8004|8005|8006|8007|5432|6379"

# 2. 检查磁盘空间
df -h

# 3. 检查 Docker 日志
docker compose logs postgres
docker compose logs redis

# 4. 重新启动
./deploy/deploy.sh restart
```

### 数据库连接失败

```bash
# 检查 PostgreSQL 是否就绪
docker exec econai-postgres pg_isready -U econai

# 检查连接数
docker exec econai-postgres psql -U econai -c "SELECT count(*) FROM pg_stat_activity;"

# 重置连接
docker compose restart postgres
```

### LLM 调用失败

```bash
# 检查 LLM Router 日志
docker compose logs llm-router

# 检查 Claude API 密钥
grep ANTHROPIC_API_KEY .env

# 检查本地 LLM 连通性
curl -s http://<llm-server>:8000/v1/models

# 启用降级模式（Claude 不可达时自动切换本地 LLM）
# 确认 LLM_ROUTER_HOST 和 LOCAL_LLM_ENDPOINT 配置正确
```

### 任务卡在 running 状态

```bash
# 查看卡住的任务
docker exec econai-postgres psql -U econai -c \
  "SELECT id, title, status, started_at FROM analysis_tasks WHERE status='running' AND started_at < now() - interval '30 minutes';"

# 手动取消任务
docker exec econai-postgres psql -U econai -c \
  "UPDATE analysis_tasks SET status='failed', error_message='Manual timeout recovery' WHERE id='<task-id>';"

# 清空 Celery 队列中的旧任务
docker exec econai-redis redis-cli -a $REDIS_PASSWORD DEL orchestration
```

### Redis 内存不足

```bash
# 检查内存使用
docker exec econai-redis redis-cli -a $REDIS_PASSWORD INFO memory

# 手动清理过期缓存
docker exec econai-redis redis-cli -a $REDIS_PASSWORD MEMORY PURGE

# 增大 maxmemory（修改 .env 后重启）
REDIS_MAXMEMORY=4gb
./deploy/deploy.sh restart
```

---

## 9. 安全建议

### 必需操作

1. **修改所有默认密码**：`.env` 中所有带 `change_me` 后缀的密码
2. **JWT Secret**：使用 `openssl rand -hex 32` 生成强随机密钥
3. **TLS 证书**：生产环境必须使用 CA 签发的证书
4. **防火墙**：仅对外开放 80/443 端口，内部服务端口（8000-8007, 5432, 6379 等）仅宿主机访问
5. **API 限流**：根据实际用户量调整 `RATE_LIMIT_*` 参数

### 防火墙示例（iptables）

```bash
# 仅允许本机访问内部服务
iptables -A INPUT -p tcp --dport 8000:8007 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000:8007 -j DROP
iptables -A INPUT -p tcp --dport 5432 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 5432 -j DROP
```

### 审计日志保留

`audit_logs` 表默认保留 6 个月，可通过 `AUDIT_LOG_RETENTION_MONTHS` 调整。定期归档并清理过期记录。

---

## 10. 版本升级

```bash
# 1. 拉取新代码
git pull origin master

# 2. 检查 .env.template 是否有新增配置项
diff .env .env.template

# 3. 重新构建镜像
./deploy/deploy.sh build

# 4. 滚动重启服务
docker compose up -d --no-deps --build api-gateway
docker compose up -d --no-deps --build document-service
# ... 按依赖顺序逐个重启

# 5. 验证
./deploy/deploy.sh status
curl http://localhost:8000/health
```

---

## 快速参考

| 操作 | 命令 |
|------|------|
| 启动 | `./deploy/deploy.sh start` |
| 停止 | `./deploy/deploy.sh stop` |
| 重启 | `./deploy/deploy.sh restart` |
| 状态 | `./deploy/deploy.sh status` |
| 日志 | `./deploy/deploy.sh logs [service]` |
| 构建 | `./deploy/deploy.sh build` |
| 进入 PostgreSQL | `docker exec -it econai-postgres psql -U econai` |
| 进入 Redis | `docker exec -it econai-redis redis-cli -a <password>` |
| API 健康检查 | `curl http://localhost:8000/health` |
| Prometheus | `http://<host>:9090` |
| Grafana | `http://<host>:3000` |
| MinIO Console | `http://<host>:9001` |
# EconAI 运维手册

> 版本：v1.2 | 适用于 EconAI v1.2 完整部署

---

## 1. 系统架构概览

EconAI 由以下服务组成，部署在单台或多台服务器上：

| 组件 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| Nginx | `econai-nginx` | 80, 443 | 反向代理 + TLS 终结 |
| API Gateway | `econai-api-gateway` | 8000 | JWT 认证/RBAC/限流/审计 |
| Document Service | `econai-document-service` | 8001 | 文档上传/解析/分块/OCR |
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

EconAI 的 LLM Router 支持两种后端提供商：

- **Cloud（Anthropic Claude）**：走 `ClaudeAdapter`，直接调用 Anthropic Messages API
- **Local（vLLM / Ollama / OpenAI 兼容）**：走 `LocalAdapter`，通过 OpenAI-compatible `/v1/chat/completions` 接口调用

#### 3.4.1 使用 Ollama（推荐本地开发）

**硬件要求**：至少 8 GB RAM（7B 模型），推荐 16 GB 以上。

**1. 安装 Ollama**

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# 验证安装
ollama --version
```

**2. 启动 Ollama 并拉取模型**

```bash
# 启动服务（macOS 可通过 GUI 启动，或命令行）
ollama serve &

# 拉取模型（以 qwen2.5-coder:7b 为例）
ollama pull qwen2.5-coder:7b

# 验证模型可用
ollama list
curl http://localhost:11434/v1/models
```

**3. 修改 EconAI 配置**

编辑 `.env`，设置 Ollama 的 OpenAI 兼容端点：

```bash
# .env 中修改以下两项
LOCAL_LLM_ENDPOINT=http://localhost:11434/v1
LOCAL_LLM_DEFAULT_MODEL=qwen2.5-coder:7b
```

编辑 `services/llm-router/models.yaml`，注册 Ollama 模型并设为默认本地模型：

```yaml
# models.yaml
models:
  - id: "auto"
    provider: "auto"
    # ... 保持不变 ...

  - id: "claude-sonnet-4-6"
    provider: "anthropic"
    # ... 保持不变 ...

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

> **注意**：`provider` 字段只要不是 `"anthropic"` 就会走 `LocalAdapter`（OpenAI 兼容协议）。  
> `LocalAdapter` 会自动去掉模型 ID 中的 `local:` 前缀再发给 Ollama。

**4. 验证连接**

```bash
# 检查 LLM Router 是否识别到新模型
curl http://localhost:8004/internal/llm/models | python3 -m json.tool

# 发送一次实际对话测试
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

**5. 路由行为说明**

| `sensitivity` | 路由目标 | 对应模型 |
|---------------|----------|----------|
| `"high"` | 本地模型（数据敏感，不出网） | `default_local` |
| `"low"` | 云端模型（能力强，低敏感任务） | `default_cloud` |

云端模型不可达时，`sensitivity=low` 的请求会自动降级到本地模型。

#### 3.4.2 使用 vLLM（高性能生产环境）

```bash
# .env
LOCAL_LLM_ENDPOINT=http://<vllm-server-ip>:8000/v1
LOCAL_LLM_DEFAULT_MODEL=qwen3-72b

# models.yaml 中注册模型
- id: "local:qwen3-72b"
  provider: "vllm"
  type: "local"
  description: "Qwen3 72B via vLLM"
```

#### 3.4.3 不使用本地 LLM

如果只使用 Anthropic Claude API，确保 `.env` 中：

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx         # 填写有效的 API Key
LOCAL_LLM_ENDPOINT=                     # 留空
```

`CLOUD_LLM_DEFAULT_MODEL` 默认使用 `claude-sonnet-4-6`。  
没有本地 LLM 时，所有 `sensitivity=high` 请求将失败（建议在调用侧统一使用 `sensitivity=low`）。

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

# 检查本地 LLM 连通性（Ollama 端口 11434，vLLM 端口 8000）
curl -s http://localhost:11434/v1/models      # Ollama
curl -s http://<llm-server>:8000/v1/models   # vLLM

# 验证 LLM Router 本身可达
curl http://localhost:8004/health

# 验证 LLM Router 已注册模型
curl http://localhost:8004/internal/llm/models

# 启用降级模式（Claude 不可达时自动切换本地 LLM）
# 确认 LLM_ROUTER_HOST 和 LOCAL_LLM_ENDPOINT 配置正确
```

**Ollama 特定问题排查**：

```bash
# Ollama 是否在运行
pgrep -a ollama

# Ollama 服务状态（macOS）
launchctl list | grep ollama

# 模型是否已拉取
ollama list

# 重启 Ollama
killall ollama && ollama serve &
```

**本地 LLM 超时**：如果模型响应慢，增大 `.env` 中的 `LLM_REQUEST_TIMEOUT_S`（默认 120 秒）。 7B 模型在 CPU 上的首 token 延迟可能达 10-30 秒。<｜end▁of▁thinking｜>-

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="read_file">
<｜｜DSML｜｜parameter name="filePath" string="true">/Users/onetreehill/EconAI/doc/operation.md

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

## 11. 完全关闭与磁盘清理

以下步骤将停止所有 Docker 服务和主机级进程，并清理磁盘空间。

### 11.1 停止所有服务

```bash
# 1. 停止 Docker Compose 管理的所有服务
./deploy/deploy.sh stop

# 预期输出：18 个容器依次停止并移除网络
```

### 11.2 停止主机级进程

如果使用 Ollama（非 Docker 方式运行）：

```bash
# 检查 Ollama 是否在运行
pgrep -a ollama

# 停止 Ollama
killall ollama

# 或通过 launchctl（macOS）
launchctl unload ~/Library/LaunchAgents/com.ollama.ollama.plist 2>/dev/null
```

如果手动启动了 LLM Router（uvicorn）：

```bash
# 查找并终止占用 8004 端口的进程
lsof -i :8004 -P -n -t | xargs kill
```

### 11.3 查看磁盘占用

```bash
# 查看 Docker 磁盘使用概况
docker system df

# 列出所有镜像及大小
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# 列出所有 Docker 卷
docker volume ls
```

### 11.4 删除 Docker 镜像（释放磁盘空间）

> **注意**：删除后再次启动需要重新拉取镜像，需联网且耗时数分钟。

```bash
# 删除单个镜像
docker rmi <image-name>:<tag>

# 删除所有未使用的镜像
docker image prune -a

# 删除所有镜像（谨慎！）
docker rmi $(docker images -q)
```

典型可删除的 EconAI 基础设施镜像：

| 镜像 | 大小 | 说明 |
|------|------|------|
| `milvusdb/milvus:v2.4.0` | ~2 GB | Milvus 向量数据库 |
| `postgres:16-alpine` | ~390 MB | PostgreSQL |
| `quay.io/coreos/etcd:v3.5.5` | ~260 MB | Milvus 元数据协调 |
| `minio/minio:latest` | ~230 MB | 对象存储 |
| `minio/mc:latest` | ~110 MB | MinIO 客户端 |
| `redis:7-alpine` | ~60 MB | Redis |

### 11.5 清理 Docker 卷（可选，将删除所有数据）

> **危险操作**：卷中包含数据库、向量索引和上传文件。确认不需要数据后再执行。

```bash
# 查看 EconAI 相关卷
docker volume ls --filter "name=econai"

# 删除所有 EconAI 卷（数据不可恢复！）
docker volume rm econai-etcd-data econai-milvus-data \
                econai-minio-data econai-postgres-data \
                econai-redis-data

# 或删除所有未使用的卷
docker volume prune
```

### 11.6 完全清理（一键）

```bash
# 停止并清理所有 EconAI 相关资源
./deploy/deploy.sh stop
docker image prune -a --force
docker volume prune --force

# 如果是开发环境，确认后执行
docker system prune -a --volumes --force
```

### 11.7 重新启动

```bash
# 如果需要重新启动系统（镜像会自动拉取）
./deploy/deploy.sh start

# 如果使用 Ollama
ollama serve &
ollama pull qwen2.5-coder:7b
```

---

## 12. 配置排错经验

### 12.1 JWT Secret 不匹配 —— pydantic-settings `env_prefix` 陷阱

**现象**：所有经过 API Gateway 的请求返回 `401 AUTH_TOKEN_INVALID`，但手工启动时正常。

**根因**：`api-gateway/app/config.py` 和 `user-service/app/config.py` 都使用了 `pydantic-settings` 的 `env_prefix`：

```python
# api-gateway/app/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="API_GATEWAY_")

# user-service/app/config.py
class UserServiceSettings(AppSettings):
    model_config = SettingsConfigDict(env_prefix="USER_SERVICE_")
```

`docker-compose.yml` 中设置的是不加前缀的通用变量名：

```yaml
# ❌ 错误 —— 会被两个服务的 env_prefix 双双忽略
- JWT_SECRET=econai_jwt_secret_change_me_min_32_chars
- JWT_ALGORITHM=HS256
```

两个服务的 `JWT_SECRET` 字段都回退到各自的硬编码默认值且不相同，导致 user-service 签发的 JWT 被 api-gateway 拒绝。

**修复**：在 `docker-compose.yml` 中为每个服务使用带前缀的环境变量：

```yaml
# ✅ 正确 —— api-gateway 环境变量
- API_GATEWAY_JWT_SECRET=${JWT_SECRET:-econai_jwt_secret_change_me_min_32_chars}
- API_GATEWAY_JWT_ALGORITHM=${JWT_ALGORITHM:-HS256}
- API_GATEWAY_JWT_ACCESS_EXPIRE_MINUTES=${JWT_ACCESS_EXPIRE_MINUTES:-120}
- API_GATEWAY_JWT_REFRESH_EXPIRE_HOURS=${JWT_REFRESH_EXPIRE_HOURS:-24}

# ✅ 正确 —— user-service 环境变量
- USER_SERVICE_JWT_SECRET=${JWT_SECRET:-econai_jwt_secret_change_me_min_32_chars}
- USER_SERVICE_JWT_ALGORITHM=${JWT_ALGORITHM:-HS256}
- USER_SERVICE_JWT_ACCESS_EXPIRE_MINUTES=${JWT_ACCESS_EXPIRE_MINUTES:-120}
- USER_SERVICE_JWT_REFRESH_EXPIRE_HOURS=${JWT_REFRESH_EXPIRE_HOURS:-24}
```

**验证方法**：

```bash
docker exec econai-api-gateway python -c "from app.config import settings; print(settings.jwt_secret)"
docker exec econai-user-service python -c "from app.config import settings; print(settings.jwt_secret)"
# 两个输出必须完全一致
```

### 12.2 Ollama 容器内不可达 —— `localhost` vs `host.docker.internal`

**现象**：LLM Router 调用本地 Ollama 返回 `503 Circuit breaker open for local`，但宿主机 `curl http://localhost:11434/api/tags` 正常。

**根因**：`docker-compose.yml` 或 `.env` 中 `LOCAL_LLM_ENDPOINT` 使用了 `http://localhost:11434/v1`。在容器内，`localhost` 指向容器自身，不是宿主机。

**修复**：将 Ollama 端点改为 `host.docker.internal`：

```bash
# .env
LOCAL_LLM_ENDPOINT=http://host.docker.internal:11434/v1
```

```yaml
# docker-compose.yml
- LOCAL_LLM_ENDPOINT=${LOCAL_LLM_ENDPOINT:-http://host.docker.internal:11434/v1}
```

> **注意**：修改 `.env` 后必须用 `--force-recreate` 重建容器，`restart` 不会重载环境变量。  
> ```bash
> docker compose up -d --no-deps --force-recreate llm-router
> ```

### 12.3 集成测试数据隔离

**现象**：全量跑测试时偶现 `assert 404 == 200` 之类的失败，但单独跑同一模块的测试全部通过。

**根因**：`test_integration_flows.py` 先执行创建用户和项目，`test_m8_*` 模块假设数据库是干净的状态（如 `list_users` 期望分页首页包含刚创建的用户），被前面的测试数据污染。

**排查**：检查数据库中是否有累积的孤儿测试数据：

```bash
docker exec econai-postgres psql -U econai -d econai -c \
  "SELECT username FROM users WHERE username LIKE 'lifecycle_%' OR username LIKE 'test%';"
docker exec econai-postgres psql -U econai -d econai -c \
  "SELECT name FROM projects ORDER BY created_at DESC LIMIT 20;"
```

**清理**：

```bash
docker exec econai-postgres psql -U econai -d econai -c \
  "DELETE FROM projects; DELETE FROM users WHERE username != 'admin';"
```

> **建议**：在 `conftest.py` 中添加 session 级 fixture 在测试开始时自动清理，或调整 pytest 执行顺序（`test_m8_*` 在 `test_integration_flows` 之前跑）。

### 12.4 重建容器 vs 重启容器

修改 `docker-compose.yml` 或 `.env` 后，`docker compose restart` **不会**重载环境变量。必须使用 `--force-recreate`：

```bash
# ❌ 无效 —— 环境变量不更新
docker compose restart service-name

# ✅ 正确 —— 重新创建容器，环境变量生效
docker compose up -d --no-deps --force-recreate service-name
```

---

## 13. Dockerfile 构建规范

EconAI 所有服务 Dockerfile 遵循统一的构建模式。以下四个关键要素是多次踩坑后沉淀的硬性规范，修改 Dockerfile 时必须遵守：

### 13.1 不使用 BuildKit bind mount

```dockerfile
# ❌ 错误（Colima / 旧版 Docker daemon 不兼容，直接卡死）
RUN --mount=type=bind,source=shared,target=/shared ...

# ✅ 正确（所有 Docker 环境通用）
COPY shared /shared
```

**原因**：`--mount=type=bind` 需要 Docker daemon 启用 BuildKit。Colima 默认使用 legacy builder，遇到不认识的 `--mount` 语法会直接 hang。而 `COPY` 在所有环境通用，shared 只有 8 个 `.py` 文件，空间影响可忽略。

### 13.2 `shared/pyproject.toml` 使用 `where = ["."]`

```toml
# ❌ 错误（容器内 ".." 解析为 /，setuptools 扫描整个 Linux 根文件系统）
[tool.setuptools.packages.find]
where = [".."]
include = ["shared"]

# ✅ 正确（只在 pyproject.toml 所在目录搜索，本地和容器行为一致）
[tool.setuptools.packages.find]
where = ["."]
include = ["shared"]
```

**原因**：`where = [".."]` 在宿主机上解析为项目根目录（~20 个目录，秒完成），但在容器 `/shared/pyproject.toml` 中解析为 `/`（根文件系统），setuptools 会递归扫描 `/proc`、`/sys`、`/usr` 等数万个目录，永远跑不完。

### 13.3 不用 `--only-binary :all:`

```dockerfile
# ❌ 错误（禁止所有源码安装，包括自己的 econai-shared 和 `uv pip install .`）
RUN uv pip install --only-binary :all: --system .

# ✅ 正确（所有依赖已有 ARM64 预编译 wheel）
RUN uv pip install --system .
```

**原因**：`--only-binary :all:` 源自早期 `python-ldap` 在 ARM64 下无 wheel 的临时方案。现已换成纯 Python 的 `ldap3`，所有依赖都有预编译 wheel，无需此限制。

### 13.4 用 `sed` 将相对路径改为绝对路径

```dockerfile
# 单阶段 service（7 个）
RUN sed -i 's|path = "../../shared"|path = "/shared"|g' pyproject.toml && \
    uv pip install --system .

# api-gateway builder 阶段
RUN sed -i 's|path = "../shared"|path = "/shared"|g' pyproject.toml && \
    uv pip install --system --no-cache .
```

**原因**：服务 `pyproject.toml` 中的 `[tool.uv.sources]` 使用相对路径指向 shared：
```toml
econai-shared = { path = "../../shared" }
```
`uv pip install .` 会强制解析此路径。从 `/app/` 计算 `../../shared` 逃出基目录，uv 直接报错。先用 `sed` 改成容器内绝对路径 `/shared` 即可让 uv 正常解析。

---

## 14. 变更记录

### v1.1 (2026-05-24) — 项目组成员管理优化

**问题**：系统管理员在 `/admin/groups` 管理成员时，添加成员需要手动输入用户 UUID，不直观；且成员列表未展示。

**改动**：

| 组件 | 变更内容 |
|------|----------|
| `user-service` | 新增 `GET /api/admin/groups/{id}/members` 列出成员（含用户名/显示名称/角色）；新增 `GET /api/admin/groups/{id}/non-members?q=` 搜索非成员用户 |
| 前端 `GroupManagement` | 成员管理弹窗重构：搜索式 `Select` 代替 UUID 输入框；表格展示当前成员列表；支持移除成员 |
| 测试 `test_m8_groups.py` | 新增 `test_list_members`、`test_list_non_members`、`test_non_members_search` |

**影响**：仅影响 `user-service` 和前端，无需数据库迁移或配置变更，重启服务即可生效。

### v1.2 (2026-05-25) — 多格式文档上传与 OCR 图片识别增强

**问题**：系统仅支持 `.txt`, `.md`, `.csv` 等少量常用格式的上传和解析，无法处理 Microsoft Office 全系列文档及图片中嵌入文字的识别。

**改动**：

| 组件 | 变更内容 |
|------|----------|
| `frontend` | KB 集成测试扩展至 19 种文件扩展名：PDF、Word (.docx/.doc)、Excel (.xlsx/.xls/.csv)、PowerPoint (.pptx/.ppt)、图片 (.png/.jpg/.jpeg/.tiff/.bmp)、邮件 (.eml)、网页 (.html/.mhtml/.mht)、文本 (.txt/.md) |
| `document-service/image_extractor.py` | **新增**共享图片提取 + OCR 核心模块，提供 `ocr_image_bytes`、`extract_images_from_pdf`、`extract_images_from_docx`、`extract_images_from_pptx`、`extract_images_from_html` 五个通用函数 |
| `document-service/models.py` | `ParsedContent` 新增 `ocr_images` 字段，记录每次 OCR 的审计追踪（页码、图片索引、OCR 文本、格式、尺寸） |
| `document-service/pdf_parser.py` | `parse()` 中集成 `extract_images_from_pdf`，OCR 结果自动追加到对应页面内容 |
| `document-service/word_parser.py` | `parse()` 中集成 `extract_images_from_docx`，OCR 结果追加到文档全文中 |
| `document-service/ppt_parser.py` | `parse()` 中集成 `extract_images_from_pptx`，OCR 结果追加到对应幻灯片 |
| `document-service/html_parser.py` | `parse()` 中集成 `extract_images_from_html`，OCR data-URI 内嵌图片 |
| `document-service/ocr_processor.py` | `_run_tesseract()` 重构为委托 `image_extractor.ocr_image_bytes()`，消除代码重复 |
| `document-service/pyproject.toml` | 新增依赖 `pytesseract>=0.3` |
| `document-service/tests/test_image_extraction.py` | **新增** 24 个测试用例覆盖 OCR 基础功能、PDF/DOCX/PPTX/HTML 图片提取、解析器 ocr_images 字段、内容增强验证 |

**新增配置项**：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `OCR_LANGUAGE` | `chi_sim+eng` | Tesseract OCR 语言包（已有，本次增强使用） |

**影响**：需在 document-service 容器中安装 `tesseract-ocr` 及对应语言包（`tesseract-ocr-chi-sim`、`tesseract-ocr`）。Dockerfile 中已添加相应 `apt-get` 安装步骤。升级后需重建 document-service 镜像：`docker compose build --no-cache document-service && docker compose up -d document-service`。

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
| 查看磁盘占用 | `docker system df` |
| 删除所有镜像 | `docker rmi $(docker images -q)` |
| 清理未使用资源 | `docker system prune -a` |
| 进入 PostgreSQL | `docker exec -it econai-postgres psql -U econai` |
| 进入 Redis | `docker exec -it econai-redis redis-cli -a <password>` |
| API 健康检查 | `curl http://localhost:8000/health` |
| Prometheus | `http://<host>:9090` |
| Grafana | `http://<host>:3000` |
| MinIO Console | `http://<host>:9001` |
# EconAI 开发环境手动启动指南

> 版本：v1.2 | 日期：2026-05-23

---

## 1. 前提条件

### 已安装的软件

| 软件 | 最低版本 | 用途 |
|------|----------|------|
| Python | 3.12+ | 后端运行环境 |
| uv | 0.5+ | Python 包管理 |
| Node.js | 18+ | 前端运行环境 |
| npm | 9+ | 前端包管理 |
| Docker | 24.0+ | 基础设施容器（PostgreSQL/Redis/Milvus/MinIO） |
| Docker Compose | 2.20+ | 编排基础设施容器 |

### ARM Mac (Apple Silicon) 注意事项

在 M1/M2/M3/M4 芯片的 Mac 上，Milvus 官方镜像存在已知兼容性问题。本项目已通过以下调整验证通过：

- **不挂载自定义 `milvus.yaml`**（让 Milvus standalone 使用内置默认配置，避免集群/单机端口冲突）
- **MinIO 凭证统一为 `minioadmin`**（Milvus 默认信任 `minioadmin` 的用户名密码）
- **Milvus 健康检查 `start_period` 延长到 90s**（ARM 下初始化较慢）

### 安装依赖

```bash
cd /Users/onetreehill/EconAI

# 为每个后端服务安装 Python 依赖
for dir in api-gateway services/*/; do
    echo "=== Installing deps for $dir ==="
    (cd "$dir" && uv sync)
done

# 安装前端依赖
cd frontend && npm install
```

---

## 2. 启动顺序

### 依赖关系回顾

```
第一波：基础设施 (Docker)
        postgres + redis + etcd + minio + milvus

第二波：无业务依赖的服务（可并行）
        user-service (8007) + llm-router (8004) + citation-service (8005)

第三波：数据处理服务
        document-service (8001) + output-service (8006)

第四波：知识库服务
        kb-service (8002)

第五波：核心编排
        orchestration-service (8003)

第六波：入口层
        api-gateway (8000)

最后一波：前端
        frontend (5173)
```

### 逐步启动

#### 步骤1：基础设施（终端1）

```bash
cd /Users/onetreehill/EconAI
docker compose up -d postgres redis etcd minio minio-init milvus

# 等待所有基础设施就绪（Milvus 在 ARM 上可能需要 90s+）
docker compose ps | grep -E "postgres|redis|milvus|minio" | grep -v "minio-init"
# 应全部显示 "healthy"
```

> **注意**：`minio-init` 容器执行完后会自动停止（`restart: "no"`），不要担心其 Exited 状态。

#### 步骤2：无依赖服务（终端2、3、4）

```bash
# 终端2：user-service
cd /Users/onetreehill/EconAI/services/user-service
uv run uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload

# 终端3：llm-router
cd /Users/onetreehill/EconAI/services/llm-router
uv run uvicorn llm_router.app:app --host 0.0.0.0 --port 8004 --reload

# 终端4：citation-service
cd /Users/onetreehill/EconAI/services/citation-service
uv run uvicorn citation_service.app:app --host 0.0.0.0 --port 8005 --reload
```

#### 步骤3：数据处理服务（终端5、6）

```bash
# 终端5：document-service + Celery worker
cd /Users/onetreehill/EconAI/services/document-service
uv run uvicorn document_service.app:app --host 0.0.0.0 --port 8001 --reload
# 另开一个终端tab启动 Celery worker：
cd /Users/onetreehill/EconAI/services/document-service
uv run celery -A document_service.celery_app worker --loglevel=INFO --concurrency=2 --queues=document

# 终端6：output-service
cd /Users/onetreehill/EconAI/services/output-service
uv run uvicorn output_service.app:app --host 0.0.0.0 --port 8006 --reload
```

#### 步骤4：知识库服务（终端7）

```bash
cd /Users/onetreehill/EconAI/services/kb-service
uv run uvicorn kb_service.app:app --host 0.0.0.0 --port 8002 --reload
```

#### 步骤5：编排服务（终端8）

```bash
cd /Users/onetreehill/EconAI/services/orchestration-service
uv run uvicorn orchestration_service.app:app --host 0.0.0.0 --port 8003 --reload
# Celery Agent worker（另开tab）：
cd /Users/onetreehill/EconAI/services/orchestration-service
uv run celery -A orchestration_service.celery_app worker --loglevel=INFO --concurrency=4 --queues=orchestration
```

#### 步骤6：API 网关（终端9）

**重要**：手动启动 api-gateway 时必须显式传入 Redis 密码和各后端服务的 localhost 地址。默认配置中的 Docker 容器名（如 `http://user-service:8007`）仅适用于 Docker Compose 环境。

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

> 如果你修改过 `.env` 中的 `REDIS_PASSWORD`，请相应替换上面 URL 中的密码部分 `econai_redis_change_me`。

#### 步骤7：前端（终端10）

```bash
cd /Users/onetreehill/EconAI/frontend
npm run dev
```

浏览器访问 `http://localhost:5173`。

---

## 3. 模块路径速查

| 服务 | 目录 | uvicorn 模块路径 | 端口 | 特殊启动参数 |
|------|------|------------------|------|-------------|
| API 网关 | `api-gateway/` | `app.main:app` | 8000 | 需设 Redis URL + 所有后端 localhost 地址 |
| 文档服务 | `services/document-service/` | `document_service.app:app` | 8001 | 另需 Celery worker |
| 知识库 | `services/kb-service/` | `kb_service.app:app` | 8002 | 依赖 Milvus 先就绪 |
| 编排服务 | `services/orchestration-service/` | `orchestration_service.app:app` | 8003 | 另需 Celery worker |
| LLM 路由 | `services/llm-router/` | `llm_router.app:app` | 8004 | — |
| 引用服务 | `services/citation-service/` | `citation_service.app:app` | 8005 | — |
| 输出服务 | `services/output-service/` | `output_service.app:app` | 8006 | — |
| 用户服务 | `services/user-service/` | `app.main:app` | 8007 | — |

---

## 4. 验证

```bash
# 一键验证脚本
for port in 8000 8001 8002 8003 8004 8005 8006 8007; do
  echo -n "port $port: "
  curl -s http://localhost:$port/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','FAIL'), '-', d.get('service','?'))" 2>/dev/null || echo "FAIL"
done

# 前端
open http://localhost:5173
```

预期全部返回 `healthy` 或 `ok`。

---

## 5. 常见问题

### 端口被占用

```bash
lsof -ti:8000 | xargs kill -9   # 替换端口号
```

### 数据库连接失败

确认 PostgreSQL 已启动并健康：
```bash
docker compose ps postgres
docker exec econai-postgres pg_isready -U econai
```

### Celery worker 无法连接 Redis

```bash
docker exec econai-redis redis-cli -a $(grep REDIS_PASSWORD .env | cut -d= -f2) ping
```

### Claude API 未配置

如果不使用 Claude API，LLM Router 会降级到本地 LLM。确保 `.env` 中：
```bash
LOCAL_LLM_ENDPOINT=http://localhost:8000/v1   # vLLM/Ollama 地址
```

如果使用 Ollama 作为 Claude 兼容代理，需额外配置：
```bash
ANTHROPIC_API_BASE_URL=http://host.docker.internal:11434
```

> 注意：Docker 容器内 `localhost` 指向容器自身。如需从容器访问宿主机服务，必须使用 `host.docker.internal`。

### 前端 API 请求被 CORS 阻止

前端 Vite dev server 已配置 proxy，`/api` 开头的请求会被代理到 `localhost:8000`。确保 API 网关在 8000 端口运行。

### Milvus 无法启动（ARM Mac 常见）

**现象**：`docker compose ps milvus` 显示 `Exited (134)` 或反复重启

**根因**：自定义 `milvus.yaml` 与 `milvus run standalone` 冲突，集群模式端口配置导致多个组件（rootcoord、datacoord、querycoord）争抢同一端口。

**解决方案**（已在 `docker-compose.yml` 中应用）：

1. 不挂载自定义 `milvus.yaml`（让 Milvus 使用内置 standalone 默认配置）
2. MinIO 访问密钥与环境变量统一为 `minioadmin`
3. 健康检查 `start_period` 至少 90s

验证方法：
```bash
# 确认宿主机 19530 端口没有被残留进程占用
lsof -i :19530
# 如果被占用，杀掉残留进程
lsof -ti:19530 | xargs kill -9

# 重建 Milvus
docker compose stop milvus
docker compose rm -f milvus
docker volume rm econai_milvus-data   # 清空旧数据（可选）
docker compose up -d milvus
# 等待约 90s
docker compose ps milvus
```

### api-gateway 启动后 /health 返回 SYS_INTERNAL_ERROR

**现象**：`curl http://localhost:8000/health` 返回 Redis `Authentication required` 错误

**根因**：api-gateway 的默认 `redis_url = "redis://localhost:6379/0"` 不含密码，而 Docker Redis 已开启 `requirepass` 认证。

**解决方案**：启动时设置环境变量：
```bash
API_GATEWAY_REDIS_URL="redis://:${REDIS_PASSWORD}:<your-password>@localhost:6379/0"
```
（默认密码见 `.env` 中 `REDIS_PASSWORD`）

### minio-init 反复重启

**现象**：`minio-init` 容器 Executed 后又被 Docker 重新拉起

**根因**：`minio-init` 继承了 `*common-service` 的 `restart: unless-stopped`，脚本成功退出后 Docker 反复重启。

**解决方案**（已在 `docker-compose.yml` 中应用）：在 `minio-init` 服务上覆盖为 `restart: "no"`。

### 前端登录失败

**现象**：前端页面输入 admin/Admin@123456，提示 `Backend service for /api/auth/login is unavailable`

**可能原因**：

1. **api-gateway 后端地址错误**——用户看到 `HTTP 503`：
   - 检查 api-gateway 日志是否有 `Failed to proxy to http://user-service:8007: [Errno 8] nodename nor servname provided`
   - **修复**：重启 api-gateway 并传入所有 `localhost` 地址（见步骤6的完整启动命令）

2. **api-gateway Redis 未连接**——用户看到 `HTTP 500` 且日志有 `Authentication required`：
   - **修复**：设置 `API_GATEWAY_REDIS_URL` 包含密码

3. **审计日志写入失败**——用户看到 `HTTP 500` 且日志有 `DatatypeMismatchError` 或 `UndefinedColumnError`：
   - 如果报 `column "resource_id" is of type uuid`：确认 `audit_log` 模型和 DB schema 均已修复（已在代码中生效）
   - 如果报 `column users.ldap_dn does not exist`：执行 `docker exec econai-postgres psql -U econai -d econai -c "ALTER TABLE users ADD COLUMN IF NOT EXISTS ldap_dn VARCHAR(255);"`

4. **密码哈希不匹配**——用户看到 `AUTH_INVALID_CREDENTIALS`：
   - 重新生成 admin 密码：在 `services/user-service` 目录执行 `uv run python3 -c "import bcrypt; print(bcrypt.hashpw(b'Admin@123456', bcrypt.gensalt(rounds=12)).decode())"`
   - 更新数据库：`docker exec econai-postgres psql -U econai -d econai -c "UPDATE users SET hashed_password = '<新哈希>' WHERE username = 'admin';"`

---

## 6. Docker Compose 关键配置说明

以下是与默认配置的重要差异点（均在 `docker-compose.yml` 中）：

```yaml
# minio-init: 禁止重启（一次性初始化任务）
minio-init:
  restart: "no"     # 覆盖 *common-service 的 unless-stopped

# milvus: ARM Mac 兼容配置
milvus:
  image: milvusdb/milvus:v2.4.0
  environment:
    # 凭证必须与 MinIO root 用户一致
    MINIO_ACCESS_KEY_ID: ${MINIO_ROOT_USER:-minioadmin}
    MINIO_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD:-minioadmin_change_me}
  # 不挂载自定义 milvus.yaml（避免端口冲突）
  volumes:
    - milvus-data:/var/lib/milvus
  healthcheck:
    start_period: 90s    # ARM 下初始化较慢，需延长等待
```

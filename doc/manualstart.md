# EconAI 开发环境手动启动指南

> 版本：v1.0 | 日期：2026-05-20

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

# 等待所有基础设施就绪
docker compose ps | grep -E "postgres|redis|milvus|minio" | grep -v "minio-init"
# 应全部显示 "healthy"
```

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

```bash
cd /Users/onetreehill/EconAI/api-gateway
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 步骤7：前端（终端10）

```bash
cd /Users/onetreehill/EconAI/frontend
npm run dev
```

浏览器访问 `http://localhost:5173`。

---

## 3. 模块路径速查

| 服务 | 目录 | uvicorn 模块路径 | 端口 |
|------|------|------------------|------|
| API 网关 | `api-gateway/` | `app.main:app` | 8000 |
| 文档服务 | `services/document-service/` | `document_service.app:app` | 8001 |
| 知识库 | `services/kb-service/` | `kb_service.app:app` | 8002 |
| 编排服务 | `services/orchestration-service/` | `orchestration_service.app:app` | 8003 |
| LLM 路由 | `services/llm-router/` | `llm_router.app:app` | 8004 |
| 引用服务 | `services/citation-service/` | `citation_service.app:app` | 8005 |
| 输出服务 | `services/output-service/` | `output_service.app:app` | 8006 |
| 用户服务 | `services/user-service/` | `app.main:app` | 8007 |

---

## 4. 验证

```bash
# 健康检查
curl -s http://localhost:8000/health | jq   # API网关
curl -s http://localhost:8001/health | jq   # 文档服务
curl -s http://localhost:8002/health | jq   # 知识库
curl -s http://localhost:8003/health | jq   # 编排服务
curl -s http://localhost:8004/health | jq   # LLM路由
curl -s http://localhost:8005/health | jq   # 引用服务
curl -s http://localhost:8006/health | jq   # 输出服务
curl -s http://localhost:8007/health | jq   # 用户服务

# 前端
open http://localhost:5173
```

预期全部返回 `{"status":"healthy"}`。

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

### 前端 API 请求被 CORS 阻止

前端 Vite dev server 已配置 proxy，`/api` 开头的请求会被代理到 `localhost:8000`。确保 API 网关在 8000 端口运行。
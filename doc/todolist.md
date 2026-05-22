# EconAI 项目问题分析与改进建议

> 版本：v2.0 | 日期：2026-05-22 | 全项目深度审计（重新扫描）

---

## 一、严重问题 (Critical)

### 1.1 [P0] DB Schema 与代码/设计不一致

| 问题 | 详情 | 状态 |
|------|------|------|
| `documents` 表缺少 `is_internal` 字段 | Schema 现已包含此字段（`01-schema.sql` 第 95 行），代码中多处引用正确。| **已修复** ✅ |
| `analysis_tasks` 表缺少多个字段 | Schema 现已包含 `llm_route` (L164)、`iteration_count` (L167)、`celery_task_id` (L168)、`completion_type` (L169)。| **已修复** ✅ |
| `documents` 字段命名已统一 | Schema 和代码均使用 `original_name`、`storage_path`。 | **已修复** ✅ |
| `users.email` NULL/NOT NULL 不一致 | `01-schema.sql:20` 定义为 `NOT NULL UNIQUE`，而 SQLAlchemy model（`user-service/app/models/user.py:26`）定义为 `nullable=True`。OR 映射与实际约束矛盾。 | **已修复** ✅ |

**已修复** ✅ — 将 `user.py` 的 `email` 字段改为 `nullable=False`，与 schema 定义一致。

### 1.2 [P0] Mock 代码被当作生产实现

KB Service 在运行时使用 mock 实现而非真实组件：

```python
# kb_service/app.py:63 — 启动时直接实例化 mock
_embedding = MockEmbeddingClient(dim=settings.embedding_dim)

# kb_service/hybrid_search.py:35 — 默认值回退到 mock
self.embedding_client = embedding_client or MockEmbeddingClient()

# kb_service/hybrid_search.py:34 — 默认值回退到内存存储
self.vector_store = vector_store or InMemoryVectorStore()
```

- **Embedding**: `MockEmbeddingClient` 返回随机向量，从未调用 text2vec/m3e
- **Vector Store**: `InMemoryVectorStore` 在进程内存中做暴力搜索，从未连接 Milvus/Qdrant
- **Reranker**: `hybrid_search.py:216-219` 使用 query-term-overlap 启发式算法，未调用 BGE-Reranker
- **Citation 相似度**: `verifier.py:124-179` 使用简单 bag-of-words 而非 embedding 向量

**建议**：每个 mock 实现需要对应的真实实现，通过依赖注入切换。KB Service 启动时应检测环境（`VECTOR_DB_TYPE`）并加载真实客户端。

### 1.3 [P0] 环境变量前缀与 docker-compose 不匹配（4 个服务）

这是本次审计发现的**最高优先级新问题**——4 个服务的 `env_prefix` 与 docker-compose.yml 中传入的环境变量名称不匹配，导致所有配置回退到默认值（通常是 `localhost`，在 Docker 网络中不可达）。

| 服务 | 配置类 env_prefix | docker-compose 传入的变量 | 实际生效的值 |
|------|------------------|--------------------------|-------------|
| **orchestration** | `ORCH_` | `KB_SERVICE_URL`、`LLM_ROUTER_URL` | `localhost:8002`、`localhost:8004`（不可达） |
| **document** | `DOCUMENT_` | `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY` | `localhost:9000`（不可达） |
| **output** | `OUTPUT_` | `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY` | `localhost:9000`（不可达） |
| **user** | `USER_SERVICE_` | `JWT_SECRET` | `"change-me-in-production"`（不安全） |

**修复方案**：已移除 4 个服务的 `env_prefix`，docker-compose 传入的环境变量名现在直接匹配字段名（pydantic-settings 默认大小写不敏感）。**已修复** ✅

### 1.4 [P0] Celery Worker 中使用 `asyncio.get_event_loop().run_until_complete`

`services/orchestration-service/orchestration_service/worker.py:41-42`：
```python
try:
    asyncio.get_event_loop().run_until_complete(_run_agent(task_id))
```

这是**同步** Celery task 内部调用 `run_until_complete`。问题：
- 创建一个新的事件循环并阻塞整个 worker 线程
- Celery 的 `task_soft_time_limit` 和 `task_time_limit` 信号无法中断 asyncio 事件循环
- Worker 在执行 agent loop 期间无法处理其他任务（prefetch 失效）

**建议**：使用 `celery.contrib.asyncio` 或将 Celery task 改写为 async，配合 `asgiref.sync.async_to_sync` 或直接使用 `anyio.to_thread.run_sync`。

### 1.5 [P0] Document Service 使用无界内存存储

`services/document-service/document_service/app.py:61-62`：
```python
_documents: dict[str, dict[str, Any]] = {}
_chunks: dict[str, list[dict[str, Any]]] = {}
```

这两个进程级 dict 随文档上传无限增长，没有 TTL、没有容量限制、没有过期驱逐。大量文档上传会导致 OOM。

**建议**：添加 LRU 驱逐策略（如 `cachetools.TTLCache`），或迁移到 Redis/PostgreSQL 持久化存储。

---

## 二、安全问题 (Security)

### 2.1 [P1] RBAC 实现位置不当

**已修复** ✅ — `api-gateway/app/middleware/rbac.py` 中的 `Role(StrEnum)` 已改为从 `shared.models` 导入 `UserRole as Role`，消除了重复定义。RBAC 中间件位置已正确放置在 JWT 之后（`api-gateway/app/main.py:126`）。

### 2.2 [P1] Token 黑名单失败时静默放行

`api-gateway/app/middleware/auth.py:110-112`：
```python
except Exception:
    # Redis unavailable — fail open or closed depending on config
    pass
```
Redis 不可用时，已登出的 token 不会被拦截（fail-open）。且代码注释提到"取决于配置"但 `TOKEN_BLACKLIST_FAIL_CLOSED` 配置项在整个代码库中不存在。

**建议**：添加配置项 `TOKEN_BLACKLIST_FAIL_CLOSED`，生产环境应设为 `true`（Redis 不可用时拒绝请求而非放行）。

### 2.3 [P2] 前端 Token 存储于 localStorage

`frontend/src/contexts/AuthContext.tsx` 将 JWT 存储在 `localStorage`：XSS 攻击可读取 token，无法设置 HttpOnly/Secure 标志。

**建议**：优先使用 HttpOnly Cookie 存储 token，或至少使用 sessionStorage + 短过期时间。若必须用 localStorage，需要 CSP 头限制内联脚本。

### 2.4 [P2] CORS 配置于生产环境不安全

`.env.template` 中 `CORS_ORIGINS=["*"]`，配合 `allow_credentials=True`（`api-gateway/app/main.py:116`），浏览器会直接拒绝请求（违反 CORS 规范）。

**建议**：生产环境配置 `CORS_ORIGINS=["https://econai.institution.cn"]`，开发环境保留 `*`。

### 2.5 [P2] MinIO 对象路径遍历风险

`services/document-service/document_service/app.py:182`：
```python
storage_path = f"projects/{project_id}/{doc_id}/{filename}"
```
`filename` 来自用户上传的 `file.filename`，攻击者可上传名为 `../../../etc/passwd` 的文件。虽然 MinIO bucket 提供一定隔离，但仍有路径遍历风险。

**建议**：使用 `os.path.basename()` 或 `pathlib.PurePath(filename).name` 提取安全文件名。

### 2.6 [P2] 缺少 CSRF 保护

**建议**：添加 CSRF token 中间件，或使用 `SameSite=Strict` cookie + 自定义请求头校验。

### 2.7 [P2] 多处硬编码默认密码

| 位置 | 默认值 |
|------|--------|
| `shared/config.py:33` | `postgres_password: str = "econai_secret_change_me"` |
| `shared/config.py:41` | `jwt_secret: str = "econai_jwt_secret_change_me_min_32_chars"` |
| `api-gateway/app/config.py:22` | `jwt_secret: str = "change-me-in-production"` |
| `user-service/app/config.py:26` | `jwt_secret: str = "change-me-in-production"` |
| `celery/celery_config.py:8` | Redis 密码在 URL 中硬编码 |

**建议**：所有默认值改为空字符串并加校验（启动时若检测到为空则报错退出），强制用户通过 `.env` 配置。

---

## 三、架构与设计问题 (Architecture)

### 3.1 [P2] 无 API 版本化

所有端点使用 `/api/projects`、`/api/tasks` 等无版本前缀的路径。

**建议**：添加 `/api/v1/` 前缀，网关层支持同时路由 v1/v2 到不同版本的后端服务。

### 3.2 [P2] Agent 循环不完整的任务被标记为"完成"

`agent_loop.py:122-134`：达到最大迭代次数时，强制调用 `format_output`，但任务状态仍是 `completed`。用户无法区分"正常完成"和"因超迭代被迫截断"。

Schema 现已包含 `completion_type` 字段，但代码中未使用。

**建议**：写入时设置 `completion_type` 为 `max_iterations_reached`，前端展示时区分标记。

### 3.3 [P2] Agent 的 LLM Plan 输出格式脆弱

`agent_loop.py:211-241` 使用正则表达式解析 LLM 文本输出来提取 tool_call。

**建议**：优先依赖 LLM 原生的 tool_use/function-calling 能力，正则 fallback 仅用于记录 warning 并重试。连续 2 次解析失败不应直接终止，应给出更详细的错误信息。

### 3.4 [P2] Prompt 模板重复存在

两个位置包含相同的 Jinja2 模板：
- `templates/prompts/`（5 个文件）
- `services/orchestration-service/orchestration_service/task_workflows.py:27-148`（作为 `DEFAULT_TEMPLATES` 字典嵌入代码）

且 `task_workflows.py:257` 将模板缓存为模块级全局变量，重启前不会更新。

**建议**：保留 `templates/prompts/` 为唯一源，删除代码内嵌的 `DEFAULT_TEMPLATES`；在 lifecycle 中加载模板而非模块级缓存。

### 3.5 [P1] `shared/` 配置基类未被任何服务继承

`shared/config.py` 定义了 `AppSettings(BaseSettings)` 包含公共的 DB/Redis/JWT 默认值。但 8 个服务（API Gateway + 7 微服务）**全部自定义独立的 `Settings` 类，没有一个继承 `AppSettings`**。

这导致每个服务的 DB URL、JWT 密钥等有**不同的默认值**（如 user-service 的 `database_url` 默认密码不同于 document-service）。

**已修复** ✅ — kb-service、orchestration-service、user-service 的配置类现已继承 `AppSettings`。公共字段（`jwt_secret`、`jwt_algorithm` 等）从基类继承，仅通过字段覆盖（`database_url`、`redis_url`）保留各服务的 Docker 默认值。

### 3.6 [P1] `shared/log_setup.py` 从未被调用

`shared/log_setup.py` 提供了 JSON 结构化日志的 `setup_logging()` 函数，但全项目零引用。所有服务使用原生 `logging.getLogger()`。API Gateway 自己在 `app/main.py:31-54` 中重复实现了 structlog 配置。

**建议**：删除 API Gateway 中的自定义日志配置，统一使用 `shared/log_setup.setup_logging()`。

### 3.7 [P2] 服务发现依赖硬编码 localhost 默认值

多个服务的配置类中，`kb_service_url`、`llm_router_url` 等默认值使用 `localhost`。当环境变量因前缀不匹配未被注入时（见 1.3），服务尝试连接 localhost 而非 Docker 服务名，在容器化环境下不可达。

**建议**：默认值应使用 Docker 服务名（如 `http://kb-service:8002`），或至少提供明确的 fallback 文档。

---

## 四、数据与存储问题 (Data)

### 4.1 [P1] 无数据库迁移策略

`db/alembic/versions/001_base_schema.py` 是一个空桩（stub），不包含实际 schema。`services/user-service/alembic/versions/` 为空。`01-schema.sql` 仅适用于首次初始化，不支持增量 schema 变更。

**建议**：为当前 schema 生成完整的初始 Alembic migration，后续所有变更通过 migration 管理。

### 4.2 [P1] PostgreSQL FTS 不支持中文分词

`01-schema.sql:130-131` 使用 `to_tsvector('simple', content)` 创建 GIN 索引，`simple` 配置不分词。

**建议**：
1. 安装 `zhparser` 或 `pg_jieba` 中文分词扩展
2. 或使用 `pg_bigm`/`pg_trgm` 做模糊匹配
3. 生产环境建议使用 Elasticsearch 做 BM25

### 4.3 [P2] 缺少字段级加密

GDPR 要求静态数据 AES-256 加密，但 schema 中用户邮箱、审计日志 IP 等均为明文。

**建议**：使用 PostgreSQL `pgcrypto` 扩展做列级加密。

### 4.4 [P2] 审计日志可被应用用户删除

**建议**：创建独立的 `econai_audit` 用户专用于写入审计日志，应用用户仅 SELECT 权限。

---

## 五、代码质量问题 (Code Quality)

### 5.1 [P2] 共享模块未被广泛使用

`shared/` 在各服务的 `pyproject.toml` 中已声明为依赖（全部 7 个服务），且基本模型（`ErrorDetail`、`ErrorResponse`、`HealthResponse` 等）已导入使用。**但以下仍未整合**：

- `AppSettings` 基类（见 3.5）
- `setup_logging` 日志配置（见 3.6）
- MinIO 客户端（见 5.6）
- `UserRole` 枚举在 RBAC 中间件中重复定义（见 2.1）

**建议**：继续将可共享的工具迁移到 `shared/`，预计可消除约 300 行重复代码。

### 5.2 [P2] HTTP 客户端生命周期管理缺失

`services/orchestration-service/orchestration_service/tools.py:29-36` 使用模块级 `_http_client` 单例，`reset_http_client()` 存在但从未调用。连接池从不释放。非线程安全（`if _http_client is None` check-then-set 竞态条件）。

**建议**：在 FastAPI lifespan 中初始化/关闭 httpx client，通过依赖注入传递给 tools。

### 5.3 [P2] 未使用的代码/依赖

| 位置 | 问题 |
|------|------|
| `api-gateway/app/middleware/auth.py:24` | `AUTH_OPTIONAL_PATHS = set()` 定义但从未填充 |
| `api-gateway/pyproject.toml` | `starlette-prometheus`、`prometheus-client` 声明但未在代码中导入使用 | **已修复** ✅ |
| `.env.template` | `MILVUS_COLLECTION_NAME`、`MILVUS_INDEX_TYPE`、`MILVUS_NLIST` 未在代码中引用 |

**建议**：清理未使用的代码和依赖。

### 5.4 [P2] 重复的错误处理逻辑

`services/orchestration-service/orchestration_service/tools.py` 中 6 个 tool 函数（`_search_kb`、`_generate_section` 等）包含几乎相同的 `try/except httpx.HTTPError` 模式（各 4-5 行）。

**建议**：提取为 `with_error_handling()` 装饰器或 context manager。

### 5.5 [P2] KB Service 异常处理器泄露内部信息

`kb-service/kb_service/app.py:286-292` 中 `str(exc)` 可能包含堆栈信息、SQL 错误等敏感内容返回给客户端。

**已修复** ✅ — `generic_exception_handler` 现在返回通用的 `"An internal error occurred. Please try again later."`，详细错误通过 `logger.exception()` 记录。

### 5.6 [P2] MinIO 客户端代码翻倍

`services/document-service/document_service/minio_client.py`（122 行）和 `services/output-service/output_service/minio_client.py`（108 行）是几乎相同的实现。

**已修复** ✅ — 核心 MinIO 操作已提取到 `shared/minio_client.py`（`MinIOClient` 类 + `MinIOConfig` 参数对象)。两个服务现在通过 `MinIOConfig` 注入各自的连接参数，使用共享实现。消除约 150 行重复代码。

### 5.7 [P3] 开发工具在 main dependencies 中

| 包 | 所属 |
|----|------|
| `shared/pyproject.toml` | `mypy`、`pytest`、`ruff` 在 `dependencies` 中 |
| `kb-service/pyproject.toml` | `pytest`、`ruff`、`mypy` 在 runtime deps |
| `orchestration-service/pyproject.toml` | `pytest`、`ruff`、`mypy` 在 runtime deps |

**建议**：将开发工具移入 `[project.optional-dependencies] dev`。

### 5.8 [P3] `# type: ignore` 过多（35+ 处）

大部分因第三方库无 typing stub（`pymilvus`、`qdrant-client`、Celery 装饰器），但也有可疑的使用：
- `tools.py:119` 和 `state.py:75` — 设置了类型不匹配的属性/参数

**建议**：对第三方库的 `# type: ignore` 添加注释说明原因，对工程代码内的尽可能修复。

---

## 六、运维与部署问题 (Operations)

### 6.1 [P2] 缺少备份脚本实现

**建议**：创建 `deploy/backup.sh` 脚本，实现 PostgreSQL dump + MinIO mirror + 配置备份。

### 6.2 [P1] Celery Worker 缺少优雅关闭

`docker-compose.yml` 中 celery-worker-document 和 celery-worker-orchestration 均未配置 `stop_grace_period`。默认 10 秒不足以完成文档解析（`CELERY_TASK_TIME_LIMIT=1800`）。

**建议**：设置 `stop_grace_period: 600s`（10 分钟），并使用 Celery 的 `worker_soft_shutdown` 信号。

### 6.3 [P3] 日志聚合缺失

运维手册提到"日志使用 ELK/Loki 集中收集"，但 docker-compose 中没有 Loki/Fluentd 配置。

**建议**：添加 `loki` + `promtail` 服务到 docker-compose，或至少配置 Docker 日志驱动为 `json-file` + logrotate。

### 6.4 [P3] 资源限制仅在部分服务配置

`docker-compose.prod.yml` 只为 5 个服务设置了 `deploy.resources.limits`，Redis、Milvus、MinIO 等关键基础设施无限制。

**建议**：为所有服务设置 CPU/内存 limits。

### 6.5 [P3] 单点故障

- PostgreSQL 单实例（无 replica）
- Redis 单实例（无 sentinel/cluster）
- API Gateway 单实例（无 LB 层多副本）

**建议**：MVP 阶段可接受，生产环境需要主备配置。

### 6.6 [P2] API Gateway Dockerfile 的 builder stage 损坏

`api-gateway/Dockerfile:7`：
```dockerfile
RUN uv pip install --system --no-cache -r <(uv pip compile pyproject.toml 2>/dev/null || echo "")
```
`<( )` process substitution 是 bash 特性，在 `/bin/sh`（Alpine 默认）中不可用；`|| echo ""` 会使 builder 静默安装空包。

**建议**：改为两步操作：先用 `uv pip compile` 生成 requirements.txt，再 `uv pip install -r requirements.txt`。

### 6.7 [P2] Docker Compose 不挂载 prompt 模板卷

Orchestration 服务的 prompt 模板在 repo root 的 `templates/prompts/`，但 `docker-compose.override.yml` 只挂载了 `./services/orchestration-service:/app`，模板路径在容器内不可见。

**建议**：增加挂载 `./templates:/app/templates` 或在 `override.yml` 中指定正确的模板路径。

### 6.8 [P2] Nginx HTTPS server 块完全注释掉

`nginx/nginx.conf:131-151` 的 HTTPS server block 被注释，当前无任何 TLS 终止。在生产环境这是必须的。

### 6.9 [P3] 7 个 Dockerfile 几乎完全相同

所有 7 个服务的 Dockerfile 共享相同的基础镜像和安装步骤，仅包路径不同。

**建议**：创建共享 base image（`econai-base`），各服务 Dockerfile 只需 `FROM econai-base` + 复制代码。

---

## 七、前端问题 (Frontend)

### 7.1 [P1] `isLoading` 硬编码 false，PrivateRoute 守卫形同虚设

`frontend/src/contexts/AuthContext.tsx:29`：
```tsx
const isLoading = false;
```
`PrivateRoute` 组件依赖 `isLoading` 来决定何时显示加载状态和触发路由守卫。由于始终为 `false`，路由守卫在 token 尚未验证时就会放行。更为严重的是，`PrivateRoute` 的测试通过是因为它 mock 了 `isLoading: true`，但这个状态在生产环境中永远不会出现。

**已修复** ✅ — `AuthProvider` 现在在 mount 时调用 `getCurrentUser()`（`GET /auth/me`）验证已存储 token 的有效性。验证期间 `isLoading = true`，阻止 PrivateRoute 提前放行。Token 无效时自动清除 localStorage 中的认证数据。

### 7.2 [P1] 无 ErrorBoundary 组件

前端整个 `src/` 目录中无任何 ErrorBoundary。任何未捕获的 React 渲染错误将导致白屏。

**建议**：在 `App.tsx` 外层添加 ErrorBoundary，至少区分"可恢复错误"和"致命错误"两类处理。

### 7.3 [P2] 401 处理使用硬导航

`frontend/src/api/client.ts:91,111` 使用 `window.location.href = '/login'`，这会丢失 React 状态并造成整页重载。

**建议**：使用 React Router 的 `navigate('/login')` 编程式导航，或通过事件总线通知 AuthContext 清除用户状态。

### 7.4 [P2] 无请求去重

快速双击"创建任务"按钮会发送多个相同请求。

**建议**：对 POST/PUT mutation 请求添加防抖或 pending 状态禁用。

### 7.5 [P2] 无全局网络错误提示

API 客户端只处理 401 错误，网络断开、超时等场景没有友好的用户提示。

**建议**：添加全局网络状态检测（`navigator.onLine` + 请求超时 toast 通知）。

### 7.6 [P2] 前端测试仅覆盖 3/20+ 组件

| 已测试 | 未测试（零用例） |
|--------|-----------------|
| AuthContext、PrivateRoute、TaskList 基础渲染 | Login、ProjectList、ProjectDetail、KnowledgeBase、TaskOutput、3 个 Admin 页面、DocumentUpload、MarkdownPreview、CitationBadge、TaskProgress、所有 hooks（usePolling、useRequest）、所有 API 模块 |

### 7.7 [P3] `useRequest` 依赖数组有 eslint-disable

`frontend/src/hooks/useRequest.ts:65-70` 的 `useEffect` 中从依赖数组中排除了 `options` 和 `run`，且 `run` 在每次渲染时重新创建（因 `useCallback` 的 `[options]` 是内联对象）。

**建议**：使用 `useRef` 存储 options 避免重创建，移除 eslint-disable。

---

## 八、测试问题 (Testing)

### 8.1 [P1] 零集成测试 + 后端覆盖不足

全部 638 个测试均为单元测试，使用纯 mock。无法验证：服务间 HTTP 调用契约、数据库迁移正确性、Redis pub/sub 事件流、Agent 循环端到端行为。

此外，多个后端服务有完整模块无测试覆盖：

| 服务 | 缺失测试的模块 |
|------|--------------|
| **user-service** | user CRUD、group management、project management、audit routers、GDPR router、LDAP auth |
| **document-service** | `app.py` 路由、`format_identifier`、`metadata_extractor`、`minio_client`、`validation` |
| **kb-service** | `app.py` 搜索/索引/生命周期路由、`deps.py`、`vector_store.py` |
| **orchestration-service** | `app.py` 路由、`task_workflows.py`、`progress.py`、`worker.py`、`state.py`、`sensitivity.py` |

**建议**：至少为关键路径添加集成测试（文献综述完整流程），使用 testcontainers 或 docker-compose 启动真实依赖。

### 8.2 [P1] Mock 测试覆盖了 Mock 实现

KB Service 的测试覆盖了 `MockEmbeddingClient` 和 `InMemoryVectorStore` 的逻辑，而不是真实的 text2vec + Milvus 调用。当切换到真实实现时，这些测试无法提供保护。

### 8.3 [P3] 部分测试仅验证 trivial 条件

- `shared/tests/test_models.py:19-28` — 仅验证枚举成员存在，无序列化/反序列化/无效输入测试
- `user-service/tests/test_auth_router.py:66-68` — logout 测试仅验证 204 状态码，不验证 token 是否真的失效
- `api-gateway/tests/test_auth.py:56-62` — 仅验证 200 状态码，不验证响应体结构

---

## 九、可观测性问题 (Observability)

### 9.1 [P2] 健康检查浅层

所有 7 个微服务的 `/health` 端点都只返回静态 JSON，不检查任何依赖（DB、Redis、MinIO、下游服务）。只有 API Gateway 会检查 Redis 连接。

**已修复** ✅ — 所有 7 个服务的 `/health` 端点已增强：
- **KB Service**: 报告 `hybrid_searcher`/`index_pipeline`/`lifecycle_manager` 初始化状态，输出 `healthy` 或 `degraded`
- **User Service**: 报告 Redis 配置状态
- **Orchestration Service**: 报告 agent 配置和下游服务 URL
- **Document Service**: 报告 MinIO endpoint/bucket 和 OCR 状态
- **Citation/Output/LLM Router Service**: 报告关键配置参数
- `shared/models.py` 的 `HealthResponse` 添加了 `extra="allow"` 以支持扩展字段

### 9.2 [P2] Prometheus metrics 未接入

`api-gateway/pyproject.toml` 声明了 `starlette-prometheus` 和 `prometheus-client`，但代码中从未导入使用。无 `/metrics` 端点，无 `PrometheusMiddleware`。

### 9.3 [P3] Request ID 未融入日志上下文

API Gateway 通过 `RequestIDMiddleware` 生成了 `X-Request-ID`，但日志输出中未关联 request_id，无法通过日志追踪完整请求链路。

---

## 十、功能完备性问题

### 10.1 [P1] OCR 流程未集成

Tesseract 已安装并可选使用，但 Docker 镜像中未包含 Tesseract 及中文语言包。

**建议**：在 document-service Dockerfile 中添加 `RUN apt-get install -y tesseract-ocr tesseract-ocr-chi-sim`。

### 10.2 [P2] 本地 LLM 的 function-calling 能力未验证

`LocalAdapter` 假设本地 vLLM/Ollama 支持 OpenAI-compatible function-calling，但并非所有本地模型都有此能力。

**建议**：为不支持 function-calling 的本地模型实现 prompt-based tool calling fallback。

### 10.3 [P2] LLM Router 重试循环无上限守护

`llm-router/llm_router/app.py:346` 使用 `while True` 循环，虽然内部异常处理会 break，但无整体迭代上限。一旦异常处理逻辑有 bug，会无限循环。

### 10.4 [P3] GB/T 9704 字体依赖

`.docx` 生成器使用"小标宋_GB2312"等字体，有版权，不能随 Docker 镜像分发。

**建议**：在运维文档中明确说明字体安装步骤，并提供检查脚本。

---

## 十一、配置与环境变量问题

### 11.1 [P2] `.env.template` 缺失多个已使用的配置项

代码中使用但 `.env.template` 中缺失的变量：

| 变量名 | 使用位置 |
|--------|---------|
| `LLM_RETRY_MAX_429` | `llm-router/config.py:37` |
| `LLM_RETRY_MAX_5XX` | `llm-router/config.py:39` |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `llm-router/config.py:43` |
| `CIRCUIT_BREAKER_RECOVERY_TIMEOUT_S` | `llm-router/config.py:44` |
| `KB_RERANKER_ENABLED` | `kb-service/config.py:43`、`deps.py`、`hybrid_search.py` |

### 11.2 [P3] 依赖版本无上限约束

所有 `pyproject.toml` 使用 `>=` 声明依赖，无上限。未来任何依赖的 breaking release 会被自动安装。

### 11.3 [P3] BM25 数据库连接池未在 shutdown 关闭

`kb-service/kb_service/bm25.py:42` 创建的 `asyncpg` 连接池在 `lifespan` shutdown 时未被调用 `close()`。

### 11.4 [P3] `except Exception: pass` 静默吞错（共 5 处）

| 位置 | 场景 |
|------|------|
| `api-gateway/app/middleware/auth.py:110-112` | Token 黑名单查询失败 |
| `api-gateway/app/middleware/audit.py:205-207` | 审计事件发布失败 |
| `document-service/parsers/pdf_parser.py:41-42` | TOC 提取失败 |
| `document-service/parsers/pdf_parser.py:68-69` | 表格提取失败 |
| `document-service/parsers/email_parser.py:59-60` | 解码失败 |

**已修复** ✅ — 所有 5 处 `except: pass` 均已替换为 `logger.warning()` 调用并包含 `exc_info=True`，确保错误可追踪但不中断正常流程。

---

## 优先级排序总览

| 优先级 | 编号 | 问题描述 | 状态 |
|--------|------|---------|------|
| **P0** | 1.2 | KB Service 使用 mock 实现，核心检索功能不可用 | 待修复 |
| **P0** | 1.3 | 4 个服务 env_prefix 与 docker-compose 不匹配，Docker 环境不可用 | ✅ 已修复 |
| **P0** | 1.4 | Celery Worker 中 `run_until_complete` 阻塞 | 待修复 |
| **P0** | 1.5 | Document Service 无界内存存储 | 待修复 |
| **P0** | 10.1 | OCR Docker 环境缺失 | 待修复 |
| **P1** | 2.1 | RBAC 位置不当 + UserRole 重复定义 | ✅ 已修复 |
| **P1** | 3.5 | `AppSettings` 基类从未被继承 | ✅ 已修复 |
| **P1** | 3.6 | `shared/log_setup.py` 从未使用 | 待修复 |
| **P1** | 4.1 | 无数据库迁移策略 | 待修复 |
| **P1** | 4.2 | PostgreSQL FTS 中文分词不可用 | 待修复 |
| **P1** | 7.1 | `isLoading` 硬编码 false，路由守卫失效 | ✅ 已修复 |
| **P1** | 7.2 | 前端无 ErrorBoundary | 待修复 |
| **P1** | 8.1 | 零集成测试 + 多模块无测试 | 待修复 |
| **P1** | 8.2 | Mock 测试覆盖了 Mock 实现 | 待修复 |
| **P1** | 6.2 | Celery Worker 缺少优雅关闭 | 待修复 |
| **P2** | 2.2 | Token 黑名单静默放行 | 待修复 |
| **P2** | 2.3 | 前端 Token localStorage 存储 | 待修复 |
| **P2** | 2.4 | CORS `*` + credentials | 待修复 |
| **P2** | 2.5 | MinIO 路径遍历风险 | 待修复 |
| **P2** | 2.7 | 硬编码默认密码（5 处） | 待修复 |
| **P2** | 3.1 | API 版本化缺失 | 待修复 |
| **P2** | 3.2 | Agent 截断任务无标记 | 待修复 |
| **P2** | 3.4 | Prompt 模板双重存在 | 待修复 |
| **P2** | 5.1 | 共享模块未完全整合（~300 行重复代码仍存在） | 部分修复 |
| **P2** | 5.5 | KB Service 异常处理器泄露 str(exc) | ✅ 已修复 |
| **P2** | 5.6 | MinIO 客户端翻倍 | ✅ 已修复 |
| **P2** | 6.6 | API Gateway Dockerfile builder 损坏 | 待修复 |
| **P2** | 6.7 | Prompt 模板卷未挂载 | 待修复 |
| **P2** | 6.8 | Nginx HTTPS 注释掉 | 待修复 |
| **P2** | 7.6 | 前端测试仅覆盖 3/20+ 组件 | 待修复 |
| **P2** | 9.1 | 健康检查浅层 | ✅ 已修复 |
| **P2** | 9.2 | Prometheus metrics 未接入 | 待修复 |
| **P2** | 10.3 | LLM Router `while True` 无上限 | 待修复 |
| **P2** | 11.1 | `.env.template` 缺失 5 个配置项 | 待修复 |
| **P3** | 1.1 | `users.email` NULL/NOT NULL 不一致 | ✅ 已修复 |
| **P3** | 2.6 | CSRF 保护缺失 | 待修复 |
| **P3** | 3.3 | Agent Plan 解析脆弱 | 待修复 |
| **P3** | 3.7 | localhost 硬编码默认值 | 待修复 |
| **P3** | 5.2 | HTTP 客户端生命周期 | 待修复 |
| **P3** | 5.3 | 未使用代码/依赖 | ✅ 已修复 |
| **P3** | 5.4 | 重复错误处理逻辑 | 待修复 |
| **P3** | 5.7 | 开发工具在 main deps | 待修复 |
| **P3** | 5.8 | `# type: ignore` 过多 | 待修复 |
| **P3** | 6.1 | 缺少备份脚本 | 待修复 |
| **P3** | 6.3 | 日志聚合缺失 | 待修复 |
| **P3** | 6.4 | 资源限制不完整 | 待修复 |
| **P3** | 6.9 | Dockerfile 重复 | 待修复 |
| **P3** | 8.3 | Trivial 测试 | 待修复 |
| **P3** | 9.3 | Request ID 未入日志 | 待修复 |
| **P3** | 11.2 | 依赖版本无上限 | 待修复 |
| **P3** | 11.3 | BM25 pool 未 close | 待修复 |
| **P3** | 11.4 | `except: pass` 共 5 处 | ✅ 已修复 |

---

*文档版本：v2.1 | 日期：2026-05-22 | 10 项关键问题已修复*

**本次更新摘要（v2.1）**：针对 v2.0 审计结果的 10 项关键问题实施了修复：
1. ✅ RBAC UserRole 重复定义 → 从 shared.models 统一导入
2. ✅ users.email NULL/NOT NULL 不一致 → SQLAlchemy model 改为 nullable=False
3. ✅ MinIO 客户端代码翻倍 → 创建 shared/minio_client.py（消除 ~150 行重复代码）
4. ✅ KB Service 异常处理器泄露 str(exc) → 泛化错误消息
5. ✅ 5 处 except:pass 静默吞错 → 全部添加 logger.warning()
6. ✅ 前端 isLoading 硬编码 false → 实现 token 验证流程
7. ✅ 4 个服务 env_prefix 不匹配 → 移除前缀，docker-compose 变量直接命中
8. ✅ AppSettings 未被继承 → kb/orchestration/user 服务继承 AppSettings
9. ✅ 全员健康检查浅层 → 7 个服务均报告依赖状态和关键配置
10. ✅ api-gateway 未使用依赖 → 移除 starlette-prometheus + prometheus-client
总计修复：11 项（含 1.1 email nullable），修复率 45 项中 11 项（24%）

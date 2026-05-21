# EconAI 项目问题分析与改进建议

> 版本：v1.0 | 日期：2026-05-21 | 全项目审计

---

## 一、严重问题 (Critical)

### 1.1 DB Schema 与代码/设计不一致

| 问题 | 详情 |
|------|------|
| `documents` 表缺少 `is_internal` 字段 | 概要设计 6.2 节定义了 `is_internal BOOLEAN DEFAULT false`，敏感度判定依赖此字段决定 LLM 路由。但 `db/init/01-schema.sql` 的 `documents` 表中没有此列。代码中多个模块引用了 `is_internal`（`document-service/celery_app.py`、`orchestration-service/sensitivity.py`），部署后会出现 SQL 错误。 |
| `analysis_tasks` 表缺少多个字段 | 概要设计 6.2 节定义了 `llm_route VARCHAR(32)`、`iteration_count INT`、`celery_task_id VARCHAR(256)`，但实际 schema 中均缺失。编排服务的 agent_loop.py 依赖 `iteration_count` 追踪迭代轮次。 |
| `documents` 表字段命名不一致 | 设计文档使用 `storage_path`，schema 使用 `minio_path`；设计文档使用 `original_name`，schema 使用 `original_filename`；设计文档使用 `size_bytes`，schema 使用 `file_size_bytes`。 |

**建议**：
1. 在 `documents` 表添加 `is_internal BOOLEAN NOT NULL DEFAULT false`
2. 在 `analysis_tasks` 表添加 `llm_route VARCHAR(32)`、`iteration_count INT DEFAULT 0`、`celery_task_id VARCHAR(256)`
3. 统一字段命名，建议以 schema 为准，更新设计文档

### 1.2 Mock 代码被当作生产实现

KB Service 在运行时使用 mock 实现而非真实组件：

```python
# kb_service/app.py:63
_embedding = MockEmbeddingClient(dim=settings.embedding_dim)

# kb_service/hybrid_search.py:35
self.embedding_client = embedding_client or MockEmbeddingClient()

# kb_service/hybrid_search.py:34
self.vector_store = vector_store or InMemoryVectorStore()
```

- **Embedding**: `MockEmbeddingClient` 返回随机向量，从未调用 text2vec/m3e
- **Vector Store**: `InMemoryVectorStore` 在进程内存中做暴力搜索，从未连接 Milvus/Qdrant
- **Reranker**: `hybrid_search.py:216-219` 使用 query-term-overlap 启发式算法，未调用 BGE-Reranker
- **Citation 相似度**: `verifier.py:124-179` 使用简单 bag-of-words 而非 embedding 向量

**建议**：每个 mock 实现需要对应的真实实现，通过依赖注入切换。KB Service 启动时应检测环境（`VECTOR_DB_TYPE`）并加载真实客户端。

### 1.3 Prompt 模板重复存在

两个位置包含相同的 Jinja2 模板：
- `services/orchestration-service/orchestration_service/templates/prompts/`（5 个文件）
- `templates/prompts/`（4 个文件，缺少 `system_prompt.j2`）

这种重复会导致仅更新一处时行为不一致。

**建议**：保留一份模板，另一处通过构建时复制或符号链接同步。推荐以 `templates/prompts/` 为唯一源。

---

## 二、安全问题 (Security)

### 2.1 RBAC 实现位置不当

RBAC 校验在 `api-gateway/app/main.py:183-205` 的 catch-all handler 中执行，而非独立中间件。这意味着：
- 直接访问网关自带的 endpoint 绕过 RBAC
- 中间件管道顺序不清晰（设计文档要求 JWT→RBAC→限流→审计，但实际实现中 RBAC 在中间件链之外）

**建议**：将 RBAC 重构为独立中间件 `RBACMiddleware`，插入到 `JWTAuthMiddleware` 之后。

### 2.2 Token 黑名单失败时静默放行

`api-gateway/app/middleware/auth.py:110-112`：
```python
except Exception:
    # Redis unavailable — fail open or closed depending on config
    pass
```
Redis 不可用时，已登出的 token 不会被拦截（fail-open），存在安全风险。

**建议**：添加配置项 `TOKEN_BLACKLIST_FAIL_CLOSED`，生产环境应设为 `true`（Redis 不可用时拒绝请求）。

### 2.3 前端 Token 存储于 localStorage

`frontend/src/contexts/AuthContext.tsx:33` 将 JWT 存储在 `localStorage`：
- XSS 攻击可读取 token
- 无法设置 HttpOnly/Secure 标志

**建议**：优先使用 HttpOnly Cookie 存储 token，或至少使用 sessionStorage + 短过期时间。如果必须用 localStorage，需要 CSP 头限制内联脚本。

### 2.4 CORS 默认允许所有来源

`.env.template` 中 `CORS_ORIGINS=["*"]`，且配合 `allow_credentials=True` 时浏览器会拒绝请求。生产环境需要限定为实际前端域名。

**建议**：生产环境配置 `CORS_ORIGINS=["https://econai.institution.cn"]`，开发环境保留 `*`。

### 2.5 缺少 CSRF 保护

使用 JWT Bearer token 的 SPA 仍然可能受到 CSRF 攻击，尤其是在 cookie 中也存储了 token 的情况下。

**建议**：添加 CSRF token 中间件，或使用 `SameSite=Strict` cookie + 自定义请求头校验。

---

## 三、架构与设计问题 (Architecture)

### 3.1 无 API 版本化

所有端点使用 `/api/projects`、`/api/tasks` 等无版本前缀的路径。未来 breaking change 无法平滑引入。

**建议**：添加 `/api/v1/` 前缀，网关层支持同时路由 v1/v2 到不同版本的后端服务。

### 3.2 Agent 循环不完整的任务被标记为"完成"

`agent_loop.py:122-134`：达到最大迭代次数时，强制调用 `format_output`，但任务状态仍是 `completed`。用户无法区分"正常完成"和"因超迭代被迫截断"。

**建议**：
1. 在 `analysis_tasks` 表添加 `completion_type` 字段（`normal` / `max_iterations_reached` / `fallback`）
2. 前端展示时区分标记，提示用户可能需要补充检索或调整参数

### 3.3 Agent 的 LLM Plan 输出格式脆弱

`agent_loop.py:211-241` 使用正则表达式解析 LLM 文本输出来提取 tool_call，这极易因 LLM 输出格式微小变化而失败。虽然有 JSON tool_calls 路径，但正则 fallback 的可靠性很低。

**建议**：优先依赖 LLM 原生的 tool_use/function-calling 能力，正则 fallback 仅用于记录 warning 并重试。连续 2 次解析失败不应直接终止，应给出更详细的错误信息。

### 3.4 服务发现依赖 Docker Compose DNS

`detailed-design.md` 第 10.4 节定义了服务主机名映射，但这仅适用于 Docker Compose 网络。在 Kubernetes 或非 Compose 环境下需要额外的服务发现机制。

**建议**：服务 URL 全部通过环境变量配置，去除对特定主机名的硬编码依赖（当前代码已基本遵循此原则，需确认无遗漏）。

---

## 四、数据与存储问题 (Data)

### 4.1 无数据库迁移策略

`db/alembic/versions/` 和 `services/user-service/alembic/versions/` 均为空。`01-schema.sql` 仅适用于首次初始化，不支持增量 schema 变更。

**建议**：为已完成的 schema 创建初始 Alembic migration（`base`），后续所有变更通过 migration 管理。

### 4.2 PostgreSQL FTS 不支持中文分词

`01-schema.sql:130-131` 使用 `to_tsvector('simple', content)` 创建 GIN 索引，`simple` 配置不分词，会将每个字作为独立 token，导致 BM25 中文搜索质量极差。

**建议**：
1. 安装 `zhparser` 或 `pg_jieba` 中文分词扩展
2. 或使用 `pg_bigm`/`pg_trgm` 做模糊匹配
3. 生产环境建议使用 Elasticsearch 做 BM25

### 4.3 缺少字段级加密

GDPR 要求在静态数据上使用 AES-256 加密（概要设计 8.1 节），但 schema 中用户邮箱、审计日志 IP、文档内容等敏感字段均为明文存储。

**建议**：使用 PostgreSQL `pgcrypto` 扩展对 `users.email`、`audit_logs.ip_address`、`documents` 中标记为 `is_internal=true` 的内容做列级加密。

### 4.4 审计日志可被应用用户删除

Schema 中 `REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC; REVOKE ... FROM econai;` 试图保护审计日志，但如果应用连接使用 `econai` 用户，这些 REVOKE 只影响 `econai` 角色。如果应用以超级用户连接则无效。

**建议**：创建独立的 `econai_audit` 用户专用于写入审计日志，应用用户仅 SELECT 权限。

---

## 五、代码质量问题 (Code Quality)

### 5.1 共享模块未被广泛使用

`shared/` 包定义在 3 个服务的 `pyproject.toml` 中（document、kb、orchestration），但 llm-router、citation、output、user-service 也应有共享的 models（如 `AnalysisTask`、`Document`、`User` 等 Pydantic models 在多服务间重复定义）。

**建议**：将通用 Pydantic models、配置基类、日志工具都迁入 `shared/`，所有服务引用统一的模型定义。

### 5.2 HTTP 客户端生命周期管理缺失

`orchestration_service/tools.py:29-42` 使用模块级 `_http_client` 单例，`reset_http_client()` 存在但从未被调用。没有连接池大小配置、没有优雅关闭。

**建议**：在 FastAPI lifespan 中初始化/关闭 httpx client，通过依赖注入传递给 tools。

### 5.3 未使用的代码

`api-gateway/app/middleware/auth.py:24` — `AUTH_OPTIONAL_PATHS = set()` 定义但从未被填充或使用。

**建议**：删除或实现"可选认证"路径机制。

### 5.4 重复的错误处理逻辑

每个 tool（`_search_kb`、`_generate_section`、`_verify_citations`、`_extract_key_claims`、`_compare_policies`、`_format_output`）都包含几乎相同的 `try/except httpx.HTTPError` 模式。

**建议**：提取为 `with_error_handling()` 装饰器或 context manager。

### 5.5 未使用的配置项

`.env.template` 中定义了 `MILVUS_COLLECTION_NAME`、`MILVUS_INDEX_TYPE`、`MILVUS_NLIST` 等配置，但在代码中未找到引用。

**建议**：清理或实现这些配置项的使用。

---

## 六、运维与部署问题 (Operations)

### 6.1 缺少备份脚本实现

运维手册第 6 节描述了备份脚本，但 `deploy/` 目录中不存在 `backup.sh`。

**建议**：创建 `deploy/backup.sh` 脚本，实现 PostgreSQL dump + MinIO mirror + 配置备份。

### 6.2 Celery Worker 缺少优雅关闭

`docker-compose.yml` 中 celery-worker 未配置 `stop_grace_period`。默认 10 秒可能不足以完成正在执行的长任务（文档解析可达 30 分钟）。

**建议**：为 celery-worker 设置 `stop_grace_period: 600s`（10 分钟），并使用 Celery 的 `worker_soft_shutdown` 信号处理正在执行的任务。

### 6.3 日志聚合缺失

运维手册提到"日志使用 ELK/Loki 集中收集"，但 docker-compose 中没有 Loki/Fluentd/Fluent Bit 配置。

**建议**：添加 `loki` + `promtail` 服务到 docker-compose，或至少配置 Docker 日志驱动为 `json-file` + logrotate。

### 6.4 无资源限制

`docker-compose.yml` 中所有服务均未设置 `deploy.resources.limits`，可能导致单个容器耗尽宿主机资源。

**建议**：为每个服务设置合理的 CPU/内存 limits，特别是 Celery worker 和 Milvus。

### 6.5 单点故障

- PostgreSQL 单实例（无 replica）
- Redis 单实例（无 sentinel/cluster）
- API Gateway 单实例（无 LB 层多副本）

**建议**：MVP 阶段可接受，但生产环境需要至少主备配置。

---

## 七、前端问题 (Frontend)

### 7.1 401 处理使用硬导航

`frontend/src/api/client.ts:91` 使用 `window.location.href = '/login'`，这会丢失 React 状态并造成整页重载。

**建议**：使用 React Router 的 `navigate('/login')` 编程式导航，或通过事件总线通知 AuthContext 清除用户状态。

### 7.2 无请求去重

快速双击"创建任务"按钮会发送多个相同请求，创建重复任务。

**建议**：对 POST/PUT 等 mutation 请求添加防抖或 pending 状态禁用。

### 7.3 无离线/网络错误提示

API 客户端只处理 401 错误，网络断开、超时等场景没有友好的用户提示。

**建议**：添加全局网络状态检测（`navigator.onLine` + 请求超时 toast 通知）。

---

## 八、测试问题 (Testing)

### 8.1 零集成测试

全部 638 个测试（622 Python + 16 TypeScript）均为单元测试，使用纯 mock。无法验证：
- 服务间 HTTP 调用契约
- 数据库迁移正确性
- Redis pub/sub 事件流
- Agent 循环端到端行为

**建议**：至少为关键路径添加集成测试（文献综述完整流程、文档上传→解析→索引→检索），使用 testcontainers 或 docker-compose 启动真实依赖。

### 8.2 Mock 测试覆盖了 Mock 实现

KB Service 的测试覆盖了 `MockEmbeddingClient` 和 `InMemoryVectorStore` 的逻辑，而不是真实的 text2vec + Milvus 调用。当切换到真实实现时，这些测试无法提供保护。

**建议**：将 mock 测试转为 contract tests（验证接口契约），补充真实实现的单元测试。

---

## 九、文档问题 (Documentation)

### 9.1 设计文档与实际实现不一致

多处设计文档描述的功能与代码实现存在差异：
- 详细设计的端口映射（10.4 节）中 citation-service 是 8005，output-service 是 8006，但 docker-compose 中也一致。需确认所有端口号统一。
- 概要设计 6.2 节和详细设计中的 schema 定义与实际 SQL 存在差异（见 1.1 节）

### 9.2 README 缺少快速开始步骤

README 引用了手动启动指南，但缺少最简单的"clone + docker compose up"快速验证步骤。

### 9.3 无 API 文档生成

FastAPI 自动生成的 OpenAPI docs 被禁用（`docs_url=None`），但没有替代的 API 文档。

**建议**：开发环境启用 `/docs`，或使用 `python generate_openapi.py` 导出静态文档。

---

## 十、功能完整性问题

### 10.1 OCR 流程未集成

Tesseract 已安装并可选使用，但 Docker 镜像中未包含 Tesseract 及中文语言包。`deploy.sh` 和 Dockerfile 没有安装步骤。

**建议**：在 document-service Dockerfile 中添加 `RUN apt-get install -y tesseract-ocr tesseract-ocr-chi-sim`。

### 10.2 本地 LLM 的 function-calling 能力未验证

`LocalAdapter` 假设本地 vLLM/Ollama 支持 OpenAI-compatible function-calling，但并非所有本地模型都有此能力。当 Agent 循环需要 tool_use 时，本地模型可能无法返回结构化 tool_call。

**建议**：为不支持 function-calling 的本地模型实现 prompt-based tool calling fallback（在 system prompt 中描述工具，通过正则解析响应）。

### 10.3 机构知识库搜索功能未实现

API 定义了 `POST /api/institutional/search`，KB Service 有相关接口，但缺少文档上传到机构知识库的入口和管理界面。

### 10.4 GB/T 9704 字体依赖

`.docx` 生成器使用"小标宋_GB2312"、"仿宋_GB2312"等字体，这些字体有版权，不能随 Docker 镜像分发。当前实现有 fallback 到宋体/仿宋/楷体/黑体，但排版效果可能不符合国标要求。

**建议**：在运维文档中明确说明字体安装步骤，并提供检查脚本。

---

## 优先级建议排序

| 优先级 | 问题编号 | 说明 |
|--------|---------|------|
| P0 | 1.1 | DB Schema 与代码不一致，会导致部署后运行时错误 |
| P0 | 1.2 | KB Service 使用 mock，核心检索功能不可用 |
| P0 | 10.1 | OCR Docker 环境缺失 |
| P1 | 2.1 | RBAC 位置不当，存在权限绕过风险 |
| P1 | 1.3 | Prompt 模板重复，维护风险 |
| P1 | 4.2 | PostgreSQL FTS 中文分词不可用 |
| P1 | 4.1 | 无数据库迁移策略 |
| P2 | 2.2 | Token 黑名单静默失败 |
| P2 | 3.1 | API 版本化缺失 |
| P2 | 3.2 | Agent 截断任务无标记 |
| P2 | 5.1 | 共享模块未广泛使用 |
| P3 | 2.4 | CORS 配置 |
| P3 | 5.2 | HTTP 客户端生命周期 |
| P3 | 6.1 | 缺少备份脚本 |
| P3 | 8.1 | 零集成测试 |

---

*文档版本：v1.0 | 日期：2026-05-21 | 基于全项目审计*
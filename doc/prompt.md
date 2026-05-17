# EconAI Vibe Coding 主控 Prompt

> 版本：v1.0 | 日期：2026-05-17 | 基于概要设计 v1.0 + 详细设计 v1.0 + 任务清单 v1.0

---

## 1. 你的角色

你是 **EconAI 项目的主控 Agent**（Orchestrator）。你的职责是：

1. 理解整个项目的架构、模块划分和依赖关系
2. 按依赖顺序调度**子 Agent** 并行/串行实现各模块
3. 跟踪每个模块的进度和状态
4. 确保每个模块通过质量门禁（pytest + mypy + ruff）后自动 git commit
5. 整个过程**无需人工干预**，从零到完整可运行的系统

---

## 2. 项目概述

**EconAI** 是一个机构级 AI 经济政策分析工具包。用户上传政策文献、研究报告等文档，系统通过自研轻量 Agent 循环（ReAct 变体：Plan → Retrieve → Generate → Verify → Decide）自动完成文献综述、政策草案、政策比较、技术解读等分析任务，输出带逐句来源追溯的 Markdown/.docx/.xlsx/.pptx 报告。

### 核心设计决策

| 决策项 | 选择 |
|--------|------|
| Embedding | text2vec / m3e（中文开源，私有化部署） |
| 工作流编排 | 自研轻量 Agent（LLM 驱动工具调用） |
| 来源追溯 | inline 引用 `[ref:doc_id:page_range]` |
| 文档分块 | 段落级(~300tokens) + 章节级(~2000tokens) |
| 检索策略 | 混合检索（向量语义 + BM25 关键词 + BGE-Reranker 重排序） |
| LLM 部署 | 混合：本地 vLLM/Ollama（敏感数据）+ Claude API（公开数据） |
| 交互模式 | 异步任务 + 进度轮询 |
| 对话模式 | 单次生成（提交→等待→结果） |

---

## 3. 系统架构

```
客户端 (React 19 + TypeScript 5 + Ant Design/Shadcn)
    │  TLS 1.2+ (HTTPS)
    ▼
API 网关 (FastAPI + Nginx)
  ├── JWT 认证中间件
  ├── RBAC 权限校验中间件
  ├── 限流中间件 (Redis Token Bucket)
  └── 审计日志中间件
    │
    ├── /api/auth/*         → user-service (8007)
    ├── /api/projects/*     → user-service (8007)
    ├── /api/projects/{id}/documents/* → document-service (8001)
    ├── /api/projects/{id}/search      → kb-service (8002)
    ├── /api/institutional/search      → kb-service (8002)
    ├── /api/projects/{id}/tasks/*     → orchestration-service (8003)
    ├── /api/tasks/{id}/*              → orchestration-service (8003)
    └── /api/admin/*                   → user-service (8007)
    │
    ▼
服务层 (7 个微服务，均为 FastAPI)
  ┌──────────────────────────────────────────────────────────────┐
  │ document-service (8001)  kb-service (8002)                   │
  │ 上传/解析/分块            embedding/向量索引/混合检索           │
  │                          ↑ Redis pub/sub 索引事件             │
  │ orchestration-service (8003)  llm-router (8004)              │
  │ 任务管理/Agent引擎/工具   敏感度判定/适配器/路由               │
  │ citation-service (8005)  output-service (8006)               │
  │ 引用解析/校验/格式化      Markdown/.docx/.xlsx/.pptx 生成     │
  │ user-service (8007)                                         │
  │ 认证/RBAC/用户组管理/审计                                     │
  └──────────────────────────────────────────────────────────────┘
    │
    ▼
数据层
  PostgreSQL 16+ (业务数据 + BM25 FTS)
  Milvus/Qdrant (向量索引)
  MinIO (文档 + 输出文件存储)
  Redis (Celery 队列 + 缓存 + 限流 + pub/sub)
  Celery (异步任务：文档解析、Agent 分析)
```

---

## 4. 模块清单与依赖关系

### 4.1 模块总览

| 编号 | 模块 | 目录 | 子任务数 | 端口 |
|------|------|------|----------|------|
| M10 | 基础设施与部署 | 项目根目录 | 34 | - |
| M8 | 用户权限服务 | `services/user-service/` | 42 | 8007 |
| M5 | LLM 路由服务 | `services/llm-router/` | 33 | 8004 |
| M1 | API 网关 | `api-gateway/` | 28 | 8000 |
| M2 | 文档解析服务 | `services/document-service/` | 43 | 8001 |
| M6 | 来源溯源服务 | `services/citation-service/` | 30 | 8005 |
| M7 | 输出生成服务 | `services/output-service/` | 39 | 8006 |
| M3 | 知识库服务 | `services/kb-service/` | 35 | 8002 |
| M4 | 任务编排服务 | `services/orchestration-service/` | 54 | 8003 |
| M9 | 前端 SPA | `frontend/` | 38 | - |

**总计：376 个子任务**

### 4.2 依赖图

```
Wave 1 (并行): M10 ─┬─ M8
                    ├─ M5
                    └─ M6

Wave 2 (并行): M8 ─── M1
               M10 ── M2
               M6 ─── M7

Wave 3: M2 + M5 ── M3

Wave 4: M3 + M5 + M6 + M7 ── M4

Wave 5: M1 ── M9
```

### 4.3 具体模块依赖说明

| 模块 | 依赖 | 说明 |
|------|------|------|
| M10 | 无 | 基础设施最先完成，定义数据库 schema、Docker 配置、共享模块 |
| M8 | M10 | 需要 DB schema 存在，但可用 migration 独立创建表 |
| M5 | M10 | 需要配置管理模块模式，无业务依赖 |
| M6 | M10 | 无业务依赖，独立的引用解析/校验逻辑 |
| M1 | M8 | 需要 M8 的认证接口（/api/auth/* 路由）和 RBAC 内部接口 |
| M2 | M10 | 需要 MinIO 客户端模式、PostgreSQL models、Celery 配置 |
| M7 | M6 | 需要 M6 的引用格式化接口（将 [ref:...] 转为脚注） |
| M3 | M2 + M5 | 需要 M2 的索引事件（Redis pub/sub）+ M5 的 LLM 调用（embedding） |
| M4 | M3 + M5 + M6 + M7 | 核心大脑，调用所有其他服务 |
| M9 | M1 | 所有 API 通过 M1 网关访问 |

---

## 5. 执行策略

### 5.1 分批并行调度

你按 **Wave** 分批调度子 Agent。同一 Wave 内的模块**并行启动**（一次发送多个 Agent 工具调用），Wave 之间**串行等待**。

```
主控流程:
  1. git init（如果尚未初始化）
  2. Wave 1: 并行启动 M10, M8, M5, M6
  3. 等待 Wave 1 全部完成
  4. Wave 2: 并行启动 M1, M2, M7
  5. 等待 Wave 2 全部完成
  6. Wave 3: 启动 M3
  7. 等待 M3 完成
  8. Wave 4: 启动 M4
  9. 等待 M4 完成
  10. Wave 5: 启动 M9
  11. 等待 M9 完成
  12. 最终验证：全量 pytest + mypy + ruff
  13. 输出完成报告
```

### 5.2 子 Agent 通用规范

每个子 Agent 负责**一个模块**的完整实现。收到任务后，子 Agent 必须：

1. 阅读对应的设计文档（概要设计 + 详细设计 + 任务清单中本模块部分）
2. 按任务清单逐项实现
3. 编写完整的 pytest 单元测试（纯 mock，不依赖外部服务）
4. 通过 `mypy` 类型检查（严格模式）
5. 通过 `ruff` 代码规范检查
6. 执行 `git add <模块目录>` + `git commit`（带模块名和完成摘要）

### 5.3 质量门禁（每个模块必须通过）

```bash
# 在模块目录下执行
cd <module-directory>
pytest --tb=short --strict-markers          # 所有测试必须通过
mypy . --strict                             # 类型检查无错误
ruff check .                                # 代码规范无问题
```

### 5.4 Git 提交规范

每个模块完成后，子 Agent 必须自动提交：

```bash
git add <module-directory>
git commit -m "$(cat <<'EOF'
feat(<module-code>): implement <module-name>

- All subtasks completed per doc/tasks/<module>.md
- pytest: <N> tests passed
- mypy: clean
- ruff: clean

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 6. 各模块实现要点

### M10 — 基础设施与部署（项目根目录）

**输入**：概要设计第8/9/10章、详细设计第10/11/12章、`doc/tasks/infrastructure.md`

**关键交付物**：
- `docker-compose.yml`（所有服务定义）+ `docker-compose.override.yml`（开发模式热重载）+ `docker-compose.prod.yml`
- 每个微服务的 `Dockerfile`（多阶段构建，python:3.12-slim）
- `db/init/01-schema.sql`：完整的建表 SQL（users, projects, documents, document_chunks, analysis_tasks, task_outputs, citations, audit_logs, llm_usage_logs, project_groups, project_group_members），含所有索引和 PostgreSQL FTS 配置
- `db/init/02-seed.sql`：默认 admin 用户 + 示例项目组
- Alembic 迁移配置
- `.env.template`：所有环境变量模板
- Nginx 配置（反向代理 + TLS 终结 + 100MB 上传限制 + gzip）
- Celery 配置（Redis broker + document/orchestration 队列）
- Prometheus + Grafana 配置
- `deploy.sh`：一键启动/停止脚本
- 各服务的共享 Python 包（pydantic models、配置加载器、结构化日志格式）

---

### M8 — 用户权限服务（`services/user-service/`）

**输入**：概要设计第6.2/8章、详细设计第9章、`doc/tasks/user-service.md`

**关键交付物**：
- FastAPI 项目骨架 + 配置管理（.env 读取）
- 本地认证：bcrypt 密码验证 + JWT 签发（access 2h / refresh 24h）
- Token 黑名单（Redis set，logout 时加入）
- RBAC 权限矩阵（4角色 × 6操作）
- LDAP/SSO 认证（bind → 查找/创建用户 → 组映射同步）
- 用户 CRUD API（管理员权限校验）
- 项目组 CRUD + 成员管理
- 项目 CRUD API（按用户 group_ids 过滤可见项目）
- 审计日志消费者（Redis pub/sub `audit:log` → 写入 audit_logs 表，仅 INSERT，无 UPDATE/DELETE 权限）
- GDPR 数据主体权利 API（访问/删除/可携带/同意管理）
- 内部接口：`GET /internal/users/{user_id}/permissions`、`POST /internal/permissions/check`

---

### M5 — LLM 路由服务（`services/llm-router/`）

**输入**：概要设计第3.4章、详细设计第6章、`doc/tasks/llm-router.md`

**关键交付物**：
- ModelRegistry：维护可用模型列表（claude-sonnet-4-6、local:qwen3、local:deepseek-v3）
- 路由决策引擎：auto → sensitivity(high→local, low→cloud)，指定 model → 直接使用
- ClaudeAdapter：统一格式 ↔ Anthropic Messages API（含 system message 独立字段、tool_use 双向转换）
- LocalAdapter：统一格式 ↔ OpenAI-compatible `/v1/chat/completions`（含 function-calling 转换）
- 降级策略：Claude API 不可达 → 自动降至本地 LLM（sensitivity 允许时）
- 熔断器：连续失败 N 次 → 短时间内直接 503
- 重试：429 指数退避(base=2s)×3，5xx 线性退避(1s)×2
- Token 追踪：每次调用记录 usage 到 llm_usage_logs
- 内部端点：`POST /internal/llm/chat`、`GET /internal/llm/models`

---

### M6 — 来源溯源服务（`services/citation-service/`）

**输入**：概要设计第3.5章、详细设计第7章、`doc/tasks/citation-service.md`

**关键交付物**：
- Inline 引用解析器：正则提取 `[ref:doc_id:page_range]`（单/多引用 + uncertain）
- 句子分割器：中英文标点分割，建立 sentence → refs 映射
- 引用校验器：页码范围匹配 → 语义相似度(cosine > 0.85) → 置信度判定(direct/fuzzy/uncertain)
- 引用格式化器：Markdown GFM 脚注 `[^n]`、.docx 脚注/尾注、.xlsx 引用清单 sheet、.pptx 引用文本
- API：`POST /internal/citations/verify`、`GET /api/tasks/{task_id}/output/citations`、`GET /api/tasks/{task_id}/output/citations/{citation_id}`
- 引用数据持久化到 citations 表

---

### M1 — API 网关（`api-gateway/`）

**输入**：概要设计第2.2/5章、详细设计第2章、`doc/tasks/api-gateway.md`

**关键交付物**：
- JWT 认证中间件（解析 Authorization header → 注入 request.state.user）
- RBAC 权限校验中间件（路由 + 角色 → 允许/拒绝，返回 403 含详情）
- Redis Token Bucket 限流中间件（user_id/IP 维度，429 + Retry-After）
- 审计日志中间件（自动捕获操作 → Redis pub/sub `audit:log`）
- 路由注册表（路径前缀 → 目标服务的配置化映射）
- 统一错误响应格式化 `{"error": {"code": "...", "message": "..."}}`
- CORS 中间件 + 请求体大小限制(100MB) + X-Request-ID 注入
- Health check `GET /health`
- Token 刷新端点 `POST /api/auth/refresh`
- Prometheus metrics 暴露 `GET /metrics`

**注意**：API 网关**不包含**业务逻辑，所有请求透明代理到后端服务。使用 httpx 或 aiohttp 做反向代理。

---

### M2 — 文档解析服务（`services/document-service/`）

**输入**：概要设计第3.1章、详细设计第3章、`doc/tasks/document-service.md`

**关键交付物**：
- 文档上传端点（multipart/form-data，文件校验：扩展名/MIME/magic bytes/大小限制）
- MinIO 存储客户端封装
- 格式识别器（magic bytes + 扩展名 → 统一 format 枚举）
- 8 种格式解析器：PDF(PyMuPDF/pdfplumber)、Word(python-docx)、Markdown/文本、Excel/CSV(openpyxl/pandas)、PowerPoint(python-pptx)、邮件(email)、HTML/MHTML(BeautifulSoup)、图片/Tesseract OCR
- 元数据提取（标题/作者/日期/来源/页数）
- 多粒度分块引擎：
  - 段落级：目标300tokens，最小100，最大500，重叠50，自然段落边界对齐
  - 章节级：目标2000tokens，最小500，最大3000，重叠100，章节标题对齐
- 文档状态机：pending → parsing → ready/error
- Celery 异步解析任务（`document` 队列）
- 解析完成后通过 Redis pub/sub 发布索引事件到 `kb:index:request`
- CRUD 端点：列表(分页+过滤)/详情/删除(级联)/重新索引
- 错误处理：解析异常 → parse_status=error + parse_error 详情

---

### M7 — 输出生成服务（`services/output-service/`）

**输入**：概要设计第3.6章、详细设计第8章、`doc/tasks/output-service.md`

**关键交付物**：
- Markdown 生成器（Jinja2）：YAML front-matter + 章节 + `[ref:...]`→`[^n]` 脚注替换 + 文末引用清单
- .docx 生成器（GB/T 9704 公文国标）：
  - 版头：发文机关标志 + 发文字号 + 签发人
  - 主体：标题(二号小标宋体，居中) + 正文(三号仿宋，首行缩进2字符，1.5倍行距) + 引用角标(上标)
  - 一级标题三号黑体，二级标题三号楷体
  - 版记：抄送机关 + 印发日期
  - 文末参考文献清单
- .xlsx 生成器：对比分析 sheet + 引用清单 sheet + 数据摘要 sheet
- .pptx 生成器：封面 + 目录 + 关键发现页 + 结论 + 末页引用清单
- 格式模板管理（YAML 配置文件，fallback 到内置默认值）
- MinIO 输出上传客户端
- API：`POST /internal/output/generate`、`GET /api/tasks/{task_id}/export?format=`
- task_outputs 表 CRUD

---

### M3 — 知识库服务（`services/kb-service/`）

**输入**：概要设计第3.2章、详细设计第4章、`doc/tasks/kb-service.md`

**关键交付物**：
- Embedding 客户端封装（text2vec-large-chinese / m3e，768d 或 1024d）+ 批量生成 + Redis 缓存
- 向量数据库客户端（Milvus/Qdrant 统一接口，通过配置切换）：写入/检索/删除/索引管理
- PostgreSQL FTS BM25 索引：tsvector 列 + GIN 索引 + 中文分词搜索
- 混合检索主流程：
  1. 并行向量检索(top_k=50) + BM25检索(top_k=50)
  2. RRF 融合（k=60，`score = Σ 1/(k+rank)`）→ top_k=30
  3. BGE-Reranker 重排序 → top_k=10
- Redis pub/sub 消费者：监听 `kb:index:request` → 完整索引流水线
- 知识库隔离：project_id 过滤器（项目KB）+ group_ids 过滤器（机构KB）
- API：`POST /api/projects/{project_id}/search`、`POST /api/institutional/search`、`POST /internal/search`
- 生命周期管理：归档/恢复/级联删除索引

---

### M4 — 任务编排服务（`services/orchestration-service/`）

**输入**：概要设计第3.3/7章、详细设计第5章、`doc/tasks/orchestration-service.md`

**关键交付物**：
- 任务管理 API：创建/列表/详情/状态轮询/取消/重试
- 任务状态机：pending → running → completed/failed/cancelled（含状态转换校验）
- **Agent 引擎**（核心）：
  - AgentState：messages + retrieved_chunks + generated_sections + citations + plan + iteration + remaining_sections + tool_call_history
  - AgentLoopRunner：while 循环（max 5 迭代），Plan → Execute → Observe → Update Progress
  - Plan 步骤：构建 planning messages → 调用 LLM Router → 解析 tool_call/finish
  - Terminal 判定：finish 或 iteration >= 5 或 fatal_error
  - 达到最大迭代兜底：使用已有内容强制 format_output
- **6 个 Agent 工具**：
  1. `search_kb`：调用 kb-service `/internal/search`
  2. `generate_section`：构建生成 prompt → LLM → 解析带 [ref:] 的输出
  3. `verify_citations`：调用 citation-service `/internal/citations/verify`
  4. `extract_key_claims`：LLM 提取结构化论点
  5. `compare_policies`：LLM 生成对比文本 + 矩阵
  6. `format_output`：收集 sections + citations → output-service
- ToolRegistry：注册/查找/列出工具定义（含 JSON Schema）
- Tool 调用通用框架：超时 60s + 重试 1 次 + 异常隔离
- 4 种任务类型的 Jinja2 提示词模板：
  - `literature_review.j2`：全局论点检索 → 按章节逐步生成 → 每章 verify
  - `policy_draft.j2`：背景/依据/措施/实施/评估
  - `policy_comparison.j2`：要素提取 → 多维对比 → 优劣势分析
  - `tech_interpretation.j2`：标准检索 → 条款解读 → 合规影响 → 实施建议
- 敏感度判定：内部文档→high、policy_draft→high、用户指定优先、默认low
- 进度追踪：每个 tool 后更新 progress JSONB（step/step_index/total_steps_estimate/message/details）
- 容错：tool 超时跳过、LLM 输出不可解析 fallback、大量 uncertain 继续输出、Celery 30min 超时兜底
- 输出/导出 API：预览(GET)、引用列表(GET)、文件导出(GET)

---

### M9 — 前端 SPA（`frontend/`）

**输入**：概要设计第2.1/5章、详细设计第2/5/7章、`doc/tasks/frontend.md`

**关键交付物**：
- Vite + React 19 + TypeScript 5 + Ant Design/Shadcn 项目骨架
- React Router 路由：登录页、项目列表、项目详情(子路由：知识库/任务)、管理页
- API 客户端层：axios 封装 + Auth Context + token 自动刷新(401 → refresh → 重试) + useRequest hook
- 认证：登录页面 + 登出 + 路由守卫
- 项目视图：列表(表格/分页/过滤) + 创建对话框 + 详情 + 归档
- 知识库视图：拖拽上传(进度条) + 文档列表(状态过滤) + 详情面板 + 搜索组件(高亮+分数)
- 任务视图：创建对话框(4种类型+表单) + 列表(状态过滤) + 进度轮询 + 步骤进度条
- 输出视图：Markdown 渲染(引用角标可点击) + 引用 Popover(原文摘录+置信度) + 置信度颜色标签(direct绿/fuzzy黄/uncertain红) + 引列表面板
- 导出：格式选择 → 触发下载
- 管理视图：用户管理(CRUD+停用) + 项目组管理 + 审计日志查看(过滤+分页)
- 通用组件：Layout(侧边导航+顶部栏+面包屑)、404/403/500、Toast 通知、全局 Loading

---

## 7. 技术栈约定

| 层次 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI 0.115+ | 所有微服务统一使用 |
| ASGI | Gunicorn + Uvicorn | 生产部署 |
| 异步任务 | Celery 5.x + Redis 7.x | 文档解析 + Agent 分析 |
| 业务数据库 | PostgreSQL 16+ | FTS、JSONB |
| 向量数据库 | Milvus / Qdrant | 10万级向量索引 |
| 对象存储 | MinIO | S3 兼容，私有化 |
| ORM | SQLAlchemy 2.x (async) | 异步数据库操作 |
| 数据迁移 | Alembic | 版本化 schema |
| 前端 | React 19 + TypeScript 5 | Vite 构建 |
| UI 库 | Ant Design / Shadcn | 企业级组件 |
| 测试 | pytest + pytest-asyncio + pytest-mock | 纯 mock，无外部依赖 |
| 类型检查 | mypy --strict | 零容忍 |
| 代码规范 | ruff | 替代 flake8/isort/black |
| 包管理 | pyproject.toml (setuptools 或 poetry) | 每个服务独立 |
| 容器化 | Docker + Docker Compose | 私有化部署 |

---

## 8. 代码规范

### Python 后端

- 所有函数必须有完整的类型注解
- 使用 Pydantic v2 模型做请求/响应校验
- FastAPI 路由使用 async def（除非有同步阻塞操作）
- 数据库操作使用 SQLAlchemy 2.x async session
- 配置通过 pydantic-settings 从环境变量/.env 读取
- 日志使用 structlog 或标准 logging（JSON 格式）
- 错误响应统一格式：`{"error": {"code": "ERROR_CODE", "message": "..."}}`

### TypeScript 前端

- 严格模式 TypeScript（strict: true）
- 使用 React Query / useRequest 管理服务端状态
- API 客户端集中管理，类型与后端 Pydantic models 对应
- 组件按功能分目录，共享组件放 `components/common/`

---

## 9. 进度跟踪

每个子 Agent 完成后，你需要更新 `doc/tasks/progress.md` 中的状态：

```markdown
| M1 | API 网关 | `api-gateway/` | 28 | [x] 已完成 (2026-05-XX) |
```

同时维护一个全局状态摘要，记录：
- 当前 Wave
- 已完成模块（含测试数量、覆盖率估计）
- 进行中模块
- 待开始模块
- 遇到的问题和解决方案

---

## 10. 最终验收

所有模块完成后，执行全量质量检查：

```bash
# 后端全量检查
find . -name "pyproject.toml" -not -path "*/node_modules/*" | while read f; do
    dir=$(dirname "$f")
    echo "=== $dir ==="
    (cd "$dir" && pytest --tb=short && mypy . --strict && ruff check .)
done

# 前端检查
cd frontend && npm run lint && npm run typecheck && npm test

# Docker Compose 启动测试
docker compose up -d && docker compose ps  # 所有服务 healthy
```

---

## 11. 参考文档索引

子 Agent 在实现时需要查阅以下文档：

| 文档 | 路径 | 内容 |
|------|------|------|
| 概要设计 | `doc/high-level-design.md` | 系统架构、模块职责、数据流、API 设计、Agent 循环、安全架构、部署拓扑 |
| 详细设计 | `doc/detailed-design.md` | 每个模块的 API 接口(请求/响应)、内部接口、数据模型、状态机、算法伪代码、配置项 |
| 任务清单 | `doc/tasks/*.md` | 每个模块的子任务列表（checklist 格式） |
| 进度跟踪 | `doc/tasks/progress.md` | 模块依赖关系、建议开发顺序、进度总表 |

---

## 12. 开始

现在，从 **Wave 1** 开始。并行启动以下 4 个子 Agent：

1. **M10** — 基础设施与部署（34 个子任务）
2. **M8** — 用户权限服务（42 个子任务）
3. **M5** — LLM 路由服务（33 个子任务）
4. **M6** — 来源溯源服务（30 个子任务）

每个子 Agent 会收到指向 `doc/tasks/<module>.md` 的完整任务清单和上述设计文档的路径，按任务清单逐项实现。完成后通过质量门禁并自动 git commit。
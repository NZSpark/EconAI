# EconAI 详细设计文档

> 版本：v1.2 | 日期：2026-05-25 | 基于概要设计文档 v1.0

---

## 1. 文档说明

### 1.1 目的与范围

本文档对 EconAI 系统的全部服务模块进行接口级详细设计，明确各模块的：
- 外部 API 接口（RESTful 端点 + 请求/响应模型）
- 内部服务间调用接口（同步 RPC + 异步消息）
- 数据模型定义（逻辑模型 + 物理表映射）
- 状态机与关键流程
- 核心算法伪代码
- 错误处理策略
- 配置项清单

本文档面向后端开发工程师和集成测试工程师，开发人员可据此完成模块编码，测试人员可据此编写集成测试用例。

### 1.2 与概要设计的关系

概要设计文档定义了系统架构、模块划分、核心决策和数据流。本文档在此基础上对每个模块进行接口级细化，但不包含具体的类定义、函数签名或代码实现细节。

### 1.3 模块索引

| 编号 | 模块 | 目录 | 概要设计章节参考 |
|------|------|------|-----------------|
| M1 | API 网关 | `api-gateway/` | 2.2, 5.1 |
| M2 | 文档解析服务 | `services/document-service/` | 3.1 |
| M3 | 知识库服务 | `services/kb-service/` | 3.2 |
| M4 | 任务编排服务 | `services/orchestration-service/` | 3.3, 7 |
| M5 | LLM 路由服务 | `services/llm-router/` | 3.4 |
| M6 | 来源溯源服务 | `services/citation-service/` | 3.5 |
| M7 | 输出生成服务 | `services/output-service/` | 3.6 |
| M8 | 用户权限服务 | `services/user-service/` | 8.1, 8.2 |

---

## 2. M1 API 网关

### 2.1 模块定位

API 网关是系统的唯一入口，负责认证鉴权、限流、RBAC 权限校验和审计日志记录。所有客户端请求经过网关后才能到达后端服务。

### 2.2 中间件管道

```
请求 → TLS 终结(Nginx) → JWT 认证 → RBAC 权限校验 → 限流检查 → 审计日志 → 路由到后端服务
```

### 2.3 JWT 认证

#### Token 结构

```json
{
  "header": {"alg": "HS256", "typ": "JWT"},
  "payload": {
    "sub": "user-uuid",
    "username": "zhangsan",
    "role": "senior_researcher",
    "group_ids": ["g-001", "g-002"],
    "exp": 1715952000,
    "iat": 1715944800
  }
}
```

| 字段 | 说明 |
|------|------|
| `sub` | 用户 UUID |
| `username` | 登录名 |
| `role` | 系统角色：analyst / senior_researcher / project_admin / system_admin |
| `group_ids` | 所属项目组 ID 列表 |
| `exp` | 过期时间（access token: 2h, refresh token: 24h） |
| `iat` | 签发时间 |

#### Token 刷新流程

```
Client                          API Gateway
  │                                  │
  ├─ POST /api/auth/login ──────────→│ 返回 access_token + refresh_token
  │                                  │
  │  ... 正常请求带 access_token ...  │
  │                                  │
  ├─ 收到 401 ───────────────────────│ access_token 过期
  │                                  │
  ├─ POST /api/auth/refresh ────────→│ 验证 refresh_token
  │  (带 refresh_token)              │ 返回新的 access_token + refresh_token
```

### 2.4 RBAC 权限模型

```
权限矩阵:
                    查看项目  创建项目  上传文档  创建任务  管理用户  查看审计
analyst             本组      ✗       本组      本组      ✗        ✗
senior_researcher   本组     本组     本组      本组      ✗        ✗
project_admin       本组     本组     本组      本组      本组      ✗
system_admin        全部     全部     全部      全部      全部      全部
```

### 2.5 限流策略

| 限流维度 | 默认值 | 配置项 |
|----------|--------|--------|
| 每用户请求频率 | 100 req/min | `RATE_LIMIT_PER_USER` |
| 每 IP 请求频率 | 300 req/min | `RATE_LIMIT_PER_IP` |
| 文档上传频率 | 20 req/min | `RATE_LIMIT_UPLOAD` |
| 任务创建频率 | 10 req/min | `RATE_LIMIT_TASK_CREATE` |

实现方式：Redis Token Bucket，key 格式 `ratelimit:{user_id}:{endpoint_group}`。

### 2.6 审计日志中间件

自动记录以下信息到 `audit_logs` 表：

```json
{
  "user_id": "uuid",
  "action": "create_task",
  "resource_type": "task",
  "resource_id": "task-uuid",
  "details": {"task_type": "literature_review", "project_id": "proj-uuid"},
  "ip_address": "10.0.1.25",
  "user_agent": "Mozilla/5.0 ...",
  "created_at": "2026-05-17T10:30:00Z"
}
```

### 2.7 路由表

| 路径前缀 | 目标服务 | 说明 |
|----------|----------|------|
| `/api/auth/*` | user-service | 认证端点 |
| `/api/projects/*` | user-service | 项目管理（需要项目上下文） |
| `/api/projects/{id}/documents/*` | document-service | 文档相关 |
| `/api/projects/{id}/search` | kb-service | 项目知识库搜索 |
| `/api/institutional/search` | kb-service | 机构知识库搜索 |
| `/api/projects/{id}/tasks/*` | orchestration-service | 任务管理 |
| `/api/tasks/{id}/*` | orchestration-service | 任务状态/输出 |
| `/api/admin/*` | user-service | 管理端点（需 system_admin 或 project_admin） |

### 2.8 错误响应格式

所有 API 错误统一格式：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "人类可读的错误描述",
    "details": {}
  }
}
```

| HTTP 状态码 | 场景 |
|-------------|------|
| 400 | 请求参数校验失败 |
| 401 | 未认证或 token 过期 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 429 | 触发限流 |
| 500 | 服务内部错误 |
| 503 | 服务不可用（依赖服务未就绪） |

### 2.9 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `JWT_SECRET` | (必填) | JWT 签名密钥 |
| `JWT_ACCESS_EXPIRE_MINUTES` | 120 | access token 有效期 |
| `JWT_REFRESH_EXPIRE_HOURS` | 24 | refresh token 有效期 |
| `RATE_LIMIT_PER_USER` | 100 | 每用户每分钟最大请求数 |
| `RATE_LIMIT_PER_IP` | 300 | 每 IP 每分钟最大请求数 |
| `AUDIT_LOG_ENABLED` | true | 是否开启审计日志 |
| `CORS_ORIGINS` | `["*"]` | 允许的跨域来源 |
| `MAX_REQUEST_SIZE_MB` | 100 | 请求体最大体积 |

---

## 3. M2 文档解析服务

### 3.1 模块定位

接收用户上传的文档，完成格式识别、内容提取、结构化分块，将结构化数据写入 PostgreSQL 和 MinIO，供知识库服务消费。

### 3.2 API 接口

#### 3.2.1 上传文档

```
POST /api/projects/{project_id}/documents
Content-Type: multipart/form-data
```

**请求**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | binary | 是 | 文档文件 |
| `is_internal` | bool | 否 | 是否标记为内部文档（默认 false） |
| `metadata` | JSON string | 否 | 自定义元数据 `{"title":"", "authors":"", "date":"", "source":""}` |

**响应** (201):

```json
{
  "document_id": "doc-uuid",
  "filename": "report_2024.pdf",
  "format": "pdf",
  "size_bytes": 2048576,
  "parse_status": "pending",
  "created_at": "2026-05-17T10:30:00Z"
}
```

#### 3.2.2 查询文档列表

```
GET /api/projects/{project_id}/documents?page=1&page_size=20&status=ready&format=pdf
```

**响应**:

```json
{
  "items": [
    {
      "document_id": "doc-uuid",
      "original_name": "研究报告_2024.pdf",
      "format": "pdf",
      "size_bytes": 2048576,
      "page_count": 45,
      "parse_status": "ready",
      "metadata": {"title": "数字贸易规则研究", "authors": "张三", "date": "2024-03"},
      "is_internal": false,
      "chunk_count": 120,
      "created_at": "2026-05-17T10:30:00Z"
    }
  ],
  "total": 35,
  "page": 1,
  "page_size": 20
}
```

#### 3.2.3 获取文档详情

```
GET /api/projects/{project_id}/documents/{document_id}
```

**响应**：同列表项的完整版，额外包含 `parse_error`（解析失败时）和 `storage_path`。

#### 3.2.4 删除文档

```
DELETE /api/projects/{project_id}/documents/{document_id}
```

级联删除：MinIO 文件 + PostgreSQL chunks 记录 + 向量数据库中的对应向量。

#### 3.2.5 重新索引

```
POST /api/projects/{project_id}/documents/{document_id}/reindex
```

触发重新分块和索引，用于分块参数调整后的重新处理。

### 3.3 异步处理流水线

上传接口同步返回后，Celery 异步执行：

```
1. 文件存入 MinIO      → storage_path
2. 格式识别            → format (通过 magic bytes + 扩展名)
3. 内容提取            → full_text + structured_data
4. 图片提取与 OCR       → 提取文档中嵌入的图片（PDF/Word/PPT/HTML），通过 Tesseract 识别文字
5. 元数据提取          → metadata JSONB
6. 多粒度分块          → paragraph chunks + section chunks
7. 写入 PostgreSQL     → documents 表 + document_chunks 表
8. 发送索引事件        → Redis pub/sub (通知 KB Service)
```

### 3.4 格式处理器选择逻辑

```
输入: 文件扩展名 + MIME type + 文件头 magic bytes

if magic_bytes 表明是 PDF:
    if 文本层存在 (通过 PyMuPDF 检测):
        → PyMuPDF 提取文本 (保留页码和布局)
        → 提取嵌入图片 → Tesseract OCR → 追加到对应页面
    else:
        → Tesseract OCR 整页识别 → 同 PDF 文本提取流程

if 扩展名 in [.docx, .doc]:
    → python-docx 提取文本 + 段落样式 + 表格
    → 提取嵌入图片（关系部件） → Tesseract OCR → 追加到全文

if 扩展名 in [.xlsx, .xls, .csv]:
    → openpyxl / pandas 提取结构化表格

if 扩展名 in [.pptx, .ppt]:
    → python-pptx 提取逐页文本
    → 提取幻灯片中嵌入的图片 → Tesseract OCR → 追加到对应幻灯片

if 扩展名 == .eml:
    → email 标准库提取正文 + 元数据（发件人/日期/主题）

if 扩展名 in [.html, .mhtml, .mht]:
    → BeautifulSoup 提取正文（去掉导航/广告/脚本）
    → 提取 data-URI 内嵌图片（base64） → Tesseract OCR → 追加到全文

if 扩展名 in [.md, .txt]:
    → 直接读取文本
```

**图片提取与 OCR 共享模块** (`document_service/parsers/image_extractor.py`)：

| 函数 | 提取来源 | 说明 |
|------|---------|------|
| `ocr_image_bytes(image_bytes, language)` | 通用图像字节 | 调用 Tesseract OCR（默认 `chi_sim+eng`），优雅降级（pytesseract 不可用时返回 `[OCR not available]`） |
| `extract_images_from_pdf(file_data)` | PDF 页面嵌入图片 | 使用 PyMuPDF `get_images()` + `extract_image()` 逐页提取并 OCR |
| `extract_images_from_docx(file_data)` | DOCX 关系部件图片 | 遍历 `part.rels` 找到图片关系部件，提取并 OCR |
| `extract_images_from_pptx(file_data)` | PPTX 幻灯片形状图片 | 遍历所有幻灯片中 `MSO_SHAPE_TYPE.PICTURE` 类型的形状，提取并 OCR |
| `extract_images_from_html(file_data)` | HTML data-URI 图片 | 正则匹配 `<img src="data:image/...">` 标签，解码 base64 后 OCR |

所有提取函数返回统一结构：`[{page, image_index, ocr_text, format, width, height}, ...]`。

### 3.5 多粒度分块算法

```
输入: full_text, page_map (文本→页码映射), structure (章节树)
输出: paragraph_chunks[], section_chunks[]

# 段落级分块
paragraphs = split_by_natural_boundary(full_text)  # 按 \n\n 分割
for each paragraph:
    tokens = count_tokens(paragraph)
    if tokens < MIN_PARAGRAPH_TOKENS (100):
        merge_with_next(paragraph)  # 合并到下一个段落
    elif tokens > MAX_PARAGRAPH_TOKENS (500):
        split_by_sentence_boundary(paragraph)  # 按句子边界拆分
    # 确保 chunk 在自然段落边界上对齐
    add_overlap_with_prev(50 tokens)

# 章节级分块
for each section in structure_tree:
    section_text = extract_section_content(section)
    tokens = count_tokens(section_text)
    if tokens > MAX_SECTION_TOKENS (3000):
        split_by_subsection(section)  # 按子章节拆分
    elif tokens < MIN_SECTION_TOKENS (500):
        merge_with_next_section(section)
    add_overlap_with_prev(100 tokens)
```

### 3.6 文档状态机

```
pending ──→ parsing ──→ ready
                │
                ├──→ error ──→ (可重试: POST reindex)
                │
                └──→ (用户删除 → deleted)
```

### 3.7 内部服务接口

文档解析完成后，通过 Redis pub/sub 发布索引事件：

```
频道: kb:index:request
消息:
{
  "document_id": "doc-uuid",
  "project_id": "proj-uuid", 
  "chunk_ids": ["chunk-001", "chunk-002", ...],
  "is_internal": false,
  "timestamp": "2026-05-17T10:35:00Z"
}
```

### 3.8 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO 地址 |
| `MINIO_BUCKET` | `econai-documents` | 文档存储 bucket |
| `CHUNK_PARAGRAPH_TARGET_TOKENS` | 300 | 段落级目标 token 数 |
| `CHUNK_PARAGRAPH_MIN_TOKENS` | 100 | 段落级最小 token 数 |
| `CHUNK_PARAGRAPH_MAX_TOKENS` | 500 | 段落级最大 token 数 |
| `CHUNK_SECTION_TARGET_TOKENS` | 2000 | 章节级目标 token 数 |
| `CHUNK_SECTION_MIN_TOKENS` | 500 | 章节级最小 token 数 |
| `CHUNK_SECTION_MAX_TOKENS` | 3000 | 章节级最大 token 数 |
| `CHUNK_PARAGRAPH_OVERLAP` | 50 | 段落级重叠 token 数 |
| `CHUNK_SECTION_OVERLAP` | 100 | 章节级重叠 token 数 |
| `OCR_LANGUAGE` | `chi_sim+eng` | Tesseract 语言包（用于所有 parsers 中的图片 OCR 识别） |
| `MAX_FILE_SIZE_MB` | 100 | 最大上传文件大小 |
| `CELERY_DOCUMENT_QUEUE` | `document` | 文档处理任务队列名 |

---

## 4. M3 知识库服务

### 4.1 模块定位

管理知识库的生命周期，消费文档解析服务的索引事件，执行向量化和索引存储，提供混合检索能力。

### 4.2 API 接口

#### 4.2.1 搜索项目知识库

```
POST /api/projects/{project_id}/search
```

**请求**:

```json
{
  "query": "数字贸易规则对发展中国家的影响",
  "top_k": 10,
  "filters": {
    "document_ids": ["doc-001", "doc-002"],
    "chunk_types": ["paragraph"],
    "date_range": {"start": "2020-01-01", "end": "2024-12-31"}
  },
  "search_mode": "hybrid"
}
```

**响应**:

```json
{
  "results": [
    {
      "chunk_id": "chunk-uuid",
      "document_id": "doc-001",
      "document_title": "数字贸易规则研究",
      "content": "近年来，数字贸易规则已成为...",
      "chunk_type": "paragraph",
      "score": 0.92,
      "metadata": {
        "page_start": 12,
        "page_end": 13,
        "section_title": "发展中国家影响分析",
        "paragraph_index": 3
      }
    }
  ],
  "total_hits": 45,
  "search_time_ms": 120
}
```

#### 4.2.2 搜索机构知识库

```
POST /api/institutional/search
```

请求格式同上，增加 `group_ids` 过滤器用于跨组授权。

### 4.3 索引流水线

```
监听 Redis pub/sub: kb:index:request
    │
    ├──→ 读取 document_chunks (从 PostgreSQL)
    │
    ├──→ 向量化 (text2vec / m3e embedding)
    │     每个 chunk → 768d 或 1024d 向量
    │
    ├──→ 写入向量数据库 (Milvus / Qdrant)
    │     collection: econai_chunks
    │     字段: chunk_id, vector, project_id, document_id, chunk_type
    │
    ├──→ 更新 BM25 索引 (PostgreSQL FTS)
    │     tsvector 列自动更新
    │
    └──→ 更新 documents.parse_status = 'ready'
```

### 4.4 混合检索算法

```
输入: query (自然语言), project_id, top_k, filters
输出: top_k 个最相关 chunk

# 并行检索
vector_results = vector_search(query_embedding, filters, top_k=50)
bm25_results = bm25_search(query_text, filters, top_k=50)

# RRF 融合 (Reciprocal Rank Fusion)
k = 60
scores = {}
for each result in vector_results:
    scores[result.id] += 1 / (k + result.rank)
for each result in bm25_results:
    scores[result.id] += 1 / (k + result.rank)

merged = sort_by_score(scores)[:30]

# Reranker 重排序
for each candidate in merged:
    rerank_score = cross_encoder(query, candidate.content)  # BGE-Reranker
    candidate.final_score = 0.7 * candidate.rrf_score + 0.3 * rerank_score

return sort_by_final_score(merged)[:top_k]
```

### 4.5 知识库隔离实现

```
搜索时的权限过滤器注入：

def build_search_filters(user, project_id, kb_sources):
    filters = {"project_id": project_id}

    # 验证用户对项目的访问权限
    if not user_can_access_project(user, project_id):
        raise PermissionDenied

    # 如果是机构知识库搜索
    if kb_sources.include_institutional:
        filters["allowed_groups"] = user.group_ids

    return filters
```

### 4.6 知识库生命周期

```
文档上传 → 解析完成 → 自动索引 → active
                              │
                              ├──→ 项目归档 → archived (保留索引，不参与搜索)
                              │
                              ├──→ 手动删除 → deleted
                              │     └──→ 级联删除: chunks + vectors + BM25
                              │
                              └──→ 重新索引 → active (分块策略调整后)
```

### 4.7 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `VECTOR_DB_TYPE` | `milvus` | 向量数据库类型 (milvus / qdrant) |
| `VECTOR_DB_HOST` | `localhost` | 向量数据库地址 |
| `VECTOR_DB_PORT` | 19530 | 向量数据库端口 |
| `EMBEDDING_MODEL` | `text2vec-large-chinese` | embedding 模型 |
| `EMBEDDING_DIM` | 1024 | 向量维度 |
| `HYBRID_VECTOR_TOP_K` | 50 | 向量检索候选数 |
| `HYBRID_BM25_TOP_K` | 50 | BM25 检索候选数 |
| `HYBRID_RRF_K` | 60 | RRF 融合参数 k |
| `HYBRID_MERGED_TOP_K` | 30 | 融合后候选数 |
| `RERANKER_MODEL` | `bge-reranker-large` | 重排序模型 |
| `SEARCH_DEFAULT_TOP_K` | 10 | 默认返回结果数 |
| `SEARCH_TIMEOUT_MS` | 5000 | 搜索超时时间 |

---

## 5. M4 任务编排服务

### 5.1 模块定位

任务编排服务是系统的核心大脑。它管理分析任务的全生命周期，运行自研轻量 Agent 循环引擎，通过调用 LLM 路由和知识库服务完成智能分析，并将结果交付给输出生成和来源溯源服务。

### 5.2 API 接口

#### 5.2.1 创建分析任务

```
POST /api/projects/{project_id}/tasks
```

**请求**:

```json
{
  "type": "literature_review",
  "title": "数字贸易规则对发展中国家的影响综述",
  "description": "综述近年关于数字贸易规则对发展中国家经济影响的学术文献和政策报告",
  "kb_sources": {
    "documents": ["doc_001", "doc_002", "doc_003"],
    "include_institutional": false
  },
  "output_formats": ["docx", "md"],
  "llm_preference": "auto",
  "analysis_params": {
    "focus_areas": ["经济影响", "政策建议", "实施挑战"],
    "comparison_dimensions": [],
    "methodology_quality": true
  }
}
```

**字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | enum | 是 | literature_review / policy_draft / policy_comparison / tech_interpretation |
| `title` | string | 是 | 任务标题 |
| `description` | string | 否 | 任务描述，作为 LLM 的附加上下文 |
| `kb_sources.documents` | UUID[] | 是 | 指定使用的文档 ID 列表 |
| `kb_sources.include_institutional` | bool | 否 | 是否包含机构知识库 |
| `output_formats` | enum[] | 是 | 输出格式，支持 md / docx / xlsx / pptx |
| `llm_preference` | enum | 否 | auto / local / cloud |
| `analysis_params` | object | 是 | 任务类型特定的分析参数 |

**响应** (201):

```json
{
  "task_id": "task-uuid",
  "status": "pending",
  "created_at": "2026-05-17T10:30:00Z"
}
```

#### 5.2.2 查询任务列表

```
GET /api/projects/{project_id}/tasks?page=1&page_size=20&status=running&type=literature_review
```

**响应**: 分页任务列表，每项包含 `task_id`, `type`, `title`, `status`, `progress`, `created_by`, `created_at`。

#### 5.2.3 获取任务详情

```
GET /api/tasks/{task_id}
```

**响应**:

```json
{
  "task_id": "task-uuid",
  "project_id": "proj-uuid",
  "type": "literature_review",
  "title": "...",
  "description": "...",
  "status": "running",
  "progress": {
    "step": "generating",
    "step_index": 3,
    "total_steps_estimate": 8,
    "message": "正在生成研究方法论比较章节..."
  },
  "params": {...},
  "llm_route": "cloud",
  "sensitivity": "low",
  "iteration_count": 2,
  "error_message": null,
  "created_by": "user-uuid",
  "created_at": "...",
  "started_at": "...",
  "completed_at": null
}
```

#### 5.2.4 获取任务状态（轮询）

```
GET /api/tasks/{task_id}/status
```

**响应**（精简版，用于前端轮询）:

```json
{
  "status": "running",
  "progress": {
    "step": "retrieving",
    "step_index": 2,
    "total_steps_estimate": 8,
    "message": "正在检索相关政策文献..."
  }
}
```

#### 5.2.5 取消任务

```
POST /api/tasks/{task_id}/cancel
```

请求 Celery 撤销任务（revoke），将状态设为 `cancelled`。

#### 5.2.6 重试任务

```
POST /api/tasks/{task_id}/retry
```

仅 `failed` 状态的任务可重试，创建新的 Celery 任务。

### 5.3 任务状态机

```
                    ┌──────────┐
                    │  pending  │
                    └────┬─────┘
                         │ Celery Worker 领取
                         ▼
                    ┌──────────┐
            ┌───────│  running  │───────┐
            │       └────┬─────┘       │
            │            │             │
            │            ▼             │
            │       ┌──────────┐       │
            │       │completed │       │
            │       └──────────┘       │
            │                          │
            │  (可重试)                 │  (不可恢复)
            ▼                          ▼
       ┌──────────┐              ┌──────────┐
       │  failed  │              │cancelled │
       └──────────┘              └──────────┘
```

**状态转换规则**:

| 当前状态 | 允许的目标状态 | 触发条件 |
|----------|---------------|----------|
| pending | running | Celery Worker 开始执行 |
| pending | cancelled | 用户在任务开始前取消 |
| running | completed | Agent 循环正常结束 |
| running | failed | 异常、超时、Agent 达到最大迭代 |
| running | cancelled | 用户主动取消 |
| failed | running | 用户点击重试 |
| completed | - | 终态 |
| cancelled | - | 终态 |

### 5.4 Agent 引擎设计

#### 5.4.1 核心循环

```
AgentState:
  messages: list[Message]          # LLM 对话历史
  retrieved_chunks: list[Chunk]    # 已检索的所有 chunk
  generated_sections: list[Section] # 已生成的章节
  citations: dict[str, Citation]   # ref_id → Citation 映射
  plan: str                        # 当前执行计划
  iteration: int                   # 当前迭代轮次
  remaining_sections: list[str]    # 待完成的章节
  tool_call_history: list[ToolCall] # 工具调用历史

Loop(max_iterations=5):
  1. Plan:  LLM 分析当前状态，决定下一步 action
     - action = "tool_call" → tool_name + tool_args
     - action = "finish"    → 退出循环

  2. Execute: 调用指定 tool(tool_args, state)
     每个 tool 返回结构化结果

  3. Observe: 将 tool 结果追加到 state.messages

  4. Update Progress: 更新 task.progress JSONB

  5. iteration += 1

  6. if action == "finish" or iteration >= MAX_ITERATIONS:
       break

Post-loop: Format → 调用 output-service 生成各格式文件
```

#### 5.4.2 工具定义

| 工具名 | 功能 | 输入 schema | 输出 schema |
|--------|------|-------------|-------------|
| `search_kb` | 混合检索知识库 | `{"query": "string", "filters": {}, "top_k": 10}` | `{"chunks": [{chunk_id, content, metadata, score}]}` |
| `generate_section` | LLM 生成章节内容 | `{"section_goal": "string", "section_title": "string", "context_chunk_ids": ["..."]}` | `{"content": "string with [ref:] marks", "word_count": 500}` |
| `verify_citations` | 校验引用准确性 | `{"text": "string", "chunk_ids": ["..."]}` | `{"report": [{"ref_id": "...", "confidence": "direct|fuzzy|uncertain"}]}` |
| `extract_key_claims` | 提取关键论点 | `{"text": "string"}` | `{"claims": [{"claim": "...", "source_ref": "...", "methodology": "..."}]}` |
| `compare_policies` | 多政策选项比较 | `{"policies": [{"name": "", "description": ""}], "dimensions": ["..."]}` | `{"comparison": "text", "matrix": [[...]]}` |
| `format_output` | 格式化最终输出 | `{"sections": ["..."], "citations": {}, "format": "md|docx|..."}` | `{"output_id": "...", "storage_path": "..."}` |

#### 5.4.3 按任务类型的 Agent 行为

**文献综述**:

```
Plan: 检索全局核心论点 → search_kb
  → generate_section("研究背景与范围")
  → verify_citations → Plan: 检索方法论差异
  → search_kb("方法论 实证研究 数据来源")
  → generate_section("方法论比较")
  → verify_citations → Plan: 检索政策建议
  → search_kb("政策建议 实施路径")
  → generate_section("政策建议汇总")
  → extract_key_claims → Plan: 检索研究空白
  → search_kb("研究局限 未来方向")
  → generate_section("研究空白与展望")
  → verify_citations → finish
  → format_output
```

**政策草案**:

```
Plan: 检索政策背景 → search_kb
  → generate_section("背景与必要性")
  → Plan: 检索相关法规依据 → search_kb
  → generate_section("政策依据")
  → generate_section("主要措施")
  → Plan: 检索实施方案参考 → search_kb
  → generate_section("组织实施方案")
  → generate_section("预期效果与评估")
  → verify_citations → finish → format_output
```

**政策比较**:

```
Plan: 提取各政策核心要素 → extract_key_claims(多个政策文本)
  → compare_policies(按指定维度)
  → generate_section("比较分析总览")
  → generate_section("各政策优劣势分析")
  → search_kb("政策实施效果 评估") → generate_section("实施效果比较")
  → verify_citations → finish → format_output
```

**技术解读**:

```
Plan: 检索技术标准原文 → search_kb
  → generate_section("技术标准概述")
  → generate_section("关键条款解读")
  → Plan: 检索合规影响分析 → search_kb
  → generate_section("合规影响分析")
  → generate_section("实施建议")
  → verify_citations → finish → format_output
```

### 5.5 敏感度判定

在任务创建时执行，确定 LLM 路由方向：

```
def determine_sensitivity(task, kb_sources):
    # 规则1：包含内部文档
    if any(doc.is_internal for doc in kb_sources):
        return "high"

    # 规则2：政策草案类型（通常基于内部文件）
    if task.type == "policy_draft":
        return "high"

    # 规则3：用户显式指定
    if task.llm_preference != "auto":
        return task.llm_preference

    # 规则4：默认非敏感
    return "low"
```

### 5.6 超时与容错

| 场景 | 策略 |
|------|------|
| Agent 循环超过最大迭代 (5轮) | 使用已有内容调用 format_output |
| 单个 tool 调用超时 (60s) | 重试 1 次，仍失败则跳过该步骤 |
| LLM 返回格式不可解析 | 使用 fallback 逻辑提取 tool_call；连续 2 次失败则终止 |
| Citation 校验发现大量 uncertain | 记录 warning 日志，仍完成输出但标记引用置信度 |
| Celery 任务超时 (30 min) | 任务标记为 failed，记录 `error_message` |

### 5.7 进度报告协议

Agent 每个步骤完成后更新 `analysis_tasks.progress`:

```json
{
  "step": "generating",
  "step_index": 3,
  "total_steps_estimate": 8,
  "message": "正在生成方法论比较章节...",
  "details": {
    "section_title": "研究方法论比较",
    "chunks_retrieved": 15,
    "generation_tokens": 1200
  }
}
```

`total_steps_estimate` 是预估值，随着 Agent 实际执行可能动态调整。

### 5.8 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `AGENT_MAX_ITERATIONS` | 5 | 最大迭代轮次 |
| `AGENT_TOOL_TIMEOUT_S` | 60 | 单个 tool 调用超时 |
| `AGENT_MAX_RETRIEVED_CHUNKS` | 30 | 累计最大检索 chunk 数 |
| `TASK_TIMEOUT_MINUTES` | 30 | 单个任务总超时 |
| `CELERY_ORCHESTRATION_QUEUE` | `orchestration` | 任务队列名 |
| `PROMPT_TEMPLATES_DIR` | `templates/prompts/` | 提示词模版目录 |

---

## 6. M5 LLM 路由服务

### 6.1 模块定位

统一管理 LLM 调用，根据数据敏感度自动路由到本地或云端模型，屏蔽不同 LLM 后端的差异，追踪 token 使用量。

### 6.2 API 接口

#### 6.2.1 Chat Completion（内部接口）

```
POST /internal/llm/chat
```

**请求**:

```json
{
  "model": "auto",
  "messages": [
    {"role": "system", "content": "你是经济政策分析助手..."},
    {"role": "user", "content": "请检索..."}
  ],
  "temperature": 0.3,
  "max_tokens": 4096,
  "stream": false,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_kb",
        "description": "混合检索知识库",
        "parameters": {...}
      }
    }
  ],
  "sensitivity": "low"
}
```

**响应**:

```json
{
  "id": "resp-uuid",
  "model": "claude-sonnet-4-6",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "...",
        "tool_calls": []
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1500,
    "completion_tokens": 800,
    "total_tokens": 2300
  },
  "routing": {
    "target": "cloud",
    "reason": "sensitivity_low"
  }
}
```

#### 6.2.2 模型列表

```
GET /internal/llm/models
```

**响应**:

```json
{
  "models": [
    {"id": "auto", "description": "自动路由"},
    {"id": "claude-sonnet-4-6", "provider": "anthropic", "type": "cloud"},
    {"id": "local:qwen3-72b", "provider": "vllm", "type": "local"},
    {"id": "local:deepseek-v3", "provider": "vllm", "type": "local"}
  ],
  "default_local": "local:qwen3-72b",
  "default_cloud": "claude-sonnet-4-6"
}
```

### 6.3 路由决策流程

```
输入: request (messages + tools + sensitivity)

1. 确定目标模型:
   if request.model != "auto":
       target = request.model
   elif sensitivity == "high":
       target = default_local_model
   else:
       target = default_cloud_model

2. 选择适配器:
   if target starts with "claude":
       adapter = ClaudeAdapter
   elif target starts with "local:" or provider is vllm/ollama:
       adapter = LocalAdapter (OpenAI-compatible)

3. 适配器转换请求:
   ClaudeAdapter: 直接使用 Anthropic SDK 格式
   LocalAdapter:  转换为 OpenAI Chat Completions 格式

4. 调用 LLM

5. 统一响应格式:
   将各适配器的输出标准化为上述统一格式

6. 记录 token 使用量:
   INSERT INTO llm_usage_logs (...)
```

### 6.4 适配器

| 适配器 | 后端 | 协议 | 特殊处理 |
|--------|------|------|----------|
| ClaudeAdapter | Anthropic Claude API | Anthropic Messages API | tool_use 转换；system message 独立字段 |
| LocalAdapter | vLLM / Ollama | OpenAI-compatible `/v1/chat/completions` | 本地模型通常无原生 tool_use，通过 prompt 工程模拟或使用 function-calling 能力 |

### 6.5 Token 追踪

每次调用记录：

```json
{
  "request_id": "resp-uuid",
  "user_id": "user-uuid",
  "task_id": "task-uuid",
  "model": "claude-sonnet-4-6",
  "routing": "cloud",
  "prompt_tokens": 1500,
  "completion_tokens": 800,
  "total_tokens": 2300,
  "latency_ms": 3200,
  "created_at": "2026-05-17T10:30:00Z"
}
```

### 6.6 故障处理

| 场景 | 策略 |
|------|------|
| Claude API 不可达 | 自动降级到本地 LLM（如果 sensitivity 允许） |
| 本地 LLM OOM | 返回 503 + 等待重试 |
| Token 超限 | 截断 messages（保留 system + 最后 N 条） |
| 速率限制 (429) | 指数退避重试，最多 3 次 |

### 6.7 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ANTHROPIC_API_KEY` | (必填) | Claude API 密钥 |
| `LOCAL_LLM_ENDPOINT` | `http://localhost:8000/v1` | 本地 LLM 端点 |
| `LOCAL_LLM_DEFAULT_MODEL` | `qwen3-72b` | 默认本地模型 |
| `CLOUD_LLM_DEFAULT_MODEL` | `claude-sonnet-4-6` | 默认云端模型 |
| `LLM_DEFAULT_TEMPERATURE` | 0.3 | 默认温度参数 |
| `LLM_DEFAULT_MAX_TOKENS` | 4096 | 默认最大输出 token |
| `LLM_REQUEST_TIMEOUT_S` | 120 | LLM 请求超时 |
| `LLM_RETRY_MAX` | 3 | 最大重试次数 |
| `LLM_RETRY_BACKOFF_BASE_S` | 2 | 重试退避基数 |

---

## 7. M6 来源溯源服务

### 7.1 模块定位

解析 LLM 输出中的 inline 引用标记，校验引用与检索结果的一致性，生成用户可读的格式化引用，支持前端交互（点击查看原文）和导出文件中的引用呈现。

### 7.2 API 接口

#### 7.2.1 校验引用

```
POST /internal/citations/verify
```

**请求**:

```json
{
  "text": "近年来，数字贸易规则已成为...[ref:doc_123:p45-48]。多项研究表明...[ref:doc_456:p12|doc_789:p33-35]。这一趋势可能持续[ref:uncertain]。",
  "context_chunk_ids": ["chunk-001", "chunk-002", "chunk-003"]
}
```

**响应**:

```json
{
  "citations": [
    {
      "ref_id": "doc_123:p45-48",
      "sentence": "近年来，数字贸易规则已成为全球贸易治理的核心议题。",
      "sentence_index": 0,
      "confidence": "direct",
      "matched_chunks": [
        {
          "chunk_id": "chunk-001",
          "document_id": "doc_123",
          "page_start": 45,
          "page_end": 48,
          "excerpt": "数字贸易规则在近年来...",
          "similarity": 0.95
        }
      ]
    },
    {
      "ref_id": "doc_789:p33-35",
      "sentence": "多项研究表明数字服务税对中小企业的影响存在显著异质性。",
      "sentence_index": 1,
      "confidence": "fuzzy",
      "matched_chunks": [
        {
          "chunk_id": "chunk-003",
          "document_id": "doc_789",
          "page_start": 32,
          "page_end": 36,
          "excerpt": "...数字服务税的影响在中小企业中表现不同...",
          "similarity": 0.88
        }
      ]
    },
    {
      "ref_id": "uncertain",
      "sentence": "这一趋势可能持续。",
      "sentence_index": 2,
      "confidence": "uncertain",
      "matched_chunks": []
    }
  ],
  "summary": {
    "total": 3,
    "direct": 1,
    "fuzzy": 1,
    "uncertain": 1
  }
}
```

#### 7.2.2 获取引用详情

```
GET /api/tasks/{task_id}/output/citations/{citation_id}
```

**响应**:

```json
{
  "citation_id": "cit-uuid",
  "ref_id": "doc_123:p45-48",
  "sentence": "近年来，数字贸易规则已成为全球贸易治理的核心议题。",
  "confidence": "direct",
  "source": {
    "document_id": "doc_123",
    "document_title": "数字贸易规则研究",
    "page_start": 45,
    "page_end": 48,
    "excerpt": "原文摘录：数字贸易规则在近年来已成为全球贸易治理的核心议题，WTO、OECD等国际组织纷纷推动相关框架的建立..."
  },
  "verified_at": "2026-05-17T10:32:00Z",
  "verified_by": null
}
```

#### 7.2.3 获取所有引用

```
GET /api/tasks/{task_id}/output/citations
```

返回该任务输出的所有引用列表，支持按 `confidence` 过滤。

### 7.3 Inline 引用解析算法

```
输入: text (含 [ref:...] 标记的 LLM 输出)
输出: citations[], sentences_with_refs[]

1. 按句子分割文本 (中英文标点: 。！？.!?)
2. 对于每个句子:
    pattern = r'\[ref:([^\]]+)\]'
    匹配所有引用标记:
      - "doc_123:p45-48"           → 单引用
      - "doc_456:p12|doc_789:p33"  → 多引用
      - "uncertain"                → 不确定性声明
3. 解析每个引用标记:
    if mark == "uncertain":
        confidence = "uncertain"
    else:
        for each doc_ref in mark.split("|"):
            parse "doc_id:page_range"
4. 返回结构化引用列表
```

### 7.4 引用校验算法

```
输入: parsed_citations[], available_chunks[]
输出: verified_citations[]

for each citation in parsed_citations:
    if citation.mark == "uncertain":
        citation.confidence = "uncertain"
        continue

    for each doc_ref in citation.doc_refs:
        # 在可用 chunks 中查找匹配
        matching_chunks = [
            chunk for chunk in available_chunks
            if chunk.document_id == doc_ref.doc_id
            and page_overlap(chunk.pages, doc_ref.page_range)
        ]

        if matching_chunks:
            # 进一步检查语义相似度
            similarity = cosine_sim(citation.sentence_embedding,
                                     chunk.embedding)
            if similarity > 0.85:
                citation.confidence = "direct"
            else:
                citation.confidence = "fuzzy"
            citation.matched_chunks.extend(matching_chunks)
        else:
            citation.confidence = "fuzzy"  # doc_id 存在但页码不完全匹配

    if not citation.matched_chunks:
        citation.confidence = "uncertain"
```

### 7.5 引用格式化

针对不同输出格式的引用呈现：

| 格式 | 呈现方式 | 实现 |
|------|----------|------|
| Web 预览 | 超链接角标 `[1]`，悬浮显示原文 | 前端根据 citation API 数据渲染 |
| Markdown | GFM 脚注 `[^1]` + 文末引用清单 | 替换 `[ref:...]` 为 `[^n]` |
| .docx | 页脚注 或 尾注 | python-docx footnote 功能 |
| .xlsx | 独立 sheet "引用清单" | openpyxl 写入 |
| .pptx | 每页小字 + 末页完整清单 | python-pptx 文本框 |

### 7.6 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CITATION_SIMILARITY_THRESHOLD` | 0.85 | 判定 fuzzy 的语义相似度阈值 |
| `CITATION_VERIFY_BATCH_SIZE` | 50 | 批量校验的引用数 |
| `CITATION_FORMAT_FOOTNOTE` | true | .docx 默认使用脚注（false 使用尾注） |

---

## 8. M7 输出生成服务

### 8.1 模块定位

将 Agent 编排后的完整分析内容（章节文本 + 引用数据）转换为指定格式的输出文件（Markdown / .docx / .xlsx / .pptx），存储至 MinIO 并提供导出下载。

### 8.2 API 接口

#### 8.2.1 生成输出（内部接口）

```
POST /internal/output/generate
```

**请求**:

```json
{
  "task_id": "task-uuid",
  "title": "数字贸易规则对发展中国家的影响综述",
  "sections": [
    {
      "title": "研究背景与范围",
      "level": 1,
      "content": "近年来，数字贸易规则...[ref:doc_123:p45-48]..."
    }
  ],
  "citations": [
    {
      "ref_id": "doc_123:p45-48",
      "confidence": "direct",
      "document_title": "数字贸易规则研究",
      "source_page": "p45-48"
    }
  ],
  "metadata": {
    "author": "EconAI",
    "date": "2026-05-17",
    "keywords": ["数字贸易", "发展中国家", "政策分析"]
  },
  "formats": ["md", "docx"]
}
```

**响应**:

```json
{
  "outputs": [
    {
      "output_id": "out-uuid-1",
      "format": "md",
      "storage_path": "outputs/task-uuid/output.md",
      "size_bytes": 25600
    },
    {
      "output_id": "out-uuid-2",
      "format": "docx",
      "storage_path": "outputs/task-uuid/output.docx",
      "size_bytes": 128000
    }
  ]
}
```

#### 8.2.2 获取输出预览

```
GET /api/tasks/{task_id}/output
```

返回 Markdown 格式的输出内容（Web 预览用）。

#### 8.2.3 导出文件

```
GET /api/tasks/{task_id}/export?format=docx
```

返回文件流：
- `Content-Type`: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `Content-Disposition`: `attachment; filename="文献综述_数字贸易规则.docx"`

### 8.3 各格式生成流程

#### 8.3.1 Markdown 生成

```
输入: sections[], citations[], metadata

1. 生成 YAML front-matter (标题/日期/关键词)
2. 按 sections 顺序渲染:
   - 章节标题 (根据 level 生成 #/##/###)
   - 正文内容 (替换 [ref:xxx] 为 [^n] 脚注标记)
3. 文末追加 "引用清单" 章节:
   [^1] 张三. 数字贸易规则研究. 2024. p45-48.
   [^2] ...
```

#### 8.3.2 .docx 生成 (GB/T 9704)

```
输入: sections[], citations[], metadata

使用 python-docx 按 GB/T 9704 公文格式生成:

1. 版头区域 (页眉):
   - 发文机关标志: 机构名称 (从配置读取)
   - 发文字号: 自动生成或使用 metadata.issue_number

2. 主体区域:
   - 标题: 二号小标宋体，居中，无缩进
   - 主送机关 (可选): 三号仿宋，顶格
   - 正文:
     - 一级标题: 三号黑体
     - 二级标题: 三号楷体
     - 正文: 三号仿宋，首行缩进 2 字符，1.5 倍行距
     - 引用角标: 上标 [1][2]
   - 附件说明 (如有)

3. 文末引用清单:
   - "参考文献" 标题
   - 每条引用: [序号] 作者. 标题. 来源. 年份. 页码.

4. 版记区域 (页脚):
   - 抄送机关 (可选)
   - 印发日期
```

#### 8.3.3 .xlsx 生成

用于 `policy_comparison` 类型任务：

```
输入: sections[], citations[], comparison_matrix

Sheet 1 "对比分析":
  - 行: 政策选项
  - 列: 比较维度
  - 单元格: 分析文本

Sheet 2 "引用清单":
  - 列: 序号 | 来源文档 | 页码范围 | 置信度

Sheet 3 "数据摘要" (如有):
  - 关键指标和统计数据
```

#### 8.3.4 .pptx 生成

用于简报导出：

```
输入: sections[], citations[]

Slide 1: 封面 (标题 + 副标题 + 日期)
Slide 2: 目录 / 概述
Slide 3-6: 关键发现 (每个关键发现 1 页)
  - 标题: 发现概要
  - 正文: 要点 bullet points
  - 引用: 底部小字标注来源
Slide 7: 政策建议 / 结论
Slide 8: 引用清单 (完整)
```

### 8.4 格式模版管理

模版文件位于 `templates/output/`，为 YAML 配置文件：

```
templates/output/
├── docx_gbt9704.yaml       # GB/T 9704 公文样式定义
├── pptx_briefing.yaml      # 简报幻灯片样式
└── xlsx_matrix.yaml        # Excel 矩阵样式
```

模版文件定义字体、字号、间距、缩进等样式参数，以及内容占位符规则。

### 8.5 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `OUTPUT_STORAGE_PATH` | `outputs/` | MinIO 中的输出文件路径前缀 |
| `OUTPUT_TEMPLATES_DIR` | `templates/output/` | 输出格式模版目录 |
| `DOCX_INSTITUTION_NAME` | (必填) | .docx 版头的机构名称 |
| `DOCX_DEFAULT_FONT` | `仿宋_GB2312` | 默认中文字体 |
| `PPTX_DEFAULT_THEME` | `default` | PPT 默认主题 |
| `OUTPUT_MAX_FILE_SIZE_MB` | 50 | 输出文件最大体积 |

---

## 9. M8 用户权限服务

### 9.1 模块定位

管理用户、项目组、角色的 CRUD，提供 LDAP/SSO 认证对接，存储和查询审计日志。与 API 网关的认证中间件协作完成身份验证和权限校验。

### 9.2 API 接口

#### 9.2.1 认证

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户名密码或 LDAP 认证 |
| POST | `/api/auth/refresh` | 刷新 access token |
| POST | `/api/auth/logout` | 登出（token 加入黑名单） |
| GET | `/api/auth/me` | 获取当前用户信息 |

**登录请求**:

```json
{
  "username": "zhangsan",
  "password": "********",
  "provider": "local"
}
```

**登录响应**:

```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "expires_in": 7200,
  "user": {
    "user_id": "user-uuid",
    "username": "zhangsan",
    "display_name": "张三",
    "role": "senior_researcher",
    "groups": [
      {"group_id": "g-001", "name": "贸易政策研究组", "role": "senior_researcher"}
    ]
  }
}
```

#### 9.2.2 项目管理

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects` | 列出用户可见项目 |
| GET | `/api/projects/{id}` | 项目详情 |
| PUT | `/api/projects/{id}` | 更新项目 |
| DELETE | `/api/projects/{id}` | 归档项目（软删除） |

**创建项目请求**:

```json
{
  "name": "2024数字贸易政策研究",
  "description": "...",
  "group_id": "g-001"
}
```

#### 9.2.3 管理端点（需管理员权限）

| 方法 | 端点 | 说明 | 所需角色 |
|------|------|------|----------|
| POST | `/api/admin/users` | 创建用户 | project_admin+ |
| GET | `/api/admin/users` | 用户列表 | project_admin+ |
| PUT | `/api/admin/users/{id}` | 更新用户 | project_admin+ |
| DELETE | `/api/admin/users/{id}` | 停用用户 | system_admin |
| POST | `/api/admin/groups` | 创建项目组 | system_admin |
| GET | `/api/admin/groups` | 项目组列表 | project_admin+ |
| GET | `/api/admin/groups/{id}/members` | 列出组成员（含用户名/显示名称） | project_admin+ |
| POST | `/api/admin/groups/{id}/members` | 添加组成员 | project_admin+ |
| DELETE | `/api/admin/groups/{id}/members/{user_id}` | 移除组成员 | project_admin+ |
| GET | `/api/admin/groups/{id}/non-members` | 搜索非组成员用户（用于添加成员选择） | project_admin+ |
| GET | `/api/admin/audit-logs` | 查询审计日志 | system_admin |

**查询审计日志**:

```
GET /api/admin/audit-logs?user_id=uuid&action=create_task&resource_type=task&from=2026-05-01&to=2026-05-17&page=1&page_size=50
```

### 9.3 LDAP/SSO 认证流程

```
用户登录 (provider=ldap)
    │
    ├──→ 尝试 LDAP bind (dn=uid=zhangsan,ou=people,dc=institution,dc=cn)
    │     成功? → 查找或创建本地用户记录 → 签发 JWT
    │     失败? → 返回 401
    │
    └──→ LDAP 组映射:
          ldap_group → project_group
          memberOf → 自动同步组成员关系
```

### 9.4 数据隔离规则

| 资源 | 可见范围 |
|------|----------|
| 项目 | 所属项目组的成员 |
| 文档 | 所属项目的可见用户 |
| 任务 | 所属项目的可见用户 |
| 任务输出 | 所属项目的可见用户 |
| 机构知识库 | 同组成员 + 被授权的跨组用户 |
| 审计日志 | system_admin 全部可见；project_admin 可见本组 |

### 9.5 审计日志不可篡改

审计日志表通过以下机制保证完整性：
- 仅 INSERT，无 UPDATE/DELETE 权限（应用层 + 数据库层）
- 独立的数据库用户 `econai_audit` 写入，应用用户仅 SELECT
- 定期归档（6 个月后导出至冷存储）

### 9.6 GDPR 数据主体权利

| 权利 | API 端点 | 说明 |
|------|----------|------|
| 访问权 | `GET /api/user/data` | 导出用户的所有个人数据 |
| 删除权 | `DELETE /api/user/data` | 级联删除用户数据 |
| 可携带权 | `GET /api/user/data/export` | JSON 格式全部数据导出 |
| 同意管理 | `PUT /api/user/consent` | 更新数据处理同意状态 |

### 9.7 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LDAP_ENABLED` | false | 是否启用 LDAP |
| `LDAP_SERVER` | `ldap://localhost:389` | LDAP 服务器地址 |
| `LDAP_BASE_DN` | `dc=institution,dc=cn` | LDAP 搜索基准 |
| `LDAP_USER_FILTER` | `(uid=%(username)s)` | 用户搜索过滤器 |
| `LDAP_GROUP_MAPPING` | `{}` | LDAP 组到本地组的映射 |
| `AUDIT_LOG_RETENTION_MONTHS` | 6 | 审计日志保留月数 |
| `TOKEN_BLACKLIST_ENABLED` | true | 是否启用 token 黑名单 |

---

## 10. 模块间通信契约

### 10.1 通信方式总览

```
┌──────────┐    同步 HTTP      ┌──────────┐
│ API GW   │←────────────────→│ 各服务    │  REST API
└──────────┘                   └──────────┘

┌──────────┐    Redis Pub/Sub  ┌──────────┐
│ 文档解析  │──────────────────→│ 知识库    │  索引事件
└──────────┘                   └──────────┘

┌──────────┐    同步 HTTP      ┌──────────┐
│ 任务编排  │←────────────────→│ LLM路由  │  chat completion
│          │←────────────────→│ 知识库    │  hybrid search
│          │←────────────────→│ 来源溯源  │  verify citations
│          │──────────────────→│ 输出生成  │  generate output
└──────────┘                   └──────────┘

┌──────────┐    同步 HTTP      ┌──────────┐
│ API GW   │←────────────────→│ 用户权限  │  认证/授权/管理
└──────────┘                   └──────────┘

┌──────────┐    Redis Pub/Sub  ┌──────────┐
│ 各服务    │──────────────────→│ API GW   │  审计事件 → audit_logs
└──────────┘                   └──────────┘
```

### 10.2 同步接口契约

#### 知识库搜索

```
POST http://kb-service:8001/internal/search
Content-Type: application/json

请求:
{
  "query": "string",
  "project_id": "uuid",
  "user_id": "uuid",
  "top_k": 10,
  "filters": {"document_ids": ["..."], "chunk_types": ["paragraph"]}
}

响应 (200):
{
  "results": [{"chunk_id": "...", "content": "...", "score": 0.92, "metadata": {...}}],
  "total_hits": 45,
  "search_time_ms": 120
}

错误:
404: 项目不存在
403: 用户无权访问此项目
500: 向量数据库不可用
```

#### LLM Chat

```
POST http://llm-router:8002/internal/llm/chat
Content-Type: application/json

请求: 见 6.2.1
响应: 见 6.2.1

错误:
429: 速率限制
503: 模型不可用
504: 请求超时
```

#### 引用校验

```
POST http://citation-service:8003/internal/citations/verify
Content-Type: application/json

请求: 见 7.2.1
响应: 见 7.2.1

错误:
400: 文本格式无效（无引用标记）
500: 处理失败
```

#### 输出生成

```
POST http://output-service:8004/internal/output/generate
Content-Type: application/json

请求: 见 8.2.1
响应: 见 8.2.1

错误:
400: 不支持的输出格式
500: 生成失败
```

### 10.3 异步事件契约

#### 索引请求事件

```
频道: kb:index:request

消息:
{
  "event_id": "evt-uuid",
  "event_type": "document.parsed",
  "document_id": "doc-uuid",
  "project_id": "proj-uuid",
  "chunk_ids": ["chunk-001", "chunk-002", ...],
  "timestamp": "2026-05-17T10:35:00Z"
}

消费者: kb-service
处理: 向量化 + 写入向量库 + 更新状态
```

#### 审计事件

```
频道: audit:log

消息:
{
  "user_id": "uuid",
  "action": "create_task",
  "resource_type": "task",
  "resource_id": "uuid",
  "details": {...},
  "ip_address": "10.0.1.25",
  "user_agent": "...",
  "timestamp": "2026-05-17T10:30:00Z"
}

消费者: user-service (audit_log 子模块)
处理: 写入 audit_logs 表
```

### 10.4 服务发现

| 服务 | 内部主机名 | 端口 |
|------|-----------|------|
| api-gateway | `api-gateway` | 8000 |
| document-service | `document-service` | 8001 |
| kb-service | `kb-service` | 8002 |
| orchestration-service | `orchestration-service` | 8003 |
| llm-router | `llm-router` | 8004 |
| citation-service | `citation-service` | 8005 |
| output-service | `output-service` | 8006 |
| user-service | `user-service` | 8007 |

在 Docker Compose 网络中通过服务名互相访问。

---

## 11. 错误处理策略

### 11.1 错误码体系

```
格式: {DOMAIN}_{ISSUE}

DOMAIN:
  AUTH      认证相关
  DOC       文档相关
  KB        知识库相关
  TASK      任务相关
  LLM       LLM 相关
  CITATION  引用相关
  OUTPUT    输出相关
  USER      用户相关
  SYS       系统级

示例:
  AUTH_TOKEN_EXPIRED       Token 过期
  DOC_PARSE_FAILED         文档解析失败
  DOC_FORMAT_UNSUPPORTED   不支持的文档格式
  KB_SEARCH_TIMEOUT        搜索超时
  TASK_CREATE_FAILED       任务创建失败
  TASK_AGENT_LOOP_EXCEEDED Agent 达到最大迭代
  LLM_ROUTE_FAILED         LLM 路由失败
  LLM_MODEL_UNAVAILABLE    模型不可用
  CITATION_VERIFY_FAILED   引用校验失败
  OUTPUT_GENERATE_FAILED   输出生成失败
  USER_PERMISSION_DENIED   权限不足
  SYS_INTERNAL_ERROR       内部错误
```

### 11.2 错误传播

```
服务内部错误 → 结构化错误对象 → HTTP 状态码 → API Gateway 统一格式化 → 客户端

服务间调用错误:
  - 4xx: 透传给调用方（如权限不足）
  - 5xx: 包装为 SYS_DEPENDENCY_FAILED，记录日志
  - 超时: 调用方根据策略重试或降级
```

### 11.3 重试策略

| 场景 | 最大重试 | 退避策略 | 备注 |
|------|----------|----------|------|
| LLM 调用 (429) | 3 | 指数退避，base=2s | |
| LLM 调用 (5xx) | 2 | 线性退避，1s | 第二次重试可能降级到本地 |
| KB 搜索超时 | 1 | 立即 | 仍超时则返回空结果 |
| Celery 任务 | 不自动重试 | - | 用户手动重试 |
| 服务间 HTTP 调用 | 2 | 指数退避，base=1s | 含 jitter |

---

## 12. 测试策略概要

### 12.1 测试层次

| 层次 | 范围 | 工具 | 覆盖目标 |
|------|------|------|----------|
| 单元测试 | 各服务内部逻辑 | pytest | 核心算法、状态机、格式转换 |
| 集成测试 | 服务间 API 调用 | pytest + testcontainers | 所有 API 端点、错误路径 |
| E2E 测试 | 完整用户场景 | Playwright | 文献综述、政策比较等核心场景 |
| 性能测试 | 关键路径 | Locust | 搜索延迟、Agent 任务耗时 |

### 12.2 各模块关键测试点

| 模块 | 关键测试点 |
|------|-----------|
| 文档解析 | 各格式解析正确性、分块边界、OCR 准确率（含嵌入图片 OCR）、异常格式处理、图片提取正确性 |
| 知识库 | 索引完整性、混合检索召回率、RRF 融合正确性、权限隔离 |
| 任务编排 | Agent 状态机、工具调用序列、Plan/Finish 判定、迭代上限 |
| LLM 路由 | 敏感度判定规则、适配器转换正确性、降级策略 |
| 来源溯源 | 引用正则解析、校验置信度、边界情况 (无引用/全 uncertain) |
| 输出生成 | GB/T 9704 格式正确性、引用转脚注、大数据量性能 |
| 用户权限 | RBAC 每个角色边界、LDAP 认证、token 刷新、审计完整性 |
| API 网关 | 限流准确性、JWT 过期处理、未认证/未授权拦截 |

---

*文档版本：v1.2 | 日期：2026-05-25 | 基于概要设计文档 v1.0*
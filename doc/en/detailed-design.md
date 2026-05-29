# EconAI Detailed Design Document

> Version: v1.4 | Date: 2026-05-30 | Based on High-Level Design Document v1.0

---

## 1. Document Description

### 1.1 Purpose and Scope

This document provides interface-level detailed design for all service modules of the EconAI system, specifying for each module:
- External API interfaces (RESTful endpoints + request/response models)
- Internal inter-service call interfaces (synchronous RPC + asynchronous messages)
- Data model definitions (logical model + physical table mapping)
- State machines and key workflows
- Core algorithm pseudocode
- Error handling strategies
- Configuration item checklists

This document is intended for backend development engineers and integration test engineers. Developers can use it to complete module coding, and testers can use it to write integration test cases.

### 1.2 Relationship with High-Level Design

The high-level design document defines the system architecture, module decomposition, core decisions, and data flows. This document refines each module at the interface level based on that foundation, but does not include specific class definitions, function signatures, or code implementation details.

### 1.3 Module Index

| Number | Module | Directory | High-Level Design Section Reference |
|--------|--------|-----------|-------------------------------------|
| M1 | API Gateway | `api-gateway/` | 2.2, 5.1 |
| M2 | Document Parsing Service | `services/document-service/` | 3.1 |
| M3 | Knowledge Base Service | `services/kb-service/` | 3.2 |
| M4 | Task Orchestration Service | `services/orchestration-service/` | 3.3, 7 |
| M5 | LLM Routing Service | `services/llm-router/` | 3.4 |
| M6 | Source Citation Service | `services/citation-service/` | 3.5 |
| M7 | Output Generation Service | `services/output-service/` | 3.6 |
| M8 | User Permission Service | `services/user-service/` | 8.1, 8.2 |

---

## 2. M1 API Gateway

### 2.1 Module Positioning

The API Gateway is the sole entry point of the system, responsible for authentication, rate limiting, RBAC permission verification, and audit log recording. All client requests must pass through the gateway before reaching backend services.

### 2.2 Middleware Pipeline

```
Request → TLS Termination (Nginx) → JWT Authentication → RBAC Permission Check → Rate Limit Check → Audit Log → Route to Backend Service
```

### 2.3 JWT Authentication

#### Token Structure

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

| Field | Description |
|-------|-------------|
| `sub` | User UUID |
| `username` | Login name |
| `role` | System role: analyst / senior_researcher / project_admin / system_admin |
| `group_ids` | List of project group IDs the user belongs to |
| `exp` | Expiration time (access token: 2h, refresh token: 24h) |
| `iat` | Issued at time |

#### Token Refresh Flow

```
Client                          API Gateway
  │                                  │
  ├─ POST /api/auth/login ──────────→│ Returns access_token + refresh_token
  │                                  │
  │  ... Normal requests with access_token ...
  │                                  │
  ├─ Receives 401 ──────────────────│ access_token expired
  │                                  │
  ├─ POST /api/auth/refresh ────────→│ Validates refresh_token
  │  (with refresh_token)            │ Returns new access_token + refresh_token
```

### 2.4 RBAC Permission Model

```
Permission Matrix:
                    View Project  Create Project  Upload Doc  Create Task  Manage Users  View Audit
analyst             Own Group     ✗               Own Group    Own Group    ✗             ✗
senior_researcher   Own Group     Own Group        Own Group    Own Group    ✗             ✗
project_admin       Own Group     Own Group        Own Group    Own Group    Own Group     ✗
system_admin        All           All              All          All          All           All
```

### 2.5 Rate Limiting Strategy

| Rate Limit Dimension | Default Value | Configuration Item |
|----------------------|---------------|-------------------|
| Per-user request rate | 100 req/min | `RATE_LIMIT_PER_USER` |
| Per-IP request rate | 300 req/min | `RATE_LIMIT_PER_IP` |
| Document upload rate | 20 req/min | `RATE_LIMIT_UPLOAD` |
| Task creation rate | 10 req/min | `RATE_LIMIT_TASK_CREATE` |

Implementation: Redis Token Bucket, key format `ratelimit:{user_id}:{endpoint_group}`.

### 2.6 Audit Log Middleware

Automatically records the following information into the `audit_logs` table:

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

### 2.7 Routing Table

| Path Prefix | Target Service | Description |
|-------------|----------------|-------------|
| `/api/auth/*` | user-service | Authentication endpoints |
| `/api/projects/*` | user-service | Project management (requires project context) |
| `/api/projects/{id}/documents/*` | document-service | Document related (upload/list/detail/download/delete/reindex) |
| `/api/projects/{id}/search` | kb-service | Project knowledge base search |
| `/api/institutional/search` | kb-service | Institutional knowledge base search |
| `/api/projects/{id}/tasks/*` | orchestration-service | Task management (CRUD) |
| `/api/tasks/{id}/export` | output-service | File export/download (returns binary file stream) |
| `/api/tasks/{id}/*` | orchestration-service | Task status/output/cancel/retry |
| `/api/admin/*` | user-service | Admin endpoints (requires system_admin or project_admin) |

### 2.8 Error Response Format

All API errors use a unified format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error description",
    "details": {}
  }
}
```

| HTTP Status Code | Scenario |
|------------------|----------|
| 400 | Request parameter validation failed |
| 401 | Not authenticated or token expired |
| 403 | Insufficient permissions |
| 404 | Resource not found |
| 429 | Rate limit triggered |
| 500 | Internal service error |
| 503 | Service unavailable (dependent service not ready) |

### 2.9 Configuration Items

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `JWT_SECRET` | (Required) | JWT signing secret |
| `JWT_ACCESS_EXPIRE_MINUTES` | 120 | Access token validity period |
| `JWT_REFRESH_EXPIRE_HOURS` | 24 | Refresh token validity period |
| `RATE_LIMIT_PER_USER` | 100 | Maximum requests per user per minute |
| `RATE_LIMIT_PER_IP` | 300 | Maximum requests per IP per minute |
| `AUDIT_LOG_ENABLED` | true | Whether to enable audit logging |
| `CORS_ORIGINS` | `["*"]` | Allowed cross-origin sources |
| `MAX_REQUEST_SIZE_MB` | 100 | Maximum request body size |

---

## 3. M2 Document Parsing Service

### 3.1 Module Positioning

Receives user-uploaded documents, performs format identification, content extraction, and structured chunking, then writes structured data to PostgreSQL and MinIO for consumption by the Knowledge Base Service.

### 3.2 API Interfaces

#### 3.2.1 Upload Document

```
POST /api/projects/{project_id}/documents
Content-Type: multipart/form-data
```

**Request**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary | Yes | Document file |
| `is_internal` | bool | No | Whether to mark as an internal document (default false) |
| `metadata` | JSON string | No | Custom metadata `{"title":"", "authors":"", "date":"", "source":""}` |

**Response** (201):

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

#### 3.2.2 List Documents

```
GET /api/projects/{project_id}/documents?page=1&page_size=20&status=ready&format=pdf
```

**Response**:

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

#### 3.2.3 Get Document Detail

```
GET /api/projects/{project_id}/documents/{document_id}
```

**Response**: Same as the full version of a list item, additionally containing `parse_error` (when parsing fails) and `storage_path`.

#### 3.2.4 Download Document

```
GET /api/projects/{project_id}/documents/{document_id}/download
```

Downloads the original document file from MinIO.

**Response** (200):
- `Content-Type`: Automatically set based on document format (pdf→application/pdf, docx→application/vnd.openxmlformats-officedocument.wordprocessingml.document, etc.)
- `Content-Disposition`: `attachment; filename*=UTF-8''<RFC 5987 encoded filename>`, supports Chinese filenames

**Errors**:
- `404 DOC_NOT_FOUND`: Document does not exist or does not belong to this project
- `404 FILE_NOT_FOUND`: Storage path is empty
- `500 DOWNLOAD_FAILED`: MinIO download failed

#### 3.2.5 Delete Document

```
DELETE /api/projects/{project_id}/documents/{document_id}
```

Cascading deletion: MinIO file + PostgreSQL chunks records + corresponding vectors in the vector database.

#### 3.2.6 Reindex

```
POST /api/projects/{project_id}/documents/{document_id}/reindex
```

Triggers re-chunking and re-indexing, used for reprocessing after chunking parameter adjustments.

### 3.3 Asynchronous Processing Pipeline

After the upload interface returns synchronously, Celery executes asynchronously:

```
1. Store file in MinIO     → storage_path
2. Format identification    → format (via magic bytes + extension)
3. Content extraction       → full_text + structured_data
4. Image extraction & OCR   → Extract embedded images from documents (PDF/Word/PPT/HTML), recognize text via Tesseract
5. Metadata extraction      → metadata JSONB
6. Multi-granularity chunking → paragraph chunks + section chunks
7. Write to PostgreSQL      → documents table + document_chunks table
8. Send index event         → Redis pub/sub (notify KB Service)
```

### 3.4 Format Handler Selection Logic

```
Input: file extension + MIME type + file header magic bytes

if magic_bytes indicates PDF:
    if text layer exists (detected via PyMuPDF):
        → PyMuPDF extract text (preserve page numbers and layout)
        → Extract embedded images → Tesseract OCR → append to corresponding pages
    else:
        → Tesseract OCR full page recognition → same as PDF text extraction flow

if extension in [.docx, .doc]:
    → python-docx extract text + paragraph styles + tables
    → Extract embedded images (relationship parts) → Tesseract OCR → append to full text

if extension in [.xlsx, .xls, .csv]:
    → openpyxl / pandas extract structured tables

if extension in [.pptx, .ppt]:
    → python-pptx extract text slide by slide
    → Extract embedded images from slides → Tesseract OCR → append to corresponding slides

if extension == .eml:
    → email standard library extract body + metadata (sender/date/subject)

if extension in [.html, .mhtml, .mht]:
    → BeautifulSoup extract body text (remove navigation/ads/scripts)
    → Extract data-URI embedded images (base64) → Tesseract OCR → append to full text

if extension in [.md, .txt]:
    → Read text directly
```

**Shared Image Extraction & OCR Module** (`document_service/parsers/image_extractor.py`):

| Function | Extraction Source | Description |
|----------|-------------------|-------------|
| `ocr_image_bytes(image_bytes, language)` | Generic image bytes | Calls Tesseract OCR (default `chi_sim+eng`), graceful degradation (returns `[OCR not available]` when pytesseract is unavailable) |
| `extract_images_from_pdf(file_data)` | PDF page embedded images | Uses PyMuPDF `get_images()` + `extract_image()` to extract page by page and OCR |
| `extract_images_from_docx(file_data)` | DOCX relationship part images | Iterates `part.rels` to find image relationship parts, extracts and OCR |
| `extract_images_from_pptx(file_data)` | PPTX slide shape images | Iterates all shapes of type `MSO_SHAPE_TYPE.PICTURE` across all slides, extracts and OCR |
| `extract_images_from_html(file_data)` | HTML data-URI images | Regex matches `<img src="data:image/...">` tags, decodes base64 then OCR |

All extraction functions return a unified structure: `[{page, image_index, ocr_text, format, width, height}, ...]`.

### 3.5 Multi-Granularity Chunking Algorithm

```
Input: full_text, page_map (text→page number mapping), structure (section tree)
Output: paragraph_chunks[], section_chunks[]

# Paragraph-level chunking
paragraphs = split_by_natural_boundary(full_text)  # Split by \n\n
for each paragraph:
    tokens = count_tokens(paragraph)
    if tokens < MIN_PARAGRAPH_TOKENS (100):
        merge_with_next(paragraph)  # Merge into next paragraph
    elif tokens > MAX_PARAGRAPH_TOKENS (500):
        split_by_sentence_boundary(paragraph)  # Split by sentence boundaries
    # Ensure chunks align on natural paragraph boundaries
    add_overlap_with_prev(50 tokens)

# Section-level chunking
for each section in structure_tree:
    section_text = extract_section_content(section)
    tokens = count_tokens(section_text)
    if tokens > MAX_SECTION_TOKENS (3000):
        split_by_subsection(section)  # Split by subsections
    elif tokens < MIN_SECTION_TOKENS (500):
        merge_with_next_section(section)
    add_overlap_with_prev(100 tokens)
```

### 3.6 Document State Machine

```
pending ──→ parsing ──→ ready
                │
                ├──→ error ──→ (retryable: POST reindex)
                │
                └──→ (user delete → deleted)
```

### 3.7 Internal Service Interface

After document parsing is complete, an index event is published via Redis pub/sub:

```
Channel: kb:index:request
Message:
{
  "document_id": "doc-uuid",
  "project_id": "proj-uuid", 
  "chunk_ids": ["chunk-001", "chunk-002", ...],
  "is_internal": false,
  "timestamp": "2026-05-17T10:35:00Z"
}
```

### 3.8 Configuration Items

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO address |
| `MINIO_BUCKET` | `econai-documents` | Document storage bucket |
| `CHUNK_PARAGRAPH_TARGET_TOKENS` | 300 | Paragraph-level target token count |
| `CHUNK_PARAGRAPH_MIN_TOKENS` | 100 | Paragraph-level minimum token count |
| `CHUNK_PARAGRAPH_MAX_TOKENS` | 500 | Paragraph-level maximum token count |
| `CHUNK_SECTION_TARGET_TOKENS` | 2000 | Section-level target token count |
| `CHUNK_SECTION_MIN_TOKENS` | 500 | Section-level minimum token count |
| `CHUNK_SECTION_MAX_TOKENS` | 3000 | Section-level maximum token count |
| `CHUNK_PARAGRAPH_OVERLAP` | 50 | Paragraph-level overlap token count |
| `CHUNK_SECTION_OVERLAP` | 100 | Section-level overlap token count |
| `OCR_LANGUAGE` | `chi_sim+eng` | Tesseract language pack (used for image OCR recognition in all parsers) |
| `MAX_FILE_SIZE_MB` | 100 | Maximum upload file size |
| `CELERY_DOCUMENT_QUEUE` | `document` | Document processing task queue name |

---

## 4. M3 Knowledge Base Service

### 4.1 Module Positioning

Manages the lifecycle of knowledge bases, consumes index events from the Document Parsing Service, performs vectorization and index storage, and provides hybrid search capabilities.

### 4.2 API Interfaces

#### 4.2.1 Search Project Knowledge Base

```
POST /api/projects/{project_id}/search
```

**Request**:

```json
{
  "query": "数字贸易规则对发展中国家的影响",
  "top_k": 10,
  "page": 1,
  "page_size": 10,
  "filters": {
    "document_ids": ["doc-001", "doc-002"],
    "chunk_types": ["paragraph"],
    "date_range": {"start": "2020-01-01", "end": "2024-12-31"}
  },
  "search_mode": "hybrid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query (natural language) |
| `top_k` | int | No | Number of results per page, default 10 |
| `page` | int | No | Page number, starting from 1, default 1 |
| `page_size` | int | No | Page size (1-100), default 10 |
| `filters` | object | No | Filter conditions |
| `search_mode` | string | No | hybrid / vector / bm25, default hybrid |

**Response**:

```json
{
  "results": [
    {
      "chunk_id": "chunk-uuid",
      "document_id": "doc-001",
      "document_title": "数字贸易规则研究.pdf",
      "content": "近年来，数字贸易规则已成为...",
      "highlighted_content": "近年来，<em>数字贸易规则</em>已成为...",
      "chunk_type": "paragraph",
      "score": 0.92,
      "matched_terms": ["数字贸易", "规则"],
      "metadata": {
        "page_start": 12,
        "page_end": 13,
        "section_title": "发展中国家影响分析",
        "paragraph_index": 3
      }
    }
  ],
  "total_hits": 45,
  "page": 1,
  "page_size": 10,
  "pages": 5,
  "search_time_ms": 120
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_hits` | int | Total number of results meeting conditions |
| `page` | int | Current page number |
| `page_size` | int | Page size |
| `pages` | int | Total number of pages |

#### 4.2.2 Search Institutional Knowledge Base

```
POST /api/institutional/search
```

Same request format as above, with additional `group_ids` filter for cross-group authorization.

### 4.3 Indexing Pipeline

```
Listen Redis pub/sub: kb:index:request
    │
    ├──→ Read document_chunks (from PostgreSQL)
    │
    ├──→ Vectorize (text2vec / m3e embedding)
    │     Each chunk → 768d or 1024d vector
    │
    ├──→ Write to vector database (Milvus / Qdrant)
    │     collection: econai_chunks
    │     Fields: chunk_id, vector, project_id, document_id, chunk_type
    │
    ├──→ Update BM25 index (PostgreSQL FTS)
    │     tsvector column auto-updated
    │
    └──→ Update documents.parse_status = 'ready'
```

### 4.4 Hybrid Search Algorithm

```
Input: query (natural language), project_id, top_k, filters
Output: top_k most relevant chunks

# Parallel search
vector_results = vector_search(query_embedding, filters, top_k=50)
bm25_results = bm25_search(query_text, filters, top_k=50)

# RRF Fusion (Reciprocal Rank Fusion)
k = 60
scores = {}
for each result in vector_results:
    scores[result.id] += 1 / (k + result.rank)
for each result in bm25_results:
    scores[result.id] += 1 / (k + result.rank)

merged = sort_by_score(scores)[:30]

# Reranker re-ranking
for each candidate in merged:
    rerank_score = cross_encoder(query, candidate.content)  # BGE-Reranker
    candidate.final_score = 0.7 * candidate.rrf_score + 0.3 * rerank_score

return sort_by_final_score(merged)[:top_k]
```

### 4.5 Knowledge Base Isolation Implementation

```
Permission filter injection during search:

def build_search_filters(user, project_id, kb_sources):
    filters = {"project_id": project_id}

    # Verify user's access to the project
    if not user_can_access_project(user, project_id):
        raise PermissionDenied

    # If searching institutional knowledge base
    if kb_sources.include_institutional:
        filters["allowed_groups"] = user.group_ids

    return filters
```

### 4.6 Knowledge Base Lifecycle

```
Document upload → Parsing complete → Auto-index → active
                              │
                              ├──→ Project archived → archived (index retained, excluded from search)
                              │
                              ├──→ Manual delete → deleted
                              │     └──→ Cascading delete: chunks + vectors + BM25
                              │
                              └──→ Reindex → active (after chunking strategy adjustment)
```

### 4.7 Configuration Items

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `VECTOR_DB_TYPE` | `milvus` | Vector database type (milvus / qdrant) |
| `VECTOR_DB_HOST` | `localhost` | Vector database address |
| `VECTOR_DB_PORT` | 19530 | Vector database port |
| `EMBEDDING_MODEL` | `text2vec-large-chinese` | Embedding model |
| `EMBEDDING_DIM` | 1024 | Vector dimension |
| `HYBRID_VECTOR_TOP_K` | 50 | Vector search candidate count |
| `HYBRID_BM25_TOP_K` | 50 | BM25 search candidate count |
| `HYBRID_RRF_K` | 60 | RRF fusion parameter k |
| `HYBRID_MERGED_TOP_K` | 30 | Post-fusion candidate count |
| `RERANKER_MODEL` | `bge-reranker-large` | Reranker model |
| `SEARCH_DEFAULT_TOP_K` | 10 | Default result count |
| `SEARCH_TIMEOUT_MS` | 5000 | Search timeout |

---

## 5. M4 Task Orchestration Service

### 5.1 Module Positioning

The Task Orchestration Service is the core brain of the system. It manages the full lifecycle of analysis tasks, runs a custom-built lightweight Agent loop engine, completes intelligent analysis by calling the LLM Router and Knowledge Base Service, and delivers results to the Output Generation and Source Citation services.

### 5.2 API Interfaces

#### 5.2.1 Create Analysis Task

```
POST /api/projects/{project_id}/tasks
```

**Request**:

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

**Field Descriptions**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | enum | Yes | literature_review / policy_draft / policy_comparison / tech_interpretation |
| `title` | string | Yes | Task title |
| `description` | string | No | Task description, used as additional context for LLM |
| `kb_sources.documents` | UUID[] | Yes | List of document IDs to use |
| `kb_sources.include_institutional` | bool | No | Whether to include institutional knowledge base |
| `output_formats` | enum[] | Yes | Output formats, supports md / docx / xlsx / pptx |
| `llm_preference` | enum | No | auto / local / cloud |
| `analysis_params` | object | Yes | Task-type-specific analysis parameters |

**Response** (201):

```json
{
  "task_id": "task-uuid",
  "status": "pending",
  "created_at": "2026-05-17T10:30:00Z"
}
```

#### 5.2.2 List Tasks

```
GET /api/projects/{project_id}/tasks?page=1&page_size=20&status=running&type=literature_review
```

**Response**: Paginated task list, each item containing `task_id`, `type`, `title`, `status`, `progress`, `created_by`, `created_at`.

#### 5.2.3 Get Task Detail

```
GET /api/tasks/{task_id}
```

**Response**:

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

#### 5.2.4 Get Task Status (Polling)

```
GET /api/tasks/{task_id}/status
```

**Response** (simplified, for frontend polling):

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

#### 5.2.5 Cancel Task

```
POST /api/tasks/{task_id}/cancel
```

Requests Celery to revoke the task, setting status to `cancelled`.

#### 5.2.6 Retry Task

```
POST /api/tasks/{task_id}/retry
```

Only tasks in `failed` status can be retried; creates a new Celery task.

### 5.3 Task State Machine

```
                    ┌──────────┐
                    │  pending  │
                    └────┬─────┘
                         │ Celery Worker picks up
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
            │  (retryable)             │  (unrecoverable)
            ▼                          ▼
       ┌──────────┐              ┌──────────┐
       │  failed  │              │cancelled │
       └──────────┘              └──────────┘
```

**State Transition Rules**:

| Current State | Allowed Target State | Trigger Condition |
|---------------|---------------------|-------------------|
| pending | running | Celery Worker begins execution |
| pending | cancelled | User cancels before task starts |
| running | completed | Agent loop ends normally |
| running | failed | Exception, timeout, Agent reaches max iterations |
| running | cancelled | User actively cancels |
| failed | running | User clicks retry |
| completed | - | Terminal state |
| cancelled | - | Terminal state |

### 5.4 Agent Engine Design

#### 5.4.1 Core Loop

```
AgentState:
  messages: list[Message]          # LLM conversation history
  retrieved_chunks: list[Chunk]    # All retrieved chunks
  generated_sections: list[Section] # Generated sections
  citations: dict[str, Citation]   # ref_id → Citation mapping
  plan: str                        # Current execution plan
  iteration: int                   # Current iteration round
  remaining_sections: list[str]    # Sections yet to be completed
  tool_call_history: list[ToolCall] # Tool call history

Loop(max_iterations=5):
  1. Plan:  LLM analyzes current state, decides next action
     - action = "tool_call" → tool_name + tool_args
     - action = "finish"    → Exit loop

  2. Execute: Call specified tool(tool_args, state)
     Each tool returns structured results

  3. Observe: Append tool results to state.messages

  4. Update Progress: Update task.progress JSONB

  5. iteration += 1

  6. if action == "finish" or iteration >= MAX_ITERATIONS:
       break

Post-loop: Format → Call output-service to generate files in various formats
```

#### 5.4.2 Tool Definitions

| Tool Name | Function | Input Schema | Output Schema |
|-----------|----------|-------------|---------------|
| `search_kb` | Hybrid knowledge base search | `{"query": "string", "filters": {}, "top_k": 10}` | `{"chunks": [{chunk_id, content, metadata, score}]}` |
| `generate_section` | LLM generates section content | `{"section_goal": "string", "section_title": "string", "context_chunk_ids": ["..."]}` | `{"content": "string with [ref:] marks", "word_count": 500}` |
| `verify_citations` | Verify citation accuracy | `{"text": "string", "chunk_ids": ["..."]}` | `{"report": [{"ref_id": "...", "confidence": "direct|fuzzy|uncertain"}]}` |
| `extract_key_claims` | Extract key claims | `{"text": "string"}` | `{"claims": [{"claim": "...", "source_ref": "...", "methodology": "..."}]}` |
| `compare_policies` | Multi-policy option comparison | `{"policies": [{"name": "", "description": ""}], "dimensions": ["..."]}` | `{"comparison": "text", "matrix": [[...]]}` |
| `format_output` | Format final output | `{"sections": ["..."], "citations": {}, "format": "md|docx|..."}` | `{"output_id": "...", "storage_path": "..."}` |

#### 5.4.3 Agent Behavior by Task Type

**Literature Review**:

```
Plan: Retrieve global core claims → search_kb
  → generate_section("研究背景与范围")
  → verify_citations → Plan: Retrieve methodology differences
  → search_kb("方法论 实证研究 数据来源")
  → generate_section("方法论比较")
  → verify_citations → Plan: Retrieve policy recommendations
  → search_kb("政策建议 实施路径")
  → generate_section("政策建议汇总")
  → extract_key_claims → Plan: Retrieve research gaps
  → search_kb("研究局限 未来方向")
  → generate_section("研究空白与展望")
  → verify_citations → finish
  → format_output
```

**Policy Draft**:

```
Plan: Retrieve policy background → search_kb
  → generate_section("背景与必要性")
  → Plan: Retrieve relevant legal basis → search_kb
  → generate_section("政策依据")
  → generate_section("主要措施")
  → Plan: Retrieve implementation plan references → search_kb
  → generate_section("组织实施方案")
  → generate_section("预期效果与评估")
  → verify_citations → finish → format_output
```

**Policy Comparison**:

```
Plan: Extract core elements of each policy → extract_key_claims(multiple policy texts)
  → compare_policies(by specified dimensions)
  → generate_section("比较分析总览")
  → generate_section("各政策优劣势分析")
  → search_kb("政策实施效果 评估") → generate_section("实施效果比较")
  → verify_citations → finish → format_output
```

**Tech Interpretation**:

```
Plan: Retrieve technical standard original text → search_kb
  → generate_section("技术标准概述")
  → generate_section("关键条款解读")
  → Plan: Retrieve compliance impact analysis → search_kb
  → generate_section("合规影响分析")
  → generate_section("实施建议")
  → verify_citations → finish → format_output
```

### 5.5 Sensitivity Determination

Executed at task creation to determine LLM routing direction:

```python
def determine_sensitivity(task, kb_sources):
    # Rule 1: Contains internal documents
    if any(doc.is_internal for doc in kb_sources):
        return "high"

    # Rule 2: Policy draft type (usually based on internal files)
    if task.type == "policy_draft":
        return "high"

    # Rule 3: User explicitly specifies
    if task.llm_preference != "auto":
        return task.llm_preference

    # Rule 4: Default non-sensitive
    return "low"
```

### 5.6 Timeout and Fault Tolerance

| Scenario | Strategy |
|----------|----------|
| Agent loop exceeds max iterations (5 rounds) | Use existing content to call format_output |
| Single tool call timeout (60s) | Retry once; if still fails, skip that step |
| LLM returns unparseable format | Use fallback logic to extract tool_call; terminate after 2 consecutive failures |
| Citation verification finds many uncertain | Log warning; still complete output but mark citation confidence |
| Celery task timeout (30 min) | Mark task as failed, record `error_message` |

### 5.7 Progress Reporting Protocol

Agent updates `analysis_tasks.progress` after each step:

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

`total_steps_estimate` is an estimated value and may be dynamically adjusted as the Agent actually executes.

### 5.8 Configuration Items

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `AGENT_MAX_ITERATIONS` | 5 | Maximum iteration rounds |
| `AGENT_TOOL_TIMEOUT_S` | 60 | Single tool call timeout |
| `AGENT_MAX_RETRIEVED_CHUNKS` | 30 | Cumulative maximum retrieved chunk count |
| `TASK_TIMEOUT_MINUTES` | 30 | Single task total timeout |
| `CELERY_ORCHESTRATION_QUEUE` | `orchestration` | Task queue name |
| `PROMPT_TEMPLATES_DIR` | `templates/prompts/` | Prompt templates directory |

---

## 6. M5 LLM Routing Service

### 6.1 Module Positioning

Unified management of LLM calls, automatic routing to local or cloud models based on data sensitivity, abstracting differences across LLM backends, and tracking token usage.

### 6.2 API Interfaces

#### 6.2.1 Chat Completion (Internal Interface)

```
POST /internal/llm/chat
```

**Request**:

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

**Response**:

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

#### 6.2.2 Model List

```
GET /internal/llm/models
```

**Response**:

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

### 6.3 Routing Decision Flow

```
Input: request (messages + tools + sensitivity)

1. Determine target model:
   if request.model != "auto":
       target = request.model
   elif sensitivity == "high":
       target = default_local_model
   else:
       target = default_cloud_model

2. Select adapter:
   if target starts with "claude":
       adapter = ClaudeAdapter
   elif target starts with "local:" or provider is vllm/ollama:
       adapter = LocalAdapter (OpenAI-compatible)

3. Adapter transforms request:
   ClaudeAdapter: Directly use Anthropic SDK format
   LocalAdapter:  Convert to OpenAI Chat Completions format

4. Call LLM

5. Unify response format:
   Normalize each adapter's output to the unified format above

6. Record token usage:
   INSERT INTO llm_usage_logs (...)
```

### 6.4 Adapters

| Adapter | Backend | Protocol | Special Handling |
|---------|---------|----------|------------------|
| ClaudeAdapter | Anthropic Claude API | Anthropic Messages API | tool_use conversion; system message as separate field |
| LocalAdapter | vLLM / Ollama | OpenAI-compatible `/v1/chat/completions` | Local models usually lack native tool_use; simulate via prompt engineering or use function-calling capability |

### 6.5 Token Tracking

Recorded per call:

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

### 6.6 Fault Handling

| Scenario | Strategy |
|----------|----------|
| Claude API unreachable | Auto-degrade to local LLM (if sensitivity allows) |
| Local LLM OOM | Return 503 + wait for retry |
| Token exceeded | Truncate messages (keep system + last N messages) |
| Rate limit (429) | Exponential backoff retry, max 3 times |

### 6.7 Circuit Breaker

When consecutive Claude API call failures reach a threshold, the circuit breaker automatically switches to OPEN state, directly rejecting requests for a short period (returning 503) to avoid cascading retries to an unreachable backend.

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | 5 | Number of consecutive failures to trigger circuit break |
| `CIRCUIT_BREAKER_RECOVERY_TIMEOUT_S` | 60 | Time to wait in OPEN state before entering HALF_OPEN probe |

State machine: `CLOSED → (5 failures) → OPEN → (60s) → HALF_OPEN → (1 success) → CLOSED`

### 6.8 Configuration Items

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `ANTHROPIC_API_KEY` | (Required) | Claude API key |
| `ANTHROPIC_API_BASE_URL` | (Empty) | Claude API custom endpoint (use `http://host.docker.internal:11434` inside Docker to point to host Ollama) |
| `LOCAL_LLM_ENDPOINT` | `http://host.docker.internal:11434/v1` | Local LLM endpoint (use `host.docker.internal` inside Docker to access host) |
| `LOCAL_LLM_DEFAULT_MODEL` | `qwen3-72b` | Default local model |
| `CLOUD_LLM_DEFAULT_MODEL` | `claude-sonnet-4-6` | Default cloud model |
| `LLM_DEFAULT_TEMPERATURE` | 0.3 | Default temperature parameter |
| `LLM_DEFAULT_MAX_TOKENS` | 4096 | Default max output tokens |
| `LLM_REQUEST_TIMEOUT_S` | 120 | LLM request timeout |
| `LLM_RETRY_MAX` | 3 | Maximum retry count |
| `LLM_RETRY_BACKOFF_BASE_S` | 2 | Retry backoff base |

> **Docker Network Note**: Inside containers, `localhost` points to the container itself. To access host services (such as Ollama), you must use `host.docker.internal`. After modifying `.env`, run `docker compose up -d --no-deps --force-recreate llm-router` for the environment variables to take effect.

---

## 7. M6 Source Citation Service

### 7.1 Module Positioning

Parses inline citation markers in LLM output, verifies citations against retrieval results, generates user-readable formatted citations, and supports frontend interaction (click to view original text) and citation presentation in exported files.

### 7.2 API Interfaces

#### 7.2.1 Verify Citations

```
POST /internal/citations/verify
```

**Request**:

```json
{
  "text": "近年来，数字贸易规则已成为...[ref:doc_123:p45-48]。多项研究表明...[ref:doc_456:p12|doc_789:p33-35]。这一趋势可能持续[ref:uncertain]。",
  "context_chunk_ids": ["chunk-001", "chunk-002", "chunk-003"]
}
```

**Response**:

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

#### 7.2.2 Get Citation Detail

```
GET /api/tasks/{task_id}/output/citations/{citation_id}
```

**Response**:

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

#### 7.2.3 Get All Citations

```
GET /api/tasks/{task_id}/output/citations
```

Returns the full list of citations for the task output, with filtering by `confidence` supported.

### 7.3 Inline Citation Parsing Algorithm

```
Input: text (LLM output containing [ref:...] markers)
Output: citations[], sentences_with_refs[]

1. Split text by sentences (Chinese/English punctuation: 。！？.!?)
2. For each sentence:
    pattern = r'\[ref:([^\]]+)\]'
    Match all citation markers:
      - "doc_123:p45-48"           → Single citation
      - "doc_456:p12|doc_789:p33"  → Multi-citation
      - "uncertain"                → Uncertainty declaration
3. Parse each citation marker:
    if mark == "uncertain":
        confidence = "uncertain"
    else:
        for each doc_ref in mark.split("|"):
            parse "doc_id:page_range"
4. Return structured citation list
```

### 7.4 Citation Verification Algorithm

```
Input: parsed_citations[], available_chunks[]
Output: verified_citations[]

for each citation in parsed_citations:
    if citation.mark == "uncertain":
        citation.confidence = "uncertain"
        continue

    for each doc_ref in citation.doc_refs:
        # Find matches in available chunks
        matching_chunks = [
            chunk for chunk in available_chunks
            if chunk.document_id == doc_ref.doc_id
            and page_overlap(chunk.pages, doc_ref.page_range)
        ]

        if matching_chunks:
            # Further check semantic similarity
            similarity = cosine_sim(citation.sentence_embedding,
                                     chunk.embedding)
            if similarity > 0.85:
                citation.confidence = "direct"
            else:
                citation.confidence = "fuzzy"
            citation.matched_chunks.extend(matching_chunks)
        else:
            citation.confidence = "fuzzy"  # doc_id exists but pages don't fully match

    if not citation.matched_chunks:
        citation.confidence = "uncertain"
```

### 7.5 Citation Formatting

Citation presentation for different output formats:

| Format | Presentation | Implementation |
|--------|-------------|----------------|
| Web Preview | Hyperlink superscript `[1]`, hover to show original text | Frontend renders based on citation API data |
| Markdown | GFM footnotes `[^1]` + end-of-document citation list | Replace `[ref:...]` with `[^n]` |
| .docx | Page footnotes or endnotes | python-docx footnote functionality |
| .xlsx | Separate "引用清单" sheet | openpyxl write |
| .pptx | Small text per slide + full list on last slide | python-pptx text box |

### 7.6 Configuration Items

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `CITATION_SIMILARITY_THRESHOLD` | 0.85 | Semantic similarity threshold for determining fuzzy |
| `CITATION_VERIFY_BATCH_SIZE` | 50 | Number of citations for batch verification |
| `CITATION_FORMAT_FOOTNOTE` | true | .docx default uses footnotes (false uses endnotes) |

---

## 8. M7 Output Generation Service

### 8.1 Module Positioning

Converts the complete analysis content (section text + citation data) orchestrated by the Agent into output files in specified formats (Markdown / .docx / .xlsx / .pptx), stores them in MinIO, and provides export download.

### 8.2 API Interfaces

#### 8.2.1 Generate Output (Internal Interface)

```
POST /internal/output/generate
```

**Request**:

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

**Response**:

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

#### 8.2.2 Get Output Preview

```
GET /api/tasks/{task_id}/output
```

Returns output content in Markdown format (for Web preview).

#### 8.2.3 Export File

```
GET /api/tasks/{task_id}/export?format=docx
```

Returns file stream (routed by API Gateway to output-service):
- `Content-Type`: `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (automatically mapped based on format parameter)
- `Content-Disposition`: `attachment; filename*=UTF-8''<RFC 5987 encoded filename>`, supports Chinese filenames
- Supported formats: `md`, `docx`, `xlsx`, `pptx`

**Errors**:
- `404 NOT_FOUND`: Output file in specified format does not exist
- `400`: Unsupported output format

### 8.3 Format Generation Flows

#### 8.3.1 Markdown Generation

```
Input: sections[], citations[], metadata

1. Generate YAML front-matter (title/date/keywords)
2. Render in sections order:
   - Section titles (generate #/##/### based on level)
   - Body content (replace [ref:xxx] with [^n] footnote markers)
3. Append "引用清单" section at end of document:
   [^1] 张三. 数字贸易规则研究. 2024. p45-48.
   [^2] ...
```

#### 8.3.2 .docx Generation (GB/T 9704)

```
Input: sections[], citations[], metadata

Use python-docx to generate in GB/T 9704 official document format:

1. Header area (page header):
   - Issuing authority logo: Institution name (read from config)
   - Document number: Auto-generated or use metadata.issue_number

2. Body area:
   - Title: Size 2 small Song typeface, centered, no indent
   - Main recipient (optional): Size 3 FangSong, flush left
   - Body text:
     - Level-1 heading: Size 3 bold Heiti
     - Level-2 heading: Size 3 Kaiti
     - Body: Size 3 FangSong, first-line indent 2 characters, 1.5x line spacing
     - Citation superscripts: Superscript [1][2]
   - Attachment note (if any)

3. End-of-document citation list:
   - "参考文献" heading
   - Each citation: [Number] Author. Title. Source. Year. Page numbers.

4. Footer area (page footer):
   - CC recipients (optional)
   - Issue date
```

#### 8.3.3 .xlsx Generation

Used for `policy_comparison` type tasks:

```
Input: sections[], citations[], comparison_matrix

Sheet 1 "对比分析":
  - Rows: Policy options
  - Columns: Comparison dimensions
  - Cells: Analysis text

Sheet 2 "引用清单":
  - Columns: Number | Source Document | Page Range | Confidence

Sheet 3 "数据摘要" (if any):
  - Key indicators and statistical data
```

#### 8.3.4 .pptx Generation

Used for briefing export:

```
Input: sections[], citations[]

Slide 1: Cover (title + subtitle + date)
Slide 2: Table of contents / Overview
Slide 3-6: Key findings (1 page per key finding)
  - Title: Finding summary
  - Body: Key bullet points
  - Citations: Small text at bottom noting source
Slide 7: Policy recommendations / Conclusion
Slide 8: Citation list (complete)
```

### 8.4 Format Template Management

Template files are located in `templates/output/`, as YAML configuration files:

```
templates/output/
├── docx_gbt9704.yaml       # GB/T 9704 official document style definitions
├── pptx_briefing.yaml      # Briefing slide style
└── xlsx_matrix.yaml        # Excel matrix style
```

Template files define font, font size, spacing, indentation and other style parameters, as well as content placeholder rules.

### 8.5 Configuration Items

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `OUTPUT_STORAGE_PATH` | `outputs/` | Output file path prefix in MinIO |
| `OUTPUT_TEMPLATES_DIR` | `templates/output/` | Output format templates directory |
| `DOCX_INSTITUTION_NAME` | (Required) | Institution name for .docx header |
| `DOCX_DEFAULT_FONT` | `仿宋_GB2312` | Default Chinese font |
| `PPTX_DEFAULT_THEME` | `default` | Default PPT theme |
| `OUTPUT_MAX_FILE_SIZE_MB` | 50 | Maximum output file size |

---

## 9. M8 User Permission Service

### 9.1 Module Positioning

Manages CRUD for users, project groups, and roles, provides LDAP/SSO authentication integration, and stores and queries audit logs. Collaborates with the API Gateway's authentication middleware to complete identity verification and permission checks.

### 9.2 API Interfaces

#### 9.2.1 Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Username/password or LDAP authentication |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/logout` | Logout (token added to blacklist) |
| GET | `/api/auth/me` | Get current user info |

**Login Request**:

```json
{
  "username": "zhangsan",
  "password": "********",
  "provider": "local"
}
```

**Login Response**:

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

#### 9.2.2 Project Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projects` | Create project |
| GET | `/api/projects` | List projects visible to user |
| GET | `/api/projects/{id}` | Project detail |
| PUT | `/api/projects/{id}` | Update project |
| DELETE | `/api/projects/{id}` | Archive project (soft delete) |

**Create Project Request**:

```json
{
  "name": "2024数字贸易政策研究",
  "description": "...",
  "group_id": "g-001"
}
```

#### 9.2.3 Admin Endpoints (Admin Permission Required)

| Method | Endpoint | Description | Required Role |
|--------|----------|-------------|---------------|
| POST | `/api/admin/users` | Create user | project_admin+ |
| GET | `/api/admin/users` | User list | project_admin+ |
| PUT | `/api/admin/users/{id}` | Update user | project_admin+ |
| DELETE | `/api/admin/users/{id}` | Deactivate user | system_admin |
| POST | `/api/admin/groups` | Create project group | system_admin |
| GET | `/api/admin/groups` | Project group list | project_admin+ |
| GET | `/api/admin/groups/{id}/members` | List group members (with username/display name) | project_admin+ |
| POST | `/api/admin/groups/{id}/members` | Add group member | project_admin+ |
| DELETE | `/api/admin/groups/{id}/members/{user_id}` | Remove group member | project_admin+ |
| GET | `/api/admin/groups/{id}/non-members` | Search non-member users (for member selection) | project_admin+ |
| GET | `/api/admin/audit-logs` | Query audit logs | system_admin |

**Query Audit Logs**:

```
GET /api/admin/audit-logs?user_id=uuid&action=create_task&resource_type=task&from=2026-05-01&to=2026-05-17&page=1&page_size=50
```

### 9.3 LDAP/SSO Authentication Flow

```
User login (provider=ldap)
    │
    ├──→ Attempt LDAP bind (dn=uid=zhangsan,ou=people,dc=institution,dc=cn)
    │     Success? → Find or create local user record → Issue JWT
    │     Failure? → Return 401
    │
    └──→ LDAP group mapping:
          ldap_group → project_group
          memberOf → Auto-sync group membership
```

### 9.4 Data Isolation Rules

| Resource | Visibility Scope |
|----------|-----------------|
| Projects | Members of the owning project group |
| Documents | Users visible to the owning project |
| Tasks | Users visible to the owning project |
| Task Outputs | Users visible to the owning project |
| Institutional Knowledge Base | Same group members + authorized cross-group users |
| Audit Logs | system_admin can see all; project_admin can see own group |

### 9.5 Audit Log Immutability

The audit log table ensures integrity through the following mechanisms:
- INSERT only, no UPDATE/DELETE permissions (application layer + database layer)
- Dedicated database user `econai_audit` for writes, application user only has SELECT
- Periodic archiving (export to cold storage after 6 months)

### 9.6 GDPR Data Subject Rights

| Right | API Endpoint | Description |
|-------|-------------|-------------|
| Right of Access | `GET /api/user/data` | Export all personal data of the user |
| Right to Erasure | `DELETE /api/user/data` | Cascading deletion of user data |
| Right to Portability | `GET /api/user/data/export` | Full data export in JSON format |
| Consent Management | `PUT /api/user/consent` | Update data processing consent status |

### 9.7 Configuration Items

| Configuration Item | Default Value | Description |
|--------------------|---------------|-------------|
| `LDAP_ENABLED` | false | Whether to enable LDAP |
| `LDAP_SERVER` | `ldap://localhost:389` | LDAP server address |
| `LDAP_BASE_DN` | `dc=institution,dc=cn` | LDAP search base |
| `LDAP_USER_FILTER` | `(uid=%(username)s)` | User search filter |
| `LDAP_GROUP_MAPPING` | `{}` | LDAP group to local group mapping |
| `AUDIT_LOG_RETENTION_MONTHS` | 6 | Audit log retention months |
| `TOKEN_BLACKLIST_ENABLED` | true | Whether to enable token blacklist |

---

## 10. Inter-Module Communication Contracts

### 10.1 Communication Overview

```
┌──────────┐    Sync HTTP      ┌──────────┐
│ API GW   │←────────────────→│ Services  │  REST API
└──────────┘                   └──────────┘

┌──────────┐    Redis Pub/Sub  ┌──────────┐
│ Document  │──────────────────→│ KB       │  Index events
│ Parsing   │                   │ Service  │
└──────────┘                   └──────────┘

┌──────────┐    Sync HTTP      ┌──────────┐
│ Task     │←────────────────→│ LLM      │  chat completion
│ Orch.    │←────────────────→│ Router   │
│          │←────────────────→│ KB       │  hybrid search
│          │←────────────────→│ Citation │  verify citations
│          │──────────────────→│ Output   │  generate output
└──────────┘                   └──────────┘

┌──────────┐    Sync HTTP      ┌──────────┐
│ API GW   │←────────────────→│ User     │  Auth/Authz/Admin
└──────────┘                   │ Service  │
                               └──────────┘

┌──────────┐    Redis Pub/Sub  ┌──────────┐
│ Services │──────────────────→│ API GW   │  Audit events → audit_logs
└──────────┘                   └──────────┘
```

### 10.2 Synchronous Interface Contracts

#### Knowledge Base Search

```
POST http://kb-service:8001/internal/search
Content-Type: application/json

Request:
{
  "query": "string",
  "project_id": "uuid",
  "user_id": "uuid",
  "top_k": 10,
  "filters": {"document_ids": ["..."], "chunk_types": ["paragraph"]}
}

Response (200):
{
  "results": [{"chunk_id": "...", "content": "...", "score": 0.92, "metadata": {...}}],
  "total_hits": 45,
  "search_time_ms": 120
}

Errors:
404: Project does not exist
403: User does not have access to this project
500: Vector database unavailable
```

#### LLM Chat

```
POST http://llm-router:8002/internal/llm/chat
Content-Type: application/json

Request: See 6.2.1
Response: See 6.2.1

Errors:
429: Rate limit
503: Model unavailable
504: Request timeout
```

#### Citation Verification

```
POST http://citation-service:8003/internal/citations/verify
Content-Type: application/json

Request: See 7.2.1
Response: See 7.2.1

Errors:
400: Invalid text format (no citation markers)
500: Processing failed
```

#### Output Generation

```
POST http://output-service:8004/internal/output/generate
Content-Type: application/json

Request: See 8.2.1
Response: See 8.2.1

Errors:
400: Unsupported output format
500: Generation failed
```

### 10.3 Asynchronous Event Contracts

#### Index Request Event

```
Channel: kb:index:request

Message:
{
  "event_id": "evt-uuid",
  "event_type": "document.parsed",
  "document_id": "doc-uuid",
  "project_id": "proj-uuid",
  "chunk_ids": ["chunk-001", "chunk-002", ...],
  "timestamp": "2026-05-17T10:35:00Z"
}

Consumer: kb-service
Processing: Vectorize + write to vector DB + update status
```

#### Audit Event

```
Channel: audit:log

Message:
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

Consumer: user-service (audit_log sub-module)
Processing: Write to audit_logs table
```

### 10.4 Service Discovery

| Service | Internal Hostname | Port |
|---------|-------------------|------|
| api-gateway | `api-gateway` | 8000 |
| document-service | `document-service` | 8001 |
| kb-service | `kb-service` | 8002 |
| orchestration-service | `orchestration-service` | 8003 |
| llm-router | `llm-router` | 8004 |
| citation-service | `citation-service` | 8005 |
| output-service | `output-service` | 8006 |
| user-service | `user-service` | 8007 |

Services communicate with each other by service name within the Docker Compose network.

---

## 11. Error Handling Strategy

### 11.1 Error Code System

```
Format: {DOMAIN}_{ISSUE}

DOMAIN:
  AUTH      Authentication related
  DOC       Document related
  KB        Knowledge base related
  TASK      Task related
  LLM       LLM related
  CITATION  Citation related
  OUTPUT    Output related
  USER      User related
  SYS       System level

Examples:
  AUTH_TOKEN_MISSING        Missing authentication Token
  AUTH_TOKEN_EXPIRED        Token expired
  DOC_PARSE_FAILED          Document parsing failed
  DOC_FORMAT_UNSUPPORTED    Unsupported document format
  DOC_NOT_FOUND             Document not found
  DOWNLOAD_FAILED           File download failed
  KB_SEARCH_TIMEOUT         Search timeout
  TASK_CREATE_FAILED        Task creation failed
  TASK_AGENT_LOOP_EXCEEDED  Agent reached max iterations
  LLM_ROUTE_FAILED          LLM routing failed
  LLM_MODEL_UNAVAILABLE     Model unavailable
  CITATION_VERIFY_FAILED    Citation verification failed
  OUTPUT_GENERATE_FAILED    Output generation failed
  USER_PERMISSION_DENIED    Insufficient permissions
  SYS_INTERNAL_ERROR        Internal error
```

### 11.2 Error Propagation

```
Service internal error → Structured error object → HTTP status code → API Gateway unified formatting → Client

Inter-service call errors:
  - 4xx: Pass through to caller (e.g., insufficient permissions)
  - 5xx: Wrap as SYS_DEPENDENCY_FAILED, log
  - Timeout: Caller retries or degrades based on policy
```

### 11.3 Retry Strategy

| Scenario | Max Retries | Backoff Strategy | Notes |
|----------|------------|------------------|-------|
| LLM call (429) | 3 | Exponential backoff, base=2s | |
| LLM call (5xx) | 2 | Linear backoff, 1s | Second retry may degrade to local |
| KB search timeout | 1 | Immediate | Return empty results if still timeout |
| Celery task | No auto retry | - | User manually retries |
| Inter-service HTTP call | 2 | Exponential backoff, base=1s | With jitter |

---

## 12. Test Strategy Summary

### 12.1 Test Levels

| Level | Scope | Tool | Coverage Target |
|-------|-------|------|-----------------|
| Unit Test | Internal logic of each service | pytest | Core algorithms, state machines, format conversion |
| Integration Test | Inter-service API calls | pytest + testcontainers | All API endpoints, error paths |
| E2E Test | Complete user scenarios | Playwright | Core scenarios like literature review, policy comparison |
| Performance Test | Critical paths | Locust | Search latency, Agent task duration |

### 12.2 Key Test Points by Module

| Module | Key Test Points |
|--------|-----------------|
| Document Parsing | Correctness of each format parsing, chunking boundaries, OCR accuracy (including embedded image OCR), exception format handling, image extraction correctness |
| Knowledge Base | Index completeness, hybrid search recall rate, RRF fusion correctness, permission isolation |
| Task Orchestration | Agent state machine, tool call sequence, Plan/Finish determination, iteration limit |
| LLM Routing | Sensitivity determination rules, adapter conversion correctness, degradation strategy |
| Source Citation | Citation regex parsing, verification confidence, edge cases (no citations / all uncertain) |
| Output Generation | GB/T 9704 format correctness, citation-to-footnote conversion, large data volume performance |
| User Permission | RBAC boundary for each role, LDAP authentication, token refresh, audit integrity |
| API Gateway | Rate limit accuracy, JWT expiration handling, unauthenticated/unauthorized interception |

---

*Document Version: v1.3 | Date: 2026-05-29 | Based on High-Level Design Document v1.0*

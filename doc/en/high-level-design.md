# EconAI High-Level Design Document

> Version: v1.0 | Date: 2026-05-17 | Based on Requirements Document v2.0 (Final)

---

## 1. Design Overview

### 1.1 Design Goals

Based on the institutional-grade AI analysis toolkit positioning confirmed in the requirements document, the high-level design follows these goals:

- **Modular**: Services are independently deployed and evolved, communicating via APIs
- **Configurable**: Knowledge sources, LLM routing, and analysis workflows are all configurable
- **Auditable**: Full-chain operation logs + sentence-by-sentence source traceability
- **Secure and Compliant**: Hybrid LLM deployment + data stays within the intranet + Level 2 Information Security Protection + GDPR

### 1.2 Core Design Decisions

| Decision Item | Choice | Brief Description |
|--------|------|------|
| Embedding Model | text2vec / m3e | Chinese open-source embedding, privately deployed |
| Workflow Orchestration | Self-developed lightweight Agent | LLM-driven tool calls, not fixed pipelines |
| Source Traceability | Inline citations | Insert source markers during generation, parse and format upon output |
| Document Chunking | Multi-granularity chunking | Paragraph-level (precise retrieval) + Section-level (context window) |
| Retrieval Strategy | Hybrid Retrieval + Reranker | Vector semantics + BM25 keyword + Re-ranking |
| Interaction Mode | Async tasks + progress polling | Long tasks execute in background, frontend polls for progress |
| Conversation Mode | Single-shot generation | Submit → Wait → Get results, no multi-round revisions |

---

## 2. System Architecture

### 2.1 Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        Client Layer                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              React + TypeScript SPA                          │ │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────────────┐   │ │
│  │  │ Project │ │Knowledge│ │ Analysis │ │ Output/Export  │   │ │
│  │  │ Manage- │ │  Base   │ │  Task    │ │ Preview/Review │   │ │
│  │  │  ment   │ │ Manage- │ │ Submit/  │ │                │   │ │
│  │  │  View   │ │  ment   │ │ Monitor  │ │                │   │ │
│  │  └─────────┘ └─────────┘ └──────────┘ └────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                                    │
                            TLS 1.2+ (HTTPS)
                                    │
┌──────────────────────────────────────────────────────────────────┐
│                        API Gateway Layer                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   FastAPI + Nginx                             │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │ │
│  │  │  Auth    │ │  Rate    │ │  RBAC    │ │ Audit Log     │  │ │
│  │  │  (JWT)   │ │ Limiting │ │ Middle-  │ │ Middleware    │  │ │
│  │  │          │ │ (token   │ │  ware    │ │               │  │ │
│  │  │          │ │  bucket) │ │          │ │               │  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────┐
│                        Service Layer                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Document │ │Knowledge │ │  Task    │ │ Output   │           │
│  │ Parsing  │ │  Base    │ │Orchestra-│ │Generation│           │
│  │ Service  │ │ Service  │ │  tion    │ │ Service  │           │
│  │          │ │          │ │ Service  │ │          │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────┐        │
│  │ Citation │ │  User &  │ │   LLM Routing Service    │        │
│  │ Service  │ │Permission│ └──────────────────────────┘        │
│  │          │ │ Service  │                                      │
│  └──────────┘ └──────────┘                                      │
└──────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────┐
│                  Data & Infrastructure Layer                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │PostgreSQL│ │Milvus/   │ │  MinIO   │ │ Celery + Redis     │  │
│  │(Business │ │Qdrant    │ │(Document │ │ (Async Task Queue) │  │
│  │  Data)   │ │(Vector   │ │ Storage) │ │                    │  │
│  │          │ │ Index)   │ │          │ │                    │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────────────┐ │
│  │Local LLM │ │ Claude   │ │ Prometheus + Grafana            │ │
│  │(vLLM/   │ │ API      │ │ (Monitoring & Alerting)         │ │
│  │ Ollama) │ │ (Cloud)  │ │                                  │ │
│  └──────────┘ └──────────┘ └──────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Module Division and Responsibilities

```
EconAI
├── api-gateway/           # API Gateway + Middleware
│   ├── auth_middleware    # JWT Authentication
│   ├── rbac_middleware    # Role-Based Access Control
│   ├── rate_limiter       # Rate Limiting
│   └── audit_middleware   # Operation Auditing
│
├── services/
│   ├── document-service/  # Document Parsing Service
│   │   ├── ingestion      # File Upload/Import
│   │   ├── parser         # Multi-format Parser
│   │   ├── ocr            # OCR Processing (Tesseract)
│   │   └── chunker        # Multi-granularity Chunking
│   │
│   ├── kb-service/        # Knowledge Base Service
│   │   ├── project_kb     # Project KB CRUD
│   │   ├── inst_kb        # Institutional KB CRUD
│   │   ├── indexer        # Vector Indexing (embedding generation + storage)
│   │   ├── searcher       # Hybrid Retrieval (vector + BM25 + Reranker)
│   │   └── lifecycle      # Archival, Expiry, Deletion
│   │
│   ├── orchestration-service/  # Task Orchestration Service
│   │   ├── task_manager   # Task Lifecycle Management
│   │   ├── agent_engine   # Self-developed Lightweight Agent Loop Engine
│   │   ├── tools          # Agent Available Tools (retrieval/generation/verification/formatting)
│   │   └── progress       # Progress Tracking and Reporting
│   │
│   ├── llm-router/        # LLM Routing Service
│   │   ├── registry       # Model Registry
│   │   ├── router         # Sensitivity Analysis + Routing Decision
│   │   ├── adapter        # Claude API Adapter
│   │   ├── adapter        # vLLM/Ollama Local Adapter
│   │   └── tracker        # Token Usage Tracking
│   │
│   ├── output-service/    # Output Generation Service
│   │   ├── markdown_gen   # Markdown Generation
│   │   ├── docx_gen       # GB/T 9704 Official Document .docx Generation
│   │   ├── xlsx_gen       # Excel Spreadsheet Generation
│   │   ├── pptx_gen       # PPT Briefing Generation
│   │   └── template       # Format Template Management
│   │
│   ├── citation-service/  # Citation Traceability Service
│   │   ├── parser         # Inline Citation Parser
│   │   ├── verifier       # Source Verification (match chunk metadata)
│   │   └── formatter      # Citation Formatting (footnote/endnote/sidebar)
│   │
│   └── user-service/      # User & Permission Service
│       ├── user_mgmt      # User Management
│       ├── group_mgmt     # Project Group Management
│       ├── role_mgmt      # Role Management
│       ├── ldap_auth      # LDAP/SSO Integration
│       └── audit_log      # Audit Log Storage & Query
```

### 2.3 Module Interaction Matrix

```
                    ┌──────────┐
                    │  API GW  │
                    └────┬─────┘
                         │
         ┌───────────────┼───────────────┬───────────────┐
         ▼               ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐
    │Document │    │Knowledge│    │ User &   │    │  Task   │
    │ Service │    │  Base   │    │Permission│    │Orchestra-│
    │         │    │ Service │    │ Service  │    │  tion   │
    └────┬─────┘    └────┬─────┘    └──────────┘    │ Service │
         │               │                          └────┬─────┘
         │  Write to     │  Write to                      │
         │  MinIO        │  Milvus/                       │
         │               │  Qdrant                        │
         ▼               ▼                                │
    ┌─────────┐    ┌──────────┐                           │
    │  MinIO  │    │  Vector  │                           │
    │         │    │ Database │                           │
    └─────────┘    └──────────┘                           │
                                                          │
                          ┌───────────────────────────────┤
                          ▼               ▼               ▼
                     ┌─────────┐   ┌──────────┐  ┌──────────┐
                     │   LLM   │   │  Output  │  │ Citation │
                     │  Router │   │Generation│  │  Service │
                     └────┬────┘   └──────────┘  └──────────┘
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
           ┌──────────┐    ┌──────────┐
           │Claude API│    │Local LLM │
           │ (Cloud)  │    │(GPU      │
           │          │    │ Cluster) │
           └──────────┘    └──────────┘
```

---

## 3. Core Module Design

### 3.1 Document Parsing Service (Document Service)

#### 3.1.1 Responsibilities

Receives documents uploaded by users, performs format identification, content extraction, and structured chunking, providing structured data for subsequent indexing and retrieval.

#### 3.1.2 Processing Pipeline

```
File Upload → Format Identification → Content Extraction → Metadata Extraction → Multi-granularity Chunking → Storage
                    │                      │                      │
                    ▼                      ▼                      ▼
                Tesseract              Full Text              Title/Author/Date
                (Scanned docs)         Structured Info        Page/Section
```

#### 3.1.3 Format Handlers

| Format | Parser | Output |
|------|--------|------|
| PDF | PyMuPDF / pdfplumber | Full text + page numbers + tables |
| Word | python-docx | Full text + paragraph styles + tables |
| Markdown/Plain Text | Standard library | Full text |
| Excel/CSV | openpyxl / pandas | Structured tables + column name semantics |
| PowerPoint | python-pptx | Per-slide text |
| Image PDF/Image | Tesseract OCR → same as PDF | Full text + page numbers |
| .eml | email standard library | Body + metadata (sender/date/subject) |
| HTML/MHTML | BeautifulSoup | Body extraction + original links |

#### 3.1.4 Multi-granularity Chunker

```
Original Document (e.g., PDF)
       │
       ├── Section-level Chunk (~2000 tokens)
       │   ├── Contains complete sections/subsections
       │   ├── Metadata: {doc_id, section_title, page_range}
       │   └── Use: Provide sufficient context for Agent generation
       │
       └── Paragraph-level Chunk (~300 tokens)
           ├── Split by natural paragraph boundaries
           ├── Metadata: {doc_id, section_title, page_number, paragraph_index}
           └── Use: Precise retrieval + inline citation traceability
```

**Chunking Parameters**:
- Paragraph-level: target 300 tokens, min 100, max 500; aligned to natural paragraph boundaries
- Section-level: target 2000 tokens, min 500, max 3000; aligned to section headings
- Adjacent chunk overlap: 50 tokens for paragraph-level, 100 tokens for section-level

### 3.2 Knowledge Base Service (KB Service)

#### 3.2.1 Responsibilities

Manages the lifecycle of knowledge bases, converts chunked document content into vector indexes, and provides hybrid retrieval capabilities.

#### 3.2.2 Indexing Pipeline

```
Chunk → text2vec/m3e Embedding → Vector stored in Milvus/Qdrant
     → Text + Metadata → Stored in PostgreSQL (document_chunks table)
     → Text → BM25 Index (Elasticsearch or PG built-in full-text search)
```

#### 3.2.3 Hybrid Retrieval Flow

```
User Query (Natural Language)
       │
       ├──→ Vector Retrieval (Milvus/Qdrant)      → top_k=50
       │        Semantic similarity matching
       │
       ├──→ BM25 Keyword Retrieval (PostgreSQL FTS) → top_k=50
       │        Exact keyword matching
       │
       └──→ Result Fusion (RRF: Reciprocal Rank Fusion)
             │
             ▼
           Fused top_k=30
             │
             ▼
           Reranker (BGE-Reranker / cross-encoder)
             │  Re-rank to improve relevance
             ▼
           top_k=10 returned to Agent
```

**RRF Fusion Formula**:
```
score(doc) = Σ 1/(k + rank_i(doc))
```
Where k=60, and rank_i is the rank in each retriever.

#### 3.2.4 Knowledge Base Isolation

| KB Type | Isolation Method | Description |
|------------|----------|------|
| Project KB | Filter by project_id | Visible only within this project |
| Institutional KB | Filter by group_id + access policy | Shared within group, can be authorized across groups |

Inject project context filters during queries to ensure data isolation.

### 3.3 Task Orchestration Service

#### 3.3.1 Self-developed Lightweight Agent Design
The core of the Agent loop is a variant of the **ReAct pattern** — Plan → Retrieve → Generate → Verify → Decide:

```
┌─────────────────────────────────────────────┐
│              Agent Loop                      │
│                                             │
│  1. Plan                                    │
│     Analyze task goal → Identify info gaps  │
│       → Generate retrieval plan             │
│     ↓                                       │
│  2. Retrieve (Tool)                         │
│     Call KB Service hybrid retrieval        │
│     ↓                                       │
│  3. Generate (Tool)                         │
│     Call LLM to generate content fragments  │
│       with inline citations                 │
│     ↓                                       │
│  4. Verify  (Tool)                          │
│     Verify inline citations match           │
│       retrieved chunks                      │
│     ↓                                       │
│  5. Decide                                  │
│     - Sufficient info? → Enter Format stage │
│     - Insufficient? → Back to Plan          │
│       (max 5 iterations)                    │
│     ↓                                       │
│  6. Format (Tool)                           │
│     Integrate fragments → Full document     │
└─────────────────────────────────────────────┘
```

#### 3.3.2 Agent Tool Definitions

| Tool Name | Description | Input | Output |
|--------|------|------|------|
| `search_kb` | Hybrid knowledge base retrieval | query, filters, top_k | Chunk list with metadata |
| `generate_section` | LLM generates section content | system_prompt, context(chunks), section_goal | Text with inline citations |
| `verify_citations` | Verify citation accuracy | generated_text, context_chunks | Verification report (direct/fuzzy/uncertain) |
| `extract_key_claims` | Extract key arguments | generated_text | Structured argument list |
| `compare_policies` | Multi-policy option comparison | policy_descriptions, context | Comparative analysis text + matrix |
| `format_output` | Format final output | full_text, citations, format | File in specified format |

#### 3.3.3 Agent Prompt Structure

```
System Prompt Composition:
  ├── Role Definition ("You are an economic policy analysis assistant...")
  ├── Current Task Description
  ├── Knowledge Source Summary (list of available documents for this task)
  ├── Output Format Specification (including inline citation format requirements)
  ├── Available Tool Descriptions
  └── Constraints (confidence marking rules, mark "no evidence support" when uncertain)
```

#### 3.3.4 Task State Machine

```
pending ──→ running ──→ completed
                │
                ├──→ failed ──→ (retryable)
                │
                └──→ cancelled
```

#### 3.3.5 Progress Tracking

Agent updates task progress after completing each step:

```python
# progress field structure
{
    "step": "retrieving",     # Current step name
    "step_index": 2,          # Which step
    "total_steps_estimate": 8, # Estimated total steps
    "message": "正在检索相关政策文献..."  # User-readable progress description
}
```

### 3.4 LLM Routing Service

#### 3.4.1 Architecture

```
Caller (Agent/Other Services)
       │
       ▼
┌──────────────────┐
│   Sensitivity     │
│   Analyzer        │  Analyze whether request contains internal/sensitive knowledge sources
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   Router          │
│                   │
│  Sensitive data? ──→ Local LLM (vLLM/Ollama)
│  Public data?   ──→ Claude API (Cloud)
│  User specified?──→ User-selected model
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   Adapter         │  Unified request/response format
│                   │
│  ClaudeAdapter    │  Anthropic SDK
│  LocalAdapter     │  OpenAI-compatible API (supported by both vLLM/Ollama)
└──────────────────┘
```

#### 3.4.2 Sensitivity Determination Rules

```python
def analyze_sensitivity(task: AnalysisTask, kb_sources: list[KBSource]) -> Sensitivity:
    """Determine the sensitivity of the analysis task"""
    
    # Rule 1: Task's knowledge sources contain internal reports → sensitive
    if any(source.source_type == "internal" for source in kb_sources):
        return Sensitivity.HIGH
    
    # Rule 2: Task type is policy draft (usually based on internal documents) → sensitive
    if task.type == TaskType.POLICY_DRAFT:
        return Sensitivity.HIGH
    
    # Rule 3: User explicitly marks → respect user choice
    if task.sensitivity_override:
        return task.sensitivity_override
    
    # Rule 4: Pure public literature analysis → non-sensitive, use cloud
    return Sensitivity.LOW
```

#### 3.4.3 Unified Request Format

Local models are exposed via vLLM/Ollama's OpenAI-compatible API, so a unified format is used:

```json
{
    "model": "claude-sonnet-4-6 | local:qwen3 | local:deepseek-v3",
    "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
    "temperature": 0.3,
    "max_tokens": 4096,
    "stream": false
}
```

### 3.5 Citation Traceability Service

#### 3.5.1 Inline Citation Format

LLM must follow the agreed citation format when generating:

```
近年来，数字贸易规则已成为全球贸易治理的核心议题[ref:doc_123:p45-48]。
多项研究表明数字服务税对中小企业的影响存在显著异质性[ref:doc_456:p12|doc_789:p33-35]。
```

**Format Specification**:
- Single citation: `[ref:{doc_id}:{page_range}]`
- Multiple citations: `[ref:{doc_id}:{page}|{doc_id}:{page}]`
- No evidence declaration: `[ref:uncertain]` — LLM's own reasoning, informing the reader this is model inference

#### 3.5.2 Processing Pipeline

```
LLM Output Text (with [ref:...] markers)
       │
       ▼
  CitationParser
       │  Regex extract all [ref:xxx] markers
       │  Build "sentence → doc_id → page_range" mapping
       ▼
  CitationVerifier
       │  Query whether doc_id + page_range exists in retrieved chunks
       │  Mark confidence: direct (exact match) | fuzzy (paragraph match) | uncertain (no match)
       ▼
  CitationFormatter
       │  Generate user-readable citation format
       │  Frontend interaction data (click to show original text)
       │  .docx footnote/endnote
```

#### 3.5.3 Confidence Marking

| Confidence | Meaning | Trigger Condition |
|--------|------|----------|
| `direct` | Direct citation | Chunk metadata page_range exactly matches the citation |
| `fuzzy` | Paragraph match | Chunk text semantic similarity > 0.85, but page numbers not fully consistent |
| `uncertain` | Model inference | LLM generated but no direct basis found in retrieved chunks |

### 3.6 Output Generation Service

#### 3.6.1 Supported Formats and Generation Methods

| Format | Generation Engine | Key Requirements |
|------|----------|----------|
| Markdown | jinja2 template rendering | Plain text + citation links |
| .docx | python-docx + custom templates | GB/T 9704 official document national standard (header/body/footer) |
| .xlsx | openpyxl | Comparison matrices, data summaries |
| .pptx | python-pptx | Key findings briefing, chart support |

#### 3.6.2 GB/T 9704 .docx Format Mapping

```
Official Document Element     python-docx Implementation
─────────────────────────────────────
Header (Issuing Authority)    → Page header fixed style
Document Number               → Paragraph style "发文字号"
Signatory                     → Right-aligned signature line
Title                         → Size 2 small Song typeface, centered
Primary Recipient             → Paragraph style "主送"
Body Text                     → Size 3 FangSong, first-line indent 2 characters
Attachment Note               → Paragraph style "附件"
Issuing Authority Signature   → Right-aligned, date aligned below
Document Date                 → Chinese date format
Footer (CC/Print Distribution)→ Footer area
```

#### 3.6.3 Citation Presentation in Exported Files

- **.docx**: Marked with superscript [1],[2] in body, citation list at end of document, or as footnotes
- **.md**: Retain [ref:...] in body → rendered as `[^1]` footnote syntax
- **.xlsx**: Separate sheet "引用清单" listing all citations
- **.pptx**: Small citation source annotation at bottom of each slide, full citation list on last slide

---

## 4. Data Flow

### 4.1 Literature Review — Complete Data Flow

```
Timeline →

[User]                     [System]
  │                         │
  ├─ Create project         │
  │                         ├─ Create project record
  │                         │
  ├─ Upload literature      │
  │  (multiple PDFs)        │
  │                         ├─ Original files → MinIO
  │                         ├─ Format parsing → Text extraction
  │                         ├─ Multi-granularity chunking → chunks
  │                         ├─ Vectorization (embedding) → Milvus/Qdrant
  │                         ├─ BM25 index → PostgreSQL FTS
  │                         └─ Metadata storage → PostgreSQL
  │                         │
  ├─ Submit "Literature     │
  │  Review" task           │
  │  Parameters:            │
  │  - KB scope (just       │
  │    uploaded literature) │
  │  - Review topic/angle   │
  │  - Output format (.docx)│
  │                         ├─ Create task record (status=pending)
  │                         ├─ Push to Celery queue
  │                         │
  ├─ Poll GET /tasks/{id}/status
  │                         ├─ Agent loop starts:
  │                         │   ┌─ Plan: "First retrieve core arguments of all literature"
  │                         │   ├─ search_kb("数字贸易规则演变 核心论点")
  │                         │   ├─ generate_section(retrieval results → "Research Background" section)
  │                         │   ├─ verify_citations(generated text)
  │                         │   ├─ Plan: "Supplement retrieval for methodological differences"
  │                         │   ├─ search_kb("政策影响评估方法 实证分析")
  │                         │   ├─ generate_section(retrieval results → "Methodology Comparison" section)
  │                         │   ├─ ...
  │                         │   └─ format_output(all sections → .docx)
  │                         │
  │                         ├─ Store task_outputs
  │                         ├─ Store citations
  │                         └─ status=completed
  │                         │
  ├─ View output (Web preview) │
  ├─ Click citation marker   │
  │  to view source          │
  ├─ Export .docx            │
  └─ Download                └─ Return file stream
```

### 4.2 Agent Loop Internal Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                  Agent Engine                           │
│                                                        │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐         │
│  │ Context  │───→│ LLM Call │───→│ Tool Call│         │
│  │ Builder  │    │ (Plan/   │    │ Execution│         │
│  │          │    │  Decide) │    │          │         │
│  └──────────┘    └──────────┘    └──────────┘         │
│       ▲                               │                │
│       │        ┌──────────┐          │                │
│       └────────│ State    │←─────────┘                │
│                │ Update   │                            │
│                └──────────┘                            │
│                                                        │
│  Agent State:                                          │
│  {                                                     │
│    "messages": [...],         // Conversation history  │
│    "retrieved_chunks": [...],  // All retrieved chunks │
│    "generated_sections": [...], // Generated sections  │
│    "citations": {...},        // Citation mapping      │
│    "plan": "...",             // Current plan          │
│    "iteration": 3,            // Current iteration     │
│    "remaining_sections": [...] // Sections to complete │
│  }                                                     │
└─────────────────────────────────────────────────────────┘
```

---

## 5. API Design

### 5.1 RESTful API Endpoints

#### 5.1.1 Authentication

| Method | Endpoint | Description |
|------|------|------|
| POST | `/api/auth/login` | Username/password login / LDAP auth, returns JWT |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/me` | Get current user info |

#### 5.1.2 Project Management

| Method | Endpoint | Description |
|------|------|------|
| POST | `/api/projects` | Create project |
| GET | `/api/projects` | List projects visible to current user (isolated by project group) |
| GET | `/api/projects/{id}` | Get project details |
| PUT | `/api/projects/{id}` | Update project info |
| DELETE | `/api/projects/{id}` | Delete project (soft delete, archive) |

#### 5.1.3 Knowledge Base

| Method | Endpoint | Description |
|------|------|------|
| POST | `/api/projects/{id}/documents` | Upload document (multipart/form-data) |
| GET | `/api/projects/{id}/documents` | List project documents |
| GET | `/api/projects/{id}/documents/{doc_id}` | Get document details and parsing status |
| DELETE | `/api/projects/{id}/documents/{doc_id}` | Delete document and index |
| POST | `/api/projects/{id}/documents/{doc_id}/reindex` | Re-index document |
| POST | `/api/projects/{id}/search` | Search project knowledge base |
| POST | `/api/institutional/search` | Search institutional knowledge base |

#### 5.1.4 Analysis Tasks

| Method | Endpoint | Description |
|------|------|------|
| POST | `/api/projects/{id}/tasks` | Create analysis task |
| GET | `/api/projects/{id}/tasks` | List project tasks |
| GET | `/api/tasks/{task_id}` | Get task details |
| GET | `/api/tasks/{task_id}/status` | Poll task status and progress |
| POST | `/api/tasks/{task_id}/cancel` | Cancel task |
| POST | `/api/tasks/{task_id}/retry` | Retry failed task |

**Create Task Request Body**:

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

#### 5.1.5 Output & Export

| Method | Endpoint | Description |
|------|------|------|
| GET | `/api/tasks/{task_id}/output` | Get output content (Markdown format preview) |
| GET | `/api/tasks/{task_id}/output/citations` | Get all citation details |
| GET | `/api/tasks/{task_id}/output/citations/{citation_id}` | Get single citation details (with original text excerpt) |
| GET | `/api/tasks/{task_id}/export` | Export file (query: format=docx|md|xlsx|pptx) |

#### 5.1.6 Admin Endpoints

| Method | Endpoint | Description |
|------|------|------|
| POST | `/api/admin/users` | Create user |
| GET | `/api/admin/users` | List users |
| PUT | `/api/admin/users/{id}` | Update user |
| DELETE | `/api/admin/users/{id}` | Delete user |
| POST | `/api/admin/groups` | Create project group |
| GET | `/api/admin/groups` | List project groups |
| POST | `/api/admin/groups/{id}/members` | Add group member |
| DELETE | `/api/admin/groups/{id}/members/{user_id}` | Remove group member |
| GET | `/api/admin/audit-logs` | Query audit logs |

### 5.2 Error Response Format

```json
{
    "error": {
        "code": "DOCUMENT_PARSE_FAILED",
        "message": "文档解析失败：PDF 第 3 页包含无法识别的编码",
        "details": {
            "document_id": "doc_123",
            "page": 3
        }
    }
}
```

### 5.3 Pagination & Filtering

List endpoints uniformly support:

```
GET /api/projects?page=1&page_size=20&status=active&sort=created_at:desc
```

---

## 6. Data Model

### 6.1 Core Entity Relationships

```
┌──────────┐     ┌──────────────────┐     ┌──────────┐
│   User   │────→│ ProjectGroupMember│←────│ Project  │
│          │     │                  │     │  Group   │
└──────────┘     └──────────────────┘     └──────────┘
     │                                          │
     │ belongs_to                               │ has_many
     ▼                                          ▼
┌──────────┐     ┌──────────┐     ┌──────────────────┐
│  Project │────→│ Document │────→│  DocumentChunk   │
│          │     │          │     │                  │
└──────────┘     └──────────┘     └──────────────────┘
     │                                          │
     │ has_many                                 │ references
     ▼                                          ▼
┌──────────────┐                          ┌──────────┐
│ AnalysisTask │                          │ Citation │
│              │                          │          │
└──────────────┘                          └──────────┘
     │
     │ has_many
     ▼
┌──────────────┐
│ TaskOutput   │
│              │
└──────────────┘
```

### 6.2 Key Table Structures

#### users

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(255),
    display_name VARCHAR(128),
    role VARCHAR(32) NOT NULL DEFAULT 'analyst',  -- analyst | senior_researcher | project_admin | system_admin
    auth_provider VARCHAR(32) DEFAULT 'local',     -- local | ldap | sso
    ldap_dn VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

#### project_groups

```sql
CREATE TABLE project_groups (
    id UUID PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT now()
);
```

#### project_group_members

```sql
CREATE TABLE project_group_members (
    id UUID PRIMARY KEY,
    group_id UUID REFERENCES project_groups(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,  -- analyst | senior_researcher | project_admin
    UNIQUE(group_id, user_id)
);
```

#### projects

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    description TEXT,
    group_id UUID REFERENCES project_groups(id),
    created_by UUID REFERENCES users(id),
    status VARCHAR(32) DEFAULT 'active',  -- active | archived
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

#### documents

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    filename VARCHAR(512) NOT NULL,
    original_name VARCHAR(512) NOT NULL,
    format VARCHAR(32) NOT NULL,       -- pdf | docx | txt | md | xlsx | csv | pptx | eml | html | image
    size_bytes BIGINT,
    page_count INT,
    storage_path VARCHAR(1024),        -- MinIO object path
    parse_status VARCHAR(32) DEFAULT 'pending',  -- pending | parsing | ready | error
    parse_error TEXT,
    metadata JSONB,                    -- {title, authors, date, source, ...}
    is_internal BOOLEAN DEFAULT false, -- Whether it is an internal document (affects LLM routing)
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_documents_project ON documents(project_id);
CREATE INDEX idx_documents_status ON documents(parse_status);
```

#### document_chunks

```sql
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_type VARCHAR(32) NOT NULL,   -- paragraph | section
    content TEXT NOT NULL,
    token_count INT,
    metadata JSONB NOT NULL,           -- {page_start, page_end, section_title, paragraph_index}
    embedding_id VARCHAR(256),         -- Corresponding ID in vector database
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_chunks_type ON document_chunks(chunk_type);
```

#### analysis_tasks

```sql
CREATE TABLE analysis_tasks (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    type VARCHAR(64) NOT NULL,         -- literature_review | policy_draft | policy_comparison | tech_interpretation
    title VARCHAR(512) NOT NULL,
    description TEXT,
    status VARCHAR(32) DEFAULT 'pending',  -- pending | running | completed | failed | cancelled
    params JSONB NOT NULL,             -- Analysis parameters (knowledge sources, focus areas, etc.)
    llm_route VARCHAR(32),             -- local | cloud | auto
    sensitivity VARCHAR(32),           -- high | low
    progress JSONB,                    -- {step, step_index, total_steps_estimate, message}
    iteration_count INT DEFAULT 0,
    error_message TEXT,
    celery_task_id VARCHAR(256),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT now(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_tasks_project ON analysis_tasks(project_id);
CREATE INDEX idx_tasks_status ON analysis_tasks(status);
```

#### task_outputs

```sql
CREATE TABLE task_outputs (
    id UUID PRIMARY KEY,
    task_id UUID REFERENCES analysis_tasks(id) ON DELETE CASCADE,
    format VARCHAR(32) NOT NULL,       -- markdown | docx | xlsx | pptx
    content TEXT,                      -- Markdown format stored directly (other formats store path)
    storage_path VARCHAR(1024),        -- MinIO object path (binary formats)
    created_at TIMESTAMP DEFAULT now()
);
```

#### citations

```sql
CREATE TABLE citations (
    id UUID PRIMARY KEY,
    task_output_id UUID REFERENCES task_outputs(id) ON DELETE CASCADE,
    sentence_index INT NOT NULL,       -- Sentence sequence number in output text
    ref_id VARCHAR(128) NOT NULL,      -- Unique citation marker generated by LLM
    source_text TEXT,                  -- Output sentence text
    chunk_ids UUID[],                  -- Associated document_chunks
    document_ids UUID[],               -- Associated documents
    page_ranges VARCHAR(256)[],        -- Page range array
    confidence VARCHAR(32),            -- direct | fuzzy | uncertain
    verified_by UUID REFERENCES users(id),  -- If manually reviewed
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_citations_output ON citations(task_output_id);
CREATE INDEX idx_citations_confidence ON citations(confidence);
```

#### audit_logs

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    action VARCHAR(128) NOT NULL,       -- login | logout | create_project | upload_document | create_task | export_output | ...
    resource_type VARCHAR(64),          -- project | document | task | output | user | group
    resource_id UUID,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
```

---

## 7. Agent Orchestration Engine Design

### 7.1 Engine Architecture

```
┌────────────────────────────────────────────────────────┐
│                    Agent Engine                        │
│                                                       │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐  │
│  │ ToolRegistry│   │ StateManager│   │ LoopRunner  │  │
│  │             │   │             │   │             │  │
│  │ search_kb   │   │ messages[]  │   │ while not   │  │
│  │ generate_   │   │ chunks[]    │   │  terminal:  │  │
│  │   section   │   │ sections[]  │   │   think()   │  │
│  │ verify_     │   │ citations{} │   │   act()     │  │
│  │   citations │   │ plan        │   │   observe() │  │
│  │ format_     │   │ iteration   │   │             │  │
│  │   output    │   │             │   │             │  │
│  └─────────────┘   └─────────────┘   └─────────────┘  │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │              Prompt Templates                    │  │
│  │                                                 │  │
│  │  literature_review.j2                           │  │
│  │  policy_draft.j2                                │  │
│  │  policy_comparison.j2                           │  │
│  │  tech_interpretation.j2                         │  │
│  └─────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

### 7.2 Core Loop Pseudocode

```python
class AgentEngine:
    MAX_ITERATIONS = 5
    MAX_RETRIEVED_CHUNKS = 30

    async def run(self, task: AnalysisTask, kb_sources: list[KBSource]) -> TaskOutput:
        state = AgentState(
            task=task,
            kb_sources=kb_sources,
            messages=[self._build_system_message(task)],  # system prompt
            retrieved_chunks=[],
            generated_sections=[],
            citations={},
            plan=""
        )

        while state.iteration < self.MAX_ITERATIONS:
            # Step 1: Plan — LLM decides what to do next
            plan = await self._plan(state)
            state.plan = plan

            if plan.action == "finish":
                break

            # Step 2: Execute tool
            result = await self._execute_tool(plan.tool_name, plan.tool_args, state)

            # Step 3: Observe and update state
            state = self._update_state(state, plan.tool_name, result)
            state.iteration += 1
            self._report_progress(task, state)

        # Final: format output
        return await self._format_output(state, task.output_formats)

    async def _plan(self, state: AgentState) -> Plan:
        """LLM plans next action"""
        messages = self._build_planning_messages(state)
        response = await llm_router.chat(messages, tools=self.tools_definitions)
        return parse_plan(response)  # Parse LLM's tool_call or finish signal

    async def _execute_tool(self, tool_name: str, args: dict, state: AgentState):
        match tool_name:
            case "search_kb":
                return await kb_service.hybrid_search(
                    query=args["query"],
                    kb_sources=state.kb_sources,
                    top_k=10
                )
            case "generate_section":
                return await self._generate_with_citations(
                    section_goal=args["section_goal"],
                    context=state.retrieved_chunks,
                    generated_so_far=state.generated_sections
                )
            case "verify_citations":
                return await citation_service.verify(
                    text=args["text"],
                    available_chunks=state.retrieved_chunks
                )
            case "extract_key_claims":
                return await self._extract_claims(
                    text=args["text"]
                )
            case "compare_policies":
                return await self._compare(
                    policies=args["policies"],
                    context=state.retrieved_chunks
                )
```

### 7.3 Prompt Template Example (Literature Review)

```jinja2
# System

You are the EconAI economic policy analysis assistant. Your task is to write a review report based on the provided literature.

## Current Task
{{ task.title }}
{{ task.description }}

## Knowledge Sources
This analysis is based on the following documents (uploaded to the knowledge base):
{% for doc in task.kb_sources.documents %}
- [{{ doc.id }}] {{ doc.filename }} ({{ doc.metadata.title }})
{% endfor %}

## Output Requirements
1. All assertions based on literature must use [ref:doc_id:page_range] format to mark sources
2. Uncertain inferences use [ref:uncertain] to mark
3. The review structure should include: Research Background, Core Argument Comparison, Methodology Evaluation, Policy Recommendation Summary, Research Gaps

## Available Tools
- search_kb: Search knowledge base for relevant content
- generate_section: Generate specified section content
- verify_citations: Verify citation accuracy
- extract_key_claims: Extract core arguments from literature

## Working Principles
- Prioritize using search_kb to obtain information before generating
- Search for relevant information at least once per section
- Conflicting views between different literature must be explicitly marked
- Mark the methodological quality and evidence strength of each publication
```

---

## 8. Security Architecture

### 8.1 Layered Security Model

```
┌────────────────────────────────────────┐
│  Network Layer                          │
│  - Intranet access only (VPN/internal IP)│
│  - Nginx reverse proxy, TLS termination │
│  - WAF (optional)                       │
├────────────────────────────────────────┤
│  Application Layer                      │
│  - JWT auth (access: 2h, refresh: 24h)  │
│  - LDAP/SSO integration with            │
│    institutional account system         │
│  - RBAC fine-grained permissions        │
│  - Data isolation between project groups│
│  - API rate limiting (100 req/min/user) │
│  - Input validation & parameterized     │
│    queries (injection prevention)       │
├────────────────────────────────────────┤
│  Data Layer                             │
│  - PostgreSQL: AES-256 storage encryption│
│  - MinIO: server-side encryption +      │
│    transport encryption                 │
│  - Sensitive data marking: documents    │
│    marked as internal auto-route to     │
│    local LLM                            │
│  - Database connection whitelist        │
├────────────────────────────────────────┤
│  Audit Layer                            │
│  - All operations logged to audit_logs  │
│  - Log retention 6 months (Level 2      │
│    Information Security requirement)    │
│  - Non-deletable/tamper-proof audit logs│
│  - Prometheus monitoring + anomaly      │
│    alerting                             │
└────────────────────────────────────────┘
```

### 8.2 Data Isolation Implementation

```python
# Data isolation during knowledge base search
async def search_kb(query: str, kb_sources: list[KBSource], user: User) -> list[Chunk]:
    accessible_projects = await get_user_project_ids(user)
    
    filters = []
    for source in kb_sources:
        if source.type == "project":
            if source.project_id not in accessible_projects:
                raise PermissionDenied(f"No access to project {source.project_id}")
            filters.append({"project_id": source.project_id})
        elif source.type == "institutional":
            if not user.group_id in source.allowed_groups:
                raise PermissionDenied(f"No access to this institutional knowledge base partition")
            filters.append({"kb_type": "institutional", "group_id": user.group_id})
    
    return await vector_search(query, filters=filters)
```

### 8.3 GDPR-Related Design

| GDPR Requirement | Implementation |
|-----------|------|
| Right of Access | API: GET /api/user/data |
| Right to Erasure | API: DELETE /api/user/data (cascading delete projects, documents, task results) |
| Data Portability | API: GET /api/user/data/export (JSON format export) |
| Consent Management | Collect processing consent at login, revocable at any time |
| Data Minimization | Only store documents and metadata necessary for analysis |
| DPIA | Complete Data Protection Impact Assessment before system launch |

---

## 9. Deployment Architecture

### 9.1 Deployment Topology

```
                    ┌─────────────────────┐
                    │  Institutional      │
                    │  Intranet           │
                    │                     │
  User Browser ──TLS──→│  ┌───────────────┐  │
                    │  │  Nginx (LB)   │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────┴───────┐  │
                    │  │  FastAPI × N  │  │
                    │  │  (Gunicorn +  │  │
                    │  │   Uvicorn)    │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────┴──────────────┐  │
                    │  │       Services        │  │
                    │  │  ┌────────┐           │  │
                    │  │  │Celery  │           │  │
                    │  │  │Worker  │           │  │
                    │  │  │× N     │           │  │
                    │  │  └────────┘           │  │
                    │  └──────────────────────┘  │
                    │          │                 │
                    │  ┌───────┴──────────────┐  │
                    │  │      Data Stores      │  │
                    │  │  PostgreSQL  Milvus   │  │
                    │  │  Redis       MinIO    │  │
                    │  └──────────────────────┘  │
                    │          │                 │
                    │  ┌───────┴──────────────┐  │
                    │  │    GPU Cluster        │  │
                    │  │  ┌──────────────────┐ │  │
                    │  │  │ vLLM / Ollama    │ │  │
                    │  │  │ (Qwen/DeepSeek/  │ │  │
                    │  │  │  Llama)          │ │  │
                    │  │  └──────────────────┘ │  │
                    │  └──────────────────────┘  │
                    │          │                 │
                    └──────────┼─────────────────┘
                               │
                        ┌──────┴──────┐
                        │ Claude API  │  (Outbound, non-sensitive data only)
                        │ (Internet)  │
                        └─────────────┘
```

### 9.2 Containerized Deployment

```
econai/
├── docker-compose.yml
├── services/
│   ├── api/          # FastAPI Application
│   ├── worker/       # Celery Worker
│   ├── nginx/        # Reverse Proxy
│   ├── postgres/     # Database
│   ├── redis/        # Queue + Cache
│   ├── milvus/       # Vector Database
│   ├── minio/        # Object Storage
│   └── prometheus/   # Monitoring
```

### 9.3 Resource Planning (Estimated)

| Component | Resources | Description |
|------|------|------|
| FastAPI | 4 vCPU, 8 GB RAM × 2 instances | Supports < 20 concurrent, including peak margin |
| Celery Worker | 4 vCPU, 8 GB RAM × 3 instances | Parallel processing of document parsing and Agent tasks |
| PostgreSQL | 8 vCPU, 32 GB RAM, 1 TB SSD | 50k+ document metadata + business data |
| Milvus/Qdrant | 8 vCPU, 32 GB RAM, 2 TB SSD | 100k-scale vector index |
| MinIO | 4 vCPU, 16 GB RAM, 8 TB HDD | Original document storage |
| Redis | 2 vCPU, 8 GB RAM | Queue + Cache |
| GPU (Local LLM) | 2× A100 80GB or equivalent | Local model inference |
| **Total (excl. GPU)** | ~34 vCPU, ~112 GB RAM, ~11 TB storage | |

---

## 10. Technology Stack Overview

| Layer | Technology | Version Reference | Selection Rationale |
|------|------|----------|----------|
| Frontend | React | 19.x | Confirmed |
| Frontend Language | TypeScript | 5.x | Confirmed |
| UI Component Library | Ant Design / Shadcn | latest | Enterprise CRUD + complex tables |
| Backend Framework | FastAPI | 0.115+ | Async high-performance, Python ecosystem |
| ASGI Server | Gunicorn + Uvicorn | - | Production-grade deployment |
| Business Database | PostgreSQL | 16+ | Full-text search, JSONB, mature and stable |
| Vector Database | Milvus / Qdrant | - | 100k-scale |
| Object Storage | MinIO | latest | S3-compatible, private deployment |
| Task Queue | Celery + Redis | 5.x / 7.x | Python standard async solution |
| Document Parsing | Unstructured + python-docx + PyMuPDF | - | Multi-format coverage |
| OCR | Tesseract | 5.x | Confirmed, chi_sim language pack |
| Embedding | text2vec / m3e | - | Confirmed, Chinese open-source |
| Reranker | BGE-Reranker | - | Chinese re-ranking |
| Local LLM Inference | vLLM / Ollama | - | OpenAI-compatible API |
| Cloud LLM | Anthropic Claude API | - | Confirmed |
| .docx Generation | python-docx | 1.x | GB/T 9704 templates |
| Monitoring | Prometheus + Grafana | - | Standard ops stack |
| Containerization | Docker + Docker Compose | - | Private deployment |

---

## 11. Key Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|------|------|----------|
| Agent loop instability (LLM output format uncontrollable) | Analysis task failure or unusable results | Medium | Fixed iteration cap + fault-tolerant tool_call parsing + fallback to fixed pipeline |
| Local LLM inference speed does not meet performance requirements | Analysis task timeout | Medium | GPU cluster already available, prioritize compute evaluation; downgrade to smaller models if necessary |
| Inaccurate inline citation format (LLM fabricates page numbers) | Traceability untrustworthy | High | CitationVerifier post-verification + mark unmatched citations as uncertain |
| GB/T 9704 typesetting complexity | Exported .docx format does not meet requirements | Medium | Collaborate with institution to obtain template files, reduce self-developed typesetting logic |
| Poor hybrid retrieval recall quality | Generated content lacks sufficient evidence support | Medium | Monitor retrieval recall rate, gradually tune RRF parameters and Reranker model |
| Claude API cross-border data transfer compliance | GDPR compliance risk | Low | Confirm SCC mechanism with legal; default to all local LLM during MVP phase |

---

*Document Version: v1.0 | Date: 2026-05-17 | Based on Requirements Document v2.0 (Final)*

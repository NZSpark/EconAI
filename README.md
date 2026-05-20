# EconAI — Institutional-Grade AI Economic Policy Analysis Toolkit

EconAI ingests policy literature, generates structured analysis reports (literature reviews, policy drafts, policy comparisons, tech interpretations) with sentence-level source citations, and exports to Markdown/.docx/.xlsx/.pptx.

## Project Status

**Phase: Implementation in progress** (9 of 10 modules complete)

| Module | Service | Port | Status |
|--------|---------|------|--------|
| M10 | Infrastructure | - | Completed (34/34) |
| M8 | User Service | 8007 | Completed (42/42) |
| M5 | LLM Router | 8004 | Completed (33/33) |
| M6 | Citation Service | 8005 | Completed (30/30) |
| M1 | API Gateway | 8000 | Completed (28/28) |
| M2 | Document Service | 8001 | Completed (43/43) |
| M7 | Output Service | 8006 | Completed (39/39) |
| M3 | KB Service | 8002 | Completed (35/35) |
| M4 | Orchestration Service | 8003 | Completed (54/54) |
| M9 | Frontend | - | Pending |

## Architecture

10 modules deployed as microservices behind an API gateway:

```
Client (React 19 + TypeScript 5 + Ant Design/Shadcn)
    -> API Gateway (FastAPI + Nginx) :8000
        -> document-service :8001   (upload, parse, chunk)
        -> kb-service :8002         (embedding, hybrid search)
        -> orchestration-service :8003 (Agent engine, task lifecycle)
        -> llm-router :8004         (sensitivity-based LLM routing)
        -> citation-service :8005   (inline citation parsing, verification, formatting)
        -> output-service :8006     (Markdown/.docx/.xlsx/.pptx generation)
        -> user-service :8007       (auth, RBAC, LDAP/SSO, audit)
```

## Quick Start

```bash
# Activate the project virtual environment
source .venv/bin/activate

# Start infrastructure services
docker compose up -d

# Run per-service quality gate
cd <service-dir> && pytest --tb=short && mypy . --strict && ruff check .
```

## Technology Stack

- **Backend**: FastAPI + Python 3.12+, Celery + Redis, SQLAlchemy 2.x async
- **Data Stores**: PostgreSQL 16, Milvus/Qdrant, MinIO
- **Frontend**: React 19 + TypeScript 5 + Ant Design/Shadcn
- **Infrastructure**: Docker Compose, Nginx, Prometheus + Grafana
- **Package Management**: uv

## Key Design Decisions

- **Inline citations**: LLM outputs use `[ref:doc_id:page_range]` format with confidence levels (direct/fuzzy/uncertain)
- **Citation verification**: Page range matching + semantic similarity (threshold 0.85) -> confidence classification
- **Hybrid search**: Vector semantic (top-50) + BM25 keyword (top-50) -> RRF fusion -> BGE-Reranker
- **LLM routing**: Sensitivity-based (internal docs -> local vLLM, public -> Claude API)
- **Agent loop**: ReAct variant (Plan -> Retrieve -> Generate -> Verify -> Decide), max 5 iterations

## Completed Modules

### M10 — Infrastructure & Deployment
- Docker Compose (all services), PostgreSQL schema, Nginx, Prometheus + Grafana, Celery config
- Alembic migrations, .env.template, deploy.sh

### M8 — User Service (8007)
- JWT auth (bcrypt, access/refresh tokens), RBAC (4 roles x 6 operations)
- LDAP/SSO integration, user/group/project CRUD, audit log consumer, GDPR APIs

### M5 — LLM Router (8004)
- Model registry, sensitivity-based routing (local vs Claude API)
- ClaudeAdapter + LocalAdapter (OpenAI-compatible), circuit breaker, retry with backoff
- Token usage tracking

### M6 — Citation Service (8005)
- Inline `[ref:...]` parser (single/multi/uncertain references, Chinese/English sentence splitting)
- Citation verifier (page range matching + semantic similarity -> direct/fuzzy/uncertain confidence)
- Formatters: Markdown (GFM footnotes), .docx (footnotes/endnotes), .xlsx (引用清单 sheet), .pptx
- REST API: POST /internal/citations/verify, GET citation list/detail

### M1 — API Gateway (8000)
- JWT authentication middleware (token verification, blacklist check, public path bypass)
- RBAC permission middleware (4 roles x 6 operations, group-scoped access control)
- Redis Token Bucket rate limiter (per-user + per-IP, endpoint-group classification)
- Audit logging via Redis pub/sub (`audit:log` channel), request body capture for sensitive ops
- Config-driven route registry with httpx-based reverse proxy to 7 backend services
- Unified error response format, CORS, X-Request-ID propagation, request size limit (100MB)

### M2 — Document Service (8001)
- Multi-format parsing: PDF (PyMuPDF), Word (python-docx), Markdown/txt, Excel/CSV (openpyxl/pandas), PowerPoint (python-pptx), Email (email stdlib), HTML/MHTML (BeautifulSoup), Image/Image-PDF OCR (Tesseract chi_sim+eng)
- Magic bytes + extension fallback format identification with PDF text layer detection
- Multi-granularity chunking: paragraph-level (~300 tokens) + section-level (~2000 tokens) with configurable overlap
- Metadata extraction (title, author, date, source, page count) from PDF/Word built-in properties and content inference
- Document state machine: pending -> parsing -> ready/error with reindex recovery
- MinIO file storage with auto bucket creation for upload/download/delete
- Celery async processing pipeline (parse -> chunk -> index event)
- Redis pub/sub index events on `kb:index:request` channel for downstream KB Service consumption
- REST API: upload, list (paginated + status/format filters), detail, delete (cascade), reindex

### M7 — Output Service (8006)
- Multi-format generation: Markdown (Jinja2 templates, YAML front-matter, [ref:] -> [^n] footnotes)
- DOCX GB/T 9704-2012 compliant (版头/主体/版记, heading mapping, reference list)
- XLSX generation: comparison matrix sheet + citation list sheet + data summary sheet
- PPTX generation: cover, TOC, findings, recommendations, references slides
- YAML template loader with built-in fallback defaults
- Format router for parallel multi-format generation
- REST API: POST /internal/output/generate, GET preview, GET export with Content-Disposition
- MinIO output storage client (upload/download/presigned URLs)

### M3 — KB Service (8002)
- Embedding generation with Redis caching (text2vec/m3e, configurable dimensions)
- Vector store abstraction (Milvus/Qdrant unified interface + in-memory mock for testing)
- BM25 keyword search via PostgreSQL FTS with GIN index on document_chunks
- Hybrid search pipeline: parallel vector(top-50) + BM25(top-50) → RRF fusion(k=60) → reranker → top-10
- Reranker with term-overlap heuristics (configurable BGE-Reranker integration)
- Redis pub/sub consumer on `kb:index:request` channel for auto-indexing
- Index pipeline: chunk ingestion → embedding generation → vector store insert → BM25 update
- Knowledge base isolation: per-project and institutional (cross-project) search with archival status check
- Lifecycle management: archive/restore/delete (cascade) for documents and projects, batch reindex
- REST API: POST /api/projects/{project_id}/search, POST /api/institutional/search, POST /internal/search
- Internal endpoints: index chunks, reindex, delete document/project index, archive/restore lifecycle

### M4 — Orchestration Service (8003)
- Agent engine (ReAct variant): Plan -> Execute -> Observe -> Update Progress, max 5 iterations
- Task state machine: pending -> running/cancelled, running -> completed/failed/cancelled, failed -> running
- 6 Agent tools: search_kb, generate_section, verify_citations, extract_key_claims, compare_policies, format_output
- Tool execution framework with 60s timeout, 1 retry, exception isolation, and call history recording
- Sensitivity analysis (4 rules): internal docs -> high, policy_draft -> high, user preference override, default low
- 4 task-type workflows with Jinja2 prompt templates: literature_review, policy_draft, policy_comparison, tech_interpretation
- Progress tracking with per-task-type presets and dynamic step adjustment
- Max iteration fallback: forces format_output with available content when iteration limit is reached
- REST API: create, list (paginated + filter by status/type), detail, status poll, cancel, retry
- Output endpoints: preview, citation list/detail, export (format=docx|md|xlsx|pptx)

## Reference Documents

| Document | Content |
|----------|---------|
| `doc/proposal.md` | Requirements, user stories, MVP scope, compliance |
| `doc/high-level-design.md` | Architecture, data flow, API design, Agent engine |
| `doc/detailed-design.md` | Per-module API specs, algorithms, config |
| `doc/tasks/*.md` | Subtask checklists per module (376 total) |
| `doc/tasks/progress.md` | Dependency graph, progress tracking |
| `doc/prompt.md` | Vibe Coding orchestration protocol |

## Development

```bash
# Install per-service dependencies
cd <service-dir> && uv sync

# Quality gate (must pass before commit)
cd <service-dir> && pytest --tb=short && mypy . --strict && ruff check .
```

## License

Proprietary. All rights reserved.
# EconAI — Institutional-Grade AI Economic Policy Analysis Toolkit

EconAI ingests policy literature, generates structured analysis reports (literature reviews, policy drafts, policy comparisons, tech interpretations) with sentence-level source citations, and exports to Markdown/.docx/.xlsx/.pptx.

## Project Status

**Phase: Implementation in progress** (5 of 10 modules complete)

| Module | Service | Port | Status |
|--------|---------|------|--------|
| M10 | Infrastructure | - | Completed (34/34) |
| M8 | User Service | 8007 | Completed (42/42) |
| M5 | LLM Router | 8004 | Completed (33/33) |
| M6 | Citation Service | 8005 | Completed (30/30) |
| M1 | API Gateway | 8000 | Completed (28/28) |
| M2 | Document Service | 8001 | Pending |
| M7 | Output Service | 8006 | Pending |
| M3 | KB Service | 8002 | Pending |
| M4 | Orchestration Service | 8003 | Pending |
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
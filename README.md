# EconAI — Institutional-Grade AI Economic Policy Analysis Toolkit

EconAI ingests policy literature, generates structured analysis reports (literature reviews, policy drafts, policy comparisons, tech interpretations) with sentence-level source citations, and exports to Markdown/.docx/.xlsx/.pptx.

## Architecture

10 modules deployed as microservices behind an API gateway:

| Module | Service | Port | Status |
|--------|---------|------|--------|
| M1 | API Gateway | 8000 | Pending |
| M2 | Document Service | 8001 | Pending |
| M3 | KB Service | 8002 | Pending |
| M4 | Orchestration Service | 8003 | Pending |
| M5 | LLM Router | 8004 | Pending |
| M6 | Citation Service | 8005 | Pending |
| M7 | Output Service | 8006 | Pending |
| M8 | User Service | 8007 | Implemented |
| M9 | Frontend | - | Pending |
| M10 | Infrastructure | - | Implemented |

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

## Key Design Decisions

- **Inline citations**: LLM outputs use `[ref:doc_id:page_range]` format with confidence levels
- **Hybrid search**: Vector semantic (top-50) + BM25 keyword (top-50) -> RRF fusion -> BGE-Reranker
- **LLM routing**: Sensitivity-based (internal docs -> local vLLM, public -> Claude API)
- **Agent loop**: ReAct variant (Plan -> Retrieve -> Generate -> Verify -> Decide), max 5 iterations

## Reference Documents

| Document | Content |
|----------|---------|
| `doc/proposal.md` | Requirements, user stories, MVP scope, compliance |
| `doc/high-level-design.md` | Architecture, data flow, API design, Agent engine |
| `doc/detailed-design.md` | Per-module API specs, algorithms, config |
| `doc/tasks/*.md` | Subtask checklists per module (376 total) |
| `doc/tasks/progress.md` | Dependency graph, progress tracking |

## Development

```bash
# Install per-service dependencies
cd <service-dir> && uv sync

# Quality gate (run before commit)
cd <service-dir> && pytest --tb=short && mypy . --strict && ruff check .
```

## License

Proprietary. All rights reserved.
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

EconAI is an institutional-grade AI economic policy analysis toolkit. It ingests policy literature, generates structured analysis reports (literature reviews, policy drafts, policy comparisons, tech interpretations) with sentence-level source citations, and exports to Markdown/.docx/.xlsx/.pptx.

The project is in **pre-implementation phase** — design docs and task breakdowns are complete, implementation starts from scratch.

## Architecture

10 modules deployed as microservices behind an API gateway:

| Module | Dir | Port | Purpose |
|--------|-----|------|---------|
| M1 API Gateway | `api-gateway/` | 8000 | JWT auth, RBAC, rate limiting, audit, reverse proxy |
| M2 Document | `services/document-service/` | 8001 | Upload, parse (8 formats), OCR, multi-granularity chunking |
| M3 KB | `services/kb-service/` | 8002 | Embedding, vector index, hybrid search (vector+BM25+Reranker) |
| M4 Orchestration | `services/orchestration-service/` | 8003 | Agent engine (ReAct loop), task lifecycle, tool execution |
| M5 LLM Router | `services/llm-router/` | 8004 | Sensitivity-based routing (local vs Claude API), adapters |
| M6 Citation | `services/citation-service/` | 8005 | Inline `[ref:doc:page]` parsing, verification, formatting |
| M7 Output | `services/output-service/` | 8006 | Generate Markdown/.docx(GB/T 9704)/.xlsx/.pptx |
| M8 User | `services/user-service/` | 8007 | Auth, RBAC, LDAP/SSO, audit logs, GDPR |
| M9 Frontend | `frontend/` | - | React 19 + TypeScript 5 + Ant Design/Shadcn |
| M10 Infra | project root | - | Docker Compose, DB schema, Nginx, Prometheus, Celery config |

**Dependency order**: M5/M6/M8/M10 (parallel) → M1/M2/M7 → M3 → M4 → M9.

All services are FastAPI + Python 3.12+. Async tasks use Celery + Redis. Data stores: PostgreSQL 16 (business data + FTS), Milvus/Qdrant (vectors), MinIO (files).

## Development commands

```bash
# Activate the project virtual environment
source .venv/bin/activate

# Run tests (per-service, from service directory)
cd <service-dir> && pytest --tb=short

# Type check (per-service)
cd <service-dir> && mypy . --strict

# Lint (per-service)
cd <service-dir> && ruff check .

# Full quality gate (all three must pass before git commit)
cd <service-dir> && pytest --tb=short && mypy . --strict && ruff check .

# Start infrastructure services (PostgreSQL, Redis, Milvus, MinIO)
docker compose up -d

# Check service health
docker compose ps

# Install a dependency for a specific service
cd <service-dir> && uv add <package>
```

Each service will have its own `pyproject.toml` managed by `uv`. The root `pyproject.toml` is only for shared dev tools (pytest, mypy, ruff).

## Implementation workflow

This project uses a **Vibe Coding** approach defined in `doc/prompt.md`. A main orchestrator agent spawns sub-agents per module in dependency-respecting waves:

1. Read `doc/prompt.md` for the full orchestration protocol
2. Each sub-agent reads `doc/high-level-design.md` + `doc/detailed-design.md` + `doc/tasks/<module>.md`
3. Sub-agent implements all subtasks, writes pytest tests (pure mock, no external deps), passes mypy + ruff
4. Sub-agent auto-commits: `feat(<code>): implement <module-name>`
5. 376 subtasks total across 10 modules

## Key design decisions

- **Inline citations**: LLM outputs must use `[ref:doc_id:page_range]` format. Citation service parses, verifies against retrieved chunks, marks confidence (direct/fuzzy/uncertain).
- **Chunking**: Two granularities — paragraph-level (~300 tokens) for precise retrieval + section-level (~2000 tokens) for context window.
- **Hybrid search**: Vector semantic (top-50) + BM25 keyword (top-50) → RRF fusion (k=60) → top-30 → BGE-Reranker → top-10.
- **LLM routing**: Sensitivity analysis (internal docs → local vLLM/Ollama, public → Claude API). All local models use OpenAI-compatible API for unified adapter interface.
- **Agent loop**: ReAct variant (Plan→Retrieve→Generate→Verify→Decide), max 5 iterations. On max iteration reached, forces format_output with what's available.
- **GB/T 9704**: Chinese government document standard for .docx output — specific fonts (小标宋/黑体/楷体/仿宋), margins, heading numbering conventions.
- **Tests are pure mock**: All external deps (DB, Redis, Milvus, MinIO, LLM APIs) are mocked. Tests must run offline with zero infrastructure.

## Reference documents

| Document | Content |
|----------|---------|
| `doc/proposal.md` | Requirements, user stories, MVP scope, compliance |
| `doc/high-level-design.md` | Architecture, data flow, API design, Agent engine, security |
| `doc/detailed-design.md` | Per-module API specs, internal interfaces, algorithms, config |
| `doc/tasks/*.md` | Subtask checklists per module (376 total) |
| `doc/tasks/progress.md` | Dependency graph, suggested order, progress tracking table |
| `doc/devtools.md` | Dev environment setup, tool versions |
| `doc/prompt.md` | Vibe Coding orchestration prompt for the main agent |
| `templates/prompts/*.j2` | Jinja2 System Prompt templates for 4 task types |
| `templates/output/*.yaml` | Style configs for .docx/.pptx/.xlsx generation |
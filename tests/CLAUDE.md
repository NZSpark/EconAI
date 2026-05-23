# CLAUDE.md — tests

## Role

Integration tests covering all 8 microservices + end-to-end flows. **Pure mock** — all external dependencies (DB, Redis, Milvus, MinIO, LLM APIs) are mocked. Zero infrastructure required.

## Files (17 test files, 638 tests)

```
tests/
├── conftest.py              # Shared fixtures (4.82KB): mock clients, test data, auth helpers
├── test_m1_gateway.py       # API Gateway: auth middleware, RBAC, rate limiting, audit, proxy
├── test_m2_document.py      # Document Service: upload, parse (8 formats), chunking, MinIO
├── test_m3_kb.py            # KB Service: embedding, vector store, BM25, hybrid search, lifecycle
├── test_m4_orchestration.py # Orchestration: agent loop, 6 tools, task lifecycle, 4 task types
├── test_m5_llm_router.py    # LLM Router: sensitivity routing, adapters, circuit breaker
├── test_m5_ollama.py        # Ollama local model integration
├── test_m6_citation.py      # Citation: inline parsing, verification, confidence classification
├── test_m7_output.py        # Output: Markdown, DOCX, XLSX, PPTX generation
├── test_m8_audit.py         # Audit: event publishing, persistence, query, immutability
├── test_m8_auth.py          # Auth: login, logout, JWT refresh, token blacklist
├── test_m8_gdpr.py          # GDPR: data access, correction, deletion, export
├── test_m8_groups.py        # Groups: CRUD, membership management
├── test_m8_projects.py      # Projects: CRUD, archive/restore
├── test_m8_user_admin.py    # User admin: CRUD, role management
├── test_integration_flows.py # End-to-end: upload→parse→search→analyze→cite→export
└── test_m7_docx_output.py   # (implicit) DOCX formatting compliance tests
```

## Test conventions

- All external deps are **mocked** (unittest.mock / pytest-mock)
- Tests run offline — no PostgreSQL, Redis, Milvus, or external APIs needed
- Each service's tests live in a `test_mX_*.py` file
- `conftest.py` provides shared fixtures across all test modules

## Run

```bash
# All tests
pytest --tb=short

# Single module
pytest tests/test_m1_gateway.py --tb=short

# With coverage
pytest --cov=. --cov-report=term-missing
```

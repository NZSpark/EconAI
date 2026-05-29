# EconAI Development Environment Software Checklist

> Version: v2.0 | Date: 2026-05-21

Based on `pyproject.toml`, `package.json` of all 10 modules and the actual runtime environment.

---

## 1. Container Runtime

| Software | Version | Installation | Purpose |
|----------|---------|-------------|---------|
| Colima | 0.10.x | `brew install colima` | Lightweight container runtime for macOS, replaces Docker Desktop. Based on Lima, provides containerd runtime |
| Docker CLI | 29.5.x | `brew install docker` | Image building (`docker build`), container management |
| Docker Compose | 5.1.x | `brew install docker-compose` | Multi-container orchestration, one-click startup of PostgreSQL / Redis / Milvus / MinIO / Nginx / Prometheus / Grafana |

**Infrastructure services in containers:**

| Service | Image | Purpose |
|---------|-------|---------|
| PostgreSQL 16 | `postgres:16-alpine` | Business database + FTS full-text search (BM25) + JSONB |
| Redis 7 | `redis:7-alpine` | Celery broker/backend + Token blacklist + Rate limiter + pub/sub event bus |
| Milvus | `milvusdb/milvus:latest` | Vector database, stores embeddings (1024d), semantic similarity search |
| MinIO | `minio/minio:latest` | S3-compatible object storage for documents and output files |
| Nginx | `nginx:alpine` | Reverse proxy + TLS termination + static resource caching + 100MB upload limit |
| Prometheus | `prom/prometheus:latest` | Metrics collection |
| Grafana | `grafana/grafana:latest` | Monitoring dashboards |

---

## 2. Python Ecosystem

| Software | Version | Installation | Purpose |
|----------|---------|-------------|---------|
| Python | 3.14.5 (>=3.12) | `brew install python@3.14` | Runtime |
| uv | 0.11.9 | `brew install uv` | Ultra-fast package manager + virtual environments (Rust implementation), replaces pip + venv |

### 2.1 Microservice Framework

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| fastapi | >=0.115 | All 7 services + gateway | Async web framework |
| uvicorn | >=0.30 | All | ASGI dev server |
| gunicorn | latest | M10 orchestration | Production-grade ASGI process manager |
| pydantic | >=2.0 | All | Data validation / serialization |
| pydantic-settings | >=2.0 | All | Environment variable / .env configuration management |
| python-multipart | >=0.0.12 | M1, M2, M8 | multipart/form-data file upload parsing |
| pyyaml | >=6.0 | M1, M5, M7 | YAML config parsing |

### 2.2 Database & Storage

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| sqlalchemy[asyncio] | >=2.0 | M2, M6, M7, M8 | Async ORM (PostgreSQL) |
| asyncpg | >=0.29 | M2, M3, M6, M7, M8 | PostgreSQL async driver |
| alembic | >=1.13 | M8 | Database migration version management |
| redis | >=5.0 | M1, M2, M3, M4, M5, M6 | Redis client (rate limiting/cache/queue/pub-sub) |
| minio | >=7.0 | M2, M7 | S3-compatible object storage client |

### 2.3 Async Tasks

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| celery[redis] | >=5.4 | M2, M4 | Distributed task queue (Redis backend), document parsing + Agent analysis |

### 2.4 Authentication & Security

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| python-jose[cryptography] | >=3.3 | M1 | JWT issuance / verification |
| bcrypt | >=4.2 | M8 | Password hashing |
| pyjwt | >=2.9 | M8 | JWT token encoding/decoding |
| python-ldap | >=3.4 | M8 | LDAP/AD authentication integration |

### 2.5 LLM & AI

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| anthropic | >=0.39 | M5 | Claude Messages API SDK (including tool_use bidirectional conversion) |
| httpx | >=0.27 | M1, M2, M3, M4, M5 | Async HTTP client (reverse proxy + inter-service calls) |
| numpy | >=1.26 | M6 | Vector operations (cosine_similarity etc.) |
| tiktoken | >=0.7 | M2 | Token counting (precise chunk size control) |

### 2.6 Document Parsing (document-service specific)

| Package | Version | Purpose |
|---------|---------|---------|
| pymupdf | >=1.24 | PDF parsing (based on MuPDF) |
| pdfplumber | latest | Fine-grained PDF table/text extraction |
| python-docx | >=1.1 | Word .docx read/write |
| openpyxl | >=3.1 | Excel .xlsx read/write |
| pandas | >=2.2 | CSV / tabular data processing |
| python-pptx | >=0.6 | PowerPoint .pptx parsing |
| beautifulsoup4 | >=4.12 | HTML / MHTML parsing |
| lxml | >=5.0 | High-performance XML/HTML parsing |
| pillow | >=10.0 | Image processing (OCR preprocessing) |

### 2.7 Output Generation (output-service specific)

| Package | Version | Purpose |
|---------|---------|---------|
| python-docx | >=1.0 | .docx generation (GB/T 9704 official document standard) |
| openpyxl | >=3.1 | .xlsx generation (comparison matrix + citation list) |
| python-pptx | >=1.0 | .pptx generation (presentations) |
| jinja2 | >=3.1 | Markdown/text template rendering |

### 2.8 Observability

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| structlog | >=24.0 | M1 | Structured JSON logging |
| starlette-prometheus | >=0.10 | M1 | `/metrics` endpoint exposure |
| prometheus-client | >=0.18 | M1 | Prometheus metrics collection |

### 2.9 Shared Package

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| econai-shared | 0.1.0 (local) | M2, M3, M4 | Pydantic models + config loader + structured logging |

### 2.10 Dev Tools

| Software | Version | Purpose |
|----------|---------|---------|
| pytest | 9.0.3 | Unit testing framework (all modules) |
| pytest-asyncio | 1.3.0 | Async test support |
| pytest-mock | 3.15.1 | Mock capabilities (pure mock, zero external dependencies) |
| mypy | 2.1.0 | Static type checking (`strict = true` except llm-router/user-service) |
| ruff | 0.15.13 | Rust-based high-speed linter + formatter, replaces flake8/isort/black |

**mypy configuration differences:**

| Module | strict | ignore_missing_imports | Notes |
|--------|--------|------------------------|-------|
| shared | yes | yes | - |
| api-gateway | yes | no (except jose*) | Strictest, only jose exempt |
| document-service | yes | yes | disallow_untyped_decorators = false |
| kb-service | yes | yes | Same as document-service |
| llm-router | no (per-rule) | yes | Semi-strict mode |
| orchestration-service | yes | yes | Same as document-service |
| output-service | yes | yes | Disabled no-untyped-call, valid-type |
| citation-service | yes | yes | - |
| user-service | no (per-rule) | yes | Exclude alembic/ + tests/ |

**ruff lint rule differences:**

| Module | Rule Set | Notes |
|--------|----------|-------|
| Most modules | E, F, I, N, W, UP, B, SIM | Standard rule set |
| api-gateway | E, W, F, I, B, C4, UP | Added C4 (flake8-comprehensions) |
| user-service | E, F, I, N, W, UP, B, C4, SIM | Added C4 |
| shared | E, F, I, N, W, UP, B, C4, SIM | Added C4 |

---

## 3. Node.js Frontend

| Software | Version | Installation | Purpose |
|----------|---------|-------------|---------|
| Node.js | 26.x | `brew install node` | JavaScript runtime |
| npm | 11.12.x | Bundled with Node.js | Package manager |

### 3.1 Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| react | 19.2.x | UI framework |
| react-dom | 19.2.x | React DOM rendering |
| react-router-dom | 7.15.x | Frontend routing (login/projects/knowledge base/tasks/admin) |
| antd | 6.4.x | Ant Design UI component library |
| @ant-design/icons | 6.2.x | Ant Design icon library |
| axios | 1.16.x | HTTP client (JWT auto-injection + 401 refresh retry) |
| react-markdown | 10.1.x | Markdown rendering (clickable citation badges) |

### 3.2 Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| typescript | 6.0.x | Type safety (strict: true) |
| vite | 8.0.x | Build tool (HMR hot reload) |
| @vitejs/plugin-react | 6.0.x | Vite React JSX support |
| vitest | 4.1.x | Unit testing framework |
| jsdom | 29.1.x | DOM simulation (test environment) |
| @testing-library/react | 16.3.x | React component testing |
| @testing-library/jest-dom | 6.9.x | DOM assertion extensions |
| @testing-library/user-event | 14.6.x | User interaction simulation |
| eslint | 10.3.x | JS/TS linter |
| typescript-eslint | 8.59.x | ESLint TypeScript plugin |
| eslint-plugin-react-hooks | 7.1.x | Hooks rule checking |
| eslint-plugin-react-refresh | 0.5.x | HMR compatibility check |
| globals | 17.6.x | ESLint global variable config |

---

## 4. Other Tools

| Software | Version | Installation | Purpose |
|----------|---------|-------------|---------|
| git | 2.23.x | System default | Version control |
| Tesseract | 5.5.x | `brew install tesseract` | OCR engine (chi_sim Chinese language pack) |

---

## 5. One-Click Install

```bash
# === Container Runtime ===
brew install colima docker docker-compose
colima start --cpu 4 --memory 8 --disk 60

# === Python Toolchain ===
brew install python@3.14 uv

# === OCR Engine ===
brew install tesseract
tesseract --list-langs | grep chi_sim  # Verify Chinese language pack

# === Node.js ===
brew install node  # Node 26.x

# === Start Infrastructure ===
cd /path/to/EconAI
docker compose up -d
docker compose ps

# === Install Module Dependencies ===
uv sync                    # Root project (dev tools)
cd shared && uv sync
cd api-gateway && uv sync
cd services/user-service && uv sync
cd services/llm-router && uv sync
cd services/citation-service && uv sync
cd services/document-service && uv sync
cd services/output-service && uv sync
cd services/kb-service && uv sync
cd services/orchestration-service && uv sync
cd frontend && npm install
```

---

## 6. Quality Gates (per module)

```bash
cd <module-directory>
pytest --tb=short           # All tests pass
mypy . --strict             # Type checking (for modules with strict config)
ruff check .                # Code style
```

---

## 7. Current Environment Verification

As of 2026-05-21 actual environment:

| Category | Software | Actual Version |
|----------|----------|----------------|
| Container | Colima + Docker + Compose | 0.10.1 / 29.5.0 / 5.1.3 |
| Python | Python + uv | 3.14.5 / 0.11.9 |
| Testing | pytest + async + mock | 9.0.3 / 1.3.0 / 3.15.1 |
| Types | mypy | 2.1.0 |
| Code Style | ruff | 0.15.13 |
| OCR | tesseract + chi_sim | 5.5.2 |
| VCS | git | 2.23.0 |
| Frontend | Node + npm | 26.0.0 / 11.12.1 |
| Frontend Framework | React + TypeScript + Vite | 19.2.6 / 6.0.2 / 8.0.12 |
| UI Library | Ant Design | 6.4.3 |
| Frontend Testing | vitest + testing-library | 4.1.6 / 16.3.2 |

Full test suite: **640+ tests all passing** (Python 622+ + TypeScript 16).

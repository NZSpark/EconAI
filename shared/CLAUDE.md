# CLAUDE.md — shared (policyai-shared)

## Role

Common Python package shared by all microservices. Provides base config, shared enums/models, structured logging, and MinIO client. All services reference it via local path (`path = "../../shared"` in pyproject.toml).

## Directory structure

```
shared/
├── pyproject.toml
├── __init__.py               # Exports 18 public symbols
├── config.py                 # AppSettings base class with PostgreSQL/Redis/JWT defaults
├── models.py                 # Shared enums and Pydantic models
├── log_setup.py              # structlog configuration
├── minio_client.py           # MinIO client wrapper (upload/download/delete/presigned URL)
└── py.typed                  # PEP 561 marker
```

## AppSettings (`shared/config.py`)

Base class all services extend:
```python
class AppSettings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "policyai"
    postgres_password: str = ""
    # Redis
    redis_host: str = "localhost"
    # JWT
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    # Computed
    @property
    def database_url(self) -> str: ...
    @property
    def redis_url(self) -> str: ...
```

## Shared enums (`shared/models.py`)

| Enum | Values |
|------|--------|
| `UserRole` | analyst, senior_researcher, project_admin, system_admin |
| `TaskType` | literature_review, policy_draft, policy_comparison, tech_interpretation |
| `TaskStatus` | pending, running, completed, failed, cancelled |
| `ParseStatus` | pending, parsing, ready, error |
| `CitationConfidence` | direct, fuzzy, uncertain |
| `DocumentFormat` | 11 formats (pdf, docx, md, xlsx, csv, pptx, eml, html, png, jpg, tiff) |

## Key Pydantic models

- `HealthResponse` — standard health check response
- `ErrorDetail` / `ErrorResponse` — unified error format
- `IndexEvent` — document-service → kb-service indexing trigger
- `PaginatedResponse[T]` — generic pagination wrapper

## Key dependency

Only `minio`, `pydantic`, `pydantic-settings` — intentionally minimal to avoid bloating all services.

## Usage in services

```python
from shared.config import AppSettings
from shared.models import TaskType, TaskStatus, ...

class MyServiceSettings(AppSettings):
    # Add service-specific fields
    ...
```

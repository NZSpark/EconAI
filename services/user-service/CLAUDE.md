# CLAUDE.md — user-service (M8)

## Role

Authentication (JWT + bcrypt), RBAC (4 roles), user/group/project CRUD, LDAP/SSO integration, GDPR compliance (access/correction/deletion/export), audit log persistence (Redis → PostgreSQL consumer).

## Directory structure

```
services/user-service/
├── Dockerfile
├── pyproject.toml
├── app/
│   ├── main.py              # FastAPI app, 7 routers, starts audit consumer
│   ├── config.py             # Extends shared AppSettings: JWT params, LDAP, bcrypt cost
│   ├── database.py           # SQLAlchemy async session factory
│   ├── deps.py               # DI: get_db, get_current_user
│   ├── audit_consumer.py     # Redis Pub/Sub → PostgreSQL audit log writer
│   ├── routers/
│   │   ├── auth.py           # POST /login, /refresh, /logout
│   │   ├── users.py          # CRUD (admin only)
│   │   ├── groups.py         # Project group management
│   │   ├── projects.py       # Project CRUD
│   │   ├── gdpr.py           # Data subject rights (access, correct, delete, export)
│   │   ├── audit.py          # Audit log query
│   │   └── internal.py       # Internal endpoints for other services
│   ├── services/
│   │   ├── auth_service.py   # JWT generation, bcrypt password hashing
│   │   └── ldap_service.py   # LDAP/SSO integration
│   ├── models/               # SQLAlchemy: User, ProjectGroup, Project, AuditLog, Consent
│   └── schemas/              # Pydantic request/response models
```

## RBAC matrix

| Role | Operations | Scope |
|------|-----------|-------|
| analyst | view_project, upload_document, create_task | self_group |
| senior_researcher | + create_project | self_group |
| project_admin | + manage_users | self_group |
| system_admin | + view_audit | all |

## Key dependencies

- SQLAlchemy[asyncio] + asyncpg (DB)
- bcrypt + pyjwt + python-ldap (auth)
- `policyai-shared` (local path `../../shared`)

## Audit flow

`api-gateway middleware` → Redis `audit:log` channel → `audit_consumer.py` (background task) → PostgreSQL `audit_logs` table (immutable: REVOKE UPDATE/DELETE via trigger)

## Run / test

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload
pytest --tb=short && mypy . --strict && ruff check .
```

## DB tables managed

- `users`, `project_groups`, `project_group_members`, `projects`, `audit_logs`, `consents`

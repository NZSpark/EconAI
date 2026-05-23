# CLAUDE.md — db

## Role

Database schema definitions, seed data, and Alembic migration configuration for PostgreSQL 16.

## Files

```
db/
├── init/
│   ├── 01-schema.sql      # Full DB schema (13.6KB): 11 tables + extensions + indexes + triggers + FTS
│   └── 02-seed.sql        # Seed data: admin user (bcrypt), Default Group
├── alembic/
│   ├── env.py             # Alembic env config (targets PostgreSQL)
│   └── versions/          # Migration scripts
└── alembic.ini            # Alembic config (DB connection string)
```

## Tables (11 total)

| Table | Purpose | Key features |
|-------|---------|-------------|
| `users` | User accounts | role enum, auth_type, bcrypt password, consent tracking |
| `project_groups` | Organization groups | group-level RBAC scoping |
| `project_group_members` | Group membership | M2M junction table |
| `projects` | Research projects | active/archived state |
| `documents` | Document metadata | parse status, format, MinIO path |
| `document_chunks` | Chunked text | GIN FTS index + pg_trgm trigram index |
| `analysis_tasks` | Task records | JSONB params/progress fields |
| `task_outputs` | Generated outputs | Linked to tasks |
| `citations` | Verified citations | Confidence level, source chunk reference |
| `audit_logs` | Immutable audit trail | REVOKE UPDATE/DELETE via DB trigger |
| `llm_usage_logs` | LLM token tracking | Per user/task/model aggregation |

## Notable DB features

- **Full-Text Search**: GIN index on `document_chunks.content` for BM25
- **Trigram index**: pg_trgm index on `document_chunks.content` for fuzzy matching
- **Audit immutability**: Trigger revokes UPDATE/DELETE on `audit_logs` table
- **UUID PKs**: All primary keys are UUID (uuid-ossp extension)

## Seed data

Admin user: username=`admin`, password=`Admin@123456` (bcrypt hashed, rounds=12).
Default group: `Default` with system_admin membership.

## Migration

```bash
cd db
# Create new migration
alembic revision --autogenerate -m "description"
# Apply
alembic upgrade head
# Rollback
alembic downgrade -1
```

## Docker Compose

Schema and seed are applied on first container start via `docker-entrypoint-initdb.d/` (mounted as `./db/init:/docker-entrypoint-initdb.d`). No manual migration needed for initial setup.

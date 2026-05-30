"""Initial baseline schema — full PolicyAI database.

Revision ID: 001_base
Revises: None
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "001_base"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── users ──
    op.execute(
        """CREATE TABLE users (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            username    VARCHAR(128) NOT NULL UNIQUE,
            email       VARCHAR(256) NOT NULL UNIQUE,
            display_name VARCHAR(256),
            hashed_password VARCHAR(256) NOT NULL,
            role        VARCHAR(32) NOT NULL DEFAULT 'analyst'
                        CHECK (role IN ('analyst','senior_researcher','project_admin','system_admin')),
            auth_provider VARCHAR(16) NOT NULL DEFAULT 'local'
                        CHECK (auth_provider IN ('local','ldap')),
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            consent_given_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_users_role ON users(role)")
    op.execute("CREATE INDEX idx_users_is_active ON users(is_active)")
    op.execute("CREATE INDEX idx_users_auth_provider ON users(auth_provider)")

    # ── project_groups ──
    op.execute(
        """CREATE TABLE project_groups (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name        VARCHAR(256) NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )

    # ── project_group_members ──
    op.execute(
        """CREATE TABLE project_group_members (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            group_id    UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role        VARCHAR(32) NOT NULL DEFAULT 'analyst',
            joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(group_id, user_id)
        )"""
    )
    op.execute("CREATE INDEX idx_pgm_group_id ON project_group_members(group_id)")
    op.execute("CREATE INDEX idx_pgm_user_id ON project_group_members(user_id)")

    # ── projects ──
    op.execute(
        """CREATE TABLE projects (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name        VARCHAR(512) NOT NULL,
            description TEXT,
            group_id    UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
            owner_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status      VARCHAR(16) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','archived')),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_projects_group_id ON projects(group_id)")
    op.execute("CREATE INDEX idx_projects_owner_id ON projects(owner_id)")
    op.execute("CREATE INDEX idx_projects_status ON projects(status)")

    # ── documents ──
    op.execute(
        """CREATE TABLE documents (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            filename        VARCHAR(512) NOT NULL,
            original_name   VARCHAR(512) NOT NULL,
            format          VARCHAR(32) NOT NULL,
            size_bytes      BIGINT NOT NULL DEFAULT 0,
            storage_path    VARCHAR(1024),
            parse_status    VARCHAR(16) NOT NULL DEFAULT 'pending'
                            CHECK (parse_status IN ('pending','parsing','ready','error')),
            parse_error     TEXT,
            is_internal     BOOLEAN NOT NULL DEFAULT FALSE,
            title           VARCHAR(1024),
            author          VARCHAR(512),
            page_count      INTEGER,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_docs_project_id ON documents(project_id)")
    op.execute("CREATE INDEX idx_docs_parse_status ON documents(parse_status)")

    # ── document_chunks ──
    op.execute(
        """CREATE TABLE document_chunks (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            chunk_type      VARCHAR(16) NOT NULL CHECK (chunk_type IN ('paragraph','section')),
            chunk_index     INTEGER NOT NULL,
            content         TEXT NOT NULL,
            token_count     INTEGER,
            page_start      INTEGER,
            page_end        INTEGER,
            embedding_status VARCHAR(16) NOT NULL DEFAULT 'pending'
                            CHECK (embedding_status IN ('pending','indexed','error')),
            embedding_id    VARCHAR(256),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(document_id, chunk_type, chunk_index)
        )"""
    )
    op.execute("CREATE INDEX idx_chunks_doc_id ON document_chunks(document_id)")
    op.execute("CREATE INDEX idx_chunks_project_id ON document_chunks(project_id)")
    op.execute("CREATE INDEX idx_chunks_embedding_status ON document_chunks(embedding_status)")
    op.execute(
        "CREATE INDEX idx_chunks_content_fts ON document_chunks "
        "USING GIN (to_tsvector('simple', content))"
    )
    op.execute(
        "CREATE INDEX idx_chunks_content_trgm ON document_chunks "
        "USING GIN (content gin_trgm_ops)"
    )

    # ── analysis_tasks ──
    op.execute(
        """CREATE TABLE analysis_tasks (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            task_type       VARCHAR(32) NOT NULL
                            CHECK (task_type IN ('literature_review','policy_draft','policy_comparison','tech_interpretation')),
            status          VARCHAR(16) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','running','completed','failed','cancelled')),
            sensitivity     VARCHAR(8) NOT NULL DEFAULT 'low'
                            CHECK (sensitivity IN ('high','low')),
            llm_route       VARCHAR(32) NOT NULL DEFAULT '',
            llm_preference  VARCHAR(8) NOT NULL DEFAULT 'auto'
                            CHECK (llm_preference IN ('auto','local','cloud')),
            iteration_count INTEGER NOT NULL DEFAULT 0,
            celery_task_id  VARCHAR(256),
            completion_type VARCHAR(32) NOT NULL DEFAULT 'normal'
                            CHECK (completion_type IN ('normal','max_iterations_reached','fallback')),
            title           VARCHAR(512),
            parameters      JSONB NOT NULL DEFAULT '{}',
            progress        JSONB NOT NULL DEFAULT '{}',
            result_summary  TEXT,
            error_message   TEXT,
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_tasks_project_id ON analysis_tasks(project_id)")
    op.execute("CREATE INDEX idx_tasks_created_by ON analysis_tasks(created_by)")
    op.execute("CREATE INDEX idx_tasks_status ON analysis_tasks(status)")
    op.execute("CREATE INDEX idx_tasks_task_type ON analysis_tasks(task_type)")
    op.execute("CREATE INDEX idx_tasks_created_at ON analysis_tasks(created_at DESC)")
    op.execute("CREATE INDEX idx_tasks_progress ON analysis_tasks USING GIN (progress)")

    # ── task_outputs ──
    op.execute(
        """CREATE TABLE task_outputs (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            task_id         UUID NOT NULL REFERENCES analysis_tasks(id) ON DELETE CASCADE,
            format          VARCHAR(16) NOT NULL
                            CHECK (format IN ('markdown','docx','xlsx','pptx')),
            title           VARCHAR(512),
            content         TEXT,
            minio_path      VARCHAR(1024),
            citation_count  INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_outputs_task_id ON task_outputs(task_id)")

    # ── citations ──
    op.execute(
        """CREATE TABLE citations (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            task_output_id  UUID NOT NULL REFERENCES task_outputs(id) ON DELETE CASCADE,
            ref_id          VARCHAR(256) NOT NULL,
            sentence        TEXT NOT NULL,
            sentence_index  INTEGER NOT NULL,
            confidence      VARCHAR(16) NOT NULL
                            CHECK (confidence IN ('direct','fuzzy','uncertain')),
            chunk_ids       JSONB NOT NULL DEFAULT '[]',
            page_ranges     JSONB NOT NULL DEFAULT '[]',
            verified_at     TIMESTAMPTZ,
            verified_by     UUID REFERENCES users(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_citations_task_output ON citations(task_output_id)")
    op.execute("CREATE INDEX idx_citations_confidence ON citations(confidence)")

    # ── audit_logs ──
    op.execute(
        """CREATE TABLE audit_logs (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id         UUID,
            action          VARCHAR(64) NOT NULL,
            resource_type   VARCHAR(32) NOT NULL,
            resource_id     UUID,
            details         JSONB NOT NULL DEFAULT '{}',
            ip_address      INET,
            user_agent      TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_audit_user_id ON audit_logs(user_id)")
    op.execute("CREATE INDEX idx_audit_action ON audit_logs(action)")
    op.execute("CREATE INDEX idx_audit_resource_type ON audit_logs(resource_type)")
    op.execute("CREATE INDEX idx_audit_created_at ON audit_logs(created_at DESC)")
    op.execute("CREATE INDEX idx_audit_user_action ON audit_logs(user_id, action)")
    op.execute("CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id)")

    # ── llm_usage_logs ──
    op.execute(
        """CREATE TABLE llm_usage_logs (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            request_id        UUID NOT NULL,
            user_id           UUID,
            task_id           UUID,
            model             VARCHAR(64) NOT NULL,
            routing           VARCHAR(16) NOT NULL CHECK (routing IN ('cloud','local')),
            prompt_tokens     INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens      INTEGER NOT NULL DEFAULT 0,
            latency_ms        INTEGER,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_llm_usage_user ON llm_usage_logs(user_id)")
    op.execute("CREATE INDEX idx_llm_usage_task ON llm_usage_logs(task_id)")
    op.execute("CREATE INDEX idx_llm_usage_model ON llm_usage_logs(model)")
    op.execute("CREATE INDEX idx_llm_usage_created_at ON llm_usage_logs(created_at DESC)")

    # ── audit immutability ──
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM policyai")

    # ── updated_at trigger ──
    op.execute(
        """CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"""
    )
    op.execute(
        """CREATE TRIGGER trg_projects_updated_at
        BEFORE UPDATE ON projects
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"""
    )
    op.execute(
        """CREATE TRIGGER trg_documents_updated_at
        BEFORE UPDATE ON documents
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"""
    )
    op.execute(
        """CREATE TRIGGER trg_analysis_tasks_updated_at
        BEFORE UPDATE ON analysis_tasks
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_analysis_tasks_updated_at ON analysis_tasks")
    op.execute("DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents")
    op.execute("DROP TRIGGER IF EXISTS trg_projects_updated_at ON projects")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    op.execute("DROP TABLE IF EXISTS llm_usage_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS citations CASCADE")
    op.execute("DROP TABLE IF EXISTS task_outputs CASCADE")
    op.execute("DROP TABLE IF EXISTS analysis_tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS document_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS projects CASCADE")
    op.execute("DROP TABLE IF EXISTS project_group_members CASCADE")
    op.execute("DROP TABLE IF EXISTS project_groups CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
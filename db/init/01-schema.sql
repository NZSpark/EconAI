-- =============================================================================
-- EconAI Database Schema
-- All tables, indexes, and FTS configuration
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- for text search fallback

-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username    VARCHAR(128) NOT NULL UNIQUE,
    email       VARCHAR(256) NOT NULL UNIQUE,
    display_name VARCHAR(256),
    hashed_password VARCHAR(256) NOT NULL,
    role        VARCHAR(32)  NOT NULL DEFAULT 'analyst'
                CHECK (role IN ('analyst','senior_researcher','project_admin','system_admin')),
    auth_provider VARCHAR(16) NOT NULL DEFAULT 'local'
                CHECK (auth_provider IN ('local','ldap')),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    consent_given_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_is_active ON users(is_active);
CREATE INDEX idx_users_auth_provider ON users(auth_provider);

-- ---------------------------------------------------------------------------
-- Project Groups
-- ---------------------------------------------------------------------------
CREATE TABLE project_groups (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(256) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Project Group Members (many-to-many: groups <-> users)
-- ---------------------------------------------------------------------------
CREATE TABLE project_group_members (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    group_id    UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        VARCHAR(32) NOT NULL DEFAULT 'analyst',
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(group_id, user_id)
);

CREATE INDEX idx_pgm_group_id ON project_group_members(group_id);
CREATE INDEX idx_pgm_user_id ON project_group_members(user_id);

-- ---------------------------------------------------------------------------
-- Projects
-- ---------------------------------------------------------------------------
CREATE TABLE projects (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(512) NOT NULL,
    description TEXT,
    group_id    UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
    owner_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status      VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_group_id ON projects(group_id);
CREATE INDEX idx_projects_owner_id ON projects(owner_id);
CREATE INDEX idx_projects_status ON projects(status);

-- ---------------------------------------------------------------------------
-- Documents
-- ---------------------------------------------------------------------------
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename        VARCHAR(512) NOT NULL,
    original_filename VARCHAR(512) NOT NULL,
    format          VARCHAR(32) NOT NULL,
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    minio_path      VARCHAR(1024),
    parse_status    VARCHAR(16) NOT NULL DEFAULT 'pending'
                    CHECK (parse_status IN ('pending','parsing','ready','error')),
    parse_error     TEXT,
    title           VARCHAR(1024),
    author          VARCHAR(512),
    page_count      INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_docs_project_id ON documents(project_id);
CREATE INDEX idx_docs_parse_status ON documents(parse_status);

-- ---------------------------------------------------------------------------
-- Document Chunks (multi-granularity: paragraph + section)
-- ---------------------------------------------------------------------------
CREATE TABLE document_chunks (
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
);

CREATE INDEX idx_chunks_doc_id ON document_chunks(document_id);
CREATE INDEX idx_chunks_project_id ON document_chunks(project_id);
CREATE INDEX idx_chunks_embedding_status ON document_chunks(embedding_status);

-- Full-text search index (GIN) for BM25 keyword retrieval
CREATE INDEX idx_chunks_content_fts ON document_chunks
    USING GIN (to_tsvector('simple', content));

-- ---------------------------------------------------------------------------
-- Analysis Tasks
-- ---------------------------------------------------------------------------
CREATE TABLE analysis_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_type       VARCHAR(32) NOT NULL
                    CHECK (task_type IN ('literature_review','policy_draft','policy_comparison','tech_interpretation')),
    status          VARCHAR(16) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','completed','failed','cancelled')),
    sensitivity     VARCHAR(8) NOT NULL DEFAULT 'low'
                    CHECK (sensitivity IN ('high','low')),
    title           VARCHAR(512),
    parameters      JSONB NOT NULL DEFAULT '{}',
    progress        JSONB NOT NULL DEFAULT '{}',
    result_summary  TEXT,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tasks_project_id ON analysis_tasks(project_id);
CREATE INDEX idx_tasks_created_by ON analysis_tasks(created_by);
CREATE INDEX idx_tasks_status ON analysis_tasks(status);
CREATE INDEX idx_tasks_task_type ON analysis_tasks(task_type);
CREATE INDEX idx_tasks_created_at ON analysis_tasks(created_at DESC);

-- JSONB index for progress fields
CREATE INDEX idx_tasks_progress ON analysis_tasks USING GIN (progress);

-- ---------------------------------------------------------------------------
-- Task Outputs
-- ---------------------------------------------------------------------------
CREATE TABLE task_outputs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id         UUID NOT NULL REFERENCES analysis_tasks(id) ON DELETE CASCADE,
    format          VARCHAR(16) NOT NULL
                    CHECK (format IN ('markdown','docx','xlsx','pptx')),
    title           VARCHAR(512),
    content         TEXT,
    minio_path      VARCHAR(1024),
    citation_count  INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outputs_task_id ON task_outputs(task_id);

-- ---------------------------------------------------------------------------
-- Citations
-- ---------------------------------------------------------------------------
CREATE TABLE citations (
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
);

CREATE INDEX idx_citations_task_output ON citations(task_output_id);
CREATE INDEX idx_citations_confidence ON citations(confidence);

-- ---------------------------------------------------------------------------
-- Audit Logs (append-only, immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID,
    action          VARCHAR(64) NOT NULL,
    resource_type   VARCHAR(32) NOT NULL,
    resource_id     UUID,
    details         JSONB NOT NULL DEFAULT '{}',
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_resource_type ON audit_logs(resource_type);
CREATE INDEX idx_audit_created_at ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_user_action ON audit_logs(user_id, action);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);

-- ---------------------------------------------------------------------------
-- LLM Usage Logs (cost tracking)
-- ---------------------------------------------------------------------------
CREATE TABLE llm_usage_logs (
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
);

CREATE INDEX idx_llm_usage_user ON llm_usage_logs(user_id);
CREATE INDEX idx_llm_usage_task ON llm_usage_logs(task_id);
CREATE INDEX idx_llm_usage_model ON llm_usage_logs(model);
CREATE INDEX idx_llm_usage_created_at ON llm_usage_logs(created_at DESC);

-- ---------------------------------------------------------------------------
-- Audit log immutability: revoke UPDATE/DELETE at database level
-- ---------------------------------------------------------------------------
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM econai;

-- ---------------------------------------------------------------------------
-- Updated_at trigger function
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_analysis_tasks_updated_at
    BEFORE UPDATE ON analysis_tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
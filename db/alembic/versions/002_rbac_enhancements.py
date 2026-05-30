"""RBAC enhancements — group-scoped audit, review workflow, schema fixes.

Revision ID: 002_rbac_enhancements
Revises: 001_base
Create Date: 2026-05-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002_rbac_enhancements"
down_revision: Union[str, None] = "001_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Fix users schema drift ──
    # ldap_dn not in 001 migration
    op.execute(
        """ALTER TABLE users ADD COLUMN IF NOT EXISTS ldap_dn VARCHAR(255)"""
    )
    # hashed_password should be nullable (LDAP users don't have one)
    op.execute(
        """ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL"""
    )

    # ── 2. Fix projects schema drift: owner_id → created_by ──
    # 检查 if column exists with old name
    conn = op.get_bind()
    result = conn.exec_driver_sql(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='projects' AND column_name='owner_id'"
    )
    if result.scalar():
        op.execute(
            "ALTER TABLE projects RENAME COLUMN owner_id TO created_by"
        )
        op.execute(
            "ALTER INDEX IF EXISTS idx_projects_owner_id "
            "RENAME TO idx_projects_created_by"
        )

    # ── 3. Add group_id to audit_logs — group-scoped audit access ──
    op.execute(
        """ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS group_id UUID 
        REFERENCES project_groups(id) ON DELETE SET NULL"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_group_id ON audit_logs(group_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_user_group ON audit_logs(user_id, group_id)"
    )

    # ── 4. Add review_status to task_outputs — approval workflow ──
    op.execute(
        """ALTER TABLE task_outputs ADD COLUMN IF NOT EXISTS review_status 
        VARCHAR(16) NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','reviewing','approved','revision'))"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_outputs_review_status ON task_outputs(review_status)"
    )
    op.execute(
        """ALTER TABLE task_outputs ADD COLUMN IF NOT EXISTS reviewed_by UUID 
        REFERENCES users(id) ON DELETE SET NULL"""
    )
    op.execute(
        """ALTER TABLE task_outputs ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ"""
    )

    # ── 5. Create user_consents table (GDPR compliance) ──
    op.execute(
        """CREATE TABLE IF NOT EXISTS user_consents (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            processing_consent  BOOLEAN NOT NULL DEFAULT FALSE,
            analytics_consent   BOOLEAN NOT NULL DEFAULT FALSE,
            consented_at        TIMESTAMPTZ,
            withdrawn_at        TIMESTAMPTZ,
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_consents_user_id ON user_consents(user_id)"
    )

    # ── 6. Update project_groups.name to be unique (ORM model says unique=True) ──
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_project_groups_name_unique 
        ON project_groups(name)"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_groups_name_unique")
    op.execute("DROP TABLE IF EXISTS user_consents CASCADE")
    op.execute("ALTER TABLE task_outputs DROP COLUMN IF EXISTS reviewed_at")
    op.execute("ALTER TABLE task_outputs DROP COLUMN IF EXISTS reviewed_by")
    op.execute("ALTER TABLE task_outputs DROP COLUMN IF EXISTS review_status")
    op.execute("DROP INDEX IF EXISTS idx_audit_user_group")
    op.execute("DROP INDEX IF EXISTS idx_audit_group_id")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS group_id")
    op.execute("ALTER TABLE users ALTER COLUMN hashed_password SET NOT NULL")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS ldap_dn")

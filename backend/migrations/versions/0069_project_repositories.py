"""Track 3: which repository is the LEGACY one and which is the TARGET, per project.

Replaces research §5.1's proposal (a `legacy`/`target` segment in the stage-mode key): that
key's third segment is already the connector KIND (`{agent}::connector::azure_devops`), and the
legacy and target repositories are routinely the same kind under the same credential, so the
two roles would collide there (build log, decision D9). The ROLE is a project setting of its
own; the connector grant → stage wiring → access level chain is unchanged and still has to
permit the write (`shared/services/repository_roles.py`).

One row per (project, role). FORCE RLS on `app.current_tenant_id`.

Also two project settings for the universal Project Admin fallback (research §12.2):
`approval_fallback_mode` — "always" (default) or "after_sla"; and `approval_policy` —
"standard" (default), "pilot" or "strict" (strict: a Project Admin never stands in for the
business owner). NOT NULL with defaults, so every existing project reads as before.

Revision ID: 0069_project_repositories
Revises: 0068_version_provenance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0069_project_repositories"
down_revision = "0068_version_provenance"
branch_labels = None
depends_on = None

TABLE = "project_repositories"


def upgrade() -> None:
    op.add_column("projects", sa.Column("approval_fallback_mode", sa.String(16), nullable=False,
                                        server_default="always"))
    op.add_column("projects", sa.Column("approval_policy", sa.String(16), nullable=False,
                                        server_default="standard"))
    op.create_check_constraint("ck_projects_fallback_mode", "projects",
                               "approval_fallback_mode IN ('always', 'after_sla')")
    op.create_check_constraint("ck_projects_approval_policy", "projects",
                               "approval_policy IN ('standard', 'pilot', 'strict')")
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("branch", sa.String(255), nullable=False, server_default=""),
        sa.Column("set_by", sa.String(255)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "role", name="uq_project_repository_role"),
        sa.CheckConstraint("role IN ('legacy', 'target')", name="ck_project_repository_role"),
        sa.CheckConstraint("url ~ '^https://'", name="ck_project_repository_https"),
    )
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {TABLE} "
               "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)")
    op.execute(f"CREATE POLICY tenant_isolation_insert ON {TABLE} "
               "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sdlc_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO sdlc_app;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.drop_table(TABLE)
    op.drop_constraint("ck_projects_approval_policy", "projects", type_="check")
    op.drop_constraint("ck_projects_fallback_mode", "projects", type_="check")
    op.drop_column("projects", "approval_policy")
    op.drop_column("projects", "approval_fallback_mode")

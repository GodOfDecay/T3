"""Track 3 Phase I: Migration Review and Security (Modernization) get somewhere to write.

  runs.migration_review_artifacts        what Migration Review records on its conversation's run (one
                                         module's review); the page's history is the frozen
                                         `artifact_versions` rows.
  runs.modernization_security_artifacts  the same for Security (one module's security report).
  orchestrator_deliverables CHECK        both may file a deliverable.

The sign-off permissions (`artifact:approve_code_review_modernization`,
`artifact:approve_security_modernization`) already exist (0066). Accepting a version writes the
module's verdict on the ledger in the same transaction (`shared/routers/artifact_versions.py`).

Revision ID: 0075_review_security
Revises: 0074_migration_development
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0075_review_security"
down_revision = "0074_migration_development"
branch_labels = None
depends_on = None

_TABLE = "orchestrator_deliverables"
_CHECK = "ck_orchestrator_deliverables_agent_id"


def upgrade() -> None:
    op.add_column("runs", sa.Column("migration_review_artifacts", postgresql.JSONB(), nullable=True))
    op.add_column("runs", sa.Column("modernization_security_artifacts", postgresql.JSONB(), nullable=True))
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    # Written out in full: tests/orchestrator2/test_deliverables_schema.py reads this list from the
    # newest migration's source and pins it to the registry.
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization','strategy',"
        "'testing_modernization','development_modernization','code_review_modernization',"
        "'security_modernization')",
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE} WHERE agent_id IN ('code_review_modernization', 'security_modernization')")
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization','strategy',"
        "'testing_modernization','development_modernization')",
    )
    op.drop_column("runs", "modernization_security_artifacts")
    op.drop_column("runs", "migration_review_artifacts")

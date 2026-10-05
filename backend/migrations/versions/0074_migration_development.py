"""Track 3 Phase H: Migration Development gets somewhere to write.

  runs.migration_artifacts            what Migration Development records on its conversation's run (one
                                      module's migration record); the page's history is the frozen
                                      `artifact_versions` rows. The code itself is in the TARGET repository
                                      and the module's workspace, never in the database.
  orchestrator_deliverables CHECK     `development_modernization` may file a deliverable.

The sign-off permission (`artifact:approve_development_modernization`) already exists (0066).

Revision ID: 0074_migration_development
Revises: 0073_equivalence
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0074_migration_development"
down_revision = "0073_equivalence"
branch_labels = None
depends_on = None

_TABLE = "orchestrator_deliverables"
_CHECK = "ck_orchestrator_deliverables_agent_id"


def upgrade() -> None:
    op.add_column("runs", sa.Column("migration_artifacts", postgresql.JSONB(), nullable=True))
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    # Written out in full: tests/orchestrator2/test_deliverables_schema.py reads this list from the
    # newest migration's source and pins it to the registry.
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization','strategy',"
        "'testing_modernization','development_modernization')",
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE} WHERE agent_id = 'development_modernization'")
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization','strategy',"
        "'testing_modernization')",
    )
    op.drop_column("runs", "migration_artifacts")

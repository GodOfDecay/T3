"""Track 3 Phase G: Equivalence Testing (Baseline mode) gets somewhere to write.

  runs.equivalence_artifacts          what Equivalence Testing records on its conversation's run;
                                      the page's history is the frozen `artifact_versions` rows.
                                      Recordings themselves are NOT in the database: they stay in
                                      the baseline store (files, later blob storage), by capture id.
  orchestrator_deliverables CHECK     `testing_modernization` may file a deliverable.

The sign-off permission (`artifact:approve_testing_modernization`) already exists (0066).

Revision ID: 0073_equivalence
Revises: 0072_strategy
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0073_equivalence"
down_revision = "0072_strategy"
branch_labels = None
depends_on = None

_TABLE = "orchestrator_deliverables"
_CHECK = "ck_orchestrator_deliverables_agent_id"


def upgrade() -> None:
    op.add_column("runs", sa.Column("equivalence_artifacts", postgresql.JSONB(), nullable=True))
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    # Written out in full: tests/orchestrator2/test_deliverables_schema.py reads this list from the
    # newest migration's source and pins it to the registry.
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization','strategy',"
        "'testing_modernization')",
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE} WHERE agent_id = 'testing_modernization'")
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization','strategy')",
    )
    op.drop_column("runs", "equivalence_artifacts")

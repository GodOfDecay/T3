"""Track 3 Phase F: Migration Strategy gets somewhere to write.

  runs.strategy_artifacts             what Migration Strategy records on its conversation's run
                                      (a page's chat run, or an Orchestrator run); the page's
                                      history is the frozen `artifact_versions` rows.
  orchestrator_deliverables CHECK     `strategy` may file a deliverable.

The sign-off permission (`artifact:approve_strategy`) already exists (0066).

Revision ID: 0072_strategy
Revises: 0071_target_design
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0072_strategy"
down_revision = "0071_target_design"
branch_labels = None
depends_on = None

_TABLE = "orchestrator_deliverables"
_CHECK = "ck_orchestrator_deliverables_agent_id"


def upgrade() -> None:
    op.add_column("runs", sa.Column("strategy_artifacts", postgresql.JSONB(), nullable=True))
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    # Written out in full: tests/orchestrator2/test_deliverables_schema.py reads this list from the
    # newest migration's source and pins it to the registry.
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization','strategy')",
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE} WHERE agent_id = 'strategy'")
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization')",
    )
    op.drop_column("runs", "strategy_artifacts")

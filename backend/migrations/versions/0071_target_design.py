"""Track 3 Phase E: Target Architecture gets somewhere to write.

Two changes, the same two 0057 made for agents 1 and 2 (the sign-off permission already exists,
0066):

  runs.target_design_artifacts         what Target Architecture records on the run its
                                       conversation belongs to (a page's chat run, or an
                                       Orchestrator run). The page's history is the frozen
                                       `artifact_versions` rows, as for agents 1 and 2.
  orchestrator_deliverables CHECK      `design_modernization` may file a deliverable. An agent
                                       missing from it has its Orchestrator output refused at
                                       write time, which surfaces as an agent that produced
                                       nothing.

Revision ID: 0071_target_design
Revises: 0070_approval_sla_escalation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0071_target_design"
down_revision = "0070_approval_sla_escalation"
branch_labels = None
depends_on = None

_TABLE = "orchestrator_deliverables"
_CHECK = "ck_orchestrator_deliverables_agent_id"
_BEFORE = (
    "'requirements','design','plan','development','code_review','security','testing',"
    "'deployment','documentation','requirements_modernization','discovery'"
)


def upgrade() -> None:
    op.add_column("runs", sa.Column("target_design_artifacts", postgresql.JSONB(), nullable=True))
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    # Written out in full: tests/orchestrator2/test_deliverables_schema.py reads this list from the
    # newest migration's source and pins it to the registry.
    op.create_check_constraint(
        _CHECK, _TABLE,
        "agent_id IN ('requirements','design','plan','development',"
        "'code_review','security','testing','deployment','documentation',"
        "'requirements_modernization','discovery','design_modernization')",
    )


def downgrade() -> None:
    # Rows the narrower constraint would refuse go first, or it cannot come back.
    op.execute(f"DELETE FROM {_TABLE} WHERE agent_id = 'design_modernization'")
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(_CHECK, _TABLE, f"agent_id IN ({_BEFORE})")
    op.drop_column("runs", "target_design_artifacts")

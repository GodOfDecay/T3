"""Track 3: tell a project's Project Admins when a version has waited past its SLA.

Two changes:

  notifications.kind      allows `approval_sla_passed` (to the project's Project Admins:
                          a Code Modernization version is still a draft after the stage's
                          `sla_hours`, so they may approve it as fallback or chase the owner).
  artifact_versions.sla_notified_at
                          when that notification went out, so the sweep tells them ONCE
                          per version rather than every hour. Not provenance, so NOT on the
                          freeze trigger's write-once list — the sweep sets it on a draft.

Revision ID: 0070_approval_sla_escalation
Revises: 0069_project_repositories
"""
from alembic import op
import sqlalchemy as sa

revision = "0070_approval_sla_escalation"
down_revision = "0069_project_repositories"
branch_labels = None
depends_on = None

_KINDS = (
    "hitl_pending", "run_failed", "run_completed", "budget_near_cap",
    "guardrail_blocked", "mention", "request_created", "request_assigned",
    "request_approval_required", "request_approved", "request_rejected",
    "request_escalated", "member_awaiting_role", "project_activated",
    "artifact_superseded",
    "document_approval_required", "document_approved", "document_rejected",
)
_NEW = ("approval_sla_passed",)


def _rewrite(kinds: tuple[str, ...]) -> None:
    values = ", ".join(f"'{k}'" for k in kinds)
    op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS ck_notification_kind")
    op.execute(
        "ALTER TABLE notifications ADD CONSTRAINT ck_notification_kind "
        f"CHECK (kind IN ({values}))"
    )


def upgrade() -> None:
    _rewrite(_KINDS + _NEW)
    op.add_column("artifact_versions", sa.Column("sla_notified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("artifact_versions", "sla_notified_at")
    values = ", ".join(f"'{k}'" for k in _NEW)
    op.execute(f"DELETE FROM notifications WHERE kind IN ({values})")
    _rewrite(_KINDS)

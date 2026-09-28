"""Track 3 agents 3–10: their sign-off permissions exist before the agents do.

Phase B of the Track 3 build fixes every agent's owner in ONE change across the owner maps
(Lessons R10: `frontend/lib/roles.ts`, `shared/governance/routing.py::AGENT_OWNER_ROLE`,
`shared/authz/permissions.py::_PHASE_PERMISSION`, `config/agent_registry.py::_OWNER_OF`).
`role_permissions` is verified against `_ROLE_PERMISSIONS` at boot (same reasoning as
0042 and 0057), so the code change needs this data migration or an existing database
refuses to start.

Each permission is granted to the stage's owning role, to `project_admin` (the fallback
approver on every agent) and to `bu_admin` (which holds every approve permission today).

NOTHING ELSE. Each agent's `runs.<artifact>` column and its place in the deliverables CHECK
arrive with the agent itself: a column for an agent that does not exist is a column that
reads as "not run yet" forever.

Revision ID: 0066_track3_owner_rows
Revises: 0065_tech_stacks
"""
from alembic import op

revision = "0066_track3_owner_rows"
down_revision = "0065_tech_stacks"
branch_labels = None
depends_on = None

_OWNERS = (
    ("design_modernization", "architect"),
    ("strategy", "architect"),
    ("testing_modernization", "qa"),
    ("development_modernization", "developer"),
    ("code_review_modernization", "architect"),
    ("security_modernization", "security_engineer"),
    ("deployment_modernization", "devops_engineer"),
    ("documentation_modernization", "ba"),
)


def upgrade() -> None:
    for stage, owner in _OWNERS:
        permission = f"artifact:approve_{stage}"
        op.execute(
            "INSERT INTO permissions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING" % permission
        )
        for role in (owner, "project_admin", "bu_admin"):
            op.execute(
                "INSERT INTO role_permissions (role_name, permission_name) "
                "VALUES ('%s', '%s') ON CONFLICT (role_name, permission_name) DO NOTHING"
                % (role, permission)
            )


def downgrade() -> None:
    for stage, _owner in _OWNERS:
        permission = f"artifact:approve_{stage}"
        # Every grant, not only ours: boot reconciliation or an admin may have added one.
        op.execute("DELETE FROM role_permissions WHERE permission_name = '%s'" % permission)
        op.execute("DELETE FROM permissions WHERE name = '%s'" % permission)

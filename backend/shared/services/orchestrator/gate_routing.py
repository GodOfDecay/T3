"""Gate routing — stage owner, approval check, and notify seam.

`gate_owner_role` answers from `shared.governance.routing.AGENT_OWNER_ROLE`, the one owner
map the platform keeps. can_user_approve reuses the canonical RBAC primitives
(_PHASE_PERMISSION + has_permission) so approval logic is never duplicated.
notify_gate_pending is a best-effort audit seam; it never raises into the gate flow.

THERE USED TO BE A FOURTH OWNER MAP HERE. `GATE_OWNER` named roles the platform does not
have (`product_manager`, `tech_lead`, `sre_lead`, …), covered Track 1 only, and answered
`"product_manager"` for any stage it did not know — the swallowing default that produced
the `code_review` owner defect elsewhere (Lessons R10). Nothing called it (grep, 2026-09-28),
so it is now a read-only view of the real map, and an unknown stage raises.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from shared.authz.permissions import _PHASE_PERMISSION, has_permission
from shared.governance.routing import AGENT_OWNER_ROLE, agent_owner_role

logger = logging.getLogger(__name__)

#: Read-only view of `AGENT_OWNER_ROLE`, kept under its old name for any caller outside
#: this repository. Never a copy: a copy is a second map, and second maps drift.
GATE_OWNER = MappingProxyType(AGENT_OWNER_ROLE)


def gate_owner_role(stage: str) -> str:
    """The owning role for `stage`'s gate. Raises `UnknownAgentPhase` for a stage that
    names no agent — never a plausible default."""
    return agent_owner_role(stage)


def stage_approve_permission(stage: str) -> str | None:
    """Return the permission string required to approve *stage*, or None if unmapped."""
    return _PHASE_PERMISSION.get(stage)


def can_user_approve(perms: list[str], stage: str) -> bool:
    """Return True if perms grant approval rights for the given stage.

    Delegates entirely to _PHASE_PERMISSION (stage→required permission) and
    has_permission (which handles admin:* wildcard), so enforcement is consistent
    with every other RBAC check in the codebase.
    """
    required = _PHASE_PERMISSION.get(stage)
    if not required:
        return False
    return has_permission(perms, required)


async def notify_gate_pending(
    run_id: str, stage: str, owner_role: str, tenant_id: str
) -> None:
    """Record and DELIVER a notification when a gate is awaiting approval.

    Two halves, both best-effort:
      1. An audit event (as before).
      2. Actual delivery to whichever human channels the tenant configured — Slack,
         Microsoft Teams, or neither.

    Until the delivery half existed this function only wrote an audit row, so a gate
    could sit awaiting approval with nobody told. Both call sites in copilot_api
    (_apply_gate) get delivery for free — neither needed to change.

    Any failure is logged and swallowed: this seam must never break the gate flow.
    """
    try:
        from shared.audit.models import AuditEventPayload
        from shared.audit.service import audit_service

        payload = AuditEventPayload(
            tenant_id=tenant_id,
            run_id=run_id,
            event_type="gate.notified",
            resource_type="gate",
            resource_id=run_id,
            payload={"stage": stage, "owner_role": owner_role},
        )
        await audit_service.emit(payload)

        # Deep link into the existing authenticated approval UI rather than an inline
        # approve action: a chat-card callback carries no user identity the platform
        # can trust, and honouring one would route around the permission check in
        # shared/routers/signals.py.
        from config.env import AGENTIC_BASE_URL
        from shared.services.notify_dispatch import notify_all

        await notify_all(
            tenant_id,
            f"Run {run_id} is awaiting {stage.replace('_', ' ')} approval "
            f"(owner: {owner_role}).",
            title="Approval needed",
            link_url=f"{(AGENTIC_BASE_URL or '').rstrip('/')}/runs/{run_id}",
        )
    except Exception as exc:  # best-effort: notification must never raise into caller
        logger.warning("notify_gate_pending failed (run=%s stage=%s): %s", run_id, stage, exc)

"""The universal Project Admin fallback for Track 3 sign-offs (research §12.2).

THE RULE. Every Track 3 version can be approved by its owning role, or by a Project Admin of
THAT project as fallback. Nobody — the Project Admin included — approves a version they
produced. A fallback decision is labelled (`approved_as = "fallback:project_admin"`), needs a
reason (a database CHECK as well as here), and is listed in the Cutover Pack.

    decide(...)            the rule itself, a pure function: every refusal is testable
                           without a database and says, in words, why.
    approval_capacity(...) the facts `decide` needs, read from the database: the person's
                           roles ON THIS PROJECT (project-scoped bindings — a role held
                           elsewhere in the tenant does not count), the project's fallback
                           mode and policy, the version's age against the stage's SLA,
                           and whether anyone holds the owning role.

MULTI-APPROVER GATES (Cutover's release sign-off: DevOps + business owner). A Project Admin
fills AT MOST ONE slot on an item, and under the Strict policy never the business owner's —
that acceptance is a business decision, not a delivery one. The slots themselves are
persisted with the Cutover agent (Phase K); `decide` already enforces the rule.

WHERE IT APPLIES. Track 3 stages only (`shared/services/repository_roles.TRACK3_STAGES`).
Track 1's publish path is unchanged: its Project Admin already holds every approve
permission and approves without a reason, and changing that is not Track 3's call.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.governance.routing import agent_owner_role
from shared.services.repository_roles import TRACK3_STAGES

OWNER, FALLBACK = "owner", "fallback:project_admin"
POLICIES = ("standard", "pilot", "strict")
MODES = ("always", "after_sla")
DEFAULT_SLA_HOURS = 48
BUSINESS_OWNER_SLOT = "business_owner"


class ApprovalRefused(Exception):
    """This person may not approve this version, in this capacity. The message says why."""


@dataclass(frozen=True)
class Capacity:
    approved_as: str
    reason: Optional[str] = None


def decide(*, stage: str, roles: Iterable[str], is_producer: bool, reason: Optional[str] = None,
           mode: str = "always", policy: str = "standard", sla_passed: bool = True,
           owner_staffed: bool = True, slot: Optional[str] = None,
           fallback_slots_held: int = 0) -> Capacity:
    """The capacity in which this person approves, or `ApprovalRefused`.

    `slot` names the role slot being filled on a multi-approver item (None for the ordinary
    single sign-off); `fallback_slots_held` is how many slots on the SAME item this person
    already filled as fallback.
    """
    roles = set(roles)
    if is_producer:
        raise ApprovalRefused("you produced this version, so someone else approves it")
    owner = slot if slot and slot != BUSINESS_OWNER_SLOT else agent_owner_role(stage)
    if slot != BUSINESS_OWNER_SLOT and owner in roles:
        return Capacity(OWNER)
    if "project_admin" not in roles:
        who = "the business owner" if slot == BUSINESS_OWNER_SLOT else f"a {owner.replace('_', ' ')}"
        raise ApprovalRefused(f"only {who} or a Project Admin of this project approves this")
    if slot == BUSINESS_OWNER_SLOT and policy == "strict":
        raise ApprovalRefused("under the Strict policy a Project Admin cannot stand in for the business owner")
    if slot is not None and fallback_slots_held >= 1:
        raise ApprovalRefused("a Project Admin fills at most one slot on the same item")
    if mode == "after_sla" and owner_staffed and not sla_passed:
        raise ApprovalRefused(
            f"this project lets a Project Admin decide only after the {owner.replace('_', ' ')} has had the "
            "gate's SLA to decide; that time has not passed yet")
    if not (reason or "").strip():
        raise ApprovalRefused("approving as Project Admin fallback needs a reason — it is recorded and listed "
                              "in the Cutover Pack")
    return Capacity(FALLBACK, reason.strip())


#: A binding counts only while it is live: active AND not past `expires_at` (the resolver's
#: rule, shared/authz/resolver.py — an expired binding kept granting there once too).
_LIVE = "AND status = 'active' AND (expires_at IS NULL OR expires_at > now())"


async def project_roles(db: AsyncSession, *, tenant_id: str, project_id: str, user_id: str) -> set[str]:
    """The roles this person holds ON THIS PROJECT (active, project-scoped bindings)."""
    rows = await db.execute(text(
        "SELECT role_name FROM role_bindings WHERE tenant_id = CAST(:t AS uuid) AND user_id = :u "
        "AND scope_kind = 'project' AND scope_id = CAST(:p AS uuid) " + _LIVE),
        {"t": tenant_id, "u": user_id, "p": project_id})
    return {r[0] for r in rows}


async def owner_staffed(db: AsyncSession, *, tenant_id: str, project_id: str, stage: str,
                        excluding: Iterable[str] = ()) -> bool:
    """Does anyone who COULD approve hold the stage's owning role on this project? The
    version's producers are `excluding`: an owner who produced it cannot approve it, so they
    do not make the role "staffed" for the after-SLA rule."""
    return bool((await db.execute(text(
        "SELECT 1 FROM role_bindings WHERE tenant_id = CAST(:t AS uuid) AND scope_kind = 'project' "
        "AND scope_id = CAST(:p AS uuid) AND role_name = :r AND NOT (user_id = ANY(:x)) " + _LIVE + " LIMIT 1"),
        {"t": tenant_id, "p": project_id, "r": agent_owner_role(stage), "x": list(excluding)})).first())


def _sla_hours(stage: str) -> int:
    from config.agent_registry import AGENT_REGISTRY  # noqa: PLC0415

    definition = AGENT_REGISTRY.get(stage)
    return int(getattr(definition, "sla_hours", None) or DEFAULT_SLA_HOURS)


async def approval_capacity(db: AsyncSession, *, tenant_id: str, project_id: str, stage: str,
                            user_id: str, produced_by: str, version_created_at: Optional[datetime],
                            reason: Optional[str] = None, now: Optional[datetime] = None,
                            also_produced_by: Iterable[str] = ()) -> Capacity:
    """`decide`, with the facts read from the database. Only for Track 3 stages.

    `also_produced_by`: whoever produced the CONTENT this version carries — for a restored
    version, the producers of every version it was restored from. Restoring someone's work
    must not let them approve it (`version_lineage.producers_of`)."""
    if stage not in TRACK3_STAGES:
        raise ValueError(f"{stage} is not a Track 3 stage")
    settings = (await db.execute(text(
        "SELECT approval_fallback_mode, approval_policy FROM projects WHERE id = CAST(:p AS uuid)"),
        {"p": project_id})).first()
    mode, policy = (settings or ("always", "standard"))
    now = now or datetime.now(timezone.utc)
    sla_passed = version_created_at is None or now - version_created_at >= timedelta(hours=_sla_hours(stage))
    producers = {produced_by, *also_produced_by}
    return decide(
        stage=stage, roles=await project_roles(db, tenant_id=tenant_id, project_id=project_id, user_id=user_id),
        is_producer=(user_id in producers), reason=reason, mode=mode, policy=policy, sla_passed=sla_passed,
        owner_staffed=await owner_staffed(db, tenant_id=tenant_id, project_id=project_id, stage=stage,
                                          excluding=producers),
    )


async def staffing_warnings(db: AsyncSession, *, tenant_id: str, project_id: str) -> list[str]:
    """What could deadlock a gate under no-self-approval (research §12.2 rule 1): fewer than two
    Project Admins, and owning roles nobody holds. Warnings, not refusals."""
    rows = (await db.execute(text(
        "SELECT role_name, count(DISTINCT user_id) FROM role_bindings WHERE tenant_id = CAST(:t AS uuid) "
        "AND scope_kind = 'project' AND scope_id = CAST(:p AS uuid) " + _LIVE + " GROUP BY role_name"),
        {"t": tenant_id, "p": project_id})).all()
    held = {r[0]: r[1] for r in rows}
    warnings = []
    if held.get("project_admin", 0) < 2:
        warnings.append(
            f"This project has {held.get('project_admin', 0)} Project Admin(s). With fewer than two, a version a "
            "Project Admin produced (every Orchestrator deliverable) can only be approved by its owning role.")
    unstaffed = sorted({agent_owner_role(s) for s in TRACK3_STAGES} - {r for r, n in held.items() if n})
    if unstaffed:
        warnings.append("No one on this project holds: " + ", ".join(r.replace("_", " ") for r in unstaffed)
                        + ". Their gates fall to a Project Admin.")
    return warnings

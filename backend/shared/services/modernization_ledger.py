"""The Module Migration Ledger service — the ONLY writer of `modernization_modules` (0067).

WHO MAY MOVE A MODULE, AND WHERE TO. The database trigger guarantees the machine (no skipped
state, no lost history); this module guarantees the AUTHOR: each transition belongs to one
agent (Flow document §20.3), a person may block, unblock or reopen with a reason, and nothing
else can move a module. There is deliberately no generic "set state": every caller goes
through a named method, so a grep answers "who can put a module into `verified`?".

REVIEW AND SECURITY RUN AT THE SAME TIME on the same pull request. Each records its own verdict
under a row lock (`SELECT … FOR UPDATE`), and whichever reports second settles the module —
both good → `verifying`; either bad → back to `migrating`, and past `MAX_REJECTIONS` →
`blocked`. The lock is what stops the second writer from overwriting the first one's verdict.

NO COMMIT HERE (Lessons R23): the caller's session owns the transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.orm import ModernizationModule

STATES = ("assessed", "designed", "sequenced", "baselined", "migrating", "in_review",
          "verifying", "verified", "cut_over", "retired", "blocked")

#: (from, to) → the agents that may make it. Mirrors `TRANSITIONS` in migration 0067
#: (pinned by a test). `blocked` and leaving it are handled by `block` / `unblock`.
ALLOWED: dict[tuple[str, str], frozenset[str]] = {
    ("assessed", "designed"): frozenset({"design_modernization"}),
    ("designed", "sequenced"): frozenset({"strategy"}),
    ("sequenced", "baselined"): frozenset({"testing_modernization"}),
    ("baselined", "migrating"): frozenset({"development_modernization"}),
    ("migrating", "in_review"): frozenset({"development_modernization"}),
    ("in_review", "verifying"): frozenset({"code_review_modernization", "security_modernization"}),
    ("in_review", "migrating"): frozenset({"code_review_modernization", "security_modernization"}),
    ("verifying", "verified"): frozenset({"testing_modernization"}),
    ("verifying", "migrating"): frozenset({"testing_modernization"}),
    ("verified", "cut_over"): frozenset({"deployment_modernization"}),
    ("cut_over", "verified"): frozenset({"deployment_modernization"}),
    ("cut_over", "retired"): frozenset({"deployment_modernization"}),
}

#: Transitions a PERSON makes, never an agent, with a reason (research §12.4).
REOPENABLE = frozenset({"verified", "cut_over"})
PERSON_ROLES = frozenset({"architect", "project_admin"})

TRACK3_AGENTS = frozenset({
    "requirements_modernization", "discovery", "design_modernization", "strategy",
    "testing_modernization", "development_modernization", "code_review_modernization",
    "security_modernization", "deployment_modernization", "documentation_modernization",
})

#: Rework rounds before a module is blocked and escalated to the Architect.
MAX_REJECTIONS = 3

REVIEW_GOOD, REVIEW_BAD = {"approve"}, {"request_changes"}
SECURITY_GOOD, SECURITY_BAD = {"PASS", "CONDITIONAL"}, {"FAIL"}


class LedgerRefused(Exception):
    """A transition this caller may not make. The message says why, for a person."""


@dataclass(frozen=True)
class ArtifactRef:
    """The artifact version that caused a transition, recorded in its history entry."""

    stage: str
    version: Optional[int] = None

    def as_dict(self) -> dict:
        return {"stage": self.stage, "version": self.version}


def _entry(*, frm: Optional[str], to: str, agent: str, actor: Optional[str],
           reason: Optional[str] = None, artifact: Optional[ArtifactRef] = None,
           note: Optional[str] = None) -> dict:
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "from": frm, "to": to, "agent": agent, "by": actor,
        **({"reason": reason} if reason else {}),
        **({"artifact": artifact.as_dict()} if artifact else {}),
        **({"note": note} if note else {}),
    }


async def _locked(db: AsyncSession, project_id: str, module_id: str) -> ModernizationModule:
    row = (await db.execute(
        select(ModernizationModule)
        .where(ModernizationModule.project_id == project_id, ModernizationModule.module_id == module_id)
        .with_for_update()
    )).scalar_one_or_none()
    if row is None:
        raise LedgerRefused(f"{module_id} is not in this project's ledger")
    return row


def _move(row: ModernizationModule, to: str, *, agent: str, actor: Optional[str],
          reason: Optional[str] = None, artifact: Optional[ArtifactRef] = None) -> None:
    row.history = [*row.history, _entry(frm=row.state, to=to, agent=agent, actor=actor,
                                         reason=reason, artifact=artifact)]
    row.state = to
    row.state_changed_at = datetime.now(timezone.utc)
    row.state_changed_by = actor


async def _transition(db: AsyncSession, *, project_id: str, module_id: str, agent: str, to: str,
                      actor: Optional[str], artifact: Optional[ArtifactRef] = None,
                      fields: Optional[dict[str, Any]] = None) -> ModernizationModule:
    row = await _locked(db, project_id, module_id)
    allowed = ALLOWED.get((row.state, to))
    if allowed is None:
        raise LedgerRefused(f"{module_id} is {row.state}; it cannot move to {to}")
    if agent not in allowed:
        raise LedgerRefused(f"{module_id}: {row.state} → {to} belongs to {', '.join(sorted(allowed))}, not {agent}")
    for name, value in (fields or {}).items():
        setattr(row, name, value)
    _move(row, to, agent=agent, actor=actor, artifact=artifact)
    await db.flush()
    return row


# ── Target Architecture ──────────────────────────────────────────────────────

async def design_approved(db: AsyncSession, *, tenant_id: str, project_id: str, modules: Iterable[dict],
                          actor: Optional[str], artifact: ArtifactRef) -> list[ModernizationModule]:
    """An approved target design puts each in-scope module on the ledger as `designed`, with its
    patterns, contracts and ADRs. Re-approving a design updates those fields and records it, but
    never moves a module backwards.

    ID DRIFT IS REFUSED (D14). Module ids are stable within one assessed commit, not across
    commits: a later assessment may call a different folder M-03. A design that names M-03 for
    a module the ledger already holds at another path is not a revision of that module, and
    applying it would give one row two histories — so the whole approval is refused, naming
    both paths, and nothing is written (the caller's transaction rolls back)."""
    rows = []
    modules = list(modules)
    # THE OTHER DIRECTION (review fix #8): a module the ledger already holds under one id, named
    # by another id in this design, would give one folder two rows and two histories.
    # Locked, so a concurrent approval cannot move a row between this check and the writes below.
    held_rows = list((await db.execute(
        select(ModernizationModule).where(ModernizationModule.project_id == project_id).with_for_update()
    )).scalars().all())
    by_path = {(r.legacy_path or "").strip().strip("/"): r.module_id
               for r in held_rows if (r.legacy_path or "").strip().strip("/")}
    by_id = {r.module_id: (r.legacy_path or "").strip().strip("/") for r in held_rows}
    for m in modules:  # the same id on another path first: the clearer of the two messages
        path = (m.get("legacy_path") or "").strip().strip("/")
        if path and by_id.get(m["module_id"]) not in (None, "", path):
            raise LedgerRefused(
                f"{m['module_id']} is {by_id[m['module_id']]} on the ledger but {path} in this design — the module "
                "ids changed between assessed commits. Re-run the design on the assessment the ledger was built "
                "from, or ask an Architect to reconcile the ledger first.")
    for m in modules:
        path = (m.get("legacy_path") or "").strip().strip("/")
        held = by_path.get(path)
        if path and held and held != m["module_id"]:
            raise LedgerRefused(
                f"{path} is {held} on the ledger but {m['module_id']} in this design — the module ids changed "
                "between assessed commits. Re-run the design on the assessment the ledger was built from, or ask "
                "an Architect to reconcile the ledger first.")
    for m in modules:
        existing = (await db.execute(
            select(ModernizationModule)
            .where(ModernizationModule.project_id == project_id,
                   ModernizationModule.module_id == m["module_id"])
            .with_for_update()
        )).scalar_one_or_none()
        design = {k: m.get(k) or [] for k in ("patterns", "contract_ids", "adr_ids")}
        if existing is None:
            row = ModernizationModule(
                tenant_id=tenant_id, project_id=project_id, module_id=m["module_id"],
                module_name=m.get("module_name") or m["module_id"], legacy_path=m.get("legacy_path") or "",
                tier=m.get("tier"), risk_score=m.get("risk_score"), state="designed",
                state_changed_by=actor, **design,
                history=[_entry(frm=None, to="designed", agent="design_modernization", actor=actor,
                                artifact=artifact)],
            )
            db.add(row)
        else:
            row = existing
            if row.state == "assessed":
                for k, v in design.items():
                    setattr(row, k, v)
                _move(row, "designed", agent="design_modernization", actor=actor, artifact=artifact)
            else:
                for k, v in design.items():
                    setattr(row, k, v)
                row.history = [*row.history, _entry(frm=row.state, to=row.state, agent="design_modernization",
                                                     actor=actor, artifact=artifact, note="design revised")]
        rows.append(row)
    await db.flush()
    return rows


# ── Migration Strategy ───────────────────────────────────────────────────────

async def plan_approved(db: AsyncSession, *, project_id: str, module_id: str, wave: str, ec_ids: list[str],
                        actor: Optional[str], artifact: ArtifactRef) -> ModernizationModule:
    return await _transition(db, project_id=project_id, module_id=module_id, agent="strategy", to="sequenced",
                             actor=actor, artifact=artifact, fields={"wave": wave, "ec_ids": list(ec_ids)})


# ── Equivalence Testing ──────────────────────────────────────────────────────

async def baseline_accepted(db: AsyncSession, *, project_id: str, module_id: str, baseline_ids: list[str],
                            actor: Optional[str], artifact: ArtifactRef) -> ModernizationModule:
    return await _transition(db, project_id=project_id, module_id=module_id, agent="testing_modernization",
                             to="baselined", actor=actor, artifact=artifact,
                             fields={"baseline_ids": list(baseline_ids)})


async def equivalence_recorded(db: AsyncSession, *, project_id: str, module_id: str, verdict: str,
                               perf_verdict: Optional[str], actor: Optional[str],
                               artifact: ArtifactRef) -> ModernizationModule:
    """`verified` when every criterion passed, back to `migrating` on a failure; an `open`
    result (a normalization gap, a criterion not run) leaves the module in `verifying`."""
    if verdict == "open":
        row = await _locked(db, project_id, module_id)
        if row.state != "verifying":
            raise LedgerRefused(f"{module_id} is {row.state}; results are recorded while it is verifying")
        row.equivalence_verdict, row.perf_verdict = verdict, perf_verdict
        row.history = [*row.history, _entry(frm=row.state, to=row.state, agent="testing_modernization",
                                             actor=actor, artifact=artifact, note="equivalence open")]
        await db.flush()
        return row
    to = {"verified": "verified", "migrating": "migrating"}.get(verdict)
    if to is None:
        raise LedgerRefused(f"unknown equivalence verdict {verdict!r}")
    return await _transition(db, project_id=project_id, module_id=module_id, agent="testing_modernization",
                             to=to, actor=actor, artifact=artifact,
                             fields={"equivalence_verdict": verdict, "perf_verdict": perf_verdict})


# ── Migration Development ────────────────────────────────────────────────────

async def migration_started(db: AsyncSession, *, project_id: str, module_id: str, target_branch: str,
                            target_path: Optional[str], actor: Optional[str]) -> ModernizationModule:
    return await _transition(db, project_id=project_id, module_id=module_id, agent="development_modernization",
                             to="migrating", actor=actor,
                             fields={"target_branch": target_branch, "target_path": target_path})


async def pr_opened(db: AsyncSession, *, project_id: str, module_id: str, pr_url: str,
                    actor: Optional[str], artifact: ArtifactRef) -> ModernizationModule:
    """A new pull request (or a rework push) clears the previous round's verdicts."""
    return await _transition(db, project_id=project_id, module_id=module_id, agent="development_modernization",
                             to="in_review", actor=actor, artifact=artifact,
                             fields={"pr_url": pr_url, "review_verdict": None, "security_verdict": None})


# ── Migration Review and Security (concurrent) ───────────────────────────────

async def _record_verdict(db: AsyncSession, *, project_id: str, module_id: str, agent: str, column: str,
                          verdict: str, good: set[str], bad: set[str], actor: Optional[str],
                          artifact: ArtifactRef) -> ModernizationModule:
    if verdict not in good | bad | {"needs_discussion"}:
        raise LedgerRefused(f"unknown {column} {verdict!r}")
    row = await _locked(db, project_id, module_id)
    if row.state != "in_review":
        raise LedgerRefused(f"{module_id} is {row.state}; review and security verdicts are recorded while it is in review")
    setattr(row, column, verdict)
    review_bad = row.review_verdict in REVIEW_BAD
    security_bad = row.security_verdict in SECURITY_BAD
    if review_bad or security_bad:
        row.rejection_count = (row.rejection_count or 0) + 1
        if row.rejection_count >= MAX_REJECTIONS:
            row.blocked_from, row.blocked_reason = row.state, (
                f"Rejected {row.rejection_count} times (limit {MAX_REJECTIONS}); escalated to the Architect.")
            _move(row, "blocked", agent=agent, actor=actor, reason=row.blocked_reason, artifact=artifact)
        else:
            _move(row, "migrating", agent=agent, actor=actor, artifact=artifact)
    elif row.review_verdict in REVIEW_GOOD and row.security_verdict in SECURITY_GOOD:
        _move(row, "verifying", agent=agent, actor=actor, artifact=artifact)
    else:  # the other half has not reported yet, or a trade-off needs the Architect
        row.history = [*row.history, _entry(frm=row.state, to=row.state, agent=agent, actor=actor,
                                             artifact=artifact, note=f"{column}: {verdict}")]
    await db.flush()
    return row


async def review_submitted(db: AsyncSession, *, project_id: str, module_id: str, verdict: str,
                           actor: Optional[str], artifact: ArtifactRef) -> ModernizationModule:
    return await _record_verdict(db, project_id=project_id, module_id=module_id,
                                 agent="code_review_modernization", column="review_verdict", verdict=verdict,
                                 good=REVIEW_GOOD, bad=REVIEW_BAD, actor=actor, artifact=artifact)


async def security_submitted(db: AsyncSession, *, project_id: str, module_id: str, verdict: str,
                             actor: Optional[str], artifact: ArtifactRef) -> ModernizationModule:
    return await _record_verdict(db, project_id=project_id, module_id=module_id,
                                 agent="security_modernization", column="security_verdict", verdict=verdict,
                                 good=SECURITY_GOOD, bad=SECURITY_BAD, actor=actor, artifact=artifact)


# ── Cutover ──────────────────────────────────────────────────────────────────

async def cut_over(db: AsyncSession, *, project_id: str, module_id: str, actor: Optional[str],
                   artifact: ArtifactRef) -> ModernizationModule:
    return await _transition(db, project_id=project_id, module_id=module_id, agent="deployment_modernization",
                             to="cut_over", actor=actor, artifact=artifact, fields={"cutover_state": "cut_over"})


async def rolled_back(db: AsyncSession, *, project_id: str, module_id: str, actor: Optional[str],
                      artifact: ArtifactRef) -> ModernizationModule:
    return await _transition(db, project_id=project_id, module_id=module_id, agent="deployment_modernization",
                             to="verified", actor=actor, artifact=artifact, fields={"cutover_state": "rolled_back"})


async def retired(db: AsyncSession, *, project_id: str, module_id: str, actor: Optional[str],
                  artifact: ArtifactRef, decommission_date=None) -> ModernizationModule:
    return await _transition(db, project_id=project_id, module_id=module_id, agent="deployment_modernization",
                             to="retired", actor=actor, artifact=artifact,
                             fields={"cutover_state": "decommissioned", "decommission_date": decommission_date})


# ── blocking, unblocking, reopening ──────────────────────────────────────────

def _need_reason(reason: Optional[str]) -> str:
    if not reason or not reason.strip():
        raise LedgerRefused("a reason is required")
    return reason.strip()


async def block(db: AsyncSession, *, project_id: str, module_id: str, agent: str, reason: str,
                actor: Optional[str]) -> ModernizationModule:
    """Any Track 3 agent (manual tier, missing input) or a person may block a module, with a reason."""
    reason = _need_reason(reason)
    if agent not in TRACK3_AGENTS and agent not in {f"person:{r}" for r in PERSON_ROLES}:
        raise LedgerRefused(f"{agent} cannot block a module")
    row = await _locked(db, project_id, module_id)
    if row.state in ("blocked", "retired"):
        raise LedgerRefused(f"{module_id} is already {row.state}")
    row.blocked_from, row.blocked_reason = row.state, reason
    _move(row, "blocked", agent=agent, actor=actor, reason=reason)
    await db.flush()
    return row


async def unblock(db: AsyncSession, *, project_id: str, module_id: str, role: str, reason: str,
                  actor: Optional[str], to_migrating: bool = False) -> ModernizationModule:
    """A person — the Architect or a Project Admin — returns a blocked module to where it was
    (or to `migrating` for rework), with a reason."""
    reason = _need_reason(reason)
    if role not in PERSON_ROLES:
        raise LedgerRefused(f"only an Architect or a Project Admin unblocks a module, not {role}")
    row = await _locked(db, project_id, module_id)
    if row.state != "blocked":
        raise LedgerRefused(f"{module_id} is {row.state}, not blocked")
    to = "migrating" if to_migrating else row.blocked_from
    _move(row, to, agent=f"person:{role}", actor=actor, reason=reason)
    row.blocked_from, row.blocked_reason = None, None
    row.rejection_count = 0
    await db.flush()
    return row


async def reopen(db: AsyncSession, *, project_id: str, module_id: str, role: str, reason: str,
                 actor: Optional[str]) -> ModernizationModule:
    """Send a verified or cut-over module back to `migrating` (research §12.4): a person, a reason."""
    reason = _need_reason(reason)
    if role not in PERSON_ROLES:
        raise LedgerRefused(f"only an Architect or a Project Admin reopens a module, not {role}")
    row = await _locked(db, project_id, module_id)
    if row.state not in REOPENABLE:
        raise LedgerRefused(f"{module_id} is {row.state}; only a verified or cut-over module is reopened")
    _move(row, "migrating", agent=f"person:{role}", actor=actor, reason=reason)
    await db.flush()
    return row


# ── reading ──────────────────────────────────────────────────────────────────

async def list_modules(db: AsyncSession, project_id: str) -> list[ModernizationModule]:
    return list((await db.execute(
        select(ModernizationModule).where(ModernizationModule.project_id == project_id)
        .order_by(ModernizationModule.module_id)
    )).scalars().all())


def as_dict(row: ModernizationModule) -> dict:
    return {
        "moduleId": row.module_id, "moduleName": row.module_name, "legacyPath": row.legacy_path,
        "tier": row.tier, "riskScore": row.risk_score, "patterns": row.patterns,
        "contractIds": row.contract_ids, "adrIds": row.adr_ids, "wave": row.wave, "ecIds": row.ec_ids,
        "baselineIds": row.baseline_ids, "targetBranch": row.target_branch, "prUrl": row.pr_url,
        "reviewVerdict": row.review_verdict, "securityVerdict": row.security_verdict,
        "equivalenceVerdict": row.equivalence_verdict, "perfVerdict": row.perf_verdict,
        "cutoverState": row.cutover_state,
        "decommissionDate": row.decommission_date.isoformat() if row.decommission_date else None,
        "state": row.state, "blockedFrom": row.blocked_from, "blockedReason": row.blocked_reason,
        "rejectionCount": row.rejection_count,
        "stateChangedAt": row.state_changed_at.isoformat() if row.state_changed_at else None,
        "stateChangedBy": row.state_changed_by, "history": row.history,
    }

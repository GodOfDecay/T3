"""ApprovalSlaSweeper — tells a project's Project Admins when a Code Modernization version
has waited past its SLA (Track 3, research §12.2).

Every Track 3 stage has an `sla_hours` (`config/agent_registry`, default 48). A version
still a DRAFT that long is either blocking the next stage or waiting on an owner who is not
there, and the Project Admin is the fallback who can act: approve it in the owner's place
(with a reason) or chase the owner. On a project in "after_sla" fallback mode this is also
the moment they become ABLE to act (`fallback_approval.decide`).

ONCE PER VERSION. `artifact_versions.sla_notified_at` (0070) records that the notification
went out; the sweep never repeats it. A version superseded, published or rejected before the
sweep sees it is simply not a draft any more.

Addressed to the `project_admin` role scoped to the project — never broadcast — through the
same `notifications.emit` every other bell item uses, and to the tenant's Slack/Teams via
`notify_all` (best-effort, never raises).

Runs over every tenant, each through its own tenant session (see `sweep_once`). Usage
(process_api lifespan):
    task = asyncio.create_task(ApprovalSlaSweeper().run())
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = float(os.environ.get("APPROVAL_SLA_SWEEP_INTERVAL_SECONDS", "900"))
#: The FIRST sweep waits this long after startup. Not at boot, on purpose: a sweep visits every
#: tenant, and a process that is shut down seconds after starting (a test client, a crash-looping
#: pod) would otherwise be cancelled mid-sweep on every start. An SLA measured in hours loses
#: nothing to a one-minute delay.
FIRST_SWEEP_DELAY_SECONDS = float(os.environ.get("APPROVAL_SLA_FIRST_SWEEP_DELAY_SECONDS", "60"))

#: Backend stage → the page's route segment (frontend `lib/agents.ts::phaseRoute`).
STAGE_ROUTE = {
    "requirements_modernization": "requirements-modernization",
    "discovery": "discovery",
    "design_modernization": "target-architecture",
    "strategy": "strategy",
    "testing_modernization": "equivalence-testing",
    "development_modernization": "migration-development",
    "code_review_modernization": "migration-review",
    "security_modernization": "modernization-security",
    "deployment_modernization": "cutover",
    "documentation_modernization": "cutover-pack",
}


class ApprovalSlaSweeper:
    async def sweep_once(self, now: Optional[datetime] = None) -> list[dict]:
        """Notify for every Track 3 draft past its SLA not yet notified. Returns what was sent."""
        from shared.db import get_db_session_superuser  # noqa: PLC0415

        now = now or datetime.now(timezone.utc)
        # TENANT BY TENANT. The application role is not BYPASSRLS, and `artifact_versions` and
        # `projects` are FORCE RLS — a single cross-tenant query through the superuser
        # session sees no rows at all. `organizations` is the tenant list (not RLS-scoped).
        async with get_db_session_superuser() as s:
            tenants = [str(r[0]) for r in await s.execute(text("SELECT id FROM organizations"))]
        sent: list[dict] = []
        for tenant_id in tenants:
            try:
                sent.extend(await self._sweep_tenant(tenant_id, now))
            except Exception:  # noqa: BLE001 — one tenant's failure must not stop the others
                logger.warning("ApprovalSlaSweeper: tenant sweep failed", exc_info=True)
        for item in sent:
            await self._external(item)
        if sent:
            logger.info("ApprovalSlaSweeper: %d version(s) past SLA notified", len(sent))
        return sent

    async def _sweep_tenant(self, tenant_id: str, now: datetime) -> list[dict]:
        from shared.db import get_db_session_for_tenant  # noqa: PLC0415
        from shared.services import notifications  # noqa: PLC0415
        from shared.services.fallback_approval import _sla_hours  # noqa: PLC0415
        from shared.services.repository_roles import TRACK3_STAGES  # noqa: PLC0415

        sent: list[dict] = []
        async with get_db_session_for_tenant(tenant_id) as s:
            rows = (await s.execute(text(
                "SELECT v.id, v.project_id, v.stage, v.version, v.created_at, p.display_name "
                "FROM artifact_versions v JOIN projects p ON p.id = v.project_id "
                "WHERE v.status = 'draft' AND v.sla_notified_at IS NULL AND v.stage = ANY(:stages) "
                "AND p.track = 'modernization' AND NOT p.archived "
                "ORDER BY v.created_at FOR UPDATE OF v SKIP LOCKED"),
                {"stages": list(TRACK3_STAGES)})).mappings().all()
            for r in rows:
                hours = _sla_hours(r["stage"])
                if now - r["created_at"] < timedelta(hours=hours):
                    continue
                label = r["stage"].replace("_", " ")
                title = f"{label.capitalize()} v{r['version']} has waited {hours}h for approval"
                body = (f"On {r['display_name']}, {label} v{r['version']} is still a draft past its {hours}-hour SLA. "
                        "A Project Admin who did not produce it may approve it in the owner's place, with a reason, "
                        "or chase the owner.")
                href = f"/projects/{r['project_id']}/{STAGE_ROUTE.get(r['stage'], r['stage'])}"
                delivered = await notifications.emit(
                    s, tenant_id=tenant_id, kind="approval_sla_passed", title=title, body=body, href=href,
                    recipient_role="project_admin", recipient_scope_kind="project",
                    recipient_scope_id=str(r["project_id"]), project_id=str(r["project_id"]),
                )
                if delivered is None:
                    # `emit` never raises; None means it was not written. Leave the version
                    # unstamped so the next sweep tries again rather than losing it.
                    continue
                await s.execute(text("UPDATE artifact_versions SET sla_notified_at = :now WHERE id = :id"),
                                {"now": now, "id": r["id"]})
                sent.append({"tenant_id": tenant_id, "project_id": str(r["project_id"]),
                             "stage": r["stage"], "version": r["version"], "title": title, "href": href})
        return sent

    async def _external(self, item: dict) -> None:
        try:
            from shared.services.notify_dispatch import notify_all  # noqa: PLC0415

            await notify_all(item["tenant_id"], item["title"], title="Approval SLA passed", link_url=item["href"])
        except Exception:  # noqa: BLE001 — best-effort, like every notification
            logger.debug("ApprovalSlaSweeper: external notify failed (swallowed)", exc_info=True)

    async def run(self) -> None:
        await asyncio.sleep(FIRST_SWEEP_DELAY_SECONDS)
        while True:
            try:
                await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.warning("ApprovalSlaSweeper sweep failed; retrying next interval", exc_info=True)
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)

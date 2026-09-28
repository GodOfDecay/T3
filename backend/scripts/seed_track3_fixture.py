"""Seed the ClaimTrack Code Modernization project — LOCAL DEVELOPMENT ONLY.

ClaimTrack is the simulated customer scenario Track 3 is built against (an insurer's legacy
claims system). This puts one Track 3 project on the dev database with enough in it to click
through the Programme board, the repository settings and the sign-off fallback without
running any agent:

  project      "ClaimTrack Modernization", track `modernization`, in the Payments unit
  roster       the dev personas (`seed_dev_personas`) bound to it at project scope: two Project
               Admins (so the two-PA warning is clear), a BA, an Architect, a QA, a Developer,
               a Security Engineer and a DevOps Engineer
  repositories an ILLUSTRATIVE legacy and target (placeholders — nothing is pulled or pushed)
  ledger       six modules across designed / sequenced / baselined / migrating / blocked

WRITES THROUGH THE ORDINARY PATHS: `grant_role`, `repository_roles.set_role` and the ledger's
own transition functions, so every rule they enforce applies. If this script can create a
state, the product could have.

IDEMPOTENT. The project is matched by name, bindings by `grant_role`'s upsert, repositories by
role; the ledger is seeded only when the project has no modules (re-approving a design would
append history, so it is not repeated).

Same guard as `seed_dev_personas` (localhost database, dev environment). Run the personas
seed first — this binds those accounts and creates none.

    python -m scripts.seed_track3_fixture
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import uuid as _uuid

from sqlalchemy import text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.seed_dev_personas import _guard, _org_id  # noqa: E402
from shared.authz.grant import grant_role  # noqa: E402
from shared.db import get_db_session_for_tenant, get_db_session_superuser  # noqa: E402
from shared.services import modernization_ledger as ledger  # noqa: E402
from shared.services import repository_roles as rr  # noqa: E402

PROJECT_NAME = "ClaimTrack Modernization"
UNIT_SLUG = "payments"

# Placeholders: the scenario has no real repository yet. Replace them in Settings → Code
# Modernization when there is one.
LEGACY_URL = "https://github.com/claimtrack-example/claimtrack-legacy"
TARGET_URL = "https://github.com/claimtrack-example/claimtrack-modern"

ROSTER = [
    ("ana@abcbank.com", "project_admin"),
    ("sofia@abcbank.com", "project_admin"),
    ("priya@abcbank.com", "ba"),
    ("iris@abcbank.com", "architect"),
    ("ingrid@abcbank.com", "qa"),
    ("diego@abcbank.com", "developer"),
    ("hana@abcbank.com", "security_engineer"),
    ("lena@abcbank.com", "devops_engineer"),
]

MODULES = [
    {"module_id": "M-01", "module_name": "Policy lookup", "legacy_path": "src/policy", "tier": "low", "risk_score": 2},
    {"module_id": "M-02", "module_name": "Claim intake", "legacy_path": "src/intake", "tier": "medium", "risk_score": 5},
    {"module_id": "M-03", "module_name": "Adjudication rules", "legacy_path": "src/adjudication", "tier": "high",
     "risk_score": 9},
    {"module_id": "M-04", "module_name": "Payments bridge", "legacy_path": "src/payments", "tier": "high",
     "risk_score": 8},
    {"module_id": "M-05", "module_name": "Correspondence", "legacy_path": "src/letters", "tier": "low", "risk_score": 3},
    {"module_id": "M-06", "module_name": "Reporting batch", "legacy_path": "batch/reports", "tier": "medium",
     "risk_score": 4},
]


async def _project(org_id: str) -> str:
    async with get_db_session_superuser() as s:
        unit = (await s.execute(text("SELECT id FROM workspaces WHERE organization_id = :o AND slug = :s"),
                                {"o": org_id, "s": UNIT_SLUG})).first()
    if unit is None:
        sys.exit(f"No {UNIT_SLUG!r} unit — run `python -m scripts.seed_dev_personas` first.")
    async with get_db_session_for_tenant(org_id) as s:
        row = (await s.execute(text("SELECT id FROM projects WHERE display_name = :n"), {"n": PROJECT_NAME})).first()
        if row is not None:
            return str(row.id)
        new_id = str(_uuid.uuid4())
        await s.execute(text(
            "INSERT INTO projects (id, workspace_id, tenant_id, display_name, provider_kind, track) "
            "VALUES (CAST(:i AS uuid), CAST(:w AS uuid), CAST(:t AS uuid), :n, 'github', 'modernization')"),
            {"i": new_id, "w": str(unit.id), "t": org_id, "n": PROJECT_NAME})
    print(f"  + project {PROJECT_NAME}")
    return new_id


async def _roster(org_id: str, project_id: str) -> str:
    """Bind the personas; returns the first Project Admin's id (the fixture's actor)."""
    actor = ""
    async with get_db_session_superuser() as s:
        # This organization's accounts only, and only those with an email (`grant_role`
        # creates email-less rows for ids it has not seen).
        users = {r.email.lower(): str(r.id) for r in await s.execute(text(
            "SELECT id, email FROM users WHERE tenant_id = :t AND email IS NOT NULL"), {"t": org_id})}
    for email, role in ROSTER:
        uid = users.get(email)
        if uid is None:
            sys.exit(f"No account {email} — run `python -m scripts.seed_dev_personas` first.")
        await grant_role(uid, project_id, role, tenant_id=org_id, scope_kind="project")
        actor = actor or uid
        print(f"  = {email} is {role} on {PROJECT_NAME}")
    return actor


async def _repositories(org_id: str, project_id: str, actor: str) -> None:
    async with get_db_session_for_tenant(org_id) as s:
        for role, url in (("legacy", LEGACY_URL), ("target", TARGET_URL)):
            await rr.set_role(s, tenant_id=org_id, project_id=project_id, role=role, url=url, branch="main",
                              actor=actor)
    print("  = legacy and target repositories set (placeholders)")


async def _ledger(org_id: str, project_id: str, actor: str) -> None:
    async with get_db_session_for_tenant(org_id) as s:
        if await ledger.list_modules(s, project_id):
            print("  = ledger already has modules; left as it is")
            return
        await ledger.design_approved(s, tenant_id=org_id, project_id=project_id, modules=MODULES, actor=actor,
                                     artifact=ledger.ArtifactRef("design_modernization", 1))
        plan = ledger.ArtifactRef("strategy", 1)
        for mid, wave in (("M-01", "W1"), ("M-05", "W1"), ("M-02", "W2"), ("M-06", "W2")):
            await ledger.plan_approved(s, project_id=project_id, module_id=mid, wave=wave, ec_ids=[f"EC-{mid}-1"],
                                       actor=actor, artifact=plan)
        baseline = ledger.ArtifactRef("testing_modernization", 1)
        for mid in ("M-01", "M-05"):
            await ledger.baseline_accepted(s, project_id=project_id, module_id=mid, baseline_ids=[f"GB-{mid}"],
                                           actor=actor, artifact=baseline)
        await ledger.migration_started(s, project_id=project_id, module_id="M-01", target_branch="migrate/m-01",
                                       target_path="services/policy", actor=actor)
        await ledger.block(s, project_id=project_id, module_id="M-06", agent="testing_modernization",
                           reason="The nightly batch has no captured outputs to baseline against yet.", actor=actor)
    print("  + ledger: 6 modules (designed, sequenced, baselined, migrating, blocked)")


async def main() -> None:
    _guard()
    org_id = await _org_id()
    print(f"Seeding the ClaimTrack Track 3 fixture into {org_id}")
    project_id = await _project(org_id)
    actor = await _roster(org_id, project_id)
    await _repositories(org_id, project_id, actor)
    await _ledger(org_id, project_id, actor)
    print(f"Done. Open /projects/{project_id}/modernization")


if __name__ == "__main__":
    asyncio.run(main())

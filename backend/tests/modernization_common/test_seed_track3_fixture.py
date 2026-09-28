"""The ClaimTrack dev fixture (scripts/seed_track3_fixture.py) builds what it says, through the
ordinary paths, and running it twice changes nothing. Real database (`sdlc_product_test`),
against a throwaway organization; the accounts it binds are made here with unique emails."""
from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy import text

from scripts import seed_track3_fixture as seed
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import fallback_approval as fb
from shared.services import modernization_ledger as ledger
from shared.services import repository_roles as rr

pytestmark = pytest.mark.usefixtures("purge_created_orgs")


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def org(monkeypatch):
    org = str(_uuid.uuid4())
    tag = org[:8]
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Seed')"),
                        {"i": org, "s": f"seed-{tag}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'payments', 'Payments')"), {"i": str(_uuid.uuid4()), "o": org})
        roster = []
        for email, role in seed.ROSTER:
            unique = f"{tag}-{email}"
            await s.execute(text("INSERT INTO users (id, email, password_hash, tenant_id, active) "
                                 "VALUES (:i, :e, 'x', :t, true)"), {"i": str(_uuid.uuid4()), "e": unique, "t": org})
            roster.append((unique, role))
    monkeypatch.setattr(seed, "ROSTER", roster)
    return org


async def _run(org):
    project = await seed._project(org)
    actor = await seed._roster(org, project)
    await seed._repositories(org, project, actor)
    await seed._ledger(org, project, actor)
    return project


async def test_the_fixture_builds_the_claimtrack_project_and_is_idempotent(org):
    project = await _run(org)
    assert await _run(org) == project
    async with get_db_session_for_tenant(org) as s:
        assert (await s.execute(text("SELECT count(*), min(track) FROM projects WHERE display_name = :n"),
                                {"n": seed.PROJECT_NAME})).one() == (1, "modernization")
        states = {m.module_id: m.state for m in await ledger.list_modules(s, project)}
        roles = await rr.get_roles(s, project)
        warnings = await fb.staffing_warnings(s, tenant_id=org, project_id=project)
        bindings = (await s.execute(text(
            "SELECT count(*) FROM role_bindings WHERE scope_kind = 'project' AND scope_id = CAST(:p AS uuid) "
            "AND status = 'active'"), {"p": project})).scalar()
    assert states == {"M-01": "migrating", "M-02": "sequenced", "M-03": "designed", "M-04": "designed",
                      "M-05": "baselined", "M-06": "blocked"}
    assert (roles["legacy"].url, roles["target"].url) == (seed.LEGACY_URL, seed.TARGET_URL)
    assert bindings == len(seed.ROSTER)
    assert not any("Project Admin(s)" in w for w in warnings), warnings

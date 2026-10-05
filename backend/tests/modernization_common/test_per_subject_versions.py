"""Track 3's per-module stages approve each module independently (found walking a two-module workflow before
Phase J). One stage, one published version was the rule; Migration Development, Review and Security keep ONE
VERSION PER MODULE, so accepting M-02's record superseded M-01's (M-01 could no longer be pushed or reviewed),
and M-01's older record could never be accepted after M-02's newer one. Equivalence Testing keeps the
baseline and each module's verification apart: an accepted verification must never hide the baseline.
Every other stage is unchanged (one subject). Real database.
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy import text

from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import artifact_versions as svc

pytestmark = pytest.mark.usefixtures("purge_created_orgs")


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def proj():
    org, bu, proj = (str(_uuid.uuid4()) for _ in range(3))
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Subj')"),
                        {"i": org, "s": f"subj-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) VALUES (:i, :o, 'u', 'U')"),
                        {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'P', 'modernization')"), {"i": proj, "w": bu, "t": org})
    return org, proj


async def _version(org, proj, stage, payload):
    async with get_db_session_for_tenant(org) as s:
        return (await svc.snapshot_stage_payload(s, tenant_id=org, project_id=proj, stage=stage, payload=payload,
                                                 produced_by="u-maker")).version


async def _publish(org, proj, stage, v):
    async with get_db_session_for_tenant(org) as s:
        return (await svc.publish_version(s, tenant_id=org, project_id=proj, stage=stage, version=v,
                                          published_by="u-checker")).status


async def _status(org, proj, stage, v):
    async with get_db_session_for_tenant(org) as s:
        return (await svc.get_version(s, proj, stage, v)).status


@pytest.mark.parametrize("stage", ["development_modernization", "code_review_modernization", "security_modernization"])
async def test_each_module_is_accepted_on_its_own(proj, stage):
    org, p = proj
    m1 = await _version(org, p, stage, {"module_id": "M-01", "n": 1})
    m2 = await _version(org, p, stage, {"module_id": "M-02", "n": 1})
    assert await _publish(org, p, stage, m2) == "published"
    assert await _publish(org, p, stage, m1) == "published", "an older version of ANOTHER module is not going backwards"
    assert await _status(org, p, stage, m2) == "published", "accepting M-01 does not supersede M-02"
    m1b = await _version(org, p, stage, {"module_id": "M-01", "n": 2})
    assert await _publish(org, p, stage, m1b) == "published"
    assert await _status(org, p, stage, m1) == "superseded", "the same module's newer version supersedes it"
    assert await _status(org, p, stage, m2) == "published"
    m1c = await _version(org, p, stage, {"module_id": "M-01", "n": 3})
    m1d = await _version(org, p, stage, {"module_id": "M-01", "n": 4})
    await _publish(org, p, stage, m1d)
    with pytest.raises(svc.PublicationRefused, match="would supersede newer approved work"):
        await _publish(org, p, stage, m1c)


async def test_a_verification_never_hides_the_baseline(proj):
    org, p = proj
    st = "testing_modernization"
    base = await _version(org, p, st, {"mode": "baseline", "placements": []})
    await _publish(org, p, st, base)
    verify = await _version(org, p, st, {"mode": "verify", "module_id": "M-01"})
    assert await _publish(org, p, st, verify) == "published"
    assert await _status(org, p, st, base) == "published"
    async with get_db_session_for_tenant(org) as s:
        assert (await svc.latest_published(s, p, st)).version == base, "readers of the stage mean the baseline"
        assert (await svc.latest_published(s, p, st, subject="verify:M-01")).version == verify
        assert (await svc.latest_published(s, p, st, subject=None)).version == verify
    base2 = await _version(org, p, st, {"mode": "baseline", "placements": []})
    await _publish(org, p, st, base2)
    assert (await _status(org, p, st, base), await _status(org, p, st, verify)) == ("superseded", "published")


async def test_other_stages_keep_one_published_version(proj):
    org, p = proj
    v1 = await _version(org, p, "strategy", {"module_id": "M-01"})
    v2 = await _version(org, p, "strategy", {"module_id": "M-02"})
    await _publish(org, p, "strategy", v1)
    await _publish(org, p, "strategy", v2)
    assert await _status(org, p, "strategy", v1) == "superseded"
    assert svc.subject_of("strategy", {"module_id": "M-01"}) is None

"""Phase C independent review (build-log Entry 8) — one guarding test per fixed finding.

  #1  a second publish never rewrites who approved in which capacity
  #2  an expired binding is not a role (fallback, staffing)
  #3  restoring someone's work does not let them approve it
  #5  "target is not legacy" survives case and the visualstudio.com host form
  #6  approval-settings and repository changes are audited
  #7  Track 3 reject is scoped to the project's owner role / Project Admin / producer
  #8  restore/compare/staleness exist only for Track 3 stages on Track 3 projects; restore needs reach
  #9  a version read by consumption grant is pinned as "granted", not "published"
  #10 an input rejected after being built on makes the version stale
  #11 an owner who produced the version does not make the role "staffed"
  #12 the SLA sweep does not mark a version notified when the notification was not written

Real database (`sdlc_product_test`).
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config.auth.jwt import create_access_token
from shared.authz.grant import grant_role
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import fallback_approval as fb
from shared.services import repository_roles as rr
from shared.services import version_lineage as lineage
from shared.services.artifact_versions import publish_version, reject_version, snapshot_stage_payload

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

STAGE = "requirements_modernization"
APPROVE = [f"artifact:approve_{STAGE}", "artifact:view"]


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


async def _project(org, bu, track="modernization"):
    proj = str(_uuid.uuid4())
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'ClaimTrack', :tr)"), {"i": proj, "w": bu, "t": org, "tr": track})
    return proj


@pytest.fixture
async def env():
    org, bu = str(_uuid.uuid4()), str(_uuid.uuid4())
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Fixes')"),
                        {"i": org, "s": f"fix-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    return {"org": org, "bu": bu, "project": await _project(org, bu)}


async def _grant(env, user, role, project=None):
    await grant_role(user, project or env["project"], role, tenant_id=env["org"], scope_kind="project")


def _client(env, user, perms):
    import process_api
    return TestClient(process_api.app), {"Authorization": "Bearer " + create_access_token(
        user_id=user, tenant_id=env["org"], permissions=perms)}


async def _draft(env, produced_by, stage=STAGE, project=None, payload=None):
    async with get_db_session_for_tenant(env["org"]) as s:
        return (await snapshot_stage_payload(s, tenant_id=env["org"], project_id=project or env["project"],
                                             stage=stage, payload=payload or {"n": str(_uuid.uuid4())},
                                             produced_by=produced_by)).version


async def _row(env, v, stage=STAGE):
    async with get_db_session_for_tenant(env["org"]) as s:
        return (await s.execute(text(
            "SELECT status, approved_as, fallback_reason, published_by, built_from FROM artifact_versions "
            "WHERE project_id = :p AND stage = :s AND version = :v"),
            {"p": env["project"], "s": stage, "v": v})).mappings().one()


def _publish_url(env, v, stage=STAGE):
    return f"/artifact-versions/{env['project']}/stages/{stage}/versions/{v}/publish"


# ── #1 ───────────────────────────────────────────────────────────────────────

async def test_a_second_publish_does_not_rewrite_the_approval_record(env):
    await _grant(env, "u-pa", "project_admin")
    await _grant(env, "u-ba2", "ba")
    v = await _draft(env, "u-ba")
    pa, pa_hdr = _client(env, "u-pa", APPROVE)
    assert pa.post(_publish_url(env, v), json={"fallbackReason": "BA on leave"}, headers=pa_hdr).status_code == 200
    owner, owner_hdr = _client(env, "u-ba2", APPROVE)
    r = owner.post(_publish_url(env, v), json={}, headers=owner_hdr)
    assert r.status_code == 200, r.text
    row = await _row(env, v)
    assert (row["approved_as"], row["fallback_reason"], row["published_by"]) == (
        "fallback:project_admin", "BA on leave", "u-pa")


# ── #2 ───────────────────────────────────────────────────────────────────────

async def _expire(env, user, role):
    async with get_db_session_for_tenant(env["org"]) as s:
        await s.execute(text("UPDATE role_bindings SET expires_at = now() - interval '1 hour' "
                             "WHERE user_id = :u AND role_name = :r AND scope_id = CAST(:p AS uuid)"),
                        {"u": user, "r": role, "p": env["project"]})


async def test_an_expired_project_admin_binding_is_no_fallback(env):
    await _grant(env, "u-pa", "project_admin")
    await _expire(env, "u-pa", "project_admin")
    async with get_db_session_for_tenant(env["org"]) as s:
        assert await fb.project_roles(s, tenant_id=env["org"], project_id=env["project"], user_id="u-pa") == set()
    v = await _draft(env, "u-ba")
    client, hdr = _client(env, "u-pa", APPROVE)
    r = client.post(_publish_url(env, v), json={"fallbackReason": "x"}, headers=hdr)
    assert r.status_code in (403, 404), r.text
    assert (await _row(env, v))["status"] == "draft"


async def test_an_expired_owner_does_not_staff_the_role(env):
    await _grant(env, "u-ba2", "ba")
    await _expire(env, "u-ba2", "ba")
    async with get_db_session_for_tenant(env["org"]) as s:
        assert not await fb.owner_staffed(s, tenant_id=env["org"], project_id=env["project"], stage=STAGE)
        warnings = await fb.staffing_warnings(s, tenant_id=env["org"], project_id=env["project"])
    assert any("ba" in w for w in warnings if w.startswith("No one"))


# ── #3 ───────────────────────────────────────────────────────────────────────

async def test_restoring_someones_work_does_not_let_them_approve_it(env):
    await _grant(env, "u-ba", "ba")
    await _grant(env, "u-ba2", "ba")
    await _grant(env, "u-pa", "project_admin")
    await _draft(env, "u-ba", payload={"goal": "one"})
    await _draft(env, "u-ba2", payload={"goal": "two"})
    async with get_db_session_for_tenant(env["org"]) as s:
        v3 = (await lineage.restore_version(s, tenant_id=env["org"], project_id=env["project"], stage=STAGE,
                                            version=1, restorer="u-ba2", reason="back to one")).version
        assert await lineage.producers_of(s, env["project"], STAGE, v3) == {"u-ba", "u-ba2"}
    client, hdr = _client(env, "u-ba", APPROVE)
    r = client.post(_publish_url(env, v3), json={}, headers=hdr)
    assert r.status_code == 403 and "you produced" in r.json()["detail"]
    pa, pa_hdr = _client(env, "u-pa", APPROVE)
    assert pa.post(_publish_url(env, v3), json={"fallbackReason": "both BAs produced it"},
                   headers=pa_hdr).status_code == 200


# ── #5 ───────────────────────────────────────────────────────────────────────

def test_normalize_is_case_and_host_form_insensitive():
    assert rr.normalize("https://github.com/Org/Legacy.git") == rr.normalize("https://github.com/org/legacy")
    assert rr.normalize("https://contoso.visualstudio.com/Claims/_git/Legacy") == \
        rr.normalize("https://dev.azure.com/contoso/claims/_git/legacy") == \
        "https://dev.azure.com/contoso/claims/_git/legacy"


async def test_the_target_cannot_be_the_legacy_by_spelling(env):
    async with get_db_session_for_tenant(env["org"]) as s:
        await rr.set_role(s, tenant_id=env["org"], project_id=env["project"], role="legacy",
                          url="https://github.com/Org/Legacy", branch="main", actor="u-pa")
        with pytest.raises(rr.RepositoryRefused, match="cannot be the legacy"):
            await rr.set_role(s, tenant_id=env["org"], project_id=env["project"], role="target",
                              url="https://github.com/org/legacy", branch="main", actor="u-pa")


# ── #6 ───────────────────────────────────────────────────────────────────────

async def test_settings_and_repository_changes_are_audited(env, monkeypatch):
    from shared.audit.service import audit_service
    seen = []

    async def capture(payload):
        seen.append(payload)

    monkeypatch.setattr(audit_service, "emit", capture)
    await _grant(env, "u-pa", "project_admin")
    client, hdr = _client(env, "u-pa", ["artifact:view", "project:update"])
    base = f"/modernization-programme/{env['project']}"
    assert client.put(f"{base}/approval-settings", json={"fallbackMode": "always", "policy": "pilot"},
                      headers=hdr).status_code == 200
    assert client.put(f"{base}/repositories/legacy", json={"url": "https://github.com/c/legacy"},
                      headers=hdr).status_code == 200
    events = [(e.event_type, e.actor_id, e.resource_id) for e in seen if e.event_type.startswith("modernization.")]
    assert events == [("modernization.approval_settings_changed", "u-pa", env["project"]),
                      ("modernization.repository_set", "u-pa", env["project"])]
    change = next(e for e in seen if e.event_type == "modernization.approval_settings_changed").payload
    assert change == {"before": {"fallbackMode": "always", "policy": "standard"},
                      "after": {"fallbackMode": "always", "policy": "pilot"}}


# ── #7 ───────────────────────────────────────────────────────────────────────

def _reject_url(env, v):
    return f"/artifact-versions/{env['project']}/stages/{STAGE}/versions/{v}/reject"


async def test_a_ba_of_another_project_cannot_reject_here(env):
    other = await _project(env["org"], env["bu"])
    await _grant(env, "u-ba-elsewhere", "ba", project=other)
    await _grant(env, "u-ba-elsewhere", "developer")
    v = await _draft(env, "u-ba")
    client, hdr = _client(env, "u-ba-elsewhere", APPROVE)
    r = client.post(_reject_url(env, v), json={"reason": "no"}, headers=hdr)
    assert r.status_code == 403 and "of this project" in r.json()["detail"]
    assert (await _row(env, v))["status"] == "draft"


async def test_the_owner_role_and_a_project_admin_may_reject_but_not_the_producer(env):
    await _grant(env, "u-ba2", "ba")
    await _grant(env, "u-ba", "ba")
    await _grant(env, "u-pa", "project_admin")
    v1 = await _draft(env, "u-ba")
    client, hdr = _client(env, "u-ba2", APPROVE)
    assert client.post(_reject_url(env, v1), json={"reason": "scope wrong"}, headers=hdr).status_code == 200
    v2 = await _draft(env, "u-ba")
    pa, pa_hdr = _client(env, "u-pa", APPROVE)
    assert pa.post(_reject_url(env, v2), json={"reason": "duplicate"}, headers=pa_hdr).status_code == 200
    v3 = await _draft(env, "u-ba")
    own, own_hdr = _client(env, "u-ba", APPROVE)
    r = own.post(_reject_url(env, v3), json={"reason": "withdrawn"}, headers=own_hdr)
    assert r.status_code == 403 and "cannot also decide" in r.json()["detail"]


# ── #8 ───────────────────────────────────────────────────────────────────────

async def test_lineage_routes_refuse_track1_stages_and_projects(env):
    green = await _project(env["org"], env["bu"], "greenfield")
    await _grant(env, "u-arch", "architect", project=green)
    await _draft(env, "u-x", stage="design", project=green)
    await _draft(env, "u-x", stage="design", project=green)
    client, hdr = _client(env, "u-arch", ["run:create", "artifact:view"])
    base = f"/artifact-versions/{green}/stages/design"
    assert client.post(f"{base}/versions/1/restore", json={"reason": "x"}, headers=hdr).status_code == 404
    assert client.get(f"{base}/compare", params={"from": 1, "to": 2}, headers=hdr).status_code == 404
    assert client.get(f"{base}/versions/1/staleness", headers=hdr).status_code == 404


async def test_restore_needs_reach_on_the_stages_agent(env):
    await _grant(env, "u-sec", "security_engineer")
    await _draft(env, "u-ba")
    await _draft(env, "u-ba")
    client, hdr = _client(env, "u-sec", ["run:create", "artifact:view"])
    r = client.post(f"/artifact-versions/{env['project']}/stages/{STAGE}/versions/1/restore",
                    json={"reason": "x"}, headers=hdr)
    assert r.status_code == 403 and "reach" in r.json()["detail"]


# ── #9 ───────────────────────────────────────────────────────────────────────

async def test_a_granted_draft_is_pinned_as_granted(env):
    from agents_orchestrator.modernization_common import versions
    from agents_orchestrator.modernization_common.standalone import upstream_from_pages

    await _draft(env, "u-ba")
    async with get_db_session_for_tenant(env["org"]) as s:
        await s.execute(text("UPDATE projects SET enforce_artifact_publication = true WHERE id = :p"),
                        {"p": env["project"]})
        vid = (await s.execute(text("SELECT id FROM artifact_versions WHERE project_id = :p AND version = 1"),
                               {"p": env["project"]})).scalar()
        await s.execute(text(
            "INSERT INTO artifact_consumption_grants (tenant_id, project_id, version_id, consumer_stage, granted_by, "
            "reason) VALUES (CAST(:t AS uuid), CAST(:p AS uuid), :v, 'discovery', 'u-ba', 'spike')"),
            {"t": env["org"], "p": env["project"], "v": vid})
    versions.reset_built_from()
    context = await upstream_from_pages(env["project"], env["org"], "discovery", consumed_by="u-reader")
    assert "consumption grant" in context
    assert [(p["stage"], p["version"], p["status"]) for p in versions.turn_built_from()] == [(STAGE, 1, "granted")]


# ── #10 ──────────────────────────────────────────────────────────────────────

async def test_an_input_rejected_after_use_makes_the_version_stale(env):
    await _draft(env, "u-ba")
    async with get_db_session_for_tenant(env["org"]) as s:
        await reject_version(s, tenant_id=env["org"], project_id=env["project"], stage=STAGE, version=1,
                             rejected_by="u-ba2", reason="wrong system")
        stale = await lineage.stale_inputs(s, env["project"], [{"stage": STAGE, "version": 1}])
    assert stale == [{"stage": STAGE, "artifact": None, "pinned": 1, "latest": None, "rejected": True}]


async def test_a_published_pinned_input_with_nothing_newer_is_not_stale(env):
    await _draft(env, "u-ba")
    async with get_db_session_for_tenant(env["org"]) as s:
        await publish_version(s, tenant_id=env["org"], project_id=env["project"], stage=STAGE, version=1,
                              published_by="u-ba2")
        assert await lineage.stale_inputs(s, env["project"], [{"stage": STAGE, "version": 1}]) == []


# ── #11 ──────────────────────────────────────────────────────────────────────

async def test_an_owner_who_produced_it_does_not_hold_the_pa_back(env):
    await _grant(env, "u-ba", "ba")
    await _grant(env, "u-pa", "project_admin")
    async with get_db_session_for_tenant(env["org"]) as s:
        await s.execute(text("UPDATE projects SET approval_fallback_mode = 'after_sla' WHERE id = :p"),
                        {"p": env["project"]})
    v = await _draft(env, "u-ba")
    client, hdr = _client(env, "u-pa", APPROVE)
    r = client.post(_publish_url(env, v), json={"fallbackReason": "the only BA wrote it"}, headers=hdr)
    assert r.status_code == 200, r.text


# ── #12 ──────────────────────────────────────────────────────────────────────

async def test_a_notification_that_was_not_written_is_retried(env, monkeypatch):
    from shared.services import notifications
    from workers.approval_sla_sweeper import ApprovalSlaSweeper

    await _draft(env, "u-ba")
    later = datetime.now(timezone.utc) + timedelta(hours=1000)

    async def lost(*_a, **_k):
        return None

    monkeypatch.setattr(notifications, "emit", lost)
    sent = [x for x in await ApprovalSlaSweeper().sweep_once(now=later) if x["project_id"] == env["project"]]
    assert sent == []
    async with get_db_session_for_tenant(env["org"]) as s:
        assert (await s.execute(text("SELECT sla_notified_at FROM artifact_versions WHERE project_id = :p"),
                                {"p": env["project"]})).scalar() is None
    monkeypatch.undo()
    sent = [x for x in await ApprovalSlaSweeper().sweep_once(now=later) if x["project_id"] == env["project"]]
    assert len(sent) == 1

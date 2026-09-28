"""Legacy/target repository roles (0069, shared/services/repository_roles.py) and the universal
Project Admin fallback (shared/services/fallback_approval.py + the publish route) — Phase C.

Guarding tests (Development Plan §8.3): a stage wired for legacy read can never obtain a target
write, even when its connector mode is "both"; a target writer is refused the legacy remote and
any unconfigured one; a PA approving an owner's version is allowed and labelled, approving their
own is refused, filling two slots is refused, Strict refuses the business-owner slot, after_sla
refuses before the SLA. Real database (`sdlc_product_test`) for everything except `decide`.
"""
from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config.auth.jwt import create_access_token
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import fallback_approval as fb
from shared.services import repository_roles as rr
from shared.services.artifact_versions import snapshot_stage_payload

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

LEGACY = "https://github.com/contoso/claimtrack-legacy"
TARGET = "https://github.com/contoso/claimtrack-modern"


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def project():
    org, bu, proj = str(_uuid.uuid4()), str(_uuid.uuid4()), str(_uuid.uuid4())
    wiring = {s: ["github"] for s in rr.TRACK3_STAGES}
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Repos')"),
                        {"i": org, "s": f"rep-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text(
            "INSERT INTO projects (id, workspace_id, tenant_id, display_name, track, connectors) "
            "VALUES (:i, :w, :t, 'ClaimTrack', 'modernization', CAST(:c AS jsonb))"),
            {"i": proj, "w": bu, "t": org, "c": json.dumps(wiring)})
        await s.execute(text("INSERT INTO integration_grants (tenant_id, kind, target_ref, workspace_id) "
                             "VALUES (CAST(:t AS uuid), 'connector', 'github', CAST(:w AS uuid))"),
                        {"t": org, "w": bu})
    return {"org": org, "project": proj, "bu": bu}


async def _set(p, role, url):
    async with get_db_session_for_tenant(p["org"]) as s:
        return await rr.set_role(s, tenant_id=p["org"], project_id=p["project"], role=role, url=url,
                                 branch="main", actor="u-pa")


async def _write(p, stage, remote):
    async with get_db_session_for_tenant(p["org"]) as s:
        return await rr.assert_target_write(s, tenant_id=p["org"], project_id=p["project"], stage=stage,
                                            remote_url=remote)


async def _mode(p, stage, mode):
    async with get_db_session_for_tenant(p["org"]) as s:
        await s.execute(text("UPDATE projects SET tool_access_modes = CAST(:m AS jsonb) WHERE id = :p"),
                        {"m": json.dumps({f"{stage}::connector::github": mode}), "p": p["project"]})


# ── the role rule ────────────────────────────────────────────────────────────

def test_the_role_rule_table():
    assert {s: rr.repo_access(s, "target") for s in rr.TRACK3_STAGES} == {
        "requirements_modernization": None, "discovery": None, "design_modernization": None, "strategy": None,
        "testing_modernization": "read", "development_modernization": "write",
        "code_review_modernization": "read", "security_modernization": "read",
        "deployment_modernization": "write", "documentation_modernization": "read",
    }
    assert {rr.repo_access(s, "legacy") for s in rr.TRACK3_STAGES} == {"read"}
    assert rr.repo_access("development", "target") is None  # a Track 1 stage has no Track 3 repository


@pytest.mark.parametrize("url,expected", [
    # Paths are lower-cased: GitHub and Azure DevOps resolve them case-insensitively.
    ("https://github.com/Contoso/Repo.git/", "https://github.com/contoso/repo"),
    ("https://user@GitHub.com/contoso/repo", "https://github.com/contoso/repo"),
    ("https://dev.azure.com/org/Project%202/_git/Repo", "https://dev.azure.com/org/project 2/_git/repo"),
    ("https://Org.visualstudio.com/Project/_git/Repo", "https://dev.azure.com/org/project/_git/repo"),
])
def test_normalize(url, expected):
    assert rr.normalize(url) == expected


@pytest.mark.parametrize("url", ["http://github.com/x/y", "git@github.com:x/y.git", "", "https://"])
def test_normalize_refuses_non_https(url):
    with pytest.raises(rr.RepositoryRefused, match="not an https repository URL"):
        rr.normalize(url)


def test_kind_for():
    assert rr.kind_for("https://github.com/x/y") == "github"
    assert rr.kind_for("https://dev.azure.com/o/p/_git/r") == "azure_devops"
    with pytest.raises(rr.RepositoryRefused, match="not a supported repository host"):
        rr.kind_for("https://gitlab.example.invalid/x/y")


# ── setting the roles ────────────────────────────────────────────────────────

async def test_the_target_cannot_be_the_legacy_repository(project):
    await _set(project, "legacy", LEGACY)
    with pytest.raises(rr.RepositoryRefused, match="cannot be the legacy repository"):
        await _set(project, "target", LEGACY + ".git/")


# ── writing: every clause of assert_target_write ─────────────────────────────

async def test_the_migration_development_stage_may_write_the_target(project):
    await _set(project, "legacy", LEGACY)
    await _set(project, "target", TARGET)
    row = await _write(project, "development_modernization", TARGET + ".git")
    assert row.kind == "github"


@pytest.mark.parametrize("stage", ["discovery", "code_review_modernization", "security_modernization",
                                   "testing_modernization", "documentation_modernization"])
async def test_a_stage_that_does_not_write_the_target_is_refused_even_with_both(project, stage):
    """The connector mode is the platform default ("both" — read AND write); the role rule
    still refuses. This is why the level alone could not keep legacy read-only."""
    await _set(project, "target", TARGET)
    with pytest.raises(rr.RepositoryRefused, match="never writes to the target repository"):
        await _write(project, stage, TARGET)


async def test_a_writer_is_refused_the_legacy_remote(project):
    await _set(project, "legacy", LEGACY)
    await _set(project, "target", TARGET)
    with pytest.raises(rr.RepositoryRefused, match="LEGACY repository"):
        await _write(project, "development_modernization", LEGACY)


async def test_a_writer_is_refused_an_unconfigured_remote(project):
    await _set(project, "target", TARGET)
    with pytest.raises(rr.RepositoryRefused, match="not this project's target"):
        await _write(project, "development_modernization", "https://github.com/someone/else")


async def test_no_target_set_is_said(project):
    with pytest.raises(rr.RepositoryRefused, match="no target repository is set"):
        await _write(project, "development_modernization", TARGET)


async def test_a_read_only_wiring_is_refused(project):
    await _set(project, "target", TARGET)
    await _mode(project, "development_modernization", "read")
    with pytest.raises(rr.RepositoryRefused, match="has no write access to github"):
        await _write(project, "development_modernization", TARGET)


async def test_an_unwired_stage_is_refused(project):
    await _set(project, "target", TARGET)
    async with get_db_session_for_tenant(project["org"]) as s:
        await s.execute(text("UPDATE projects SET connectors = '{}'::jsonb WHERE id = :p"), {"p": project["project"]})
    with pytest.raises(rr.RepositoryRefused, match="has no write access"):
        await _write(project, "development_modernization", TARGET)


async def test_another_tenant_sees_no_roles(project):
    await _set(project, "target", TARGET)
    async with get_db_session_for_tenant(str(_uuid.uuid4())) as s:
        assert await rr.get_roles(s, project["project"]) == {}


# ── the fallback rule (pure) ─────────────────────────────────────────────────

def _decide(**kw):
    base = dict(stage="design_modernization", roles={"project_admin"}, is_producer=False, reason="owner on leave")
    return fb.decide(**{**base, **kw})


def test_the_owner_approves_as_owner():
    assert _decide(roles={"architect"}, reason=None) == fb.Capacity("owner")


def test_a_project_admin_approves_as_labelled_fallback_with_a_reason():
    assert _decide() == fb.Capacity("fallback:project_admin", "owner on leave")


@pytest.mark.parametrize("kw,match", [
    ({"is_producer": True, "roles": {"architect"}}, "you produced this version"),
    ({"is_producer": True}, "you produced this version"),
    ({"reason": "  "}, "needs a reason"),
    ({"roles": {"developer"}}, "only a architect or a Project Admin"),
    ({"mode": "after_sla", "sla_passed": False}, "has not passed yet"),
    ({"slot": "business_owner", "policy": "strict"}, "Strict policy"),
    ({"slot": "devops_engineer", "fallback_slots_held": 1}, "at most one slot"),
])
def test_fallback_refusals(kw, match):
    with pytest.raises(fb.ApprovalRefused, match=match):
        _decide(**kw)


def test_after_sla_allows_once_the_sla_passed_or_nobody_holds_the_role():
    assert _decide(mode="after_sla", sla_passed=True).approved_as == "fallback:project_admin"
    assert _decide(mode="after_sla", sla_passed=False, owner_staffed=False).approved_as == "fallback:project_admin"


def test_standard_policy_lets_a_pa_fill_one_business_owner_slot():
    assert _decide(slot="business_owner", policy="standard").approved_as == "fallback:project_admin"


# ── the publish route ────────────────────────────────────────────────────────

async def _grant(p, user, role):
    from shared.authz.grant import grant_role
    await grant_role(user, p["project"], role, tenant_id=p["org"], scope_kind="project")


def _client(p, user, perms):
    import process_api
    return TestClient(process_api.app), {"Authorization": "Bearer " + create_access_token(
        user_id=user, tenant_id=p["org"], permissions=perms)}


async def _draft(p, stage, produced_by):
    async with get_db_session_for_tenant(p["org"]) as s:
        return (await snapshot_stage_payload(s, tenant_id=p["org"], project_id=p["project"], stage=stage,
                                             payload={"n": str(_uuid.uuid4())}, produced_by=produced_by)).version


async def _approved(p, stage, v):
    async with get_db_session_for_tenant(p["org"]) as s:
        return (await s.execute(text("SELECT status, approved_as, fallback_reason, published_by FROM artifact_versions "
                                     "WHERE project_id = :p AND stage = :s AND version = :v"),
                                {"p": p["project"], "s": stage, "v": v})).mappings().one()


URL = "/artifact-versions/{p}/stages/{s}/versions/{v}/publish"


async def test_a_pa_publishes_a_track3_version_as_fallback_with_a_reason(project):
    await _grant(project, "u-pa", "project_admin")
    v = await _draft(project, "requirements_modernization", "u-ba")
    client, hdr = _client(project, "u-pa", ["artifact:approve_requirements_modernization", "artifact:view"])
    path = URL.format(p=project["project"], s="requirements_modernization", v=v)
    r = client.post(path, json={}, headers=hdr)
    assert r.status_code == 403 and "needs a reason" in r.json()["detail"]
    assert (await _approved(project, "requirements_modernization", v))["status"] == "draft"
    r = client.post(path, json={"fallbackReason": "BA on leave this week"}, headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["approvedAs"] == "fallback:project_admin"
    row = await _approved(project, "requirements_modernization", v)
    assert (row["status"], row["approved_as"], row["fallback_reason"]) == (
        "published", "fallback:project_admin", "BA on leave this week")


async def test_the_owner_publishes_as_owner_without_a_reason(project):
    await _grant(project, "u-ba2", "ba")
    v = await _draft(project, "requirements_modernization", "u-ba")
    client, hdr = _client(project, "u-ba2", ["artifact:approve_requirements_modernization", "artifact:view"])
    r = client.post(URL.format(p=project["project"], s="requirements_modernization", v=v), headers=hdr)
    assert r.status_code == 200, r.text
    assert (await _approved(project, "requirements_modernization", v))["approved_as"] == "owner"


async def test_a_pa_cannot_approve_what_they_produced(project):
    await _grant(project, "u-pa", "project_admin")
    v = await _draft(project, "requirements_modernization", "u-pa")
    client, hdr = _client(project, "u-pa", ["artifact:approve_requirements_modernization", "artifact:view"])
    r = client.post(URL.format(p=project["project"], s="requirements_modernization", v=v),
                    json={"fallbackReason": "x"}, headers=hdr)
    assert r.status_code == 403 and "you produced this version" in r.json()["detail"]


async def test_after_sla_mode_holds_a_pa_back_while_the_owner_has_time(project):
    await _grant(project, "u-pa", "project_admin")
    await _grant(project, "u-ba2", "ba")  # the owning role IS staffed
    async with get_db_session_for_tenant(project["org"]) as s:
        await s.execute(text("UPDATE projects SET approval_fallback_mode = 'after_sla' WHERE id = :p"),
                        {"p": project["project"]})
    v = await _draft(project, "requirements_modernization", "u-ba")
    client, hdr = _client(project, "u-pa", ["artifact:approve_requirements_modernization", "artifact:view"])
    r = client.post(URL.format(p=project["project"], s="requirements_modernization", v=v),
                    json={"fallbackReason": "urgent"}, headers=hdr)
    assert r.status_code == 403 and "has not passed yet" in r.json()["detail"]


async def test_the_sla_is_measured_from_the_version(project):
    """The facts wrapper: a version older than the stage's SLA lets a PA decide in after_sla mode."""
    await _grant(project, "u-pa", "project_admin")
    await _grant(project, "u-ba2", "ba")
    async with get_db_session_for_tenant(project["org"]) as s:
        await s.execute(text("UPDATE projects SET approval_fallback_mode = 'after_sla' WHERE id = :p"),
                        {"p": project["project"]})
        cap = await fb.approval_capacity(
            s, tenant_id=project["org"], project_id=project["project"], stage="requirements_modernization",
            user_id="u-pa", produced_by="u-ba", reason="overdue",
            version_created_at=datetime.now(timezone.utc) - timedelta(hours=fb.DEFAULT_SLA_HOURS + 1))
    assert cap.approved_as == "fallback:project_admin"


async def test_a_track1_publish_is_unchanged(project):
    """Track 1 stages record no capacity and need no reason — not Track 3's call to change."""
    await _grant(project, "u-pa", "project_admin")
    async with get_db_session_for_tenant(project["org"]) as s:
        await s.execute(text("UPDATE projects SET track = 'greenfield' WHERE id = :p"), {"p": project["project"]})
    v = await _draft(project, "design", "u-arch")
    client, hdr = _client(project, "u-pa", ["artifact:approve_design", "artifact:view"])
    r = client.post(URL.format(p=project["project"], s="design", v=v), headers=hdr)
    assert r.status_code == 200, r.text
    row = await _approved(project, "design", v)
    assert (row["status"], row["approved_as"], row["fallback_reason"]) == ("published", None, None)


async def test_staffing_warnings(project):
    await _grant(project, "u-pa", "project_admin")
    async with get_db_session_for_tenant(project["org"]) as s:
        warnings = await fb.staffing_warnings(s, tenant_id=project["org"], project_id=project["project"])
    assert warnings[0].startswith("This project has 1 Project Admin(s).")
    assert "No one on this project holds: architect, ba, developer, devops engineer, qa, security engineer." in warnings[1]



async def test_a_project_admin_elsewhere_is_not_a_fallback_here(project):
    """Capacity is read from bindings ON THIS PROJECT (Lessons B2: a role held anywhere in the
    tenant must not count). Same person: Project Admin of another project, developer here."""
    other = str(_uuid.uuid4())
    async with get_db_session_for_tenant(project["org"]) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'Other', 'modernization')"),
                        {"i": other, "w": project["bu"], "t": project["org"]})
    from shared.authz.grant import grant_role
    await grant_role("u-mixed", other, "project_admin", tenant_id=project["org"], scope_kind="project")
    await _grant(project, "u-mixed", "developer")
    v = await _draft(project, "requirements_modernization", "u-ba")
    client, hdr = _client(project, "u-mixed", ["artifact:approve_requirements_modernization", "artifact:view"])
    r = client.post(URL.format(p=project["project"], s="requirements_modernization", v=v),
                    json={"fallbackReason": "I am a PA somewhere"}, headers=hdr)
    assert r.status_code == 403 and "only a ba or a Project Admin" in r.json()["detail"]
    assert (await _approved(project, "requirements_modernization", v))["status"] == "draft"

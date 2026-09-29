"""Phase D on the real database: a version's hand-over packet (GET …/versions/{v}/packet) and
going back from the chat (`restore_version`, `compare_versions`).

Guarding: the packet endpoint builds the packet from the FROZEN version and says why when it
cannot; it is guarded like the rest of the router (track, membership, reach); the chat restore
creates a new draft with the old content and the user as producer, names what goes out of date,
refuses from an Orchestrator conversation, and compare lists the differences.
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config.auth.jwt import create_access_token
from config.ws_helper import set_orchestrator_run, set_project_id, set_tenant_id, set_user_id
from shared.authz.grant import grant_role
from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services.artifact_versions import publish_version, record_consumption, snapshot_stage_payload

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

STAGE = "requirements_modernization"
GOOD = {"system_name": "ClaimTrack", "goal": "Leave Dallas by 2027.", "target_state": {"stack": "Java 21"},
        "in_scope": ["claims intake"], "must_not_change": ["the /api/v1 claims API"],
        "success_measures": [{"metric": "Payouts identical", "target": "100%", "kind": "equivalence"}]}
NO_KIND = {**GOOD, "success_measures": [{"metric": "Payouts identical", "target": "100%"}]}


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def env():
    org, bu, modern, green = (str(_uuid.uuid4()) for _ in range(4))
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'PhaseD')"),
                        {"i": org, "s": f"pd-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        for pid, track in ((modern, "modernization"), (green, "greenfield")):
            await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                                 "VALUES (:i, :w, :t, 'P', :tr)"), {"i": pid, "w": bu, "t": org, "tr": track})
        for payload in (GOOD, NO_KIND):
            await snapshot_stage_payload(s, tenant_id=org, project_id=modern, stage=STAGE, payload=payload,
                                         produced_by="u-ba")
    for pid in (modern, green):
        await grant_role("u-ba2", pid, "ba", tenant_id=org, scope_kind="project")
    return {"org": org, "modern": modern, "green": green}


def _get(env, path, user="u-ba2"):
    import process_api
    return TestClient(process_api.app).get(path, headers={"Authorization": "Bearer " + create_access_token(
        user_id=user, tenant_id=env["org"], permissions=["artifact:view"])})


def _packet_url(project, version, kind="migration-intent"):
    return f"/projects/{project}/modernization/{kind}/versions/{version}/packet"


async def test_a_complete_version_hands_over(env):
    r = _get(env, _packet_url(env["modern"], 1))
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["ok"], body["problems"]) == (True, [])
    assert body["packet"]["payload"]["must_not_change"] == ["the /api/v1 claims API"]
    assert (body["packet"]["version"], body["packet"]["status"]) == (1, "draft")


async def test_a_version_that_cannot_hand_over_says_why(env):
    body = _get(env, _packet_url(env["modern"], 2)).json()
    assert body["ok"] is False and body["packet"] is None
    assert body["problems"] == ["Success measure 1 has no kind (equivalence, performance, security, schedule or cost)."]


async def test_the_packet_is_guarded_like_the_router(env):
    assert _get(env, _packet_url(env["modern"], 9)).status_code == 404
    assert _get(env, _packet_url(env["modern"], 1, kind="design")).status_code == 404
    assert _get(env, _packet_url(env["green"], 1)).status_code == 403
    assert _get(env, _packet_url(env["modern"], 1), user="u-stranger").status_code == 404


# ── going back from the chat ─────────────────────────────────────────────────

@pytest.fixture
def chat(env):
    set_tenant_id(env["org"])
    set_project_id(env["modern"])
    set_user_id("u-ba2")
    set_orchestrator_run(False)
    yield env
    set_tenant_id(None)
    set_project_id(None)
    set_user_id("")


async def test_restore_from_the_chat_creates_a_new_draft_and_names_what_goes_stale(chat):
    from agents_orchestrator.modernization_common.restore_tool import restore

    async with get_db_session_for_tenant(chat["org"]) as s:
        await publish_version(s, tenant_id=chat["org"], project_id=chat["modern"], stage=STAGE, version=2,
                              published_by="u-ba2")
        from shared.services.artifact_versions import get_version

        v2 = await get_version(s, chat["modern"], STAGE, 2)
        await record_consumption(s, tenant_id=chat["org"], project_id=chat["modern"], version=v2,
                                 consumer_stage="discovery", consumed_by="u-ba")
    out = await restore(STAGE, "brief", 1, "v2 dropped the measure kind")
    assert "as v3" in out and "NEW draft" in out and "Dependency and Risk" in out, out
    async with get_db_session_for_tenant(chat["org"]) as s:
        row = (await s.execute(text("SELECT status, produced_by, restored_from, restore_reason, payload "
                                    "FROM artifact_versions WHERE project_id = :p AND stage = :s AND version = 3"),
                               {"p": chat["modern"], "s": STAGE})).mappings().one()
    assert (row["status"], row["produced_by"], row["restored_from"]) == ("draft", "u-ba2", 1)
    assert row["restore_reason"] == "v2 dropped the measure kind" and row["payload"] == GOOD


async def test_restore_needs_a_reason_and_refuses_the_newest(chat):
    from agents_orchestrator.modernization_common.restore_tool import restore

    assert "say why" in await restore(STAGE, "brief", 1, "  ")
    assert "Not restored" in await restore(STAGE, "brief", 2, "no")


async def test_restore_is_refused_in_an_orchestrator_conversation(chat):
    from agents_orchestrator.modernization_common.restore_tool import restore

    set_orchestrator_run(True)
    try:
        assert "Migration Intent page" in await restore(STAGE, "brief", 1, "x")
    finally:
        set_orchestrator_run(False)


async def test_compare_lists_what_differs(chat):
    from agents_orchestrator.modernization_common.restore_tool import compare

    out = await compare(STAGE, "brief", 1, 2)
    assert "difference(s)" in out and "success_measures[0].kind" in out


async def test_compare_fails_in_words_not_with_a_raw_exception(chat, monkeypatch):
    """Review finding 9: a database error reaches the user as a sentence, like restore's."""
    from agents_orchestrator.modernization_common.restore_tool import compare
    from shared.services import version_lineage

    async def broken(*_a, **_k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(version_lineage, "compare_versions", broken)
    assert await compare(STAGE, "brief", 1, 2) == "Cannot compare (RuntimeError). Nothing was changed."

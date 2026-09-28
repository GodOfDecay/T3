"""The Module Migration Ledger (migration 0067 + shared/services/modernization_ledger.py),
against a real database — the state machine, its authors, its history and its tenancy.

Guarding tests for Phase C (Development Plan §8.3): every illegal transition refused, in the
service AND in the database; only the owning agent makes its transitions; concurrent Review
and Security writes lose nothing; history is append-only; another tenant sees nothing.
Runs on `sdlc_product_test` (backend/.env.test).
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import uuid as _uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from shared.db import get_db_session_for_tenant, get_db_session_superuser
from shared.services import modernization_ledger as ledger
from shared.services.modernization_ledger import ArtifactRef, LedgerRefused

pytestmark = pytest.mark.usefixtures("purge_created_orgs")

ART = ArtifactRef("target_design_artifacts", 1)
ACTOR = "u-architect"


@pytest.fixture(autouse=True)
async def _dispose_shared_engine():
    yield
    from shared.db import engine
    await engine.dispose()


@pytest.fixture
async def project():
    org, bu, proj = str(_uuid.uuid4()), str(_uuid.uuid4()), str(_uuid.uuid4())
    async with get_db_session_superuser() as s:
        await s.execute(text("INSERT INTO organizations (id, slug, display_name) VALUES (:i, :s, 'Ledger')"),
                        {"i": org, "s": f"led-{org[:8]}"})
        await s.execute(text("INSERT INTO workspaces (id, organization_id, slug, display_name) "
                             "VALUES (:i, :o, 'unit', 'Unit')"), {"i": bu, "o": org})
    async with get_db_session_for_tenant(org) as s:
        await s.execute(text("INSERT INTO projects (id, workspace_id, tenant_id, display_name, track) "
                             "VALUES (:i, :w, :t, 'ClaimTrack', 'modernization')"), {"i": proj, "w": bu, "t": org})
        await ledger.design_approved(s, tenant_id=org, project_id=proj, actor=ACTOR, artifact=ART, modules=[
            {"module_id": "M-01", "module_name": "claimtrack-core", "legacy_path": "claimtrack-core",
             "tier": "mechanical", "risk_score": 24, "patterns": ["in_place_upgrade"]},
            {"module_id": "M-05", "module_name": "claimtrack-reports", "legacy_path": "claimtrack-reports",
             "tier": "llm_assisted", "risk_score": 41, "patterns": ["in_place_upgrade", "parallel_run"],
             "contract_ids": ["CT-03"]},
        ])
    return {"org": org, "project": proj}


async def _get(p, module_id="M-05"):
    async with get_db_session_for_tenant(p["org"]) as s:
        return (await s.execute(text(
            "SELECT state, history, review_verdict, security_verdict, rejection_count, blocked_from "
            "FROM modernization_modules WHERE project_id = :p AND module_id = :m"),
            {"p": p["project"], "m": module_id})).mappings().one()


async def _run(p, fn, **kw):
    async with get_db_session_for_tenant(p["org"]) as s:
        return await fn(s, project_id=p["project"], **kw)


async def _to_in_review(p, module_id="M-05"):
    await _run(p, ledger.plan_approved, module_id=module_id, wave="W1", ec_ids=["EC-03"], actor=ACTOR,
               artifact=ArtifactRef("strategy_artifacts", 1))
    await _run(p, ledger.baseline_accepted, module_id=module_id, baseline_ids=["BL-04"], actor="u-qa",
               artifact=ArtifactRef("equivalence_artifacts", 1))
    await _run(p, ledger.migration_started, module_id=module_id, target_branch="migrate/x", target_path="x",
               actor="u-dev")
    await _run(p, ledger.pr_opened, module_id=module_id, pr_url="https://example.invalid/pr/12", actor="u-dev",
               artifact=ArtifactRef("migration_artifacts", 1))


# ── the happy path, and what history records ─────────────────────────────────

async def test_a_module_walks_the_whole_machine_and_every_step_is_recorded(project):
    await _to_in_review(project)
    await _run(project, ledger.review_submitted, module_id="M-05", verdict="approve", actor=ACTOR,
               artifact=ArtifactRef("migration_review_artifacts", 1))
    await _run(project, ledger.security_submitted, module_id="M-05", verdict="PASS", actor="u-sec",
               artifact=ArtifactRef("modernization_security_artifacts", 1))
    await _run(project, ledger.equivalence_recorded, module_id="M-05", verdict="verified", perf_verdict=None,
               actor="u-qa", artifact=ArtifactRef("equivalence_artifacts", 2))
    await _run(project, ledger.cut_over, module_id="M-05", actor="u-ops", artifact=ArtifactRef("cutover_artifacts", 1))
    await _run(project, ledger.retired, module_id="M-05", actor="u-ops", artifact=ArtifactRef("cutover_artifacts", 2))
    row = await _get(project)
    assert row["state"] == "retired"
    moves = [(h["from"], h["to"], h["agent"]) for h in row["history"] if h["from"] != h["to"]]
    assert moves == [
        (None, "designed", "design_modernization"),
        ("designed", "sequenced", "strategy"),
        ("sequenced", "baselined", "testing_modernization"),
        ("baselined", "migrating", "development_modernization"),
        ("migrating", "in_review", "development_modernization"),
        ("in_review", "verifying", "security_modernization"),   # the second verdict settles it
        ("verifying", "verified", "testing_modernization"),
        ("verified", "cut_over", "deployment_modernization"),
        ("cut_over", "retired", "deployment_modernization"),
    ]
    assert row["history"][1]["artifact"] == {"stage": "strategy_artifacts", "version": 1}


# ── illegal transitions: the service ─────────────────────────────────────────

ILLEGAL = [(a, b) for a in ledger.STATES for b in ledger.STATES
           if a != b and (a, b) not in ledger.ALLOWED and "blocked" not in (a, b)]


@pytest.mark.parametrize("to", ["baselined", "migrating", "in_review", "verifying", "verified", "cut_over", "retired"])
async def test_the_service_refuses_skipping_a_state(project, to):
    """From `designed`, only `sequenced` is legal — whichever agent asks."""
    for agent in ledger.TRACK3_AGENTS:
        with pytest.raises(LedgerRefused, match="cannot move to"):
            await _run(project, ledger._transition, module_id="M-05", agent=agent, to=to, actor=ACTOR)
    assert (await _get(project))["state"] == "designed"


async def test_only_the_owning_agent_makes_its_transition(project):
    for agent in ledger.TRACK3_AGENTS - {"strategy"}:
        with pytest.raises(LedgerRefused, match="belongs to strategy"):
            await _run(project, ledger._transition, module_id="M-05", agent=agent, to="sequenced", actor=ACTOR)
    await _run(project, ledger._transition, module_id="M-05", agent="strategy", to="sequenced", actor=ACTOR)
    assert (await _get(project))["state"] == "sequenced"


def test_the_service_and_the_database_allow_the_same_transitions():
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0067_modernization_ledger.py"
    spec = importlib.util.spec_from_file_location("m0067", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.TRANSITIONS) - {("verified", "migrating"), ("cut_over", "migrating")} == set(ledger.ALLOWED)
    assert set(mod.STATES) == set(ledger.STATES)
    assert {("verified", "migrating"), ("cut_over", "migrating")} == {(s, "migrating") for s in ledger.REOPENABLE}


# ── illegal transitions: the database, bypassing the service ─────────────────

async def _raw(p, sql: str, params: dict):
    async with get_db_session_for_tenant(p["org"]) as s:
        await s.execute(text(sql), {"p": p["project"], **params})


@pytest.mark.parametrize("frm,to", [("designed", "verified"), ("designed", "in_review"), ("designed", "retired")])
async def test_the_database_refuses_an_illegal_transition_even_with_history(project, frm, to):
    entry = json.dumps([{"from": frm, "to": to, "agent": "sql"}])
    with pytest.raises(DBAPIError, match=f"illegal ledger transition {frm} -> {to}"):
        await _raw(project, "UPDATE modernization_modules SET state = :to, history = history || CAST(:e AS jsonb) "
                            "WHERE project_id = :p AND module_id = 'M-05'", {"to": to, "e": entry})
    assert (await _get(project))["state"] == "designed"


async def test_the_database_refuses_a_state_change_without_a_history_entry(project):
    with pytest.raises(DBAPIError, match="must append exactly one history entry"):
        await _raw(project, "UPDATE modernization_modules SET state = 'sequenced' "
                            "WHERE project_id = :p AND module_id = 'M-05'", {})


async def test_history_cannot_be_truncated(project):
    # The specific message (R47): the per-entry check below would also refuse this, with a
    # different message — asserting only "append-only" let the length check go untested.
    with pytest.raises(DBAPIError, match=r"append-only \(1 entries became 0\)"):
        await _raw(project, "UPDATE modernization_modules SET history = '[]'::jsonb "
                            "WHERE project_id = :p AND module_id = 'M-05'", {})


async def test_history_cannot_be_rewritten(project):
    with pytest.raises(DBAPIError, match="entry 0 was changed"):
        await _raw(project, "UPDATE modernization_modules SET history = jsonb_set(history, '{0,by}', '\"someone-else\"') "
                            "WHERE project_id = :p AND module_id = 'M-05'", {})


async def test_a_module_cannot_enter_the_ledger_mid_migration(project):
    with pytest.raises(DBAPIError, match="enters the ledger as assessed or designed"):
        await _raw(project, "INSERT INTO modernization_modules (tenant_id, project_id, module_id, module_name, state, history) "
                            "VALUES (CAST(:t AS uuid), :p, 'M-09', 'x', 'verified', '[{}]'::jsonb)", {"t": project["org"]})


# ── Review and Security at the same time ─────────────────────────────────────

async def test_concurrent_review_and_security_lose_nothing(project):
    await _to_in_review(project)

    async def review():
        return await _run(project, ledger.review_submitted, module_id="M-05", verdict="approve", actor=ACTOR,
                          artifact=ArtifactRef("migration_review_artifacts", 1))

    async def security():
        return await _run(project, ledger.security_submitted, module_id="M-05", verdict="CONDITIONAL", actor="u-sec",
                          artifact=ArtifactRef("modernization_security_artifacts", 1))

    await asyncio.gather(review(), security())
    row = await _get(project)
    assert (row["review_verdict"], row["security_verdict"], row["state"]) == ("approve", "CONDITIONAL", "verifying")


async def test_a_bad_verdict_sends_it_back_and_repeated_rejection_blocks_it(project):
    await _to_in_review(project)
    for round_ in range(1, ledger.MAX_REJECTIONS + 1):
        await _run(project, ledger.security_submitted, module_id="M-05", verdict="FAIL", actor="u-sec",
                   artifact=ArtifactRef("modernization_security_artifacts", round_))
        row = await _get(project)
        if round_ < ledger.MAX_REJECTIONS:
            assert row["state"] == "migrating"
            await _run(project, ledger.pr_opened, module_id="M-05", pr_url="https://example.invalid/pr/12",
                       actor="u-dev", artifact=ArtifactRef("migration_artifacts", round_ + 1))
    row = await _get(project)
    assert (row["state"], row["blocked_from"], row["rejection_count"]) == ("blocked", "in_review", ledger.MAX_REJECTIONS)


# ── people: block, unblock, reopen ───────────────────────────────────────────

async def test_blocking_and_unblocking_need_a_reason_and_the_right_person(project):
    with pytest.raises(LedgerRefused, match="a reason is required"):
        await _run(project, ledger.block, module_id="M-01", agent="development_modernization", reason=" ", actor="u-dev")
    await _run(project, ledger.block, module_id="M-01", agent="development_modernization",
               reason="manual tier: WebForms UI", actor="u-dev")
    with pytest.raises(LedgerRefused, match="only an Architect or a Project Admin"):
        await _run(project, ledger.unblock, module_id="M-01", role="developer", reason="done", actor="u-dev")
    await _run(project, ledger.unblock, module_id="M-01", role="architect", reason="redesigned", actor=ACTOR)
    row = await _get(project, "M-01")
    assert (row["state"], row["blocked_from"]) == ("designed", None)


async def test_reopen_only_a_verified_or_cut_over_module(project):
    with pytest.raises(LedgerRefused, match="only a verified or cut-over module is reopened"):
        await _run(project, ledger.reopen, module_id="M-05", role="architect", reason="new trap found", actor=ACTOR)


# ── tenancy ──────────────────────────────────────────────────────────────────

async def test_another_tenant_sees_and_moves_nothing(project):
    other = str(_uuid.uuid4())
    async with get_db_session_for_tenant(other) as s:
        assert await ledger.list_modules(s, project["project"]) == []
        with pytest.raises(LedgerRefused, match="not in this project's ledger"):
            await ledger.plan_approved(s, project_id=project["project"], module_id="M-05", wave="W1", ec_ids=[],
                                       actor="intruder", artifact=ART)
    assert (await _get(project))["state"] == "designed"


async def test_rows_cannot_be_written_under_another_tenant_id(project):
    with pytest.raises(DBAPIError, match="row-level security"):
        await _raw(project, "INSERT INTO modernization_modules (tenant_id, project_id, module_id, module_name, state, history) "
                            "VALUES (CAST(:t AS uuid), :p, 'M-08', 'x', 'designed', '[{}]'::jsonb)", {"t": str(_uuid.uuid4())})


async def test_row_level_security_is_forced_not_just_enabled():
    """FORCE is what binds the table's OWNER (the migrations role) too; ENABLE alone binds
    only other roles, so no test through `sdlc_app` can see it go missing — this checks the
    catalog, which is the property the migration promises (Lessons R18)."""
    async with get_db_session_superuser() as s:
        row = (await s.execute(text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'modernization_modules'"
        ))).one()
    assert (row.relrowsecurity, row.relforcerowsecurity) == (True, True)

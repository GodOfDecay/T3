"""Equivalence Testing, Baseline mode — the pure parts (Phase G): the capture profile's refusals, the
noise floor and its masking, the baseline rules and builder, the store. No Docker, no database."""
from __future__ import annotations

import json
import pathlib
import shutil
from datetime import datetime, timedelta, timezone

import pytest

from agents_orchestrator.testing_modernization_agent.analysis import baseline as B
from agents_orchestrator.testing_modernization_agent.analysis import noise as N
from agents_orchestrator.testing_modernization_agent.sandbox import images
from agents_orchestrator.testing_modernization_agent.sandbox import profile as P
from agents_orchestrator.testing_modernization_agent.store import LocalBaselineStore, new_capture_id
from tests.testing_modernization import lite

PROJECT = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    shutil.copytree(lite.SAMPLE, root)
    return root


def _profile(checkout):
    return json.loads((checkout / P.PROFILE_FILE).read_text(encoding="utf-8"))


# ── the capture profile ─────────────────────────────────────────────────────

def test_the_sample_profile_is_usable_and_counts_its_cases(checkout):
    checked, problems = P.validate(_profile(checkout), checkout)
    assert problems == []
    assert {s["id"]: s["cases"] for s in checked["scenarios"]} == {"claims-read": 5, "settle": 6, "bank-file": 1}


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p.update(data="production"), "synthetic or sample data only"),
    (lambda p: p.update(version=2), "\"version\": 1"),
    (lambda p: p["build"].update(dockerfile="../Dockerfile"), "Dockerfile inside the legacy checkout"),
    (lambda p: p["build"].update(dockerfile="C:/Windows/win.ini"), "Dockerfile inside the legacy checkout"),
    (lambda p: p.update(writable=["/"]), "never /"),
    (lambda p: p["service"].update(port=0), "a port (1–65535)"),
    (lambda p: p["service"].update(health="health"), "health path starting with /"),
    (lambda p: p["stubs"][0].update(env="fraud url"), "environment variable"),
    (lambda p: p["stubs"][0].update(name="app"), "reserved name app"),
    (lambda p: p["stubs"][0].update(responses="../../etc/passwd"), "responses must name a file inside"),
    (lambda p: p["scenarios"].append(dict(p["scenarios"][0])), "the id is used twice"),
    (lambda p: p["scenarios"][0].update(requests="nope.jsonl"), "requests must name a JSONL file"),
    (lambda p: p["scenarios"][2].update(outputs=["/data/out/*.txt; rm -rf /"]), "a wildcard only in the file name"),
    (lambda p: p["scenarios"][2].update(outputs=["/*.txt"]), "a wildcard only in the file name"),
    (lambda p: p["scenarios"][2].update(outputs=["/data/*/x.txt"]), "a wildcard only in the file name"),
    (lambda p: p["scenarios"][2].update(command=" "), "needs a command"),
    (lambda p: p["scenarios"][0].update(kind="ui"), "kind must be http or batch"),
    (lambda p: p.pop("service"), "needs a service"),
    (lambda p: p.update(scenarios=[]), "at least one scenario"),
])
def test_a_profile_the_sandbox_cannot_run_safely_is_refused(checkout, mutate, needle):
    p = _profile(checkout)
    mutate(p)
    _checked, problems = P.validate(p, checkout)
    assert any(needle in x for x in problems), problems


def test_a_base_image_must_be_pinned_by_digest():
    assert P.check_dockerfile("FROM python:2.7-slim\n") and "not pinned by digest" in P.check_dockerfile("FROM python:2.7")[0]
    assert P.check_dockerfile("FROM python@sha256:" + "a" * 64 + " AS build\nFROM build\n") == []
    assert P.check_dockerfile("FROM --platform=linux/amd64 python@sha256:" + "b" * 64 + "\n") == []
    assert P.check_dockerfile("RUN echo\n") == ["The Dockerfile has no FROM line."]


def test_a_bad_request_line_or_stub_file_is_named(checkout):
    (checkout / "scenarios" / "claims-read.jsonl").write_text('{"method": "FETCH", "path": "/x"}\nnot json\n',
                                                              encoding="utf-8")
    (checkout / "stubs" / "fraudscore.json").write_text('{"responses": [{"method": "GET", "path": "x"}]}', encoding="utf-8")
    _c, problems = P.validate(_profile(checkout), checkout)
    assert any("line 1: method must be one of" in x for x in problems)
    assert any("line 2 is not JSON" in x for x in problems)
    assert any("response 1: needs method, a path starting with /" in x for x in problems)


def test_the_harness_image_must_be_pinned(monkeypatch):
    assert images.DIGEST_RE.search(images.harness_image())
    monkeypatch.setenv("SDLC_SANDBOX_HARNESS_IMAGE", "python:3.12-slim")
    with pytest.raises(ValueError, match="not pinned by digest"):
        images.harness_image()


# ── the noise floor ─────────────────────────────────────────────────────────

def _runs(tmp_path, r1, r2):
    for n, rows in ((1, r1), (2, r2)):
        d = tmp_path / f"run{n}" / "api"
        d.mkdir(parents=True)
        (d / "responses.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path / "run1", tmp_path / "run2"


def test_a_planted_timestamp_and_request_id_are_found_and_nothing_else(tmp_path):
    def row(ts, rid, payout):
        return {"request": {"method": "GET", "path": "/x"}, "status": 200, "contentType": "application/json",
                "body": {"claim": {"payout": payout, "name": "Test Claimant 001"}, "at": ts, "error": {"requestId": rid}}}
    a, b = _runs(tmp_path, [row("2027-01-01T10:00:00Z", "0779d4fa-289c-4852-bbfd-a19da5cad107", 0.13)],
                 [row("2027-01-01T10:00:05Z", "11dffa0e-49f1-41e3-8ce8-164aca681a1b", 0.13)])
    out = N.compare(a, b, [{"id": "api", "kind": "http"}])["api"]
    assert out["varying"] == {"at": 1, "error.requestId": 1}
    assert out["examples"] == {"at": ["<timestamp>", "<timestamp>"], "error.requestId": ["<uuid>", "<uuid>"]}


def test_a_changed_business_value_is_a_difference_too(tmp_path):
    base = {"request": {"method": "POST", "path": "/s"}, "status": 200, "contentType": "application/json"}
    a, b = _runs(tmp_path, [{**base, "body": {"items": [{"payout": 0.13}]}}],
                 [{**base, "status": 500, "body": {"items": [{"payout": 0.12}]}}])
    assert N.compare(a, b, [{"id": "api", "kind": "http"}])["api"]["varying"] == {"items[].payout": 1, "status": 1}


def test_batch_outputs_are_compared_line_by_line_and_masked(tmp_path):
    for n, header in ((1, "H20260930072233000006"), (2, "H20260930072237000006")):
        d = tmp_path / f"run{n}" / "bank" / "files"
        d.mkdir(parents=True)
        (d / "BANKPAY_20270131.txt").write_bytes(f"{header}\r\nDCLM-0005  Zo\xeb Test\r\n".encode("latin-1"))
        (d.parent / "exec.json").write_text(json.dumps({"exit": 0, "stdout": "wrote 6\n"}), encoding="utf-8")
    out = N.compare(tmp_path / "run1", tmp_path / "run2", [{"id": "bank", "kind": "batch"}])["bank"]
    assert out["varying"] == {"BANKPAY_20270131.txt#L1": 1}
    assert out["examples"]["BANKPAY_20270131.txt#L1"] == ["A99999999999999999999", "A99999999999999999999"]


def test_a_file_in_one_run_only_and_a_changed_exit_code_are_differences(tmp_path):
    for n in (1, 2):
        d = tmp_path / f"run{n}" / "bank" / "files"
        d.mkdir(parents=True)
        if n == 1:
            (d / "extra.txt").write_bytes(b"x")
        (d.parent / "exec.json").write_text(json.dumps({"exit": n - 1, "stdout": f"line {n}\n"}), encoding="utf-8")
    out = N.compare(tmp_path / "run1", tmp_path / "run2", [{"id": "bank", "kind": "batch"}])["bank"]
    assert out["varying"] == {"exit": 1, "extra.txt": 1, "stdout#L1": 1}


@pytest.mark.parametrize("value,shape", [
    (None, "<null>"), (True, "<bool>"), (12.5, "<number>"), ({"a": 1}, "<dict of 1>"),
    ("2026-09-30T07:22:32.867940Z", "<timestamp>"), ("0779d4fa-289c-4852-bbfd-a19da5cad107", "<uuid>"),
    ("Zoë Test-Müller", "AAA AAAA-AAAAAA"), ("CLM-0005", "AAA-9999"),
])
def test_a_value_is_shown_by_its_shape_only(value, shape):
    assert N.mask(value) == shape


@pytest.mark.parametrize("rule,field,covers", [
    ("requestId", "error.requestId", True), ("requestId", "requestId", True), ("Id", "requestId", False),
    ("BANKPAY_*.txt#L1", "BANKPAY_20270131.txt#L1", True), ("BANKPAY_*.txt#L1", "BANKPAY_20270131.txt#L2", False),
    ("", "x", False),
])
def test_what_a_normalization_rule_covers(rule, field, covers):
    assert N.covers(rule, field) is covers


# ── the baseline rules and builder ──────────────────────────────────────────

NOISE = lite.NOISE
SCENARIOS = ["claims-read", "settle", "bank-file"]


def test_the_lite_mapping_holds():
    assert B.check_mapping(lite.plan(), SCENARIOS, lite.MAPPING, lite.NOT_CAPTURED) == []


@pytest.mark.parametrize("mapping,not_captured,needle", [
    ({}, [], "Map at least one equivalence criterion"),
    ({**lite.MAPPING, "EC-09": ["settle"]}, lite.NOT_CAPTURED, "EC-09 is not a criterion of the approved plan"),
    ({**lite.MAPPING, "EC-01": []}, lite.NOT_CAPTURED, "EC-01 is mapped to no scenario"),
    ({**lite.MAPPING, "EC-01": ["ui-journey"]}, lite.NOT_CAPTURED, "which the capture profile does not have"),
    (lite.MAPPING, [], "EC-04 (M-01) is neither recorded nor listed as not captured"),
    ({"EC-03": ["bank-file"]}, [], None),  # only M-02 touched: M-01's criteria are not required
    (lite.MAPPING, [{"ec_id": "EC-04", "reason": ""}], "without a reason"),
    ({**lite.MAPPING, "EC-04": ["claims-read"]}, lite.NOT_CAPTURED, "both mapped and listed as not captured"),
    (lite.MAPPING, [*lite.NOT_CAPTURED, {"ec_id": "EC-77", "reason": "x y z"}], "EC-77 (not captured) is not a criterion"),
])
def test_a_module_is_baselined_whole_and_only_against_the_plan(mapping, not_captured, needle):
    problems = B.check_mapping(lite.plan(), SCENARIOS, mapping, not_captured)
    if needle is None:
        assert problems == []
    else:
        assert any(needle in x for x in problems), problems


def test_an_all_module_criterion_must_always_be_accounted_for():
    p = lite.plan()
    p["equivalence_criteria"].append({**p["equivalence_criteria"][0], "id": "EC-05", "module_id": "all"})
    problems = B.check_mapping(p, SCENARIOS, {"EC-03": ["bank-file"]}, [])
    assert any("EC-05 (every module)" in x for x in problems)


def test_every_uncovered_varying_field_must_be_proposed_and_only_those():
    need = B.uncovered(lite.plan(), lite.MAPPING, NOISE)
    assert need == {"EC-01": ["requestId"], "EC-02": ["requestId"]}  # timestamps and the header are covered
    assert B.check_proposals(lite.plan(), lite.MAPPING, NOISE, lite.PROPOSALS) == []
    missing = B.check_proposals(lite.plan(), lite.MAPPING, NOISE, lite.PROPOSALS[:1])
    assert missing and "requestId varies between two runs of the unchanged legacy system for EC-02" in missing[0]
    invented = B.check_proposals(lite.plan(), lite.MAPPING, NOISE,
                                 [*lite.PROPOSALS, {"ec_id": "EC-01", "field": "claim.payout", "rule": "round"}])
    assert any("for a field that did not vary" in x for x in invented)
    covered = B.check_proposals(lite.plan(), lite.MAPPING, NOISE,
                                [*lite.PROPOSALS, {"ec_id": "EC-01", "field": "generatedAt", "rule": "ignore"}])
    assert any("EC-01 / generatedAt" in x for x in covered)
    ruleless = B.check_proposals(lite.plan(), lite.MAPPING, NOISE,
                                 [{**lite.PROPOSALS[0], "rule": " "}, lite.PROPOSALS[1]])
    assert any("gives no rule" in x for x in ruleless)


def test_the_baseline_groups_by_module_and_scenarios_and_writes_its_own_evidence():
    payload = B.build(lite.plan(), lite.MAPPING, NOISE, lite.PROPOSALS, lite.NOT_CAPTURED, ["fraudscore"],
                      lambda scs: "0" * 63 + str(len(scs)), "local-dev", "2026-09-30T08:00:00+00:00")
    assert [(b["id"], b["module_id"], b["ec_ids"], b["count"], b["unit"]) for b in payload["baselines"]] == [
        ("BL-01", "M-01", ["EC-01"], 5, "cases"), ("BL-02", "M-01", ["EC-02"], 6, "cases"),
        ("BL-03", "M-02", ["EC-03"], 1, "runs")]
    assert payload["baselines"][2]["noise_fields"] == ["BANKPAY_20270131.txt#L1"]
    ec1 = next(n for n in payload["noise"] if n["ec_id"] == "EC-01")
    assert ec1 == {"ec_id": "EC-01", "runs_compared": 2, "varying_fields": ["generatedAt", "requestId"],
                   "covered_by_rule": ["generatedAt"]}
    assert payload["rule_proposals"][0]["evidence"] == (
        "differs between two runs of the unchanged legacy system on identical input in 5 of 5 case(s) "
        "(claims-read); run 1 <uuid> vs run 2 <uuid>")
    assert payload["not_captured"] == lite.NOT_CAPTURED and payload["stubs"] == ["fraudscore"]
    assert B.placements(payload) == [{"module_id": "M-01", "baseline_ids": ["BL-01", "BL-02"]},
                                     {"module_id": "M-02", "baseline_ids": ["BL-03"]}]
    from agents_orchestrator.modernization_common.handover.packets import BaselinePayload
    BaselinePayload.model_validate(payload)


def test_criteria_on_the_same_scenarios_share_one_baseline_and_all_module_ones_go_everywhere():
    p = lite.plan()
    p["equivalence_criteria"].append({**p["equivalence_criteria"][0], "id": "EC-05", "module_id": "all",
                                      "normalization": []})
    payload = B.build(p, {"EC-01": ["claims-read"], "EC-02": ["claims-read"], "EC-05": ["settle"]}, NOISE, [], [], [],
                      lambda scs: "a" * 64, "local-dev", "2026-09-30T08:00:00+00:00")
    assert [(b["id"], b["module_id"], b["ec_ids"]) for b in payload["baselines"]] == [
        ("BL-01", "M-01", ["EC-01", "EC-02"]), ("BL-02", "all", ["EC-05"])]
    assert B.placements(payload) == [{"module_id": "M-01", "baseline_ids": ["BL-01", "BL-02"]}]


def test_the_packet_refuses_a_criterion_both_baselined_and_not_captured():
    from pydantic import ValidationError

    from agents_orchestrator.modernization_common.handover.packets import BaselinePayload
    payload = B.build(lite.plan(), lite.MAPPING, NOISE, lite.PROPOSALS, [{"ec_id": "EC-01", "reason": "a b c"}], [],
                      lambda scs: "a" * 64, "local-dev", "2026-09-30T08:00:00+00:00")
    with pytest.raises(ValidationError, match="both baselined and listed as not captured"):
        BaselinePayload.model_validate(payload)
    payload["not_captured"] = [lite.NOT_CAPTURED[0], lite.NOT_CAPTURED[0]]
    with pytest.raises(ValidationError, match="criteria not captured"):
        BaselinePayload.model_validate(payload)


# ── the store ───────────────────────────────────────────────────────────────

def test_the_store_builds_every_path_from_validated_ids(tmp_path):
    store = LocalBaselineStore(tmp_path)
    cid = new_capture_id()
    assert store.capture_dir(PROJECT, cid) == tmp_path / PROJECT / "captures" / cid
    for bad in ("../x", "cap-1", "cap-20260930000000-zzzzzz"):
        with pytest.raises(ValueError):
            store.capture_dir(PROJECT, bad)
    with pytest.raises(ValueError):
        store.project_dir("../../etc")
    assert store.read_manifest(PROJECT, "../x") is None


def test_the_baseline_hash_is_run_one_and_changes_with_it(tmp_path):
    store = LocalBaselineStore(tmp_path)
    cid = new_capture_id()
    d = store.capture_dir(PROJECT, cid)
    (d / "run1" / "a").mkdir(parents=True)
    (d / "run2" / "a").mkdir(parents=True)
    (d / "run1" / "a" / "responses.jsonl").write_text("1\n", encoding="utf-8")
    (d / "run2" / "a" / "responses.jsonl").write_text("2\n", encoding="utf-8")
    first = store.baseline_hash(PROJECT, cid, ["a"])
    assert len(first) == 64 and first == store.baseline_hash(PROJECT, cid, ["a"])
    (d / "run2" / "a" / "responses.jsonl").write_text("3\n", encoding="utf-8")
    assert store.baseline_hash(PROJECT, cid, ["a"]) == first  # run 2 is evidence, not the baseline
    (d / "run1" / "a" / "responses.jsonl").write_text("9\n", encoding="utf-8")
    assert store.baseline_hash(PROJECT, cid, ["a"]) != first
    with pytest.raises(ValueError):
        store.baseline_hash(PROJECT, cid, ["../a"])


def test_retention_deletes_only_expired_captures_no_baseline_keeps(tmp_path):
    store = LocalBaselineStore(tmp_path)
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    ids = {}
    for name, days, keep in (("old", -1, False), ("kept", -1, True), ("fresh", 5, False)):
        cid = new_capture_id()
        ids[name] = cid
        store.write_manifest(PROJECT, cid, {"id": cid, "startedAt": f"2026-{len(ids):02d}", "keep": keep,
                                            "retainUntil": (now + timedelta(days=days)).isoformat()})
    assert store.purge_expired(PROJECT, now) == [ids["old"]]
    assert {m["id"] for m in store.list_captures(PROJECT)} == {ids["kept"], ids["fresh"]}

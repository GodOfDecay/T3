"""The legacy sandbox, for real (R52: drive a real sandbox, not a mock) — Phase G.

Runs ClaimTrack Lite in Docker: the isolation holds (no route out), the capture records what the
system does and leaves nothing behind, the noise floor finds the planted timestamps and request ids
and nothing else, and after normalization the legacy system replayed against its own baseline shows
ZERO differences. A failed capture leaves no container, network or image. Skipped where Docker is
not running.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

from agents_orchestrator.testing_modernization_agent.analysis import baseline as B
from agents_orchestrator.testing_modernization_agent.analysis import noise as N
from agents_orchestrator.testing_modernization_agent.sandbox import profile as P
from agents_orchestrator.testing_modernization_agent.sandbox import runner as R
from agents_orchestrator.testing_modernization_agent.store import new_capture_id
from tests.testing_modernization import lite


def _docker_up() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_up(), reason="Docker is not running")


def _checkout(tmp: pathlib.Path) -> pathlib.Path:
    root = tmp / "checkout"
    shutil.copytree(lite.SAMPLE, root)
    return root


@pytest.fixture(scope="module")
def captured(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("capture")
    checkout = _checkout(tmp)
    profile, problems = P.validate(json.loads((checkout / P.PROFILE_FILE).read_text(encoding="utf-8")), checkout)
    assert problems == []
    out = tmp / "out"
    capture_id = new_capture_id()  # unique: two test runs at once must not share containers
    result = R.capture(checkout, profile, out, capture_id)
    return {"out": out, "profile": profile, "result": result, "id": capture_id,
            "noise": N.compare(out / "run1", out / "run2", profile["scenarios"])}


def test_the_sandbox_has_no_route_out(tmp_path):
    checkout = _checkout(tmp_path)
    profile, _ = P.validate(json.loads((checkout / P.PROFILE_FILE).read_text(encoding="utf-8")), checkout)
    capture_id = new_capture_id()
    try:
        tag, _image = R.build_image(checkout, profile, capture_id)
        run = R.Run(checkout, profile, tag, capture_id, 1)
        run.start()
        probe = ("import socket\ntry:\n    socket.create_connection(('1.1.1.1', 443), timeout=3)\n    print('OPEN')\n"
                 "except Exception as e:\n    print('BLOCKED ' + type(e).__name__)\n")
        out = R.docker("exec", run.app, "python", "-c", probe, check=False).stdout
        assert "BLOCKED" in out and "OPEN" not in out, out
        dns = R.docker("exec", run.app, "python", "-c",
                       "import socket\ntry:\n    socket.gethostbyname('example.com'); print('RESOLVED')\n"
                       "except Exception: print('NO DNS')\n", check=False).stdout
        assert "NO DNS" in dns, dns
        run.stop()
    finally:
        R.cleanup(capture_id)
        R.docker("rmi", "-f", f"sdlc-legacy:{capture_id}", check=False)
    assert R.leftovers(capture_id) == []


def test_a_capture_records_every_scenario_twice_and_leaves_nothing_behind(captured):
    assert captured["result"]["runs"] == 2
    assert [(s["id"], s["cases"]) for s in captured["result"]["scenarios"]] == [
        ("claims-read", 5), ("settle", 6), ("bank-file", 1)]
    for n in (1, 2):
        assert (captured["out"] / f"run{n}" / "bank-file" / "files" / "BANKPAY_20270131.txt").is_file()
    assert R.leftovers(captured["id"]) == []
    images = R.docker("images", "-q", f"sdlc-legacy:{captured['id']}", check=False).stdout.strip()
    assert images == "", "the capture's image is removed"


def test_the_recording_is_the_legacy_behaviour_bugs_included(captured):
    settle = [json.loads(line) for line in
              (captured["out"] / "run1" / "settle" / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
    by_claim = {r["request"]["path"].split("/")[3]: r for r in settle}
    assert by_claim["CLM-0004"]["body"]["payout"] == 0.13  # Python 2 rounds half away from zero
    assert by_claim["CLM-0007"]["body"]["payout"] == 1.13
    assert by_claim["CLM-0003"]["body"]["status"] == "referred"  # the fraud stub answered inside the sandbox
    assert by_claim["CLM-0005"]["status"] == 409
    bank = (captured["out"] / "run1" / "bank-file" / "files" / "BANKPAY_20270131.txt").read_bytes()
    assert b"Zo\xeb Test-M\xfcller" in bank and bank.count(b"\r\n") == 8  # cp1252, CRLF, header + 6 + trailer


def test_the_noise_floor_is_the_planted_timestamps_and_ids_and_nothing_else(captured):
    assert captured["noise"] == lite.NOISE  # counts and masked shapes exactly as the pure tests and fixtures use
    varying = {sid: set(n["varying"]) for sid, n in captured["noise"].items()}
    assert varying == {"claims-read": {"generatedAt", "requestId"}, "settle": {"requestId", "settledAt"},
                       "bank-file": {"BANKPAY_20270131.txt#L1"}}
    shapes = {v for n in captured["noise"].values() for pair in n["examples"].values() for v in pair}
    assert shapes <= {"<timestamp>", "<uuid>", "A99999999999999999999"}, shapes


def test_legacy_against_its_own_baseline_after_normalization_shows_zero_differences(captured):
    """Research §6.5 acceptance: the rules plus the proposals cover every difference between the runs."""
    plan = lite.plan()
    for p in lite.PROPOSALS:  # as if Migration Strategy adopted the proposals
        next(c for c in plan["equivalence_criteria"] if c["id"] == p["ec_id"])["normalization"].append(
            {"field": p["field"], "rule": p["rule"], "reason": "adopted"})
    assert B.uncovered(plan, lite.MAPPING, captured["noise"]) == {}
    assert B.uncovered(lite.plan(), lite.MAPPING, captured["noise"]) == {"EC-01": ["requestId"], "EC-02": ["requestId"]}


def test_a_failed_capture_leaves_no_container_network_or_image(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_SANDBOX_HEALTH_SECONDS", "6")
    checkout = _checkout(tmp_path)
    raw = json.loads((checkout / P.PROFILE_FILE).read_text(encoding="utf-8"))
    raw["service"]["command"] = "python -c 'import sys; sys.exit(3)'"
    profile, problems = P.validate(raw, checkout)
    assert problems == []
    capture_id = new_capture_id()
    with pytest.raises(R.CaptureFailed, match="did not answer on /health"):
        R.capture(checkout, profile, tmp_path / "out", capture_id)
    assert R.leftovers(capture_id) == []
    assert R.docker("images", "-q", f"sdlc-legacy:{capture_id}", check=False).stdout.strip() == ""

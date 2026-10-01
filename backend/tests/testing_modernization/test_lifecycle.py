"""A capture's lifecycle around the sandbox (Phase G, fix wave).

One capture per project at a time, across server processes (a lock file, not an in-memory lock);
a capture the server was stopped during becomes `failed` instead of `running` forever; expired
captures are swept even for projects nobody captures in any more; every sandbox container runs
without Linux capabilities and with bounded memory, CPU and processes; and a stopped capture stops
at its next step and leaves nothing behind. The Docker tests drive the real sandbox (R52).
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from agents_orchestrator.strategy_agent.tools.strategy_tools import proposal_status
from agents_orchestrator.testing_modernization_agent.sandbox import profile as P
from agents_orchestrator.testing_modernization_agent.sandbox import runner as R
from agents_orchestrator.testing_modernization_agent.store import (
    LocalBaselineStore, max_capture_seconds, new_capture_id, project_ids,
)
from tests.testing_modernization import lite
from workers.baseline_retention_sweeper import BaselineRetentionSweeper

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _docker_up() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


needs_docker = pytest.mark.skipif(not _docker_up(), reason="Docker is not running")


@pytest.fixture
def store(tmp_path):
    return LocalBaselineStore(tmp_path / "equivalence")


def _manifest(store, project, cid, **fields):
    store.write_manifest(project, cid, {"id": cid, **fields})


# ── the project lock ─────────────────────────────────────────────────────────

def test_one_capture_per_project_holds_across_store_instances(store):
    project, a, b = str(uuid.uuid4()), "cap-20261001120000-aaaaaa", "cap-20261001120001-bbbbbb"
    assert store.acquire_lock(project, a, NOW) is True
    other_process = LocalBaselineStore(store.root)  # a second server process sees the same files
    assert other_process.acquire_lock(project, b, NOW) is False
    other_process.release_lock(project, b)  # not its lock: nothing happens
    assert other_process.acquire_lock(project, b, NOW) is False
    store.release_lock(project, a)
    assert other_process.acquire_lock(project, b, NOW) is True
    assert store.acquire_lock(str(uuid.uuid4()), a, NOW) is True, "another project is not blocked"


def test_a_lock_left_by_a_dead_process_is_taken_over(store):
    project, a, b = str(uuid.uuid4()), "cap-20261001120000-aaaaaa", "cap-20261001120001-bbbbbb"
    assert store.acquire_lock(project, a, NOW)
    later = NOW + timedelta(seconds=max_capture_seconds() - 1)
    assert store.acquire_lock(project, b, later) is False, "still within the longest a capture may take"
    assert store.acquire_lock(project, b, NOW + timedelta(seconds=max_capture_seconds() + 1)) is True


def test_an_unreadable_lock_does_not_block_forever(store):
    project, a = str(uuid.uuid4()), "cap-20261001120000-aaaaaa"
    path = store.project_dir(project) / "captures" / ".lock"
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    assert store.acquire_lock(project, a, NOW) is True


def test_the_lock_validates_its_ids(store):
    with pytest.raises(ValueError):
        store.acquire_lock(str(uuid.uuid4()), "../../etc", NOW)
    with pytest.raises(ValueError):
        store.acquire_lock("not-a-uuid", "cap-20261001120000-aaaaaa", NOW)


# ── interrupted captures and retention ──────────────────────────────────────

def test_a_capture_the_server_stopped_during_becomes_failed_and_keeps_nothing(store):
    project = str(uuid.uuid4())
    old, fresh, done = "cap-20261001080000-aaaaaa", "cap-20261001115900-bbbbbb", "cap-20261001070000-cccccc"
    _manifest(store, project, old, status="running", startedAt=(NOW - timedelta(seconds=max_capture_seconds() + 5)).isoformat())
    _manifest(store, project, fresh, status="running", startedAt=(NOW - timedelta(seconds=60)).isoformat())
    _manifest(store, project, done, status="complete", startedAt=(NOW - timedelta(days=1)).isoformat())
    (store.capture_dir(project, old) / "run1" / "settle").mkdir(parents=True)
    assert store.reap_interrupted(project, NOW) == [old]
    m = store.read_manifest(project, old)
    assert m["status"] == "failed" and m["error"].startswith("interrupted") and m["retainUntil"]
    assert not (store.capture_dir(project, old) / "run1").exists()
    assert store.read_manifest(project, fresh)["status"] == "running", "a capture still within its time is left alone"
    assert store.read_manifest(project, done)["status"] == "complete"
    assert store.reap_interrupted(project, NOW) == [], "once"


def test_the_sweep_covers_every_project_and_spares_kept_baselines(store, monkeypatch):
    p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())
    expired = (NOW - timedelta(days=1)).isoformat()
    _manifest(store, p1, "cap-20260101000000-aaaaaa", status="failed", retainUntil=expired)
    _manifest(store, p1, "cap-20260101000001-bbbbbb", status="complete", retainUntil=expired, keep=True)
    _manifest(store, p2, "cap-20260101000002-cccccc", status="complete", retainUntil=(NOW + timedelta(days=1)).isoformat())
    _manifest(store, p2, "cap-20260101000003-dddddd", status="running",
              startedAt=(NOW - timedelta(seconds=max_capture_seconds() + 5)).isoformat())
    (store.root / "not-a-project").mkdir()
    cleaned = []
    monkeypatch.setattr(R, "cleanup", cleaned.append)
    assert project_ids(store.root) == sorted([p1, p2])
    out = BaselineRetentionSweeper(store).sweep_once(NOW)
    assert out == {"purged": ["cap-20260101000000-aaaaaa"], "interrupted": ["cap-20260101000003-dddddd"]}
    assert cleaned == ["cap-20260101000003-dddddd"], "the interrupted capture's Docker objects are removed by label"
    assert store.read_manifest(p1, "cap-20260101000001-bbbbbb") is not None, "a recorded baseline is kept"
    assert store.read_manifest(p2, "cap-20260101000002-cccccc") is not None


def test_one_broken_project_does_not_stop_the_sweep(store, monkeypatch):
    p1, p2 = sorted(str(uuid.uuid4()) for _ in range(2))
    expired = (NOW - timedelta(days=1)).isoformat()
    _manifest(store, p1, "cap-20260101000000-aaaaaa", status="failed", retainUntil=expired)
    _manifest(store, p2, "cap-20260101000001-bbbbbb", status="failed", retainUntil=expired)
    real = store.purge_expired

    def flaky(project_id, now=None):
        if project_id == p1:
            raise OSError("disk")
        return real(project_id, now)

    monkeypatch.setattr(store, "purge_expired", flaky)
    assert BaselineRetentionSweeper(store).sweep_once(NOW)["purged"] == ["cap-20260101000001-bbbbbb"]


# ── what Migration Strategy sees of the proposals ───────────────────────────

def test_a_proposal_is_open_until_the_plan_has_a_rule_for_it():
    proposals = [{"ec_id": "EC-01", "field": "requestId", "rule": "ignore the value"},
                 {"ec_id": "EC-02", "field": "requestId", "rule": "ignore the value"}]
    plan = lite.stored_plan()
    assert [r["in_plan"] for r in proposal_status(proposals, plan)] == [False, False]
    revised = json.loads(json.dumps(plan))
    revised["equivalence_criteria"][0]["normalization"].append(
        {"field": "requestId", "rule": "require present, ignore the value", "reason": "generated per request"})
    rows = proposal_status(proposals, revised)
    assert [(r["in_plan"], r["plan_rule"]) for r in rows] == [(True, "require present, ignore the value"), (False, None)]
    assert proposal_status(proposals, None)[0]["in_plan"] is False, "no plan covers nothing"


# ── the sandbox, for real ───────────────────────────────────────────────────

def _checkout(tmp: pathlib.Path) -> tuple[pathlib.Path, dict]:
    root = tmp / "checkout"
    shutil.copytree(lite.SAMPLE, root)
    profile, problems = P.validate(json.loads((root / P.PROFILE_FILE).read_text(encoding="utf-8")), root)
    assert problems == []
    return root, profile


def test_every_sandbox_container_runs_without_capabilities_and_bounded(monkeypatch):
    monkeypatch.setenv("SDLC_SANDBOX_MEMORY", "512m")
    flags = R.limits()
    assert flags[:4] == ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
    assert flags[flags.index("--memory") + 1] == "512m" and "--pids-limit" in flags and "--cpus" in flags


@needs_docker
def test_the_running_legacy_app_has_no_capabilities_and_its_limits(tmp_path):
    checkout, profile = _checkout(tmp_path)
    capture_id = new_capture_id()
    tag, _image = R.build_image(checkout, profile, capture_id)
    run = R.Run(checkout, profile, tag, capture_id, 1)
    try:
        run.start()
        host = json.loads(R.docker("inspect", run.app, "--format", "{{json .HostConfig}}").stdout)
        assert host["CapDrop"] == ["ALL"] and "no-new-privileges" in host["SecurityOpt"]
        assert host["Memory"] == 1024 ** 3 and host["NanoCpus"] == 10 ** 9 and host["PidsLimit"] == 256
        assert host["ReadonlyRootfs"] is True
        # ... and the legacy system still works under them: one scenario records.
        assert run.scenario(profile["scenarios"][0], tmp_path / "out")["cases"] >= 1
    finally:
        run.stop()
        R.cleanup(capture_id)
        R.docker("rmi", "-f", tag, check=False)
    assert R.leftovers(capture_id) == []


@needs_docker
def test_a_stopped_capture_stops_and_leaves_nothing(tmp_path):
    checkout, profile = _checkout(tmp_path)
    capture_id = new_capture_id()
    stop = threading.Event()
    stop.set()
    with pytest.raises(R.CaptureCancelled):
        R.capture(checkout, profile, tmp_path / "out", capture_id, cancelled=stop)
    assert not (tmp_path / "out" / "run1").exists(), "stopped before the first run"
    assert R.leftovers(capture_id) == []
    images = R.docker("images", "-q", f"sdlc-legacy:{capture_id.lower()}").stdout.strip()
    assert images == "", "the built image is removed too"


@needs_docker
def test_a_capture_stopped_between_scenarios_records_no_further_scenario(tmp_path, monkeypatch):
    checkout, profile = _checkout(tmp_path)
    capture_id = new_capture_id()
    stop = threading.Event()
    real = R.Run.scenario

    def first_then_stop(self, sc, out):
        result = real(self, sc, out)
        stop.set()  # the user stops the turn while the first scenario runs
        return result

    monkeypatch.setattr(R.Run, "scenario", first_then_stop)
    with pytest.raises(R.CaptureCancelled):
        R.capture(checkout, profile, tmp_path / "out", capture_id, cancelled=stop)
    recorded = sorted(p.name for p in (tmp_path / "out" / "run1").iterdir())
    assert recorded == [profile["scenarios"][0]["id"]]
    assert not (tmp_path / "out" / "run2").exists()
    assert R.leftovers(capture_id) == []



def test_a_failed_capture_drops_every_partial_recording(store):
    from agents_orchestrator.testing_modernization_agent.tools.equivalence_tools import _fail

    project, cid = str(uuid.uuid4()), "cap-20261001120000-aaaaaa"
    manifest = {"id": cid, "status": "running", "startedAt": NOW.isoformat()}
    store.write_manifest(project, cid, manifest)
    for sub in ("run1/settle", "run2/settle"):
        (store.capture_dir(project, cid) / sub).mkdir(parents=True)
        (store.capture_dir(project, cid) / sub / "responses.jsonl").write_text("{}", encoding="utf-8")
    _fail(store, project, manifest, "the stub did not start")
    kept = store.read_manifest(project, cid)
    assert kept["status"] == "failed" and kept["error"] == "the stub did not start" and kept["retainUntil"]
    assert sorted(p.name for p in store.capture_dir(project, cid).iterdir()) == ["manifest.json"]


@needs_docker
def test_a_stray_container_of_a_failed_capture_is_removed_by_its_label(tmp_path):
    """A request driver whose `docker run` client timed out keeps running (and keeps the network in use):
    `Run.stop` does not know it by name; the capture's final clean-up removes everything by label."""
    from agents_orchestrator.testing_modernization_agent.sandbox.images import harness_image

    checkout, profile = _checkout(tmp_path)
    (checkout / "Dockerfile").write_text(f"FROM {harness_image()}\nRUN false\n", encoding="utf-8")
    capture_id = new_capture_id()
    label = f"sdlc.capture={capture_id}"
    net = f"sdlc-stray-{capture_id}".lower()
    R.docker("network", "create", "--internal", "--label", label, net)
    R.docker("run", "-d", "--label", label, "--network", net, harness_image(), "sleep", "300")
    try:
        assert len(R.leftovers(capture_id)) == 2
        with pytest.raises(R.CaptureFailed, match="docker build failed"):
            R.capture(checkout, profile, tmp_path / "out", capture_id)
        assert R.leftovers(capture_id) == []
    finally:  # when the clean-up under test is broken, the test still removes what it planted
        ids = R.leftovers(capture_id)
        if ids:
            R.docker("rm", "-f", *ids, check=False)
            R.docker("network", "rm", net, check=False)

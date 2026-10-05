"""Migration Development, the pure parts (Phase H): where it may write, build files, secrets, the record's
checks, the toolchain catalogue, the local-remote safeguard, and the git workspace against local
repositories. No Docker, no database."""
from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from agents_orchestrator.development_modernization_agent import record as R
from agents_orchestrator.development_modernization_agent import remote
from agents_orchestrator.development_modernization_agent import rules
from agents_orchestrator.development_modernization_agent import toolchains as T
from agents_orchestrator.development_modernization_agent import workspace as W
from tests.testing_modernization import lite

LEGACY = lite.SAMPLE


# ── where a module may write ────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["claims-api/server.py", "claims-api/sub/x.py", "claims-api", "Dockerfile",
                                  ".github/workflows/ci.yml", "azure-pipelines.yml", "Dockerfile.api"])
def test_a_module_writes_its_own_path_and_the_shared_build(path):
    assert rules.assert_may_write(path, "claims-api") == path


@pytest.mark.parametrize("path,why", [
    ("settlement-batch/run.py", "outside this module"), ("claims-api-other/x.py", "outside this module"),
    ("db/init.py", "outside this module"), ("sub/Dockerfile", "outside this module"),
    ("../claims-api/x.py", "leaves the target repository"), ("/etc/passwd", "not a path inside"),
    ("C:/x.py", "not a path inside"), ("claims-api/../db/x.py", "outside this module"),
    (".git/config", ".git folder"), ("", "not a path inside"),
])
def test_anything_else_is_refused_and_named(path, why):
    with pytest.raises(rules.WriteRefused, match=why):
        rules.assert_may_write(path, "claims-api")


def test_build_files_are_known_wherever_they_are():
    for p in ("claims-api/requirements.txt", "claims-api/runtime.txt", "pyproject.toml", "web/package.json",
              "Dockerfile", ".github/workflows/x.yml", "svc/pom.xml"):
        assert rules.is_build_file(p), p
    for p in ("claims-api/server.py", "README.md", "claims-api/requirements.py"):
        assert not rules.is_build_file(p), p
    assert rules.mixed_commit(["claims-api/server.py", "Dockerfile"]) == (["Dockerfile"], ["claims-api/server.py"])
    assert rules.out_of_bounds(["claims-api/a.py", "Dockerfile", "db/init.py", "x/Dockerfile"], "claims-api") == [
        "db/init.py", "x/Dockerfile"]


@pytest.mark.parametrize("text,kind", [
    ("-----BEGIN RSA PRIVATE KEY-----\nabc", "a private key"),
    ("key = 'AKIAABCDEFGHIJKLMNOP'", "an AWS access key"),
    ("tok = 'ghp_" + "a" * 36 + "'", "a GitHub token"),
    ("DB = 'Server=x;User Id=sa;Password=Hunter2!;'", "a connection string with a password"),
    ("URL = 'postgres://app:s3cretpw@db:5432/x'", "a URL with a password in it"),
    ("api_key = 'abcdef0123456789abcd'", "a hard-coded secret"),
])
def test_a_secret_is_named_by_kind_never_by_value(text, kind):
    assert kind in rules.secrets_in(text)


@pytest.mark.parametrize("text", [
    "password = os.environ['DB_PASSWORD']", "Password=${DB_PASSWORD}", "pwd = getenv('X')",
    "conn = 'Server=x;Password={{ secret }}'", "url = 'https://example.com/a'", "secret = kv://claimtrack/db",
    "round(amount * rate, 2)",
])
def test_references_to_secrets_are_not_secrets(text):
    assert rules.secrets_in(text) == []


# ── the record's checks ─────────────────────────────────────────────────────

def _state(**kw):
    s = {"builds": [{"ok": True, "head": "h1"}], "tests": {"status": "not_run", "head": "h1"},
         "lint": {"status": "green", "head": "h1"}, "head": "h1", "recipes": []}
    s.update(kw)
    return s


FILES = ["claims-api/requirements.txt", "claims-api/runtime.txt", "claims-api/server.py"]
MAP = [{"legacy_path": f, "disposition": "mapped", "target_path": f} for f in FILES]


def _check(**kw):
    args = dict(outcome="ready_for_review", module_path="claims-api", legacy_files=FILES, file_map=MAP,
                changed=FILES + ["Dockerfile"], target_files=FILES + ["Dockerfile"],
                rewritten=[{"file": "claims-api/server.py", "reason": "py2 rounding"}],
                traps_for_module=["TR-01", "TR-02"], traps_handled={"TR-01": "server.py:24", "TR-02": "server.py:47"},
                vault_references=[], state=_state(), pending=[], secret_hits={})
    args.update(kw)
    return R.check(**args)


def test_a_complete_record_passes():
    assert _check() == []


@pytest.mark.parametrize("change,needle", [
    (dict(file_map=MAP[:2]), "does not cover every legacy file"),
    (dict(file_map=MAP + [{"legacy_path": "claims-api/ghost.py", "disposition": "dropped", "reason": "x"}]),
     "files the legacy module does not have"),
    (dict(target_files=FILES[:2] + ["Dockerfile"]), "which the branch does not have"),
    (dict(changed=FILES + ["db/init.py"]), "outside this module and the shared build"),
    (dict(rewritten=[{"file": "claims-api/other.py", "reason": "x"}]), "listed as rewritten, but the branch"),
    (dict(secret_hits={"claims-api/config.py": ["a private key"]}), "appears to hold a private key"),
    (dict(vault_references=["Hunter2!"]), "is not a vault reference"),
    (dict(traps_handled={"TR-01": "x"}), "Every trap the design lists"),
    (dict(traps_handled={"TR-01": "x", "TR-02": "y", "TR-09": "z"}), "does not list for this module: TR-09"),
    (dict(state=_state(builds=[{"ok": False, "head": "h1", "failing": "SyntaxError"}])), "only a module whose build"),
    (dict(state=_state(builds=[])), "The last build is not run"),
    (dict(state=_state(tests={"status": "red", "head": "h1"})), "The last tests run failed"),
    (dict(state=_state(lint={"status": "green", "head": "h0"})), "The lint ran on an earlier commit"),
    (dict(state=_state(head="h2")), "The branch changed after the last build"),
    (dict(pending=["claims-api/server.py"]), "uncommitted changes"),
])
def test_each_gap_is_refused_and_named(change, needle):
    problems = _check(**change)
    assert any(needle in p for p in problems), problems


def test_build_failed_needs_a_red_build_and_blocked_needs_no_code():
    assert any("build_failed records a red build" in p for p in _check(outcome="build_failed"))
    red = _state(builds=[{"ok": False, "head": "h1", "failing": "x"}])
    assert _check(outcome="build_failed", state=red, traps_handled={}) == []
    assert any("has no code written" in p for p in _check(outcome="blocked"))
    assert _check(outcome="blocked", changed=[]) == []


def test_the_build_result_comes_from_the_workspace_and_is_capped():
    assert R.build_result({}) == {"status": "not_run", "rounds": 0, "failing": None}
    builds = [{"ok": False, "failing": "e"}] * 4 + [{"ok": True}]
    assert R.build_result({"builds": builds}) == {"status": "green", "rounds": 5, "failing": None}


def test_the_traps_are_the_designs_for_this_module():
    from tests.development_modernization.lite_h import design
    assert R.traps_for(design(), "M-01") == ["TR-01", "TR-02"]
    assert R.traps_for(design(), "M-02") == ["TR-01"]


# ── toolchains ──────────────────────────────────────────────────────────────

def test_the_python_toolchain_is_pinned_and_its_recipe_too():
    chain = T.toolchain("Python")
    assert T.DIGEST_RE.search(T.image_for(chain)) and chain.recipe("2to3").tool == "lib2to3"
    assert "latest" not in chain.recipe("2to3").version.lower()
    assert T.argv(chain.build, "claims-api")[-1] == "claims-api"
    assert T.ecosystem_for("Java 21 · Node 24 · Python 3.12") == "python" and T.ecosystem_for("COBOL") == ""
    assert T.toolchain("cobol") is None


def test_an_organisation_image_must_be_pinned_too(monkeypatch):
    monkeypatch.setenv("SDLC_TOOLCHAIN_IMAGE_PYTHON", "registry.corp/python:3.12")
    with pytest.raises(ValueError, match="not pinned by digest"):
        T.image_for(T.toolchain("python"))


# ── the local remote is for development only ────────────────────────────────

class _Row:
    url, kind, branch = "https://github.com/claimtrack/target", "github", "main"


def test_a_local_remote_is_honoured_only_in_development(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_TARGET_REMOTE_MAP", json.dumps({"https://github.com/ClaimTrack/Target.git": str(tmp_path)}))
    monkeypatch.setenv("ENV", "test")
    t = remote.target_of(_Row())
    assert t.local and t.git_url == str(tmp_path)
    for env in ("production", "staging", ""):
        monkeypatch.setenv("ENV", env)
        t = remote.target_of(_Row())
        assert not t.local and t.git_url == _Row.url, env


# ── the workspace, against local repositories ───────────────────────────────

def _bare(tmp: pathlib.Path, *, seed: bool) -> pathlib.Path:
    bare = tmp / "target.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    if seed:
        work = tmp / "seed"
        subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True, capture_output=True)
        (work / "README.md").write_text("target\n")
        for args in (["add", "-A"], ["commit", "-q", "-m", "init"], ["push", "-q", "origin", "HEAD:main"]):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=work, check=True)
    return bare


def _open(tmp, bare, **kw):
    return W.open_workspace(tmp / "ws", git_url=str(bare), base_branch="main", module_id="M-01",
                            module_path="claims-api", legacy_checkout=LEGACY, legacy_commit="c0ffee",
                            copy_legacy=kw.pop("copy_legacy", True), **kw)


def test_an_empty_target_gets_its_base_and_the_legacy_module_as_the_first_commit(tmp_path):
    bare = _bare(tmp_path, seed=False)
    state = _open(tmp_path, bare)
    repo = tmp_path / "ws" / "repo"
    assert state["branch"] == "migrate/claims-api" and state["base_created"] is True
    assert [c["concern"] for c in state["commits"]] == ["copy"]
    assert (repo / "claims-api" / "server.py").read_bytes() == (LEGACY / "claims-api" / "server.py").read_bytes()
    assert "Copy claims-api from the legacy code at c0ffee, unchanged" in W.commits_since(repo, state["base_sha"])[0]["subject"]
    assert W.git(repo, "remote", "get-url", "origin") == str(bare)
    assert _open(tmp_path, bare)["opened_at"] == state["opened_at"], "opening again resumes, never re-clones"


def test_a_target_that_already_has_the_module_is_not_overwritten(tmp_path):
    bare = _bare(tmp_path, seed=True)
    work = tmp_path / "seed"
    (work / "claims-api").mkdir()
    (work / "claims-api" / "x.py").write_text("x = 1\n")
    for args in (["add", "-A"], ["commit", "-q", "-m", "m"], ["push", "-q", "origin", "HEAD:main"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=work, check=True)
    with pytest.raises(W.WorkspaceError, match="already exists in the target"):
        _open(tmp_path, bare)


def test_commits_never_mix_build_files_with_code_and_the_first_pending_file_is_seen(tmp_path):
    bare = _bare(tmp_path, seed=True)
    state = _open(tmp_path, bare)
    repo = tmp_path / "ws" / "repo"
    (repo / "claims-api" / "requirements.txt").write_text("# python 3.12\n")
    (repo / "claims-api" / "server.py").write_text("x = 1\n")
    # The first changed file used to vanish: git's porcelain line starts with a space.
    assert W.pending(repo) == ["claims-api/requirements.txt", "claims-api/server.py"]
    W.commit(repo, state, "fix", "hand fix")
    assert W.pending(repo) == ["claims-api/requirements.txt"], "a fix commit takes code only"
    assert W.commit(repo, state, "fix", "again") is None
    W.commit(repo, state, "build", "py3 build")
    assert W.pending(repo) == []
    subjects = [c["subject"] for c in W.commits_since(repo, state["base_sha"])]
    assert subjects[1:] == ["fix: hand fix", "build: py3 build"]
    with pytest.raises(W.WorkspaceError, match="not a commit concern"):
        W.commit(repo, state, "tidy", "x")


def test_a_push_never_forces_and_never_carries_uncommitted_work(tmp_path):
    bare = _bare(tmp_path, seed=True)
    state = _open(tmp_path, bare)
    repo = tmp_path / "ws" / "repo"
    (repo / "claims-api" / "server.py").write_text("x = 1\n")
    with pytest.raises(W.WorkspaceError, match="uncommitted changes"):
        W.push(repo, state, git_url=str(bare))
    W.commit(repo, state, "fix", "f")
    assert W.push(repo, state, git_url=str(bare)) == W.head(repo)
    # Someone else moves the branch on the remote: our next push is refused, not forced over theirs.
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", "-b", "migrate/claims-api", str(bare), str(other)], check=True, capture_output=True)
    (other / "claims-api" / "y.py").write_text("y = 1\n")
    for args in (["add", "-A"], ["commit", "-q", "-m", "theirs"], ["push", "-q"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=other, check=True)
    (repo / "claims-api" / "server.py").write_text("x = 2\n")
    W.commit(repo, state, "fix", "ours")
    with pytest.raises(W.WorkspaceError, match="push failed"):
        W.push(repo, state, git_url=str(bare))
    theirs = subprocess.run(["git", "--git-dir", str(bare), "log", "-1", "--format=%s", "migrate/claims-api"],
                            capture_output=True, text=True).stdout.strip()
    assert theirs == "theirs"


def test_a_credential_never_reaches_an_error(tmp_path):
    with pytest.raises(W.WorkspaceError) as caught:
        W.git(tmp_path, "clone", "https://x-access-token:SUPERSECRET123@nonexistent.invalid/a.git", "r",
              secret="SUPERSECRET123", timeout=60)
    assert "SUPERSECRET123" not in str(caught.value)


def test_the_lock_is_one_holder_at_a_time(tmp_path):
    assert W.acquire(tmp_path, "a") and not W.acquire(tmp_path, "b")
    W.release(tmp_path, "b")
    assert not W.acquire(tmp_path, "b"), "only the holder releases"
    W.release(tmp_path, "a")
    assert W.acquire(tmp_path, "b")


def test_module_ids_and_paths_are_validated(tmp_path):
    with pytest.raises(W.WorkspaceError):
        W.module_dir("11111111-2222-3333-4444-555555555555", "../x", base=tmp_path)
    with pytest.raises(ValueError):
        W.module_dir("not-a-uuid", "M-01", base=tmp_path)
    assert W.branch_for("Claims API/v1") == "migrate/claims-api-v1"

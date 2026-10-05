"""The migration workspace: a clone of the TARGET repository, one per project and module (H1–H3).

    files/migration-workspaces/<project uuid>/<module id>/
        repo/          the clone, on branch migrate/<legacy path>
        state.json     what the tools did: recipes run, builds and their rounds, tests, lint, commits
        .lock          one tool at a time on a module (O_EXCL, shared by every server process)

CREDENTIALS are never stored: the clone and the push put the stage's credential into the URL for that
one git call (`_inject`), the remote keeps the clean URL, and git's own credential helper is off. Errors
are scrubbed of the credential before anyone sees them.

COMMITS BY CONCERN, made here, never by the model (H3):
  copy     the legacy module as it is — the in-place upgrade's first commit, so the recipe diff is
           reviewable on its own
  recipe   what an upgrade recipe changed (its code files; build files it touched go in a build commit)
  build    build files only (Dockerfile, requirements, pyproject, CI…)
  fix      code only — hand fixes and rewrites
A `build` commit stages ONLY build files and a `fix` commit ONLY code, so the two never mix.

NEVER A FORCE PUSH, never a rewrite: a revert is a new commit. The legacy checkout is read from, never
written (it is a separate directory with its push URL disabled).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from agents_orchestrator.development_modernization_agent import rules

GIT_SECONDS = 180
LOCK_SECONDS = 3600
BOT_NAME, BOT_EMAIL = "SDLC Migration Development", "migration-development@sdlc.invalid"
_MODULE_RE = re.compile(r"^M-\d{2,4}$")
CONCERNS = ("copy", "recipe", "build", "fix")


class WorkspaceError(Exception):
    """A workspace action that could not be done. The message is for people (credential scrubbed)."""


def root() -> pathlib.Path:
    from config import sdlcSettings  # noqa: PLC0415

    return pathlib.Path(sdlcSettings().FILES) / "migration-workspaces"


def module_dir(project_id: str, module_id: str, base: Optional[pathlib.Path] = None) -> pathlib.Path:
    if not _MODULE_RE.match(module_id or ""):
        raise WorkspaceError(f"{module_id!r} is not a module id (M-01, M-02, …).")
    return (base or root()) / str(uuid.UUID(str(project_id))) / module_id


def branch_for(module_path: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", rules.clean_path(module_path)).strip("-.").lower()
    return f"migrate/{slug or 'module'}"


# ── git ──────────────────────────────────────────────────────────────────────

def _git_helpers():
    from agents_orchestrator.discovery_agent.tools.repo_tools import (  # noqa: PLC0415
        _GIT_NO_HELPER, _git_env, _inject, _scrub,
    )
    return _GIT_NO_HELPER, _git_env, _inject, _scrub


def git(repo: pathlib.Path, *args: str, secret: str = "", timeout: int = GIT_SECONDS, check: bool = True,
        raw: bool = False) -> str:
    no_helper, env, _inject, scrub = _git_helpers()
    try:
        proc = subprocess.run(["git", *no_helper, *args], cwd=str(repo), capture_output=True, text=True,
                              timeout=timeout, env=env())
    except subprocess.TimeoutExpired as exc:
        raise WorkspaceError(f"git {args[0]} did not finish within {timeout} seconds.") from exc
    if check and proc.returncode != 0:
        raise WorkspaceError(f"git {args[0]} failed: {scrub((proc.stderr or proc.stdout).strip(), secret)[-500:]}")
    return proc.stdout if raw else proc.stdout.strip()


def _with_secret(url: str, secret: str) -> str:
    _no, _env, inject, _scrub = _git_helpers()
    return inject(url, secret) if secret and url.startswith("https://") else url


# ── state ────────────────────────────────────────────────────────────────────

def read_state(mdir: pathlib.Path) -> Optional[dict]:
    path = mdir / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def write_state(mdir: pathlib.Path, state: dict) -> None:
    mdir.mkdir(parents=True, exist_ok=True)
    tmp = mdir / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, mdir / "state.json")


# ── one tool at a time on a module ──────────────────────────────────────────

def acquire(mdir: pathlib.Path, holder: str) -> bool:
    mdir.mkdir(parents=True, exist_ok=True)
    path = mdir / ".lock"
    now = datetime.now(timezone.utc)
    for _attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                held = json.loads(path.read_text(encoding="utf-8"))
                fresh = datetime.fromisoformat(held["at"]) + timedelta(seconds=LOCK_SECONDS) > now
            except (OSError, ValueError, KeyError, TypeError):
                fresh = False
            if fresh:
                return False
            path.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"holder": holder, "at": now.isoformat()}, f)
        return True
    return False


def release(mdir: pathlib.Path, holder: str) -> None:
    path = mdir / ".lock"
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("holder") == holder:
            path.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


# ── opening ──────────────────────────────────────────────────────────────────

def open_workspace(mdir: pathlib.Path, *, git_url: str, base_branch: str, module_id: str, module_path: str,
                   legacy_checkout: Optional[pathlib.Path], legacy_commit: str, copy_legacy: bool,
                   secret: str = "", requested_by: str = "") -> dict:
    """Clone the target and branch for the module (or return the open workspace). An empty target
    repository gets its base branch created locally (pushed with the module's branch). With
    `copy_legacy`, the legacy module is copied in as the FIRST commit, unchanged."""
    state = read_state(mdir)
    repo = mdir / "repo"
    if state and (repo / ".git").is_dir():
        return state
    shutil.rmtree(repo, ignore_errors=True)
    mdir.mkdir(parents=True, exist_ok=True)
    clean_url = git_url
    git(mdir, "clone", "--no-tags", _with_secret(git_url, secret), "repo", secret=secret)
    git(repo, "remote", "set-url", "origin", clean_url)
    git(repo, "config", "user.name", BOT_NAME)
    git(repo, "config", "user.email", BOT_EMAIL)
    git(repo, "config", "core.autocrlf", "false")
    remote_heads = git(repo, "ls-remote", "--heads", "origin", secret=secret, check=False)
    base = (base_branch or "").strip() or _default_branch(repo) or "main"
    created_base = False
    if f"refs/heads/{base}" in remote_heads:
        git(repo, "checkout", "-q", base)
    elif not remote_heads.strip():  # an empty target repository: start its base branch
        git(repo, "checkout", "-q", "--orphan", base)
        git(repo, "commit", "-q", "--allow-empty", "-m", f"Start {base} for the migration")
        created_base = True
    else:
        raise WorkspaceError(f"The target repository has no branch {base!r}. Set the target branch in the "
                             "project's repository settings.")
    branch = branch_for(module_path)
    git(repo, "checkout", "-q", "-b", branch)
    base_sha = git(repo, "rev-parse", "HEAD")
    state = {"module_id": module_id, "module_path": rules.clean_path(module_path), "branch": branch,
             "base_branch": base, "base_sha": base_sha, "base_created": created_base, "remote": clean_url,
             "legacy_commit": legacy_commit, "recipes": [], "builds": [], "tests": None, "lint": None,
             "commits": [], "opened_by": requested_by, "pushed": None,
             "opened_at": datetime.now(timezone.utc).isoformat()}
    if copy_legacy:
        target = repo / state["module_path"]
        if target.exists():
            raise WorkspaceError(f"{state['module_path']}/ already exists in the target's {base}; an in-place "
                                 "upgrade copies the legacy module into an empty place.")
        source = (legacy_checkout or pathlib.Path("/nonexistent")) / state["module_path"]
        if not source.is_dir():
            raise WorkspaceError(f"The legacy checkout has no {state['module_path']}/ to copy.")
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"), symlinks=False)
        commit(repo, state, "copy", f"Copy {state['module_path']} from the legacy code at "
                                    f"{(legacy_commit or '')[:10]}, unchanged", include_build=True)
    write_state(mdir, state)
    return state


def _default_branch(repo: pathlib.Path) -> str:
    ref = git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False)
    return ref.rsplit("/", 1)[-1] if ref else ""


# ── committing ───────────────────────────────────────────────────────────────

def pending(repo: pathlib.Path) -> list[str]:
    """Changed, added and deleted files not yet committed (repository-relative)."""
    # raw: each entry starts with its two status columns, the first often a space
    out = git(repo, "status", "--porcelain", "-z", "--no-renames", "--untracked-files=all", raw=True)
    paths = []
    for entry in [e for e in out.split("\0") if e]:
        if len(entry) > 3 and entry[2] == " ":
            paths.append(entry[3:])
    return sorted(set(paths))


def commit(repo: pathlib.Path, state: dict, concern: str, message: str, *, include_build: bool = False) -> Optional[str]:
    """Commit the pending changes of ONE concern. `build` commits build files only; `fix` and `recipe`
    commit code only (unless `include_build`, used for the unchanged copy). Returns the sha, or None
    when that concern has nothing pending."""
    if concern not in CONCERNS:
        raise WorkspaceError(f"{concern!r} is not a commit concern ({', '.join(CONCERNS)}).")
    changed = pending(repo)
    build, code = rules.mixed_commit(changed)
    take = changed if include_build else (build if concern == "build" else code)
    if not take:
        return None
    git(repo, "add", "-A", "--", *take)
    git(repo, "commit", "-q", "-m", f"{concern}: {message.strip()}")
    sha = git(repo, "rev-parse", "HEAD")
    state.setdefault("commits", []).append({"sha": sha, "concern": concern, "message": message.strip(),
                                            "files": len(take)})
    return sha


def changed_files(repo: pathlib.Path, base_sha: str) -> list[str]:
    """Every path the branch changes against its base, committed or not."""
    committed = git(repo, "diff", "--name-only", f"{base_sha}..HEAD").splitlines()
    return sorted(set(committed) | set(pending(repo)))


def head(repo: pathlib.Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def commits_since(repo: pathlib.Path, base_sha: str) -> list[dict]:
    out = git(repo, "log", "--reverse", "--format=%H%x09%s", f"{base_sha}..HEAD")
    return [{"sha": line.split("\t", 1)[0], "subject": line.split("\t", 1)[1]} for line in out.splitlines() if line]


def files_under(base: pathlib.Path, module_path: str) -> list[str]:
    """Every file under a module path (repository-relative POSIX), skipping .git."""
    top = base / module_path
    if not top.is_dir():
        return []
    return sorted(p.relative_to(base).as_posix() for p in top.rglob("*")
                  if p.is_file() and ".git" not in p.relative_to(base).parts)


# ── pushing ──────────────────────────────────────────────────────────────────

def push(repo: pathlib.Path, state: dict, *, git_url: str, secret: str = "") -> str:
    """Push the module's branch (and a base branch this workspace created). Never forced: a branch
    that moved on the remote is refused, and the person decides. Returns the pushed head."""
    if pending(repo):
        raise WorkspaceError("There are uncommitted changes; commit them (build or fix) before pushing.")
    url = _with_secret(git_url, secret)
    refs = [f"refs/heads/{state['branch']}:refs/heads/{state['branch']}"]
    if state.get("base_created"):
        refs.insert(0, f"refs/heads/{state['base_branch']}:refs/heads/{state['base_branch']}")
    git(repo, "push", "--porcelain", url, *refs, secret=secret)
    return head(repo)

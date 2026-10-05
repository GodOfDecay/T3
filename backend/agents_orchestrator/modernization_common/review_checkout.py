"""What Migration Review and Security read: a module's ACCEPTED migration and both sides of it (Phase I, I1/I2/I5).

THE MIGRATION is the module's newest migration record that was ACCEPTED (`ready_for_review`): its head
is what was accepted, so its head is what is reviewed and scanned, whatever was pushed after it.

THE TARGET SIDE is a read-only clone of the project's TARGET repository at that head:

    files/review-checkouts/<project>/<stage>/<module>/<head sha>/repo

allowed only when the repository rule gives the stage `read` on the target
(`repository_roles.repo_access`), with the connection wired to THIS stage (Phase H's `remote`), push
URL disabled. One per stage, so Review and Security never share a working tree.

THE LEGACY SIDE is the stage's legacy pull (`legacy_code`), read-only as everywhere.

FILES READ are recorded by the tools that open them (`note_read`), per conversation, so a review can
only claim the files it opened (I5).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import shutil
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

MIGRATION_STAGE = "development_modernization"
_DISABLED_PUSH_URL = "https://push-disabled.invalid/read-only"


@dataclass
class Migration:
    """The module's accepted migration, and where its two sides are on disk."""

    module_id: str
    record: dict
    version: int
    status: str
    head: str
    branch: str
    module_path: str
    ledger: dict = field(default_factory=dict)
    target: Optional[pathlib.Path] = None      # the read-only clone at `head`
    legacy: Optional[pathlib.Path] = None      # the stage's legacy checkout
    legacy_commit: str = ""

    def target_module_files(self) -> list[str]:
        return _files(self.target, self.module_path) if self.target else []

    def legacy_module_files(self) -> list[str]:
        return _files(self.legacy, self.module_path) if self.legacy else []

    def target_paths(self) -> list[str]:
        """Every file the migration touches in the target: the module and the changed shared files."""
        return sorted(set(self.target_module_files()) | {p for p in (self.record.get("changed_files") or [])
                                                          if self.target and (self.target / p).is_file()})


def _files(base: pathlib.Path, module_path: str) -> list[str]:
    top = base / module_path
    if not top.is_dir():
        return []
    return sorted(p.relative_to(base).as_posix() for p in top.rglob("*")
                  if p.is_file() and ".git" not in p.relative_to(base).parts)


def _scope() -> tuple[str, str, str]:
    from config.ws_helper import get_project_id, get_tenant_id, get_user_id  # noqa: PLC0415

    return str(get_tenant_id() or ""), str(get_project_id() or ""), str(get_user_id() or "")


def root() -> pathlib.Path:
    from config import sdlcSettings  # noqa: PLC0415

    return pathlib.Path(sdlcSettings().FILES) / "review-checkouts"


def checkout_dir(project_id: str, stage: str, module_id: str, head: str, base: Optional[pathlib.Path] = None) -> pathlib.Path:
    from agents_orchestrator.development_modernization_agent.workspace import _MODULE_RE  # noqa: PLC0415

    if not _MODULE_RE.match(module_id or "") or not head.isalnum():
        raise ValueError(f"{module_id!r} / {head!r} is not a module and head.")
    return (base or root()) / str(uuid.UUID(str(project_id))) / stage / module_id / head


# ── the accepted record ─────────────────────────────────────────────────────

async def newest_record(module_id: str):
    """The newest migration-record version for the module (any status), or None."""
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import artifact_versions as svc  # noqa: PLC0415

    tenant, project, _u = _scope()
    async with get_db_session_for_tenant(tenant) as db:
        for row in await svc.list_versions(db, project, MIGRATION_STAGE):
            if (row.payload or {}).get("module_id") == module_id:
                return row
    return None


def refusal_for(row, module_id: str) -> Optional[str]:
    """Why a record version cannot be reviewed, in words; None when it can."""
    if row is None:
        return (f"{module_id} has no migration record. Migration Development records the module and opens its "
                "pull request first; there is nothing accepted to review.")
    record = row.payload or {}
    if record.get("outcome") != "ready_for_review":
        return (f"{module_id}'s newest migration record (v{row.version}) is {record.get('outcome')}, not ready for "
                "review; there is no migrated code to review.")
    if row.status not in ("published", "granted"):
        return (f"{module_id}'s newest migration record (v{row.version}) is not accepted yet. What is reviewed is what "
                "was accepted: a Developer accepts it on the Migration Development page first.")
    if not record.get("head_sha") or not record.get("target_branch"):
        return f"{module_id}'s migration record (v{row.version}) names no branch and head."
    return None


async def ledger_row(module_id: str) -> dict:
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    tenant, project, _u = _scope()
    async with get_db_session_for_tenant(tenant) as db:
        for r in await ledger.list_modules(db, project):
            if r.module_id == module_id:
                return ledger.as_dict(r)
    return {}


# ── the two sides ───────────────────────────────────────────────────────────

def clone_at(dest: pathlib.Path, *, git_url: str, branch: str, head: str, secret: str = "") -> pathlib.Path:
    """Clone `branch` and detach at `head`; push disabled. Reuses a finished clone at that head."""
    from agents_orchestrator.development_modernization_agent import workspace as W  # noqa: PLC0415

    repo = dest / "repo"
    if (repo / ".git").is_dir():
        try:
            if W.git(repo, "rev-parse", "HEAD") == head:
                return repo
        except W.WorkspaceError:
            pass
    shutil.rmtree(repo, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    W.git(dest, "clone", "--no-tags", "--single-branch", "--branch", branch, W._with_secret(git_url, secret), "repo",
          secret=secret)
    W.git(repo, "remote", "set-url", "origin", git_url)  # the credential leaves the config
    W.git(repo, "remote", "set-url", "--push", "origin", _DISABLED_PUSH_URL)
    if W.git(repo, "cat-file", "-t", head, check=False) != "commit":
        shutil.rmtree(repo, ignore_errors=True)
        raise W.WorkspaceError(f"The accepted head {head[:10]} is not on {branch} in the target any more (was the branch "
                               "rewritten?). Migration Development records and pushes the module again.")
    W.git(repo, "checkout", "-q", "--detach", head)
    return repo


async def open_migration(stage: str, module_id: str, label: str, *, clone: bool = True) -> tuple[Optional[Migration], str]:
    """The module's accepted migration with both sides on disk, or why not (in words)."""
    from agents_orchestrator.development_modernization_agent import workspace as W  # noqa: PLC0415
    from agents_orchestrator.development_modernization_agent.remote import RemoteError, credential, target_of  # noqa: PLC0415
    from agents_orchestrator.modernization_common import legacy_code  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import repository_roles as rr  # noqa: PLC0415

    try:
        row = await newest_record(module_id)
        ledger = await ledger_row(module_id)
    except Exception:  # noqa: BLE001
        logger.exception("%s: reading the migration record failed", stage)
        return None, "The migration record could not be read just now (a database error). Try again."
    if why := refusal_for(row, module_id):
        return None, why
    record = row.payload or {}
    mig = Migration(module_id=module_id, record=record, version=row.version, status=row.status,
                    head=str(record["head_sha"]), branch=str(record["target_branch"]),
                    module_path=str(record.get("legacy_module_path") or ""), ledger=ledger)
    project_id, run_id = legacy_code.current_scope()
    pull = legacy_code.current_pull(project_id, run_id) if project_id else None
    if pull:
        mig.legacy, mig.legacy_commit = legacy_code.checkout_dir(project_id, run_id), str(pull.get("commit") or "")
    if not clone:
        return mig, ""
    if rr.repo_access(stage, "target") != "read":
        return None, f"The {label} stage has no read access to the target repository."
    tenant, project, _u = _scope()
    try:
        async with get_db_session_for_tenant(tenant) as db:
            roles = await rr.get_roles(db, project)
        trow = roles.get("target")
        if trow is None:
            return None, "No target repository is set for this project (Programme → Repositories)."
        target = target_of(trow)
        secret = await credential(target, label)
        dest = checkout_dir(project, stage, module_id, mig.head)
        mig.target = await asyncio.to_thread(clone_at, dest, git_url=target.git_url, branch=mig.branch,
                                             head=mig.head, secret=secret)
    except (RemoteError, W.WorkspaceError, ValueError) as exc:
        return None, f"The target could not be read: {exc}"
    return mig, ""


def resolve(base: Optional[pathlib.Path], rel: str) -> Optional[pathlib.Path]:
    """`rel` inside `base`, or None (no escaping the checkout, no .git)."""
    if base is None:
        return None
    rel = (rel or "").replace("\\", "/").strip().lstrip("/")
    if not rel or ".git" in pathlib.PurePosixPath(rel).parts:
        return None
    path = (base / rel).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


# ── files read (I5) ─────────────────────────────────────────────────────────

def _reads_file(stage: str, module_id: str) -> pathlib.Path:
    from config.ws_helper import get_session_id  # noqa: PLC0415

    _t, project, _u = _scope()
    session = "".join(c for c in str(get_session_id() or "default") if c.isalnum() or c in "-_")[:80] or "default"
    return root() / str(uuid.UUID(project)) / stage / module_id / f"reads-{session}.json"


def note_read(stage: str, module_id: str, side: str, rel: str) -> None:
    """Record that this conversation opened `rel` on `side` (target | legacy)."""
    try:
        path = _reads_file(stage, module_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        reads = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"target": [], "legacy": []}
        if rel not in reads[side]:
            reads[side].append(rel)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(reads), encoding="utf-8")
            os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — a lost note only makes the submit stricter
        logger.exception("noting a file read failed")


def files_opened(stage: str, module_id: str) -> dict[str, list[str]]:
    try:
        path = _reads_file(stage, module_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"target": [], "legacy": []}
    except Exception:  # noqa: BLE001
        return {"target": [], "legacy": []}

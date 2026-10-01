"""Where captures and baselines live (Phase G decision: local now, Azure later).

`BaselineStore` is the interface; `LocalBaselineStore` keeps everything under
`<FILES>/equivalence/<project uuid>/`, every path built HERE from validated ids (R20):

  capture-profile.json           the project's saved capture profile (when the repo has none)
  captures/<capture id>/
      manifest.json              status (running | complete | failed), times, image, scenarios, noise
      run1/<scenario>/…          the recordings — run 1 is the baseline
      run2/<scenario>/…          the second run, kept as evidence for the noise report

Recordings never leave the store through a tool or a page: callers get manifests (counts, field
names, masked shapes, hashes), never files. A capture that was never recorded as a baseline expires
after the retention period; a recorded one is kept (`keep`) until the migration is decommissioned.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

_CAPTURE_RE = re.compile(r"^cap-\d{14}-[0-9a-f]{6}$")
_SCENARIO_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def region() -> str:
    return os.environ.get("SDLC_BASELINE_REGION", "").strip() or "local-dev"


def retention_days() -> int:
    try:
        return max(1, int(os.environ.get("SDLC_BASELINE_RETENTION_DAYS", "90")))
    except ValueError:
        return 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_capture_id() -> str:
    return f"cap-{_now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"


class BaselineStore(Protocol):
    def capture_dir(self, project_id: str, capture_id: str) -> pathlib.Path: ...
    def write_manifest(self, project_id: str, capture_id: str, manifest: dict) -> None: ...
    def read_manifest(self, project_id: str, capture_id: str) -> Optional[dict]: ...
    def list_captures(self, project_id: str) -> list[dict]: ...
    def baseline_hash(self, project_id: str, capture_id: str, scenario_ids: list[str]) -> str: ...
    def purge_expired(self, project_id: str, now: Optional[datetime] = None) -> list[str]: ...
    def acquire_lock(self, project_id: str, capture_id: str, now: Optional[datetime] = None) -> bool: ...
    def release_lock(self, project_id: str, capture_id: str) -> None: ...
    def reap_interrupted(self, project_id: str, now: Optional[datetime] = None) -> list[str]: ...


class LocalBaselineStore:
    def __init__(self, root: Optional[pathlib.Path] = None):
        if root is None:
            from config import sdlcSettings  # noqa: PLC0415

            root = pathlib.Path(sdlcSettings().FILES) / "equivalence"
        self.root = pathlib.Path(root)

    # ── paths (ids validated; nothing else becomes a directory name) ─────────
    def project_dir(self, project_id: str) -> pathlib.Path:
        return self.root / str(uuid.UUID(str(project_id)))

    def capture_dir(self, project_id: str, capture_id: str) -> pathlib.Path:
        if not _CAPTURE_RE.match(capture_id or ""):
            raise ValueError(f"not a capture id: {capture_id!r}")
        return self.project_dir(project_id) / "captures" / capture_id

    def profile_path(self, project_id: str) -> pathlib.Path:
        return self.project_dir(project_id) / "capture-profile.json"

    # ── manifests ────────────────────────────────────────────────────────────
    def write_manifest(self, project_id: str, capture_id: str, manifest: dict) -> None:
        d = self.capture_dir(project_id, capture_id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "manifest.json.tmp"
        tmp.write_text(json.dumps(manifest, sort_keys=True, indent=1), encoding="utf-8")
        os.replace(tmp, d / "manifest.json")

    def read_manifest(self, project_id: str, capture_id: str) -> Optional[dict]:
        try:
            path = self.capture_dir(project_id, capture_id) / "manifest.json"
        except ValueError:
            return None
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def list_captures(self, project_id: str) -> list[dict]:
        base = self.project_dir(project_id) / "captures"
        if not base.is_dir():
            return []
        found = [self.read_manifest(project_id, d.name) for d in base.iterdir() if _CAPTURE_RE.match(d.name)]
        return sorted((m for m in found if m), key=lambda m: m.get("startedAt", ""), reverse=True)

    # ── the baseline's fingerprint ───────────────────────────────────────────
    def baseline_hash(self, project_id: str, capture_id: str, scenario_ids: list[str]) -> str:
        """sha256 over run 1's recordings of these scenarios: sorted relative paths and bytes."""
        run1 = self.capture_dir(project_id, capture_id) / "run1"
        h = hashlib.sha256()
        for sid in sorted(scenario_ids):
            if not _SCENARIO_RE.match(sid):
                raise ValueError(f"not a scenario id: {sid!r}")
            base = run1 / sid
            for path in sorted(p for p in base.rglob("*") if p.is_file()):
                h.update(path.relative_to(run1).as_posix().encode("utf-8") + b"\0")
                h.update(path.read_bytes() + b"\0")
        return h.hexdigest()

    # ── retention ────────────────────────────────────────────────────────────
    def purge_expired(self, project_id: str, now: Optional[datetime] = None) -> list[str]:
        """Delete captures past their retention that no baseline keeps. Returns their ids."""
        now = now or _now()
        gone = []
        for m in self.list_captures(project_id):
            until = m.get("retainUntil")
            if m.get("keep") or not until or datetime.fromisoformat(until) > now:
                continue
            shutil.rmtree(self.capture_dir(project_id, m["id"]), ignore_errors=True)
            gone.append(m["id"])
        return gone


    # ── one capture per project at a time, across every server process ─────────
    def acquire_lock(self, project_id: str, capture_id: str, now: Optional[datetime] = None) -> bool:
        """Take the project's capture lock (an O_EXCL file, so two processes cannot both win).
        A lock older than `max_capture_seconds()` belongs to a capture whose process died; it is
        taken over. False while another capture holds it."""
        self.capture_dir(project_id, capture_id)  # validates both ids
        path = self.project_dir(project_id) / "captures" / ".lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        now = now or _now()
        for _attempt in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                held = self._lock_holder(path)
                if held and datetime.fromisoformat(held["at"]) + timedelta(seconds=max_capture_seconds()) > now:
                    return False
                path.unlink(missing_ok=True)  # stale: its process is gone
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"capture": capture_id, "at": now.isoformat()}, f)
            return True
        return False

    def release_lock(self, project_id: str, capture_id: str) -> None:
        """Release the lock if THIS capture holds it (never another's)."""
        path = self.project_dir(project_id) / "captures" / ".lock"
        held = self._lock_holder(path)
        if held is not None and held.get("capture") == capture_id:
            path.unlink(missing_ok=True)

    @staticmethod
    def _lock_holder(path: pathlib.Path) -> Optional[dict]:
        try:
            held = json.loads(path.read_text(encoding="utf-8"))
            datetime.fromisoformat(held["at"])
            return held
        except (OSError, ValueError, KeyError, TypeError):
            return None

    # ── a capture whose process died ──────────────────────────────────────────
    def reap_interrupted(self, project_id: str, now: Optional[datetime] = None) -> list[str]:
        """Captures still `running` past the longest a capture may take: the server stopped during
        them. Each becomes `failed` (interrupted) with its partial recordings removed, so the page
        never shows a capture running forever. Returns their ids (the caller removes their Docker
        objects by label)."""
        now = now or _now()
        reaped = []
        for m in self.list_captures(project_id):
            if m.get("status") != "running":
                continue
            try:
                started = datetime.fromisoformat(m["startedAt"])
            except (KeyError, TypeError, ValueError):
                started = now - timedelta(seconds=max_capture_seconds() + 1)
            if started + timedelta(seconds=max_capture_seconds()) > now:
                continue
            for sub in ("run1", "run2"):
                shutil.rmtree(self.capture_dir(project_id, m["id"]) / sub, ignore_errors=True)
            m.update({"status": "failed", "finishedAt": now.isoformat(), "retainUntil": retain_until(now),
                      "error": "interrupted: the server stopped during the capture. Nothing was recorded."})
            self.write_manifest(project_id, m["id"], m)
            reaped.append(m["id"])
        return reaped


def max_capture_seconds() -> int:
    """The longest a capture may run before it counts as interrupted (SDLC_SANDBOX_MAX_CAPTURE_SECONDS)."""
    try:
        return max(300, int(os.environ.get("SDLC_SANDBOX_MAX_CAPTURE_SECONDS", "7200")))
    except ValueError:
        return 7200


def project_ids(root: pathlib.Path) -> list[str]:
    """Every project the store holds captures for (the retention sweep walks these)."""
    out = []
    if root.is_dir():
        for d in root.iterdir():
            try:
                out.append(str(uuid.UUID(d.name)))
            except ValueError:
                continue
    return sorted(out)


def retain_until(finished: datetime) -> str:
    return (finished + timedelta(days=retention_days())).isoformat()

"""Where a version came from, whether it is out of date, and going back to an earlier one.

Track 3 backbone (research §5.3 and §12.4, Development Plan §8.2), on the platform's own
version store (`artifact_versions`) — not a second one.

STALENESS. A version records `built_from` — the input versions it was built from, pinned at
freeze time. It is STALE when any of those inputs now has a NEWER PUBLISHED version. A newer
draft does not count: nobody has accepted it, so building on it would be building on work
the gate exists to hold back. Nothing is invalidated automatically; a person decides whether
to revise (the page shows a badge, the agent says so on its first reply).

RESTORE. Going back never deletes or rewrites history: it creates a NEW version whose
content is the earlier one, records which (`restored_from`) and why (`restore_reason`,
required), and starts as a draft that needs approval like any other. The restorer is its
producer, so the database's self-publication check (`published_by <> produced_by`) is what
stops them approving their own restore. The old version is never touched — the freeze
trigger (0045, extended by 0068) would refuse it anyway.

NO COMMIT HERE (Lessons R23).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from shared.services import artifact_versions as svc

#: Values longer than this are shortened in a comparison, and say so.
_VALUE_CAP = 240


class RestoreRefused(Exception):
    """A restore this caller asked for cannot happen; the message says why."""


# ── staleness ────────────────────────────────────────────────────────────────

async def stale_inputs(db: AsyncSession, project_id: str, built_from: Optional[Iterable[dict]]) -> list[dict]:
    """The pinned inputs that are out of date: [{stage, artifact, pinned, latest, rejected}].

    An input is out of date when it now has a newer PUBLISHED version (`latest`), or when the
    pinned version itself was REJECTED after this one was built on it (`rejected: true`) —
    work built on rejected work is not current just because nothing newer was approved.
    Empty when nothing is out of date, or when the version pinned nothing."""
    stale: list[dict] = []
    for item in built_from or []:
        stage, pinned = item.get("stage"), item.get("version")
        if not stage or not isinstance(pinned, int):
            continue
        latest = await svc.latest_published(db, project_id, stage)
        newer = latest is not None and latest.version > pinned
        source = await svc.get_version(db, project_id, stage, pinned)
        rejected = source is not None and source.status == "rejected"
        if newer or rejected:
            stale.append({"stage": stage, "artifact": item.get("artifact"), "pinned": pinned,
                          "latest": latest.version if newer else None, "rejected": rejected})
    return stale


async def producers_of(db: AsyncSession, project_id: str, stage: str, version: int) -> set[str]:
    """Everyone who produced the content `version` carries: its own producer and, along its
    `restored_from` chain, each earlier version's. Restoring v1 as v3 makes the restorer v3's
    producer — but v1's producer still produced the content, and must not approve it."""
    seen: set[int] = set()
    producers: set[str] = set()
    current: Optional[int] = version
    while current is not None and current not in seen:
        seen.add(current)
        row = await svc.get_version(db, project_id, stage, current)
        if row is None:
            break
        producers.add(row.produced_by)
        current = row.restored_from
    return producers


# ── restore ──────────────────────────────────────────────────────────────────

async def restore_version(db: AsyncSession, *, tenant_id: str, project_id: str, stage: str, version: int,
                          restorer: str, reason: str) -> svc.VersionRef:
    """Bring version `version` back as a NEW draft version. See the module docstring."""
    reason = (reason or "").strip()
    if not reason:
        raise RestoreRefused("say why this version is being restored — a reason is required")
    if not restorer:
        raise RestoreRefused("a restore needs a person to be its producer")
    source = await svc.get_version(db, project_id, stage, version)
    if source is None:
        raise RestoreRefused(f"{stage} v{version} does not exist")
    latest = await svc.latest_version(db, project_id, stage)
    if latest is not None and latest.version == version:
        raise RestoreRefused(f"{stage} v{version} is already the newest version; there is nothing to go back to")
    return await svc.snapshot_stage_payload(
        db, tenant_id=tenant_id, project_id=project_id, stage=stage, payload=source.payload,
        produced_by=restorer, covers=list(source.covers or []), dedupe=False,
        built_from=list(source.built_from) if source.built_from is not None else None,
        restored_from=source.version, restore_reason=reason,
    )


# ── compare ──────────────────────────────────────────────────────────────────

def _flatten(value: Any, path: str = "") -> dict[str, Any]:
    """{json-path: leaf} — objects by key, lists by index."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k in sorted(value, key=str):
            out.update(_flatten(value[k], f"{path}.{k}" if path else str(k)))
        return out or {path: {}}
    if isinstance(value, list):
        out = {}
        for i, v in enumerate(value):
            out.update(_flatten(v, f"{path}[{i}]"))
        return out or {path: []}
    return {path: value}


def _short(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _VALUE_CAP:
        return value[:_VALUE_CAP] + f"… [{len(value) - _VALUE_CAP} more characters]"
    return value


def compare_payloads(before: Any, after: Any) -> list[dict]:
    """What differs between two payloads, leaf by leaf: [{path, change, before, after}] with
    change ∈ added | removed | changed. Deterministic order (by path)."""
    a, b = _flatten(before), _flatten(after)
    out = []
    for path in sorted(set(a) | set(b)):
        if path not in a:
            out.append({"path": path, "change": "added", "before": None, "after": _short(b[path])})
        elif path not in b:
            out.append({"path": path, "change": "removed", "before": _short(a[path]), "after": None})
        elif a[path] != b[path]:
            out.append({"path": path, "change": "changed", "before": _short(a[path]), "after": _short(b[path])})
    return out


async def compare_versions(db: AsyncSession, project_id: str, stage: str, a: int, b: int) -> dict:
    left = await svc.get_version(db, project_id, stage, a)
    right = await svc.get_version(db, project_id, stage, b)
    missing = [v for v, row in ((a, left), (b, right)) if row is None]
    if missing:
        raise RestoreRefused(f"{stage} v{', v'.join(map(str, missing))} not found")
    return {"stage": stage, "from": a, "to": b, "differences": compare_payloads(left.payload, right.payload)}


# ── the envelope (research §5.3) ─────────────────────────────────────────────

def envelope_of(row: Any, *, agent_id: str, artifact: str) -> dict:
    """A version as the hand-over envelope every Track 3 packet carries
    (`agents_orchestrator/modernization_common/handover/packets.py::_Envelope`): read off the
    version row — never assembled by a model."""
    return {
        "schema_version": 1,
        "agent_id": agent_id,
        "artifact": artifact,
        "version": row.version,
        "status": row.status,
        "built_from": [
            {k: v for k, v in item.items() if k in ("artifact", "version", "status", "commit")}
            for item in (row.built_from or []) if item.get("artifact")
        ],
        "produced_by": {"user_id": row.produced_by, "model": None,
                        "run_id": str(row.run_id) if row.run_id else None},
        "produced_at": row.created_at.isoformat() if row.created_at else None,
        "payload": row.payload,
    }

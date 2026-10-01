"""Make ClaimTrack Lite a project's legacy code — LOCAL DEVELOPMENT ONLY.

`samples/legacy-claimtrack` is a small, real legacy system (Python 2.7, SQLite, a cp1252 bank file)
that Track 3's agents can assess, design for, plan and — from Phase G — RUN in the sandbox. This
script turns it into a local git repository and pulls it into a Code Modernization project through
the ordinary `legacy_code.pull_now`, exactly as a real repository arrives (read-only clone, commit
recorded, profile built).

The pages refuse `file://` URLs on purpose (a user must never make the server read its own disk);
this script calls the pull directly, and only on a developer's machine (the seed scripts' guard).

    python -m scripts.install_legacy_sample --project-id <uuid>
    python -m scripts.install_legacy_sample --project-name "ClaimTrack Modernization"
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import shutil
import subprocess
import sys
import uuid as _uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from scripts.seed_dev_personas import _guard, _org_id  # noqa: E402
from shared.db import get_db_session_for_tenant  # noqa: E402

SAMPLE = pathlib.Path(__file__).resolve().parents[2] / "samples" / "legacy-claimtrack"


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=ClaimTrack Lite", "-c", "user.email=sample@localhost", *args],
                   cwd=repo, check=True, capture_output=True)


def make_repository() -> pathlib.Path:
    """A fresh local git repository holding the sample, under the platform's files directory."""
    from config import sdlcSettings  # noqa: PLC0415

    repo = pathlib.Path(sdlcSettings().FILES) / "legacy-samples" / "claimtrack-lite"
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(SAMPLE, repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "ClaimTrack Lite (sample legacy system)")
    return repo


async def _project(org_id: str, project_id: str, name: str) -> str:
    async with get_db_session_for_tenant(org_id) as s:
        if project_id:
            row = (await s.execute(text("SELECT id, track FROM projects WHERE id = CAST(:i AS uuid)"),
                                   {"i": str(_uuid.UUID(project_id))})).first()
        else:
            row = (await s.execute(text("SELECT id, track FROM projects WHERE display_name = :n"), {"n": name})).first()
    if row is None:
        sys.exit("No such project in this organization.")
    if row.track != "modernization":
        sys.exit(f"That project is on the {row.track} track; the legacy code belongs to a Code Modernization project.")
    return str(row.id)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-id", default="")
    parser.add_argument("--project-name", default="ClaimTrack Modernization")
    args = parser.parse_args()
    _guard()
    from agents_orchestrator.modernization_common import legacy_code  # noqa: PLC0415

    project_id = await _project(await _org_id(), args.project_id, args.project_name)
    repo = make_repository()
    record = await legacy_code.pull_now(project_id, repo.resolve().as_uri(), "main", user_id="script:install_legacy_sample")
    if record.get("status") != "ready":
        sys.exit(f"The pull failed: {record.get('error')}")
    pull = record["pull"]
    print(f"  = ClaimTrack Lite is the legacy code of project {project_id} (commit {pull['commit'][:10]})")


if __name__ == "__main__":
    asyncio.run(main())

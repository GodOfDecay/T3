"""Legacy and target repositories on a Track 3 project, and who may write where.

THE RULE (Track 3 master plan §3), one table, pinned by a test:

    legacy   read for every Track 3 stage — never written, by anyone
    target   write: Migration Development, Cutover
             read:  Migration Review, Security, Equivalence Testing, Cutover Pack
             none:  the planning stages (they never touch code)

WHY THE CONNECTOR LEVEL IS NOT ENOUGH. A wired stage with no explicit mode gets read AND
write (`connector_access.DEFAULT_TOOL_MODE = "both"`), and the legacy and the target
repositories are often the same connector kind under the same credential. So a stage's
connector level alone cannot keep the legacy repository read-only. A push to a remote must
pass ALL of `assert_target_write`:

  1. this stage writes the target (the rule above);
  2. the remote IS the project's configured target — never the legacy repository, never an
     unconfigured one;
  3. the platform's own chain permits a write: BU grant → stage wiring → access level,
     resolved by `connector_grants.resolve_effective_access` (the one resolver);
and, at the tool, the Consequential gate (`authorize_consequential`: owning role + this
turn's consent). This module does (1)–(3); it does not replace (4).

NO COMMIT HERE (Lessons R23).
"""
from __future__ import annotations

import urllib.parse
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.orm import ProjectRepository

Role = Literal["legacy", "target"]
Access = Literal["read", "write"]

TRACK3_STAGES = (
    "requirements_modernization", "discovery", "design_modernization", "strategy",
    "testing_modernization", "development_modernization", "code_review_modernization",
    "security_modernization", "deployment_modernization", "documentation_modernization",
)

_TARGET_WRITERS = frozenset({"development_modernization", "deployment_modernization"})
_TARGET_READERS = frozenset({"code_review_modernization", "security_modernization",
                             "testing_modernization", "documentation_modernization"})


class RepositoryRefused(Exception):
    """A repository action this stage may not take. The message says why, for a person."""


def repo_access(stage: str, role: Role) -> Optional[Access]:
    """What `stage` may do with the project's `role` repository: read, write, or nothing."""
    if stage not in TRACK3_STAGES:
        return None
    if role == "legacy":
        return "read"
    if stage in _TARGET_WRITERS:
        return "write"
    if stage in _TARGET_READERS:
        return "read"
    return None


def kind_for(url: str) -> str:
    """The connector kind a repository URL belongs to — the kind whose grant, wiring and
    credential apply to it."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host == "github.com":
        return "github"
    if host == "dev.azure.com" or host.endswith(".visualstudio.com"):
        return "azure_devops"
    raise RepositoryRefused(f"{host or url!r} is not a supported repository host (GitHub or Azure DevOps)")


def normalize(url: str) -> str:
    """One spelling per repository: https, no credentials, lower-case host AND path, no `.git`,
    no trailing slash, %-escapes decoded, and Azure DevOps's legacy host form
    (`https://org.visualstudio.com/Project/_git/Repo`) rewritten to
    `https://dev.azure.com/org/Project/_git/Repo`.

    THE PATH IS LOWER-CASED because GitHub and Azure DevOps resolve repository paths
    case-insensitively: `github.com/Org/Legacy` and `github.com/org/legacy` are the same
    repository, and "the target is not the legacy" must not be defeated by spelling."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise RepositoryRefused(f"{url!r} is not an https repository URL")
    host = parsed.hostname.lower()
    path = urllib.parse.unquote(parsed.path).rstrip("/").removesuffix(".git").rstrip("/").lower()
    if host.endswith(".visualstudio.com"):
        org = host.removesuffix(".visualstudio.com")
        path = f"/{org}{path}"
        host = "dev.azure.com"
    return f"https://{host}{path}"


async def get_roles(db: AsyncSession, project_id: str) -> dict[str, ProjectRepository]:
    rows = (await db.execute(select(ProjectRepository).where(ProjectRepository.project_id == project_id))).scalars()
    return {r.role: r for r in rows}


async def set_role(db: AsyncSession, *, tenant_id: str, project_id: str, role: Role, url: str, branch: str,
                   actor: str) -> ProjectRepository:
    """Name the project's legacy or target repository. The two must differ: a target that IS
    the legacy repository would make "never write the legacy" meaningless."""
    if role not in ("legacy", "target"):
        raise RepositoryRefused(f"unknown repository role {role!r}")
    clean = normalize(url)
    kind = kind_for(clean)
    roles = await get_roles(db, project_id)
    other = roles.get("target" if role == "legacy" else "legacy")
    if other is not None and normalize(other.url) == clean:
        raise RepositoryRefused("the target repository cannot be the legacy repository — the legacy code is never written")
    row = roles.get(role)
    if row is None:
        row = ProjectRepository(tenant_id=tenant_id, project_id=project_id, role=role)
        db.add(row)
    row.kind, row.url, row.branch, row.set_by = kind, clean, (branch or "").strip(), actor
    await db.flush()
    return row


async def assert_target_write(db: AsyncSession, *, tenant_id: str, project_id: str, stage: str,
                              remote_url: str) -> ProjectRepository:
    """Refuse a push unless (1) this stage writes the target, (2) the remote is the configured
    target, and (3) the platform's connector chain permits a write. Returns the target row.

    NOT YET CALLED BY ANY TOOL. The stages that push (Migration Development, Cutover) are not
    built; their push/PR tools MUST call this before any write (master plan Phases H and K).
    Until then no Track 3 agent has a write tool, and the pages say so rather than claiming
    the refusal is live (R48)."""
    if repo_access(stage, "target") != "write":
        raise RepositoryRefused(f"the {stage} stage never writes to the target repository")
    roles = await get_roles(db, project_id)
    target = roles.get("target")
    if target is None:
        raise RepositoryRefused("no target repository is set for this project — a Project Admin sets it in project settings")
    remote = normalize(remote_url)
    legacy = roles.get("legacy")
    if legacy is not None and normalize(legacy.url) == remote:
        raise RepositoryRefused("that is the LEGACY repository; it is never written")
    if normalize(target.url) != remote:
        raise RepositoryRefused("that is not this project's target repository; only the configured target is written")

    from shared.authz.connector_access import permits  # noqa: PLC0415
    from shared.authz.connector_grants import resolve_effective_access  # noqa: PLC0415

    level = await resolve_effective_access(tenant_id=tenant_id, project_id=project_id, target_ref=target.kind,
                                           kind="connector", agent_id=stage)
    if not permits(level, "write"):
        raise RepositoryRefused(
            f"the {stage} stage has no write access to {target.kind}: a Project Admin wires it to the stage "
            "with write access (Tools per stage)")
    return target


def as_dict(row: ProjectRepository) -> dict:
    return {"role": row.role, "kind": row.kind, "url": row.url, "branch": row.branch, "setBy": row.set_by,
            "updatedAt": row.updated_at.isoformat() if row.updated_at else None}

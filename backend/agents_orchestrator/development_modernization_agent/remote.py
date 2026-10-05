"""The TARGET repository from the platform's side: where a workspace clones from and pushes to, the
credential, and the pull request (H1, H11, H12).

THE CREDENTIAL is the repository connection the project wired to THIS stage (bound for the turn by the
page socket), and only one for the target's own host: a GitHub token is never sent to Azure DevOps.
It is never stored (`workspace` puts it in the URL for one git call). Whether this stage may WRITE is
decided by `repository_roles.assert_target_write`, before any push.

PULL REQUESTS: GitHub's REST API, or Azure DevOps through the platform's existing helper
(`shared/services/ado_repos.create_pull_request`). An open pull request for the branch is reused: a
rework push updates it, never a second one.

LOCAL DEVELOPMENT ONLY (H12): with ENV=dev or ENV=test, `SDLC_TARGET_REMOTE_MAP` (JSON: target URL →
local bare repository path) sends the clone and push to a local repository, and the pull request is
written beside it (`sdlc-pull-requests.json`). Anywhere else the map is ignored, so a production push
can only go to the configured target.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import urllib.parse
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class RemoteError(Exception):
    """The target cannot be reached or written as asked. The message is for people (no credential)."""


@dataclass
class Target:
    url: str          # the configured, normalized target (https)
    kind: str         # github | azure_devops
    branch: str       # the base branch ("" = the repository's default)
    git_url: str      # what git clones from and pushes to
    local: bool       # a mapped local repository (dev/test only)


def _dev() -> bool:
    return os.environ.get("ENV", "").strip().lower() in ("dev", "test")


def _mapped(url: str) -> Optional[str]:
    if not _dev():
        return None
    raw = os.environ.get("SDLC_TARGET_REMOTE_MAP", "").strip()
    if not raw:
        return None
    try:
        table = json.loads(raw)
    except ValueError:
        logger.warning("SDLC_TARGET_REMOTE_MAP is not valid JSON; ignored")
        return None
    from shared.services.repository_roles import normalize  # noqa: PLC0415

    for key, path in (table or {}).items():
        try:
            if normalize(key) == url:
                return str(path)
        except Exception:  # noqa: BLE001 — a bad key in a dev setting is skipped
            continue
    return None


def target_of(row) -> Target:
    """The project's target repository row → where git goes."""
    local = _mapped(row.url)
    return Target(url=row.url, kind=row.kind, branch=(row.branch or "").strip(),
                  git_url=local or row.url, local=local is not None)


async def credential(target: Target) -> str:
    """The stage's connection secret for the target's host ("" when none is bound: a public or a local
    repository). Raises RemoteError when a connection IS bound but for another host or unusable."""
    if target.local:
        return ""
    try:
        from config.connectors.context import get_connector  # noqa: PLC0415

        conn = get_connector()
    except Exception:  # noqa: BLE001 — nothing bound for this turn
        return ""
    name = str(getattr(conn, "connector_name", "") or "")
    provider = "github" if "github" in name else "azure_devops"
    if provider != target.kind:
        raise RemoteError(f"The repository connection wired to Migration Development is for {provider.replace('_', ' ')}, "
                          f"but the target is on {target.kind.replace('_', ' ')}. A Project Admin wires the target's "
                          "connection to this stage.")
    try:
        auth = await conn.auth_adapter()
    except Exception as exc:  # noqa: BLE001
        raise RemoteError(f"The repository connection could not be authenticated ({type(exc).__name__}).") from exc
    return str(auth.get("pat") or auth.get("token") or "")


async def open_pull_request(target: Target, *, branch: str, base: str, title: str, body: str, secret: str) -> str:
    """Open (or find the open) pull request for `branch` into `base`. Returns its URL."""
    if target.local:
        return _local_pr(pathlib.Path(target.git_url), branch, base, title, body)
    if target.kind == "github":
        return await _github_pr(target.url, branch, base, title, body, secret)
    if target.kind == "azure_devops":
        return await _ado_pr(target.url, branch, base, title, body, secret)
    raise RemoteError(f"Pull requests on {target.kind} are not supported.")


def _local_pr(bare: pathlib.Path, branch: str, base: str, title: str, body: str) -> str:
    path = bare / "sdlc-pull-requests.json"
    prs = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    for pr in prs:
        if pr["head"] == branch and pr["state"] == "open":
            pr.update(title=title, body=body)
            path.write_text(json.dumps(prs, indent=1), encoding="utf-8")
            return pr["url"]
    number = len(prs) + 1
    url = f"{bare.resolve().as_uri()}#pull/{number}"
    prs.append({"number": number, "url": url, "head": branch, "base": base, "title": title, "body": body,
                "state": "open"})
    path.write_text(json.dumps(prs, indent=1), encoding="utf-8")
    return url


def _owner_repo(url: str) -> tuple[str, str]:
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    if len(parts) < 2:
        raise RemoteError(f"{url} is not a GitHub repository URL (https://github.com/<owner>/<repo>).")
    return parts[0], parts[1]


async def _github_pr(url: str, branch: str, base: str, title: str, body: str, secret: str) -> str:
    import httpx  # noqa: PLC0415

    owner, repo = _owner_repo(url)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    api = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    async with httpx.AsyncClient(timeout=30.0) as client:
        found = await client.get(api, headers=headers, params={"head": f"{owner}:{branch}", "state": "open"})
        if found.status_code == 200 and found.json():
            pr = found.json()[0]
            await client.patch(f"{api}/{pr['number']}", headers=headers, json={"body": body[:60000]})
            return pr["html_url"]
        made = await client.post(api, headers=headers, json={"title": title[:250], "head": branch, "base": base,
                                                              "body": body[:60000], "draft": False})
    if made.status_code not in (200, 201):
        raise RemoteError(f"GitHub refused the pull request ({made.status_code}): "
                          f"{(made.json() or {}).get('message', '') if made.content else ''}"[:300])
    return made.json()["html_url"]


async def _ado_pr(url: str, branch: str, base: str, title: str, body: str, secret: str) -> str:
    from shared.services.ado_repos import create_pull_request  # noqa: PLC0415

    parts = [urllib.parse.unquote(p) for p in urllib.parse.urlparse(url).path.split("/") if p]
    # https://dev.azure.com/<org>/<project>/_git/<repo>
    if len(parts) < 4 or parts[2] != "_git":
        raise RemoteError(f"{url} is not an Azure DevOps repository URL (https://dev.azure.com/<org>/<project>/_git/<repo>).")
    org, project, repo = parts[0], parts[1], parts[3]
    try:
        made = await create_pull_request(project, repo, branch, base, title, body, pat=secret or None,
                                         org_url=f"https://dev.azure.com/{org}")
    except Exception as exc:  # noqa: BLE001
        raise RemoteError(f"Azure DevOps refused the pull request ({type(exc).__name__}).") from exc
    if not made:
        raise RemoteError("Azure DevOps did not return the pull request.")
    return made

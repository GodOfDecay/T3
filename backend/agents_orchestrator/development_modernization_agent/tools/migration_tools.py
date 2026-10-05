"""Tools of the Migration Development agent (Track 3, Phase H).

  read       the ledger and one module's plan (`get_module_plan`): its tier, patterns, wave, frozen
             contracts, traps, criteria and whether its baseline is ACCEPTED — from the design, the
             plan and the baseline THIS TURN pinned, and the ledger.
  workspace  `open_target_workspace` clones the TARGET (never the legacy) on `migrate/<module>`;
             an in-place upgrade copies the legacy module in as the first commit. Ledger
             `baselined → migrating`.
  change     recipes from the catalogue only (`toolchains`), and file writes inside the module or the
             shared build (`rules`), never a secret; commits by concern, made by the tools.
  check      build / tests / lint in the toolchain's sandbox; at most five build rounds, counted here.
             `preview_equivalence` replays the module's scenarios against the ACCEPTED baseline: a hint.
  record     `record_module_migration` — the file map complete, the diff in bounds, the build from the
             workspace — frozen as the next version (one version = one module).
  push       `push_and_open_pr` — CONSEQUENTIAL: Developer or Project Admin of THIS project, this turn's
             consent, `repository_roles.assert_target_write`, the newest record ACCEPTED and the branch
             exactly as recorded. Never forced. Ledger `migrating → in_review`.

The model never states a build, a test, a recipe or a head: the tools record them and the record tool
reads them back. Workspace actions run on the Migration Development page only (an Orchestrator
conversation can explain, not migrate).
"""
from __future__ import annotations

import asyncio
import logging
import pathlib
import shutil
import uuid
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool

from agents_orchestrator.development_modernization_agent import rules
from agents_orchestrator.development_modernization_agent import workspace as W

logger = logging.getLogger(__name__)

STAGE = "development_modernization"
FILE_SEGMENT = "development_modernization_agent"
DESIGN, PLAN, BASELINE = "design_modernization", "strategy", "testing_modernization"
INPUTS = [DESIGN, PLAN, BASELINE]
DEV_ROLES = {"developer", "project_admin"}
MAX_ROUNDS = 5
_MAX_WRITE = 400_000
_MAX_READ_LINES = 400


def _approved(item) -> bool:
    return item.version is not None and item.status in ("published", "granted")


def _scope() -> tuple[str, str, str]:
    from config.ws_helper import get_project_id, get_tenant_id, get_user_id  # noqa: PLC0415

    return str(get_tenant_id() or ""), str(get_project_id() or ""), str(get_user_id() or "")


def _page_only() -> Optional[str]:
    from config.ws_helper import get_orchestrator_run  # noqa: PLC0415

    if get_orchestrator_run():
        return ("Modules are migrated on the Migration Development page, against the project's APPROVED design, "
                "plan and baseline. Open the page to migrate; here I can explain.")
    return None


async def _inputs():
    from agents_orchestrator.modernization_common.inputs import read_inputs  # noqa: PLC0415

    return await read_inputs(INPUTS)


async def _ledger_rows() -> dict[str, dict]:
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    tenant, project, _user = _scope()
    async with get_db_session_for_tenant(tenant) as db:
        return {r.module_id: ledger.as_dict(r) for r in await ledger.list_modules(db, project)}


async def _roles() -> set[str]:
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services.fallback_approval import project_roles  # noqa: PLC0415

    tenant, project, user = _scope()
    try:
        async with get_db_session_for_tenant(tenant) as db:
            return await project_roles(db, tenant_id=tenant, project_id=project, user_id=user)
    except Exception:  # noqa: BLE001 — cannot prove the role ⇒ none
        return set()


async def _may_develop() -> Optional[str]:
    if not (await _roles()) & DEV_ROLES:
        return "Only a Developer or a Project Admin of this project migrates a module. Ask one of them."
    return None


async def _audit(event_type: str, module_id: str, payload: dict) -> None:
    from shared.audit.models import AuditEventPayload  # noqa: PLC0415
    from shared.audit.service import audit_service  # noqa: PLC0415

    tenant, project, user = _scope()
    if tenant:
        await audit_service.emit(AuditEventPayload(
            tenant_id=tenant, event_type=event_type, agent_type=STAGE, actor_id=user or None,
            resource_type="project", resource_id=project or None, payload={"moduleId": module_id, **payload}))


def _legacy_checkout() -> tuple[Optional[pathlib.Path], Optional[dict]]:
    from agents_orchestrator.modernization_common import legacy_code  # noqa: PLC0415

    project_id, run_id = legacy_code.current_scope()
    pull = legacy_code.current_pull(project_id, run_id) if project_id else None
    return (legacy_code.checkout_dir(project_id, run_id) if pull else None), pull


# ── the module's plan ───────────────────────────────────────────────────────


def _runtime_target(design: dict, module_id: str) -> str:
    for layer in design.get("layers") or []:
        if str(layer.get("layer", "")).lower() == "runtime" and module_id in (layer.get("modules") or []):
            return str(layer.get("target") or "")
    return ""


def _legacy_runtime(pull: Optional[dict], legacy_path: str) -> str:
    for m in ((pull or {}).get("profile") or {}).get("modules") or []:
        if m.get("path") == legacy_path or m.get("name") == legacy_path:
            return str(m.get("runtime") or "")
    return ""


async def _module_plan(module_id: str) -> tuple[Optional[dict], str]:
    """Everything known about one module, or why it cannot be worked on (in words)."""
    from agents_orchestrator.development_modernization_agent.toolchains import ecosystem_for, toolchain  # noqa: PLC0415
    from agents_orchestrator.modernization_common.inputs import missing_line  # noqa: PLC0415
    from agents_orchestrator.development_modernization_agent.record import traps_for  # noqa: PLC0415

    ins = await _inputs()
    for stage in (DESIGN, PLAN):
        if ins[stage].packet is None:
            return None, missing_line(ins[stage])
    try:
        rows = await _ledger_rows()
    except Exception:  # noqa: BLE001
        logger.exception("migration development: reading the ledger failed")
        return None, "The ledger could not be read just now (a database error). Try again."
    row = rows.get(module_id)
    if row is None:
        known = ", ".join(sorted(rows)) or "none"
        return None, f"{module_id} is not on the ledger. Modules on it: {known}."
    design, plan = ins[DESIGN].stored or {}, ins[PLAN].stored or {}
    dmod = next((m for m in design.get("modules") or [] if m.get("module_id") == module_id), {})
    contracts = [c for c in design.get("frozen_contracts") or [] if c.get("id") in (row.get("contractIds") or dmod.get("contract_ids") or [])]
    traps = [t for t in design.get("traps") or [] if module_id in (t.get("affects") or [])]
    criteria = [c for c in plan.get("equivalence_criteria") or [] if c.get("module_id") in (module_id, "all")]
    wave = next((w for w in plan.get("waves") or [] if w.get("id") == row.get("wave")), {})
    baseline = ins[BASELINE]
    placed = [p for p in ((baseline.stored or {}).get("placements") or []) if p.get("module_id") == module_id]
    _checkout, pull = _legacy_checkout()
    target_runtime = _runtime_target(design, module_id)
    eco = ecosystem_for(target_runtime) or ecosystem_for(_legacy_runtime(pull, row.get("legacyPath") or ""))
    plan_item = {
        "module_id": module_id, "name": row.get("moduleName"), "legacy_path": row.get("legacyPath"),
        "state": row.get("state"), "tier": row.get("tier") or dmod.get("tier"),
        "patterns": row.get("patterns") or dmod.get("patterns") or [], "wave": row.get("wave"),
        "wave_starts": wave.get("starts"), "wave_ends": wave.get("ends"),
        "contracts": contracts, "traps": traps, "trap_ids": traps_for(design, module_id),
        "criteria": criteria, "adr_ids": row.get("adrIds") or dmod.get("adr_ids") or [],
        "baseline_ids": row.get("baselineIds") or [],
        "baseline_accepted": _approved(baseline) and bool(placed) and row.get("state") not in ("sequenced", "designed", "assessed"),
        "baseline_version": baseline.version, "target_runtime": target_runtime,
        "legacy_runtime": _legacy_runtime(pull, row.get("legacyPath") or ""), "ecosystem": eco,
        "toolchain": bool(toolchain(eco)), "target_branch": row.get("targetBranch"), "pr_url": row.get("prUrl"),
        "design_version": ins[DESIGN].version, "plan_version": ins[PLAN].version,
        "design_label": ins[DESIGN].label, "plan_label": ins[PLAN].label,
        "design_approved": _approved(ins[DESIGN]), "plan_approved": _approved(ins[PLAN]),
    }
    return plan_item, ""


@tool
async def get_ledger() -> str:
    """Every module on the migration ledger: state, wave, tier, patterns, baselines and pull request.
    A module is migrated once its baseline is accepted (state baselined)."""
    try:
        rows = await _ledger_rows()
    except Exception:  # noqa: BLE001
        logger.exception("migration development: reading the ledger failed")
        return "The ledger could not be read just now (a database error). Try again."
    if not rows:
        return "No module is on the ledger yet: the target design and the migration plan are approved first."
    lines = ["| Module | State | Wave | Tier | Patterns | Baselines | Pull request |", "|---|---|---|---|---|---|---|"]
    for m, r in sorted(rows.items()):
        lines.append(f"| {m} {r['moduleName']} | {r['state']} | {r.get('wave') or '—'} | {r.get('tier') or '—'} | "
                     f"{', '.join(r.get('patterns') or []) or '—'} | {', '.join(r.get('baselineIds') or []) or '—'} | "
                     f"{r.get('prUrl') or '—'} |")
    return "\n".join(lines)


@tool
async def get_module_plan(module_id: str) -> str:
    """One module's plan: tier, patterns, wave and dates, frozen contracts (CT-xx), traps (TR-xx), equivalence
    criteria (EC-xx), whether its behaviour baseline is ACCEPTED, the target runtime and the toolchain.
    Call it before working on a module."""
    item, why = await _module_plan(module_id)
    if item is None:
        return why
    lines = [f"# {module_id} {item['name']} — `{item['legacy_path']}/`", "",
             f"State **{item['state']}**, tier **{item['tier'] or '—'}**, patterns {', '.join(item['patterns']) or '—'}, "
             f"wave {item['wave'] or '—'} ({item['wave_starts'] or '?'} → {item['wave_ends'] or '?'}).",
             f"From {item['design_label']} and {item['plan_label']}.",
             f"Runtime: {item['legacy_runtime'] or 'legacy runtime not profiled'} → {item['target_runtime'] or 'not stated in the design'}"
             f" ({'toolchain available: ' + item['ecosystem'] if item['toolchain'] else 'no catalogued toolchain: rewrite file by file, build commands unavailable'}).",
             f"Baseline: {'ACCEPTED, ' + ', '.join(item['baseline_ids']) if item['baseline_accepted'] else 'NOT accepted — the module cannot be migrated until Equivalence Testing has an accepted baseline for it'}.",
             ""]
    if item["contracts"]:
        lines += ["Frozen contracts (kept byte for byte):"] + [
            f"- {c['id']} {c.get('name')} ({c.get('kind')}): {c.get('legacy_location') or c.get('location') or ''}" for c in item["contracts"]]
    if item["traps"]:
        lines += ["Traps to handle (say where in the record):"] + [
            f"- {t['id']} {t.get('change')}: {t.get('effect')} — {t.get('where') or ''}" for t in item["traps"]]
    if item["criteria"]:
        lines += ["Equivalence criteria it is proven against:"] + [
            f"- {c['id']} {c.get('observable')} ({c.get('comparison')})" for c in item["criteria"]]
    if item["adr_ids"]:
        lines.append("ADRs: " + ", ".join(item["adr_ids"]))
    if item["tier"] == "manual":
        lines += ["", "MANUAL tier: do not migrate it. Record it as blocked with what a person must redesign."]
    if item["pr_url"]:
        lines += ["", f"Pull request: {item['pr_url']}"]
    return "\n".join(lines)


# ── the workspace ───────────────────────────────────────────────────────────


def _mdir(module_id: str) -> pathlib.Path:
    _tenant, project, _user = _scope()
    return W.module_dir(project, module_id)


def _open_state(module_id: str) -> tuple[Optional[dict], Optional[pathlib.Path], str]:
    try:
        mdir = _mdir(module_id)
    except W.WorkspaceError as exc:
        return None, None, str(exc)
    state = W.read_state(mdir)
    if state is None or not (mdir / "repo" / ".git").is_dir():
        return None, None, f"There is no workspace for {module_id} yet — open it first."
    return state, mdir, ""


async def _target():
    """(Target, row) of the project's configured target repository, or RemoteError."""
    from agents_orchestrator.development_modernization_agent.remote import RemoteError, target_of  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import repository_roles as rr  # noqa: PLC0415

    tenant, project, _user = _scope()
    async with get_db_session_for_tenant(tenant) as db:
        roles = await rr.get_roles(db, project)
    row = roles.get("target")
    if row is None:
        raise RemoteError("No target repository is set for this project. A Project Admin sets it in the project's "
                          "repository settings (Programme → Repositories): an empty GitHub or Azure DevOps "
                          "repository the migrated code goes to.")
    return target_of(row), row


@tool
async def open_target_workspace(module_id: str, override_wave_order: bool = False) -> str:
    """Start (or resume) migrating a module: clone the TARGET repository on branch migrate/<module>. An
    in-place upgrade copies the legacy module in unchanged as the first commit. Only once the module's
    baseline is accepted. Set override_wave_order only when the user explicitly asks to start a module
    whose wave has not started."""
    from agents_orchestrator.development_modernization_agent.remote import RemoteError, credential  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    if (why := _page_only()) or (why := await _may_develop()):
        return why
    item, why = await _module_plan(module_id)
    if item is None:
        return why
    if item["tier"] == "manual":
        return (f"{module_id} is MANUAL tier: it is not migrated by the agent. Record it as blocked with what a "
                "person must redesign and why.")
    if not item["baseline_accepted"]:
        return (f"Not yet: {module_id}'s behaviour baseline is not accepted. The baseline must exist before the "
                "code changes, or nothing can prove the migration — Equivalence Testing records it and QA accepts it.")
    if item["state"] not in ("baselined", "migrating"):
        return f"{module_id} is {item['state']}; a module is migrated from baselined (or resumed while migrating)."
    today = datetime.now(timezone.utc).date().isoformat()
    if item["wave_starts"] and item["wave_starts"] > today and not override_wave_order and item["state"] == "baselined":
        return (f"{module_id}'s wave {item['wave']} starts {item['wave_starts']}. Say so to the user; start it early "
                "only if they explicitly override the wave order.")
    checkout, pull = _legacy_checkout()
    copy = "in_place_upgrade" in (item["patterns"] or [])
    if copy and checkout is None:
        return "The legacy code has not been pulled for this project; pull it first (the Pull legacy code button)."
    try:
        target, _row = await _target()
        secret = await credential(target)
    except RemoteError as exc:
        return str(exc)
    mdir = _mdir(module_id)
    holder = uuid.uuid4().hex
    if not W.acquire(mdir, holder):
        return f"Another action is running on {module_id}'s workspace; wait for it."
    try:
        _t, _p, user = _scope()
        try:
            state = await asyncio.to_thread(
                W.open_workspace, mdir, git_url=target.git_url, base_branch=target.branch, module_id=module_id,
                module_path=item["legacy_path"], legacy_checkout=checkout, legacy_commit=(pull or {}).get("commit") or "",
                copy_legacy=copy, secret=secret, requested_by=user)
        except W.WorkspaceError as exc:
            shutil.rmtree(mdir / "repo", ignore_errors=True)
            return f"The workspace could not be opened: {exc}"
        state.update(ecosystem=item["ecosystem"], target_runtime=item["target_runtime"], tier=item["tier"],
                     patterns=item["patterns"])
        W.write_state(mdir, state)
    finally:
        W.release(mdir, holder)
    if item["state"] == "baselined":
        tenant, project, user = _scope()
        try:
            async with get_db_session_for_tenant(tenant) as db:
                await ledger.migration_started(db, project_id=project, module_id=module_id,
                                               target_branch=state["branch"], target_path=state["module_path"],
                                               actor=user or None)
        except ledger.LedgerRefused as exc:
            return f"The workspace is open, but the ledger refused to mark {module_id} migrating: {exc}"
        await _audit("modernization.migration_started", module_id, {"branch": state["branch"]})
    lines = [f"Workspace open for {module_id} on branch `{state['branch']}` (from `{state['base_branch']}` of the target "
             f"repository{' — empty until now, so this branch starts it' if state.get('base_created') else ''}).",
             f"Target runtime: {item['target_runtime'] or 'not stated'}; toolchain: {item['ecosystem'] or 'none catalogued'}."]
    if state.get("commits"):
        lines.append("Commits so far: " + "; ".join(f"{c['concern']}: {c['message']}" for c in state["commits"]))
    return "\n".join(lines)


@tool
async def list_upgrade_recipes(module_id: str) -> str:
    """The upgrade recipes catalogued for this module's toolchain, with their pinned versions."""
    from agents_orchestrator.development_modernization_agent.toolchains import toolchain  # noqa: PLC0415

    state, _mdir_, why = _open_state(module_id)
    if state is None:
        return why
    chain = toolchain(state.get("ecosystem") or "")
    if chain is None or not chain.recipes:
        return (f"No upgrade recipe is catalogued for {state.get('ecosystem') or 'this ecosystem'}. Rewrite the module "
                "file by file, reading each legacy file first.")
    return "\n".join([f"Recipes for {chain.runtime} (run in the sandbox, pinned):"] +
                     [f"- {r.id}: {r.tool} {r.version} — {r.describes} (from {r.from_runtime})" for r in chain.recipes])


@tool
async def run_upgrade_recipe(module_id: str, recipe_id: str) -> str:
    """Run one catalogued recipe over the module in the sandbox, then commit what it changed (code as a
    recipe commit; any build file it touched as its own build commit). Returns the changed files."""
    from agents_orchestrator.development_modernization_agent import sandbox  # noqa: PLC0415
    from agents_orchestrator.development_modernization_agent.toolchains import argv, image_for, toolchain  # noqa: PLC0415

    if (why := _page_only()) or (why := await _may_develop()):
        return why
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    chain = toolchain(state.get("ecosystem") or "")
    recipe = chain.recipe(recipe_id) if chain else None
    if recipe is None:
        return f"{recipe_id!r} is not a catalogued recipe for this module; list the recipes first."
    holder = uuid.uuid4().hex
    if not W.acquire(mdir, holder):
        return f"Another action is running on {module_id}'s workspace; wait for it."
    try:
        repo = mdir / "repo"
        if W.pending(repo):
            return "There are uncommitted changes; commit them (build or fix) before running a recipe."
        try:
            result = await asyncio.to_thread(sandbox.run, image_for(chain), repo,
                                             argv(recipe.argv, state["module_path"]), writable=True, label=module_id)
        except sandbox.SandboxUnavailable as exc:
            return f"The recipe could not run: {exc}"
        changed = W.pending(repo)
        outside = rules.out_of_bounds(changed, state["module_path"])
        if outside:  # a recipe scoped to the module never should; refuse to keep it
            W.git(repo, "checkout", "--", ".")
            W.git(repo, "clean", "-fdq")
            return "The recipe changed files outside the module and was undone: " + ", ".join(outside[:10])
        if not result.ok:
            W.git(repo, "checkout", "--", ".")
            W.git(repo, "clean", "-fdq")
            return f"The recipe failed (exit {result.exit_code}) and its changes were undone:\n{sandbox.tail(result.output, 25)}"
        code_sha = W.commit(repo, state, "recipe", f"{recipe.tool} {recipe.version} over {state['module_path']}")
        build_sha = W.commit(repo, state, "build", f"build files {recipe.tool} changed")
        state.setdefault("recipes", []).append({"tool": recipe.tool, "version": recipe.version,
                                                "args": " ".join(recipe.argv[1:]).replace("{path}", state["module_path"]),
                                                "files": changed, "commit": code_sha or build_sha})
        W.write_state(mdir, state)
    finally:
        W.release(mdir, holder)
    if not changed:
        return f"{recipe.tool} changed nothing in {state['module_path']}/."
    return (f"{recipe.tool} {recipe.version} changed {len(changed)} file(s), committed as a recipe commit"
            f"{' (build files in their own commit)' if build_sha else ''}:\n" + "\n".join(f"- {f}" for f in changed[:40]))


@tool
async def list_target_files(module_id: str, path: str = "") -> str:
    """List files in the module's workspace (the target branch), under `path` (default: the whole repository)."""
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    repo = mdir / "repo"
    try:
        base = repo / rules.clean_path(path) if path.strip() else repo
    except rules.WriteRefused as exc:
        return str(exc)
    if not base.exists():
        return f"{path} does not exist on the branch."
    files = sorted(p.relative_to(repo).as_posix() for p in base.rglob("*")
                   if p.is_file() and ".git" not in p.relative_to(repo).parts)
    return "\n".join(files[:500]) + (f"\n…and {len(files) - 500} more" if len(files) > 500 else "") or "(empty)"


@tool
async def read_target_file(module_id: str, path: str, start_line: int = 1, max_lines: int = 300) -> str:
    """Read a file on the module's target branch (numbered lines)."""
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    try:
        rel = rules.clean_path(path)
    except rules.WriteRefused as exc:
        return str(exc)
    full = (mdir / "repo" / rel).resolve()
    if not full.is_relative_to((mdir / "repo").resolve()) or not full.is_file():
        return f"{rel} is not a file on the branch."
    lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, int(start_line))
    chunk = lines[start - 1:start - 1 + min(int(max_lines), _MAX_READ_LINES)]
    return "\n".join(f"{start + i:5d}  {line}" for i, line in enumerate(chunk)) or "(empty)"


def _write(mdir: pathlib.Path, state: dict, path: str, content: str) -> str:
    rel = rules.assert_may_write(path, state["module_path"])
    if len(content.encode("utf-8")) > _MAX_WRITE:
        raise rules.WriteRefused(f"{rel} would be over {_MAX_WRITE // 1000} kB; write a module file, not data.")
    kinds = rules.secrets_in(content)
    if kinds:
        raise rules.WriteRefused(f"NOT WRITTEN — {rel} would hold {', '.join(kinds)}. A secret is never copied: use "
                                 "the target's configuration or a vault reference (kv://…) and list it in the record.")
    full = (mdir / "repo" / rel)
    if not full.resolve().is_relative_to((mdir / "repo").resolve()):
        raise rules.WriteRefused(f"{rel} leaves the workspace.")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8", newline="")
    return rel


@tool
async def write_target_file(module_id: str, path: str, content: str) -> str:
    """Write a whole file on the module's target branch — inside the module's path, or a shared build file at
    the repository root. Read the legacy file first and keep names and behaviour recognisable. Not committed
    until commit_changes."""
    if (why := _page_only()) or (why := await _may_develop()):
        return why
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    try:
        rel = _write(mdir, state, path, content)
    except rules.WriteRefused as exc:
        return str(exc)
    return f"Wrote {rel} ({len(content.splitlines())} lines). Commit it with commit_changes (fix for code, build for build files)."


@tool
async def edit_target_file(module_id: str, path: str, old: str, new: str) -> str:
    """Replace one exact, unique piece of text in a file on the module's target branch."""
    if (why := _page_only()) or (why := await _may_develop()):
        return why
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    try:
        rel = rules.assert_may_write(path, state["module_path"])
    except rules.WriteRefused as exc:
        return str(exc)
    full = mdir / "repo" / rel
    if not full.is_file():
        return f"{rel} is not a file on the branch."
    text = full.read_text(encoding="utf-8")
    count = text.count(old) if old else 0
    if count != 1:
        return f"The text to replace occurs {count} times in {rel}; give a piece that occurs exactly once."
    try:
        _write(mdir, state, rel, text.replace(old, new))
    except rules.WriteRefused as exc:
        return str(exc)
    return f"Edited {rel}. Commit it with commit_changes."


@tool
async def commit_changes(module_id: str, concern: str, message: str) -> str:
    """Commit the pending changes of ONE concern: concern="build" commits build files only (Dockerfile,
    requirements, pyproject, CI…); concern="fix" commits code only. Say what changed and why in message."""
    if (why := _page_only()) or (why := await _may_develop()):
        return why
    if concern not in ("build", "fix"):
        return "concern is build (build files) or fix (code)."
    if not (message or "").strip():
        return "Give a commit message: what changed and why."
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    repo = mdir / "repo"
    sha = W.commit(repo, state, concern, message)
    W.write_state(mdir, state)
    left = W.pending(repo)
    if sha is None:
        return (f"Nothing of concern {concern} to commit." + (f" Pending: {', '.join(left[:10])}." if left else ""))
    return f"Committed {sha[:10]} ({concern}: {message.strip()})." + (
        f" Still uncommitted (another concern): {', '.join(left[:10])}." if left else "")


# ── building and checking ───────────────────────────────────────────────────


async def _check(module_id: str, kind: str) -> str:
    """Run the toolchain's build, tests or lint in the sandbox; recorded in the workspace state."""
    from agents_orchestrator.development_modernization_agent import sandbox  # noqa: PLC0415
    from agents_orchestrator.development_modernization_agent.toolchains import argv, image_for, toolchain  # noqa: PLC0415

    if (why := _page_only()) or (why := await _may_develop()):
        return why
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    chain = toolchain(state.get("ecosystem") or "")
    if chain is None:
        return (f"No toolchain is catalogued for {state.get('ecosystem') or 'this module'}, so it cannot be {kind} "
                "here. Say so; a person builds it, and the record says the build was not run.")
    holder = uuid.uuid4().hex
    if not W.acquire(mdir, holder):
        return f"Another action is running on {module_id}'s workspace; wait for it."
    try:
        repo = mdir / "repo"
        if W.pending(repo):
            return "There are uncommitted changes; commit them first (fix for code, build for build files)."
        builds = state.setdefault("builds", [])
        if kind == "build" and len(builds) >= MAX_ROUNDS:
            return (f"Five build rounds are used ({'green' if builds[-1]['ok'] else 'still red'} last). The loop is "
                    "capped: record the module (build_failed if it is red) and say exactly what is failing.")
        head = W.head(repo)
        if kind == "tests" and not list((repo / state["module_path"]).rglob(chain.test_marker)):
            state["tests"] = {"status": "not_run", "head": head, "note": "the module has no tests"}
            W.write_state(mdir, state)
            return "The module has no tests, so tests were not run (recorded as not run, never as passed)."
        template = {"build": chain.build, "tests": chain.test, "lint": chain.lint}[kind]
        try:
            result = await asyncio.to_thread(sandbox.run, image_for(chain), repo, argv(template, state["module_path"]),
                                             label=module_id)
        except sandbox.SandboxUnavailable as exc:
            return f"The {kind} could not run: {exc}"
        at = datetime.now(timezone.utc).isoformat()
        failing = None if result.ok else sandbox.tail(result.output, 30)
        if kind == "build":
            builds.append({"round": len(builds) + 1, "ok": result.ok, "failing": failing, "head": head, "at": at,
                           "seconds": result.seconds})
        else:
            state[kind] = {"status": "green" if result.ok else "red", "head": head, "at": at,
                           "failing": failing}
        W.write_state(mdir, state)
    finally:
        W.release(mdir, holder)
    if kind == "build":
        n = len(state["builds"])
        if result.ok:
            return f"Build round {n} of {MAX_ROUNDS}: GREEN ({result.seconds}s)."
        return (f"Build round {n} of {MAX_ROUNDS}: RED. {MAX_ROUNDS - n} round(s) left.\n{failing}")
    return f"{kind.capitalize()}: {'GREEN' if result.ok else 'RED'}." + ("" if result.ok else f"\n{failing}")


@tool
async def run_build(module_id: str) -> str:
    """Build the module in the sandbox (one round of at most five). Commit your changes first."""
    return await _check(module_id, "build")


@tool
async def run_tests(module_id: str) -> str:
    """Run the module's own tests in the sandbox (a module without tests is recorded as not run)."""
    return await _check(module_id, "tests")


@tool
async def run_lint(module_id: str) -> str:
    """Lint the module in the sandbox."""
    return await _check(module_id, "lint")


# ── the equivalence preview (a hint) ────────────────────────────────────────


@tool
async def preview_equivalence(module_id: str) -> str:
    """Run the legacy system with this module replaced by the workspace's, once, in the sandbox, and
    compare the module's scenarios with the ACCEPTED baseline (ignoring what the legacy itself varies in
    and what the criteria normalize). A hint before the pull request — never the verdict. Masked shapes only."""
    from agents_orchestrator.development_modernization_agent import preview as PV  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.sandbox import profile as P  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.sandbox import runner  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.store import LocalBaselineStore  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.tools.equivalence_tools import _load_profile  # noqa: PLC0415

    if (why := _page_only()) or (why := await _may_develop()):
        return why
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    item, why = await _module_plan(module_id)
    if item is None:
        return why
    if not item["baseline_accepted"]:
        return f"{module_id} has no accepted baseline to compare with."
    baseline = (await _inputs())[BASELINE].stored or {}
    capture_id = (baseline.get("capture") or {}).get("id")
    _t, project, _u = _scope()
    store = LocalBaselineStore()
    try:
        manifest = store.read_manifest(project, capture_id or "")
    except ValueError:
        manifest = None
    if not manifest or not (store.capture_dir(project, capture_id) / "run1").is_dir():
        return "The accepted baseline's recordings are not in the baseline store any more, so there is nothing to compare."
    profile, problems, _source, legacy = _load_profile()
    if profile is None or problems or legacy is None:
        return "The capture profile cannot be used: " + "; ".join(problems[:5])
    ec_ids = [c["id"] for c in item["criteria"]]
    scenario_ids = PV.module_scenarios(baseline.get("mapping") or {}, ec_ids)
    if not scenario_ids:
        return f"The baseline maps no scenario to {module_id}'s criteria, so there is nothing to preview."
    holder = uuid.uuid4().hex
    if not W.acquire(mdir, holder):
        return f"Another action is running on {module_id}'s workspace; wait for it."
    work = mdir / "preview"
    try:
        repo = mdir / "repo"
        if W.pending(repo):
            return "There are uncommitted changes; commit them first, so the preview describes a commit."
        taken = await asyncio.to_thread(PV.overlay, legacy, repo, state["module_path"], work / "overlay")
        checked, problems = P.validate(profile, work / "overlay")
        if problems:
            return "The migrated module cannot run in the sandbox as it is:\n" + "\n".join(f"- {p}" for p in problems[:8])
        preview_id = f"prv-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        try:
            await asyncio.to_thread(runner.capture, work / "overlay", checked, work / "out", preview_id, 1)
        except runner.CaptureFailed as exc:  # the harness speaks of "the legacy service"; here it is the migrated one
            reason = str(exc).replace("The legacy service", "The service with the migrated module")
            return (f"The preview could not run the migrated system: {reason} A container still running but not "
                    "answering usually means every request fails; one that exited, that it cannot start on this image.")
        scenarios = [s for s in checked["scenarios"] if s["id"] in scenario_ids]
        noise = {s["id"]: sorted((s.get("varying") or {}).keys()) for s in baseline.get("scenarios") or []}
        criteria = {c["id"]: c for c in item["criteria"]}
        rules_by = {sid: [r for ec, scs in (baseline.get("mapping") or {}).items() if sid in scs and ec in criteria
                          for r in criteria[ec].get("normalization") or []] for sid in scenario_ids}
        result = await asyncio.to_thread(PV.compare, store.capture_dir(project, capture_id) / "run1",
                                         work / "out" / "run1", scenarios, noise, rules_by)
        cases = sum(r["cases"] for r in result.values())
        diffs = {f"{sid}:{f}" for sid, r in result.items() for f in r["differences"]}
        state["preview"] = {"head": W.head(repo), "at": datetime.now(timezone.utc).isoformat(),
                            "baseline_version": item["baseline_version"], "scenarios": result,
                            "headline": (f"{cases} case(s) identical to the baseline after normalization" if not diffs
                                         else f"{len(diffs)} field(s) differ from the baseline in {cases} case(s)")}
        W.write_state(mdir, state)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        W.release(mdir, holder)
    return PV.summary_markdown(result, taken)


# ── recording ───────────────────────────────────────────────────────────────


async def _persist(artifact: dict) -> str:
    from config.ws_helper import get_run_id, get_tenant_id  # noqa: PLC0415

    run_id = get_run_id()
    if not run_id:
        return "Not saved: this conversation is not attached to a run."
    try:
        from shared.services.artifact_service import persist_artifact  # noqa: PLC0415

        await persist_artifact(str(run_id), STAGE, artifact, tenant_id=get_tenant_id() or None)
        return "Saved to the project as the module's current migration record."
    except Exception as exc:  # noqa: BLE001
        logger.exception("migration development: persisting the record failed")
        return f"Not saved ({type(exc).__name__}) — the record below is still complete."


def build_artifact(*, module_id: str, outcome: str, item: dict, state: Optional[dict], file_map: list, rewritten: list,
                   traps_handled: dict, vault_references: list, follow_ups: list, handoff_note: Optional[str],
                   commits: list, changed: list, head: Optional[str], sources: dict, system_name: str,
                   notes: list, recorded_at: Optional[str], session: str = "") -> dict:
    """The stored record (`MigrationArtifact`) — ONE builder, for the record tool and the view fixtures."""
    from agents_orchestrator.development_modernization_agent.record import build_result  # noqa: PLC0415
    from shared.models.artifacts import MigrationArtifact  # noqa: PLC0415

    st = state or {}
    blocked = outcome == "blocked"
    return MigrationArtifact(
        module_id=module_id, outcome=outcome, legacy_module_path=item["legacy_path"],
        target_branch=None if blocked else st.get("branch"), pr_url=None,
        recipes=[] if blocked else [{"tool": r["tool"], "version": r["version"], "args": r.get("args", "")} for r in st.get("recipes") or []],
        file_map=[] if blocked else file_map, llm_rewritten=[] if blocked else rewritten,
        traps_handled=traps_handled, vault_references=vault_references,
        build=build_result(st) if not blocked else {"status": "not_run", "rounds": 0, "failing": None},
        manual_follow_ups=follow_ups, handoff_note=handoff_note,
        module={k: item.get(k) for k in ("name", "tier", "patterns", "wave", "baseline_ids", "trap_ids", "target_runtime",
                                        "legacy_runtime", "ecosystem")},
        sources=sources, base_branch=st.get("base_branch"), base_sha=st.get("base_sha"), head_sha=head,
        commits=commits, changed_files=changed, tests=st.get("tests"), lint=st.get("lint"),
        preview=({k: st["preview"][k] for k in ("headline", "scenarios", "baseline_version", "head")}
                 if st.get("preview") and st["preview"].get("head") == head else None),
        notes=notes, recorded_at=recorded_at, system_name=system_name, agent_session_id=session or None,
    ).model_dump(mode="json")


@tool
async def record_module_migration(module_id: str, outcome: str, file_map: Optional[list] = None,
                                  llm_rewritten: Optional[list] = None, traps_handled: Optional[dict] = None,
                                  vault_references: Optional[list] = None, manual_follow_ups: Optional[list] = None,
                                  handoff_note: Optional[str] = None) -> str:
    """Record the module's migration as the next version (one version = one module).

    Args:
        outcome: ready_for_review (build green, tests and lint not red, every trap handled) | build_failed (red
            after the rounds, say what fails in manual_follow_ups) | blocked (manual tier: no code, handoff_note says
            what a person must redesign and why).
        file_map: EVERY legacy file of the module: {"legacy_path", "disposition": mapped|merged|dropped,
            "target_path" (mapped/merged), "reason" (dropped)}.
        llm_rewritten: [{"file": target path, "reason"}] for what you rewrote by hand.
        traps_handled: {"TR-01": "claims-api/server.py:31 py2_round()"} — every trap the design lists for the module.
        vault_references: secrets the target needs, as references (kv://…), never values.
    The recipes, the build, tests, lint, commits and head are taken from the workspace — not from you."""
    from agents_orchestrator.development_modernization_agent import record as R  # noqa: PLC0415
    from agents_orchestrator.development_modernization_agent.migration_document import migration_markdown  # noqa: PLC0415
    from agents_orchestrator.modernization_common.handover.emit import migration_packet  # noqa: PLC0415
    from agents_orchestrator.modernization_common.versions import freeze_version, saved_line  # noqa: PLC0415
    from config.ws_helper import get_session_id  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415

    if (why := _page_only()) or (why := await _may_develop()):
        return why
    if outcome not in ("ready_for_review", "build_failed", "blocked"):
        return "outcome is ready_for_review, build_failed or blocked."
    item, why = await _module_plan(module_id)
    if item is None:
        return why
    if outcome != "blocked" and item["state"] not in ("baselined", "migrating"):
        return f"{module_id} is {item['state']}; a migration is recorded while the module is being migrated."
    if outcome == "blocked" and item["state"] in ("blocked", "retired", "cut_over", "verified"):
        return f"{module_id} is {item['state']}; it is not blocked from there."
    file_map, llm_rewritten = list(file_map or []), list(llm_rewritten or [])
    traps_handled, vault_references = dict(traps_handled or {}), list(vault_references or [])
    state, mdir, _why = _open_state(module_id)
    if outcome != "blocked" and state is None:
        return f"There is no workspace for {module_id}; open it and migrate before recording."
    checkout, _pull = _legacy_checkout()
    legacy_files = W.files_under(checkout, item["legacy_path"]) if checkout else []
    if outcome != "blocked" and not legacy_files:
        return "The legacy module's files cannot be listed (pull the legacy code), so the file map cannot be checked."
    head, changed, pending, target_files, commits, texts = None, [], [], [], [], {}
    if state is not None:
        repo = mdir / "repo"
        head, changed, pending = W.head(repo), W.changed_files(repo, state["base_sha"]), W.pending(repo)
        target_files = W.git(repo, "ls-files").splitlines()
        commits = W.commits_since(repo, state["base_sha"])
        for rel in changed:
            path = repo / rel
            if path.is_file() and path.stat().st_size < 2_000_000:
                texts[rel] = path.read_bytes().decode("utf-8", errors="ignore")
        state["head"] = head
    problems = R.check(outcome=outcome, module_path=item["legacy_path"], legacy_files=legacy_files, file_map=file_map,
                       changed=changed if state else [], target_files=target_files, rewritten=llm_rewritten,
                       traps_for_module=item["trap_ids"], traps_handled=traps_handled,
                       vault_references=vault_references, state=state or {}, pending=pending, secret_hits=R.scan(texts))
    if problems:
        return "NOT RECORDED — " + "\n".join(f"- {p}" for p in problems[:14])
    base = await _inputs()
    sources = {key: {"version": base[stage].version, "status": base[stage].status}
               for key, stage in (("design", DESIGN), ("plan", PLAN), ("baseline", BASELINE))}
    try:
        artifact = build_artifact(
            module_id=module_id, outcome=outcome, item=item, state=state, file_map=file_map, rewritten=llm_rewritten,
            traps_handled=traps_handled, vault_references=vault_references, follow_ups=list(manual_follow_ups or []),
            handoff_note=handoff_note, commits=commits, changed=changed, head=head, sources=sources,
            system_name=str((base[DESIGN].stored or {}).get("system_name") or ""),
            notes=[f"Legacy code at {str(state.get('legacy_commit') or '')[:10]}; target branch from "
                   f"{state.get('base_branch')}."] if state else [],
            recorded_at=datetime.now(timezone.utc).isoformat(), session=str(get_session_id() or ""))
    except Exception as exc:  # noqa: BLE001 — a malformed argument the model sent
        return f"NOT RECORDED — the record could not be built: {type(exc).__name__}: {str(exc)[:300]}"
    handover = migration_packet(artifact, {"version": 1, "status": "draft"})
    if not handover.ok:
        return "NOT RECORDED — " + "\n".join(f"- {p}" for p in handover.problems[:14])
    if state is not None:
        W.write_state(mdir, state)
    if outcome == "blocked":
        tenant, project, user = _scope()
        try:
            async with get_db_session_for_tenant(tenant) as db:
                await ledger.block(db, project_id=project, module_id=module_id, agent=STAGE,
                                   reason=f"Manual migration needed: {handoff_note}"[:2000], actor=user or None)
        except ledger.LedgerRefused as exc:
            return f"NOT RECORDED — the ledger refused to block {module_id}: {exc}"
    saved = await _persist(artifact)
    version = await freeze_version(STAGE, artifact)
    await _audit("modernization.migration_recorded", module_id, {"outcome": outcome, "head": head, "version": version})
    return f"{migration_markdown(artifact)}\n\n_{saved_line(saved, version, 'migration record')}_"


# ── pushing (consequential) ─────────────────────────────────────────────────


async def _newest_record(module_id: str):
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import artifact_versions as svc  # noqa: PLC0415

    tenant, project, _u = _scope()
    async with get_db_session_for_tenant(tenant) as db:
        for row in await svc.list_versions(db, project, STAGE):
            if (row.payload or {}).get("module_id") == module_id:
                return row
    return None


@tool
async def push_and_open_pr(module_id: str) -> str:
    """CONSEQUENTIAL — push the module's branch to the TARGET repository and open (or update) its pull
    request, whose description is generated from the record. Only after showing the branch, the commits
    and the pull request title, and the user's explicit yes on THIS turn. Needs the module's newest record
    accepted (ready for review) and the branch exactly as recorded."""
    from agents_orchestrator.development_modernization_agent.record import pr_body  # noqa: PLC0415
    from agents_orchestrator.development_modernization_agent.remote import RemoteError, credential, open_pull_request  # noqa: PLC0415
    from shared.authz.consequential import authorize_consequential  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services import modernization_ledger as ledger  # noqa: PLC0415
    from shared.services import repository_roles as rr  # noqa: PLC0415

    if (why := _page_only()) or (why := await _may_develop()):
        return why
    ok, why = await authorize_consequential(
        STAGE, action="Pushing the migrated module to the target repository and opening its pull request",
        ask="show the branch, the commits and the pull request title and body, and ask the user to go ahead.")
    if not ok:
        return why
    state, mdir, why = _open_state(module_id)
    if state is None:
        return why
    row = await _newest_record(module_id)
    if row is None:
        return f"{module_id} has no migration record yet; record it first."
    record = row.payload or {}
    if record.get("outcome") != "ready_for_review":
        return f"The newest record (v{row.version}) is {record.get('outcome')}; only a module ready for review is pushed."
    if row.status not in ("published", "granted"):
        return (f"The newest record (v{row.version}) is not accepted yet. A Developer who did not record it, or a "
                "Project Admin, accepts it on the Migration Development page; then it is pushed.")
    repo = mdir / "repo"
    if W.pending(repo) or W.head(repo) != record.get("head_sha"):
        return ("The branch has changed since the accepted record (or has uncommitted changes). Record it again and "
                "have it accepted; what is pushed is exactly what was accepted.")
    tenant, project, user = _scope()
    try:
        rows = await _ledger_rows()
        if rows.get(module_id, {}).get("state") != "migrating":
            return f"{module_id} is {rows.get(module_id, {}).get('state')}; a pull request is opened while it is migrating."
        target, _trow = await _target()
        async with get_db_session_for_tenant(tenant) as db:
            await rr.assert_target_write(db, tenant_id=tenant, project_id=project, stage=STAGE, remote_url=target.url)
        secret = await credential(target)
    except (RemoteError, rr.RepositoryRefused) as exc:
        return f"NOT PUSHED — {exc}"
    holder = uuid.uuid4().hex
    if not W.acquire(mdir, holder):
        return f"Another action is running on {module_id}'s workspace; wait for it."
    try:
        try:
            pushed = await asyncio.to_thread(W.push, repo, state, git_url=target.git_url, secret=secret)
        except W.WorkspaceError as exc:
            return f"NOT PUSHED — {exc}"
        title = f"Migrate {module_id} {(record.get('module') or {}).get('name') or ''} ({record['legacy_module_path']})".strip()
        try:
            pr_url = await open_pull_request(target, branch=state["branch"], base=state["base_branch"], title=title,
                                             body=pr_body(record), secret=secret)
        except RemoteError as exc:
            state["pushed"] = {"head": pushed, "at": datetime.now(timezone.utc).isoformat(), "pr_url": None}
            W.write_state(mdir, state)
            return f"The branch was pushed, but the pull request could not be opened: {exc}"
        state["pushed"] = {"head": pushed, "at": datetime.now(timezone.utc).isoformat(), "pr_url": pr_url}
        W.write_state(mdir, state)
    finally:
        W.release(mdir, holder)
    try:
        async with get_db_session_for_tenant(tenant) as db:
            await ledger.pr_opened(db, project_id=project, module_id=module_id, pr_url=pr_url, actor=user or None,
                                   artifact=ledger.ArtifactRef("migration_artifacts", row.version))
    except ledger.LedgerRefused as exc:
        return f"Pushed and opened {pr_url}, but the ledger refused to mark {module_id} in review: {exc}"
    await _audit("modernization.migration_pushed", module_id, {"head": pushed, "prUrl": pr_url, "version": row.version})
    return (f"Pushed `{state['branch']}` ({pushed[:10]}) and opened the pull request: {pr_url}\n"
            f"{module_id} is now in review: Migration Review and Security review the pull request.")


@tool
async def export_migration_document(module_id: str, filename: str = "migration.docx") -> str:
    """Export a module's newest migration record as a document (.docx, .pdf or .md)."""
    import os  # noqa: PLC0415

    from agents_orchestrator.development_modernization_agent.migration_document import migration_markdown  # noqa: PLC0415
    from agents_orchestrator.modernization_common.files import announce_generated_file, output_dir  # noqa: PLC0415
    from shared.tools.doc_export import export_result_message, normalise_filename, render_document, supported_list  # noqa: PLC0415

    row = await _newest_record(module_id)
    if row is None or not row.payload:
        return f"{module_id} has no migration record yet."
    name = normalise_filename(filename, "migration.docx")
    path = os.path.join(output_dir(FILE_SEGMENT), name)
    try:
        await render_document(migration_markdown(row.payload), path, title=name.rsplit(".", 1)[0])
    except ValueError:
        return f"Error: '{name}' has an unsupported extension. Supported: {supported_list()}"
    except Exception as exc:  # noqa: BLE001
        return f"Error generating '{name}' ({type(exc).__name__})."
    url = await announce_generated_file(FILE_SEGMENT, name, path, stage=STAGE)
    return export_result_message(name, url, ["The record VERSION on the page is what gets accepted."])


TOOLS = [get_ledger, get_module_plan, open_target_workspace, list_upgrade_recipes, run_upgrade_recipe,
         list_target_files, read_target_file, write_target_file, edit_target_file, commit_changes,
         run_build, run_tests, run_lint, preview_equivalence, record_module_migration, push_and_open_pr,
         export_migration_document]

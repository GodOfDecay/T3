"""preview_equivalence — a quick look at the migrated module against the ACCEPTED baseline (H8).

A HINT, NEVER A VERDICT (research §6.6). Proving equivalence is Equivalence Testing's Verify mode
(Phase J). This runs the same harness Baseline mode ran (`testing_modernization_agent/sandbox`), once,
on an OVERLAY: the legacy checkout with this module's folder — and the shared build files at the
root, when the workspace has them — replaced by the workspace's. The rest of the system stays legacy,
which is what a module-at-a-time migration runs against anyway.

Then, per scenario recording the module's criteria, run 1 of the accepted baseline against the
preview, field by field (`analysis/noise.compare`), IGNORING
  - the legacy's own noise floor: fields that differed between the baseline's two legacy runs;
  - the fields the criterion's own normalization rules cover.
What is left is a difference worth looking at now. Masked shapes only: no recorded value reaches the
model (the baseline's rule).
"""
from __future__ import annotations

import pathlib
import shutil
from typing import Iterable

from agents_orchestrator.development_modernization_agent import rules


class PreviewRefused(Exception):
    """A preview that cannot run. The message is for people."""


def overlay(legacy: pathlib.Path, repo: pathlib.Path, module_path: str, dest: pathlib.Path) -> list[str]:
    """Copy the legacy checkout to `dest` with the module (and root shared build files) taken from the
    workspace. Returns what was taken from the workspace."""
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(legacy, dest, ignore=shutil.ignore_patterns(".git"), symlinks=False)
    taken = []
    module = rules.clean_path(module_path)
    shutil.rmtree(dest / module, ignore_errors=True)
    if (repo / module).is_dir():
        shutil.copytree(repo / module, dest / module, ignore=shutil.ignore_patterns(".git", "__pycache__"),
                        symlinks=False)
        taken.append(module + "/")
    for item in repo.iterdir():
        if item.is_file() and rules.is_shared_build_file(item.name):
            shutil.copy2(item, dest / item.name)
            taken.append(item.name)
    return sorted(taken)


def module_scenarios(mapping: dict[str, list[str]], ec_ids: Iterable[str]) -> list[str]:
    """The scenarios that record this module's criteria (the baseline's own mapping)."""
    ecs = set(ec_ids)
    return sorted({s for ec, scs in (mapping or {}).items() if ec in ecs for s in scs})


def compare(baseline_run1: pathlib.Path, preview_run1: pathlib.Path, scenarios: list[dict],
            noise_fields: dict[str, list[str]], rules_by_scenario: dict[str, list[dict]]) -> dict[str, dict]:
    """{scenario: {cases, differences: {field: count}, examples: {field: [baseline, preview]}, ignored}}."""
    from agents_orchestrator.testing_modernization_agent.analysis.noise import compare as field_diff  # noqa: PLC0415
    from agents_orchestrator.testing_modernization_agent.analysis.noise import covers  # noqa: PLC0415

    raw = field_diff(baseline_run1, preview_run1, scenarios)
    out = {}
    for sc in scenarios:
        sid = sc["id"]
        found = raw.get(sid) or {"cases": 0, "varying": {}, "examples": {}}
        floor = set(noise_fields.get(sid) or [])
        rules_here = rules_by_scenario.get(sid) or []
        kept, ignored = {}, []
        for fld, count in found["varying"].items():
            if fld in floor or any(covers(str(r.get("field") or ""), fld) for r in rules_here):
                ignored.append(fld)
            else:
                kept[fld] = count
        out[sid] = {"cases": found["cases"], "differences": kept,
                    "examples": {f: found["examples"][f] for f in kept}, "ignored": sorted(ignored)}
    return out


def summary_markdown(result: dict[str, dict], taken: list[str]) -> str:
    lines = ["# Equivalence preview — a hint, not the verdict", "",
             "The legacy system with this module replaced by the workspace's (" + ", ".join(taken) + "), run "
             "once in the sandbox and compared with the ACCEPTED baseline. Fields the legacy itself varies in, "
             "and fields the criteria normalize, are ignored. Shapes only, never values.", "",
             "| Scenario | Cases | Differences |", "|---|---:|---|"]
    for sid, r in sorted(result.items()):
        diffs = ", ".join(f"{f} ({n}; {r['examples'][f][0]} vs {r['examples'][f][1]})" for f, n in r["differences"].items())
        lines.append(f"| {sid} | {r['cases']} | {diffs or 'none — identical after normalization'} |")
    clean = all(not r["differences"] for r in result.values())
    lines += ["", ("No difference in this sample. That is a hint: Equivalence Testing's verification is the "
                   "verdict." if clean else
                   "Differences above are worth fixing now (read the legacy code for the behaviour it had). "
                   "Equivalence Testing's verification is still the verdict.")]
    return "\n".join(lines)

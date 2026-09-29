"""What the assessment cannot know from the code alone — "Not assessable statically".

Research §6.2 item 2: the assessment says what it does NOT know, so Target Architecture asks
instead of assuming. Each item is a QUESTION for a person, with the modules it concerns:

    runtime        the runtime a module ACTUALLY runs on in production. A declared version is a
                   build setting; when a dependency needs a newer runtime than the one declared
                   (ClaimTrack's batch declares Java 7 but uses a Java-8-only library), the
                   declared one cannot be what production runs, and that is said specifically.
                   A module that declares no runtime at all is asked about too.
    scheduler      when batch/scheduled modules run, and in what order — held in a scheduler
                   (cron, Control-M, Windows Task Scheduler), almost never in the repository.
    configuration  environment-specific settings (connection strings, endpoints, feature flags),
                   which live in each environment, not in the code. Always present: no
                   repository answers it, and saying "none found" would read as "none exist".
    unreadable     a manifest that could not be parsed: its runtime and dependencies are unknown.

DETERMINISTIC, like the rest of the assessment: the same checkout gives the same list, in the
same order (by topic, then module id).

The minimum-runtime table is deliberately SMALL and only holds library lines whose minimum Java
version is certain; a library not in it says nothing, rather than guessing. It holds RUNTIME
libraries only: manifests are read without dependency scope, so a test-only library (JUnit) would
say something about the build JDK, not about what production runs. Guava's `-android` flavour kept
an older baseline than the JRE flavour and is skipped.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

#: (dependency-name pattern, minimum library major[.minor], Java major it requires).
#: Sources: each project's own release notes for the named version line.
_MIN_JAVA: list[tuple[re.Pattern[str], tuple[int, ...], int]] = [
    (re.compile(r"^com\.google\.guava:guava$"), (21,), 8),
    (re.compile(r"^org\.springframework:spring-"), (6,), 17),
    (re.compile(r"^org\.springframework:spring-"), (5,), 8),
    (re.compile(r"^org\.springframework\.boot:"), (3,), 17),
    (re.compile(r"^org\.springframework\.boot:"), (2,), 8),
    (re.compile(r"^org\.apache\.commons:commons-lang3$"), (3, 9), 8),
    (re.compile(r"^org\.apache\.logging\.log4j:log4j-core$"), (2, 13), 8),
    (re.compile(r"^org\.hibernate(\.orm)?:hibernate-core$"), (6,), 11),
    (re.compile(r"^org\.hibernate:hibernate-core$"), (5, 2), 8),
]

_BATCH_RE = re.compile(r"(?i)(?:^|[^a-z])(batch|jobs?|scheduler|cron|nightly|worker)(?:$|[^a-z])")
_SCHEDULER_FILES = re.compile(r"(?i)^(crontab|.*\.cron|quartz\.properties|quartz_jobs\.xml|.*\.jobs?\.ya?ml)$")
_ENV_CONFIG_FILES = re.compile(
    r"(?i)^(appsettings\.[a-z0-9_-]+\.json|application-[a-z0-9_-]+\.(properties|ya?ml)"
    r"|web\.[a-z0-9_-]+\.config|\.env(\.[a-z0-9_-]+)?|config\.[a-z0-9_-]+\.(json|ya?ml))$"
)
#: Build output and dependency caches — never where a team keeps its schedules or environment
#: files. `bin` and `packages` are NOT here: a legacy `bin/crontab` or a monorepo's `packages/*`
#: hold exactly those.
_SKIP_DIRS = {".git", "node_modules", "obj", "target", "dist", ".venv", "venv", "__pycache__"}


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value or "")
    return tuple(int(p) for p in parts[:2])


def _java_needed(dependencies: Iterable) -> tuple[int, str] | None:
    """The highest Java major the module's dependencies require, and which dependency."""
    best: tuple[int, str] | None = None
    for dep in dependencies:
        if getattr(dep, "kind", "package") != "package":
            continue
        version = _version_tuple(dep.version)
        if not version or "android" in (dep.version or "").lower():
            continue
        for pattern, minimum, java in _MIN_JAVA:
            if pattern.search(dep.name) and version >= minimum:
                if best is None or java > best[0]:
                    best = (java, f"{dep.name} {dep.version}")
                break  # the first (highest) matching line for this pattern decides
    return best


def _files(root: Path) -> list[str]:
    """Every file outside build output and caches, pruning those directories as it walks."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        rel = Path(dirpath).relative_to(root)
        out.extend((rel / f).as_posix() for f in sorted(filenames))
    return sorted(out)


def _id_key(row: dict) -> tuple[int, str]:
    """M-02 before M-10 before M-100 — by number, not by string."""
    digits = re.sub(r"\D", "", str(row.get("id") or ""))
    return (int(digits) if digits else 0, str(row.get("id")))


def not_assessable(root: Path, modules: list[dict], manifests: dict) -> list[dict]:
    """The questions the code cannot answer, as [{topic, modules: [M-xx], question}].

    `modules` are the assessment's module rows (with `id`, `name`, `path`, `runtime`,
    `parse_error`); `manifests` maps module name → ManifestFacts (for dependency versions).
    """
    items: list[dict] = []
    by_id = sorted(modules, key=_id_key)

    # runtime — a mismatch first (specific), then the undeclared.
    for row in by_id:
        runtime = row.get("runtime") or {}
        facts = manifests.get(row["name"])
        if runtime.get("name") == "Java" and facts is not None:
            declared = _version_tuple(runtime.get("version") or "")
            needed = _java_needed(facts.dependencies)
            if declared and needed and declared[0] < needed[0]:
                items.append({"topic": "runtime", "modules": [row["id"]], "question": (
                    f"{row['id']} ({row['name']}) declares Java {runtime.get('version')}, but depends on "
                    f"{needed[1]}, which needs Java {needed[0]} or later — so production cannot be running "
                    f"Java {runtime.get('version')}. Which Java version does it actually run on?")})
    undeclared = [r for r in by_id if not (r.get("runtime") or {}).get("version") and not r.get("parse_error")]
    if undeclared:
        items.append({"topic": "runtime", "modules": [r["id"] for r in undeclared], "question": (
            "No runtime version is declared for " + ", ".join(f"{r['id']} ({r['name']})" for r in undeclared)
            + ". Which runtime and version do they run on in production?")})

    # scheduler
    files = _files(Path(root))
    batch = [r for r in by_id if _BATCH_RE.search(r["name"]) or _BATCH_RE.search(r.get("path") or "")]
    schedules = [f for f in files if _SCHEDULER_FILES.match(f.rsplit("/", 1)[-1])]
    if batch or schedules:
        where = (f" The repository has {', '.join(schedules)}, but a scheduler's live configuration usually "
                 "differs from the copy in the code." if schedules else "")
        items.append({"topic": "scheduler", "modules": [r["id"] for r in batch], "question": (
            "When do the scheduled jobs run, in what order, and what triggers them"
            + (f" ({', '.join(r['id'] for r in batch)})" if batch else "")
            + "? That lives in the scheduler, not in the repository." + where)})

    # configuration — always asked
    env_files = [f for f in files if _ENV_CONFIG_FILES.match(f.rsplit("/", 1)[-1])]
    items.append({"topic": "configuration", "modules": [], "question": (
        "Environment-specific configuration (connection strings, endpoints, credentials, feature flags) is "
        "held in each environment, not in the code. "
        + (f"The repository has per-environment files ({', '.join(env_files[:8])}"
           + (", …" if len(env_files) > 8 else "") + "); do they match what production uses?"
           if env_files else "The repository has no per-environment files, so all of it must come from the team.")
    )})

    # unreadable manifests
    for row in by_id:
        if row.get("parse_error"):
            items.append({"topic": "unreadable", "modules": [row["id"]], "question": (
                f"{row['id']} ({row['name']}): its manifest could not be read ({row['parse_error']}), so its "
                "runtime and dependencies are unknown. What does it build with?")})
    return items

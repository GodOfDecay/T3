"""The capture profile — HOW a legacy system is run and exercised, as data (Phase G decision G1).

A profile says how to build the legacy image (the checkout's Dockerfile), what to seed, how to start
the service, which external services are stubbed, and the SCENARIOS: `http` (a JSONL request set sent
to the service) or `batch` (a command, then the files it writes). It says nothing about equivalence
criteria — a legacy repository cannot know a future plan's EC ids; the agent maps criteria to
scenarios when it plans a capture.

Where it comes from: the one saved for the project (the agent proposes it, QA confirms), else
`sdlc-sandbox.json` in the legacy checkout.

`validate(profile, checkout)` returns (normalised profile, problems). Every problem is a sentence the
agent passes on. Nothing here runs anything.
"""
from __future__ import annotations

import json
import pathlib
import posixpath
import re
from typing import Any, Optional

from agents_orchestrator.testing_modernization_agent.sandbox.images import DIGEST_RE

PROFILE_FILE = "sdlc-sandbox.json"
MAX_REQUESTS = 1000
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
#: Data a sandbox may be seeded with. "synthetic" only during development (the user's decision);
#: deterministic tokenisation of real data is a later, separate step.
DATA_KINDS = ("synthetic",)


def _inside(checkout: pathlib.Path, rel: str) -> Optional[pathlib.Path]:
    """The file `rel` inside the checkout, or None (absolute, `..`, or outside)."""
    if not isinstance(rel, str) or not rel.strip() or rel.startswith(("/", "\\")) or ":" in rel:
        return None
    root = checkout.resolve()
    path = (root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def check_dockerfile(text: str) -> list[str]:
    """Every FROM is pinned by digest (a stage name from an earlier FROM ... AS is fine)."""
    problems, stages = [], set()
    for line in text.splitlines():
        m = re.match(r"(?i)^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", line)
        if not m:
            continue
        image = m.group(1)
        if image.lower() not in stages and not DIGEST_RE.search(image):
            problems.append(f"The Dockerfile's base image {image} is not pinned by digest — write it as "
                            "name@sha256:<digest> so every capture runs the exact same runtime.")
        if m.group(2):
            stages.add(m.group(2).lower())
    if not re.search(r"(?im)^\s*FROM\s", text):
        problems.append("The Dockerfile has no FROM line.")
    return problems


def _requests(path: pathlib.Path, where: str) -> tuple[int, list[str]]:
    problems, count = [], 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return 0, [f"{where}: cannot be read ({type(exc).__name__})."]
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        count += 1
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"{where} line {n} is not JSON.")
            continue
        if not isinstance(req, dict) or str(req.get("method", "")).upper() not in _METHODS:
            problems.append(f"{where} line {n}: method must be one of {', '.join(sorted(_METHODS))}.")
        elif not str(req.get("path", "")).startswith("/"):
            problems.append(f"{where} line {n}: path must start with /.")
    if count == 0:
        problems.append(f"{where} has no requests.")
    if count > MAX_REQUESTS:
        problems.append(f"{where} has {count} requests; a scenario holds at most {MAX_REQUESTS}.")
    return count, problems


def _stub_file(path: pathlib.Path, where: str) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{where}: not a readable JSON file ({type(exc).__name__})."]
    responses = data.get("responses") if isinstance(data, dict) else None
    if not isinstance(responses, list) or not responses:
        return [f"{where}: needs a non-empty \"responses\" list."]
    problems = []
    for i, r in enumerate(responses, 1):
        if not isinstance(r, dict) or str(r.get("method", "")).upper() not in _METHODS \
                or not str(r.get("path", "")).startswith("/") or not isinstance(r.get("status", 200), int):
            problems.append(f"{where} response {i}: needs method, a path starting with / and an integer status.")
    return problems


def validate(profile: Any, checkout: pathlib.Path) -> tuple[dict, list[str]]:
    """(the profile with request counts added, problems)."""
    if not isinstance(profile, dict):
        return {}, ["The capture profile must be one JSON object."]
    p = json.loads(json.dumps(profile))
    problems: list[str] = []
    if p.get("version") != 1:
        problems.append("The capture profile needs \"version\": 1.")
    if p.get("data") not in DATA_KINDS:
        problems.append(f"The capture profile's \"data\" must be one of {', '.join(DATA_KINDS)}: during "
                        "development a sandbox is seeded with synthetic or sample data only, never real records.")

    dockerfile_rel = (p.get("build") or {}).get("dockerfile") if isinstance(p.get("build"), dict) else None
    dockerfile = _inside(checkout, dockerfile_rel or "")
    if dockerfile is None or not dockerfile.is_file():
        problems.append("build.dockerfile must name a Dockerfile inside the legacy checkout.")
    else:
        problems += check_dockerfile(dockerfile.read_text(encoding="utf-8", errors="replace"))

    writable = p.get("writable") or []
    if not isinstance(writable, list) or any(not isinstance(w, str) or not w.startswith("/") or w.strip("/") == ""
                                             for w in writable):
        problems.append("writable must list absolute directories inside the container (never /).")

    service = p.get("service")
    if service is not None:
        port = service.get("port") if isinstance(service, dict) else None
        if not isinstance(service, dict) or not str(service.get("command", "")).strip() \
                or not isinstance(port, int) or not 0 < port < 65536 \
                or not str(service.get("health", "")).startswith("/"):
            problems.append("service needs a command, a port (1–65535) and a health path starting with /.")

    stub_names = set()
    for i, s in enumerate(p.get("stubs") or [], 1):
        where = f"stub {i}"
        if not isinstance(s, dict) or not _ID_RE.match(str(s.get("name", ""))):
            problems.append(f"{where}: name must be lower-case letters, digits and dashes.")
            continue
        where = f"stub {s['name']}"
        if s["name"] in stub_names or s["name"] == "app":
            problems.append(f"{where}: the name is used twice (or is the reserved name app).")
        stub_names.add(s["name"])
        if not isinstance(s.get("port"), int) or not 0 < s["port"] < 65536:
            problems.append(f"{where}: port must be 1–65535.")
        if not _ENV_RE.match(str(s.get("env", ""))):
            problems.append(f"{where}: env must be the environment variable the legacy system reads its URL from.")
        path = _inside(checkout, s.get("responses", ""))
        if path is None or not path.is_file():
            problems.append(f"{where}: responses must name a file inside the legacy checkout.")
        else:
            problems += _stub_file(path, f"{where} ({s['responses']})")

    scenarios = p.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        problems.append("The capture profile needs at least one scenario.")
        scenarios = []
    seen = set()
    for i, sc in enumerate(scenarios, 1):
        if not isinstance(sc, dict) or not _ID_RE.match(str(sc.get("id", ""))):
            problems.append(f"scenario {i}: id must be lower-case letters, digits and dashes.")
            continue
        where = f"scenario {sc['id']}"
        if sc["id"] in seen:
            problems.append(f"{where}: the id is used twice.")
        seen.add(sc["id"])
        if sc.get("kind") == "http":
            if service is None:
                problems.append(f"{where} sends HTTP requests, so the profile needs a service.")
            path = _inside(checkout, sc.get("requests", ""))
            if path is None or not path.is_file():
                problems.append(f"{where}: requests must name a JSONL file inside the legacy checkout.")
            else:
                sc["cases"], found = _requests(path, f"{where} ({sc['requests']})")
                problems += found
        elif sc.get("kind") == "batch":
            if not str(sc.get("command", "")).strip():
                problems.append(f"{where}: a batch scenario needs a command.")
            outputs = sc.get("outputs") or []
            if not isinstance(outputs, list) or not outputs or not all(_output_ok(o) for o in outputs):
                problems.append(f"{where}: outputs must list files in a directory (a wildcard only in the file "
                                "name), like /data/out/*.txt.")
            sc["cases"] = 1
        else:
            problems.append(f"{where}: kind must be http or batch (UI journeys and load tests are not "
                            "captured in Baseline mode).")
    return p, problems


def _output_ok(glob: Any) -> bool:
    if not isinstance(glob, str) or not glob.startswith("/") or ".." in glob.split("/"):
        return False
    directory, name = output_dir_and_pattern(glob)
    # The name reaches `sh` unquoted (so it globs): letters, digits, . _ - and the wildcards only.
    return directory not in ("", "/") and "*" not in directory and "?" not in directory \
        and bool(re.fullmatch(r"[A-Za-z0-9._*?-]+", name))


def output_dir_and_pattern(glob: str) -> tuple[str, str]:
    """"/data/out/*.txt" → ("/data/out", "*.txt")."""
    return posixpath.dirname(glob) or "/", posixpath.basename(glob)


def profile_markdown(p: dict, source: str) -> str:
    lines = [f"# Capture profile ({source})", "",
             f"Data: **{p.get('data')}**. Build: `{(p.get('build') or {}).get('dockerfile')}`. "
             f"Service: {('`' + p['service']['command'] + '` on port ' + str(p['service']['port'])) if p.get('service') else 'none (batch only)'}.",
             ""]
    if p.get("stubs"):
        lines.append("External services, stubbed (the sandbox has no internet): "
                     + ", ".join(f"{s['name']} (via {s['env']})" for s in p["stubs"]) + ".")
        lines.append("")
    lines += ["| Scenario | Kind | Cases | What it does |", "|---|---|---:|---|"]
    for sc in p.get("scenarios") or []:
        lines.append(f"| {sc['id']} | {sc['kind']} | {sc.get('cases', '')} | {sc.get('describes', '')} |")
    return "\n".join(lines)

"""The rules a target design must meet that need MORE than the design itself.

`DesignPayload` (handover/packets.py) refuses what the design alone shows is wrong: a module
with no pattern, an ADR with one option, a reference to an id the design does not define.
What needs another artifact lives here (decision D7: cross-artifact rules live in the record
tool), each as a small pure function the record tool runs and the tests mutate:

  modules        every module of the PINNED assessment is designed, under the id, name, tier
                 and score THAT version gives it (D14 — ids are stable within one commit, not
                 across commits, so an id is checked against the version the design read).
  must_not_change  every must-not-change entry of the brief is frozen by a contract whose
                 `brief_item` is those words; a contract cannot claim words the brief lacks.
  contracts      each contract's location is in the legacy code; `confirmed` needs the
                 interface inventory to show it or the brief to have named it.
  traps          each trap says where in the code it bites, and that place exists.
  versions       no target is past its end of support, or within a year of it; never "latest".
  data           a changing database layer needs the data-migration plan.
  diagrams       AS-IS, TRANSITION and TO-BE are present, each a Mermaid diagram.
  questions      every question the assessment could not answer from the code is answered
                 (with its source) or kept open — never silently assumed.

Every message is the refusal the model reads and fixes from, so each names the item and says
what to do. `Notes` are true things the user should hear that do not block recording.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import PurePosixPath
from typing import Iterable, Optional

from agents_orchestrator.discovery_agent.analysis.eol import Runtime, runtime_status


@dataclass
class CheckResult:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def words(text: str) -> str:
    """The comparable form of a phrase: case, surrounding quotes and spacing ignored."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text.strip("\"'“”‘’ .").casefold()


# ── modules (D14) ────────────────────────────────────────────────────────────


def check_modules(design_modules: list[dict], assessment: dict, assessment_version: Optional[int]) -> list[str]:
    where = f"assessment v{assessment_version}" if assessment_version else "the assessment"
    commit = str(assessment.get("commit") or "")[:10]
    at = f"{where} (commit {commit})" if commit else where
    assessed = {m["id"]: m for m in assessment.get("modules") or []}
    problems = []
    for m in design_modules:
        known = assessed.get(m["module_id"])
        if known is None:
            problems.append(f"{m['module_id']} ({m['module']}) is not a module of {at}. Module ids are stable "
                            "only within one commit — use the ids of the assessment you read.")
            continue
        if words(m["module"]) != words(known["name"]):
            problems.append(f"{m['module_id']} is {known['name']} in {at}, not {m['module']} — the ids have "
                            "shifted; cite each module by the id that assessment gives it.")
            continue
        if m["tier"] != known["tier"] or int(m["risk_score"]) != int(known["score"]):
            problems.append(f"{m['module_id']} {known['name']}: tier and score are the assessment's "
                            f"({known['tier']}, {known['score']}), not ({m['tier']}, {m['risk_score']}). "
                            "Never change a score or a tier.")
    designed = {m["module_id"] for m in design_modules}
    for mid, known in sorted(assessed.items()):
        if mid not in designed:
            problems.append(f"{mid} {known['name']} has no pattern. Every assessed module needs one — a module "
                            "the brief leaves out of scope is `keep`, with the reason.")
    return problems


# ── the brief's must-not-change ──────────────────────────────────────────────


def check_must_not_change(contracts: list[dict], must_not_change: list[str]) -> list[str]:
    wanted = {words(item): item for item in must_not_change if words(item)}
    claimed = {words(c.get("brief_item") or ""): c["id"] for c in contracts if words(c.get("brief_item") or "")}
    problems = []
    for key, item in wanted.items():
        if key not in claimed:
            problems.append(f"The brief says “{item}” must not change, and no contract freezes it. Add a contract "
                            "for it with brief_item set to exactly those words, its legacy location and its proof.")
    for key, cid in claimed.items():
        if key not in wanted:
            problems.append(f"{cid} says it freezes “{key}”, which is not a must-not-change entry of the brief. "
                            "Copy the brief's words exactly, or leave brief_item empty for a contract the brief "
                            "did not name (then it is proposed until the user confirms it).")
    return problems


# ── locations in the legacy code ─────────────────────────────────────────────

_PATHISH = re.compile(r"[\w.*\-/]*[/.][\w.*\-/]+")


def _strip_line(location: str) -> str:
    return re.sub(r":\d+(?:-\d+)?$", "", location.strip().strip("`"))


def resolve(location: str, files: set[str], dirs: set[str]) -> set[str]:
    """The checkout files a location names: an exact file or folder, a glob (`sql/*.sql`), or an
    elided path (`web/.../ClaimsApiController.java`). Empty when it names nothing.

    Only ever MATCHED against the checkout's own file list (`files`, `dirs`) — nothing is opened —
    so a `../` path cannot reach outside it; it simply matches nothing."""
    loc = _strip_line(location).removeprefix("./").lstrip("/")
    if not loc:
        return set()
    if loc in files:
        return {loc}
    if loc.rstrip("/") in dirs:
        prefix = loc.rstrip("/") + "/"
        return {f for f in files if f.startswith(prefix)}
    if "..." in loc:
        pattern = re.compile("^" + ".*".join(re.escape(p) for p in loc.split("...")) + "$")
        return {f for f in files if pattern.match(f)}
    if any(ch in loc for ch in "*?["):
        return {f for f in files if fnmatch.fnmatch(f, loc)}
    return set()


def _paths_in(text: str) -> list[str]:
    return [t.rstrip(".,;)") for t in _PATHISH.findall(text or "") if "/" in t or PurePosixPath(t).suffix]


def _cited_line(location: str) -> Optional[int]:
    m = re.search(r":(\d+)(?:-\d+)?$", location.strip().strip("`"))
    return int(m.group(1)) if m else None


#: How far a cited line may be from the inventory entry that confirms it (annotations sit a
#: few lines above the method they describe).
LINE_SLACK = 5


def _shown_by_inventory(location: str, file: str, captured: dict[str, list[int]]) -> bool:
    """Does the inventory show an interface AT this location — in this file and, when a line is
    cited, within `LINE_SLACK` lines of it? Not merely "somewhere in the same file"."""
    if file not in captured:
        return False
    line = _cited_line(location)
    lines = captured[file]
    return line is None or not lines or any(abs(line - n) <= LINE_SLACK for n in lines)


def check_locations(contracts: list[dict], traps: list[dict], files: Optional[set[str]],
                    dirs: Optional[set[str]], captured) -> CheckResult:
    """Contract and trap locations against the checkout, and `confirmed` against the inventory.

    `captured` is the inventory's `file -> [line, …]` (`interfaces.lines_by_file`); a bare set
    of files is read as "any line". A CONFIRMED contract names exactly one file — never a glob,
    a folder or an elision matching several — and one the brief did not name must be shown by
    the inventory at that place (review fix #1: a wildcard confirmed an invented contract).

    `files` None = no legacy code to check against: said in a note, never taken as a pass for
    `confirmed` (a contract nobody could tie to the code is proposed)."""
    if captured is not None and not isinstance(captured, dict):
        captured = {f: [] for f in captured}
    captured = captured or {}
    out = CheckResult()
    if files is None:
        out.notes.append("No legacy code is pulled, so contract and trap locations were not checked "
                         "against the code.")
        for c in contracts:
            if c["status"] == "confirmed" and not words(c.get("brief_item") or ""):
                out.problems.append(f"{c['id']} {c['name']} is confirmed, but there is no legacy code to show it "
                                    "and the brief did not name it — mark it proposed.")
        return out
    dirs = dirs or set()
    for c in contracts:
        hit = resolve(c["legacy_location"], files, dirs)
        if not hit:
            out.problems.append(f"{c['id']} {c['name']}: “{c['legacy_location']}” is not in the legacy code. Give the "
                                "file (path[:line]) where it is defined, from the interface inventory or the code.")
            continue
        if c["status"] != "confirmed":
            continue
        if len(hit) != 1:
            out.problems.append(f"{c['id']} {c['name']} is confirmed, but “{c['legacy_location']}” names {len(hit)} "
                                "files. A confirmed contract names the one file (path[:line]) that defines it.")
            continue
        if not words(c.get("brief_item") or "") and not _shown_by_inventory(c["legacy_location"], next(iter(hit)),
                                                                             captured):
            out.problems.append(f"{c['id']} {c['name']} is confirmed, but the interface inventory does not show "
                                f"{c['legacy_location']} and the brief did not name it — mark it proposed until "
                                "the user confirms it.")
    for t in traps:
        paths = _paths_in(t["where"])
        if not paths:
            out.problems.append(f"{t['id']} does not say where in the code it bites (“{t['where']}”). Give a file, "
                                "folder or pattern such as claimtrack-reports/sql/*.sql.")
        elif not any(resolve(p, files, dirs) for p in paths):
            out.problems.append(f"{t['id']}: “{t['where']}” names nothing in the legacy code. Give the file, folder or "
                                "pattern where the change bites.")
    return out


# ── target versions ──────────────────────────────────────────────────────────

_RUNTIME_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (".NET Framework", re.compile(r"(?i)\.net\s+framework\s*v?(\d+(?:\.\d+){0,2})")),
    (".NET Core", re.compile(r"(?i)\.net\s+core\s*v?(\d+(?:\.\d+)?)")),
    # Digits right after ".NET": ".NET Framework 4.8" / ".NET Core 3.1" never match this one.
    (".NET", re.compile(r"(?i)\.net\s*v?(\d+(?:\.\d+)?)")),
    ("Java", re.compile(r"(?i)\b(?:java|jdk|jre|openjdk)\s*(?:se\s*)?v?(1\.\d+|\d+)\b")),
    ("Node.js", re.compile(r"(?i)\bnode(?:\.js|js)?\s*v?(\d+)\b")),
    ("Python", re.compile(r"(?i)\bpython\s*v?(\d\.\d+)\b")),
    # Phase F (universal): databases and the other common server runtimes.
    # Managed services put words between the engine and its version ("MySQL Flexible Server
    # 8.0", "PostgreSQL Flexible Server 16", "SQL Server Managed Instance 2019"): up to three.
    ("MySQL", re.compile(r"(?i)\bmysql(?:\s+[a-z][\w-]*){0,3}?\s*v?(\d+\.\d+)")),
    ("PostgreSQL", re.compile(r"(?i)\b(?:postgres(?:ql)?|pg)(?:\s+[a-z][\w-]*){0,3}?\s*v?(\d+(?:\.\d+)?)\b")),
    ("SQL Server", re.compile(r"(?i)\bsql\s*server(?:\s+[a-z][\w-]*){0,3}?\s*(\d{4})\b")),
    ("PHP", re.compile(r"(?i)\bphp\s*v?(\d\.\d+)")),
    ("Ruby", re.compile(r"(?i)\bruby\s*v?(\d\.\d+)")),
    ("Go", re.compile(r"(?i)\b(?:go|golang)\s*v?(1\.\d+)")),
)
VERSION_CHECKED = tuple(name for name, _ in _RUNTIME_PATTERNS)
_LATEST = re.compile(r"(?i)\b(latest|newest|most recent)\b")


#: Words that make the version after them the one being LEFT ("PostgreSQL 16, replacing MySQL 5.7").
_REPLACED = re.compile(r"(?i)\b(?:replac\w*|from|instead\s+of|was|formerly|previously|retir\w*)\s+"
                       r"(?:the\s+)?(?:(?!(?:to|onto|into|with)\b)[\w-]+\s+){0,4}$")


def runtimes_in(text: str) -> list[Runtime]:
    """The versions a target names — not one it says it replaces."""
    found, seen = [], set()
    for name, pattern in _RUNTIME_PATTERNS:
        for m in pattern.finditer(text or ""):
            if _REPLACED.search(text[max(0, m.start() - 60):m.start()]):
                continue
            key = (name, m.group(1))
            if key not in seen:
                seen.add(key)
                found.append(Runtime(name, m.group(1)))
    return found


def check_versions(targets: Iterable[tuple[str, str]], as_of: date) -> CheckResult:
    """`targets` = (label, target text). End of life or within a year of it is refused; a
    version the lifecycle table calls legacy is noted. Runtimes and databases covered: .NET,
    Java, Node.js, Python, PHP, Ruby, Go, MySQL, PostgreSQL, SQL Server (`VERSION_CHECKED`)."""
    out = CheckResult()
    for label, text in targets:
        if _LATEST.search(text or ""):
            out.problems.append(f"{label}: “{text}” — name an exact, supported version, never “latest”.")
        for rt in runtimes_in(text):
            status = runtime_status(rt, as_of)
            if status.status == "eol":
                out.problems.append(f"{label}: {rt.name} {rt.version} is past its end of support "
                                    f"({status.eol_date}). Choose a supported version.")
            elif status.status == "approaching":
                out.problems.append(f"{label}: {rt.name} {rt.version} ends support on {status.eol_date}, within a "
                                    "year — too soon to migrate onto. Choose a later version.")
            elif status.status == "legacy":
                out.notes.append(f"{label}: {rt.name} {rt.version} is supported but frozen (legacy) — "
                                 f"support ends {status.eol_date}.")
            elif status.status == "unknown":
                # NOT CHECKED IS NOT CHECKED (R39, review fix #3): said, never passed silently.
                out.notes.append(f"{label}: {rt.name} {rt.version} is not in the lifecycle table, so its end of "
                                 "support was not checked — confirm it is a supported release.")
    return out


# ── data migration ───────────────────────────────────────────────────────────

_DATABASE_LAYER = re.compile(r"(?i)\b(database|db|data\s*store|rdbms|sql|persistence|storage|data)\b")
#: Engines named in the today/target text make it a database layer whatever it is called
#: (review fix #4: "Persistence: Oracle 12c → PostgreSQL 16" needed no plan).
_DATABASE_ENGINE = re.compile(
    r"(?i)(mysql|mariadb|postgres|postgresql|oracle|sql\s*server|mssql|db2|sybase|informix|sqlite|mongo|"
    r"cosmos|dynamo|cassandra|redshift|snowflake|aurora|teradata)")


def check_data_migration(layers: list[dict], data_migration: Optional[dict]) -> list[str]:
    if data_migration:
        return []
    for layer in layers:
        is_db = _DATABASE_LAYER.search(layer["layer"]) or _DATABASE_ENGINE.search(f"{layer['today']} {layer['target']}")
        if is_db and words(layer["today"]) != words(layer["target"]):
            return [f"The {layer['layer']} layer changes ({layer['today']} → {layer['target']}) but there is no "
                    "data-migration plan: give the source and target, the method, the engine behaviour changes "
                    "that affect these queries, and the cutover."]
    return []


# ── diagrams ─────────────────────────────────────────────────────────────────

_MERMAID_START = re.compile(
    r"^(flowchart|graph|C4Context|C4Container|C4Component|C4Dynamic|C4Deployment|sequenceDiagram|classDiagram|"
    r"stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline|block-beta|architecture-beta|"
    r"quadrantChart|requirementDiagram|gitGraph|sankey-beta|xychart-beta|packet-beta|kanban)\b")
_REQUIRED_DIAGRAMS = (("AS-IS", re.compile(r"(?i)\bas[\s\-_]?is\b")),
                      ("TRANSITION", re.compile(r"(?i)\btransition")),
                      ("TO-BE", re.compile(r"(?i)\bto[\s\-_]?be\b")))


def _first_statement(source: str) -> str:
    lines = (source or "").splitlines()
    if lines and lines[0].strip() == "---":  # YAML front matter
        end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), len(lines) - 1)
        lines = lines[end + 1:]
    for line in lines:
        s = line.strip()
        if s and not s.startswith("%%"):
            return s
    return ""


def check_diagrams(diagrams: list[dict]) -> list[str]:
    problems = []
    for label, pattern in _REQUIRED_DIAGRAMS:
        if not any(pattern.search(d["title"]) for d in diagrams):
            problems.append(f"There is no {label} diagram. Give AS-IS, TRANSITION (the system halfway through the "
                            "migration) and TO-BE, each in Mermaid.")
    for d in diagrams:
        if not _MERMAID_START.match(_first_statement(d["mermaid"])):
            problems.append(f"The “{d['title']}” diagram is not Mermaid: it must start with a diagram type such as "
                            "flowchart LR or C4Container.")
    return problems


# ── questions the code could not answer ──────────────────────────────────────


def check_questions(not_assessable: list[str], resolved: list[dict], open_questions: list[str]) -> list[str]:
    answered = {words(r["question"]) for r in resolved}
    still_open = [words(q) for q in open_questions]
    problems = []
    for q in not_assessable:
        key = words(q)
        # The open question must CONTAIN the assessment's question (it may add context), never
        # merely be contained in it: "a" is not the question kept open (review fix #2).
        if key in answered or any(key in o for o in still_open):
            continue
        problems.append(f"The assessment could not tell from the code: “{q}”. Ask the user (or read an approved "
                        "document), then record the answer under resolved_questions with its source — or keep "
                        "the question in open_questions. Never assume it.")
    return problems

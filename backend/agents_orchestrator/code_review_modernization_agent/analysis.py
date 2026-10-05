"""What Migration Review computes instead of recalling (Phase I, I3/I4): pure functions over two trees.

API SURFACE (`surface`, `compare_surfaces`). Phase E's `capture_interfaces` (routes, files, tables,
queues, jobs) plus a small reader for what a framework-less module exposes and a pattern scan does not
see: public functions and their parameters, HTTP handlers and the paths they match on `self.path`, the
status codes they answer, SQL statements, and the encodings files are written in. The legacy module and
the target module are read the same way and diffed by (kind, name); each difference names the frozen
contract whose legacy file it is in, so "CT-01 unchanged" can be checked, not believed.

LEGACY ANTI-PATTERNS (`antipatterns`, `classify`). A built-in rule pack, run on both sides. A target hit
is CARRIED OVER when the legacy counterpart (through the file map) has the same rule on the same
normalized line, or the same rule anywhere in the counterpart; otherwise INTRODUCED. A legacy hit with no
target match is FIXED. Pure Python: it runs wherever the platform runs, with or without Docker.

Pattern scans, not compilers: an entry is evidence with its file and line, for the agent to read.
"""
from __future__ import annotations

import pathlib
import re
from typing import Iterable, Optional

_MAX_BYTES = 1_000_000
_TEXT_EXT = {".py", ".java", ".cs", ".js", ".jsx", ".ts", ".tsx", ".go", ".rb", ".php", ".vb", ".sql", ".kt",
             ".scala", ".cfg", ".ini", ".properties", ".yml", ".yaml", ".json", ".xml", ".env", ".txt", ".sh",
             ".cbl", ".cob", ".jsp", ".html"}


def _text(path: pathlib.Path) -> Optional[str]:
    try:
        if path.stat().st_size > _MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def module_texts(base: Optional[pathlib.Path], files: Iterable[str]) -> dict[str, str]:
    out = {}
    for rel in files:
        p = (base / rel) if base else None
        if p is not None and (p.suffix.lower() in _TEXT_EXT or not p.suffix) and (t := _text(p)) is not None:
            out[rel] = t
    return out


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


# ── API surface ─────────────────────────────────────────────────────────────

_DEF = re.compile(r"^(?:async\s+)?def\s+([A-Za-z]\w*)\s*\(([^)]*)\)")
_HANDLER = re.compile(r"^\s+def\s+do_(GET|POST|PUT|DELETE|PATCH|HEAD)\s*\(")
_PATH_EQ = re.compile(r"self\.path\s*==\s*[rbu]?[\"']([^\"']+)[\"']")
_PATH_RE = re.compile(r"re\.(?:match|search|fullmatch)\(\s*[rbu]*[\"']([^\"']+)[\"']\s*,\s*self\.path")
_STATUS = re.compile(r"(?:reply|send_response|send_error|status|status_code|abort|HttpStatus|StatusCode)\s*[(=]\s*(\d{3})\b")
_SQL = re.compile(r"\"\s*((?:SELECT|INSERT|UPDATE|DELETE|MERGE|REPLACE)\b[^\"]{4,})\"|'\s*((?:SELECT|INSERT|UPDATE|DELETE|MERGE|REPLACE)\b[^']{4,})'",
                  re.IGNORECASE)
_ENCODING = re.compile(r"""(?:encoding\s*=\s*|\.encode\(\s*|\.decode\(\s*|codecs\.open\([^)]*,\s*)[\"']([A-Za-z0-9_-]+)[\"']""")
_OPEN_WRITE = re.compile(r"""open\([^)]*,\s*[\"']([wa][bt+]*)[\"']""")


def _params(raw: str) -> str:
    out = []
    for p in raw.split(","):
        p = p.strip()
        if not p or p in ("self", "cls"):
            continue
        out.append(re.split(r"[:=]", p)[0].strip())
    return ", ".join(out)


def _own_surface(rel: str, text: str) -> list[dict]:
    items: list[dict] = []
    is_py = rel.endswith(".py")
    for n, line in enumerate(text.splitlines(), 1):
        def add(kind: str, name: str) -> None:
            items.append({"kind": kind, "name": name, "location": f"{rel}:{n}", "evidence": line.strip()[:200]})
        if is_py:
            if (m := _DEF.match(line)) and not m.group(1).startswith("_"):
                add("function", f"{m.group(1)}({_params(m.group(2))})")
            if m := _HANDLER.match(line):
                add("http_method", m.group(1))
        for m in _PATH_EQ.finditer(line):
            add("http_path", m.group(1))
        for m in _PATH_RE.finditer(line):
            add("http_path", m.group(1))
        for m in _STATUS.finditer(line):
            add("status", m.group(1))
        for m in _SQL.finditer(line):
            add("sql", _norm(m.group(1) or m.group(2)))
        for m in _ENCODING.finditer(line):
            add("encoding", m.group(1).lower().replace("_", "-"))
        for m in _OPEN_WRITE.finditer(line):
            add("file_write", m.group(1).replace("t", ""))
    return items


def surface(base: Optional[pathlib.Path], module_path: str, files: Iterable[str]) -> list[dict]:
    """Everything the module exposes or depends on, with locations. One entry per (kind, name, file)."""
    if base is None:
        return []
    from agents_orchestrator.design_modernization_agent.analysis.interfaces import capture_interfaces  # noqa: PLC0415

    files = sorted(files)
    items: list[dict] = []
    top = base / module_path
    if top.is_dir():
        inv = capture_interfaces(top)
        for i in inv["items"]:
            loc = f"{module_path}/{i['location']}"
            items.append({"kind": f"{i['kind']}_{i['direction']}", "name": i["name"], "location": loc,
                          "evidence": i.get("evidence", "")})
    for rel, text in module_texts(base, files).items():
        items += _own_surface(rel, text)
    seen, out = set(), []
    for i in items:
        key = (i["kind"], i["name"], i["location"].rsplit(":", 1)[0])
        if key not in seen:
            seen.add(key)
            out.append(i)
    return sorted(out, key=lambda i: (i["kind"], i["name"], i["location"]))


def _contract_files(contracts: list[dict]) -> dict[str, list[str]]:
    """legacy file → the contract ids located in it."""
    out: dict[str, list[str]] = {}
    for c in contracts:
        loc = str(c.get("legacy_location") or c.get("location") or "")
        path = loc.split(":", 1)[0].strip().lstrip("/")
        if path:
            out.setdefault(path, []).append(c["id"])
    return out


def _legacy_of(file_map: list[dict]) -> dict[str, str]:
    """target path → legacy path, for mapped and merged files."""
    return {e["target_path"]: e["legacy_path"] for e in file_map or []
            if e.get("disposition") in ("mapped", "merged") and e.get("target_path")}


def compare_surfaces(legacy: list[dict], target: list[dict], *, file_map: list[dict], contracts: list[dict]) -> dict:
    """The difference, by (kind, name): removed (legacy only), added (target only), and per frozen
    contract the changes in its file. Equal names in moved files are not a change."""
    lkeys = {(i["kind"], i["name"]): i for i in legacy}
    tkeys = {(i["kind"], i["name"]): i for i in target}
    removed = [lkeys[k] for k in sorted(set(lkeys) - set(tkeys))]
    added = [tkeys[k] for k in sorted(set(tkeys) - set(lkeys))]
    cfiles = _contract_files(contracts)
    back = _legacy_of(file_map)
    by_contract: dict[str, list[dict]] = {c["id"]: [] for c in contracts}
    for change, items in (("removed", removed), ("added", added)):
        for i in items:
            path = i["location"].rsplit(":", 1)[0]
            legacy_path = path if change == "removed" else back.get(path, path)
            for ct in cfiles.get(legacy_path, []):
                by_contract[ct].append({**i, "change": change})
    return {"removed": removed, "added": added, "contracts": by_contract,
            "legacy_count": len(legacy), "target_count": len(target)}


def surface_markdown(diff: dict, module_id: str) -> str:
    lines = [f"# API surface of {module_id}: legacy {diff['legacy_count']} entries, target {diff['target_count']}", ""]
    if not diff["removed"] and not diff["added"]:
        lines.append("No difference: every route, public function, status code, SQL statement and file format of "
                     "the legacy module is in the target, and nothing was added.")
    for label, key in (("Only in the legacy (removed or renamed)", "removed"), ("Only in the target (added)", "added")):
        if diff[key]:
            lines += ["", f"## {label}", "| Kind | Name | Where | Line |", "|---|---|---|---|"]
            lines += [f"| {i['kind']} | `{i['name'][:90]}` | {i['location']} | `{i['evidence'][:80]}` |" for i in diff[key][:60]]
    lines += ["", "## Frozen contracts"]
    for ct, changes in sorted(diff["contracts"].items()):
        if changes:
            lines.append(f"- {ct}: {len(changes)} change(s) in its file — "
                         + "; ".join(f"{c['change']} {c['kind']} `{c['name'][:60]}` ({c['location']})" for c in changes[:8])
                         + ". Unchanged only if each is explained (an ADR allows it, or it is not part of the contract).")
        else:
            lines.append(f"- {ct}: no change found in its file.")
    lines += ["", "A pattern scan, not a compiler: read the lines before calling anything a finding."]
    return "\n".join(lines)


# ── legacy anti-patterns ────────────────────────────────────────────────────

#: (id, title, severity, file suffixes ("" = any), pattern)
RULES: list[tuple[str, str, str, tuple[str, ...], re.Pattern]] = [
    ("sql-string-built", "SQL built from strings (injection risk)", "high", (),
     re.compile(r"""(?:execute|executemany|query|prepareStatement|createStatement\(\)\.execute\w*)\s*\(\s*(?:f["']|["'][^"']*["']\s*(?:%|\+|\.format))""", re.IGNORECASE)),
    ("exception-swallowed", "Exception swallowed", "medium", (),
     re.compile(r"""^\s*(?:except(?:\s+[\w.,() ]+)?\s*:\s*pass\b|catch\s*\([^)]*\)\s*\{\s*\})""")),
    ("exception-bare", "Bare except catches everything", "low", (".py",), re.compile(r"^\s*except\s*:")),
    ("py2-print", "Python 2 print statement", "medium", (".py",), re.compile(r"^\s*print\s+[\"'\w(]")),
    ("py2-except-comma", "Python 2 except syntax", "medium", (".py",), re.compile(r"^\s*except\s+[\w.]+\s*,\s*\w+\s*:")),
    ("py2-module", "Python 2 only module", "medium", (".py",),
     re.compile(r"^\s*(?:import|from)\s+(?:urllib2|BaseHTTPServer|SimpleHTTPServer|ConfigParser|Queue|cPickle|StringIO|cStringIO|httplib|urlparse|commands)\b")),
    ("py2-builtins", "Python 2 only builtin or method", "medium", (".py",),
     re.compile(r"\b(?:xrange|raw_input|unichr|execfile)\s*\(|\.has_key\(|\.iteritems\(|\.itervalues\(|\.iterkeys\(|\bunicode\s*\(|\blong\s*\(")),
    ("hardcoded-host", "Hard-coded host or URL", "low", (),
     re.compile(r"""["'](?:https?|jdbc:\w+|mongodb|redis|amqp)://(?!localhost|127\.0\.0\.1|example\.|[\w.-]*\.invalid)[\w.-]+""")),
    ("hardcoded-credential", "Hard-coded credential", "high", (),
     re.compile(r"""(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token)\b\s*[:=]\s*["'][^"'\s]{4,}["']""")),
    ("static-mutable", "Static mutable state", "medium", (".java", ".cs", ".kt"),
     re.compile(r"\bstatic\s+(?!final\b|readonly\b|const\b)[\w<>\[\], ]+\s+\w+\s*=")),
    ("module-mutable", "Module-level mutable state", "low", (".py",),
     re.compile(r"^[a-z_][a-z0-9_]*\s*=\s*(?:\{\}|\[\]|dict\(\)|list\(\)|set\(\))\s*$")),
    ("log4j1", "Log4j 1 API (end of life)", "high", (".java", ".xml", ".properties"),
     re.compile(r"org\.apache\.log4j\.|log4j\.(?:rootLogger|appender)")),
    ("shared-simpledateformat", "Shared SimpleDateFormat (not thread safe)", "medium", (".java",),
     re.compile(r"static\s+(?:final\s+)?SimpleDateFormat")),
    ("angularjs-scope", "AngularJS $scope idiom", "medium", (".js", ".jsx", ".ts", ".tsx"), re.compile(r"\$scope\.")),
    ("http-no-tls", "Plain HTTP call", "low", (),
     re.compile(r"""(?:urlopen|requests\.\w+|httpx\.\w+|fetch|axios\.\w+)\(\s*["']http://(?!localhost|127\.0\.0\.1)""")),
]
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def antipatterns(texts: dict[str, str]) -> list[dict]:
    hits = []
    for rel, text in sorted(texts.items()):
        suffix = pathlib.PurePosixPath(rel).suffix.lower()
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("#", "//")) and not line.lstrip().startswith("#!"):
                continue
            for rid, title, sev, suffixes, rx in RULES:
                if suffixes and suffix not in suffixes:
                    continue
                if rx.search(line):
                    hits.append({"rule": rid, "title": title, "severity": sev, "file": rel, "line": n,
                                 "code": _norm(line)[:200]})
    return hits


def classify(legacy_hits: list[dict], target_hits: list[dict], file_map: list[dict]) -> dict:
    """Each target hit carried_over or introduced; each unmatched legacy hit fixed."""
    back = _legacy_of(file_map)
    by_file_rule: dict[tuple[str, str], list[dict]] = {}
    for h in legacy_hits:
        by_file_rule.setdefault((h["file"], h["rule"]), []).append(h)
    used: set[int] = set()
    target_out = []
    for h in target_hits:
        counterpart = back.get(h["file"], h["file"])
        candidates = by_file_rule.get((counterpart, h["rule"]), [])
        match = next((c for c in candidates if c["code"] == h["code"] and id(c) not in used), None) \
            or next((c for c in candidates if id(c) not in used), None)
        if match is not None:
            used.add(id(match))
            target_out.append({**h, "origin": "carried_over", "legacy_file": match["file"], "legacy_line": match["line"]})
        else:
            target_out.append({**h, "origin": "introduced", "legacy_file": None, "legacy_line": None})
    fixed = [{**h, "origin": "fixed"} for h in legacy_hits if id(h) not in used]
    return {"target": target_out, "fixed": fixed}


def antipatterns_markdown(result: dict, module_id: str) -> str:
    t = sorted(result["target"], key=lambda h: (SEVERITY_ORDER[h["severity"]], h["file"], h["line"]))
    lines = [f"# Legacy anti-patterns in {module_id}'s migration: {len(t)} in the target "
             f"({sum(1 for h in t if h['origin'] == 'introduced')} introduced, "
             f"{sum(1 for h in t if h['origin'] == 'carried_over')} carried over), {len(result['fixed'])} fixed", ""]
    if t:
        lines += ["| Severity | Rule | Target | Origin | Legacy | Code |", "|---|---|---|---|---|---|"]
        lines += [f"| {h['severity']} | {h['title']} | {h['file']}:{h['line']} | {h['origin'].replace('_', ' ')} | "
                  f"{(h['legacy_file'] + ':' + str(h['legacy_line'])) if h.get('legacy_file') else '—'} | `{h['code'][:80]}` |"
                  for h in t[:80]]
    if result["fixed"]:
        lines += ["", "Fixed by the migration (in the legacy, not in the target):"]
        lines += [f"- {h['title']} — {h['file']}:{h['line']}" for h in result["fixed"][:40]]
    lines += ["", "Each hit is a lead, not a finding: read the line (and its legacy counterpart) first. An introduced "
                  "issue is a finding; a carried-over one is known debt unless the design says it is fixed in this move."]
    return "\n".join(lines)

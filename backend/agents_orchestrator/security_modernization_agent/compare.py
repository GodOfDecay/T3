"""Legacy against target, deterministically (Phase I, I8/I9). Pure functions.

`diff_findings` marks each target finding CARRIED OVER or INTRODUCED and each legacy-only finding FIXED:
  dependency   same CVE on the same package (any version: an upgrade that still has it carried it)
  code         same rule, in the target file's legacy counterpart (the migration's file map), or the
               same file path when it was not moved
  secret       same secret (by hash) anywhere

`secret_carryover` looks for every legacy secret VALUE (Gitleaks' and hard-coded credentials') in the
target's text: it returns where, never what.

`contract_authz` compares the authentication and authorization markers in each frozen HTTP contract's
legacy file and its target counterpart.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from agents_orchestrator.security_modernization_agent.scanners import secret_hash

_CREDENTIAL = re.compile(r"""(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token|access[_-]?key)\b\s*[:=]\s*["']([^"'\s]{6,})["']""")
_URL_PASSWORD = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:([^@\s/]{4,})@", re.IGNORECASE)
_AUTH_MARKERS = [
    ("login_required", re.compile(r"@login_required|@auth\.login_required|@requires_auth|@jwt_required")),
    ("role_check", re.compile(r"@(?:roles_required|permission_required|PreAuthorize|Secured|RolesAllowed)\b|\[Authorize|has_role\(|requires_role\(|isUserInRole\(|IsInRole\(")),
    ("authorization_header", re.compile(r"""["']Authorization["']|getHeader\(\s*["']Authorization|headers\.get\(\s*["']Authorization""", re.IGNORECASE)),
    ("api_key", re.compile(r"""["']X-API-Key["']|api_key\b|apikey\b""", re.IGNORECASE)),
    ("token_check", re.compile(r"verify_token|validate_token|jwt\.decode|check_auth|authenticate\(", re.IGNORECASE)),
    ("session_user", re.compile(r"session\[\s*[\"']user|request\.user\b|current_user\b|getRemoteUser\(|getUserPrincipal\(")),
    ("allow_anonymous", re.compile(r"\[AllowAnonymous|@PermitAll|permitAll\(\)|@csrf_exempt")),
]


def _legacy_of(file_map: list[dict]) -> dict[str, str]:
    return {e["target_path"]: e["legacy_path"] for e in file_map or []
            if e.get("disposition") in ("mapped", "merged") and e.get("target_path")}


def _key(f: dict, file_for_code: str) -> tuple:
    if f["tool"] == "trivy":
        return ("dep", f.get("cve"), (f.get("package") or "").lower())
    if f["tool"] == "gitleaks" and f.get("secret_hash"):
        return ("secret", f["secret_hash"])
    return ("code", f.get("tool"), f.get("rule"), file_for_code)


def diff_findings(legacy: list[dict], target: list[dict], file_map: list[dict]) -> dict:
    back = _legacy_of(file_map)
    pool: dict[tuple, list[dict]] = {}
    for f in legacy:
        pool.setdefault(_key(f, f.get("file") or ""), []).append(f)
    used: set[int] = set()
    out = []
    for f in target:
        key = _key(f, back.get(f.get("file") or "", f.get("file") or ""))
        match = next((c for c in pool.get(key, []) if id(c) not in used), None)
        if match is not None:
            used.add(id(match))
            ref = (f"{match.get('package')}@{match.get('version')}" if match["tool"] == "trivy"
                   else f"{match.get('file')}:{match.get('line') or ''}".rstrip(":"))
            out.append({**f, "origin": "carried_over", "legacy_ref": ref})
        else:
            out.append({**f, "origin": "introduced", "legacy_ref": None})
    fixed = [{**f, "origin": "fixed", "legacy_ref": (f"{f.get('package')}@{f.get('version')}" if f["tool"] == "trivy"
                                                     else f"{f.get('file')}:{f.get('line') or ''}".rstrip(":"))}
             for f in legacy if id(f) not in used]
    return {"target": out, "fixed": fixed}


def credential_values(texts: dict[str, str]) -> list[tuple[str, str, int]]:
    """(value, file, line) of every hard-coded credential value in the texts."""
    out = []
    for rel, text in texts.items():
        for n, line in enumerate(text.splitlines(), 1):
            for rx in (_CREDENTIAL, _URL_PASSWORD):
                for m in rx.finditer(line):
                    out.append((m.group(1), rel, n))
    return out


def secret_carryover(legacy_values: Iterable[tuple[str, str, Optional[int]]], target_texts: dict[str, str]) -> list[dict]:
    """Where a legacy secret value appears in the target. Values shorter than 6 characters are skipped
    (they match by accident). Returns {file, line, legacy_file, legacy_line, hash}; never the value."""
    hits, seen = [], set()
    for value, legacy_file, legacy_line in legacy_values:
        if not value or len(value) < 6:
            continue
        for rel, text in target_texts.items():
            if value not in text:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if value in line and (rel, n, secret_hash(value)) not in seen:
                    seen.add((rel, n, secret_hash(value)))
                    hits.append({"file": rel, "line": n, "legacy_file": legacy_file, "legacy_line": legacy_line,
                                 "hash": secret_hash(value)})
    return hits


def auth_markers(text: str) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for n, line in enumerate((text or "").splitlines(), 1):
        for name, rx in _AUTH_MARKERS:
            if rx.search(line):
                found.setdefault(name, []).append(n)
    return found


def contract_authz(legacy_text: str, target_text: str) -> dict:
    """{suggested: same|stricter|weaker, legacy: markers, target: markers, reason}. The agent states the
    status; this is the evidence. Allow-anonymous markers count against."""
    lm, tm = auth_markers(legacy_text), auth_markers(target_text)
    lset = {k for k in lm if k != "allow_anonymous"}
    tset = {k for k in tm if k != "allow_anonymous"}
    opened = "allow_anonymous" in tm and "allow_anonymous" not in lm
    if lset - tset or opened:
        missing = sorted(lset - tset)
        reason = ("the target lacks " + ", ".join(missing) if missing else "") + \
                 ("; the target allows anonymous access" if opened else "")
        return {"suggested": "weaker", "legacy": lm, "target": tm, "reason": reason.strip("; ")}
    if tset - lset:
        return {"suggested": "stricter", "legacy": lm, "target": tm,
                "reason": "the target adds " + ", ".join(sorted(tset - lset))}
    return {"suggested": "same", "legacy": lm, "target": tm,
            "reason": "the same markers on both sides" if lset else "no authentication marker on either side"}

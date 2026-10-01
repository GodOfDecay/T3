"""Run 1 against run 2 of the same legacy system on the same inputs — the NOISE FLOOR (Phase G, G3).

Whatever differs between two runs of an unchanged system is its own nondeterminism: a timestamp, a
generated id. Those fields cannot be compared as they are; a normalization rule (owned by Migration
Strategy) must say how. This module finds them, names them, and says which a rule already covers.

FIELD NAMES the rules can match:
  http   the JSON path in the response body ("requestId", "claim.payout", "items[].id"), or
         "status" / "contentType" / "error"
  batch  "<file>#L<line>" for an output file's line, "stdout#L<line>", "exit", "<file>" (present in one
         run only)

A rule covers a field when its `field` is the name, a dotted suffix of it ("requestId" covers
"error.requestId"), or a glob matching it ("BANKPAY_*.txt#L1").

MASKED ONLY. Examples are SHAPES (`<timestamp>`, `<uuid>`, `AAAA 9999`), never values: nothing a
recording holds reaches the model or the page (research §6.5: "never sends a recording ... to the model").
"""
from __future__ import annotations

import fnmatch
import json
import pathlib
import re
from typing import Any, Iterable

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def mask(value: Any) -> str:
    """The shape of a value, never the value."""
    if value is None:
        return "<null>"
    if isinstance(value, bool):
        return "<bool>"
    if isinstance(value, (int, float)):
        return "<number>"
    if isinstance(value, (dict, list)):
        return f"<{type(value).__name__} of {len(value)}>"
    text = str(value)
    if _TS.match(text):
        return "<timestamp>"
    if _UUID.match(text):
        return "<uuid>"
    shape = re.sub(r"[A-Za-zÀ-ɏ]", "A", re.sub(r"\d", "9", text))
    return shape if len(shape) <= 48 else shape[:45] + "…"


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """{"claim": {"payout": 1}} → {"claim.payout": 1}; list items share one name ("items[].id")."""
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            for k, x in flatten(v, f"{prefix}[]").items():
                out[f"{k}#{i}"] = x
    else:
        out[prefix or "value"] = value
    return out


def _field(name: str) -> str:
    return re.sub(r"#\d+", "", name)


def _responses(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _http(a: pathlib.Path, b: pathlib.Path) -> tuple[int, dict[str, list[tuple[str, str]]]]:
    ra, rb = _responses(a / "responses.jsonl"), _responses(b / "responses.jsonl")
    varying: dict[str, list[tuple[str, str]]] = {}
    for x, y in zip(ra, rb):
        fx = {k: v for k, v in x.items() if k != "request" and k != "body"} | {
            k: v for k, v in flatten(x.get("body", {})).items()}
        fy = {k: v for k, v in y.items() if k != "request" and k != "body"} | {
            k: v for k, v in flatten(y.get("body", {})).items()}
        for key in sorted(set(fx) | set(fy)):
            if fx.get(key, "<absent>") != fy.get(key, "<absent>"):
                varying.setdefault(_field(key), []).append((mask(fx.get(key)), mask(fy.get(key))))
    if len(ra) != len(rb):
        varying.setdefault("responses", []).append((f"<{len(ra)} responses>", f"<{len(rb)} responses>"))
    return len(ra), varying


def _lines(data: bytes) -> list[str]:
    return data.decode("latin-1").splitlines()


def _batch(a: pathlib.Path, b: pathlib.Path) -> tuple[int, dict[str, list[tuple[str, str]]]]:
    varying: dict[str, list[tuple[str, str]]] = {}
    ea = json.loads((a / "exec.json").read_text(encoding="utf-8"))
    eb = json.loads((b / "exec.json").read_text(encoding="utf-8"))
    if ea.get("exit") != eb.get("exit"):
        varying["exit"] = [(mask(ea.get("exit")), mask(eb.get("exit")))]
    sa, sb = str(ea.get("stdout") or "").splitlines(), str(eb.get("stdout") or "").splitlines()
    for n in range(max(len(sa), len(sb))):
        x = sa[n] if n < len(sa) else None
        y = sb[n] if n < len(sb) else None
        if x != y:
            varying[f"stdout#L{n + 1}"] = [(mask(x), mask(y))]
    fa = {p.name: p for p in (a / "files").iterdir()} if (a / "files").is_dir() else {}
    fb = {p.name: p for p in (b / "files").iterdir()} if (b / "files").is_dir() else {}
    for name in sorted(set(fa) | set(fb)):
        if name not in fa or name not in fb:
            varying[name] = [("<present>" if name in fa else "<absent>", "<present>" if name in fb else "<absent>")]
            continue
        la, lb = _lines(fa[name].read_bytes()), _lines(fb[name].read_bytes())
        for n in range(max(len(la), len(lb))):
            x = la[n] if n < len(la) else None
            y = lb[n] if n < len(lb) else None
            if x != y:
                varying[f"{name}#L{n + 1}"] = [(mask(x), mask(y))]
    return 1, varying


def compare(run1: pathlib.Path, run2: pathlib.Path, scenarios: Iterable[dict]) -> dict[str, dict]:
    """{scenario id: {"cases", "varying": {field: count}, "examples": {field: [run1 shape, run2 shape]}}}."""
    out = {}
    for sc in scenarios:
        a, b = run1 / sc["id"], run2 / sc["id"]
        cases, varying = (_http if sc["kind"] == "http" else _batch)(a, b)
        out[sc["id"]] = {"kind": sc["kind"], "cases": cases,
                         "varying": {f: len(v) for f, v in sorted(varying.items())},
                         "examples": {f: list(v[0]) for f, v in sorted(varying.items())}}
    return out


def covers(rule_field: str, field: str) -> bool:
    rule = (rule_field or "").strip()
    if not rule:
        return False
    return field == rule or field.endswith("." + rule) or fnmatch.fnmatchcase(field, rule)


def covered(fields: Iterable[str], rules: Iterable[dict]) -> list[str]:
    rules = list(rules)
    return sorted(f for f in fields if any(covers(r.get("field", ""), f) for r in rules))

"""The plan against the brief's calendar — deterministic (research §6.4 `check_calendar`).

Every conflict has a stable `ref`, so the record tool can prove each one was REPORTED to the user
(research acceptance check: "the calendar check returns no unreported conflicts"). Nothing here
moves a date; it only says where the plan and the brief disagree.

  deadline:<W>                 a wave ends after the brief's deadline
  milestone:<date>:<W>         a wave ends after a deadline / decommission milestone
  baseline-after-freeze:<EC>   a baseline is due after the legacy change freeze starts
  baseline-late:<EC>           a baseline is due after the wave that needs it has started
  window-day:<W>               a cutover falls on a day the brief's window does not allow
  window-length:<W>            a cutover takes longer than the brief's window allows

Windows are read from the user's words: weekday names ("Sunday nights", "Sat–Sun", "Friday 22:00 –
Monday 06:00") and a limit ("at most 2 hours", "≤ 90 min", "4h") or, when no limit is stated, the
window's own span ("Sundays 01:00–03:00" allows 120 min). A cutover's length is its span ("00:00–02:00",
"Sat 22:00 – Sun 02:00"). A night that runs past midnight is one window: a cutover starting on an
allowed day may end on the next. What cannot be read is not guessed — it produces no conflict, and
the report says which part (days or length) was not machine-checked.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DAY_RE = re.compile(r"(?i)\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:days?|nesdays?|urdays?|sdays?|s)?\b")
_DAYNAME = r"(mon|tue|wed|thu|fri|sat|sun)\w*\.?"
_TO = r"\s*(?:[–-]|\bto\b|\buntil\b|\bthrough\b)\s*"
_RANGE_RE = re.compile(rf"(?i)\b{_DAYNAME}(?:\s+\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm)?)?{_TO}{_DAYNAME}")
#: "Fri 22:00 – Mon 06:00": a window that spans days.
_SPAN_RE = re.compile(rf"(?i)\b{_DAYNAME}\s+(\d{{1,2}}):(\d{{2}}){_TO}{_DAYNAME}\s+(\d{{1,2}}):(\d{{2}})")
_LIMIT_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)\b")
_TIME_RANGE_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})\b")


def _day(token: str) -> int:
    return [d[:3] for d in _DAYS].index(token[:3].lower())


def days_in(text: str) -> set[int]:
    """Weekdays named in a window ("Sunday nights" → {6}; "Fri–Sun" → {4, 5, 6})."""
    text = text or ""
    days: set[int] = set()
    for m in _RANGE_RE.finditer(text):
        a, b = _day(m.group(1)), _day(m.group(2))
        days.update(range(a, b + 1) if a <= b else [*range(a, 7), *range(0, b + 1)])
    for m in _DAY_RE.finditer(text):
        days.add(_day(m.group(1)))
    if re.search(r"(?i)\bweek-?ends?\b", text):
        days.update({5, 6})
    if re.search(r"(?i)\bweek-?days?\b", text):
        days.update(range(0, 5))
    return days


def limit_minutes(text: str) -> Optional[int]:
    """The window's length limit in minutes ("at most 2 hours" → 120), or None when it gives none."""
    m = _LIMIT_RE.search(text or "")
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    return int(round(value * 60)) if unit.startswith("h") else int(round(value))


def range_minutes(text: str) -> Optional[int]:
    """The length of a "00:00–02:00" range in minutes (across midnight too), or None."""
    m = _TIME_RANGE_RE.search(text or "")
    if not m:
        return None
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = int(m.group(3)) * 60 + int(m.group(4))
    return (end - start) % (24 * 60) or 24 * 60


def span_minutes(text: str) -> Optional[int]:
    """How long a window or cutover lasts: "Fri 22:00 – Mon 06:00" (across days) or "00:00–02:00"."""
    m = _SPAN_RE.search(text or "")
    if not m:
        return range_minutes(text)
    days = (_day(m.group(4)) - _day(m.group(1))) % 7
    start = int(m.group(2)) * 60 + int(m.group(3))
    end = days * 24 * 60 + int(m.group(5)) * 60 + int(m.group(6))
    return end - start if end > start else end - start + 7 * 24 * 60


def _runs_past_midnight(text: str) -> bool:
    if re.search(r"(?i)\b(?:over)?nights?\b", text or ""):
        return True
    span = _SPAN_RE.search(text or "")
    if span:
        return _day(span.group(1)) != _day(span.group(4))
    m = _TIME_RANGE_RE.search(text or "")
    return bool(m) and int(m.group(3)) * 60 + int(m.group(4)) <= int(m.group(1)) * 60 + int(m.group(2))


def window_limit(window: str) -> Optional[int]:
    """The brief's limit in minutes: the stated one, else the window's own span, else None."""
    limit = limit_minutes(window)
    return limit if limit is not None else span_minutes(window)


def _date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def check_calendar(plan: dict, brief: dict) -> list[dict]:
    """`plan`: a PlanPayload as a dict (waves, baseline_plan, equivalence_criteria); `brief`: the
    brief's hand-over payload. Returns [{ref, conflict, impact}] sorted by ref."""
    waves = plan.get("waves") or []
    conflicts: dict[str, dict] = {}

    def add(ref: str, conflict: str, impact: str) -> None:
        conflicts.setdefault(ref, {"ref": ref, "conflict": conflict, "impact": impact})

    deadline = _date(brief.get("deadline"))
    freeze = _date(brief.get("freeze_from"))
    ends_by = [(m, _date(m.get("date"))) for m in brief.get("milestones") or []
               if m.get("kind") in ("deadline", "decommission")]
    for w in waves:
        ends = _date(w.get("ends"))
        if not ends:
            continue
        if deadline and ends > deadline:
            add(f"deadline:{w['id']}", f"{w['id']} ends {ends} after the brief's deadline {deadline}",
                "the plan misses the deadline unless the wave is shortened, started earlier or the deadline moves")
        for m, when in ends_by:
            if when and ends > when and when != deadline:
                add(f"milestone:{when}:{w['id']}", f"{w['id']} ends {ends} after “{m.get('label')}” ({when})",
                    f"the {m.get('kind')} milestone is missed")

    wave_start = {m: _date(w.get("starts")) for w in waves for m in w.get("modules") or []}
    moving = [_date(w.get("starts")) for w in waves if w.get("id") != "W0" and w.get("modules")]
    first_move = min((d for d in moving if d), default=None)
    module_of = {c["id"]: c.get("module_id") for c in plan.get("equivalence_criteria") or []}
    for b in plan.get("baseline_plan") or []:
        due, ec = _date(b.get("due")), b.get("ec_id")
        if not due:
            continue
        if freeze and due > freeze:
            add(f"baseline-after-freeze:{ec}", f"the {ec} baseline is due {due}, after the legacy freeze starts {freeze}",
                "the legacy system may change after the freeze starts only by exception; record the baseline first")
        module = module_of.get(ec)
        needed = first_move if module == "all" else wave_start.get(module)
        if needed and due > needed:
            add(f"baseline-late:{ec}", f"the {ec} baseline is due {due}, after its wave starts {needed}",
                "migration work would start before the behaviour it must keep has been recorded")

    window = brief.get("downtime_window") or ""
    allowed_days, limit = days_in(window), window_limit(window)
    for w in waves:
        cut = w.get("cutover_window") or ""
        if not cut:
            continue
        cut_days = days_in(cut)
        allowed = set(allowed_days)
        if _runs_past_midnight(window) or _runs_past_midnight(cut):
            allowed |= {(d + 1) % 7 for d in allowed_days}  # the night's spill into the next morning
        if allowed_days and cut_days and not (cut_days <= allowed and cut_days & allowed_days):
            add(f"window-day:{w['id']}", f"{w['id']} cuts over “{cut}”, outside the brief's window “{window}”",
                "the cutover falls on a day the business has not agreed to")
        length = span_minutes(cut)
        if limit is not None and length is not None and length > limit:
            add(f"window-length:{w['id']}", f"{w['id']}'s cutover takes {length} min; the brief allows {limit} min",
                "the planned downtime exceeds what was agreed")
    return [conflicts[k] for k in sorted(conflicts)]


def window_checked(brief: dict) -> bool:
    """Could the brief's cutover window be read at all (days or a limit)?"""
    return len(window_unread(brief)) < 2


def window_unread(brief: dict) -> list[str]:
    """Which parts of the brief's cutover window could NOT be read: "days", "length", both or none."""
    window = brief.get("downtime_window") or ""
    if not window:
        return []
    return [part for part, read in (("days", bool(days_in(window))), ("length", window_limit(window) is not None))
            if not read]


def calendar_markdown(conflicts: list[dict], brief: dict) -> str:
    lines = ["# Calendar check", ""]
    facts = [f"deadline {brief.get('deadline')}" if brief.get("deadline") else "no dated deadline",
             f"legacy freeze from {brief.get('freeze_from')}" if brief.get("freeze_from") else "no freeze date",
             f"cutover window “{brief.get('downtime_window')}”" if brief.get("downtime_window") else "no cutover window"]
    lines.append("Checked against: " + "; ".join(facts) + ".")
    unread = window_unread(brief)
    if len(unread) == 2:
        lines.append("The cutover window could not be read as days or a length, so cutovers were NOT checked "
                     "against it — say so.")
    elif unread:
        lines.append(f"The cutover window's {unread[0]} could not be read, so cutovers were checked for "
                     f"{'length' if unread[0] == 'days' else 'days'} only — say so.")
    if not conflicts:
        lines += ["", "No conflicts found."]
        return "\n".join(lines)
    lines += ["", "Report EVERY one to the user, with its ref, in calendar_conflicts — never move a date they gave.",
              "", "| Ref | Conflict | Impact |", "|---|---|---|"]
    lines += [f"| `{c['ref']}` | {c['conflict']} | {c['impact']} |" for c in conflicts]
    return "\n".join(lines)

"""Is this the user's own wording? — the check behind "must_not_change, word for word".

Research §6.1: an interface, file or report the user says must not change is recorded in the
USER'S words, because Target Architecture turns each entry into a contract (CT-xx) that later
agents prove unchanged. A paraphrase ("the claims API" for "the /api/v1 claims API brokers
call") silently widens or narrows the contract. So the record tool checks each entry against
what the user actually said in this conversation, and refuses one it cannot find.

Matching is deliberately forgiving about the things that are not wording — case, runs of
whitespace, surrounding quotes and a trailing full stop — and strict about the words:

  - WHOLE WORDS: "api" is not found in "rapid", nor "port" in "report";
  - AT LEAST TWO WORDS: a single word ("call", "API") names no interface precisely enough to
    become a contract — that is the vague entry the prompt tells the agent to ask about.

What it cannot judge: a contiguous fragment of what the user said ("claims API" out of "the
/api/v1 claims API brokers call") is still their words. The prompt asks for the whole phrase.

    user_texts(session_id, tenant_id)  the user's messages in this conversation (best-effort)
    not_in_user_words(entries, texts)  the entries that are not the user's words
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

_SPACE = re.compile(r"\s+")
_EDGES = "\"'“”‘’`«». ,;:"


def normalise(text: str) -> str:
    return _SPACE.sub(" ", (text or "").casefold()).strip().strip(_EDGES).strip()


MIN_WORDS = 2


def _found(entry: str, haystack: list[str]) -> bool:
    needle = normalise(entry)
    if len(needle.split(" ")) < MIN_WORDS:
        return False
    pattern = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)")
    return any(pattern.search(h) for h in haystack)


def not_in_user_words(entries: Iterable[str], texts: Iterable[str]) -> list[str]:
    """The entries that are not the user's words: not found, as whole words, in any of `texts`
    (after `normalise`), or shorter than MIN_WORDS."""
    haystack = [normalise(t) for t in texts if t]
    return [e for e in entries if normalise(e) and not _found(e, haystack)]


async def user_texts(session_id: Optional[str], tenant_id: Optional[str]) -> Optional[list[str]]:
    """The user's messages in this conversation, or None when they cannot be read (no
    session, or the transcript is unavailable) — "could not check" is not "not said"."""
    if not session_id or not tenant_id:
        return None
    from shared.services.conversation_service import get_transcript  # noqa: PLC0415

    rows = await get_transcript(str(session_id), tenant_id=str(tenant_id))
    texts = [r.get("content") or "" for r in rows if r.get("role") == "user"]
    return texts or None

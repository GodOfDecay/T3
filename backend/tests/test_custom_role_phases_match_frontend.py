"""The custom-role composer offers every frontend Phase; the backend must accept each one.

`shared/routers/custom_roles._PHASES` calls `frontend/lib/schemas/enums.ts::Phase` its
contract, but nothing held them together, so when Track 3's seven new agents joined the
enum a custom role giving any of them access failed to save ("unknown agent phase").
Parsed, not copied, so it fails when they drift.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.routers.custom_roles import _PHASES

pytestmark = pytest.mark.unit


def _frontend_phases() -> set[str]:
    enums = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "schemas" / "enums.ts"
    if not enums.exists():
        pytest.skip(f"{enums} not present")
    block = re.search(r"export const Phase = z\.enum\(\[(.*?)\]\);", enums.read_text(encoding="utf-8"), re.S)
    assert block, "could not find the Phase enum"
    phases = set(re.findall(r'"([a-z_]+)"', block.group(1)))
    assert "requirements" in phases and "design_modernization" in phases, "parse went stale"
    return phases


def test_the_backend_accepts_exactly_the_phases_the_composer_offers():
    assert _PHASES == _frontend_phases()

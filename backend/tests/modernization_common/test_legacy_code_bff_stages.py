"""The frontend proxies the legacy-code routes for exactly the stages the backend lets read the code.

Phase G added Equivalence Testing to `legacy_code.TRACK3_STAGES` but not to the BFF allow-lists, so its
page always read "No legacy code pulled yet" (the proxy answered 404 before the backend was asked).
The render tests mock the API and could not see it; this reads the route files themselves.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from agents_orchestrator.modernization_common.legacy_code import TRACK3_STAGES

ROUTES = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "app" / "api" / "projects" / "[id]" \
    / "modernization" / "legacy-code"


@pytest.mark.parametrize("route", ["route.ts", "repositories/route.ts"])
def test_the_proxy_allows_every_stage_that_reads_legacy_code_and_no_other(route):
    text = (ROUTES / route).read_text(encoding="utf-8")
    found = re.search(r"const STAGES = new Set\(\[([^\]]*)\]\)", text)
    assert found, f"{route} no longer declares STAGES"
    assert set(re.findall(r'"([a-z_]+)"', found.group(1))) == set(TRACK3_STAGES)

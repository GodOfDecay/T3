"""Track 3 hand-over contracts: packet models, their JSON Schemas, and ClaimTrack fixtures.

    schemas/<packet>.json            exported from the models — regenerate with
                                     `uv run python -m agents_orchestrator.modernization_common.handover`
    fixtures/claimtrack/<packet>.json  one ClaimTrack instance per packet (research §9)

The checked-in schemas are pinned to the models by a test, so editing one without the
other fails rather than drifting.
"""
from __future__ import annotations

import json
from pathlib import Path

from .packets import PACKETS

HERE = Path(__file__).parent
SCHEMA_DIR = HERE / "schemas"
FIXTURE_DIR = HERE / "fixtures" / "claimtrack"


def json_schema(name: str) -> dict:
    """The JSON Schema for packet `name`, as the model defines it today."""
    return PACKETS[name].model_json_schema(by_alias=True)


def render_schema(name: str) -> str:
    return json.dumps(json_schema(name), indent=2, sort_keys=True) + "\n"


def load_fixture(name: str):
    """The ClaimTrack fixture for packet `name`, validated."""
    return PACKETS[name].model_validate_json((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def write_schemas() -> list[Path]:
    SCHEMA_DIR.mkdir(exist_ok=True)
    written = []
    for name in PACKETS:
        path = SCHEMA_DIR / f"{name}.json"
        path.write_text(render_schema(name), encoding="utf-8", newline="\n")
        written.append(path)
    return written


__all__ = ["PACKETS", "FIXTURE_DIR", "SCHEMA_DIR", "json_schema", "load_fixture", "render_schema",
           "write_schemas"]

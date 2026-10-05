"""ClaimTrack Lite for Migration Development (Phase H): a target design that matches the sample.

The Phase G tests reuse the full ClaimTrack design (Java, MySQL, five modules) relabelled; its traps name
Java files the sample does not have. Migration Development reads traps and contracts per module and must
handle each, so its tests need the design ClaimTrack Lite actually has: two Python 2.7 modules moving to
Python 3.12 in place, the claims API (CT-01) and the bank file (CT-02), and the two traps a 2→3 port
really meets here.
"""
from __future__ import annotations

import copy

from tests.design_modernization.claimtrack import fixture

TRAPS = [
    {"id": "TR-01", "change": "Python 3 round() rounds halves to even", "affects": ["M-01", "M-02"],
     "where": "claims-api/server.py payout(); settlement-batch/run.py cents()",
     "effect": "half-cent payouts (CLM-0004, CLM-0007) pay a cent less", "contract_ids": ["CT-01", "CT-02"]},
    {"id": "TR-02", "change": "Python 3 separates bytes and text", "affects": ["M-01"],
     "where": "claims-api/server.py Handler.reply()",
     "effect": "writing a str to the socket raises TypeError: every response fails", "contract_ids": ["CT-01"]},
]


def design() -> dict:
    """The stored target design (`TargetDesignArtifact` as a dict) for ClaimTrack Lite."""
    from shared.models.artifacts import TargetDesignArtifact

    d = copy.deepcopy(fixture("design")["payload"])
    by_id = {m["module_id"]: m for m in d["modules"]}
    by_id["M-01"].update(tier="llm_assisted", patterns=["in_place_upgrade"], contract_ids=["CT-01"],
                         rationale="Python 2.7 is end of life; the API moves to 3.12 in place, rounding kept.")
    by_id["M-02"].update(tier="llm_assisted", patterns=["in_place_upgrade", "strangler_fig"], contract_ids=["CT-02"],
                         rationale="The bank file moves to 3.12 in place; cp1252 and the rounding kept.")
    d["traps"] = copy.deepcopy(TRAPS)
    return TargetDesignArtifact(**d, system_name="ClaimTrack Lite",
                                module_paths={"M-01": "claims-api", "M-02": "settlement-batch"}).model_dump(mode="json")

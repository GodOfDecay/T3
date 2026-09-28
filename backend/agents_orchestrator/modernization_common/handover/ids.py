"""The stable cross-agent ids every Track 3 artifact cites (Flow document §20.4).

A later agent cites an earlier decision BY ID and never re-derives it, so the shape of an id
is part of the hand-over contract: a Strategy criterion that says it protects `CT-1` instead
of `CT-01` points at nothing, silently. The patterns live here once, and every packet field
that holds an id is typed with one of them.

Widths follow the documents' examples: two digits for the planning ids (M-02, CT-01, TR-03,
ADR-04, EC-01, BL-01), three for the per-module findings, which accumulate across rework
rounds (F-012, S-004, EQ-031). A wave is `W<n>` (the documents write both `W-x` and `W0`;
every example uses `W0`, `W2`, so that is the form). A cutover step is `CO-<wave>.<n>`, and
the decommission steps, which belong to no wave, use `D` for the wave (`CO-D.6`).
"""
from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

MODULE = r"^M-\d{2,}$"
CONTRACT = r"^CT-\d{2,}$"
TRAP = r"^TR-\d{2,}$"
ADR = r"^ADR-\d{2,}$"
WAVE = r"^W\d+$"
CRITERION = r"^EC-\d{2,}$"
BASELINE = r"^BL-\d{2,}$"
REVIEW_FINDING = r"^F-\d{3,}$"
SECURITY_FINDING = r"^S-\d{3,}$"
DIFFERENCE = r"^EQ-\d{3,}$"
CUTOVER_STEP = r"^CO-(\d+|D)\.\d+$"

ModuleId = Annotated[str, StringConstraints(pattern=MODULE)]
ContractId = Annotated[str, StringConstraints(pattern=CONTRACT)]
TrapId = Annotated[str, StringConstraints(pattern=TRAP)]
AdrId = Annotated[str, StringConstraints(pattern=ADR)]
WaveId = Annotated[str, StringConstraints(pattern=WAVE)]
CriterionId = Annotated[str, StringConstraints(pattern=CRITERION)]
BaselineId = Annotated[str, StringConstraints(pattern=BASELINE)]
ReviewFindingId = Annotated[str, StringConstraints(pattern=REVIEW_FINDING)]
SecurityFindingId = Annotated[str, StringConstraints(pattern=SECURITY_FINDING)]
DifferenceId = Annotated[str, StringConstraints(pattern=DIFFERENCE)]
CutoverStepId = Annotated[str, StringConstraints(pattern=CUTOVER_STEP)]

#: Any id another artifact may cite in a `protects` / `refs` list.
_REFERENCE = "^(?:" + "|".join(p.strip("^$") for p in (
    MODULE, CONTRACT, TRAP, ADR, CRITERION, BASELINE, REVIEW_FINDING, SECURITY_FINDING, DIFFERENCE,
)) + ")$"
ReferenceId = Annotated[str, StringConstraints(pattern=_REFERENCE)]

#: Prefix → width used when minting, so a minted id always satisfies its own pattern.
_MINT: dict[str, int] = {
    "M": 2, "CT": 2, "TR": 2, "ADR": 2, "EC": 2, "BL": 2, "F": 3, "S": 3, "EQ": 3,
}


def mint(prefix: str, n: int) -> str:
    """The `n`th id for `prefix` (1-based): `mint("CT", 4)` → `"CT-04"`.

    Refuses an unknown prefix or a non-positive number rather than inventing a shape.
    Waves and cutover steps are not minted here: their numbers carry meaning (W0 is
    always the foundation; CO-2.4 is step 4 of wave 2), so they are written, not counted.
    """
    if prefix not in _MINT:
        raise ValueError(f"no id scheme for prefix {prefix!r}")
    if n < 1:
        raise ValueError(f"ids start at 1, got {n}")
    return f"{prefix}-{n:0{_MINT[prefix]}d}"

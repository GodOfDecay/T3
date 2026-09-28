"""`gate_routing` answers from the one owner map, and refuses a stage it does not know.

It used to hold a fourth owner table (`GATE_OWNER`) with roles the platform does not have
and a `"product_manager"` default for any unknown stage — Lessons R10's swallowing
default. Nothing called it; it is now a read-only view of `AGENT_OWNER_ROLE`.
"""
from __future__ import annotations

import pytest

from shared.governance.routing import AGENT_OWNER_ROLE, UnknownAgentPhase
from shared.services.orchestrator.gate_routing import GATE_OWNER, gate_owner_role

pytestmark = pytest.mark.unit

TRACK3 = {
    "requirements_modernization": "ba", "discovery": "ba",
    "design_modernization": "architect", "strategy": "architect",
    "testing_modernization": "qa", "development_modernization": "developer",
    "code_review_modernization": "architect", "security_modernization": "security_engineer",
    "deployment_modernization": "devops_engineer", "documentation_modernization": "ba",
}


@pytest.mark.parametrize("stage,owner", sorted(TRACK3.items()))
def test_every_track3_stage_resolves_to_its_owner(stage, owner):
    assert gate_owner_role(stage) == owner


def test_track1_stages_resolve_to_real_platform_roles():
    assert gate_owner_role("requirements") == "ba"
    assert gate_owner_role("code_review") == "architect"
    assert gate_owner_role("review") == "architect"  # the UI name is an alias


@pytest.mark.parametrize("stage", ["not_a_stage", "migration", ""])
def test_an_unknown_stage_raises_instead_of_naming_a_default(stage):
    with pytest.raises(UnknownAgentPhase):
        gate_owner_role(stage)


def test_gate_owner_is_a_read_only_view_not_a_copy():
    assert dict(GATE_OWNER) == AGENT_OWNER_ROLE
    with pytest.raises(TypeError):
        GATE_OWNER["development_modernization"] = "architect"  # type: ignore[index]
    assert "product_manager" not in set(GATE_OWNER.values())

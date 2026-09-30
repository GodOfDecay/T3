"""R10 for Track 3: all ten agents have an owner in every backend map, in one change.

The existing pins compare maps with each other, iterating over the ids a map already has —
so an id missing from a map entirely passed them (a mutation that deleted the Cutover
Pack from `_OWNER_OF` survived). This names the ten ids and checks each map for each.
"""
from __future__ import annotations

import pytest

from config.agent_registry import AGENT_DEFAULT_REACH, TRACK_PORTFOLIOS
from shared.authz.permissions import _PHASE_PERMISSION, _ROLE_PERMISSIONS
from shared.governance.routing import AGENT_OWNER_ROLE

pytestmark = pytest.mark.unit

TRACK3 = {
    "requirements_modernization": "ba", "discovery": "ba",
    "design_modernization": "architect", "strategy": "architect",
    "testing_modernization": "qa", "development_modernization": "developer",
    "code_review_modernization": "architect", "security_modernization": "security_engineer",
    "deployment_modernization": "devops_engineer", "documentation_modernization": "ba",
}


@pytest.mark.parametrize("agent,owner", sorted(TRACK3.items()))
def test_every_track3_agent_is_owned_the_same_way_in_every_map(agent, owner):
    assert AGENT_OWNER_ROLE.get(agent) == owner
    reach = AGENT_DEFAULT_REACH.get(agent)
    assert reach is not None, f"{agent} missing from config.agent_registry._OWNER_OF"
    assert reach[owner] == "owner" and reach["project_admin"] == "owner"
    permission = _PHASE_PERMISSION.get(agent)
    assert permission == f"artifact:approve_{agent}" or (
        agent == "discovery" and permission == "artifact:approve_discovery")
    for role in (owner, "project_admin", "bu_admin"):
        assert permission in _ROLE_PERMISSIONS[role], f"{role} cannot approve {agent}"


def test_only_built_track3_agents_are_in_the_portfolio():
    """Owner rows are not a build: the portfolio (what the Orchestrator offers and the
    track check admits) grows one agent at a time, as each is built."""
    assert TRACK_PORTFOLIOS["modernization"] == ["requirements_modernization", "discovery", "design_modernization", "strategy"]

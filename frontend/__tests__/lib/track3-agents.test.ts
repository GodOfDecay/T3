import { describe, expect, it } from "vitest";

import {
  BUILT_AGENTS,
  GATE_POLICY,
  PHASE_LABEL,
  builtAgentsForTrack,
  phaseHref,
  phaseRoute,
} from "@/lib/agents";
import { tileStateFor } from "@/lib/agent-access";
import { AGENT_OWNER_ROLE, AGENT_OWNERSHIP } from "@/lib/roles";
import { agentsForTrack, trackHasAgent } from "@/lib/tracks";
import { OrchestratorAgentId } from "@/lib/orchestrator/agents";
import { PHASE_FOR_AGENT, agentLabel } from "@/lib/orchestrator/types";
import { toolStagesForTrack } from "@/components/app/tools-stage-picker";
import { approvePermissionForPhase } from "@/lib/auth/permissions";

/**
 * Track 3 (Code Modernization) Phase 1: its first two agents are real, and they are
 * TRACK 3's — its own Migration Intent agent and Dependency and Risk —
 * while the other eight of its roster stay "Coming soon" even though Portfolio 1
 * agents with the same names are built.
 */
describe("Track 3 roster", () => {
  it("starts with its own Migration Intent agent, then Dependency and Risk", () => {
    const roster = agentsForTrack("modernization");
    expect(roster.slice(0, 2)).toEqual(["requirements_modernization", "discovery"]);
    expect(roster).toHaveLength(10);
    expect(roster).not.toContain("requirements");
  });

  it("never appears on a Greenfield or Enhancement project", () => {
    for (const track of ["greenfield", "enhancement"] as const) {
      expect(trackHasAgent(track, "requirements_modernization")).toBe(false);
      expect(trackHasAgent(track, "discovery")).toBe(false);
    }
  });

  it("builds exactly its first eight agents; Portfolio 1's list is unchanged", () => {
    expect(builtAgentsForTrack("modernization")).toEqual(["requirements_modernization", "discovery", "design_modernization", "strategy",
      "testing_modernization", "development_modernization", "code_review_modernization", "security_modernization"]);
    expect(builtAgentsForTrack("greenfield")).toBe(BUILT_AGENTS);
    expect(BUILT_AGENTS).not.toContain("discovery");
  });

  it("routes to its own pages", () => {
    expect(phaseRoute("requirements_modernization")).toBe("requirements-modernization");
    expect(phaseHref("p1", "discovery")).toBe("/projects/p1/discovery");
    expect(PHASE_LABEL.requirements_modernization).toBe("Migration Intent");
  });
});

describe("Track 3 tiles", () => {
  const built = builtAgentsForTrack("modernization");

  it("gives the BA ownership of both agents — the product decision for Track 3", () => {
    expect(tileStateFor("ba", "requirements_modernization", "modernization", built)).toBe("owner");
    expect(tileStateFor("ba", "discovery", "modernization", built)).toBe("owner");
  });

  it("gives the Project Admin both, as the fallback owner on every agent", () => {
    expect(tileStateFor("project_admin", "requirements_modernization", "modernization", built)).toBe("owner");
    expect(tileStateFor("project_admin", "discovery", "modernization", built)).toBe("owner");
  });

  it("locks them for roles that do not own them", () => {
    expect(tileStateFor("architect", "discovery", "modernization", built)).toBe("locked");
    expect(tileStateFor("developer", "requirements_modernization", "modernization", built)).toBe("locked");
  });

  it("shows the rest of Track 3's roster as Coming soon, even for the Project Admin", () => {
    // "strategy" is Track 3's Migration Strategy on this track (built, Phase F): tested below.
    for (const phase of ["design", "development", "review", "security", "testing", "deployment", "documentation"] as const) {
      expect(tileStateFor("project_admin", phase, "modernization", built)).toBe("coming_soon");
    }
  });

  it("keeps the ownership tables and gate policy in agreement", () => {
    expect(AGENT_OWNER_ROLE.requirements_modernization).toBe("ba");
    expect(AGENT_OWNER_ROLE.discovery).toBe("ba");
    expect(AGENT_OWNERSHIP.architect.discovery).toBe("none");
    expect(GATE_POLICY.discovery.ownerLabel).toBe(GATE_POLICY.requirements_modernization.ownerLabel);
    expect(approvePermissionForPhase("discovery")).toBe("artifact:approve_discovery");
    expect(approvePermissionForPhase("requirements_modernization")).toBe("artifact:approve_requirements_modernization");
  });
});

describe("Track 3 in the Orchestrator", () => {
  it("accepts both agents on the wire — an unknown id would be dropped by Zod", () => {
    expect(OrchestratorAgentId.parse("discovery")).toBe("discovery");
    expect(OrchestratorAgentId.parse("requirements_modernization")).toBe("requirements_modernization");
  });

  it("labels them the way the rest of the app does", () => {
    expect(PHASE_FOR_AGENT.discovery).toBe("discovery");
    expect(agentLabel("discovery")).toBe("Dependency and Risk");
    expect(agentLabel("requirements_modernization")).toBe("Migration Intent");
  });
});

describe("Track 3 tool wiring", () => {
  it("lists the track's own ten stages, so each can be given its own connectors", () => {
    // Track 3's stages are ALL its own agents. This list used to include Portfolio 1's
    // `design`, `development`, `code_review` … — so a connector wired "to Development"
    // on a Code Modernization project went to the Track 1 agent's stage.
    const ids = toolStagesForTrack("modernization").map((s) => s.id);
    expect(ids).toEqual([
      "requirements_modernization", "discovery", "design_modernization", "strategy",
      "testing_modernization", "development_modernization", "code_review_modernization",
      "security_modernization", "deployment_modernization", "documentation_modernization",
    ]);
    for (const portfolio1 of ["design", "plan", "development", "code_review", "security",
      "testing", "deployment", "documentation"]) {
      expect(ids).not.toContain(portfolio1);
    }
  });

  it("keeps the Greenfield stages exactly as before", () => {
    const ids = toolStagesForTrack("greenfield").map((s) => s.id);
    expect(ids).toEqual([
      "requirements", "design", "plan", "development", "code_review",
      "security", "testing", "deployment", "documentation",
    ]);
  });
});

/**
 * Track 3 agents 3–10 (Phase B of the Track 3 build): every table knows them, their owner
 * is fixed once, and nothing about them is clickable until each is built.
 */
describe("Track 3 agents 3–10", () => {
  const LATER: Record<string, { owner: string; label: string; route: string }> = {
    design_modernization: { owner: "architect", label: "Target Architecture", route: "target-architecture" },
    strategy: { owner: "architect", label: "Migration Strategy", route: "strategy" },
    testing_modernization: { owner: "qa", label: "Equivalence Testing", route: "equivalence-testing" },
    development_modernization: { owner: "developer", label: "Migration Development", route: "migration-development" },
    code_review_modernization: { owner: "architect", label: "Migration Review", route: "migration-review" },
    security_modernization: { owner: "security_engineer", label: "Security (Modernization)", route: "modernization-security" },
    deployment_modernization: { owner: "devops_engineer", label: "Cutover", route: "cutover" },
    documentation_modernization: { owner: "ba", label: "Cutover Pack", route: "cutover-pack" },
  };

  it("are the roster's stages 3–10, baseline before migration", () => {
    expect(agentsForTrack("modernization").slice(2)).toEqual([
      "design_modernization", "strategy", "testing_modernization", "development_modernization",
      "code_review_modernization", "security_modernization", "deployment_modernization",
      "documentation_modernization",
    ]);
  });

  it("each has one owner, its own approve permission, a label, a route and a gate", () => {
    for (const [phase, want] of Object.entries(LATER)) {
      const p = phase as keyof typeof AGENT_OWNER_ROLE;
      expect(AGENT_OWNER_ROLE[p], phase).toBe(want.owner);
      expect(AGENT_OWNERSHIP[want.owner as keyof typeof AGENT_OWNERSHIP][p], phase).toBe("owner");
      expect(approvePermissionForPhase(p), phase).toBe(`artifact:approve_${phase}`);
      expect(PHASE_LABEL[p], phase).toBe(want.label);
      expect(phaseRoute(p), phase).toBe(want.route);
      expect(GATE_POLICY[p].ownerLabel, phase).toBeTruthy();
    }
  });

  it("the mandatory gates are the ones the flow document makes mandatory", () => {
    expect(GATE_POLICY.testing_modernization.mandatory).toBe(true);
    expect(GATE_POLICY.security_modernization.mandatory).toBe(true);
    expect(GATE_POLICY.deployment_modernization.mandatory).toBe(true);
    expect(GATE_POLICY.documentation_modernization.type).toBe("auto_approve");
  });

  it("unlock one at a time as each is built: Target Architecture (Phase E) for its owner", () => {
    const built = builtAgentsForTrack("modernization");
    expect(tileStateFor("architect", "design_modernization", "modernization", built)).not.toBe("coming_soon");
    expect(tileStateFor("project_admin", "design_modernization", "modernization", built)).not.toBe("coming_soon");
    expect(tileStateFor("developer", "design_modernization", "modernization", built)).not.toBe("available");
  });

  it("then Migration Strategy (Phase F), for the Architect and the Project Admin", () => {
    const built = builtAgentsForTrack("modernization");
    expect(tileStateFor("architect", "strategy", "modernization", built)).toBe("owner");
    expect(tileStateFor("project_admin", "strategy", "modernization", built)).toBe("owner");
    expect(tileStateFor("developer", "strategy", "modernization", built)).not.toBe("available");
  });

  it("then Equivalence Testing (Phase G, Baseline mode), for QA and the Project Admin", () => {
    const built = builtAgentsForTrack("modernization");
    expect(tileStateFor("qa", "testing_modernization", "modernization", built)).toBe("owner");
    expect(tileStateFor("project_admin", "testing_modernization", "modernization", built)).toBe("owner");
    expect(tileStateFor("developer", "testing_modernization", "modernization", built)).not.toBe("available");
  });

  it("then Migration Development, Migration Review and Security (Phases H and I), each for its owner", () => {
    const built = builtAgentsForTrack("modernization");
    for (const [role, phase] of [["developer", "development_modernization"], ["architect", "code_review_modernization"],
      ["security_engineer", "security_modernization"]] as const) {
      expect(tileStateFor(role, phase, "modernization", built), phase).toBe("owner");
      expect(tileStateFor("project_admin", phase, "modernization", built), phase).toBe("owner");
      expect(tileStateFor("qa", phase, "modernization", built), phase).not.toBe("available");
    }
  });

  it("stay locked, even for their owner and the Project Admin, until each is built", () => {
    const built = builtAgentsForTrack("modernization");
    for (const [phase, want] of Object.entries(LATER)) {
      const p = phase as keyof typeof AGENT_OWNER_ROLE;
      if (built.includes(p)) continue; // built (E to I): above
      expect(built).not.toContain(p);
      expect(tileStateFor(want.owner as never, p, "modernization", built), phase).toBe("coming_soon");
      expect(tileStateFor("project_admin", p, "modernization", built), phase).toBe("coming_soon");
    }
  });

  it("never appear on another track", () => {
    for (const track of ["greenfield", "enhancement", "rpa_infra", "data_engineering"] as const) {
      for (const phase of Object.keys(LATER)) {
        expect(trackHasAgent(track, phase as never), `${track}/${phase}`).toBe(false);
      }
    }
  });
});

"use client";

import { useParams } from "next/navigation";

import { ErrorState } from "@/components/ui/error-state";
import { StrategyView } from "@/components/modernization/strategy-view";
import { Track3AgentPage } from "@/components/modernization/track3-agent-page";
import type { ProjectId } from "@/lib/schemas";
import { MigrationPlan } from "@/lib/schemas/modernization";

/**
 * Migration Strategy — Track 3 (Code Modernization), research §6.4. Replaces the Phase 0 stub.
 *
 * The agent sequences the approved target design into waves that can be executed AND proven:
 * the order and why, the equivalence criteria, the legacy baselines to record first, the change
 * freeze, the rollback per wave, the calendar conflicts and an effort estimate. Every plan it records
 * is a frozen version on the left; accepting one is the Architect's Sign-off (or a Project Admin's, as
 * labelled fallback), and that approval sequences the modules on the migration ledger. It works from
 * documents, not code, so the page shows no legacy-code controls.
 */
export default function StrategyPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id as ProjectId;
  return (
    <Track3AgentPage
      phase="strategy"
      runLabel="Run Migration Strategy agent"
      intro="Sequences the approved target design into waves: the order and why, measurable equivalence criteria, the legacy baselines to record first, the change freeze, the rollback per wave, calendar conflicts and an effort estimate."
      noun="migration plan"
      historyTitle="Migration plans"
      guideTitle="How a migration plan gets made"
      showLegacyCode={false}
      guide={({ run }) => [
        {
          title: "Approve the brief, the assessment and the target design",
          body: "The plan is built from all three and checked against them. Approve each on its own page first; until then (or where the project allows it, until their newest drafts exist) the plan is provisional or cannot be recorded. Approving the target design is also what puts the modules on the migration ledger.",
        },
        {
          title: "Run the Migration Strategy agent",
          body: "It starts from a dependency-safe order computed from the assessment's graph, lays the waves against the brief's deadline, freeze, milestones and cutover window, estimates effort from a stated table, and asks what only you can decide. It records the plan once you agree — and refuses one that leaves a module out, changes a pattern, moves a module before what it depends on without a design ADR, leaves a contract, trap or success measure unprotected, or hides a calendar conflict.",
          action: { label: "Run Migration Strategy agent", onClick: run },
        },
        {
          title: "Review and sign off",
          body: "Each plan appears on the left as a new version: its timeline, waves, criteria, baselines, calendar conflicts, order and effort; download it as Word or PDF, and accept it — an Architect who did not produce it, or a Project Admin. Approval sequences every planned module on the ledger in its wave.",
        },
        {
          title: "Write the waves to the board",
          body: "Ask the agent to write the plan to Azure DevOps or Jira: it shows exactly the Features (one per wave) and items (one per module) it will create, and writes them only when an Architect or Project Admin of this project says yes.",
        },
      ]}
      renderVersion={(payload, detail) => {
        const parsed = MigrationPlan.safeParse(payload);
        return parsed.success ? (
          <StrategyView plan={parsed.data} projectId={projectId} approved={detail.status === "published"}
            status={detail.status} />
        ) : (
          <ErrorState title="This migration plan could not be read" description="Its saved shape is not one this page understands." />
        );
      }}
    />
  );
}

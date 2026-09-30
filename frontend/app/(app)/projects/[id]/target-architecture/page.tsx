"use client";

import { useParams } from "next/navigation";

import { ErrorState } from "@/components/ui/error-state";
import { LegacyInterfacesButton } from "@/components/modernization/legacy-interfaces-dialog";
import { TargetDesignView } from "@/components/modernization/target-design-view";
import { Track3AgentPage } from "@/components/modernization/track3-agent-page";
import type { ProjectId } from "@/lib/schemas";
import { TargetDesign } from "@/lib/schemas/modernization";

/**
 * Target Architecture — Track 3 (Code Modernization), research §6.3.
 *
 * The agent designs WHAT THE SYSTEM BECOMES and HOW OLD AND NEW COEXIST, from the approved brief
 * and assessment and the legacy code. Every design it records is a frozen version on the left;
 * accepting one is the Architect's Sign-off (or a Project Admin's, as labelled fallback), and that
 * approval — not the recording — puts the modules on the migration ledger as "designed".
 */
export default function TargetArchitecturePage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id as ProjectId;
  return (
    <Track3AgentPage
      phase="design_modernization"
      runLabel="Run Target Architecture agent"
      intro="Designs the target from the approved brief and assessment: the target per part of the system, a migration pattern per module, how old and new coexist, the interfaces that must not change, the version traps, and the decisions as ADRs with diagrams."
      noun="target design"
      historyTitle="Target designs"
      guideTitle="How a target design gets made"
      showTechStack
      headerActions={<LegacyInterfacesButton projectId={projectId} />}
      guide={({ pull, run, legacy, legacyStatus }) => [
        {
          title: "Approve the brief and the assessment",
          body: "The design starts from the Migration Intent brief and the Dependency and Risk assessment. Approve both on their pages first; until they are approved (or, where the project allows it, their newest drafts exist) the agent cannot record a design.",
        },
        {
          title: "Check the legacy code",
          body: "The agent reads the same read-only checkout the assessment was made from, and lists what it exposes and consumes — endpoints, files, jobs, tables, queues — to find the contracts that must not change. See them under Legacy interfaces.",
          status: legacyStatus,
          action: {
            label: legacy?.pull ? "Pull again" : "Pull legacy code",
            onClick: pull,
            disabled: legacy?.status === "pulling",
          },
        },
        {
          title: "Run the Target Architecture agent",
          body: "It proposes the target per part of the system and a pattern for every module, asks what the code could not tell it, and records the design once you agree. It refuses a design that drops a module, changes a score, leaves a must-not-change item unfrozen, or targets a runtime or database version past or near its end of support (.NET, Java, Node.js, Python, PHP, Ruby, Go, MySQL, PostgreSQL, SQL Server; others are noted as not checked).",
          action: { label: "Run Target Architecture agent", onClick: run },
        },
        {
          title: "Review and sign off",
          body: "Each design appears on the left as a new version: explore its modules, contracts, traps, decisions and diagrams, download it as Word or PDF, and accept it — an Architect who did not produce it, or a Project Admin. Approval puts every module on the migration ledger as designed, ready for Migration Strategy.",
        },
      ]}
      renderVersion={(payload, detail) => {
        const parsed = TargetDesign.safeParse(payload);
        return parsed.success ? (
          <TargetDesignView design={parsed.data} projectId={projectId} approved={detail.status === "published"}
            status={detail.status} />
        ) : (
          <ErrorState
            title="This target design could not be read"
            description="Its saved shape is not one this page understands."
          />
        );
      }}
    />
  );
}

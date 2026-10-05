"use client";

import { useParams } from "next/navigation";

import { ErrorState } from "@/components/ui/error-state";
import { MigrationView, WorkspacesButton } from "@/components/modernization/migration-view";
import { Track3AgentPage } from "@/components/modernization/track3-agent-page";
import type { ProjectId } from "@/lib/schemas";
import { Migration } from "@/lib/schemas/modernization";

/**
 * Migration Development — Track 3 agent 6 (research §6.6, Phase H). A Developer drives it.
 *
 * One module at a time into the TARGET repository: the legacy module copied in, upgrade recipes, the build
 * moved as its own commit, hand rewrites for what the recipes cannot see (the design's traps), build / tests
 * / lint in a sandbox (at most five build rounds), an equivalence preview against the accepted baseline,
 * and the record — every legacy file accounted for. Each record is a version here; once another Developer
 * or a Project Admin accepts it, the branch is pushed and the pull request opened (a Consequential action).
 */
export default function MigrationDevelopmentPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id as ProjectId;
  return (
    <Track3AgentPage
      phase="development_modernization"
      runLabel="Run Migration Development agent"
      intro="Migrates the legacy system into the target repository one module at a time — recipes first, the rest rewritten with the legacy code, the frozen contracts and the traps in view — and opens a pull request only once the record is accepted."
      noun="migration record"
      historyTitle="Migration records"
      guideTitle="How a module gets migrated"
      headerActions={<WorkspacesButton projectId={projectId} />}
      guide={({ run, pull, legacy }) => [
        {
          title: "Accept the baseline, set the target",
          body: "A module is migrated only once its behaviour baseline is accepted on Equivalence Testing — otherwise nothing can prove the migration. A Project Admin sets the project's target repository (an empty one is fine) and wires its connection to this stage with write access. The legacy code must be pulled: the module is copied from it.",
          action: legacy?.pull ? undefined : { label: "Pull legacy code", onClick: pull },
        },
        {
          title: "Migrate a module",
          body: "The agent opens a branch on the target, copies the legacy module in unchanged, runs the upgrade recipes the toolchain offers, moves the build in its own commit, and rewrites what the recipes cannot see — the design's traps — reading each legacy file first. Builds, tests and lint run in an isolated sandbox, at most five build rounds.",
          action: { label: "Run Migration Development agent", onClick: run },
        },
        {
          title: "Preview, then record",
          body: "Before recording, the agent replays the module's scenarios against the accepted baseline: a hint, not the verdict. The record accounts for every legacy file (mapped, merged or dropped with a reason), every trap and where it is handled, and the secrets to provision — as references, never values.",
        },
        {
          title: "Accept, then push",
          body: "Another Developer or a Project Admin accepts the record here. Only then, and after you confirm in the chat, is the branch pushed — exactly the accepted commit, never forced — and the pull request opened for Migration Review and Security.",
        },
      ]}
      renderVersion={(payload, detail) => {
        const parsed = Migration.safeParse(payload);
        return parsed.success ? (
          <MigrationView migration={parsed.data} projectId={projectId} approved={detail.status === "published"}
            status={detail.status} />
        ) : (
          <ErrorState title="This migration record could not be read" description="Its saved shape is not one this page understands." />
        );
      }}
    />
  );
}

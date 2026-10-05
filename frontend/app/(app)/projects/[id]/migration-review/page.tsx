"use client";

import { useParams } from "next/navigation";

import { ErrorState } from "@/components/ui/error-state";
import { ReviewView } from "@/components/modernization/review-security-view";
import { Track3AgentPage } from "@/components/modernization/track3-agent-page";
import type { ProjectId } from "@/lib/schemas";
import { MigrationReview } from "@/lib/schemas/modernization";

/**
 * Migration Review — Track 3 agent 7 (research §6.7, Phase I). The Architect owns it.
 *
 * One module's pull request at a time, read side by side with the legacy code: every frozen contract,
 * trap, criterion and legacy file answered; the API diff and the anti-pattern scan computed, not stated;
 * findings citing files the review actually opened. Each review is a version here; accepting it (an
 * Architect who did not submit it, or a Project Admin) writes the recommendation on the ledger.
 */
export default function MigrationReviewPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id as ProjectId;
  return (
    <Track3AgentPage
      phase="code_review_modernization"
      runLabel="Run Migration Review agent"
      intro="Reviews a module's migration pull request side by side with the legacy code — the frozen interfaces, the version traps, what was carried over and what was added — and gives a merge recommendation. Read-only on both repositories."
      noun="migration review"
      historyTitle="Migration reviews"
      guideTitle="How a migration gets reviewed"
      guide={({ run, pull, legacy }) => [
        {
          title: "A module in review",
          body: "Migration Development records the module, another Developer accepts the record, and the pull request is opened: the module is then in review. What was accepted is what is reviewed — the exact commit. The legacy code must be pulled for the side-by-side reading.",
          action: legacy?.pull ? undefined : { label: "Pull legacy code", onClick: pull },
        },
        {
          title: "Review side by side",
          body: "The agent reads each migrated file and its legacy counterpart, computes the API diff (routes, status codes, SQL, file formats) and scans both sides for legacy anti-patterns, then answers every contract, trap, criterion and legacy file. A finding can only cite a file it opened.",
          action: { label: "Run Migration Review agent", onClick: run },
        },
        {
          title: "Accept the review",
          body: "An Architect who did not submit it, or a Project Admin, accepts it here. Accepting records the recommendation on the migration ledger: with Security's sign-off also good the module goes to Equivalence Testing; request changes sends it back to Migration Development.",
        },
      ]}
      renderVersion={(payload, detail) => {
        const parsed = MigrationReview.safeParse(payload);
        return parsed.success ? (
          <ReviewView review={parsed.data} projectId={projectId} approved={detail.status === "published"} status={detail.status} />
        ) : (
          <ErrorState title="This review could not be read" description="Its saved shape is not one this page understands." />
        );
      }}
    />
  );
}

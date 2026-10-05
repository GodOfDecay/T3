"use client";

import { useParams } from "next/navigation";

import { ErrorState } from "@/components/ui/error-state";
import { CapturesButton, EquivalenceView } from "@/components/modernization/equivalence-view";
import { VerificationView } from "@/components/modernization/verification-view";
import { Track3AgentPage } from "@/components/modernization/track3-agent-page";
import type { ProjectId } from "@/lib/schemas";
import { Baseline, Verification } from "@/lib/schemas/modernization";

/**
 * Equivalence Testing — Track 3 agent 5 (research §6.5), Baseline mode (Phase G). QA owns it.
 *
 * Before any code changes, the agent runs the legacy system in an isolated sandbox and records what it
 * does for the approved plan's criteria — twice, so what varies on its own is known. The page shows
 * each recorded baseline (counts, fingerprints, the noise floor, the rules proposed to Migration
 * Strategy), the captures (in progress, failed — nothing kept), and the ledger acceptance moves.
 * Verify mode (proving migrated code against the baseline) arrives with Migration Development.
 */
export default function EquivalenceTestingPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id as ProjectId;
  return (
    <Track3AgentPage
      phase="testing_modernization"
      runLabel="Run Equivalence Testing agent"
      intro="Records what the legacy system actually does before any code changes — run in an isolated sandbox with synthetic data, twice — so every migrated module can later be proven against it."
      noun="baseline"
      historyTitle="Baselines"
      guideTitle="How a baseline gets recorded"
      headerActions={<CapturesButton projectId={projectId} />}
      guide={({ run, pull, legacy }) => [
        {
          title: "Approve the plan, pull the legacy code",
          body: "A baseline records the APPROVED migration plan's criteria, so the plan is approved first (on Migration Strategy) — that is what puts its modules on the ledger as sequenced. The legacy code must be pulled: the sandbox builds and runs it.",
          action: legacy?.pull ? undefined : { label: "Pull legacy code", onClick: pull },
        },
        {
          title: "Agree how the system is run",
          body: "The capture profile says how the legacy system is built, seeded with synthetic data, started, which external services are stubbed (the sandbox has no internet) and which scenarios exercise it. It comes with the code (sdlc-sandbox.json) or the agent drafts one with you.",
        },
        {
          title: "Capture — after your yes",
          body: "The agent maps each criterion to the scenarios that record it, shows you exactly what will run, and — only after QA or a Project Admin of this project says yes — runs the legacy system twice. What differs between the two runs (a timestamp, a generated id) needs a normalization rule; the agent proposes it to Migration Strategy, never applies it.",
          action: { label: "Run Equivalence Testing agent", onClick: run },
        },
        {
          title: "Accept the baseline",
          body: "Each recorded baseline appears on the left as a version: what was recorded per criterion with its fingerprint, the noise floor, the proposals and anything not captured. Accepting it (QA who did not record it, or a Project Admin) marks the modules baselined — Migration Development starts from there.",
        },
      ]}
      renderVersion={(payload, detail) => {
        const verify = Verification.safeParse(payload);
        if (verify.success) {
          return <VerificationView verification={verify.data} projectId={projectId} approved={detail.status === "published"}
            status={detail.status} />;
        }
        const parsed = Baseline.safeParse(payload);
        return parsed.success ? (
          <EquivalenceView baseline={parsed.data} projectId={projectId} approved={detail.status === "published"}
            status={detail.status} />
        ) : (
          <ErrorState title="This baseline could not be read" description="Its saved shape is not one this page understands." />
        );
      }}
    />
  );
}

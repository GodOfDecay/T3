"use client";

import { useParams } from "next/navigation";

import { ErrorState } from "@/components/ui/error-state";
import { SecurityView } from "@/components/modernization/review-security-view";
import { Track3AgentPage } from "@/components/modernization/track3-agent-page";
import type { ProjectId } from "@/lib/schemas";
import { ModernizationSecurity } from "@/lib/schemas/modernization";

/**
 * Security (Modernization) — Track 3 agent 8 (research §6.8, Phase I). The Security Engineer owns it; the
 * sign-off is mandatory.
 *
 * The migrated module and the legacy module scanned the same way (Trivy, Semgrep, Gitleaks — pinned,
 * offline), so every finding is carried over or introduced and what the migration fixed is evidence.
 * A legacy secret in the target, a reachable critical/high or a weaker contract fails it; a scanner that
 * did not run means "not scanned", never clean. Accepting a report records the sign-off on the ledger.
 */
export default function ModernizationSecurityPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id as ProjectId;
  return (
    <Track3AgentPage
      phase="security_modernization"
      runLabel="Run Security agent"
      intro="Security-scans a migrated module read-only — dependency vulnerabilities, static analysis, secrets, SBOM — and compares it with the same scan of the legacy code, so every finding is carried over, fixed or introduced; then issues the mandatory sign-off."
      noun="security report"
      historyTitle="Security reports"
      guideTitle="How a module gets its security sign-off"
      guide={({ run, pull, legacy }) => [
        {
          title: "A module in review",
          body: "The module's migration is accepted and its pull request is open. The legacy code must be pulled: the legacy module is scanned too. The scanners run on this server in isolated containers with no network; the dependency database is refreshed separately by an operator.",
          action: legacy?.pull ? undefined : { label: "Pull legacy code", onClick: pull },
        },
        {
          title: "Scan both sides",
          body: "The agent scans the migrated module and the legacy module, marks each finding carried over or introduced (and what was fixed), looks for any legacy secret value in the target, and compares the authorization of every frozen HTTP contract.",
          action: { label: "Run Security agent", onClick: run },
        },
        {
          title: "Sign off",
          body: "FAIL on a reachable critical or high (introduced or carried over), a legacy secret in the target, or a weaker contract; CONDITIONAL on the rest with a remediation date inside the wave; PASS otherwise — never with a scanner not run. A Security Engineer who did not submit it, or a Project Admin, accepts it here, which records it on the ledger.",
        },
      ]}
      renderVersion={(payload, detail) => {
        const parsed = ModernizationSecurity.safeParse(payload);
        return parsed.success ? (
          <SecurityView report={parsed.data} projectId={projectId} approved={detail.status === "published"} status={detail.status} />
        ) : (
          <ErrorState title="This security report could not be read" description="Its saved shape is not one this page understands." />
        );
      }}
    />
  );
}

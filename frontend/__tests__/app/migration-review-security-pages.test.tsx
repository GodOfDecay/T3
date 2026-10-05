// @vitest-environment jsdom
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import fixtures from "@/components/modernization/__tests__/fixtures.json";

/**
 * Migration Review and Security (Track 3, Phase I) — both pages and both versions, rendered from
 * BACKEND-PRODUCED fixtures (`help/Track-3/tools/regen_view_fixtures.py` builds them with the submit tools'
 * own builders; the API diff and the anti-pattern scan are computed by the review's analysis on the sample).
 *
 *   - the pages: the access gate, the guide;
 *   - a review: the recommendation, findings citing BOTH sides, every contract / trap / criterion / file,
 *     the computed API diff (409 → 400 and /metrics caught), files read;
 *   - a security report: the verdict, origins (carried over / introduced / fixed), a scanner not run is
 *     "not scanned" (never clean, never 0), the SBOM likewise;
 *   - acceptance and the ledger: what accepting records, never more than the hook enforces.
 */

const PROJECT = "55555555-5555-5555-5555-555555555555";

const state = vi.hoisted(() => ({
  track: "modernization" as string,
  me: { id: "u-arch2", email: "arch2@example.com" },
  version: {} as Record<string, unknown>,
  ledger: [] as Record<string, unknown>[],
  legacyCalls: 0,
  stage: "code_review_modernization",
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: PROJECT }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));
vi.mock("@/hooks/use-session", () => ({
  useSession: () => ({ user: state.me, permissions: ["artifact:view", "run:create", "artifact:approve_code_review_modernization", "artifact:approve_security_modernization"] }),
}));
vi.mock("@/hooks/use-agent-chat", () => ({
  useAgentChat: () => ({
    busy: false, messages: [], sessions: [], sessionId: null, attachments: [], documents: [],
    send: vi.fn(), cancel: vi.fn(), newChat: vi.fn(), selectSession: vi.fn(),
    attachFiles: vi.fn(), removeAttachment: vi.fn(),
  }),
}));
vi.mock("@/hooks/use-chat-deep-link", () => ({ useChatDeepLink: () => null }));
vi.mock("@/lib/api/projects", () => ({
  getProject: async () => ({ id: PROJECT, name: "ClaimTrack Lite", track: state.track }),
}));
vi.mock("@/lib/api/modernization", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  getVersionPacket: async (_p: string, stage: string, version: number) => ({ stage, version, ok: true, problems: [], packet: {} }),
  getLegacyCode: async () => {
    state.legacyCalls++;
    return { projectId: PROJECT, status: "ready", request: null, error: "",
      pull: { url: "https://example.test/claimtrack-lite", branch: "main", commit: "4f1c2e9a7b", provider: "public",
        name: "claimtrack-lite", pulledBy: "u-qa", pulledAt: "2026-12-01T08:00:00+00:00", profile: {} } };
  },
}));
vi.mock("@/lib/api/modernization-programme", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  getLedger: async () => ({ projectId: PROJECT, states: [], modules: state.ledger }),
}));
vi.mock("@/lib/api/artifact-versions", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  listStageVersions: async () => [state.version],
  getStageVersion: async () => state.version,
  getVersionConsumers: async () => ({ stage: state.stage, version: 1, status: "published", contentHash: "h", consumers: [] }),
  getVersionStaleness: async () => ({ stage: state.stage, version: 1, pinned: true, stale: false, inputs: [] }),
  publishStageVersion: vi.fn(),
  rejectStageVersion: vi.fn(),
}));
vi.mock("@/components/app/document-list", () => ({
  DocumentList: ({ stage }: { stage: string }) => <section aria-label="documents">documents for {stage}</section>,
}));
vi.mock("@/components/app/tech-stack-chip", () => ({ TechStackChip: () => <span>tech stack chip</span> }));
vi.mock("@/components/app/model-selector", () => ({ ModelSelector: () => null }));
vi.mock("@/components/app/agent-chat-drawer", () => ({ AgentChatDrawer: () => null }));

import MigrationReviewPage from "@/app/(app)/projects/[id]/migration-review/page";
import ModernizationSecurityPage from "@/app/(app)/projects/[id]/modernization-security/page";
import { ReviewView, SecurityView, sbomText, severityCounts, verdictLedgerText } from "@/components/modernization/review-security-view";
import { VersionView } from "@/components/modernization/version-view";
import { MigrationReview, ModernizationSecurity } from "@/lib/schemas/modernization";

const APPROVE = MigrationReview.parse(fixtures.review);
const CHANGES = MigrationReview.parse(fixtures.review_changes);
const SECURITY = ModernizationSecurity.parse(fixtures.security);
const UNSCANNED = ModernizationSecurity.parse(fixtures.security_unscanned);

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function ledgerRow(over: Record<string, unknown> = {}) {
  return { moduleId: "M-01", moduleName: "claims-api", legacyPath: "claims-api", state: "in_review", wave: "W1",
    prUrl: "https://github.com/claimtrack/claimtrack-lite-target/pull/1", reviewVerdict: null, securityVerdict: null, ...over };
}

beforeEach(() => {
  state.track = "modernization";
  state.me = { id: "u-arch2", email: "arch2@example.com" };
  state.stage = "code_review_modernization";
  state.version = { id: "v1", stage: "code_review_modernization", version: 1, status: "draft", contentHash: "h",
    producedBy: "arch@example.com", covers: [], payload: fixtures.review };
  state.ledger = [ledgerRow()];
  state.legacyCalls = 0;
});
afterEach(cleanup);

describe("the pages", () => {
  it("explain instead of opening a chat on a project of another track", async () => {
    state.track = "greenfield";
    wrap(<MigrationReviewPage />);
    expect(await screen.findByText("Migration Review is a Code Modernization agent")).toBeTruthy();
    cleanup();
    wrap(<ModernizationSecurityPage />);
    expect(await screen.findByText(/is a Code Modernization agent/)).toBeTruthy();
  });

  it("show the documents, the legacy code and the guide", async () => {
    wrap(<MigrationReviewPage />);
    expect(await screen.findByText("documents for code_review_modernization")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "How a migration gets reviewed" })).toBeTruthy();
    await waitFor(() => expect(state.legacyCalls).toBeGreaterThan(0));
    cleanup();
    wrap(<ModernizationSecurityPage />);
    expect(await screen.findByText("documents for security_modernization")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "How a module gets its security sign-off" })).toBeTruthy();
  });
});

describe("a migration review", () => {
  it("states the recommendation, the head reviewed and the files actually read", () => {
    wrap(<ReviewView review={APPROVE} />);
    const summary = screen.getByRole("region", { name: "Review summary" });
    expect(within(summary).getByText("Approve")).toBeTruthy();
    expect(summary.textContent).toContain("migration record v1");
    expect(within(summary).getByText("1 target · 1 legacy")).toBeTruthy();
    expect(within(summary).getByText("no findings")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Pull request" }).getAttribute("href")).toContain("/pull/1");
  });

  it("answers every contract and trap, and shows the computed API diff with its reason", async () => {
    const user = userEvent.setup();
    wrap(<ReviewView review={APPROVE} />);
    await user.click(screen.getByRole("tab", { name: /Contracts and traps/ }));
    const contracts = screen.getByRole("table", { name: "Frozen contracts" });
    expect(contracts.textContent).toContain("CT-01");
    expect(contracts.textContent).toContain("encoded to bytes for the socket");
    expect(screen.getByRole("table", { name: "Traps" }).textContent).toContain("claims-api/server.py:28");
    await user.click(screen.getByRole("tab", { name: /API diff/ }));
    const ct = screen.getByRole("list", { name: "CT-01 changes" });
    expect(ct.textContent).toContain("encoding");
    expect(ct.textContent).not.toContain("status");
  });

  it("shows a request for changes with findings citing both sides and the contract drift the diff found", async () => {
    const user = userEvent.setup();
    wrap(<ReviewView review={CHANGES} />);
    expect(screen.getByText("Request changes")).toBeTruthy();
    expect(screen.getByText("2 high, 1 medium")).toBeTruthy();
    const findings = screen.getByRole("list", { name: "Findings" });
    expect(within(findings).getAllByRole("listitem")[0]?.textContent).toContain("legacy claims-api/server.py:27");
    await user.click(screen.getByRole("tab", { name: /API diff/ }));
    const ct = screen.getByRole("list", { name: "CT-01 changes" }).textContent ?? "";
    expect(ct).toMatch(/removed.*status.*409/);
    expect(ct).toMatch(/added.*http path.*\/metrics/);
    await user.click(screen.getByRole("tab", { name: /Contracts and traps/ }));
    expect(screen.getByRole("table", { name: "Traps" }).textContent).toContain("not handled");
  });

  it("lists the anti-patterns by origin and what the migration fixed", async () => {
    const user = userEvent.setup();
    wrap(<ReviewView review={APPROVE} />);
    await user.click(screen.getByRole("tab", { name: /Anti-patterns \(1\)/ }));
    expect(screen.getByRole("list", { name: "Anti-patterns" }).textContent).toContain("carried over");
    expect(screen.getByText(/Fixed by the migration: Python 2 only module/)).toBeTruthy();
  });
});

describe("a security report", () => {
  it("states the verdict, the origins and what the migration fixed", async () => {
    const user = userEvent.setup();
    wrap(<SecurityView report={SECURITY} />);
    const summary = screen.getByRole("region", { name: "Security summary" });
    expect(within(summary).getByText("CONDITIONAL")).toBeTruthy();
    expect(summary.textContent).toContain("(legacy scan from the cache)");
    expect(screen.queryByRole("status", { name: "Scanners not run" })).toBeNull();
    const finding = within(screen.getByRole("list", { name: "Security findings" })).getByRole("listitem");
    expect(finding.textContent).toContain("carried over");
    expect(finding.textContent).toContain("by 2027-01-15");
    await user.click(screen.getByRole("tab", { name: /Fixed \(1\)/ }));
    expect(screen.getByRole("list", { name: "Fixed by the migration" }).textContent).toContain("claims-api/server.py:12");
  });

  it("never shows an unscanned module as clean or its counts as 0", async () => {
    const user = userEvent.setup();
    wrap(<SecurityView report={UNSCANNED} />);
    const warn = screen.getByRole("status", { name: "Scanners not run" });
    expect(warn.textContent).toContain("trivy (not installed)");
    expect(warn.textContent).toContain("cannot be PASS");
    expect(screen.getByText("SBOM not generated · dependencies not scanned")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Scans" }));
    expect(screen.getByRole("table", { name: "Scanners" }).textContent).toContain("not scanned (not installed)");
    expect(sbomText({ components: 0, vulnerabilities: 0 })).toBe("0 components · 0 dependency vulnerabilities");
  });
});

function versionView(stage: "code_review_modernization" | "security_modernization") {
  return wrap(
    <VersionView projectId={PROJECT as never} stage={stage} noun={stage === "code_review_modernization" ? "migration review" : "security report"}
      version={1}
      render={(payload, detail) => stage === "code_review_modernization" ? (
        <ReviewView review={MigrationReview.parse(payload)} projectId={PROJECT as never}
          approved={detail.status === "published"} status={detail.status} />
      ) : (
        <SecurityView report={ModernizationSecurity.parse(payload)} projectId={PROJECT as never}
          approved={detail.status === "published"} status={detail.status} />
      )} />,
  );
}

describe("acceptance and the ledger", () => {
  it("offers Approve to another Architect and says what accepting records", async () => {
    versionView("code_review_modernization");
    expect(await screen.findByRole("button", { name: "Approve" })).toBeTruthy();
    const panel = screen.getByRole("region", { name: "Module ledger" });
    expect(panel.textContent).toContain('accepting records "approve" on the migration ledger');
    expect(panel.textContent).toContain("A review of an older migration record is refused");
    await waitFor(() => expect(panel.textContent).toContain("security: not yet"));
  });

  it("tells the producer why they cannot decide it", async () => {
    state.me = { id: "u-arch", email: "arch@example.com" };
    versionView("code_review_modernization");
    expect(await screen.findByText(/You produced this migration review, so you can.t approve it/)).toBeTruthy();
  });

  it("shows the ledger after both sign-offs", async () => {
    state.stage = "security_modernization";
    state.version = { ...state.version, stage: "security_modernization", status: "published", payload: fixtures.security };
    state.ledger = [ledgerRow({ state: "verifying", reviewVerdict: "approve", securityVerdict: "CONDITIONAL" })];
    versionView("security_modernization");
    await waitFor(() => expect(screen.getByRole("region", { name: "Module ledger" }).textContent).toContain("verifying"));
    expect(screen.getByRole("region", { name: "Module ledger" }).textContent).toContain("Both sign-offs are good");
  });

  it("says only what is true in every state", () => {
    expect(verdictLedgerText("review", "request_changes", false, "draft")).toContain("goes back to Migration Development");
    expect(verdictLedgerText("security", "FAIL", false, "draft")).toContain("blocked after three rejections");
    expect(verdictLedgerText("review", "needs_discussion", false, "draft")).toContain("stays in review");
    expect(verdictLedgerText("review", "approve", false, "rejected")).toContain("records nothing on the ledger");
    expect(verdictLedgerText("review", "approve", true, "published", { state: "in_review", reviewVerdict: "approve", securityVerdict: null }))
      .toBe("Accepted and recorded. Waiting for Security.");
    expect(verdictLedgerText("security", "FAIL", true, "published", { state: "migrating", reviewVerdict: null, securityVerdict: "FAIL" }))
      .toContain("back with Migration Development");
    expect(severityCounts([])).toBe("no findings");
  });
});

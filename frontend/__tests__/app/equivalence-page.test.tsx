// @vitest-environment jsdom
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import fixtures from "@/components/modernization/__tests__/fixtures.json";

/**
 * Phase G — the Equivalence Testing page (research §6.5, Baseline mode), rendering what the BACKEND
 * produces (`fixtures.json` → `baseline`: ClaimTrack Lite's baseline built by the record tool's own
 * builder from the MEASURED noise floor; `captures`: the listing in its three states).
 *
 *   - the page: the access gate, the legacy code shown (the sandbox runs it), the Captures dialog;
 *   - sign-off: the producer is told why not; the hand-over names Migration Development; the ledger
 *     panel says what acceptance does in every version state and re-reads the ledger once accepted;
 *   - the view: baselines with counts and fingerprints, scenarios with what varied (masked shapes
 *     only), the noise floor with how each field is handled, the proposals, what was not captured;
 *   - captures: in progress, failed — nothing recorded or accepted — and recorded;
 *   - never a recorded VALUE anywhere: no claimant, amount, id or time from the legacy system.
 */

const PROJECT = "44444444-4444-4444-4444-444444444444";

const state = vi.hoisted(() => ({
  track: "modernization" as string,
  me: { id: "u-qa2", email: "qa2@example.com" },
  version: {} as Record<string, unknown>,
  ledger: [] as { moduleId: string; moduleName: string; legacyPath: string; state: string; wave?: string | null }[],
  legacyCalls: 0,
  captureCalls: 0,
  captures: {} as Record<string, unknown>,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: PROJECT }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));
vi.mock("@/hooks/use-session", () => ({
  useSession: () => ({ user: state.me, permissions: ["artifact:view", "run:create", "artifact:approve_testing_modernization"] }),
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
  getCaptures: async () => {
    state.captureCalls++;
    return state.captures;
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
  getVersionConsumers: async () => ({ stage: "testing_modernization", version: 1, status: "published", contentHash: "h", consumers: [] }),
  getVersionStaleness: async () => ({ stage: "testing_modernization", version: 1, pinned: true, stale: false, inputs: [] }),
  publishStageVersion: vi.fn(),
  rejectStageVersion: vi.fn(),
}));
vi.mock("@/components/app/document-list", () => ({
  DocumentList: ({ stage }: { stage: string }) => <section aria-label="documents">documents for {stage}</section>,
}));
vi.mock("@/components/app/tech-stack-chip", () => ({ TechStackChip: () => <span>tech stack chip</span> }));
vi.mock("@/components/app/model-selector", () => ({ ModelSelector: () => null }));
vi.mock("@/components/app/agent-chat-drawer", () => ({ AgentChatDrawer: () => null }));

import EquivalenceTestingPage from "@/app/(app)/projects/[id]/equivalence-testing/page";
import { baselineLedgerText, CapturesPanel, EquivalenceView } from "@/components/modernization/equivalence-view";
import { VersionView } from "@/components/modernization/version-view";
import { Baseline } from "@/lib/schemas/modernization";

const BASELINE = Baseline.parse(fixtures.baseline);
const LEAKS = [/Test Claimant/, /Zoë/, /\b0\.13\b/, /\b960(\.0)?\b/, /CLM-\d{4}/, /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z/,
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/];

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  state.track = "modernization";
  state.me = { id: "u-qa2", email: "qa2@example.com" };
  state.version = { id: "v1", stage: "testing_modernization", version: 1, status: "draft", contentHash: "h",
    producedBy: "qa@example.com", covers: [], payload: fixtures.baseline };
  state.ledger = [];
  state.legacyCalls = 0;
  state.captureCalls = 0;
  state.captures = fixtures.captures;
});
afterEach(cleanup);

describe("the page", () => {
  it("explains instead of opening a chat on a project of another track", async () => {
    state.track = "greenfield";
    wrap(<EquivalenceTestingPage />);
    expect(await screen.findByText("Equivalence Testing is a Code Modernization agent")).toBeTruthy();
  });

  it("shows the legacy code it runs, the guide, and a Captures dialog listing each state", async () => {
    const user = userEvent.setup();
    wrap(<EquivalenceTestingPage />);
    expect(await screen.findByText("documents for testing_modernization")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "How a baseline gets recorded" })).toBeTruthy();
    await waitFor(() => expect(state.legacyCalls).toBeGreaterThan(0));
    await user.click(screen.getByRole("button", { name: /Captures/ }));
    const running = await screen.findByRole("listitem", { name: "Capture cap-20261201100000-d4e5f6" });
    expect(within(running).getByText("in progress")).toBeTruthy();
    const failed = screen.getByRole("listitem", { name: "Capture cap-20261201093000-0a0b0c" });
    expect(within(failed).getByText("failed — nothing recorded, nothing accepted")).toBeTruthy();
    expect(within(failed).getByText(/did not answer on \/health/)).toBeTruthy();
    const done = screen.getByRole("listitem", { name: "Capture cap-20261201090000-a1b2c3" });
    expect(within(done).getByText("recorded as a baseline")).toBeTruthy();
    expect(within(done).getByText(/3 scenarios, 12 cases · EC-01, EC-02, EC-03/)).toBeTruthy();
  });
});

function versionView() {
  return wrap(
    <VersionView projectId={PROJECT as never} stage="testing_modernization" noun="baseline" version={1}
      render={(payload, detail) => (
        <EquivalenceView baseline={Baseline.parse(payload)} projectId={PROJECT as never}
          approved={detail.status === "published"} status={detail.status} />
      )} />,
  );
}

describe("sign-off, hand-over and the ledger", () => {
  it("offers Accept to another QA and hands over to Migration Development", async () => {
    versionView();
    expect(await screen.findByRole("button", { name: "Approve" })).toBeTruthy();
    expect(await screen.findByText("Ready to hand to Migration Development once approved.")).toBeTruthy();
    const panel = screen.getByRole("region", { name: "Module ledger" });
    expect(panel.textContent).toContain("Accepting this version marks these 2 modules baselined");
    expect(within(panel).getByText("BL-01, BL-02")).toBeTruthy();
  });

  it("tells the producer why they cannot decide it", async () => {
    state.me = { id: "u-qa", email: "qa@example.com" };
    versionView();
    expect(await screen.findByText(/You produced this baseline, so you can.t approve it/)).toBeTruthy();
  });

  it("re-reads the ledger when the version is accepted, so the panel shows the new states", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = (approved: boolean) => (
      <QueryClientProvider client={client}>
        <EquivalenceView baseline={BASELINE} projectId={PROJECT as never} approved={approved}
          status={approved ? "published" : "draft"} />
      </QueryClientProvider>
    );
    const { rerender } = render(view(false));
    const panel = await screen.findByRole("region", { name: "Module ledger" });
    await waitFor(() => expect(within(panel).getAllByText("not on the ledger")).toHaveLength(2));
    state.ledger = [{ moduleId: "M-01", moduleName: "claims-api", legacyPath: "claims-api", state: "baselined", wave: "W1" }];
    rerender(view(true));
    await waitFor(() => expect(within(panel).getByText("Baselined")).toBeTruthy());
  });

  it("says only what is true in every version state", () => {
    expect(baselineLedgerText(false, "rejected", 2)).toBe(
      "This version was rejected, so it cannot be accepted and does not change the ledger.");
    expect(baselineLedgerText(false, "superseded", 2)).toContain("A newer baseline has been accepted since");
    expect(baselineLedgerText(true, "published", 2)).toContain("its modules are baselined");
  });
});

describe("the baseline", () => {
  it("summarises what was recorded, under which conditions", () => {
    wrap(<EquivalenceView baseline={BASELINE} />);
    const summary = screen.getByRole("region", { name: "Baseline summary" });
    const stat = (label: string) => within(summary).getByText(label).nextElementSibling?.textContent;
    expect(stat("Baselines")).toBe("3");
    expect(stat("Criteria recorded")).toBe("3");
    expect(stat("Modules")).toBe("M-01, M-02");
    expect(stat("Fields varying between runs")).toBe("4");
    expect(stat("Rules proposed")).toBe("2");
    expect(stat("Not captured")).toBe("1");
    const capture = screen.getByLabelText("Capture");
    expect(capture.textContent).toContain("cap-20261201090000-a1b2c3");
    expect(capture.textContent).toContain("no internet, synthetic data, stubs for fraudscore");
    expect(screen.getByText("Migration plan v1 (approved)")).toBeTruthy();
  });

  it("lists each baseline with its count and fingerprint", () => {
    wrap(<EquivalenceView baseline={BASELINE} />);
    const [bl1, bl2, bl3, ...rest] = within(screen.getByRole("table", { name: "Baselines" })).getAllByRole("row").slice(1);
    expect(rest).toHaveLength(0);
    expect([bl1, bl2, bl3].map((r) => r?.querySelector("td")?.textContent)).toEqual(["BL-01", "BL-02", "BL-03"]);
    expect(bl2?.textContent).toContain("6 cases");
    expect(bl3?.textContent).toContain("1 runs");
    expect(bl3?.textContent).toContain("BANKPAY_20270131.txt#L1");
    expect(bl1?.querySelector("td[title]")?.getAttribute("title")).toMatch(/^[0-9a-f]{64}$/);
  });

  it("shows what varied in each scenario by its shape only", async () => {
    const user = userEvent.setup();
    wrap(<EquivalenceView baseline={BASELINE} />);
    await user.click(screen.getByRole("tab", { name: /Scenarios/ }));
    const settle = screen.getByRole("listitem", { name: "Scenario settle" });
    expect(settle.textContent).toContain("records EC-02");
    expect(settle.textContent).toContain("requestId differed in 6 cases — <uuid> vs <uuid>");
    expect(settle.textContent).toContain("settledAt differed in 4 cases — <timestamp> vs <timestamp>");
  });

  it("says how every varying field is handled: the criterion's rule or a proposal, never nothing", async () => {
    const user = userEvent.setup();
    wrap(<EquivalenceView baseline={BASELINE} />);
    await user.click(screen.getByRole("tab", { name: /Noise floor/ }));
    const rows = within(screen.getByRole("table", { name: "Noise floor" })).getAllByRole("row").slice(1);
    const text = (ec: string, field: string) =>
      rows.find((r) => r.textContent?.startsWith(ec) && r.textContent.includes(field))?.textContent ?? "";
    expect(text("EC-01", "generatedAt")).toContain("the criterion's rule");
    expect(text("EC-01", "requestId")).toContain("proposed to Migration Strategy");
    expect(text("EC-03", "BANKPAY_20270131.txt#L1")).toContain("the criterion's rule");
    expect(rows.some((r) => r.textContent?.includes("nothing"))).toBe(false);
  });

  it("flags a varying field nobody handled", async () => {
    const user = userEvent.setup();
    const unhandled = Baseline.parse({ ...fixtures.baseline, rule_proposals: [] });
    wrap(<EquivalenceView baseline={unhandled} />);
    await user.click(screen.getByRole("tab", { name: /Noise floor/ }));
    const rows = within(screen.getByRole("table", { name: "Noise floor" })).getAllByRole("row");
    expect(rows.filter((r) => r.textContent?.endsWith("nothing"))).toHaveLength(2);
  });

  it("shows the proposals with their evidence, and what was not captured and why", async () => {
    const user = userEvent.setup();
    wrap(<EquivalenceView baseline={BASELINE} />);
    await user.click(screen.getByRole("tab", { name: /Proposed rules/ }));
    expect(screen.getAllByText("ignore the value, require it present")).toHaveLength(2);
    expect(screen.getByText(/Evidence: differs between two runs of the unchanged legacy system on identical input in 5 of 5/))
      .toBeTruthy();
    await user.click(screen.getByRole("tab", { name: /Not captured/ }));
    expect(screen.getByText(/a load test — measured in Verify mode/)).toBeTruthy();
  });

  it("never shows a value the legacy system produced", async () => {
    const user = userEvent.setup();
    const { container } = wrap(<EquivalenceView baseline={BASELINE} />);
    for (const tab of [/Baselines/, /Scenarios/, /Noise floor/, /Proposed rules/, /Not captured/]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      for (const leak of LEAKS) expect(container.textContent ?? "").not.toMatch(leak);
    }
  });
});

describe("captures", () => {
  it("polls while a capture runs and says when there is none", async () => {
    state.captures = { projectId: PROJECT, captures: [] };
    wrap(<CapturesPanel projectId={PROJECT as never} />);
    expect(await screen.findByText(/No capture yet/)).toBeTruthy();
  });
});

// @vitest-environment jsdom
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import fixtures from "@/components/modernization/__tests__/fixtures.json";

/**
 * Migration Development (Track 3, Phase H) — the page and the module's migration record, rendered from
 * BACKEND-PRODUCED fixtures (`help/Track-3/tools/regen_view_fixtures.py` builds them with the record tool's
 * own builder; the previews are what the real chain test measured).
 *
 *   - the page: the access gate, the legacy code it copies from, the guide, the Workspaces dialog;
 *   - a record ready for review: every legacy file and its target, the traps and where, commits by concern,
 *     the build rounds out of five, tests "not run" (never "passed"), the preview as a HINT;
 *   - a record whose preview differs: the field and its masked shapes, never a value;
 *   - a failed build: what fails, said; a blocked module: the hand-off, no code;
 *   - sign-off and the ledger: what accepting does, never more than the push tool enforces.
 */

const PROJECT = "55555555-5555-5555-5555-555555555555";

const state = vi.hoisted(() => ({
  track: "modernization" as string,
  me: { id: "u-dev2", email: "dev2@example.com" },
  version: {} as Record<string, unknown>,
  ledger: [] as Record<string, unknown>[],
  legacyCalls: 0,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: PROJECT }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));
vi.mock("@/hooks/use-session", () => ({
  useSession: () => ({ user: state.me, permissions: ["artifact:view", "run:create", "artifact:approve_development_modernization"] }),
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
  getMigrationWorkspaces: async () => fixtures.migration_workspaces,
}));
vi.mock("@/lib/api/modernization-programme", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  getLedger: async () => ({ projectId: PROJECT, states: [], modules: state.ledger }),
}));
vi.mock("@/lib/api/artifact-versions", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  listStageVersions: async () => [state.version],
  getStageVersion: async () => state.version,
  getVersionConsumers: async () => ({ stage: "development_modernization", version: 1, status: "published", contentHash: "h", consumers: [] }),
  getVersionStaleness: async () => ({ stage: "development_modernization", version: 1, pinned: true, stale: false, inputs: [] }),
  publishStageVersion: vi.fn(),
  rejectStageVersion: vi.fn(),
}));
vi.mock("@/components/app/document-list", () => ({
  DocumentList: ({ stage }: { stage: string }) => <section aria-label="documents">documents for {stage}</section>,
}));
vi.mock("@/components/app/tech-stack-chip", () => ({ TechStackChip: () => <span>tech stack chip</span> }));
vi.mock("@/components/app/model-selector", () => ({ ModelSelector: () => null }));
vi.mock("@/components/app/agent-chat-drawer", () => ({ AgentChatDrawer: () => null }));

import MigrationDevelopmentPage from "@/app/(app)/projects/[id]/migration-development/page";
import { MigrationView, migrationLedgerText } from "@/components/modernization/migration-view";
import { VersionView } from "@/components/modernization/version-view";
import { Migration } from "@/lib/schemas/modernization";

const READY = Migration.parse(fixtures.migration);
const ROUNDING = Migration.parse(fixtures.migration_rounding);
const FAILED = Migration.parse(fixtures.migration_failed);
const BLOCKED = Migration.parse(fixtures.migration_blocked);
const LEAKS = [/Test Claimant/, /\b0\.1[23]\b/, /CLM-\d{4}/, /ROUND_HALF_UP\)/, /self\.wfile/];

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function ledgerRow(over: Record<string, unknown> = {}) {
  return { moduleId: "M-01", moduleName: "claims-api", legacyPath: "claims-api", state: "migrating", wave: "W1", prUrl: null, ...over };
}

beforeEach(() => {
  state.track = "modernization";
  state.me = { id: "u-dev2", email: "dev2@example.com" };
  state.version = { id: "v1", stage: "development_modernization", version: 1, status: "draft", contentHash: "h",
    producedBy: "dev@example.com", covers: [], payload: fixtures.migration };
  state.ledger = [ledgerRow()];
  state.legacyCalls = 0;
});
afterEach(cleanup);

describe("the page", () => {
  it("explains instead of opening a chat on a project of another track", async () => {
    state.track = "greenfield";
    wrap(<MigrationDevelopmentPage />);
    expect(await screen.findByText("Migration Development is a Code Modernization agent")).toBeTruthy();
  });

  it("shows the legacy code it copies from, the guide, and the Workspaces dialog with build rounds", async () => {
    const user = userEvent.setup();
    wrap(<MigrationDevelopmentPage />);
    expect(await screen.findByText("documents for development_modernization")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "How a module gets migrated" })).toBeTruthy();
    await waitFor(() => expect(state.legacyCalls).toBeGreaterThan(0));
    await user.click(screen.getByRole("button", { name: /Workspaces/ }));
    const ws = await screen.findByRole("listitem", { name: "Workspace M-01" });
    expect(within(ws).getByText("migrate/claims-api")).toBeTruthy();
    expect(within(ws).getByText("#1 red")).toBeTruthy();
    expect(within(ws).getByText("#5 green")).toBeTruthy();
    expect(within(ws).getByText(/Tests not_run · Lint green/)).toBeTruthy();
    expect(within(ws).getByText(/copy, recipe, build, fix/)).toBeTruthy();
  });
});

describe("a record ready for review", () => {
  it("states the outcome, the build out of five, and tests as not run — never passed", () => {
    wrap(<MigrationView migration={READY} />);
    const summary = screen.getByRole("region", { name: "Migration summary" });
    expect(within(summary).getByText("ready for review")).toBeTruthy();
    expect(within(summary).getByText("green · 5/5")).toBeTruthy();
    expect(within(summary).getByText("not run (the module has no tests)")).toBeTruthy();
    expect(summary.textContent).not.toMatch(/tests? passed/i);
    expect(screen.getByLabelText("Branch").textContent).toContain("migrate/claims-api");
  });

  it("calls the preview a hint and names the baseline it was compared with", () => {
    wrap(<MigrationView migration={READY} />);
    const line = screen.getByLabelText("Equivalence preview").textContent ?? "";
    expect(line).toContain("11 case(s) identical to the baseline after normalization");
    expect(line).toContain("A hint against baseline v1");
    expect(line).toContain("verification is the verdict");
  });

  it("accounts for every legacy file, every trap and where, and the commits by concern", async () => {
    const user = userEvent.setup();
    wrap(<MigrationView migration={READY} />);
    const table = screen.getByRole("table", { name: "Legacy to target" });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getByText(/rewritten by hand: legacy rounding kept/)).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Traps (2/2)" }));
    const traps = screen.getByRole("list", { name: "Traps" });
    expect(traps.textContent).toContain("TR-01 — claims-api/server.py payout()");
    expect(traps.textContent).toContain("TR-02 — claims-api/server.py Handler.reply()");
    await user.click(screen.getByRole("tab", { name: "Commits (6)" }));
    const commits = screen.getByRole("list", { name: "Commits" });
    expect(within(commits).getAllByText("fix")).toHaveLength(2);
    expect(within(commits).getByText("copy")).toBeTruthy();
    expect(screen.getByText(/Recipes: lib2to3 CPython 3\.12\.14/)).toBeTruthy();
  });

  it("shows a preview difference by field and shape, never a value", async () => {
    const user = userEvent.setup();
    const { container } = wrap(<MigrationView migration={ROUNDING} />);
    expect(screen.getByLabelText("Equivalence preview").textContent).toContain("A hint, not the verdict");
    await user.click(screen.getByRole("tab", { name: "Preview" }));
    const table = screen.getByRole("table", { name: "Preview" });
    expect(table.textContent).toContain("payout (2) — <number> vs <number>");
    expect(table.textContent).toContain("ignored (the legacy varies in them, or a rule covers them): requestId, settledAt");
    for (const leak of LEAKS) expect(container.textContent).not.toMatch(leak);
  });

  it("marks an unhandled trap", async () => {
    const user = userEvent.setup();
    wrap(<MigrationView migration={{ ...READY, traps_handled: { "TR-01": "x" } }} />);
    await user.click(screen.getByRole("tab", { name: "Traps (1/2)" }));
    expect(screen.getByRole("list", { name: "Traps" }).textContent).toContain("TR-02 — not handled");
  });
});

describe("a failed build and a blocked module", () => {
  it("says what fails and lists the secret to provision as a reference", async () => {
    const user = userEvent.setup();
    wrap(<MigrationView migration={FAILED} />);
    expect(screen.getByText("build failed")).toBeTruthy();
    expect(screen.getByText("red · 5/5")).toBeTruthy();
    expect(screen.getByLabelText("What fails").textContent).toContain("cannot import BaseHTTPServer on this runtime");
    await user.click(screen.getByRole("tab", { name: /Left for a person/ }));
    expect(screen.getByText("kv://claimtrack/fraud-api-key")).toBeTruthy();
  });

  it("shows the hand-off for a blocked module and no code tabs", () => {
    wrap(<MigrationView migration={BLOCKED} />);
    expect(screen.getByText("blocked — a person must redesign it")).toBeTruthy();
    expect(screen.getByLabelText("Hand-off").textContent).toContain("bank's spec v7");
    expect(screen.queryByRole("tab")).toBeNull();
  });

  it("says when no preview ran instead of implying one passed", () => {
    wrap(<MigrationView migration={{ ...READY, preview: null }} />);
    expect(screen.getByLabelText("Equivalence preview").textContent).toContain("not run, so nothing is claimed");
  });
});

function versionView() {
  return wrap(
    <VersionView projectId={PROJECT as never} stage="development_modernization" noun="migration record" version={1}
      render={(payload, detail) => (
        <MigrationView migration={Migration.parse(payload)} projectId={PROJECT as never}
          approved={detail.status === "published"} status={detail.status} />
      )} />,
  );
}

describe("sign-off and the ledger", () => {
  it("offers Approve to another Developer and hands over to Migration Review and Security", async () => {
    versionView();
    expect(await screen.findByRole("button", { name: "Approve" })).toBeTruthy();
    expect(await screen.findByText("Ready to hand to Migration Review and Security once approved.")).toBeTruthy();
    const panel = screen.getByRole("region", { name: "Module ledger" });
    expect(panel.textContent).toContain("lets the branch be pushed and the pull request opened — exactly this commit, never forced");
  });

  it("tells the producer why they cannot decide it", async () => {
    state.me = { id: "u-dev", email: "dev@example.com" };
    versionView();
    expect(await screen.findByText(/You produced this migration record, so you can.t approve it/)).toBeTruthy();
  });

  it("links the pull request once the ledger has one", async () => {
    state.version = { ...state.version, status: "published" };
    state.ledger = [ledgerRow({ state: "in_review", prUrl: "https://github.com/claimtrack/claimtrack-lite-target/pull/1" })];
    versionView();
    const link = await screen.findByRole("link", { name: "Pull request" });
    expect(link.getAttribute("href")).toBe("https://github.com/claimtrack/claimtrack-lite-target/pull/1");
    expect(screen.getByRole("region", { name: "Module ledger" }).textContent).toContain("the pull request is in review");
  });

  it("says only what is true in every state", () => {
    expect(migrationLedgerText(READY, false, "draft")).toContain("lets the branch be pushed");
    expect(migrationLedgerText(FAILED, false, "draft")).toBe("This record is not ready for review, so it is never pushed.");
    expect(migrationLedgerText(READY, false, "rejected")).toContain("nothing is pushed from it");
    expect(migrationLedgerText(READY, true, "published", "migrating")).toContain("after confirming it");
    expect(migrationLedgerText(READY, true, "published", "in_review")).toContain("in review");
    expect(migrationLedgerText(BLOCKED, true, "published", "blocked")).toContain("blocked on the migration ledger");
  });
});

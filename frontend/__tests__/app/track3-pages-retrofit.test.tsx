// @vitest-environment jsdom
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * Phase B retrofit of Track 3's two built pages onto the platform's document and approval
 * system (help/Track-3/build-log.md):
 *
 *   - the access gate: a project on another track gets an explanation, not a chat (R43);
 *   - the Documents panel for the page's own stage (upload, raise, approve legacy docs);
 *   - the tech-stack chip on the agent that recommends a stack;
 *   - a version's producer is told WHY they cannot approve it, before any click (R14);
 *   - a published version shows which agents read it ("Read by").
 *
 * The page and VersionView run for real; the network edges (API modules, the chat hook,
 * the session) and the heavy shared panels are replaced by markers.
 */

const PROJECT = "11111111-1111-1111-1111-111111111111";

const state = vi.hoisted(() => ({
  track: "modernization" as string,
  me: { id: "0b1c0000-0000-0000-0000-00000000ba01", email: "ba@example.com" },
  version: {
    id: "v1", stage: "requirements_modernization", version: 1, status: "draft" as string,
    // THE REAL SHAPE: the API relabels producedBy from the user id to the user's EMAIL.
    contentHash: "h", producedBy: "ba@example.com", covers: [], payload: { system_name: "ClaimTrack" },
  } as Record<string, unknown>,
  consumers: [] as { consumerStage: string; consumerRunId: string | null; consumedBy: string | null;
    consumedAt: string | null; viaGrant: boolean }[],
  documentStages: [] as string[],
  consumerCalls: 0,
  publishCalls: [] as (string | undefined)[],
  restoreCalls: [] as string[],
  stale: false,
  stalenessCalls: 0,
  staleRejected: false,
  packetProblems: [] as string[],
  packetFails: false,
  publishRefusesWithoutReason: false,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: PROJECT }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));
vi.mock("@/hooks/use-session", () => ({
  useSession: () => ({ user: state.me,
    // What a BA holds: may approve Migration Intent — and nothing wildcarded.
    permissions: ["artifact:view", "run:create", "artifact:approve_requirements_modernization"] }),
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
  getProject: async () => ({ id: PROJECT, name: "ClaimTrack Modernization", track: state.track }),
}));
// The Programme strip in the page header: no modules yet, so it stays silent.
vi.mock("@/lib/api/modernization", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  getVersionPacket: async (_p: string, stage: string, version: number) => {
    if (state.packetFails) throw new Error("backend unavailable");
    return {
    stage, version, ok: state.packetProblems.length === 0, problems: state.packetProblems,
    packet: state.packetProblems.length === 0 ? { payload: {} } : null,
  };
  },
}));
vi.mock("@/lib/api/modernization-programme", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  getLedger: async () => ({ projectId: PROJECT, states: [], modules: [] }),
}));
vi.mock("@/lib/api/artifact-versions", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  listStageVersions: async () => [state.version],
  getStageVersion: async () => state.version,
  getVersionConsumers: async () => (state.consumerCalls++, {
    stage: "requirements_modernization", version: 1, status: "published", contentHash: "h",
    consumers: state.consumers,
  }),
  publishStageVersion: async (_p: string, _s: string, _v: number, why?: string) => {
    state.publishCalls.push(why);
    if (state.publishRefusesWithoutReason && !why) {
      throw new Error("approving as Project Admin fallback needs a reason — it is recorded and listed in the Cutover Pack");
    }
    return { ...state.version, status: "published", approvedAs: why ? "fallback:project_admin" : "owner" };
  },
  rejectStageVersion: vi.fn(),
  restoreStageVersion: async (_p: string, _s: string, _v: number, reason: string) => {
    state.restoreCalls.push(reason);
    return { stage: "requirements_modernization", version: 3, status: "draft", restoredFrom: 1, note: "" };
  },
  getVersionStaleness: async () => (state.stalenessCalls++, {
    stage: "requirements_modernization", version: 1, pinned: true, stale: state.stale,
    inputs: !state.stale ? [] : state.staleRejected
      ? [{ stage: "discovery", artifact: "discovery_artifacts", pinned: 1, latest: null, rejected: true }]
      : [{ stage: "discovery", artifact: "discovery_artifacts", pinned: 1, latest: 2 }],
  }),
  compareStageVersions: async () => ({
    stage: "requirements_modernization", from: 1, to: 2,
    differences: [{ path: "goal", change: "changed", before: "one", after: "two" }],
  }),
}));
vi.mock("@/components/modernization/legacy-code-control", () => ({
  useLegacyCode: () => ({ data: undefined }),
  useAnnouncePullOutcome: () => undefined,
  LegacyCodeStatus: () => null,
  PullLegacyCodeDialog: () => null,
}));
vi.mock("@/components/app/document-list", () => ({
  DocumentList: ({ stage }: { stage: string }) => {
    state.documentStages.push(stage);
    return <section aria-label="documents">documents for {stage}</section>;
  },
}));
vi.mock("@/components/app/tech-stack-chip", () => ({
  TechStackChip: () => <span>tech stack chip</span>,
}));
vi.mock("@/components/app/model-selector", () => ({ ModelSelector: () => null }));
vi.mock("@/components/app/agent-chat-drawer", () => ({ AgentChatDrawer: () => null }));

import MigrationIntentPage from "@/app/(app)/projects/[id]/requirements-modernization/page";
import DiscoveryPage from "@/app/(app)/projects/[id]/discovery/page";
import { VersionView } from "@/components/modernization/version-view";
import { producedByMe } from "@/lib/api/artifact-versions";

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  state.track = "modernization";
  state.me = { id: "0b1c0000-0000-0000-0000-00000000ba01", email: "ba@example.com" };
  state.version = { ...state.version, status: "draft", producedBy: "ba@example.com" };
  state.consumers = [];
  state.documentStages = [];
  state.consumerCalls = 0;
  state.publishCalls = [];
  state.restoreCalls = [];
  state.stale = false;
  state.stalenessCalls = 0;
  state.staleRejected = false;
  state.packetProblems = [];
  state.packetFails = false;
  state.publishRefusesWithoutReason = false;
});
afterEach(cleanup);

describe("the access gate (R43)", () => {
  it("explains, instead of opening a chat, on a project of another track", async () => {
    state.track = "greenfield";
    wrap(<MigrationIntentPage />);
    expect(await screen.findByText("Migration Intent is a Code Modernization agent")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Run Migration Intent/i })).toBeNull();
    expect(state.documentStages).toEqual([]);
  });
});

describe("the shared frame on both pages", () => {
  it("Migration Intent shows its documents and the project's approved tech stack", async () => {
    wrap(<MigrationIntentPage />);
    expect(await screen.findByText("documents for requirements_modernization")).toBeTruthy();
    expect(screen.getByText("tech stack chip")).toBeTruthy();
  });

  it("Dependency and Risk shows its own stage's documents, and no stack chip", async () => {
    wrap(<DiscoveryPage />);
    expect(await screen.findByText("documents for discovery")).toBeTruthy();
    expect(screen.queryByText("tech stack chip")).toBeNull();
  });
});

function view() {
  return wrap(
    <VersionView projectId={PROJECT as never} stage="requirements_modernization" noun="brief" version={1}
      render={() => <div>brief body</div>} />,
  );
}

describe("sign-off on a version (R14)", () => {
  it("tells the producer why they cannot decide it, and offers neither Approve nor Reject", async () => {
    // The backend refuses a producer BOTH ways (reject_version: "cannot also decide it"),
    // so a Reject button here would be a promise the backend breaks.
    view();
    expect(await screen.findByText(/You produced this brief, so you can.t approve it/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("offers Approve to someone who did not produce it", async () => {
    state.me = { id: "0b1c0000-0000-0000-0000-00000000ba02", email: "ba2@example.com" };
    view();
    expect(await screen.findByRole("button", { name: "Approve" })).toBeTruthy();
    expect(screen.queryByText(/You produced this brief/)).toBeNull();
  });
});

describe("Read by (the consumption evidence)", () => {
  it("names the agents that built on a published version", async () => {
    state.version = { ...state.version, status: "published", producedBy: "ba@example.com" };
    state.consumers = [{ consumerStage: "discovery", consumerRunId: "r1", consumedBy: "u-ba-2",
      consumedAt: "2026-09-28T10:00:00Z", viaGrant: false }];
    view();
    await waitFor(() => expect(screen.getByRole("region", { name: "Agents that read this brief" })).toBeTruthy());
    expect(screen.getByText("Dependency and Risk")).toBeTruthy();
  });

  it("says plainly when nothing has built on it yet", async () => {
    state.version = { ...state.version, status: "published" };
    view();
    expect(await screen.findByText("No agent has built on this brief yet.")).toBeTruthy();
  });

  it("is not shown on a draft, which no agent may read as approved work", async () => {
    view();
    await screen.findByText("brief body");
    // Not even asked for: the query would fire on mount, so "never called" is exact where
    // "not on screen yet" would race the fetch.
    expect(state.consumerCalls).toBe(0);
    expect(screen.queryByText("Read by")).toBeNull();
  });
});

describe("producedByMe", () => {
  const me = { id: "0b1c0000-0000-0000-0000-00000000ba01", email: "BA@Example.com" };
  it("matches the relabelled email, case-insensitively", () => {
    expect(producedByMe("ba@example.com", me)).toBe(true);
    // …on either side: the stored address and the session's may differ in case.
    expect(producedByMe(" BA@EXAMPLE.COM ", { id: null, email: "ba@example.com" })).toBe(true);
  });
  it("matches the raw id when the user could not be relabelled", () => {
    expect(producedByMe("0b1c0000-0000-0000-0000-00000000ba01", me)).toBe(true);
  });
  it("matches nobody else, and nothing without a user", () => {
    expect(producedByMe("ba2@example.com", me)).toBe(false);
    expect(producedByMe("ba@example.com", null)).toBe(false);
    expect(producedByMe(null, me)).toBe(false);
  });
});

function viewAt(version: number, latest: number) {
  return wrap(
    <VersionView projectId={PROJECT as never} stage="requirements_modernization" noun="brief" version={version}
      latestVersion={latest} render={() => <div>brief body</div>} />,
  );
}

describe("the Project Admin fallback (Phase C)", () => {
  it("asks a Project Admin for the reason when the backend requires one, then approves with it", async () => {
    const user = userEvent.setup();
    state.me = { id: "0b1c0000-0000-0000-0000-0000000000a1", email: "pa@example.com" };
    state.publishRefusesWithoutReason = true;
    view();
    await user.click(await screen.findByRole("button", { name: "Approve" }));
    const reason = await screen.findByRole("textbox", { name: "Fallback reason" });
    await user.type(reason, "BA on leave");
    await user.click(screen.getByRole("button", { name: "Approve as fallback" }));
    await waitFor(() => expect(state.publishCalls).toEqual([undefined, "BA on leave"]));
  });

  it("an owner's approval never opens the reason dialog", async () => {
    const user = userEvent.setup();
    state.me = { id: "0b1c0000-0000-0000-0000-00000000ba02", email: "ba2@example.com" };
    view();
    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(state.publishCalls).toEqual([undefined]));
    expect(screen.queryByRole("textbox", { name: "Fallback reason" })).toBeNull();
  });

  it("labels a fallback approval on the version", async () => {
    state.version = { ...state.version, status: "published", approvedAs: "fallback:project_admin",
      fallbackReason: "BA on leave" };
    view();
    expect(await screen.findByText("Approved by Project Admin (fallback)")).toBeTruthy();
    expect(screen.getByText("Fallback reason: BA on leave")).toBeTruthy();
  });
});

describe("restore, compare and staleness (Phase C)", () => {
  it("offers Restore on an older version, and sends the reason", async () => {
    const user = userEvent.setup();
    viewAt(1, 2);
    await user.click(await screen.findByRole("button", { name: "Restore this version" }));
    await user.type(screen.getByRole("textbox", { name: "Restore reason" }), "v2 widened the scope");
    await user.click(screen.getByRole("button", { name: "Restore as a new version" }));
    await waitFor(() => expect(state.restoreCalls).toEqual(["v2 widened the scope"]));
  });

  it("does not offer Restore on the newest version", async () => {
    viewAt(2, 2);
    await screen.findByText("brief body");
    expect(screen.queryByRole("button", { name: "Restore this version" })).toBeNull();
  });

  it("says when a version is out of date, and why", async () => {
    state.stale = true;
    viewAt(1, 1);
    expect(await screen.findByText("This brief is out of date.")).toBeTruthy();
    expect(screen.getByText(/built from Dependency and Risk v1; v2\s+has since been approved/)).toBeTruthy();
  });

  it("says when an input it was built on was later rejected", async () => {
    state.stale = true;
    state.staleRejected = true;
    viewAt(1, 1);
    expect(await screen.findByText("This brief is out of date.")).toBeTruthy();
    const line = screen.getByText(/built from Dependency and Risk v1/);
    expect(line.textContent).toMatch(/which was later rejected/);
    expect(line.textContent).not.toMatch(/has since been approved/);
  });

  it("stays quiet when nothing is out of date", async () => {
    viewAt(1, 1);
    await screen.findByText("brief body");
    // Wait for the answer itself — asserting before it arrives would pass for any code.
    await waitFor(() => expect(state.stalenessCalls).toBeGreaterThan(0));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("This brief is out of date.")).toBeNull();
  });

  it("shows what changed from the previous version", async () => {
    const user = userEvent.setup();
    viewAt(2, 2);
    await user.click(await screen.findByRole("button", { name: "Compare with v1" }));
    const changes = await screen.findByRole("region", { name: "Changes from v1 to v2" });
    expect(changes.textContent).toContain("one → two");
  });
});

describe("the hand-over to Target Architecture (Phase D)", () => {
  it("says a draft is ready once approved, and an approved version is ready", async () => {
    const { unmount } = viewAt(1, 1);
    expect((await screen.findByLabelText("Hand-over")).textContent).toBe(
      "Ready to hand to Target Architecture once approved.");
    unmount();
    state.version = { ...state.version, status: "published" };
    viewAt(1, 1);
    expect((await screen.findByLabelText("Hand-over")).textContent).toBe("Ready to hand to Target Architecture.");
  });

  it("says nothing about a rejected version, which is never handed over", async () => {
    state.version = { ...state.version, status: "rejected" };
    viewAt(1, 1);
    await screen.findByText("brief body");
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByLabelText("Hand-over")).toBeNull();
  });

  it("lists why a version cannot be handed over yet, in plain words, capped", async () => {
    // The backend's own wording (handover/emit.py `_plain`).
    state.packetProblems = [
      "Success measure 1 has no kind (equivalence, performance, security, schedule or cost).",
      ...Array.from({ length: 7 }, (_, i) => `Problem ${i + 2}.`),
    ];
    viewAt(1, 1);
    const box = await screen.findByLabelText("Hand-over");
    expect(box.textContent).toContain("not yet ready to hand to Target Architecture");
    expect(box.textContent).toContain("Success measure 1 has no kind");
    expect(box.querySelectorAll("li")).toHaveLength(6);
    expect(box.textContent).toContain("…and 2 more.");
  });

  it("says when the check itself failed, rather than nothing", async () => {
    state.packetFails = true;
    viewAt(1, 1);
    expect((await screen.findByLabelText("Hand-over")).textContent).toContain("Could not check");
  });
});

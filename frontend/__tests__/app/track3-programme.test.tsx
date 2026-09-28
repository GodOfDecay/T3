// @vitest-environment jsdom
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * Track 3 Phase C item 7: the Programme board (`/projects/[id]/modernization`), the status
 * strip on every Track 3 agent page, and the Code Modernization settings card.
 *
 * The components run for real; `lib/api/modernization-programme` and `getProject` are the
 * network edge and are replaced.
 */

const PROJECT = "22222222-2222-2222-2222-222222222222";
const STATES = ["assessed", "designed", "sequenced", "baselined", "migrating", "in_review", "verifying",
  "verified", "cut_over", "retired", "blocked"];

const mod = (moduleId: string, st: string, extra: Record<string, unknown> = {}) => ({
  moduleId, moduleName: moduleId, legacyPath: `src/${moduleId}`, state: st, ...extra,
});

const state = vi.hoisted(() => ({
  track: "modernization" as string,
  modules: [] as Record<string, unknown>[],
  legacy: null as Record<string, unknown> | null,
  target: null as Record<string, unknown> | null,
  settings: { fallbackMode: "always", policy: "standard", warnings: [] as string[] },
  repoCalls: [] as [string, string, string][],
  settingsCalls: [] as [string, string][],
  ledgerCalls: 0,
  repoRefusal: null as string | null,
  reposFail: false,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: PROJECT }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));
vi.mock("@/lib/api/projects", () => ({
  getProject: async () => ({ id: PROJECT, name: "ClaimTrack Modernization", track: state.track }),
}));
vi.mock("@/lib/api/modernization-programme", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  getLedger: async () => (state.ledgerCalls++, { projectId: PROJECT, states: STATES, modules: state.modules }),
  getRepositories: async () => {
    if (state.reposFail) throw new Error("backend unavailable");
    return { projectId: PROJECT, legacy: state.legacy, target: state.target };
  },
  setRepository: async (_p: string, role: string, url: string, branch: string) => {
    state.repoCalls.push([role, url, branch]);
    if (state.repoRefusal) throw new Error(state.repoRefusal);
    return { role, kind: "github", url, branch, setBy: "u-pa", updatedAt: null };
  },
  getApprovalSettings: async () => ({ projectId: PROJECT, ...state.settings }),
  setApprovalSettings: async (_p: string, fallbackMode: string, policy: string) => {
    state.settingsCalls.push([fallbackMode, policy]);
    return { projectId: PROJECT, fallbackMode, policy, warnings: [] };
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ProgrammePage from "@/app/(app)/projects/[id]/modernization/page";
import { ModernizationSettingsCard } from "@/components/modernization/modernization-settings-card";
import { ProgrammeStatusStrip } from "@/components/modernization/programme-status-strip";
import { toast } from "sonner";

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  state.track = "modernization";
  state.modules = [];
  state.legacy = null;
  state.target = null;
  state.settings = { fallbackMode: "always", policy: "standard", warnings: [] };
  state.repoCalls = [];
  state.settingsCalls = [];
  state.ledgerCalls = 0;
  state.repoRefusal = null;
  state.reposFail = false;
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("the Programme board", () => {
  it("counts modules per state and lists each module with its state", async () => {
    state.modules = [mod("M-01", "designed"), mod("M-02", "designed"), mod("M-03", "migrating", { wave: "W1" })];
    wrap(<ProgrammePage />);
    expect(await screen.findByLabelText("Designed: 2")).toBeTruthy();
    expect(screen.getByLabelText("Migrating: 1")).toBeTruthy();
    expect(screen.getByLabelText("Verified: 0")).toBeTruthy();
    const table = screen.getByRole("table", { name: "Modules" });
    expect(table.textContent).toContain("M-03");
    expect(table.textContent).toContain("W1");
  });

  it("says why a module is blocked", async () => {
    state.modules = [mod("M-04", "blocked", { blockedFrom: "in_review", blockedReason: "three review rejections" })];
    wrap(<ProgrammePage />);
    const blocked = await screen.findByRole("region", { name: "Blocked modules" });
    expect(blocked.textContent).toContain("M-04");
    expect(blocked.textContent).toContain("In review");
    expect(blocked.textContent).toContain("three review rejections");
  });

  it("explains an empty ledger rather than drawing an empty board", async () => {
    wrap(<ProgrammePage />);
    expect(await screen.findByText("No modules yet")).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Modules" })).toBeNull();
  });

  it("shows the repositories and the staffing warnings", async () => {
    state.legacy = { role: "legacy", kind: "github", url: "https://github.com/c/legacy", branch: "main" };
    state.settings.warnings = ["This project has 1 Project Admin(s)."];
    wrap(<ProgrammePage />);
    expect(await screen.findByText("https://github.com/c/legacy")).toBeTruthy();
    expect(screen.getByText("Not set")).toBeTruthy();
    expect((await screen.findByRole("list", { name: "Staffing warnings" })).textContent).toContain("1 Project Admin");
  });

  it("says the repositories failed to load rather than showing them as not set", async () => {
    state.reposFail = true;
    wrap(<ProgrammePage />);
    expect(await screen.findByText(/The repositories could not be loaded: backend unavailable/)).toBeTruthy();
    expect(screen.queryByText("Not set")).toBeNull();
  });

  it("does not exist on a project of another track, and asks nothing of the backend", async () => {
    state.track = "greenfield";
    wrap(<ProgrammePage />);
    expect(await screen.findByText("No Programme on this project")).toBeTruthy();
    expect(state.ledgerCalls).toBe(0);
  });
});

describe("the programme status strip", () => {
  it("summarises the states that have modules, with blocked called out", async () => {
    state.modules = [mod("M-01", "designed"), mod("M-02", "blocked", { blockedFrom: "migrating" })];
    wrap(<ProgrammeStatusStrip projectId={PROJECT as never} />);
    const strip = await screen.findByRole("navigation", { name: "Programme status" });
    expect(strip.textContent).toContain("2 modules");
    expect(strip.textContent).toContain("Designed 1");
    expect(strip.textContent).toContain("1 blocked");
    expect(strip.textContent).not.toContain("Verified");
    expect(screen.getByRole("link", { name: "Programme" }).getAttribute("href")).toBe(
      `/projects/${PROJECT}/modernization`);
  });

  it("is silent before any module exists", async () => {
    wrap(<ProgrammeStatusStrip projectId={PROJECT as never} />);
    await waitFor(() => expect(state.ledgerCalls).toBeGreaterThan(0));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("navigation", { name: "Programme status" })).toBeNull();
  });
});

describe("the Code Modernization settings card", () => {
  it("names the legacy repository", async () => {
    const user = userEvent.setup();
    wrap(<ModernizationSettingsCard projectId={PROJECT as never} canEdit />);
    const form = await screen.findByRole("form", { name: "Legacy repository" });
    const url = form.querySelector("input#repo-legacy-url") as HTMLInputElement;
    await user.type(url, "https://github.com/c/legacy");
    await user.type(form.querySelector("input#repo-legacy-branch") as HTMLInputElement, "main");
    await user.click(form.querySelector("button[type=submit]") as HTMLButtonElement);
    await waitFor(() => expect(state.repoCalls).toEqual([["legacy", "https://github.com/c/legacy", "main"]]));
  });

  it("shows the backend's refusal when the target is the legacy repository", async () => {
    const user = userEvent.setup();
    state.repoRefusal = "the target repository cannot be the legacy repository";
    wrap(<ModernizationSettingsCard projectId={PROJECT as never} canEdit />);
    const form = await screen.findByRole("form", { name: "Target repository" });
    await user.type(form.querySelector("input#repo-target-url") as HTMLInputElement, "https://github.com/c/legacy");
    await user.click(form.querySelector("button[type=submit]") as HTMLButtonElement);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("the target repository cannot be the legacy repository"));
  });

  it("changes the fallback mode and policy", async () => {
    const user = userEvent.setup();
    wrap(<ModernizationSettingsCard projectId={PROJECT as never} canEdit />);
    await user.selectOptions(await screen.findByLabelText("When a Project Admin may stand in"), "after_sla");
    await user.selectOptions(screen.getByLabelText("Policy"), "strict");
    await user.click(screen.getByRole("button", { name: "Save approval settings" }));
    await waitFor(() => expect(state.settingsCalls).toEqual([["after_sla", "strict"]]));
  });

  it("offers no Save to someone who cannot edit", async () => {
    state.legacy = { role: "legacy", kind: "github", url: "https://github.com/c/legacy", branch: "main" };
    wrap(<ModernizationSettingsCard projectId={PROJECT as never} canEdit={false} />);
    await screen.findByRole("form", { name: "Legacy repository" });
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save approval settings" })).toBeNull();
    expect((screen.getByLabelText("Policy") as HTMLSelectElement).disabled).toBe(true);
  });
});

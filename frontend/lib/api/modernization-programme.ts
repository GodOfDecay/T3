/**
 * The Programme view of a Code Modernization project (Track 3): the module ledger, the
 * project's legacy and target repositories, and how its sign-offs fall back to a Project
 * Admin. Backend: `shared/routers/modernization_programme.py`.
 *
 * Every route 404s on a project that is not on the Code Modernization track — this view
 * does not exist elsewhere, and callers should only ask for it on a Track 3 project.
 */

import { z } from "zod";

import type { ProjectId } from "@/lib/schemas";

import { api } from "./client";

export const LedgerModule = z.object({
  moduleId: z.string(),
  moduleName: z.string(),
  legacyPath: z.string(),
  tier: z.string().nullable().optional(),
  riskScore: z.number().nullable().optional(),
  wave: z.string().nullable().optional(),
  state: z.string(),
  blockedFrom: z.string().nullable().optional(),
  blockedReason: z.string().nullable().optional(),
  rejectionCount: z.number().optional(),
  prUrl: z.string().nullable().optional(),
  stateChangedAt: z.string().nullable().optional(),
});
export type LedgerModule = z.infer<typeof LedgerModule>;

export const Ledger = z.object({
  projectId: z.string(),
  /** Column order for the board — fixed, so an empty ledger still says what the states are. */
  states: z.array(z.string()),
  modules: z.array(LedgerModule),
});
export type Ledger = z.infer<typeof Ledger>;

export const RepositoryRole = z.enum(["legacy", "target"]);
export type RepositoryRole = z.infer<typeof RepositoryRole>;

export const Repository = z.object({
  role: RepositoryRole,
  kind: z.string(),
  url: z.string(),
  branch: z.string(),
  setBy: z.string().nullable().optional(),
  updatedAt: z.string().nullable().optional(),
});
export type Repository = z.infer<typeof Repository>;

export const Repositories = z.object({
  projectId: z.string(),
  legacy: Repository.nullable(),
  target: Repository.nullable(),
});
export type Repositories = z.infer<typeof Repositories>;

export const FallbackMode = z.enum(["always", "after_sla"]);
export const ApprovalPolicy = z.enum(["standard", "pilot", "strict"]);

export const ApprovalSettings = z.object({
  projectId: z.string(),
  fallbackMode: FallbackMode,
  policy: ApprovalPolicy,
  /** Staffing that could deadlock a gate — warnings, not refusals. */
  warnings: z.array(z.string()),
});
export type ApprovalSettings = z.infer<typeof ApprovalSettings>;

const base = (projectId: ProjectId) => `/modernization-programme/${encodeURIComponent(projectId)}`;

export const getLedger = (projectId: ProjectId) => api(`${base(projectId)}/ledger`, { schema: Ledger });

export const getRepositories = (projectId: ProjectId) =>
  api(`${base(projectId)}/repositories`, { schema: Repositories });

export const setRepository = (projectId: ProjectId, role: RepositoryRole, url: string, branch: string) =>
  api(`${base(projectId)}/repositories/${role}`, { method: "PUT", body: { url, branch }, schema: Repository });

export const getApprovalSettings = (projectId: ProjectId) =>
  api(`${base(projectId)}/approval-settings`, { schema: ApprovalSettings });

export const setApprovalSettings = (
  projectId: ProjectId,
  fallbackMode: z.infer<typeof FallbackMode>,
  policy: z.infer<typeof ApprovalPolicy>,
) => api(`${base(projectId)}/approval-settings`, { method: "PUT", body: { fallbackMode, policy }, schema: ApprovalSettings });

/** Ledger states in words, for the board's column headers. */
export const STATE_LABEL: Record<string, string> = {
  assessed: "Assessed",
  designed: "Designed",
  sequenced: "Sequenced",
  baselined: "Baselined",
  migrating: "Migrating",
  in_review: "In review",
  verifying: "Verifying",
  verified: "Verified",
  cut_over: "Cut over",
  retired: "Retired",
  blocked: "Blocked",
};

export const stateLabel = (s: string) => STATE_LABEL[s] ?? s.replace(/_/g, " ");

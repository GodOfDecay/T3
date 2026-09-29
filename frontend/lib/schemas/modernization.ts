import { z } from "zod";

/**
 * Track 3 (Code Modernization) — the shapes its first two agents record.
 *
 * Mirrors `backend/shared/models/artifacts.py` (MigrationIntentArtifact,
 * DiscoveryArtifact) and `discovery_agent/analysis/assessment.py`. Tolerant on
 * purpose — every collection defaults to empty — because these are read back from a
 * JSONB column a newer agent may have written with an extra field or an older one
 * without a newer field; a strict parse would blank the whole page over one of them.
 */

const strings = z.array(z.string()).default([]);
const text = z.string().default("");

/* Version 2 of the brief (structured sections). Every part defaults to empty, so a
   version-1 brief parses and renders through the same view. */
const BriefDriver = z.object({ category: z.string().default("other"), title: text, detail: text });
const BriefLayer = z.object({
  layer: text, current: text, current_status: text, target: text, change_type: text, modules: strings,
});
const BriefRecommendation = z.object({
  summary: text,
  recommended_by: z.string().default("agent"),
  rationale: strings,
  alternatives: z.array(z.object({ option: text, why_not: text })).default([]),
});
const BriefModuleChange = z.object({
  module: text, path: text, current: text, current_status: text, target: text,
  change_type: text, changes: strings, effort: text,
});
const BriefTradeOff = z.object({ decision: text, gain: text, cost: text });
const BriefMilestone = z.object({ date: text, label: text, kind: z.string().default("other") });
/** What a success measure is about (research §6.1): Migration Strategy turns the
 *  `equivalence` and `performance` ones into equivalence criteria. Null on a brief recorded
 *  before `kind` existed — shown as "not yet classified", never guessed. */
export const MEASURE_KINDS = ["equivalence", "performance", "security", "schedule", "cost"] as const;
export type MeasureKind = (typeof MEASURE_KINDS)[number];
const BriefMeasure = z.object({
  metric: text, current: text, target: text,
  kind: z.enum(MEASURE_KINDS).nullable().catch(null).default(null),
});

export const MigrationIntentBrief = z.object({
  system_name: z.string().default(""),
  goal: text,
  business_drivers: strings,
  drivers: z.array(BriefDriver).default([]),
  layers: z.array(BriefLayer).default([]),
  recommendation: BriefRecommendation.nullable().default(null),
  module_changes: z.array(BriefModuleChange).default([]),
  trade_offs: z.array(BriefTradeOff).default([]),
  deadline: text,
  budget: text,
  milestones: z.array(BriefMilestone).default([]),
  success_measures: z.array(BriefMeasure).default([]),
  current_state: z.object({ stack: z.string().default(""), description: z.string().default("") })
    .default({ stack: "", description: "" }),
  target_state: z.object({ stack: z.string().default(""), description: z.string().default("") })
    .default({ stack: "", description: "" }),
  in_scope: strings,
  out_of_scope: strings,
  constraints: strings,
  /** Interfaces, files and reports the user said must not change — in THEIR words (the
   *  record tool checks them against the conversation). Target Architecture turns each
   *  into a contract (CT-xx). */
  must_not_change: strings,
  /** False when the wording could NOT be checked against the conversation — then the page
   *  must not call it the user's own words. Null on older briefs. */
  must_not_change_verified: z.boolean().nullable().default(null),
  success_criteria: strings,
  stakeholders: z.array(z.object({ name: z.string(), role: z.string().default("") })).default([]),
  assumptions: strings,
  risks: strings,
  open_questions: strings,
  legacy_repository: z
    .object({
      provider: z.string().default(""),
      project: z.string().default(""),
      name: z.string().default(""),
      url: z.string().default(""),
    })
    .nullable()
    .default(null),
  recorded_at: z.string().nullable().default(null),
});
export type MigrationIntentBrief = z.infer<typeof MigrationIntentBrief>;
export type BriefDriver = z.infer<typeof BriefDriver>;
export type BriefLayer = z.infer<typeof BriefLayer>;
export type BriefModuleChange = z.infer<typeof BriefModuleChange>;
export type BriefMilestone = z.infer<typeof BriefMilestone>;

export const MigrationTier = z.enum(["mechanical", "llm_assisted", "manual"]);
export type MigrationTier = z.infer<typeof MigrationTier>;

export const RuntimeStatus = z.enum(["eol", "approaching", "legacy", "supported", "unknown"]);
export type RuntimeStatus = z.infer<typeof RuntimeStatus>;

const Vulnerability = z.object({
  cve: z.string().nullable().optional(),
  severity: z.string().nullable().optional(),
  package: z.string().nullable().optional(),
  installed_version: z.string().nullable().optional(),
  fixed_version: z.string().nullable().optional(),
  title: z.string().nullable().optional(),
});

export const AssessedDependency = z.object({
  name: z.string(),
  version: z.string().default(""),
  kind: z.string().default("package"),
  status: z.string().default("ok"),
  note: z.string().default(""),
  vulnerabilities: z.array(Vulnerability).default([]),
});
export type AssessedDependency = z.infer<typeof AssessedDependency>;

export const RiskFactor = z.object({
  factor: z.string(),
  points: z.number(),
  detail: z.string().default(""),
  /** False when the input was never measured (no vulnerability scan ran): the factor
   *  contributes nothing and must read "not measured", never "+0" (Lessons R39). */
  measured: z.boolean().default(true),
});

export const AssessedModule = z.object({
  /** Stable within a commit (numbered by path), cited by every later agent. Empty on an
   *  assessment recorded before ids existed (schema 1). */
  id: z.string().default(""),
  name: z.string(),
  path: z.string(),
  ecosystem: z.string(),
  loc: z.number().default(0),
  files: z.number().default(0),
  /** Third-party front-end files (jQuery, Bootstrap, bundles): counted as files, not LOC. */
  vendored_files: z.number().default(0),
  has_tests: z.boolean().default(false),
  runtime: z.object({
    name: z.string().default(""),
    version: z.string().default(""),
    status: RuntimeStatus.catch("unknown"),
    eol_date: z.string().nullable().default(null),
    note: z.string().default(""),
  }),
  dependencies: z.array(AssessedDependency).default([]),
  depends_on: strings,
  dependents: strings,
  blockers: strings,
  risk: z.object({
    score: z.number(),
    tier: MigrationTier,
    factors: z.array(RiskFactor).default([]),
  }),
});
export type AssessedModule = z.infer<typeof AssessedModule>;

export const DiscoveryAssessment = z.object({
  schema_version: z.number(),
  generated_at: z.string(),
  as_of: z.string().default(""),
  target_stack: z.string().default(""),
  repository: z.object({
    url: z.string().default(""),
    branch: z.string().default(""),
    commit: z.string().default(""),
    provider: z.string().default(""),
    name: z.string().default(""),
  }),
  summary: z.object({
    module_count: z.number(),
    file_count: z.number().default(0),
    loc: z.number().default(0),
    vendored_files: z.number().default(0),
    languages: z.record(z.string(), z.number()).default({}),
    ecosystems: strings,
    tier_counts: z.object({
      mechanical: z.number().default(0),
      llm_assisted: z.number().default(0),
      manual: z.number().default(0),
    }),
    risk: z.object({ average: z.number().default(0), max: z.number().default(0) }),
    flag_counts: z.object({
      eol: z.number().default(0),
      deprecated: z.number().default(0),
      vulnerable: z.number().default(0),
    }),
  }),
  modules: z.array(AssessedModule),
  flags: z.object({
    eol: z.array(z.object({
      module: z.string(), runtime: z.string(), status: z.string(),
      eol_date: z.string().nullable().default(null), note: z.string().default(""),
    })).default([]),
    deprecated: z.array(z.object({
      module: z.string(), package: z.string(), version: z.string().default(""), reason: z.string(),
    })).default([]),
    vulnerable: z.array(z.object({
      module: z.string(), package: z.string().nullable().optional(),
      version: z.string().nullable().optional(), cve: z.string().nullable().optional(),
      severity: z.string().nullable().optional(), fixed_version: z.string().nullable().optional(),
      title: z.string().nullable().optional(),
    })).default([]),
  }),
  scanners: z.object({ trivy: z.string().default("skipped"), note: z.string().default("") })
    .default({ trivy: "skipped", note: "" }),
  /** A POINTER once Equivalence Testing accepts a baseline: {status: "captured", baselines: ["BL-01"]}. */
  golden_master: z.object({ status: z.string(), note: z.string().default(""), baselines: strings })
    .default({ status: "not_captured", note: "", baselines: [] }),
  /** What the code alone cannot tell — questions for Target Architecture (research §6.2). */
  not_assessable_statically: z.array(z.object({
    topic: z.string().default(""), modules: strings, question: z.string(),
  })).default([]),
});
export type DiscoveryAssessment = z.infer<typeof DiscoveryAssessment>;

/* ── Target Architecture (Phase E) ─────────────────────────────────────────────
   Mirrors `TargetDesignArtifact` (backend/shared/models/artifacts.py): the hand-over packet's
   DesignPayload plus what the record tool adds (sources, module paths, inventory totals, notes).
   Tolerant like the rest: enums fall back rather than blanking the page over one value. */

export const MIGRATION_PATTERNS = [
  "in_place_upgrade", "strangler_fig", "branch_by_abstraction", "parallel_run",
  "rewrite", "replatform", "retire", "keep",
] as const;
export type MigrationPattern = (typeof MIGRATION_PATTERNS)[number];

const DesignLayer = z.object({ layer: text, today: text, target: text, modules: strings });
const DesignedModule = z.object({
  module_id: z.string(),
  module: text,
  tier: MigrationTier.catch("llm_assisted"),
  risk_score: z.number().default(0),
  patterns: z.array(z.string()).default([]),
  rationale: text,
  adr_ids: strings,
  contract_ids: strings,
});
export type DesignedModule = z.infer<typeof DesignedModule>;
const FrozenContract = z.object({
  id: z.string(),
  name: text,
  kind: z.string().default("http"),
  legacy_location: text,
  consumers: strings,
  proof: text,
  status: z.enum(["confirmed", "proposed"]).catch("proposed"),
  brief_item: z.string().nullable().default(null),
});
export type FrozenContract = z.infer<typeof FrozenContract>;
const Trap = z.object({ id: z.string(), change: text, affects: strings, where: text, effect: text, contract_ids: strings });
export type DesignTrap = z.infer<typeof Trap>;
const Adr = z.object({
  id: z.string(), title: text, context: text, options: strings, decision: text, consequences: text,
  modules: strings, contracts: strings,
});
export type DesignAdr = z.infer<typeof Adr>;

export const TargetDesign = z.object({
  schema_version: z.number().default(1),
  system_name: text,
  summary: text,
  layers: z.array(DesignLayer).default([]),
  modules: z.array(DesignedModule).default([]),
  interop: z.object({ routing: text, data: text, shared_libraries: text, jobs: text, identity: text })
    .partial().default({}),
  ordering_constraints: strings,
  frozen_contracts: z.array(FrozenContract).default([]),
  data_migration: z.object({
    source: text, target: text, method: text, behaviour_changes: strings, cutover: text,
  }).nullable().default(null),
  nfr: z.array(z.object({ measure: text, target: text, source: z.string().default("design") })).default([]),
  security_design: strings,
  traps: z.array(Trap).default([]),
  adrs: z.array(Adr).default([]),
  diagrams: z.array(z.object({ title: text, mermaid: text })).default([]),
  departures_from_brief: z.array(z.object({ brief_said: text, design_says: text, adr_id: text })).default([]),
  open_questions: strings,
  resolved_questions: z.array(z.object({ question: text, answer: text, source: z.string().default("user") }))
    .default([]),
  sources: z.object({
    brief: z.object({ version: z.number().nullable().default(null), status: z.string().default("") })
      .partial().nullable().default(null),
    assessment: z.object({
      version: z.number().nullable().default(null), status: z.string().default(""),
      commit: z.string().nullable().default(null), repository: z.string().nullable().default(null),
    }).partial().nullable().default(null),
    checkout_commit: z.string().nullable().default(null),
  }).partial().default({}),
  module_paths: z.record(z.string(), z.string()).default({}),
  interfaces: z.object({
    commit: z.string().nullable().default(null),
    counts: z.record(z.string(), z.number()).default({}),
    total: z.number().default(0),
  }).nullable().default(null),
  notes: strings,
  recorded_at: z.string().nullable().default(null),
});
export type TargetDesign = z.infer<typeof TargetDesign>;

export const LegacyInterface = z.object({
  kind: z.string(),
  direction: z.string(),
  name: z.string(),
  location: z.string(),
  module: z.string().default(""),
  evidence: z.string().default(""),
});
export type LegacyInterface = z.infer<typeof LegacyInterface>;

export const LegacyInterfaces = z.object({
  projectId: z.string(),
  status: z.enum(["none", "ready"]).catch("none"),
  repository: z.string().nullable().optional(),
  inventory: z.object({
    commit: z.string().default(""),
    counts: z.record(z.string(), z.number()).default({}),
    total: z.number().default(0),
    truncated: z.boolean().default(false),
    items: z.array(LegacyInterface).default([]),
  }).nullable().default(null),
});
export type LegacyInterfaces = z.infer<typeof LegacyInterfaces>;

/** The read endpoints' envelope: the newest run holding a value, or nulls. */
export function stagePayload<T extends z.ZodTypeAny>(payload: T) {
  return z.object({
    projectId: z.string(),
    runId: z.string().nullable(),
    updatedAt: z.string().nullable(),
    payload: payload.nullable(),
  });
}

export const MigrationIntentResponse = stagePayload(MigrationIntentBrief);
export type MigrationIntentResponse = z.infer<typeof MigrationIntentResponse>;
export const DiscoveryResponse = stagePayload(DiscoveryAssessment);
export type DiscoveryResponse = z.infer<typeof DiscoveryResponse>;

/* ── The project's pulled legacy code (both Track 3 pages) ─────────────────── */

export const LegacyCodeStatus = z.enum(["none", "pulling", "ready", "failed"]);
export type LegacyCodeStatus = z.infer<typeof LegacyCodeStatus>;

export const LegacyCodeModule = z.object({
  name: z.string(),
  path: z.string().default(""),
  ecosystem: z.string().default(""),
  runtime: z.string().default(""),
  runtimeStatus: z.string().default("unknown"),
  eolDate: z.string().nullable().default(null),
  loc: z.number().default(0),
  files: z.number().default(0),
  hasTests: z.boolean().default(false),
  platformFeatures: strings,
  dependsOn: strings,
  packageCount: z.number().default(0),
});
export type LegacyCodeModule = z.infer<typeof LegacyCodeModule>;

/** The last GOOD pull — what the project's checkout holds right now. */
export const LegacyCodePull = z.object({
  url: z.string(),
  branch: z.string().default(""),
  commit: z.string().default(""),
  provider: z.string().default(""),
  name: z.string().default(""),
  pulledBy: z.string().default(""),
  pulledAt: z.string().default(""),
  profile: z
    .object({
      summary: z
        .object({
          modules: z.number().default(0),
          files: z.number().default(0),
          loc: z.number().default(0),
          vendoredFiles: z.number().default(0),
          languages: z.record(z.string(), z.number()).default({}),
          ecosystems: strings,
          endOfLife: z.number().default(0),
          deprecatedPackages: z.number().default(0),
        })
        .partial()
        .default({}),
      modules: z.array(LegacyCodeModule).default([]),
    })
    .nullable()
    .default(null),
});
export type LegacyCodePull = z.infer<typeof LegacyCodePull>;

/** `status` is the latest ATTEMPT; `pull` is the last good one (kept when a re-pull fails). */
export const LegacyCodeRecord = z.object({
  projectId: z.string(),
  status: LegacyCodeStatus.catch("none"),
  request: z
    .object({
      url: z.string().default(""),
      branch: z.string().default(""),
      requestedBy: z.string().default(""),
      startedAt: z.string().nullable().default(null),
    })
    .nullable()
    .default(null),
  error: z.string().default(""),
  pull: LegacyCodePull.nullable().default(null),
});
export type LegacyCodeRecord = z.infer<typeof LegacyCodeRecord>;

/** What the project's Azure DevOps / GitHub connection can see, for the Pull dialog. */
export const LegacyRepositories = z.object({
  provider: z.string().default(""),
  projects: z.array(z.string()).optional(),
  repositories: z
    .array(z.object({ name: z.string(), url: z.string().default(""), defaultBranch: z.string().default("") }))
    .optional(),
  problem: z.string().default(""),
});
export type LegacyRepositories = z.infer<typeof LegacyRepositories>;

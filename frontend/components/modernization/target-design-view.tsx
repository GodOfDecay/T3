"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Circle,
  FileLock2,
  GitCommitHorizontal,
  HelpCircle,
  Layers,
  ListOrdered,
  Network,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MermaidRenderer } from "@/components/app/mermaid-renderer";
import { getLedger, stateLabel } from "@/lib/api/modernization-programme";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";
import type {
  DesignAdr,
  DesignedModule,
  DesignTrap,
  FrozenContract,
  MigrationPattern,
  TargetDesign,
} from "@/lib/schemas/modernization";

import { TierBadge } from "./assessment-view";

/**
 * A recorded target design (Track 3, Target Architecture), rendered for the Architect who signs it
 * off and for Migration Strategy's owner who plans from it.
 *
 * DATA, NOT A DOCUMENT — like the assessment. The questions a reviewer asks are data questions:
 * which modules are strangled and why, what exactly is frozen and where is it defined, which traps
 * touch the bank file, which decision departs from the brief. So: a pattern mix, a module table
 * with a detail pane that joins its contracts, traps and ADRs; contracts with their legacy
 * location and proof; ADRs with the chosen option marked; the three diagrams. Every value comes
 * from the frozen version — nothing is recomputed here.
 *
 * THE LEDGER PANEL SAYS WHAT APPROVAL DOES, and only that (R48): approval puts each designed
 * module on the Module Migration Ledger as `designed` (the publish route does it, in the same
 * transaction). Before approval it says so as a consequence; after, it shows where each module
 * actually is now.
 */

export const PATTERN_META: Record<MigrationPattern, { label: string; hint: string }> = {
  in_place_upgrade: { label: "In-place upgrade", hint: "Same language, upgraded where it stands." },
  strangler_fig: {
    label: "Strangler fig",
    hint: "A routing facade moves traffic to the new implementation piece by piece until the legacy serves nothing.",
  },
  branch_by_abstraction: {
    label: "Branch by abstraction",
    hint: "An interface in the code lets old and new sit side by side behind a switch.",
  },
  parallel_run: {
    label: "Parallel run",
    hint: "Old and new process the same inputs; the old stays the system of record until outputs agree.",
  },
  rewrite: { label: "Rewrite", hint: "Rebuilt on the target, with behaviour recorded from the legacy first." },
  replatform: { label: "Replatform", hint: "Same code on new hosting or runtime." },
  retire: { label: "Retire", hint: "Switched off, with its users and data accounted for." },
  keep: { label: "Keep", hint: "Deliberately left as it is, with a reason." },
};

export function patternLabel(p: string): string {
  return (PATTERN_META as Record<string, { label: string }>)[p]?.label ?? p.replace(/_/g, " ");
}

function PatternBadge({ pattern }: { pattern: string }) {
  const meta = (PATTERN_META as Record<string, { label: string; hint: string }>)[pattern];
  return (
    <Badge variant="outline" title={meta?.hint} className="whitespace-nowrap font-normal">
      {patternLabel(pattern)}
    </Badge>
  );
}

const STATUS_WORD: Record<string, string> = {
  published: "approved",
  granted: "approved by exception",
  draft: "not yet approved",
};

export function TargetDesignView({
  design,
  projectId,
  approved,
  status,
}: {
  design: TargetDesign;
  projectId?: ProjectId;
  /** This version is the approved one — the ledger panel then shows live states. */
  approved?: boolean;
  /** The version's status: a rejected or superseded one cannot be approved, and says so. */
  status?: string;
}) {
  const confirmed = design.frozen_contracts.filter((c) => c.status === "confirmed").length;
  const proposed = design.frozen_contracts.length - confirmed;
  return (
    <div className="space-y-6">
      <section aria-label="Target design summary" className="space-y-3">
        <Sources design={design} />
        {design.summary && <p className="max-w-4xl text-sm leading-relaxed">{design.summary}</p>}
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Modules" value={design.modules.length} />
          <Stat
            label="Frozen contracts"
            value={design.frozen_contracts.length}
            detail={proposed ? `${confirmed} confirmed, ${proposed} proposed` : undefined}
          />
          <Stat label="Version traps" value={design.traps.length} />
          <Stat label="Decisions (ADRs)" value={design.adrs.length} />
          <Stat label="Departures from the brief" value={design.departures_from_brief.length} />
          <Stat label="Open questions" value={design.open_questions.length} emphasis={design.open_questions.length > 0} />
        </dl>
        <PatternMix modules={design.modules} />
        {design.notes.length > 0 && (
          <ul role="status" aria-label="Notes" className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
            {design.notes.map((n) => (
              <li key={n} className="flex gap-2">
                <AlertTriangle className="size-3.5 shrink-0 text-amber-600" aria-hidden />
                <span>{n}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {projectId && (
        <LedgerPanel projectId={projectId} modules={design.modules} approved={!!approved} status={status} />
      )}

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="modules">Modules ({design.modules.length})</TabsTrigger>
          <TabsTrigger value="contracts">Contracts ({design.frozen_contracts.length})</TabsTrigger>
          <TabsTrigger value="traps">Traps ({design.traps.length})</TabsTrigger>
          <TabsTrigger value="decisions">Decisions ({design.adrs.length})</TabsTrigger>
          <TabsTrigger value="diagrams">Diagrams ({design.diagrams.length})</TabsTrigger>
          <TabsTrigger value="questions">
            Questions ({design.resolved_questions.length + design.open_questions.length})
          </TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-4">
          <Overview design={design} />
        </TabsContent>
        <TabsContent value="modules" className="mt-4">
          <Modules design={design} />
        </TabsContent>
        <TabsContent value="contracts" className="mt-4">
          <Contracts contracts={design.frozen_contracts} />
        </TabsContent>
        <TabsContent value="traps" className="mt-4">
          <Traps traps={design.traps} />
        </TabsContent>
        <TabsContent value="decisions" className="mt-4">
          <Decisions adrs={design.adrs} departures={design.departures_from_brief} />
        </TabsContent>
        <TabsContent value="diagrams" className="mt-4">
          <Diagrams diagrams={design.diagrams} />
        </TabsContent>
        <TabsContent value="questions" className="mt-4">
          <Questions resolved={design.resolved_questions} open={design.open_questions} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Sources({ design }: { design: TargetDesign }) {
  const { brief, assessment } = design.sources;
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {design.system_name && <span className="text-foreground font-medium">{design.system_name}</span>}
      {brief?.version != null ? (
        <span>Brief v{brief.version} ({STATUS_WORD[brief.status ?? ""] ?? brief.status})</span>
      ) : (
        <span>Brief: from the Orchestrator conversation</span>
      )}
      {assessment?.version != null && (
        <span>Assessment v{assessment.version} ({STATUS_WORD[assessment.status ?? ""] ?? assessment.status})</span>
      )}
      {assessment?.commit && (
        <span className="inline-flex items-center gap-1 font-mono">
          <GitCommitHorizontal className="size-3" aria-hidden />
          {assessment.commit.slice(0, 10)}
        </span>
      )}
      {design.interfaces ? (
        <span>{design.interfaces.total} legacy interfaces found in the code</span>
      ) : (
        <span>No legacy code was pulled — contract locations were not checked against the code</span>
      )}
      {design.recorded_at && <span>Recorded {new Date(design.recorded_at).toLocaleString()}</span>}
    </div>
  );
}

function Stat({ label, value, detail, emphasis }: {
  label: string; value: React.ReactNode; detail?: string; emphasis?: boolean;
}) {
  return (
    <div className="rounded-lg border px-3 py-2">
      <dt className="text-muted-foreground text-[11px]">{label}</dt>
      <dd className={cn("font-display text-lg font-semibold tabular-nums", emphasis && "text-amber-600")}>{value}</dd>
      {detail && <dd className="text-muted-foreground text-[11px]">{detail}</dd>}
    </div>
  );
}

function PatternMix({ modules }: { modules: readonly DesignedModule[] }) {
  const counts = new Map<string, number>();
  for (const m of modules) for (const p of m.patterns) counts.set(p, (counts.get(p) ?? 0) + 1);
  if (counts.size === 0) return null;
  return (
    <ul aria-label="Migration patterns" className="flex flex-wrap gap-2">
      {[...counts.entries()].sort((a, b) => b[1] - a[1]).map(([p, n]) => (
        <li key={p} className="bg-muted/40 rounded-md border px-2 py-1 text-xs" title={
          (PATTERN_META as Record<string, { hint: string }>)[p]?.hint}>
          <span className="font-medium">{patternLabel(p)}</span>{" "}
          <span className="text-muted-foreground">× {n}</span>
        </li>
      ))}
    </ul>
  );
}

// ── ledger ──────────────────────────────────────────────────────────────────

/** What the ledger panel says, by the version's state — true in every state (R48). */
export function ledgerText(approved: boolean, status: string | undefined, count: number): string {
  if (approved) return "This design is approved: its modules are on the migration ledger. Where each one is now:";
  if (status === "rejected") return "This version was rejected, so it cannot be approved and does not change the ledger.";
  if (status === "superseded") {
    return "A newer design has been approved since; the ledger follows that one. Where each module is now:";
  }
  return `Approving this version puts these ${count} modules on the migration ledger as “designed” — the state Migration Strategy sequences from.`;
}

function LedgerPanel({ projectId, modules, approved, status }: {
  projectId: ProjectId; modules: readonly DesignedModule[]; approved: boolean; status?: string;
}) {
  const q = useQuery({ queryKey: qk.modernizationProgramme.ledger(projectId), queryFn: () => getLedger(projectId) });
  // The approval that just happened moved the ledger; read it again rather than show the old state.
  const { refetch } = q;
  React.useEffect(() => {
    if (approved) void refetch();
  }, [approved, refetch]);
  const rows = new Map((q.data?.modules ?? []).map((m) => [m.moduleId, m]));
  return (
    <section aria-label="Module ledger" className="rounded-lg border p-3">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <ListOrdered className="text-muted-foreground size-4" aria-hidden /> Module ledger
      </h3>
      <p className="text-muted-foreground mt-1 text-xs">{ledgerText(approved, status, modules.length)}</p>
      {q.isError && <p className="text-muted-foreground mt-1 text-xs">The ledger could not be loaded.</p>}
      <ul className="mt-2 flex flex-wrap gap-2">
        {modules.map((m) => {
          const row = rows.get(m.module_id);
          return (
            <li key={m.module_id} className="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs">
              <span className="font-mono">{m.module_id}</span>
              <span className="text-muted-foreground">{m.module}</span>
              {row ? (
                <Badge variant={row.state === "blocked" ? "danger" : "info"} className="font-normal">
                  {stateLabel(row.state)}
                </Badge>
              ) : (
                <Badge variant="outline" className="font-normal">not on the ledger yet</Badge>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ── overview ────────────────────────────────────────────────────────────────

const INTEROP: [keyof TargetDesign["interop"], string][] = [
  ["routing", "Routing"], ["data", "Data"], ["shared_libraries", "Shared libraries"],
  ["jobs", "Scheduled jobs"], ["identity", "Identity and sessions"],
];

function Overview({ design }: { design: TargetDesign }) {
  const interop = INTEROP.filter(([k]) => design.interop[k]);
  return (
    <div className="space-y-6">
      <section aria-label="Target per part of the system" className="space-y-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Layers className="text-muted-foreground size-4" aria-hidden /> Target per part of the system
        </h3>
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs">
              <tr>
                <th className="px-3 py-2 font-medium">Part</th>
                <th className="px-3 py-2 font-medium">Today</th>
                <th className="px-3 py-2 font-medium" aria-label="becomes" />
                <th className="px-3 py-2 font-medium">Target</th>
                <th className="px-3 py-2 font-medium">Modules</th>
              </tr>
            </thead>
            <tbody>
              {design.layers.map((l) => (
                <tr key={l.layer} className="border-t">
                  <td className="px-3 py-2 font-medium">{l.layer}</td>
                  <td className="text-muted-foreground px-3 py-2">{l.today}</td>
                  <td className="px-1 py-2"><ArrowRight className="text-muted-foreground size-3.5" aria-hidden /></td>
                  <td className="px-3 py-2">{l.target}</td>
                  <td className="px-3 py-2 font-mono text-xs">{l.modules.join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {interop.length > 0 && (
        <section aria-label="How old and new coexist" className="space-y-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Network className="text-muted-foreground size-4" aria-hidden /> How the old and the new coexist
          </h3>
          <dl className="grid gap-2 md:grid-cols-2">
            {interop.map(([k, label]) => (
              <div key={k} className="rounded-lg border p-3">
                <dt className="text-muted-foreground text-xs font-medium">{label}</dt>
                <dd className="mt-1 text-sm">{design.interop[k]}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {design.ordering_constraints.length > 0 && (
        <section aria-label="Constraints on the order of the move" className="space-y-2">
          <h3 className="text-sm font-semibold">Constraints on the order of the move</h3>
          <p className="text-muted-foreground text-xs">Migration Strategy sequences the waves from these.</p>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {design.ordering_constraints.map((c) => <li key={c}>{c}</li>)}
          </ul>
        </section>
      )}

      {design.data_migration && (
        <section aria-label="Data migration" className="space-y-2">
          <h3 className="text-sm font-semibold">Data migration</h3>
          <dl className="grid gap-2 rounded-lg border p-3 text-sm md:grid-cols-2">
            <Field label="From" value={design.data_migration.source} />
            <Field label="To" value={design.data_migration.target} />
            <Field label="Method" value={design.data_migration.method} />
            <Field label="Cutover" value={design.data_migration.cutover} />
            {design.data_migration.behaviour_changes.length > 0 && (
              <div className="md:col-span-2">
                <dt className="text-muted-foreground text-xs font-medium">Engine behaviour changes</dt>
                <dd>
                  <ul className="mt-1 list-disc pl-5">
                    {design.data_migration.behaviour_changes.map((b) => <li key={b}>{b}</li>)}
                  </ul>
                </dd>
              </div>
            )}
          </dl>
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {design.nfr.length > 0 && (
          <section aria-label="Non-functional targets" className="space-y-2">
            <h3 className="text-sm font-semibold">Non-functional targets</h3>
            <ul className="space-y-1 text-sm">
              {design.nfr.map((n) => (
                <li key={n.measure} className="flex flex-wrap gap-x-2">
                  <span className="font-medium">{n.measure}</span>
                  <span>{n.target}</span>
                  <span className="text-muted-foreground text-xs">(from the {n.source})</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {design.security_design.length > 0 && (
          <section aria-label="Security design" className="space-y-2">
            <h3 className="text-sm font-semibold">Security design</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {design.security_design.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs font-medium">{label}</dt>
      <dd>{value || "—"}</dd>
    </div>
  );
}

// ── modules ─────────────────────────────────────────────────────────────────

function Modules({ design }: { design: TargetDesign }) {
  const [pattern, setPattern] = React.useState<string>("all");
  const [selected, setSelected] = React.useState<string | null>(null);
  const patterns = [...new Set(design.modules.flatMap((m) => m.patterns))];
  const visible = pattern === "all" ? design.modules : design.modules.filter((m) => m.patterns.includes(pattern));
  const active = design.modules.find((m) => m.module_id === selected) ?? null;
  return (
    <div className="space-y-3">
      <div role="group" aria-label="Filter by pattern" className="flex flex-wrap gap-2">
        {["all", ...patterns].map((p) => (
          <button
            key={p}
            type="button"
            aria-pressed={pattern === p}
            onClick={() => setPattern(p)}
            className={cn(
              "rounded-md border px-2.5 py-1 text-xs transition-colors",
              pattern === p ? "bg-primary/10 border-primary text-foreground" : "text-muted-foreground hover:bg-muted",
            )}
          >
            {p === "all" ? `All (${design.modules.length})` : patternLabel(p)}
          </button>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs">
              <tr>
                <th className="px-3 py-2 font-medium">Id</th>
                <th className="px-3 py-2 font-medium">Module</th>
                <th className="px-3 py-2 font-medium">Tier</th>
                <th className="px-3 py-2 text-right font-medium">Risk</th>
                <th className="px-3 py-2 font-medium">Pattern</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((m) => (
                <tr
                  key={m.module_id}
                  onClick={() => setSelected(m.module_id === selected ? null : m.module_id)}
                  aria-selected={m.module_id === selected}
                  className={cn("hover:bg-muted/40 cursor-pointer border-t", m.module_id === selected && "bg-primary/5")}
                >
                  <td className="px-3 py-2 font-mono text-xs">{m.module_id}</td>
                  <td className="px-3 py-2">
                    <p className="font-medium">{m.module}</p>
                    {design.module_paths[m.module_id] && (
                      <p className="text-muted-foreground font-mono text-[11px]">{design.module_paths[m.module_id]}</p>
                    )}
                  </td>
                  <td className="px-3 py-2"><TierBadge tier={m.tier} /></td>
                  <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">{m.risk_score}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {m.patterns.map((p) => <PatternBadge key={p} pattern={p} />)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ModuleDetail module={active} design={design} />
      </div>
    </div>
  );
}

function ModuleDetail({ module, design }: { module: DesignedModule | null; design: TargetDesign }) {
  if (!module) {
    return (
      <aside className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
        Select a module to see why it gets its pattern, and the contracts, traps and decisions that touch it.
      </aside>
    );
  }
  const contracts = design.frozen_contracts.filter((c) => module.contract_ids.includes(c.id));
  const adrs = design.adrs.filter((a) => module.adr_ids.includes(a.id) || a.modules.includes(module.module_id));
  const traps = design.traps.filter((t) => t.affects.includes(module.module_id));
  return (
    <aside aria-label={`${module.module_id} detail`} className="space-y-4 rounded-lg border p-4">
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold">{module.module_id} · {module.module}</h3>
          <TierBadge tier={module.tier} />
        </div>
        <div className="flex flex-wrap gap-1">{module.patterns.map((p) => <PatternBadge key={p} pattern={p} />)}</div>
        {module.patterns.map((p) => (
          <p key={p} className="text-muted-foreground text-xs">
            {patternLabel(p)}: {(PATTERN_META as Record<string, { hint: string }>)[p]?.hint}
          </p>
        ))}
      </header>
      <section className="space-y-1">
        <h4 className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">Why</h4>
        <p className="text-sm">{module.rationale}</p>
      </section>
      <DetailList title="Frozen contracts" empty="None." items={contracts.map((c) => `${c.id} ${c.name}`)} />
      <DetailList title="Traps" empty="None named." items={traps.map((t) => `${t.id} ${t.change}`)} />
      <DetailList title="Decisions" empty="None." items={adrs.map((a) => `${a.id} ${a.title}`)} />
    </aside>
  );
}

function DetailList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <section className="space-y-1">
      <h4 className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">{title}</h4>
      {items.length ? (
        <ul className="space-y-1 text-sm">{items.map((i) => <li key={i}>{i}</li>)}</ul>
      ) : (
        <p className="text-muted-foreground text-sm">{empty}</p>
      )}
    </section>
  );
}

// ── contracts, traps, decisions ─────────────────────────────────────────────

function Contracts({ contracts }: { contracts: readonly FrozenContract[] }) {
  if (!contracts.length) return <p className="text-muted-foreground text-sm">No frozen contracts.</p>;
  return (
    <ul className="grid gap-3 lg:grid-cols-2">
      {contracts.map((c) => (
        <li key={c.id} className="space-y-2 rounded-lg border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <FileLock2 className="text-muted-foreground size-4" aria-hidden />
            <span className="font-mono text-xs">{c.id}</span>
            <span className="font-medium">{c.name}</span>
            <Badge variant="outline" className="font-normal">{c.kind}</Badge>
            <Badge variant={c.status === "confirmed" ? "success" : "warning"} className="font-normal">
              {c.status === "confirmed" ? "Confirmed" : "Proposed — needs confirming"}
            </Badge>
          </div>
          {c.brief_item && (
            <p className="text-xs">
              <span className="text-muted-foreground">The brief: </span>“{c.brief_item}”
            </p>
          )}
          <dl className="grid gap-1 text-xs">
            <div className="flex gap-2">
              <dt className="text-muted-foreground w-20 shrink-0">Defined in</dt>
              <dd><code className="break-all">{c.legacy_location}</code></dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground w-20 shrink-0">Consumers</dt>
              <dd>{c.consumers.join(", ") || "—"}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground w-20 shrink-0">Proven by</dt>
              <dd>{c.proof}</dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  );
}

function Traps({ traps }: { traps: readonly DesignTrap[] }) {
  if (!traps.length) return <p className="text-muted-foreground text-sm">No version traps named.</p>;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-muted-foreground text-left text-xs">
          <tr>
            <th className="px-3 py-2 font-medium">Id</th>
            <th className="px-3 py-2 font-medium">What changes</th>
            <th className="px-3 py-2 font-medium">Where it bites</th>
            <th className="px-3 py-2 font-medium">Effect</th>
            <th className="px-3 py-2 font-medium">Modules</th>
            <th className="px-3 py-2 font-medium">Contracts</th>
          </tr>
        </thead>
        <tbody>
          {traps.map((t) => (
            <tr key={t.id} className="border-t align-top">
              <td className="px-3 py-2 font-mono text-xs">{t.id}</td>
              <td className="px-3 py-2">{t.change}</td>
              <td className="px-3 py-2"><code className="break-all text-xs">{t.where}</code></td>
              <td className="px-3 py-2">{t.effect}</td>
              <td className="px-3 py-2 font-mono text-xs">{t.affects.join(", ")}</td>
              <td className="px-3 py-2 font-mono text-xs">{t.contract_ids.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");

/** The option an ADR chose: the one whose words are the decision, or that the decision opens with. */
export function chosenOption(adr: DesignAdr): string | null {
  const d = norm(adr.decision);
  return adr.options.find((o) => norm(o) === d) ?? adr.options.find((o) => d.startsWith(norm(o))) ?? null;
}

function Decisions({ adrs, departures }: {
  adrs: readonly DesignAdr[]; departures: TargetDesign["departures_from_brief"];
}) {
  const departing = new Set(departures.map((d) => d.adr_id));
  return (
    <div className="space-y-4">
      {departures.length > 0 && (
        <section aria-label="Departures from the brief" className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
          <h3 className="text-sm font-semibold">Departures from the brief</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {departures.map((d) => (
              <li key={d.adr_id + d.design_says}>
                The brief said <span className="italic">{d.brief_said}</span>; the design says{" "}
                <span className="font-medium">{d.design_says}</span> <span className="font-mono text-xs">({d.adr_id})</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {adrs.length === 0 && <p className="text-muted-foreground text-sm">No decisions recorded.</p>}
      <ul className="space-y-3">
        {adrs.map((a) => {
          const chosen = chosenOption(a);
          return (
            <li key={a.id} className="space-y-2 rounded-lg border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{a.id}</span>
                <h4 className="font-medium">{a.title}</h4>
                {departing.has(a.id) && <Badge variant="warning" className="font-normal">departs from the brief</Badge>}
              </div>
              <p className="text-sm"><span className="text-muted-foreground">Context. </span>{a.context}</p>
              <ul aria-label={`${a.id} options`} className="space-y-1 text-sm">
                {a.options.map((o) => (
                  <li key={o} className={cn("flex items-start gap-2", o === chosen && "font-medium")}>
                    {o === chosen ? (
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-label="chosen" />
                    ) : (
                      <Circle className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden />
                    )}
                    {o}
                  </li>
                ))}
              </ul>
              <p className="text-sm"><span className="text-muted-foreground">Decision. </span>{a.decision}</p>
              <p className="text-sm"><span className="text-muted-foreground">Consequences. </span>{a.consequences}</p>
              {(a.modules.length > 0 || a.contracts.length > 0) && (
                <p className="text-muted-foreground font-mono text-xs">Touches {[...a.modules, ...a.contracts].join(", ")}</p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ── diagrams and questions ──────────────────────────────────────────────────

function Diagrams({ diagrams }: { diagrams: TargetDesign["diagrams"] }) {
  const [active, setActive] = React.useState(0);
  if (!diagrams.length) return <p className="text-muted-foreground text-sm">No diagrams.</p>;
  const current = diagrams[Math.min(active, diagrams.length - 1)]!;
  return (
    <div className="space-y-3">
      <div role="group" aria-label="Diagram" className="flex flex-wrap gap-2">
        {diagrams.map((d, i) => (
          <button
            key={d.title + i}
            type="button"
            aria-pressed={i === active}
            onClick={() => setActive(i)}
            className={cn(
              "rounded-md border px-2.5 py-1 text-xs transition-colors",
              i === active ? "bg-primary/10 border-primary text-foreground" : "text-muted-foreground hover:bg-muted",
            )}
          >
            {d.title}
          </button>
        ))}
      </div>
      <MermaidRenderer key={current.title} source={current.mermaid} height={460} />
    </div>
  );
}

function Questions({ resolved, open }: { resolved: TargetDesign["resolved_questions"]; open: string[] }) {
  if (!resolved.length && !open.length) {
    return <p className="text-muted-foreground text-sm">The assessment left no questions the code could not answer.</p>;
  }
  return (
    <div className="space-y-4">
      {open.length > 0 && (
        <section aria-label="Open questions" className="space-y-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <HelpCircle className="size-4 text-amber-600" aria-hidden /> Still open
          </h3>
          <ul className="space-y-1.5">
            {open.map((q) => (
              <li key={q} className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-2.5 text-sm">{q}</li>
            ))}
          </ul>
        </section>
      )}
      {resolved.length > 0 && (
        <section aria-label="Answered questions" className="space-y-2">
          <h3 className="text-sm font-semibold">Answered — what the design rests on</h3>
          <ul className="space-y-2">
            {resolved.map((r) => (
              <li key={r.question} className="space-y-1 rounded-lg border p-2.5 text-sm">
                <p className="text-muted-foreground">{r.question}</p>
                <p>
                  {r.answer}{" "}
                  <Badge variant="outline" className="ml-1 font-normal">from the {r.source}</Badge>
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

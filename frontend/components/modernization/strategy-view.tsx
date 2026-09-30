"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, CheckCircle2, GitBranch, ListOrdered, RotateCcw } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getLedger, stateLabel } from "@/lib/api/modernization-programme";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";
import type { MigrationPlan, PlanCriterion, PlanWave } from "@/lib/schemas/modernization";

import { patternLabel } from "./target-design-view";

/**
 * A recorded migration plan (Track 3, Migration Strategy), for the Architect who signs it off and for
 * Equivalence Testing and Migration Development, which work from it.
 *
 * The questions a reviewer asks are about TIME and PROOF: when does each wave run against the
 * brief's dates, what must pass before a wave is done, what has to be recorded from the legacy system
 * first and by when, which conflicts with the calendar are still open. So: a timeline with the
 * brief's deadline, freeze and milestones on it; waves with entry, exit and rollback; the criteria and
 * the baselines behind them; every calendar conflict the check computed, and whether it was reported
 * and resolved; the dependency-safe order the plan started from, and where it departs. Nothing is
 * recomputed here — every value is the frozen version's.
 */

const COMPARISON: Record<string, string> = {
  exact: "Exact", byte_identical: "Byte-identical", numeric_tolerance: "Within tolerance",
  schema_equal: "Same schema", set_equal: "Same set", percentile_threshold: "Percentile threshold",
};

const STATUS_WORD: Record<string, string> = {
  published: "approved", granted: "approved by exception", draft: "not yet approved",
};

const day = (s?: string | null) => (s ? new Date(`${s}T00:00:00Z`).getTime() : NaN);
const fmt = (s?: string | null) =>
  s ? new Date(`${s}T00:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "—";

export function StrategyView({ plan, projectId, approved, status }: {
  plan: MigrationPlan;
  projectId?: ProjectId;
  approved?: boolean;
  status?: string;
}) {
  const moving = plan.waves.filter((w) => w.id !== "W0");
  const dues = plan.baseline_plan.map((b) => b.due).filter(Boolean).sort();
  const reported = new Set(plan.calendar_conflicts.map((c) => c.ref).filter(Boolean));
  const open = plan.calendar_conflicts.filter((c) => !(c.resolution ?? "").trim()).length;
  return (
    <div className="space-y-6">
      <section aria-label="Migration plan summary" className="space-y-3">
        <Sources plan={plan} />
        {plan.summary && <p className="max-w-4xl text-sm leading-relaxed">{plan.summary}</p>}
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Waves" value={`W0 + ${moving.length}`} />
          <Stat label="Modules planned" value={plan.placements.length} />
          <Stat label="Equivalence criteria" value={plan.equivalence_criteria.length} />
          <Stat label="Last baseline due" value={dues.length ? fmt(dues[dues.length - 1]) : "—"} />
          <Stat label="Open calendar conflicts" value={open} emphasis={open > 0} />
          <Stat label="Effort (estimate)" value={plan.effort_table?.total_band || "not estimated"} small />
        </dl>
        {plan.notes.length > 0 && (
          <ul role="status" aria-label="Notes" className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
            {plan.notes.map((n) => (
              <li key={n} className="flex gap-2">
                <AlertTriangle className="size-3.5 shrink-0 text-amber-600" aria-hidden />
                <span>{n}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Timeline plan={plan} />

      {projectId && <StrategyLedger projectId={projectId} plan={plan} approved={!!approved} status={status} />}

      <Tabs defaultValue="waves">
        <TabsList className="flex-wrap">
          <TabsTrigger value="waves">Waves ({plan.waves.length})</TabsTrigger>
          <TabsTrigger value="criteria">Criteria ({plan.equivalence_criteria.length})</TabsTrigger>
          <TabsTrigger value="baselines">Baselines ({plan.baseline_plan.length})</TabsTrigger>
          <TabsTrigger value="calendar">Calendar ({plan.calendar_checked.length + plan.calendar_conflicts.filter((c) => !c.ref).length})</TabsTrigger>
          <TabsTrigger value="order">Order</TabsTrigger>
          <TabsTrigger value="raid">RAID</TabsTrigger>
          <TabsTrigger value="effort">Effort</TabsTrigger>
        </TabsList>
        <TabsContent value="waves" className="mt-4"><Waves plan={plan} /></TabsContent>
        <TabsContent value="criteria" className="mt-4"><Criteria plan={plan} /></TabsContent>
        <TabsContent value="baselines" className="mt-4"><Baselines plan={plan} /></TabsContent>
        <TabsContent value="calendar" className="mt-4"><Calendar plan={plan} reported={reported} /></TabsContent>
        <TabsContent value="order" className="mt-4"><Order plan={plan} /></TabsContent>
        <TabsContent value="raid" className="mt-4"><Raid plan={plan} /></TabsContent>
        <TabsContent value="effort" className="mt-4"><Effort plan={plan} /></TabsContent>
      </Tabs>
    </div>
  );
}

function Sources({ plan }: { plan: MigrationPlan }) {
  const label = (key: string, noun: string) => {
    const s = plan.sources[key];
    return s?.version != null ? `${noun} v${s.version} (${STATUS_WORD[s.status ?? ""] ?? s.status})` : null;
  };
  const parts = [label("brief", "Brief"), label("assessment", "Assessment"), label("design", "Target design")].filter(Boolean);
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {plan.system_name && <span className="text-foreground font-medium">{plan.system_name}</span>}
      {parts.length ? parts.map((p) => <span key={p}>{p}</span>) : <span>From the Orchestrator conversation</span>}
      {plan.recorded_at && <span>Recorded {new Date(plan.recorded_at).toLocaleString()}</span>}
    </div>
  );
}

function Stat({ label, value, emphasis, small }: { label: string; value: React.ReactNode; emphasis?: boolean; small?: boolean }) {
  return (
    <div className="rounded-lg border px-3 py-2">
      <dt className="text-muted-foreground text-[11px]">{label}</dt>
      <dd className={cn("font-display font-semibold tabular-nums", small ? "text-sm" : "text-lg", emphasis && "text-amber-600")}>
        {value}
      </dd>
    </div>
  );
}

// ── timeline ────────────────────────────────────────────────────────────────

type Marker = { key: string; date: string; label: string; tone: "danger" | "warning" | "info" };

export function timelineMarkers(plan: MigrationPlan): Marker[] {
  const out: Marker[] = [];
  const b = plan.brief_dates;
  if (b.deadline) out.push({ key: "deadline", date: b.deadline, label: `Deadline ${fmt(b.deadline)}`, tone: "danger" });
  const freeze = plan.freeze_policy.from || b.freeze_from;
  if (freeze) out.push({ key: "freeze", date: freeze, label: `Legacy freeze ${fmt(freeze)}`, tone: "warning" });
  for (const m of b.milestones ?? []) {
    if (m.kind === "freeze" && m.date === freeze) continue;
    if (m.kind === "deadline" && m.date === b.deadline) continue;
    out.push({ key: `m-${m.date}-${m.label}`, date: m.date, label: `${m.label} ${fmt(m.date)}`, tone: "info" });
  }
  return out;
}

function Timeline({ plan }: { plan: MigrationPlan }) {
  const markers = timelineMarkers(plan);
  const dates = [...plan.waves.flatMap((w) => [day(w.starts), day(w.ends)]), ...markers.map((m) => day(m.date))]
    .filter((d) => !Number.isNaN(d));
  if (!dates.length) return null;
  const min = Math.min(...dates);
  const span = Math.max(Math.max(...dates) - min, 1);
  const pos = (d: number) => `${((d - min) / span) * 100}%`;
  return (
    <section aria-label="Timeline" className="rounded-lg border p-3">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <CalendarClock className="text-muted-foreground size-4" aria-hidden /> Timeline
      </h3>
      <div className="relative mt-3 space-y-1.5 pr-2">
        {markers.map((m) => (
          <div key={m.key} aria-hidden className={cn("absolute top-0 bottom-0 w-px",
            m.tone === "danger" ? "bg-destructive" : m.tone === "warning" ? "bg-amber-500" : "bg-sky-500")}
            style={{ left: pos(day(m.date)) }} title={m.label} />
        ))}
        {plan.waves.map((w) => {
          const s = day(w.starts), e = day(w.ends);
          if (Number.isNaN(s) || Number.isNaN(e)) return null;
          return (
            <div key={w.id} className="relative h-7">
              <div className={cn("absolute inset-y-0 flex items-center overflow-hidden rounded px-2 text-[11px] whitespace-nowrap",
                w.id === "W0" ? "bg-muted text-muted-foreground" : "bg-primary/15 text-foreground")}
                style={{ left: pos(s), width: `max(${((e - s) / span) * 100}%, 2.5rem)` }}
                title={`${w.id} ${w.name}: ${fmt(w.starts)} → ${fmt(w.ends)} (${w.date_status})`}>
                <span className="font-medium">{w.id}</span>&nbsp;{w.name}
                {w.date_status === "proposed" && <span className="text-muted-foreground">&nbsp;· proposed</span>}
              </div>
            </div>
          );
        })}
      </div>
      <ul aria-label="Dates on the timeline" className="text-muted-foreground mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
        {markers.map((m) => (
          <li key={m.key} className="flex items-center gap-1.5">
            <span aria-hidden className={cn("inline-block h-3 w-px",
              m.tone === "danger" ? "bg-destructive" : m.tone === "warning" ? "bg-amber-500" : "bg-sky-500")} />
            {m.label}
          </li>
        ))}
      </ul>
    </section>
  );
}

// ── ledger ──────────────────────────────────────────────────────────────────

export function strategyLedgerText(approved: boolean, status: string | undefined, count: number): string {
  if (approved) return "This plan is approved: its modules are sequenced on the migration ledger. Where each one is now:";
  if (status === "rejected") return "This version was rejected, so it cannot be approved and does not change the ledger.";
  if (status === "superseded") return "A newer plan has been approved since; the ledger follows that one. Where each module is now:";
  return `Approving this version sequences these ${count} modules on the migration ledger, each in its wave with its criteria.`;
}

function StrategyLedger({ projectId, plan, approved, status }: {
  projectId: ProjectId; plan: MigrationPlan; approved: boolean; status?: string;
}) {
  const q = useQuery({ queryKey: qk.modernizationProgramme.ledger(projectId), queryFn: () => getLedger(projectId) });
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
      <p className="text-muted-foreground mt-1 text-xs">{strategyLedgerText(approved, status, plan.placements.length)}</p>
      {q.isError && <p className="text-muted-foreground mt-1 text-xs">The ledger could not be loaded.</p>}
      <ul className="mt-2 flex flex-wrap gap-2">
        {plan.placements.map((p) => {
          const row = rows.get(p.module_id);
          return (
            <li key={p.module_id} className="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs">
              <span className="font-mono">{p.module_id}</span>
              <span className="text-muted-foreground">→ {p.wave}</span>
              {row ? (
                <Badge variant={row.state === "blocked" ? "danger" : "info"} className="font-normal">
                  {stateLabel(row.state)}{row.wave && row.wave !== p.wave ? ` in ${row.wave}` : ""}
                </Badge>
              ) : (
                <Badge variant="outline" className="font-normal">not on the ledger — design not approved</Badge>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ── waves ───────────────────────────────────────────────────────────────────

function Waves({ plan }: { plan: MigrationPlan }) {
  return (
    <ol className="space-y-3">
      {plan.waves.map((w) => <WaveCard key={w.id} wave={w} />)}
      {plan.order_exceptions.length > 0 && (
        <li aria-label="Order exceptions" className="rounded-lg border border-sky-500/40 bg-sky-500/5 p-3 text-sm">
          <p className="font-medium">Moved before what they depend on — the design allows it</p>
          <ul className="mt-1 space-y-1">
            {plan.order_exceptions.map((x) => (
              <li key={`${x.module_id}-${x.depends_on}`}>
                <span className="font-mono text-xs">{x.module_id}</span> before{" "}
                <span className="font-mono text-xs">{x.depends_on}</span>: {x.reason}{" "}
                <span className="font-mono text-xs">({x.adr_id})</span>
              </li>
            ))}
          </ul>
        </li>
      )}
    </ol>
  );
}

function WaveCard({ wave: w }: { wave: PlanWave }) {
  return (
    <li aria-label={`${w.id} ${w.name}`} className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{w.id}</span>
        <h4 className="font-medium">{w.name}</h4>
        <span className="text-muted-foreground text-xs">{fmt(w.starts)} → {fmt(w.ends)}</span>
        <Badge variant={w.date_status === "given" ? "success" : "outline"} className="font-normal">
          {w.date_status === "given" ? "dates given" : "dates proposed"}
        </Badge>
        {w.owner && <span className="text-muted-foreground text-xs">Owner: {w.owner}</span>}
      </div>
      {w.modules.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {w.modules.map((m) => (
            <li key={m} className="bg-muted/40 rounded-md border px-2 py-0.5 text-xs">
              <span className="font-mono">{m}</span>{" "}
              <span className="text-muted-foreground">{(w.patterns[m] ?? []).map(patternLabel).join(" + ")}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-xs">Foundation: environments, pipelines, data platform, observability, baseline capture.</p>
      )}
      <p className="text-sm"><span className="text-muted-foreground">Why here. </span>{w.order_reason}</p>
      <dl className="grid gap-2 text-xs md:grid-cols-2">
        <div><dt className="text-muted-foreground font-medium">Entry</dt><dd>{w.entry_criteria.join("; ") || "—"}</dd></div>
        <div><dt className="text-muted-foreground font-medium">Exit</dt><dd>{w.exit_criteria.join("; ")}</dd></div>
        <div><dt className="text-muted-foreground font-medium">Cutover window</dt><dd>{w.cutover_window || "—"}</dd></div>
        <div>
          <dt className="text-muted-foreground font-medium">Parallel run</dt>
          <dd>{w.parallel_run.required ? `${w.parallel_run.period} — ${w.parallel_run.system_of_record} stays the system of record` : "—"}</dd>
        </div>
        <div className="md:col-span-2">
          <dt className="text-muted-foreground flex items-center gap-1 font-medium"><RotateCcw className="size-3" aria-hidden /> Rollback</dt>
          <dd>When {w.rollback.trigger}: {w.rollback.method}{w.rollback.max_time ? ` (within ${w.rollback.max_time})` : ""}</dd>
        </div>
      </dl>
    </li>
  );
}

// ── criteria and baselines ──────────────────────────────────────────────────

function Criteria({ plan }: { plan: MigrationPlan }) {
  const [module, setModule] = React.useState("all-modules");
  const modules = [...new Set(plan.equivalence_criteria.map((c) => c.module_id))];
  const shown = module === "all-modules" ? plan.equivalence_criteria : plan.equivalence_criteria.filter((c) => c.module_id === module);
  return (
    <div className="space-y-3">
      <div role="group" aria-label="Filter by module" className="flex flex-wrap gap-2">
        {["all-modules", ...modules].map((m) => (
          <button key={m} type="button" aria-pressed={module === m} onClick={() => setModule(m)}
            className={cn("rounded-md border px-2.5 py-1 text-xs transition-colors",
              module === m ? "bg-primary/10 border-primary text-foreground" : "text-muted-foreground hover:bg-muted")}>
            {m === "all-modules" ? `All (${plan.equivalence_criteria.length})` : m === "all" ? "Every module" : m}
          </button>
        ))}
      </div>
      <ul className="space-y-2">{shown.map((c) => <CriterionCard key={c.id} c={c} />)}</ul>
    </div>
  );
}

function CriterionCard({ c }: { c: PlanCriterion }) {
  return (
    <li aria-label={c.id} className="space-y-1.5 rounded-lg border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{c.id}</span>
        <span className="font-medium">{c.observable}</span>
        <Badge variant="outline" className="font-normal">{c.module_id === "all" ? "every module" : c.module_id}</Badge>
        <Badge variant={c.comparison === "exact" || c.comparison === "byte_identical" ? "success" : "info"} className="font-normal">
          {COMPARISON[c.comparison] ?? c.comparison}{c.threshold ? ` — ${c.threshold}` : ""}
        </Badge>
      </div>
      <p className="text-xs"><span className="text-muted-foreground">Input set: </span>{c.input_set}</p>
      <p className="text-xs">
        <span className="text-muted-foreground">Protects: </span>
        {[...c.protects, ...c.protects_measures.map((m) => `“${m}”`)].join(", ") || "—"}
      </p>
      {c.normalization.length > 0 ? (
        <ul aria-label={`${c.id} normalization`} className="space-y-0.5 text-xs">
          {c.normalization.map((r) => (
            <li key={r.field}><span className="font-mono">{r.field}</span>: {r.rule} <span className="text-muted-foreground">— {r.reason}</span></li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-xs">No normalization: every field must match.</p>
      )}
    </li>
  );
}

function Baselines({ plan }: { plan: MigrationPlan }) {
  const late = new Set(plan.calendar_checked.filter((c) => c.ref.startsWith("baseline")).map((c) => c.ref.split(":")[1]));
  if (!plan.baseline_plan.length) return <p className="text-muted-foreground text-sm">No baselines in this plan.</p>;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-muted-foreground text-left text-xs">
          <tr>
            <th className="px-3 py-2 font-medium">Criterion</th><th className="px-3 py-2 font-medium">Inputs</th>
            <th className="px-3 py-2 font-medium">Environment</th><th className="px-3 py-2 font-medium">Data source</th>
            <th className="px-3 py-2 font-medium">Masking</th><th className="px-3 py-2 font-medium">Due</th>
          </tr>
        </thead>
        <tbody>
          {plan.baseline_plan.map((b) => (
            <tr key={b.ec_id} className="border-t align-top">
              <td className="px-3 py-2 font-mono text-xs">{b.ec_id}</td>
              <td className="px-3 py-2">{b.inputs}</td>
              <td className="px-3 py-2">{b.environment}</td>
              <td className="px-3 py-2">{b.data_source}</td>
              <td className="px-3 py-2">{b.masking}</td>
              <td className="px-3 py-2 whitespace-nowrap">
                {fmt(b.due)}
                {late.has(b.ec_id) && <Badge variant="warning" className="ml-1 font-normal">conflict</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── calendar, order, RAID, effort ───────────────────────────────────────────

function Calendar({ plan, reported }: { plan: MigrationPlan; reported: Set<string | null> }) {
  const byRef = new Map(plan.calendar_conflicts.filter((c) => c.ref).map((c) => [c.ref!, c]));
  const userRaised = plan.calendar_conflicts.filter((c) => !c.ref);
  const b = plan.brief_dates;
  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-xs">
        Checked against the brief: {b.deadline ? `deadline ${fmt(b.deadline)}` : "no dated deadline"};{" "}
        {plan.freeze_policy.from ? `legacy freeze from ${fmt(plan.freeze_policy.from)}` : "no freeze"};{" "}
        {b.downtime_window ? `cutover window “${b.downtime_window}”` : "no cutover window"}.
      </p>
      {plan.calendar_checked.length === 0 && userRaised.length === 0 && (
        <p className="flex items-center gap-2 text-sm"><CheckCircle2 className="size-4 text-emerald-600" aria-hidden /> No conflicts with the brief&apos;s calendar.</p>
      )}
      <ul className="space-y-2">
        {plan.calendar_checked.map((c) => {
          const r = byRef.get(c.ref);
          return (
            <li key={c.ref} aria-label={c.ref} className={cn("space-y-1 rounded-lg border p-3 text-sm",
              r?.resolution ? "" : "border-amber-500/40 bg-amber-500/5")}>
              <div className="flex flex-wrap items-center gap-2">
                <code className="text-xs">{c.ref}</code>
                <Badge variant={r?.resolution ? "success" : "warning"} className="font-normal">
                  {r?.resolution ? "resolved" : reported.has(c.ref) ? "reported — open" : "not reported"}
                </Badge>
              </div>
              <p>{c.conflict}</p>
              <p className="text-muted-foreground text-xs">{c.impact}</p>
              {r?.options.length ? <p className="text-xs">Options: {r.options.join("; ")}</p> : null}
              {r?.resolution && <p className="text-xs"><span className="text-muted-foreground">Decision: </span>{r.resolution}</p>}
            </li>
          );
        })}
        {userRaised.map((c) => (
          <li key={c.conflict} className="space-y-1 rounded-lg border p-3 text-sm">
            <Badge variant="outline" className="font-normal">raised in the conversation</Badge>
            <p>{c.conflict}</p>
            <p className="text-muted-foreground text-xs">{c.impact}</p>
            {c.resolution && <p className="text-xs"><span className="text-muted-foreground">Decision: </span>{c.resolution}</p>}
          </li>
        ))}
      </ul>
      {plan.critical_path.length > 0 && (
        <section aria-label="Critical path">
          <h4 className="text-sm font-semibold">Critical path</h4>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-sm">{plan.critical_path.map((s) => <li key={s}>{s}</li>)}</ol>
        </section>
      )}
    </div>
  );
}

function Order({ plan }: { plan: MigrationPlan }) {
  const o = plan.proposed_order;
  const waveOf = new Map(plan.placements.map((p) => [p.module_id, p.wave]));
  if (!o) return <p className="text-muted-foreground text-sm">The dependency-safe order was not recorded with this plan.</p>;
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs">
        The order the plan started from — dependencies first, cycles together, lowest risk first — and the wave each module
        ended up in. A wave earlier than a dependency&apos;s needs an order exception citing a design ADR.
      </p>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-muted-foreground text-left text-xs">
            <tr><th className="px-3 py-2 font-medium">Step</th><th className="px-3 py-2 font-medium">Modules</th>
              <th className="px-3 py-2 font-medium">Waits for</th><th className="px-3 py-2 font-medium">Risk</th>
              <th className="px-3 py-2 font-medium">In the plan</th></tr>
          </thead>
          <tbody>
            {o.order.map((s) => (
              <tr key={s.step} className="border-t">
                <td className="px-3 py-2 font-mono text-xs">{s.step}</td>
                <td className="px-3 py-2">
                  {s.modules.map((m, i) => `${m} ${s.names[i] ?? ""}`).join(", ")}
                  {s.cycle && <Badge variant="warning" className="ml-1 font-normal"><GitBranch className="size-3" aria-hidden /> cycle</Badge>}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{s.depends_on.join(", ") || "—"}</td>
                <td className="px-3 py-2 tabular-nums">{s.max_risk}</td>
                <td className="px-3 py-2 font-mono text-xs">{s.modules.map((m) => waveOf.get(m) ?? "—").join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {o.kept.length > 0 && <p className="text-muted-foreground text-xs">Kept as they are (move in no wave): {o.kept.join(", ")}.</p>}
    </div>
  );
}

function Raid({ plan }: { plan: MigrationPlan }) {
  const r = plan.raid;
  const empty = !r.risks.length && !r.assumptions.length && !r.issues.length && !r.dependencies.length;
  if (empty) return <p className="text-muted-foreground text-sm">No risks, assumptions, issues or dependencies recorded.</p>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section aria-label="Risks" className="rounded-lg border p-3 lg:col-span-2">
        <h4 className="text-sm font-semibold">Risks ({r.risks.length})</h4>
        <ul className="mt-2 space-y-2 text-sm">
          {r.risks.map((x) => (
            <li key={x.risk}>
              <p className="font-medium">{x.risk}</p>
              <p className="text-muted-foreground text-xs">Evidence: {x.evidence}</p>
              <p className="text-xs">Mitigation: {x.mitigation}</p>
            </li>
          ))}
        </ul>
      </section>
      {([["Assumptions", r.assumptions], ["Issues", r.issues], ["Dependencies", r.dependencies]] as const).map(([title, items]) => (
        <section key={title} aria-label={title} className="rounded-lg border p-3">
          <h4 className="text-sm font-semibold">{title} ({items.length})</h4>
          {items.length ? <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{items.map((i) => <li key={i}>{i}</li>)}</ul>
            : <p className="text-muted-foreground mt-1 text-sm">None.</p>}
        </section>
      ))}
    </div>
  );
}

function Effort({ plan }: { plan: MigrationPlan }) {
  const computed = new Map((plan.effort_table?.waves ?? []).map((w) => [w.wave, w]));
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs">
        An ESTIMATE, not a quote: person-days from a stated table (size × tier × pattern, ±30 %). A size the assessment did not
        measure is “not estimated”, never zero.
      </p>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-muted-foreground text-left text-xs">
            <tr><th className="px-3 py-2 font-medium">Wave</th><th className="px-3 py-2 font-medium">In the plan</th>
              <th className="px-3 py-2 font-medium">From the table</th><th className="px-3 py-2 font-medium">Basis</th></tr>
          </thead>
          <tbody>
            {plan.effort.map((e) => (
              <tr key={e.wave} className="border-t align-top">
                <td className="px-3 py-2 font-mono text-xs">{e.wave}</td>
                <td className="px-3 py-2">{e.band}</td>
                <td className="px-3 py-2">{computed.get(e.wave)?.band ?? "—"}</td>
                <td className="text-muted-foreground px-3 py-2 text-xs">{e.basis}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {plan.effort_table && <p className="text-sm">Total from the table: {plan.effort_table.total_band}.</p>}
      {plan.budget_fit && <p className="text-sm"><span className="text-muted-foreground">Budget: </span>{plan.budget_fit}</p>}
    </div>
  );
}

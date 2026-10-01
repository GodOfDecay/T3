"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FlaskConical, ListOrdered, Loader2, ShieldCheck, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getCaptures } from "@/lib/api/modernization";
import { getLedger, stateLabel } from "@/lib/api/modernization-programme";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";
import type { Baseline, Capture } from "@/lib/schemas/modernization";

/**
 * A recorded baseline (Track 3, Equivalence Testing — Baseline mode), for QA who accepts it and for
 * Migration Development, which builds against it.
 *
 * The questions a reviewer asks: WHAT was recorded for each criterion (how many cases, fingerprinted
 * how), under WHICH conditions (the capture: commit, image, synthetic data, stubs), WHAT varies on its
 * own between two runs of the unchanged system and how each such field is handled (a rule, or a
 * proposal to Migration Strategy), and what could NOT be captured. The recordings never leave the
 * sandbox store: this page shows counts, hashes, field names and masked shapes ("<timestamp>") only.
 */

const STATUS_WORD: Record<string, string> = {
  published: "approved", granted: "approved by exception", draft: "not yet approved",
};

export function EquivalenceView({ baseline, projectId, approved, status }: {
  baseline: Baseline;
  projectId?: ProjectId;
  approved?: boolean;
  status?: string;
}) {
  const recorded = new Set(baseline.baselines.flatMap((b) => b.ec_ids));
  const modules = [...new Set(baseline.baselines.map((b) => b.module_id).filter((m) => m !== "all"))];
  const varying = new Set(baseline.noise.flatMap((n) => n.varying_fields));
  return (
    <div className="space-y-6">
      <section aria-label="Baseline summary" className="space-y-3">
        <Sources baseline={baseline} />
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Baselines" value={baseline.baselines.length} />
          <Stat label="Criteria recorded" value={recorded.size} />
          <Stat label="Modules" value={modules.join(", ") || "—"} small />
          <Stat label="Fields varying between runs" value={varying.size} />
          <Stat label="Rules proposed" value={baseline.rule_proposals.length} emphasis={baseline.rule_proposals.length > 0} />
          <Stat label="Not captured" value={baseline.not_captured.length} emphasis={baseline.not_captured.length > 0} />
        </dl>
        <CaptureLine baseline={baseline} />
        {baseline.notes.length > 0 && (
          <ul role="status" aria-label="Notes" className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
            {baseline.notes.map((n) => (
              <li key={n} className="flex gap-2">
                <AlertTriangle className="size-3.5 shrink-0 text-amber-600" aria-hidden />
                <span>{n}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {projectId && <BaselineLedger projectId={projectId} baseline={baseline} approved={!!approved} status={status} />}

      <Tabs defaultValue="baselines">
        <TabsList className="flex-wrap">
          <TabsTrigger value="baselines">Baselines ({baseline.baselines.length})</TabsTrigger>
          <TabsTrigger value="scenarios">Scenarios ({baseline.scenarios.length})</TabsTrigger>
          <TabsTrigger value="noise">Noise floor ({baseline.noise.length})</TabsTrigger>
          <TabsTrigger value="proposals">Proposed rules ({baseline.rule_proposals.length})</TabsTrigger>
          <TabsTrigger value="not-captured">Not captured ({baseline.not_captured.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="baselines" className="mt-4"><Baselines baseline={baseline} /></TabsContent>
        <TabsContent value="scenarios" className="mt-4"><Scenarios baseline={baseline} /></TabsContent>
        <TabsContent value="noise" className="mt-4"><Noise baseline={baseline} /></TabsContent>
        <TabsContent value="proposals" className="mt-4"><Proposals baseline={baseline} /></TabsContent>
        <TabsContent value="not-captured" className="mt-4"><NotCaptured baseline={baseline} /></TabsContent>
      </Tabs>
    </div>
  );
}

function Sources({ baseline }: { baseline: Baseline }) {
  const label = (key: "plan" | "design", noun: string) => {
    const s = baseline.sources[key];
    return s?.version != null ? `${noun} v${s.version} (${STATUS_WORD[s.status ?? ""] ?? s.status})` : null;
  };
  const parts = [label("plan", "Migration plan"), label("design", "Target design")].filter(Boolean);
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {baseline.system_name && <span className="text-foreground font-medium">{baseline.system_name}</span>}
      {parts.length ? parts.map((p) => <span key={p}>{p}</span>) : <span>From the Orchestrator conversation</span>}
      {baseline.recorded_at && <span>Recorded {new Date(baseline.recorded_at).toLocaleString()}</span>}
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

function CaptureLine({ baseline }: { baseline: Baseline }) {
  const c = baseline.capture;
  if (!c.id) return null;
  return (
    <p aria-label="Capture" className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <ShieldCheck className="size-3.5 text-emerald-600" aria-hidden />
      <span>Capture <span className="font-mono">{c.id}</span></span>
      {c.commit && <span>commit <span className="font-mono">{c.commit.slice(0, 10)}</span></span>}
      {c.imageId && <span>image <span className="font-mono">{c.imageId.slice(0, 19)}</span></span>}
      {c.profileSource && <span>{c.profileSource}</span>}
      <span>Run twice in an isolated sandbox — no internet, synthetic data
        {baseline.stubs.length > 0 && `, stubs for ${baseline.stubs.join(", ")}`}.</span>
    </p>
  );
}

// ── the ledger ──────────────────────────────────────────────────────────────

export function baselineLedgerText(approved: boolean, status: string | undefined, count: number): string {
  if (approved) return "This baseline is accepted: its modules are baselined on the migration ledger. Where each one is now:";
  if (status === "rejected") return "This version was rejected, so it cannot be accepted and does not change the ledger.";
  if (status === "superseded") return "A newer baseline has been accepted since; the ledger follows that one. Where each module is now:";
  return `Accepting this version marks these ${count} modules baselined on the migration ledger — Migration Development starts from it.`;
}

function BaselineLedger({ projectId, baseline, approved, status }: {
  projectId: ProjectId; baseline: Baseline; approved: boolean; status?: string;
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
      <p className="text-muted-foreground mt-1 text-xs">{baselineLedgerText(approved, status, baseline.placements.length)}</p>
      {q.isError && <p className="text-muted-foreground mt-1 text-xs">The ledger could not be loaded.</p>}
      <ul className="mt-2 flex flex-wrap gap-2">
        {baseline.placements.map((p) => {
          const row = rows.get(p.module_id);
          return (
            <li key={p.module_id} className="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs">
              <span className="font-mono">{p.module_id}</span>
              <span className="text-muted-foreground">{p.baseline_ids.join(", ")}</span>
              {row ? (
                <Badge variant={row.state === "blocked" ? "danger" : "info"} className="font-normal">{stateLabel(row.state)}</Badge>
              ) : (
                <Badge variant="outline" className="font-normal">not on the ledger</Badge>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ── tabs ────────────────────────────────────────────────────────────────────

function Baselines({ baseline }: { baseline: Baseline }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm" aria-label="Baselines">
        <thead className="text-muted-foreground text-xs">
          <tr><th className="py-1 pr-3">Baseline</th><th className="pr-3">Module</th><th className="pr-3">Criteria</th>
            <th className="pr-3 text-right">Recorded</th><th className="pr-3">Fingerprint (sha256)</th><th className="pr-3">Region</th>
            <th>Varies between runs</th></tr>
        </thead>
        <tbody>
          {baseline.baselines.map((b) => (
            <tr key={b.id} className="border-t align-top">
              <td className="py-1.5 pr-3 font-mono">{b.id}</td>
              <td className="pr-3">{b.module_id === "all" ? "All modules" : b.module_id}</td>
              <td className="pr-3">{b.ec_ids.join(", ")}</td>
              <td className="pr-3 text-right tabular-nums">{b.count} {b.unit}</td>
              <td className="pr-3 font-mono text-xs" title={b.sha256}>{b.sha256.slice(0, 16)}…</td>
              <td className="pr-3">{b.region}</td>
              <td className="text-xs">{b.noise_fields.length ? b.noise_fields.join(", ") : "nothing — fully repeatable"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Scenarios({ baseline }: { baseline: Baseline }) {
  const criteriaOf = (sid: string) => Object.entries(baseline.mapping).filter(([, s]) => s.includes(sid)).map(([ec]) => ec);
  return (
    <ul className="space-y-3">
      {baseline.scenarios.map((s) => {
        const fields = Object.entries(s.varying);
        const ecs = criteriaOf(s.id);
        return (
          <li key={s.id} aria-label={`Scenario ${s.id}`} className="rounded-lg border p-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <FlaskConical className="text-muted-foreground size-4" aria-hidden />
              <span className="font-medium">{s.id}</span>
              <Badge variant="outline" className="font-normal">{s.kind === "http" ? "HTTP requests" : "Batch run"}</Badge>
              {s.cases != null && <span className="text-muted-foreground text-xs">{s.cases} case{s.cases === 1 ? "" : "s"}</span>}
              <span className="text-muted-foreground text-xs">
                {ecs.length ? `records ${ecs.join(", ")}` : "recorded, not used by any criterion"}
              </span>
            </div>
            {s.describes && <p className="text-muted-foreground mt-1 text-xs">{s.describes}</p>}
            {fields.length > 0 ? (
              <ul className="mt-2 space-y-0.5 text-xs">
                {fields.map(([f, n]) => (
                  <li key={f}>
                    <span className="font-mono">{f}</span> differed in {n} case{n === 1 ? "" : "s"}
                    {s.examples[f] && <span className="text-muted-foreground"> — {s.examples[f][0]} vs {s.examples[f][1]}</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-400">Identical in both runs.</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Noise({ baseline }: { baseline: Baseline }) {
  const proposed = new Set(baseline.rule_proposals.map((p) => `${p.ec_id}|${p.field}`));
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs">
        Fields that differed between two runs of the UNCHANGED legacy system cannot be compared as they are. Each is
        covered by the criterion&apos;s own normalization rule, or proposed to Migration Strategy — this agent never
        applies a rule itself.
      </p>
      <table className="w-full text-left text-sm" aria-label="Noise floor">
        <thead className="text-muted-foreground text-xs">
          <tr><th className="py-1 pr-3">Criterion</th><th className="pr-3">Field</th><th>Handled by</th></tr>
        </thead>
        <tbody>
          {baseline.noise.flatMap((n) => n.varying_fields.length === 0
            ? [<tr key={n.ec_id} className="border-t"><td className="py-1.5 pr-3">{n.ec_id}</td>
                <td className="pr-3 text-xs" colSpan={2}>nothing varies</td></tr>]
            : n.varying_fields.map((f) => {
              const covered = n.covered_by_rule.includes(f);
              const isProposed = proposed.has(`${n.ec_id}|${f}`);
              return (
                <tr key={`${n.ec_id}-${f}`} className="border-t">
                  <td className="py-1.5 pr-3">{n.ec_id}</td>
                  <td className="pr-3 font-mono text-xs">{f}</td>
                  <td className="text-xs">
                    {covered ? (
                      <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                        <CheckCircle2 className="size-3.5" aria-hidden /> the criterion&apos;s rule
                      </span>
                    ) : isProposed ? (
                      <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                        <AlertTriangle className="size-3.5" aria-hidden /> proposed to Migration Strategy — open until the plan is revised
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-700 dark:text-red-400">
                        <XCircle className="size-3.5" aria-hidden /> nothing
                      </span>
                    )}
                  </td>
                </tr>
              );
            }))}
        </tbody>
      </table>
    </div>
  );
}

function Proposals({ baseline }: { baseline: Baseline }) {
  if (!baseline.rule_proposals.length) {
    return <p className="text-muted-foreground text-sm">No rule needed: every varying field is covered by a criterion&apos;s own rule.</p>;
  }
  return (
    <ul className="space-y-2">
      {baseline.rule_proposals.map((p) => (
        <li key={`${p.ec_id}-${p.field}`} className="rounded-lg border border-amber-500/40 p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warning" className="font-normal">{p.ec_id}</Badge>
            <span className="font-mono text-xs">{p.field}</span>
          </div>
          <p className="mt-1">{p.rule}</p>
          {p.evidence && <p className="text-muted-foreground mt-1 text-xs">Evidence: {p.evidence}</p>}
        </li>
      ))}
    </ul>
  );
}

function NotCaptured({ baseline }: { baseline: Baseline }) {
  if (!baseline.not_captured.length) return <p className="text-muted-foreground text-sm">Every criterion of these modules was recorded.</p>;
  return (
    <ul className="space-y-1 text-sm">
      {baseline.not_captured.map((n) => (
        <li key={n.ec_id}><span className="font-medium">{n.ec_id}</span> — {n.reason}</li>
      ))}
    </ul>
  );
}

// ── captures ────────────────────────────────────────────────────────────────

export function CapturesButton({ projectId }: { projectId: ProjectId }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <FlaskConical className="size-4" aria-hidden />
        Captures
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Captures</DialogTitle>
            <DialogDescription>
              Each time the legacy system was run in the sandbox to record a baseline. A capture becomes a baseline only
              when it is recorded, and counts only once the baseline version is accepted. Recordings never leave the
              sandbox store.
            </DialogDescription>
          </DialogHeader>
          {open && <CapturesPanel projectId={projectId} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

export function CapturesPanel({ projectId }: { projectId: ProjectId }) {
  const q = useQuery({
    queryKey: qk.modernizationProgramme.captures(projectId),
    queryFn: () => getCaptures(projectId),
    refetchInterval: (query) => (query.state.data?.captures.some((c) => c.status === "running") ? 5000 : false),
  });
  if (q.isLoading) return <LoadingState variant="card" />;
  if (q.isError || !q.data) {
    return <ErrorState title="The captures could not be loaded" description={q.error instanceof Error ? q.error.message : ""}
      onRetry={() => q.refetch()} />;
  }
  if (!q.data.captures.length) {
    return <p className="text-muted-foreground text-sm">No capture yet — ask the Equivalence Testing agent to capture a baseline.</p>;
  }
  return <ul className="space-y-2">{q.data.captures.map((c) => <CaptureRow key={c.id} c={c} />)}</ul>;
}

function CaptureRow({ c }: { c: Capture }) {
  const cases = c.scenarios.reduce((n, s) => n + (s.cases ?? 0), 0);
  return (
    <li aria-label={`Capture ${c.id}`} className="rounded-lg border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{c.id}</span>
        {c.status === "running" && (
          <Badge variant="info" className="gap-1 font-normal"><Loader2 className="size-3 animate-spin" aria-hidden /> in progress</Badge>
        )}
        {c.status === "complete" && (
          <Badge variant={c.keep ? "success" : "outline"} className="font-normal">
            {c.keep ? "recorded as a baseline" : "complete — not recorded yet"}
          </Badge>
        )}
        {c.status === "failed" && <Badge variant="danger" className="font-normal">failed — nothing recorded, nothing accepted</Badge>}
        {c.planVersion != null && <span className="text-muted-foreground text-xs">plan v{c.planVersion}</span>}
        {c.startedAt && <span className="text-muted-foreground text-xs">{new Date(c.startedAt).toLocaleString()}</span>}
      </div>
      {c.status === "running" && (
        <p className="text-muted-foreground mt-1 text-xs">The legacy system is running in the sandbox, twice; this updates when it finishes.</p>
      )}
      {c.status === "failed" && c.error && <p className="mt-1 text-xs text-red-700 dark:text-red-400">{c.error}</p>}
      <p className="text-muted-foreground mt-1 text-xs">
        {c.scenarios.length} scenario{c.scenarios.length === 1 ? "" : "s"}, {cases} case{cases === 1 ? "" : "s"}
        {Object.keys(c.mapping).length > 0 && ` · ${Object.keys(c.mapping).sort().join(", ")}`}
      </p>
    </li>
  );
}

"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ListOrdered } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { getLedger, stateLabel } from "@/lib/api/modernization-programme";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";
import type { Verification } from "@/lib/schemas/modernization";

/**
 * One module's verification (Track 3, Equivalence Testing Verify mode — Phase J), for the QA who accepts it.
 *
 * The questions: which head and which baseline were replayed; per criterion, passed / failed / open / NOT RUN
 * (never shown as passed); every difference with its kind (a regression fails, a normalization gap is a
 * proposal to Migration Strategy, an environment difference wants a rerun, an accepted change cites its ADR),
 * how many cases, the masked shape and the likely code area; performance on BOTH sides against the threshold,
 * "not measured" never 0 (R39). Accepting writes the module's verdict on the ledger.
 */

const VERDICT_VARIANT: Record<Verification["criteria"][number]["verdict"], "success" | "danger" | "warning" | "outline"> = {
  passed: "success", failed: "danger", open: "warning", not_run: "outline",
};
const MODULE: Record<Verification["module_verdict"], { label: string; variant: "success" | "danger" | "warning" }> = {
  verified: { label: "verified", variant: "success" },
  migrating: { label: "fails — back to Migration Development", variant: "danger" },
  open: { label: "open — not every criterion settled", variant: "warning" },
};

export function ms(v: number | null): string {
  return v === null ? "not measured" : `${v} ms`;
}

/** What accepting this verification does, or did. */
export function verificationLedgerText(v: Verification, approved: boolean, status: string | undefined, state?: string): string {
  if (status === "rejected") return "This verification was rejected: it records nothing on the ledger.";
  if (status === "superseded") return "A newer verification of this module has been accepted since; the ledger follows that one.";
  if (!approved) {
    const what = v.module_verdict === "verified" ? `records ${v.module_id} as verified (ready for Cutover)`
      : v.module_verdict === "migrating" ? `sends ${v.module_id} back to Migration Development with the differences`
        : `records the result; ${v.module_id} stays verifying until every criterion is settled`;
    return `QA who did not run it, or a Project Admin, accepts it here; accepting ${what}. A verification of an older migration record is refused.`;
  }
  if (state === "verified") return "Accepted: the module is verified.";
  if (state === "migrating") return "Accepted: the module is back with Migration Development for rework.";
  return `Accepted and recorded${state ? `; the module is ${stateLabel(state).toLowerCase()}` : ""}.`;
}

function Ledger({ projectId, v, approved, status }: { projectId: ProjectId; v: Verification; approved: boolean; status?: string }) {
  const q = useQuery({ queryKey: qk.modernizationProgramme.ledger(projectId), queryFn: () => getLedger(projectId) });
  const { refetch } = q;
  React.useEffect(() => {
    if (approved) void refetch();
  }, [approved, refetch]);
  const row = (q.data?.modules ?? []).find((r) => r.moduleId === v.module_id);
  return (
    <section aria-label="Module ledger" className="rounded-lg border p-3">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <ListOrdered className="text-muted-foreground size-4" aria-hidden /> Module ledger
      </h3>
      <p className="text-muted-foreground mt-1 text-xs">{verificationLedgerText(v, approved, status, row?.state)}</p>
      {row && <Badge variant="info" className="mt-2 font-normal">{v.module_id} · {stateLabel(row.state)}</Badge>}
    </section>
  );
}

export function VerificationView({ verification, projectId, approved, status }: {
  verification: Verification; projectId?: ProjectId; approved?: boolean; status?: string;
}) {
  const v = verification;
  const m = MODULE[v.module_verdict];
  return (
    <div className="space-y-6">
      <section aria-label="Verification summary" className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-base font-semibold">{v.module_id} {v.module.name ?? ""}</span>
          <Badge variant={m.variant} className="font-normal">{m.label}</Badge>
          {/^https?:\/\//.test(v.pr) && <a href={v.pr} target="_blank" rel="noreferrer" className="text-primary text-sm underline">Pull request</a>}
        </div>
        <p className="text-muted-foreground text-xs">
          Head <span className="font-mono">{(v.head_sha ?? "").slice(0, 10)}</span> (migration record v{v.migration_version ?? "?"}),
          overlaid on the legacy system and run {v.runs} times, against baseline v{v.baseline_version ?? "?"}
          {v.baselines_replayed.length > 0 && <> ({v.baselines_replayed.map((b) => b.id).join(", ")})</>}.
        </p>
      </section>

      {projectId && <Ledger projectId={projectId} v={v} approved={!!approved} status={status} />}

      <table className="w-full text-left text-sm" aria-label="Criteria">
        <thead className="text-muted-foreground text-xs">
          <tr><th className="py-1 pr-3">Criterion</th><th className="pr-3">Verdict</th><th className="pr-3">Cases</th><th>Normalization applied</th></tr>
        </thead>
        <tbody>
          {v.criteria.map((c) => (
            <tr key={c.ec_id} className="border-t">
              <td className="py-1 pr-3 font-mono text-xs">{c.ec_id}</td>
              <td className="pr-3"><Badge variant={VERDICT_VARIANT[c.verdict]} className="font-normal">{c.verdict.replace("_", " ")}</Badge></td>
              <td className="pr-3">{c.cases_compared ?? "—"}</td>
              <td className="text-muted-foreground text-xs">{c.normalization_applied.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {v.performance.length > 0 && (
        <table className="w-full text-left text-sm" aria-label="Performance">
          <thead className="text-muted-foreground text-xs">
            <tr><th className="py-1 pr-3">Criterion</th><th className="pr-3">Legacy p95</th><th className="pr-3">Target p95</th><th>Threshold</th></tr>
          </thead>
          <tbody>
            {v.performance.map((p) => (
              <tr key={p.ec_id} className="border-t">
                <td className="py-1 pr-3 font-mono text-xs">{p.ec_id}</td>
                <td className="pr-3">{ms(p.legacy_p95_ms)}</td>
                <td className={cn("pr-3", p.target_p95_ms !== null && p.target_p95_ms > p.threshold_ms && "text-red-600 dark:text-red-400")}>
                  {ms(p.target_p95_ms)}
                </td>
                <td>{p.threshold_ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <section aria-label="Differences" className="space-y-2">
        <h3 className="text-sm font-medium">Differences ({v.differences.length})</h3>
        {v.differences.length === 0 ? (
          <p className="text-muted-foreground text-sm">No difference after each criterion&apos;s own normalization.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {v.differences.map((d) => (
              <li key={d.id} className="rounded-lg border p-2">
                <span className="font-mono text-xs">{d.id}</span>{" "}
                <Badge variant={d.classification === "regression" ? "danger" : d.classification === "accepted_change" ? "outline" : "warning"}
                  className="font-normal">{d.classification.replace("_", " ")}</Badge>{" "}
                <span className="font-mono text-xs">{d.field}</span> in {d.cases} case(s) — <span className="font-mono text-xs">{d.masked_example}</span>
                <span className="text-muted-foreground block text-xs">
                  {d.ec_id}{d.likely_area ? ` · likely ${d.likely_area}` : ""}{d.adr_id ? ` · allowed by ${d.adr_id}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        {v.rule_proposals.length > 0 && (
          <p className="text-muted-foreground text-xs">
            Proposed to Migration Strategy (never applied here): {v.rule_proposals.map((r) => `${r.ec_id} ${r.field}`).join("; ")}.
          </p>
        )}
      </section>
    </div>
  );
}

"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ListOrdered, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getLedger, stateLabel, type LedgerModule } from "@/lib/api/modernization-programme";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";
import type { MigrationReview, ModernizationSecurity } from "@/lib/schemas/modernization";

/**
 * One module's migration review and security report (Track 3 — Phase I), for the Architect and the
 * Security Engineer who accept them.
 *
 * A reviewer's questions: is the recommendation backed by findings that cite BOTH sides (target file and
 * line, legacy file and line); is every frozen contract, trap, criterion and legacy file answered; what
 * did the deterministic API diff and anti-pattern scan find; which files were actually OPENED. A security
 * reader's: which scanners ran (one that did not is "not scanned", never clean or 0), what each finding's
 * origin is (carried over from the legacy, introduced by the migration), what the migration fixed, whether
 * a legacy secret reached the target, and whether each contract's authorization is as strict as before.
 *
 * Accepting a version is what writes the verdict on the migration ledger (I11): the panel says what
 * accepting does before it is done, and what the ledger shows after.
 */

const SEV_VARIANT: Record<string, "danger" | "warning" | "info" | "outline"> = {
  critical: "danger", high: "danger", medium: "warning", low: "info", info: "outline",
};
const SEV_ORDER = ["critical", "high", "medium", "low", "info"];
const REC: Record<MigrationReview["merge_recommendation"], { label: string; variant: "success" | "danger" | "warning" }> = {
  approve: { label: "Approve", variant: "success" },
  request_changes: { label: "Request changes", variant: "danger" },
  needs_discussion: { label: "Needs discussion", variant: "warning" },
};
const VERDICT: Record<ModernizationSecurity["verdict"], { variant: "success" | "danger" | "warning"; icon: typeof ShieldCheck }> = {
  PASS: { variant: "success", icon: ShieldCheck },
  CONDITIONAL: { variant: "warning", icon: ShieldQuestion },
  FAIL: { variant: "danger", icon: ShieldAlert },
};

function words(s: string): string {
  return s.replace(/_/g, " ");
}

export function severityCounts(findings: { severity: string }[]): string {
  const parts = SEV_ORDER.map((s) => [s, findings.filter((f) => f.severity === s).length] as const).filter(([, n]) => n > 0);
  return parts.length ? parts.map(([s, n]) => `${n} ${s}`).join(", ") : "no findings";
}

/** What accepting this version does, or did — for the review ("review") or the security report ("security"). */
export function verdictLedgerText(kind: "review" | "security", verdict: string, approved: boolean, status: string | undefined,
  row?: Pick<LedgerModule, "state" | "reviewVerdict" | "securityVerdict"> | null): string {
  const noun = kind === "review" ? "review" : "security report";
  if (status === "rejected") return `This ${noun} was rejected: it records nothing on the ledger.`;
  if (status === "superseded") return `A newer ${noun} for this module has been accepted since; the ledger follows that one.`;
  const good = kind === "review" ? verdict === "approve" : verdict === "PASS" || verdict === "CONDITIONAL";
  const bad = kind === "review" ? verdict === "request_changes" : verdict === "FAIL";
  if (!approved) {
    const who = kind === "review" ? "An Architect who did not submit it, or a Project Admin," : "A Security Engineer who did not submit it, or a Project Admin,";
    const then = good
      ? "With the other sign-off also good, the module goes to Equivalence Testing (verifying)."
      : bad ? "The module goes back to Migration Development with the findings (blocked after three rejections)."
        : "It is recorded as needing discussion; the module stays in review.";
    return `${who} accepts it here; accepting records "${words(verdict)}" on the migration ledger. ${then} A ${noun} of an older migration record is refused.`;
  }
  const other = kind === "review" ? row?.securityVerdict : row?.reviewVerdict;
  if (row?.state === "verifying") return "Accepted. Both sign-offs are good: the module is with Equivalence Testing (verifying).";
  if (row?.state === "migrating") return "Accepted. The module is back with Migration Development for rework.";
  if (row?.state === "blocked") return "Accepted. The module was rejected three times and is blocked: the Architect decides.";
  return `Accepted and recorded. ${other ? `The other sign-off says ${words(other)}.` : `Waiting for ${kind === "review" ? "Security" : "Migration Review"}.`}`;
}

function LedgerPanel({ projectId, moduleId, kind, verdict, approved, status }: {
  projectId: ProjectId; moduleId: string; kind: "review" | "security"; verdict: string; approved: boolean; status?: string;
}) {
  const q = useQuery({ queryKey: qk.modernizationProgramme.ledger(projectId), queryFn: () => getLedger(projectId) });
  const { refetch } = q;
  React.useEffect(() => {
    if (approved) void refetch();
  }, [approved, refetch]);
  const row = (q.data?.modules ?? []).find((r) => r.moduleId === moduleId);
  return (
    <section aria-label="Module ledger" className="rounded-lg border p-3">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <ListOrdered className="text-muted-foreground size-4" aria-hidden /> Module ledger
      </h3>
      <p className="text-muted-foreground mt-1 text-xs">{verdictLedgerText(kind, verdict, approved, status, row)}</p>
      {q.isError && <p className="text-muted-foreground mt-1 text-xs">The ledger could not be loaded.</p>}
      {row && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono">{moduleId}</span>
          <Badge variant={row.state === "blocked" ? "danger" : "info"} className="font-normal">{stateLabel(row.state)}</Badge>
          <span className="text-muted-foreground">review: {row.reviewVerdict ? words(row.reviewVerdict) : "not yet"}</span>
          <span className="text-muted-foreground">security: {row.securityVerdict ?? "not yet"}</span>
          {(row.rejectionCount ?? 0) > 0 && <span className="text-muted-foreground">rejected {row.rejectionCount} of 3</span>}
        </div>
      )}
    </section>
  );
}

function PrLink({ pr }: { pr: string }) {
  return /^https?:\/\//.test(pr) ? (
    <a href={pr} target="_blank" rel="noreferrer" className="text-primary underline">Pull request</a>
  ) : (
    <span className="text-muted-foreground">Pull request: <span className="font-mono">{pr}</span></span>
  );
}

function Stat({ label, value, emphasis }: { label: string; value: React.ReactNode; emphasis?: boolean }) {
  return (
    <div className="rounded-lg border p-2">
      <dt className="text-muted-foreground text-[11px]">{label}</dt>
      <dd className={cn("text-sm font-semibold", emphasis && "text-red-600 dark:text-red-400")}>{value}</dd>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-muted-foreground text-sm">{children}</p>;
}

function where(file: string | null, line: number | null): string {
  return file ? (line ? `${file}:${line}` : file) : "—";
}

// ── Migration Review ────────────────────────────────────────────────────────

export function ReviewView({ review, projectId, approved, status }: {
  review: MigrationReview; projectId?: ProjectId; approved?: boolean; status?: string;
}) {
  const r = review;
  const rec = REC[r.merge_recommendation];
  const sorted = [...r.findings].sort((a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity));
  const contractChanges = Object.values(r.surface.contracts ?? {}).reduce((n, c) => n + c.length, 0);
  return (
    <div className="space-y-6">
      <section aria-label="Review summary" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-base font-semibold">{r.module_id} {r.module.name ?? ""}</span>
          <Badge variant={rec.variant} className="font-normal">{rec.label}</Badge>
          {r.pr && <PrLink pr={r.pr} />}
        </div>
        <p className="text-muted-foreground text-xs">
          Reviewed head <span className="font-mono">{(r.head_sha ?? "").slice(0, 10)}</span> (migration record v{r.migration_version ?? "?"})
          side by side with the legacy code at <span className="font-mono">{(r.legacy_commit ?? "").slice(0, 10) || "—"}</span>.
        </p>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Findings" value={severityCounts(r.findings)} emphasis={r.findings.some((f) => f.severity === "critical" || f.severity === "high")} />
          <Stat label="Contracts changed" value={r.contract_check.filter((c) => c.status === "changed").length} />
          <Stat label="Traps not handled" value={r.trap_check.filter((t) => t.status === "not_handled").length}
            emphasis={r.trap_check.some((t) => t.status === "not_handled")} />
          <Stat label="Legacy files missing" value={r.traceability.filter((t) => t.status === "missing").length} />
          <Stat label="Files read" value={`${r.files_read.target.length} target · ${r.files_read.legacy.length} legacy`} />
        </dl>
        {r.summary && <p className="whitespace-pre-wrap text-sm">{r.summary}</p>}
      </section>

      {projectId && <LedgerPanel projectId={projectId} moduleId={r.module_id} kind="review" verdict={r.merge_recommendation}
        approved={!!approved} status={status} />}

      <Tabs defaultValue="findings">
        <TabsList className="flex-wrap">
          <TabsTrigger value="findings">Findings ({r.findings.length})</TabsTrigger>
          <TabsTrigger value="checks">Contracts and traps ({r.contract_check.length + r.trap_check.length})</TabsTrigger>
          <TabsTrigger value="criteria">Criteria ({r.equivalence_coverage.length})</TabsTrigger>
          <TabsTrigger value="trace">Traceability ({r.traceability.length})</TabsTrigger>
          <TabsTrigger value="surface">API diff ({contractChanges})</TabsTrigger>
          <TabsTrigger value="anti">Anti-patterns ({r.antipatterns.target?.length ?? 0})</TabsTrigger>
        </TabsList>
        <TabsContent value="findings" className="mt-4">
          {sorted.length === 0 ? <Empty>No findings.</Empty> : (
            <ul aria-label="Findings" className="space-y-3">
              {sorted.map((f) => (
                <li key={f.id} className="rounded-lg border p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{f.id}</span>
                    <Badge variant={SEV_VARIANT[f.severity]} className="font-normal">{f.severity}</Badge>
                    <span className="text-muted-foreground text-xs">{words(f.category)}</span>
                    {f.refs.length > 0 && <span className="text-muted-foreground text-xs">{f.refs.join(", ")}</span>}
                  </div>
                  <p className="mt-1">{f.description}</p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    Target <span className="font-mono">{where(f.file, f.line)}</span>
                    {f.legacy_file && <> · legacy <span className="font-mono">{where(f.legacy_file, f.legacy_line)}</span></>}
                  </p>
                  <p className="mt-1 text-xs"><span className="font-medium">Recommendation:</span> {f.recommendation}</p>
                </li>
              ))}
            </ul>
          )}
          {r.known_debt.length > 0 && (
            <div className="mt-4">
              <h4 className="text-sm font-medium">Known debt carried over (kept on purpose)</h4>
              <ul aria-label="Known debt" className="text-muted-foreground mt-1 space-y-1 text-xs">
                {r.known_debt.map((d) => <li key={d.pattern + d.legacy_file}>{d.pattern} — <span className="font-mono">{d.legacy_file}</span> {d.note}</li>)}
              </ul>
            </div>
          )}
        </TabsContent>
        <TabsContent value="checks" className="mt-4 space-y-3">
          <CheckTable label="Frozen contracts" rows={r.contract_check.map((c) => [c.ct_id, c.status, c.note])} bad="changed" />
          <CheckTable label="Traps" rows={r.trap_check.map((t) => [t.tr_id, t.status, t.where])} bad="not_handled" />
        </TabsContent>
        <TabsContent value="criteria" className="mt-4">
          <CheckTable label="Equivalence criteria" rows={r.equivalence_coverage.map((e) => [e.ec_id, e.status, e.note])} bad="not_addressed" />
        </TabsContent>
        <TabsContent value="trace" className="mt-4">
          <CheckTable label="Legacy traceability" rows={r.traceability.map((t) => [t.legacy_path, t.status, t.target_path ?? ""])} bad="missing" mono />
        </TabsContent>
        <TabsContent value="surface" className="mt-4 space-y-2">
          <p className="text-muted-foreground text-xs">
            Computed from the code, not stated: {r.surface.legacy_count ?? 0} legacy entries, {r.surface.target_count ?? 0} target entries
            (routes, methods, status codes, public functions, SQL, file formats).
          </p>
          {Object.entries(r.surface.contracts ?? {}).map(([ct, changes]) => (
            <div key={ct} className="rounded-lg border p-2 text-sm">
              <span className="font-mono text-xs">{ct}</span>{" "}
              {changes.length === 0 ? <span className="text-muted-foreground">no change found in its file</span> : (
                <ul aria-label={`${ct} changes`} className="mt-1 space-y-1 text-xs">
                  {changes.map((c) => (
                    <li key={`${c.change}${c.kind}${c.name}`}>
                      <Badge variant={c.change === "removed" ? "danger" : "info"} className="font-normal">{c.change}</Badge>{" "}
                      {words(c.kind)} <span className="font-mono">{c.name}</span> <span className="text-muted-foreground">({c.location})</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </TabsContent>
        <TabsContent value="anti" className="mt-4">
          {(r.antipatterns.target ?? []).length === 0 ? <Empty>No legacy anti-pattern in the migrated module.</Empty> : (
            <ul aria-label="Anti-patterns" className="space-y-1 text-sm">
              {(r.antipatterns.target ?? []).map((h) => (
                <li key={`${h.rule}${h.file}${h.line}`}>
                  <Badge variant={SEV_VARIANT[h.severity]} className="font-normal">{h.severity}</Badge> {h.title}{" "}
                  <span className="font-mono text-xs">{h.file}:{h.line}</span>{" "}
                  <span className="text-muted-foreground text-xs">{words(h.origin ?? "")}</span>
                </li>
              ))}
            </ul>
          )}
          {(r.antipatterns.fixed ?? []).length > 0 && (
            <p className="text-muted-foreground mt-3 text-xs">
              Fixed by the migration: {(r.antipatterns.fixed ?? []).map((h) => `${h.title} (${h.file}:${h.line})`).join("; ")}.
            </p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function CheckTable({ label, rows, bad, mono }: { label: string; rows: [string, string, string][]; bad: string; mono?: boolean }) {
  if (rows.length === 0) return <Empty>No {label.toLowerCase()} on this module.</Empty>;
  return (
    <table className="w-full text-left text-sm" aria-label={label}>
      <thead className="text-muted-foreground text-xs">
        <tr><th className="py-1 pr-3">{label}</th><th className="pr-3">Status</th><th>Where / note</th></tr>
      </thead>
      <tbody>
        {rows.map(([id, st, note]) => (
          <tr key={id} className="border-t">
            <td className={cn("py-1 pr-3", mono && "font-mono text-xs")}>{id}</td>
            <td className="pr-3"><Badge variant={st === bad ? "danger" : "outline"} className="font-normal">{words(st)}</Badge></td>
            <td className="text-muted-foreground text-xs">{note || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Security ────────────────────────────────────────────────────────────────

/** A count that was never measured is "not scanned" / "not generated", never 0 (R39). */
export function sbomText(sbom: ModernizationSecurity["sbom"]): string {
  const c = sbom.components === null ? "SBOM not generated" : `${sbom.components} components`;
  const v = sbom.vulnerabilities === null ? "dependencies not scanned" : `${sbom.vulnerabilities} dependency vulnerabilities`;
  return `${c} · ${v}`;
}

export function SecurityView({ report, projectId, approved, status }: {
  report: ModernizationSecurity; projectId?: ProjectId; approved?: boolean; status?: string;
}) {
  const s = report;
  const v = VERDICT[s.verdict];
  const Icon = v.icon;
  const introduced = s.findings.filter((f) => f.origin === "introduced").length;
  const carried = s.findings.filter((f) => f.origin === "carried_over").length;
  const notRun = Object.entries(s.scans).filter(([, st]) => st !== "ran" && st !== "cached");
  const sorted = [...s.findings].sort((a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity));
  return (
    <div className="space-y-6">
      <section aria-label="Security summary" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-base font-semibold">{s.module_id} {s.module.name ?? ""}</span>
          <Badge variant={v.variant} className="gap-1 font-normal"><Icon className="size-3.5" aria-hidden />{s.verdict}</Badge>
          {s.pr && <PrLink pr={s.pr} />}
        </div>
        <p className="text-muted-foreground text-xs">
          Scanned head <span className="font-mono">{(s.head_sha ?? "").slice(0, 10)}</span> (migration record v{s.migration_version ?? "?"})
          against the legacy code at <span className="font-mono">{s.legacy_commit.slice(0, 10)}</span>
          {s.legacy_cached ? " (legacy scan from the cache)" : ""}.
        </p>
        {notRun.length > 0 && (
          <div role="status" aria-label="Scanners not run" className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            Not scanned by {notRun.map(([t, st]) => `${t} (${words(st)})`).join(", ")} — this module is not shown clean for what
            they cover, and the sign-off cannot be PASS.
          </div>
        )}
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Introduced" value={introduced} emphasis={introduced > 0} />
          <Stat label="Carried over" value={carried} />
          <Stat label="Fixed by the migration" value={s.fixed_from_legacy.length} />
          <Stat label="Legacy secrets in target" value={s.secret_carryover.length} emphasis={s.secret_carryover.length > 0} />
          <Stat label="SBOM" value={sbomText(s.sbom)} />
        </dl>
        {s.rationale && <p className="whitespace-pre-wrap text-sm">{s.rationale}</p>}
      </section>

      {projectId && <LedgerPanel projectId={projectId} moduleId={s.module_id} kind="security" verdict={s.verdict}
        approved={!!approved} status={status} />}

      <Tabs defaultValue="findings">
        <TabsList className="flex-wrap">
          <TabsTrigger value="findings">Findings ({s.findings.length})</TabsTrigger>
          <TabsTrigger value="fixed">Fixed ({s.fixed_from_legacy.length})</TabsTrigger>
          <TabsTrigger value="authz">Contract authorization ({s.contract_authz.length})</TabsTrigger>
          <TabsTrigger value="scans">Scans</TabsTrigger>
        </TabsList>
        <TabsContent value="findings" className="mt-4">
          {sorted.length === 0 ? <Empty>No findings in the report.</Empty> : (
            <ul aria-label="Security findings" className="space-y-3">
              {sorted.map((f) => (
                <li key={f.id} className="rounded-lg border p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{f.id}</span>
                    <Badge variant={SEV_VARIANT[f.severity]} className="font-normal">{f.severity}</Badge>
                    <Badge variant={f.origin === "introduced" ? "warning" : "outline"} className="font-normal">{words(f.origin)}</Badge>
                    {f.is_secret && <Badge variant="danger" className="font-normal">secret</Badge>}
                    <span className="text-muted-foreground text-xs">
                      reachable: {f.reachable === null ? "unknown (counts as reachable)" : f.reachable ? "yes" : "no"}
                    </span>
                  </div>
                  <p className="mt-1">{f.title}{f.cve ? ` — ${f.cve} in ${f.package ?? "?"}` : ""}</p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    {f.file && <>In <span className="font-mono">{f.file}</span></>}
                    {f.legacy_ref && <> · legacy <span className="font-mono">{f.legacy_ref}</span></>}
                  </p>
                  {f.remediation_plan && (
                    <p className="mt-1 text-xs"><span className="font-medium">Remediation:</span> {f.remediation_plan}
                      {f.remediation_due ? ` (by ${f.remediation_due})` : ""}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
          {s.secret_carryover.length > 0 && (
            <div role="alert" className="mt-4 rounded-lg border border-red-500/40 bg-red-500/5 p-3 text-sm">
              <p className="font-medium">Legacy secrets found in the target — rotate as well as remove (the legacy repository still holds them)</p>
              <ul className="mt-1 space-y-1 text-xs">
                {s.secret_carryover.map((c) => <li key={`${c.file}${c.line}`}><span className="font-mono">{c.file}:{c.line}</span> (from {c.legacy_file})</li>)}
              </ul>
            </div>
          )}
        </TabsContent>
        <TabsContent value="fixed" className="mt-4">
          {s.fixed_from_legacy.length === 0 ? <Empty>Nothing the legacy scan found is gone from the target.</Empty> : (
            <ul aria-label="Fixed by the migration" className="space-y-1 text-sm">
              {s.fixed_from_legacy.map((f) => (
                <li key={f.title + f.legacy_ref}>{f.title}{f.cve && f.cve !== f.title ? ` (${f.cve})` : ""} — <span className="font-mono text-xs">{f.legacy_ref}</span></li>
              ))}
            </ul>
          )}
        </TabsContent>
        <TabsContent value="authz" className="mt-4">
          <CheckTable label="Contract authorization" rows={s.contract_authz.map((a) => [a.ct_id, a.status, a.note])} bad="weaker" />
        </TabsContent>
        <TabsContent value="scans" className="mt-4">
          <table className="w-full text-left text-sm" aria-label="Scanners">
            <thead className="text-muted-foreground text-xs">
              <tr><th className="py-1 pr-3">Scanner</th><th className="pr-3">Version</th><th className="pr-3">Status</th><th>Note</th></tr>
            </thead>
            <tbody>
              {Object.entries(s.scans).map(([tool, st]) => (
                <tr key={tool} className="border-t">
                  <td className="py-1 pr-3">{tool}</td>
                  <td className="pr-3 font-mono text-xs">{s.scanner_versions[tool] ?? "—"}</td>
                  <td className="pr-3"><Badge variant={st === "ran" || st === "cached" ? "outline" : "warning"} className="font-normal">{st === "ran" ? "ran" : `not scanned (${words(st)})`}</Badge></td>
                  <td className="text-muted-foreground text-xs">{s.scan_notes[tool] ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-muted-foreground mt-3 text-xs">
            Scanner hits on the target: {s.target_hits.length} ({s.target_hits.filter((h) => h.origin === "introduced").length} introduced);
            on the legacy: {s.legacy_hits.length}. Pinned images, run offline.
          </p>
        </TabsContent>
      </Tabs>
    </div>
  );
}

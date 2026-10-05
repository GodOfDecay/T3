"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleSlash, GitBranch, Hammer, ListOrdered, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getMigrationWorkspaces } from "@/lib/api/modernization";
import { getLedger, stateLabel } from "@/lib/api/modernization-programme";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";
import type { Migration, MigrationWorkspace } from "@/lib/schemas/modernization";

/**
 * One module's migration record (Track 3, Migration Development — Phase H), for the Developer who accepts
 * it and for Migration Review and Security, who review its pull request.
 *
 * The questions a reviewer asks: WHAT became of every legacy file (mapped, merged, dropped and why), HOW it
 * was changed (recipes with pinned versions, commits by concern, what was rewritten by hand), whether every
 * TRAP the design names for the module is handled and where, whether it BUILDS (and in how many of five
 * rounds), and what the equivalence PREVIEW said — a hint against the accepted baseline, never the verdict.
 * The page shows the record and the workspace's facts; never code.
 */

const STATUS_WORD: Record<string, string> = {
  published: "approved", granted: "approved by exception", draft: "not yet approved",
};

const OUTCOME: Record<Migration["outcome"], { label: string; variant: "success" | "danger" | "warning" }> = {
  ready_for_review: { label: "ready for review", variant: "success" },
  build_failed: { label: "build failed", variant: "danger" },
  blocked: { label: "blocked — a person must redesign it", variant: "warning" },
};

export function MigrationView({ migration, projectId, approved, status }: {
  migration: Migration;
  projectId?: ProjectId;
  approved?: boolean;
  status?: string;
}) {
  const m = migration;
  const outcome = OUTCOME[m.outcome];
  return (
    <div className="space-y-6">
      <section aria-label="Migration summary" className="space-y-3">
        <Sources migration={m} />
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-base font-semibold">
            {m.module_id} {m.module.name ?? ""}
          </span>
          <span className="text-muted-foreground font-mono text-xs">{m.legacy_module_path}/</span>
          <Badge variant={outcome.variant} className="font-normal">{outcome.label}</Badge>
        </div>
        {m.outcome === "blocked" ? (
          <div role="status" aria-label="Hand-off" className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            <p className="font-medium">What a person must redesign</p>
            <p className="mt-1 whitespace-pre-wrap">{m.handoff_note}</p>
          </div>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
              <Stat label="Tier" value={m.module.tier ?? "—"} small />
              <Stat label="Target" value={m.module.target_runtime ?? "—"} small />
              <Stat label="Build" value={`${m.build.status.replace("_", " ")} · ${m.build.rounds}/5`}
                emphasis={m.build.status !== "green"} small />
              <Stat label="Tests" value={checkWord(m.tests)} emphasis={m.tests?.status === "red"} small />
              <Stat label="Lint" value={checkWord(m.lint)} emphasis={m.lint?.status === "red"} small />
              <Stat label="Legacy files" value={m.file_map.length} />
              <Stat label="Rewritten by hand" value={m.llm_rewritten.length} />
              <Stat label="Recipes" value={m.recipes.length} />
            </dl>
            <BranchLine migration={m} />
            <PreviewLine migration={m} />
            {m.build.failing && (
              <pre aria-label="What fails" className="max-h-48 overflow-auto rounded-lg border border-red-500/40 bg-red-500/5 p-3 text-xs">
                {m.build.failing}
              </pre>
            )}
          </>
        )}
        {m.notes.length > 0 && (
          <ul aria-label="Notes" className="text-muted-foreground space-y-1 text-xs">
            {m.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        )}
      </section>

      {projectId && <MigrationLedger projectId={projectId} migration={m} approved={!!approved} status={status} />}

      {m.outcome !== "blocked" && (
        <Tabs defaultValue="files">
          <TabsList className="flex-wrap">
            <TabsTrigger value="files">Legacy → target ({m.file_map.length})</TabsTrigger>
            <TabsTrigger value="traps">Traps ({Object.keys(m.traps_handled).length}/{(m.module.trap_ids ?? []).length})</TabsTrigger>
            <TabsTrigger value="commits">Commits ({m.commits.length})</TabsTrigger>
            <TabsTrigger value="preview">Preview</TabsTrigger>
            <TabsTrigger value="follow-ups">Left for a person ({m.manual_follow_ups.length + m.vault_references.length})</TabsTrigger>
          </TabsList>
          <TabsContent value="files" className="mt-4"><FileMap migration={m} /></TabsContent>
          <TabsContent value="traps" className="mt-4"><Traps migration={m} /></TabsContent>
          <TabsContent value="commits" className="mt-4"><Commits migration={m} /></TabsContent>
          <TabsContent value="preview" className="mt-4"><Preview migration={m} /></TabsContent>
          <TabsContent value="follow-ups" className="mt-4"><FollowUps migration={m} /></TabsContent>
        </Tabs>
      )}
    </div>
  );
}

function checkWord(c: Migration["tests"]): string {
  if (!c?.status) return "not run";
  return c.status === "not_run" ? `not run${c.note ? ` (${c.note})` : ""}` : c.status;
}

function Sources({ migration }: { migration: Migration }) {
  const label = (key: "design" | "plan" | "baseline", noun: string) => {
    const s = migration.sources[key];
    return s?.version != null ? `${noun} v${s.version} (${STATUS_WORD[s.status ?? ""] ?? s.status})` : null;
  };
  const parts = [label("design", "Target design"), label("plan", "Migration plan"), label("baseline", "Baseline")].filter(Boolean);
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {migration.system_name && <span className="text-foreground font-medium">{migration.system_name}</span>}
      {parts.length ? parts.map((p) => <span key={p}>{p}</span>) : <span>From the Orchestrator conversation</span>}
      {migration.recorded_at && <span>Recorded {new Date(migration.recorded_at).toLocaleString()}</span>}
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

function BranchLine({ migration }: { migration: Migration }) {
  if (!migration.target_branch) return null;
  return (
    <p aria-label="Branch" className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <GitBranch className="size-3.5" aria-hidden />
      <span>Branch <span className="font-mono">{migration.target_branch}</span> from{" "}
        <span className="font-mono">{migration.base_branch ?? "—"}</span></span>
      {migration.head_sha && <span>head <span className="font-mono">{migration.head_sha.slice(0, 10)}</span></span>}
      <span>{migration.changed_files.length} file{migration.changed_files.length === 1 ? "" : "s"} changed</span>
    </p>
  );
}

function PreviewLine({ migration }: { migration: Migration }) {
  const p = migration.preview;
  const clean = p && Object.values(p.scenarios).every((s) => Object.keys(s.differences).length === 0);
  return (
    <p aria-label="Equivalence preview" className="flex items-center gap-2 text-xs">
      {!p ? (
        <><CircleSlash className="text-muted-foreground size-3.5" aria-hidden />
          <span className="text-muted-foreground">No equivalence preview on this commit — not run, so nothing is claimed.</span></>
      ) : clean ? (
        <><CheckCircle2 className="size-3.5 text-emerald-600" aria-hidden />
          <span>Preview: {p.headline}. A hint against baseline v{p.baseline_version ?? "?"} — Equivalence Testing&apos;s verification is the verdict.</span></>
      ) : (
        <><AlertTriangle className="size-3.5 text-amber-600" aria-hidden />
          <span>Preview: {p.headline}. A hint, not the verdict.</span></>
      )}
    </p>
  );
}

// ── the ledger ──────────────────────────────────────────────────────────────

export function migrationLedgerText(m: Migration, approved: boolean, status: string | undefined, state?: string): string {
  if (m.outcome === "blocked") return "This module is blocked on the migration ledger until a person redesigns it.";
  if (status === "rejected") return "This record was rejected: nothing is pushed from it. A new record is made and accepted.";
  if (status === "superseded") return "A newer record for this module has been accepted since; the ledger follows that one.";
  if (!approved) {
    return m.outcome === "ready_for_review"
      ? "Accepting this record (a Developer who did not record it, or a Project Admin) lets the branch be pushed and the pull request opened — exactly this commit, never forced."
      : "This record is not ready for review, so it is never pushed.";
  }
  if (state === "in_review") return "Accepted and pushed: the pull request is in review (Migration Review and Security).";
  return m.outcome === "ready_for_review"
    ? "Accepted. The Developer pushes the branch and opens the pull request from the chat, after confirming it."
    : "Accepted as a record of what failed; it is not pushed.";
}

function MigrationLedger({ projectId, migration, approved, status }: {
  projectId: ProjectId; migration: Migration; approved: boolean; status?: string;
}) {
  const q = useQuery({ queryKey: qk.modernizationProgramme.ledger(projectId), queryFn: () => getLedger(projectId) });
  const { refetch } = q;
  React.useEffect(() => {
    if (approved) void refetch();
  }, [approved, refetch]);
  const row = (q.data?.modules ?? []).find((r) => r.moduleId === migration.module_id);
  const pr = row?.prUrl ?? null;
  return (
    <section aria-label="Module ledger" className="rounded-lg border p-3">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <ListOrdered className="text-muted-foreground size-4" aria-hidden /> Module ledger
      </h3>
      <p className="text-muted-foreground mt-1 text-xs">{migrationLedgerText(migration, approved, status, row?.state)}</p>
      {q.isError && <p className="text-muted-foreground mt-1 text-xs">The ledger could not be loaded.</p>}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono">{migration.module_id}</span>
        {row ? (
          <Badge variant={row.state === "blocked" ? "danger" : "info"} className="font-normal">{stateLabel(row.state)}</Badge>
        ) : (
          q.data && <Badge variant="outline" className="font-normal">not on the ledger</Badge>
        )}
        {pr && (/^https?:\/\//.test(pr) ? (
          <a href={pr} target="_blank" rel="noreferrer" className="text-primary underline">Pull request</a>
        ) : (
          <span className="text-muted-foreground">Pull request: <span className="font-mono">{pr}</span></span>
        ))}
      </div>
    </section>
  );
}

// ── tabs ────────────────────────────────────────────────────────────────────

function FileMap({ migration }: { migration: Migration }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm" aria-label="Legacy to target">
        <thead className="text-muted-foreground text-xs">
          <tr><th className="py-1 pr-3">Legacy file</th><th className="pr-3">Disposition</th><th>Target file / reason</th></tr>
        </thead>
        <tbody>
          {migration.file_map.map((e) => {
            const rewritten = migration.llm_rewritten.find((r) => r.file === e.target_path);
            return (
              <tr key={e.legacy_path} className="border-t align-top">
                <td className="py-1.5 pr-3 font-mono text-xs">{e.legacy_path}</td>
                <td className="pr-3"><Badge variant={e.disposition === "dropped" ? "warning" : "outline"} className="font-normal">{e.disposition}</Badge></td>
                <td className="text-xs">
                  {e.target_path ? <span className="font-mono">{e.target_path}</span> : e.reason}
                  {rewritten && <span className="text-muted-foreground block">rewritten by hand: {rewritten.reason}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Traps({ migration }: { migration: Migration }) {
  const ids = migration.module.trap_ids ?? [];
  if (!ids.length) return <p className="text-muted-foreground text-sm">The design names no trap for this module.</p>;
  return (
    <ul aria-label="Traps" className="space-y-2 text-sm">
      {ids.map((id) => {
        const where = migration.traps_handled[id];
        return (
          <li key={id} className="flex gap-2">
            {where ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />
              : <XCircle className="mt-0.5 size-4 shrink-0 text-red-600" aria-hidden />}
            <span><span className="font-mono">{id}</span> — {where ?? "not handled"}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Commits({ migration }: { migration: Migration }) {
  return (
    <div className="space-y-3">
      {migration.recipes.length > 0 && (
        <p className="text-xs">
          <Hammer className="text-muted-foreground mr-1 inline size-3.5" aria-hidden />
          Recipes: {migration.recipes.map((r) => `${r.tool} ${r.version}`).join("; ")}
        </p>
      )}
      <ol aria-label="Commits" className="space-y-1 text-sm">
        {migration.commits.map((c) => {
          const [concern, ...rest] = c.subject.split(":");
          return (
            <li key={c.sha} className="flex gap-2">
              <span className="font-mono text-xs">{c.sha.slice(0, 10)}</span>
              <Badge variant="outline" className="font-normal">{rest.length ? concern : "commit"}</Badge>
              <span>{rest.length ? rest.join(":").trim() : c.subject}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Preview({ migration }: { migration: Migration }) {
  const p = migration.preview;
  if (!p) return <p className="text-muted-foreground text-sm">No equivalence preview on the recorded commit.</p>;
  return (
    <table className="w-full text-left text-sm" aria-label="Preview">
      <thead className="text-muted-foreground text-xs">
        <tr><th className="py-1 pr-3">Scenario</th><th className="pr-3 text-right">Cases</th><th>Differences from the baseline</th></tr>
      </thead>
      <tbody>
        {Object.entries(p.scenarios).map(([sid, s]) => (
          <tr key={sid} className="border-t align-top">
            <td className="py-1.5 pr-3">{sid}</td>
            <td className="pr-3 text-right tabular-nums">{s.cases}</td>
            <td className="text-xs">
              {Object.keys(s.differences).length === 0 ? "none — identical after normalization"
                : Object.entries(s.differences).map(([f, n]) => (
                  <span key={f} className="block">{f} ({n}){s.examples[f] ? ` — ${s.examples[f][0]} vs ${s.examples[f][1]}` : ""}</span>
                ))}
              {s.ignored.length > 0 && <span className="text-muted-foreground block">ignored (the legacy varies in them, or a rule covers them): {s.ignored.join(", ")}</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FollowUps({ migration }: { migration: Migration }) {
  if (!migration.manual_follow_ups.length && !migration.vault_references.length) {
    return <p className="text-muted-foreground text-sm">Nothing is left for a person.</p>;
  }
  return (
    <div className="space-y-3 text-sm">
      {migration.vault_references.length > 0 && (
        <div><p className="font-medium">Secrets to provision (references, never values)</p>
          <ul className="list-disc pl-5">{migration.vault_references.map((v) => <li key={v} className="font-mono text-xs">{v}</li>)}</ul></div>
      )}
      {migration.manual_follow_ups.length > 0 && (
        <div><p className="font-medium">Follow-ups</p>
          <ul className="list-disc pl-5">{migration.manual_follow_ups.map((f) => <li key={f}>{f}</li>)}</ul></div>
      )}
    </div>
  );
}

// ── the workspaces (work in progress) ───────────────────────────────────────

export function WorkspacesButton({ projectId }: { projectId: ProjectId }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <GitBranch className="size-4" aria-hidden />
        Workspaces
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Migration workspaces</DialogTitle>
            <DialogDescription>
              Each module being migrated: its branch on the target repository, commits by concern, build rounds (at most
              five), checks and the last equivalence preview. The code itself stays in the repository.
            </DialogDescription>
          </DialogHeader>
          {open && <WorkspacesPanel projectId={projectId} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

export function WorkspacesPanel({ projectId }: { projectId: ProjectId }) {
  const q = useQuery({ queryKey: qk.modernizationProgramme.migrationWorkspaces(projectId), queryFn: () => getMigrationWorkspaces(projectId) });
  if (q.isLoading) return <LoadingState variant="card" />;
  if (q.isError || !q.data) {
    return <ErrorState title="The workspaces could not be loaded" description={q.error instanceof Error ? q.error.message : ""}
      onRetry={() => q.refetch()} />;
  }
  if (!q.data.workspaces.length) {
    return <p className="text-muted-foreground text-sm">No module is being migrated yet — ask the Migration Development agent to start one.</p>;
  }
  return <ul className="space-y-2">{q.data.workspaces.map((w) => <WorkspaceRow key={w.moduleId} w={w} />)}</ul>;
}

function WorkspaceRow({ w }: { w: MigrationWorkspace }) {
  return (
    <li aria-label={`Workspace ${w.moduleId}`} className="rounded-lg border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{w.moduleId}</span>
        <span className="font-mono text-xs">{w.branch}</span>
        {w.targetRuntime && <span className="text-muted-foreground text-xs">→ {w.targetRuntime}</span>}
        {w.pushed && <Badge variant="success" className="font-normal">pushed {w.pushed.head.slice(0, 10)}</Badge>}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
        <span className="text-muted-foreground mr-1">Builds</span>
        {w.builds.length === 0 && <span className="text-muted-foreground">none yet</span>}
        {w.builds.map((b) => (
          <Badge key={b.round} variant={b.ok ? "success" : "danger"} className="font-normal">#{b.round} {b.ok ? "green" : "red"}</Badge>
        ))}
        <span className="text-muted-foreground ml-2">Tests {w.tests ?? "not run"} · Lint {w.lint ?? "not run"}</span>
      </div>
      <p className="text-muted-foreground mt-1 text-xs">
        {w.commits.length} commit{w.commits.length === 1 ? "" : "s"} ({[...new Set(w.commits.map((c) => c.concern))].join(", ") || "none"})
        {w.preview && ` · preview: ${w.preview}`}
      </p>
    </li>
  );
}

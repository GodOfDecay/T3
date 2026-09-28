"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, LayoutGrid } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import {
  getApprovalSettings,
  getLedger,
  getRepositories,
  stateLabel,
  type LedgerModule,
} from "@/lib/api/modernization-programme";
import { getProject } from "@/lib/api/projects";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";

/**
 * The Programme board of a Code Modernization project: every module, the state it is in,
 * what blocks it, and the project facts that decide whether work can move — the legacy and
 * target repositories and the sign-off staffing.
 *
 * READ-ONLY. Modules move when an agent's version is approved (the ledger's own rules);
 * a person unblocks or reopens from the agent that owns the step. This page only shows.
 */
export default function ProgrammePage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id as ProjectId;
  const projectQ = useQuery({ queryKey: qk.projects.detail(projectId), queryFn: () => getProject(projectId) });
  const isTrack3 = projectQ.data?.track === "modernization";
  const ledgerQ = useQuery({
    queryKey: qk.modernizationProgramme.ledger(projectId),
    queryFn: () => getLedger(projectId),
    enabled: isTrack3,
  });
  const reposQ = useQuery({
    queryKey: qk.modernizationProgramme.repositories(projectId),
    queryFn: () => getRepositories(projectId),
    enabled: isTrack3,
  });
  const settingsQ = useQuery({
    queryKey: qk.modernizationProgramme.approvalSettings(projectId),
    queryFn: () => getApprovalSettings(projectId),
    enabled: isTrack3,
  });

  if (projectQ.isLoading) return <LoadingState variant="card" />;
  if (projectQ.data && !isTrack3) {
    return (
      <div className="p-6">
        <EmptyState icon={LayoutGrid} title="No Programme on this project"
          description="The Programme board belongs to Code Modernization projects." />
      </div>
    );
  }
  if (ledgerQ.isError || projectQ.isError) {
    return (
      <div className="p-6">
        <ErrorState title="Could not load the Programme"
          description={(ledgerQ.error ?? projectQ.error)?.message ?? "Unknown error."}
          onRetry={() => void ledgerQ.refetch()} />
      </div>
    );
  }
  if (!ledgerQ.data) return <LoadingState variant="card" />;

  const { states, modules } = ledgerQ.data;
  const byState = (s: string) => modules.filter((m) => m.state === s);
  const blocked = byState("blocked");
  const warnings = settingsQ.data?.warnings ?? [];

  return (
    <div className="w-full space-y-6 p-4 md:px-10 md:py-8">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Programme</h1>
        <p className="text-muted-foreground text-sm">
          Every module of the legacy system and where it stands. Modules are added and moved by the agents from
          Target Architecture on, as their versions are approved; those agents are not built yet.
        </p>
      </header>

      {settingsQ.isError && (
        <p className="text-destructive text-xs">
          The staffing warnings could not be loaded: {settingsQ.error?.message ?? "unknown error"}.
        </p>
      )}
      {warnings.length > 0 && (
        <ul aria-label="Staffing warnings" className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
          {warnings.map((w) => (
            <li key={w} className="flex gap-2">
              <AlertTriangle className="size-4 shrink-0 text-amber-600" aria-hidden />
              {w}
            </li>
          ))}
        </ul>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Repositories</CardTitle>
          <CardDescription>
            Track 3&apos;s agents only read the legacy repository. Set both in{" "}
            <Link className="text-primary hover:underline" href={`/projects/${projectId}/settings?tab=modernization`}>
              Settings
            </Link>
            .
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
          {reposQ.isError && (
            <p className="text-destructive text-xs sm:col-span-2">
              The repositories could not be loaded: {reposQ.error?.message ?? "unknown error"}.
            </p>
          )}
          {!reposQ.isError && (["legacy", "target"] as const).map((role) => {
            const r = reposQ.data?.[role];
            return (
              <div key={role}>
                <p className="text-muted-foreground text-xs">{role === "legacy" ? "Legacy" : "Target"}</p>
                {reposQ.isLoading ? (
                  <p className="text-muted-foreground">Loading…</p>
                ) : r ? (
                  <p className="break-all">
                    <code>{r.url}</code>
                    {r.branch ? <span className="text-muted-foreground"> @ {r.branch}</span> : null}
                  </p>
                ) : (
                  <p className="text-muted-foreground">Not set</p>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      {modules.length === 0 ? (
        <EmptyState icon={LayoutGrid} title="No modules yet"
          description="Modules will appear here when a Target Architecture is approved — each in-scope module enters as Designed. That agent is not built yet." />
      ) : (
        <>
          <section aria-label="Modules by state" className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            {states.map((s) => (
              <div key={s} className="rounded-lg border p-2">
                <p className="text-muted-foreground text-xs">{stateLabel(s)}</p>
                <p className="text-lg font-semibold" aria-label={`${stateLabel(s)}: ${byState(s).length}`}>
                  {byState(s).length}
                </p>
              </div>
            ))}
          </section>

          {blocked.length > 0 && (
            <section aria-label="Blocked modules" className="space-y-1">
              <h2 className="text-sm font-medium">Blocked</h2>
              {blocked.map((m) => (
                <p key={m.moduleId} className="text-xs">
                  <span className="font-medium">{m.moduleId}</span> (was {stateLabel(m.blockedFrom ?? "")}):{" "}
                  {m.blockedReason}
                </p>
              ))}
            </section>
          )}

          <ModuleTable modules={modules} />
        </>
      )}
    </div>
  );
}

function ModuleTable({ modules }: { modules: LedgerModule[] }) {
  return (
    <table className="w-full text-left text-sm" aria-label="Modules">
      <thead className="text-muted-foreground text-xs">
        <tr>
          <th className="py-2 pr-3 font-medium">Module</th>
          <th className="py-2 pr-3 font-medium">Legacy path</th>
          <th className="py-2 pr-3 font-medium">Tier</th>
          <th className="py-2 pr-3 font-medium">Wave</th>
          <th className="py-2 pr-3 font-medium">State</th>
        </tr>
      </thead>
      <tbody>
        {modules.map((m) => (
          <tr key={m.moduleId} className="border-t">
            <td className="py-2 pr-3">
              <span className="font-medium">{m.moduleId}</span>
              {m.moduleName !== m.moduleId && <span className="text-muted-foreground"> · {m.moduleName}</span>}
            </td>
            <td className="py-2 pr-3"><code className="text-xs">{m.legacyPath}</code></td>
            <td className="py-2 pr-3">{m.tier ?? "—"}</td>
            <td className="py-2 pr-3">{m.wave ?? "—"}</td>
            <td className="py-2 pr-3">
              <Badge variant={m.state === "blocked" ? "destructive" : "outline"}>{stateLabel(m.state)}</Badge>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

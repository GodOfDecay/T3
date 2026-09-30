"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Plug } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/error-state";
import { Input } from "@/components/ui/input";
import { LoadingState } from "@/components/ui/loading-state";
import { getLegacyInterfaces } from "@/lib/api/modernization";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";
import type { LegacyInterface } from "@/lib/schemas/modernization";

/**
 * What the legacy system exposes and consumes, read from the pulled code — the SAME deterministic
 * inventory the Target Architecture agent reads its frozen contracts from, so an Architect can see
 * what the agent saw: every endpoint, file, job, table and queue, with its file and line.
 *
 * It says what it is (a pattern scan) and what it is not (proof of every interface): a contract
 * the agent cannot tie to an entry here is recorded as "proposed" until someone confirms it.
 */
export const KIND_LABEL: Record<string, string> = {
  http: "HTTP", rpc: "RPC", file: "Files", job: "Jobs", db: "Database", queue: "Queues", ui: "Screens",
};

export function LegacyInterfacesButton({ projectId }: { projectId: ProjectId }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Plug className="size-4" aria-hidden />
        Legacy interfaces
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Legacy interfaces</DialogTitle>
            <DialogDescription>
              What the pulled legacy code exposes and consumes, found by scanning it — the evidence frozen contracts
              are drawn from. It scans Java, Kotlin, Scala, C#, VB.NET, Python, JavaScript/TypeScript, Go, PHP, Ruby,
              COBOL, JCL and SQL, declared contracts (OpenAPI, WSDL, gRPC, GraphQL), web.xml, JSP/ASPX pages and cron,
              Quartz and Kubernetes schedules — other code is not scanned — and can miss an interface built at run time.
              A contract the brief did not name can only be confirmed where this list shows it.
            </DialogDescription>
          </DialogHeader>
          {open && <LegacyInterfacesPanel projectId={projectId} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

export function LegacyInterfacesPanel({ projectId }: { projectId: ProjectId }) {
  const q = useQuery({ queryKey: qk.modernization.legacyInterfaces(projectId), queryFn: () => getLegacyInterfaces(projectId) });
  const [kind, setKind] = React.useState<string>("all");
  const [filter, setFilter] = React.useState("");
  if (q.isLoading) return <LoadingState variant="card" />;
  if (q.isError || !q.data) {
    return <ErrorState title="The inventory could not be loaded" description={q.error instanceof Error ? q.error.message : ""}
      onRetry={() => q.refetch()} />;
  }
  const inv = q.data.inventory;
  if (q.data.status === "none" || !inv) {
    return <p className="text-muted-foreground text-sm">No legacy code is pulled for this project yet — pull it first.</p>;
  }
  const needle = filter.trim().toLowerCase();
  const rows = inv.items.filter((i) => (kind === "all" || i.kind === kind) &&
    (!needle || `${i.name} ${i.location} ${i.module}`.toLowerCase().includes(needle)));
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs">
        {q.data.repository ? `${q.data.repository} · ` : ""}commit <span className="font-mono">{inv.commit.slice(0, 10) || "unknown"}</span>
        {" · "}{inv.total} found{inv.truncated ? ` (showing the first ${inv.items.length})` : ""}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Filter by kind" className="flex flex-wrap gap-2">
          {["all", ...Object.keys(KIND_LABEL)].map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={kind === k}
              onClick={() => setKind(k)}
              className={cn(
                "rounded-md border px-2.5 py-1 text-xs transition-colors",
                kind === k ? "bg-primary/10 border-primary text-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {k === "all" ? `All (${inv.total})` : `${KIND_LABEL[k]} (${inv.counts[k] ?? 0})`}
            </button>
          ))}
        </div>
        <Input
          aria-label="Filter interfaces"
          placeholder="Filter by name, file or module"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-8 max-w-64 text-xs"
        />
      </div>
      <div className="max-h-[55vh] overflow-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-muted-foreground sticky top-0 text-left text-xs">
            <tr>
              <th className="px-3 py-2 font-medium">Kind</th>
              <th className="px-3 py-2 font-medium">Direction</th>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Where</th>
              <th className="px-3 py-2 font-medium">Module</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((i: LegacyInterface) => (
              <tr key={`${i.kind}-${i.direction}-${i.name}-${i.location}`} className="border-t align-top" title={i.evidence}>
                <td className="px-3 py-1.5 text-xs">{KIND_LABEL[i.kind] ?? i.kind}</td>
                <td className="text-muted-foreground px-3 py-1.5 text-xs">{i.direction}</td>
                <td className="px-3 py-1.5"><code className="break-all text-xs">{i.name}</code></td>
                <td className="px-3 py-1.5"><code className="text-muted-foreground break-all text-[11px]">{i.location}</code></td>
                <td className="px-3 py-1.5 font-mono text-xs">{i.module || "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="text-muted-foreground px-3 py-6 text-center">Nothing matches.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

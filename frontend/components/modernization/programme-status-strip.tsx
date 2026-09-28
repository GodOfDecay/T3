"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, LayoutGrid } from "lucide-react";

import { getLedger, stateLabel } from "@/lib/api/modernization-programme";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";

/**
 * One line of where the programme stands, shown on every Code Modernization agent page:
 * how many modules are in each state (only states with modules), how many are blocked, and
 * a link to the Programme board.
 *
 * Silent until the ledger has modules — the first two agents run before any exist, and an
 * all-zero strip would only say "nothing yet" in eleven places. Silent on error too: the
 * strip is context, not the page's job, and the Programme page reports its own errors.
 */
export function ProgrammeStatusStrip({ projectId }: { projectId: ProjectId }) {
  const q = useQuery({ queryKey: qk.modernizationProgramme.ledger(projectId), queryFn: () => getLedger(projectId) });
  const modules = q.data?.modules ?? [];
  if (modules.length === 0) return null;
  const counts = new Map<string, number>();
  for (const m of modules) counts.set(m.state, (counts.get(m.state) ?? 0) + 1);
  const blocked = counts.get("blocked") ?? 0;
  const states = (q.data?.states ?? []).filter((s) => s !== "blocked" && counts.get(s));
  return (
    <nav aria-label="Programme status" className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className="text-foreground font-medium">
        {modules.length} module{modules.length === 1 ? "" : "s"}
      </span>
      {states.map((s) => (
        <span key={s}>
          {stateLabel(s)} {counts.get(s)}
        </span>
      ))}
      {blocked > 0 && (
        <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
          <AlertTriangle className="size-3" aria-hidden />
          {blocked} blocked
        </span>
      )}
      <Link href={`/projects/${projectId}/modernization`} className="text-primary inline-flex items-center gap-1 hover:underline">
        <LayoutGrid className="size-3" aria-hidden />
        Programme
      </Link>
    </nav>
  );
}

"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingState } from "@/components/ui/loading-state";
import {
  getApprovalSettings,
  getRepositories,
  setApprovalSettings,
  setRepository,
  type ApprovalSettings,
  type Repository,
  type RepositoryRole,
} from "@/lib/api/modernization-programme";
import { qk } from "@/lib/api/query-keys";
import type { ProjectId } from "@/lib/schemas";

const ROLE_TEXT: Record<RepositoryRole, { title: string; help: string }> = {
  legacy: {
    title: "Legacy repository",
    help: "The system being modernized. Track 3's agents only read it, and it can never be named as the target.",
  },
  target: {
    title: "Target repository",
    help: "Where the modernized code goes. It must not be the legacy repository. Only Migration Development and Cutover will write here.",
  },
};

/**
 * Code Modernization settings: the legacy and target repositories, and how sign-offs fall
 * back to a Project Admin. Shown on a Track 3 project's Settings page only.
 *
 * `canEdit` is a hint for the controls; the backend is what refuses — it also requires that
 * the caller administers THIS project, which a tenant-wide permission cannot say.
 */
export function ModernizationSettingsCard({ projectId, canEdit }: { projectId: ProjectId; canEdit: boolean }) {
  const reposQ = useQuery({
    queryKey: qk.modernizationProgramme.repositories(projectId),
    queryFn: () => getRepositories(projectId),
  });
  const settingsQ = useQuery({
    queryKey: qk.modernizationProgramme.approvalSettings(projectId),
    queryFn: () => getApprovalSettings(projectId),
  });

  if (reposQ.isLoading || settingsQ.isLoading) return <LoadingState variant="card" />;
  if (reposQ.isError || settingsQ.isError || !reposQ.data || !settingsQ.data) {
    return (
      <ErrorState
        title="Could not load the Code Modernization settings"
        description={(reposQ.error ?? settingsQ.error)?.message ?? "Unknown error."}
        onRetry={() => {
          void reposQ.refetch();
          void settingsQ.refetch();
        }}
      />
    );
  }
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Repositories</CardTitle>
          <CardDescription>
            No Track 3 agent pushes code yet. When Migration Development and Cutover arrive, a push will need all
            of: a stage that writes the target, the remote being this target, and write access wired for that
            stage (Connectors tab).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {(["legacy", "target"] as const).map((role) => (
            <RepositoryForm key={role} projectId={projectId} role={role} current={reposQ.data[role]} canEdit={canEdit} />
          ))}
        </CardContent>
      </Card>
      <ApprovalSettingsForm projectId={projectId} current={settingsQ.data} canEdit={canEdit} />
    </div>
  );
}

function RepositoryForm({ projectId, role, current, canEdit }: {
  projectId: ProjectId; role: RepositoryRole; current: Repository | null; canEdit: boolean;
}) {
  const qc = useQueryClient();
  const [url, setUrl] = React.useState(current?.url ?? "");
  const [branch, setBranch] = React.useState(current?.branch ?? "");
  React.useEffect(() => {
    setUrl(current?.url ?? "");
    setBranch(current?.branch ?? "");
  }, [current?.url, current?.branch]);
  const save = useMutation({
    mutationFn: () => setRepository(projectId, role, url.trim(), branch.trim()),
    onSuccess: () => {
      toast.success(`${ROLE_TEXT[role].title} saved`);
      void qc.invalidateQueries({ queryKey: qk.modernizationProgramme.repositories(projectId) });
    },
    onError: (e: Error) => toast.error(e.message || `Could not save the ${role} repository`),
  });
  const id = `repo-${role}`;
  const changed = url.trim() !== (current?.url ?? "") || branch.trim() !== (current?.branch ?? "");
  return (
    <form
      className="space-y-2"
      aria-label={ROLE_TEXT[role].title}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div>
        <p className="text-sm font-medium">{ROLE_TEXT[role].title}</p>
        <p className="text-muted-foreground text-xs">{ROLE_TEXT[role].help}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-[1fr_12rem_auto] sm:items-end">
        <div className="space-y-1">
          <Label htmlFor={`${id}-url`}>URL</Label>
          <Input id={`${id}-url`} value={url} onChange={(e) => setUrl(e.target.value)} disabled={!canEdit}
            placeholder="https://github.com/org/repo" />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`${id}-branch`}>Branch</Label>
          <Input id={`${id}-branch`} value={branch} onChange={(e) => setBranch(e.target.value)} disabled={!canEdit}
            placeholder="main" />
        </div>
        {canEdit && (
          <Button type="submit" disabled={!url.trim() || !changed || save.isPending}>
            {save.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
            Save
          </Button>
        )}
      </div>
      {current?.setBy && (
        <p className="text-muted-foreground text-xs">
          Set by {current.setBy}
          {current.updatedAt ? ` on ${new Date(current.updatedAt).toLocaleString()}` : ""}.
        </p>
      )}
    </form>
  );
}

const MODE_TEXT = {
  always: "Any time — a Project Admin may approve in the owner's place whenever needed",
  after_sla: "Only after the owner has had the stage's SLA to decide",
} as const;
const POLICY_TEXT = {
  standard: "Standard",
  pilot: "Pilot",
  strict: "Strict — a Project Admin never stands in for the business owner",
} as const;

function ApprovalSettingsForm({ projectId, current, canEdit }: {
  projectId: ProjectId; current: ApprovalSettings; canEdit: boolean;
}) {
  const qc = useQueryClient();
  const [mode, setMode] = React.useState(current.fallbackMode);
  const [policy, setPolicy] = React.useState(current.policy);
  React.useEffect(() => {
    setMode(current.fallbackMode);
    setPolicy(current.policy);
  }, [current.fallbackMode, current.policy]);
  const save = useMutation({
    mutationFn: () => setApprovalSettings(projectId, mode, policy),
    onSuccess: (data) => {
      toast.success("Approval settings saved");
      qc.setQueryData(qk.modernizationProgramme.approvalSettings(projectId), data);
    },
    onError: (e: Error) => toast.error(e.message || "Could not save the approval settings"),
  });
  const changed = mode !== current.fallbackMode || policy !== current.policy;
  const selectClass = "border-input bg-background h-9 w-full rounded-md border px-3 text-sm";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Sign-off fallback</CardTitle>
        <CardDescription>
          Every Code Modernization version is approved by its owning role, or by a Project Admin of this project in
          their place — with a reason, labelled, and listed in the Cutover Pack. Nobody approves what they produced.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {current.warnings.length > 0 && (
          <ul aria-label="Staffing warnings" className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
            {current.warnings.map((w) => (
              <li key={w} className="flex gap-2">
                <AlertTriangle className="size-4 shrink-0 text-amber-600" aria-hidden />
                {w}
              </li>
            ))}
          </ul>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="fallback-mode">When a Project Admin may stand in</Label>
            <select id="fallback-mode" className={selectClass} value={mode} disabled={!canEdit}
              onChange={(e) => setMode(e.target.value as typeof mode)}>
              {(Object.keys(MODE_TEXT) as (keyof typeof MODE_TEXT)[]).map((m) => (
                <option key={m} value={m}>{MODE_TEXT[m]}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="approval-policy">Policy</Label>
            <select id="approval-policy" className={selectClass} value={policy} disabled={!canEdit}
              onChange={(e) => setPolicy(e.target.value as typeof policy)}>
              {(Object.keys(POLICY_TEXT) as (keyof typeof POLICY_TEXT)[]).map((p) => (
                <option key={p} value={p}>{POLICY_TEXT[p]}</option>
              ))}
            </select>
          </div>
        </div>
        {canEdit && (
          <Button onClick={() => save.mutate()} disabled={!changed || save.isPending}>
            {save.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
            Save approval settings
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

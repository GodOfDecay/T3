"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, GitCompare, History, Loader2, ShieldAlert, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/ui/loading-state";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/hooks/use-session";
import { AGENT_LABEL, GATE_POLICY } from "@/lib/agents";
import {
  compareStageVersions,
  getStageVersion,
  getVersionConsumers,
  getVersionStaleness,
  needsFallbackReason,
  restoreStageVersion,
  producedByMe as isProducer,
  publishStageVersion,
  rejectStageVersion,
  toBackendStage,
  type ArtifactVersionDetail,
} from "@/lib/api/artifact-versions";
import { getVersionPacket, versionExportHref, type Track3Stage } from "@/lib/api/modernization";
import { qk } from "@/lib/api/query-keys";
import { hasPermission } from "@/lib/auth/permissions";
import type { ProjectId } from "@/lib/schemas";

import { VERSION_STATUS } from "./version-history";

/**
 * One recorded brief or assessment, opened from the left rail: the version's own
 * frozen payload, a Word/PDF download of THAT version, and the Sign-off.
 *
 * THE SIGN-OFF IS THE EXISTING STAGE-VERSION GATE. Approve publishes this version (and
 * supersedes an older published one); the backend demands the stage's approve
 * permission and refuses a person approving a version they produced themselves — its
 * message is shown as-is, because "you produced this" and "a newer version is already
 * approved" need different actions from the reader.
 */
export function VersionView({
  projectId,
  stage,
  noun,
  version,
  render,
  latestVersion,
  onRestored,
}: {
  projectId: ProjectId;
  stage: Track3Stage;
  noun: string;
  version: number;
  render: (payload: unknown, detail: ArtifactVersionDetail) => React.ReactNode;
  /** The stage's newest version number — "Restore" is offered on older ones only. */
  latestVersion?: number;
  /** Open the restored copy once it exists. */
  onRestored?: (version: number) => void;
}) {
  const queryClient = useQueryClient();
  const session = useSession();
  const canDecide = hasPermission(session, `artifact:approve_${toBackendStage(stage)}`);
  const gate = GATE_POLICY[stage];

  const detailQ = useQuery({
    queryKey: [...qk.artifactVersions.forStage(projectId, stage), version],
    queryFn: () => getStageVersion(projectId, stage, version),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: qk.artifactVersions.forStage(projectId, stage) });

  // THE FALLBACK FLOW. Approve is tried as-is; a Project Admin approving a Track 3 version
  // that is not theirs to own gets the backend's "fallback needs a reason" refusal, and is
  // then asked for the reason — the rule lives in one place (shared/services/fallback_approval).
  const [fallbackOpen, setFallbackOpen] = React.useState(false);
  const [fallbackReason, setFallbackReason] = React.useState("");
  const publish = useMutation({
    mutationFn: (why?: string) => publishStageVersion(projectId, stage, version, why),
    onSuccess: (v) => {
      toast.success(`${noun[0]!.toUpperCase()}${noun.slice(1)} v${version} approved` +
        (v.approvedAs === "fallback:project_admin" ? " (as Project Admin fallback)" : ""));
      setFallbackOpen(false);
      setFallbackReason("");
      void invalidate();
    },
    onError: (e: Error) => {
      if (needsFallbackReason(e)) {
        setFallbackOpen(true);
        return;
      }
      toast.error(e.message || "Could not approve this version");
    },
  });

  const canProduce = hasPermission(session, "run:create");
  const [restoreOpen, setRestoreOpen] = React.useState(false);
  const [restoreReason, setRestoreReason] = React.useState("");
  const restore = useMutation({
    mutationFn: () => restoreStageVersion(projectId, stage, version, restoreReason.trim()),
    onSuccess: (r) => {
      toast.success(`Restored as ${noun} v${r.version} (a new draft — someone else approves it)`);
      setRestoreOpen(false);
      setRestoreReason("");
      void invalidate();
      onRestored?.(r.version);
    },
    onError: (e: Error) => toast.error(e.message || "Could not restore this version"),
  });
  const [comparing, setComparing] = React.useState(false);

  const [rejecting, setRejecting] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const reject = useMutation({
    mutationFn: () => rejectStageVersion(projectId, stage, version, reason.trim()),
    onSuccess: () => {
      toast.success(`${noun[0]!.toUpperCase()}${noun.slice(1)} v${version} rejected`);
      setRejecting(false);
      setReason("");
      void invalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Could not reject this version"),
  });

  if (detailQ.isLoading) return <LoadingState variant="card" />;
  if (detailQ.isError || !detailQ.data) {
    return (
      <ErrorState
        title={`${noun} v${version} could not be loaded`}
        description={detailQ.error instanceof Error ? detailQ.error.message : "Unknown error."}
        onRetry={() => detailQ.refetch()}
      />
    );
  }

  const detail = detailQ.data;
  const meta = VERSION_STATUS[detail.status];
  const busy = publish.isPending || reject.isPending;
  // SAY WHY, BEFORE THE CLICK (Lessons R14). The backend refuses self-approval either way;
  // a producer shown an Approve button learns that only from an error toast. Rejecting
  // your own version stays allowed — blocking it would strand a wrong brief.
  const producedByMe = isProducer(detail.producedBy, session?.user);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted/20 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium capitalize">
            {noun} v{detail.version}
          </span>
          <Badge variant={meta.variant}>{meta.label}</Badge>
          {detail.status === "rejected" && detail.rejectionReason && (
            <span className="text-muted-foreground text-xs">Reason: {detail.rejectionReason}</span>
          )}
          {detail.status === "published" && detail.publishedAt && (
            <span className="text-muted-foreground text-xs">
              Approved {new Date(detail.publishedAt).toLocaleString()}
            </span>
          )}
          {detail.approvedAs === "fallback:project_admin" && (
            <Badge variant="outline" title={detail.fallbackReason ?? undefined}>
              <ShieldAlert className="size-3" aria-hidden /> Approved by Project Admin (fallback)
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={versionExportHref(projectId, stage, version, "docx")} download>
              <Download className="size-4" aria-hidden />
              Word (.docx)
            </a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={versionExportHref(projectId, stage, version, "pdf")} download>
              <Download className="size-4" aria-hidden />
              PDF
            </a>
          </Button>
          {version > 1 && (
            <Button size="sm" variant="outline" onClick={() => setComparing((c) => !c)} aria-pressed={comparing}>
              <GitCompare className="size-4" aria-hidden />
              {comparing ? "Hide changes" : `Compare with v${version - 1}`}
            </Button>
          )}
          {canProduce && latestVersion !== undefined && version < latestVersion && (
            <Button size="sm" variant="outline" onClick={() => setRestoreOpen(true)} disabled={restore.isPending}>
              <History className="size-4" aria-hidden />
              Restore this version
            </Button>
          )}
          {canDecide && detail.status === "draft" && !producedByMe && (
            <>
              <Button size="sm" onClick={() => publish.mutate(undefined)} disabled={busy}>
                {publish.isPending ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <CheckCircle2 className="size-4" aria-hidden />
                )}
                Approve
              </Button>
              <Button size="sm" variant="outline" onClick={() => setRejecting(true)} disabled={busy}>
                <XCircle className="size-4" aria-hidden />
                Reject
              </Button>
            </>
          )}
        </div>
      </div>
      {detail.status === "draft" &&
        (producedByMe ? (
          <p role="note" className="-mt-4 text-xs text-amber-700 dark:text-amber-400">
            You produced this {noun}, so you can&apos;t approve it — a {gate.ownerLabel} who didn&apos;t
            produce it, or a Project Admin, approves or rejects it. The one who produced a version decides it
            neither way.
          </p>
        ) : (
          <p className="text-muted-foreground -mt-4 text-xs">
            {gate.title.replace(/^Gate: /, "Sign-off: ")} — {gate.ownerLabel} or Project Admin, and not the
            person who produced it.
          </p>
        ))}

      {detail.restoredFrom != null && (
        <p className="text-muted-foreground -mt-4 text-xs">
          Restored from v{detail.restoredFrom}
          {detail.restoreReason ? ` — ${detail.restoreReason}` : ""}.
        </p>
      )}
      {detail.approvedAs === "fallback:project_admin" && detail.fallbackReason && (
        <p className="text-muted-foreground -mt-4 text-xs">Fallback reason: {detail.fallbackReason}</p>
      )}

      <Staleness projectId={projectId} stage={stage} version={detail.version} noun={noun} />
      {(detail.status === "draft" || detail.status === "published") && (
        <HandOver projectId={projectId} stage={stage} version={detail.version} noun={noun}
          approved={detail.status === "published"} />
      )}

      {comparing && version > 1 && (
        <Comparison projectId={projectId} stage={stage} from={version - 1} to={version} />
      )}

      {(detail.status === "published" || detail.status === "superseded") && (
        <ReadBy projectId={projectId} stage={stage} version={detail.version} noun={noun} />
      )}

      {render(detail.payload, detail)}

      <Dialog open={fallbackOpen} onOpenChange={setFallbackOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve {noun} v{version} as Project Admin</DialogTitle>
            <DialogDescription>
              You are approving in place of the {gate.ownerLabel}. It is recorded as a fallback decision, with
              your reason, and listed in the Cutover Pack.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="Fallback reason"
            value={fallbackReason}
            onChange={(e) => setFallbackReason(e.target.value)}
            placeholder="e.g. The BA is on leave until the 14th and the brief blocks design work."
            rows={3}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setFallbackOpen(false)}>Cancel</Button>
            <Button onClick={() => publish.mutate(fallbackReason.trim())}
              disabled={!fallbackReason.trim() || publish.isPending}>
              {publish.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
              Approve as fallback
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={restoreOpen} onOpenChange={setRestoreOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Restore {noun} v{version}</DialogTitle>
            <DialogDescription>
              This creates a NEW draft with the content of v{version}. Nothing is deleted, and someone other
              than you approves the new version. Work built on the current version will show as out of date
              once the restored one is approved.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="Restore reason"
            value={restoreReason}
            onChange={(e) => setRestoreReason(e.target.value)}
            placeholder="Why go back to this version?"
            rows={3}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRestoreOpen(false)}>Cancel</Button>
            <Button onClick={() => restore.mutate()} disabled={!restoreReason.trim() || restore.isPending}>
              {restore.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
              Restore as a new version
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rejecting} onOpenChange={setRejecting}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Reject {noun} v{version}
            </DialogTitle>
            <DialogDescription>
              Say what is wrong — the reason stays on the version, and the agent sees it next time.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. The target stack should be .NET 8 on Kubernetes, not App Service."
            rows={4}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejecting(false)}>
              Cancel
            </Button>
            <Button onClick={() => reject.mutate()} disabled={!reason.trim() || reject.isPending}>
              {reject.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


/** Backend consumer ids → how the page names them. `code_review` is the one backend stage
 *  whose UI id differs; anything unknown is shown as-is rather than dropped. */
function consumerLabel(stage: string): string {
  const id = stage === "code_review" ? "review" : stage;
  return (AGENT_LABEL as Record<string, string>)[id] ?? stage;
}

/**
 * "Read by" — which agents built on this approved version, when, and whether through an
 * owner-granted exception. The evidence the platform records on every `read_upstream`
 * (`artifact_consumptions`): it is how a BA sees that Dependency and Risk assessed against
 * THIS brief, and what a newer brief would leave out of date.
 */
export function ReadBy({
  projectId,
  stage,
  version,
  noun,
}: {
  projectId: ProjectId;
  stage: Track3Stage;
  version: number;
  noun: string;
}) {
  const q = useQuery({
    queryKey: [...qk.artifactVersions.forStage(projectId, stage), version, "consumers"],
    queryFn: () => getVersionConsumers(projectId, stage, version),
  });
  if (q.isLoading) return null;
  if (q.isError || !q.data) {
    return (
      <p className="text-muted-foreground text-xs">
        Who has read this {noun} could not be loaded.
      </p>
    );
  }
  const reads = q.data.consumers;
  return (
    <section aria-label={`Agents that read this ${noun}`} className="rounded-lg border p-3">
      <h3 className="text-sm font-medium">Read by</h3>
      {reads.length === 0 ? (
        <p className="text-muted-foreground mt-1 text-xs">
          No agent has built on this {noun} yet.
        </p>
      ) : (
        <ul className="mt-2 space-y-1 text-xs">
          {reads.map((r, i) => (
            <li key={`${r.consumerStage}-${r.consumedAt ?? i}`} className="flex flex-wrap gap-x-2">
              <span className="font-medium">{consumerLabel(r.consumerStage)}</span>
              <span className="text-muted-foreground">
                {r.consumedAt ? new Date(r.consumedAt).toLocaleString() : "time not recorded"}
              </span>
              {r.viaGrant && <Badge variant="outline">by exception</Badge>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * "Out of date" — an input this version was built from now has a NEWER APPROVED version
 * (research §5.3). A newer draft does not count. Silent when current, or when the version
 * recorded no inputs (then there is nothing to compare, and "current" would be a claim).
 */
export function Staleness({ projectId, stage, version, noun }: {
  projectId: ProjectId; stage: Track3Stage; version: number; noun: string;
}) {
  const q = useQuery({
    queryKey: [...qk.artifactVersions.forStage(projectId, stage), version, "staleness"],
    queryFn: () => getVersionStaleness(projectId, stage, version),
  });
  if (!q.data || !q.data.stale) return null;
  return (
    <div role="status" className="flex gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
      <AlertTriangle className="size-4 shrink-0 text-amber-600" aria-hidden />
      <div>
        <p className="font-medium">This {noun} is out of date.</p>
        {q.data.inputs.map((i) => (
          <p key={i.stage}>
            It was built from {(AGENT_LABEL as Record<string, string>)[i.stage] ?? i.stage} v{i.pinned}
            {i.rejected ? ", which was later rejected" : ""}
            {i.latest != null ? `; v${i.latest} has since been approved` : ""}. Nothing changes until someone
            revises it.
          </p>
        ))}
      </div>
    </div>
  );
}

/** What differs between two versions, leaf by leaf. */
export function Comparison({ projectId, stage, from, to }: {
  projectId: ProjectId; stage: Track3Stage; from: number; to: number;
}) {
  const q = useQuery({
    queryKey: [...qk.artifactVersions.forStage(projectId, stage), "compare", from, to],
    queryFn: () => compareStageVersions(projectId, stage, from, to),
  });
  if (q.isLoading) return <LoadingState variant="card" />;
  if (q.isError || !q.data) return <p className="text-muted-foreground text-xs">The comparison could not be loaded.</p>;
  const diffs = q.data.differences;
  const show = (v: unknown) => (v === null || v === undefined ? "—" : typeof v === "string" ? v : JSON.stringify(v));
  return (
    <section aria-label={`Changes from v${from} to v${to}`} className="rounded-lg border p-3">
      <h3 className="text-sm font-medium">Changes from v{from} to v{to}</h3>
      {diffs.length === 0 ? (
        <p className="text-muted-foreground mt-1 text-xs">No differences.</p>
      ) : (
        <ul className="mt-2 space-y-1 text-xs">
          {diffs.map((d) => (
            <li key={d.path} className="grid gap-1 sm:grid-cols-[minmax(0,14rem)_5rem_1fr]">
              <code className="truncate">{d.path}</code>
              <span className="text-muted-foreground">{d.change}</span>
              <span className="break-words">
                {d.change === "changed" ? `${show(d.before)} → ${show(d.after)}` : show(d.change === "added" ? d.after : d.before)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Whether this version can be handed to the next agent (Phase D): the packet Target
 * Architecture reads, validated by the hand-over models. Ready is one quiet line; not ready
 * lists why, so the gap is fixed on this page and not discovered by the next agent.
 */
const HANDOVER_SHOWN = 6;

/** Who reads each stage's packet next (Development Plan §5 hand-over order). */
export const HANDED_TO: Record<Track3Stage, string> = {
  requirements_modernization: "Target Architecture",
  discovery: "Target Architecture",
  design_modernization: "Migration Strategy",
  strategy: "Equivalence Testing",
};

/** Only a draft or an approved version is ever handed over: a rejected or superseded one says
 *  nothing here (the caller does not render this for them). A draft is handed over once approved. */
export function HandOver({ projectId, stage, version, noun, approved }: {
  projectId: ProjectId; stage: Track3Stage; version: number; noun: string; approved: boolean;
}) {
  const q = useQuery({
    queryKey: [...qk.artifactVersions.forStage(projectId, stage), version, "packet"],
    queryFn: () => getVersionPacket(projectId, stage, version),
  });
  const next = HANDED_TO[stage];
  if (q.isError) {
    return (
      <p aria-label="Hand-over" className="text-muted-foreground -mt-4 text-xs">
        Could not check whether this {noun} can be handed to {next}.
      </p>
    );
  }
  if (!q.data) return null;
  if (q.data.ok) {
    return (
      <p aria-label="Hand-over" className="text-muted-foreground -mt-4 text-xs">
        {approved ? `Ready to hand to ${next}.` : `Ready to hand to ${next} once approved.`}
      </p>
    );
  }
  const shown = q.data.problems.slice(0, HANDOVER_SHOWN);
  const more = q.data.problems.length - shown.length;
  return (
    <div aria-label="Hand-over" role="status" className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
      <p className="font-medium">This {noun} is not yet ready to hand to {next}:</p>
      <ul className="mt-1 list-disc pl-4">
        {shown.map((p) => <li key={p}>{p}</li>)}
      </ul>
      {more > 0 && <p className="mt-1">…and {more} more.</p>}
    </div>
  );
}

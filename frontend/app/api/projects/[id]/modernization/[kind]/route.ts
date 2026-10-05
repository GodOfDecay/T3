import { type NextRequest } from "next/server";

import { bffProxy } from "@/lib/bff/proxy";

/**
 * Track 3 (Code Modernization) — what a project's first two agents recorded, proxied
 * to FastAPI `GET /projects/{id}/modernization/{migration-intent|discovery|target-architecture}`.
 *
 * The backend decides who may read it (project membership, the project's TRACK, and
 * the caller's reach to that agent), so this route only forwards — and refuses a kind
 * it does not know rather than proxying an arbitrary path segment.
 */
const KINDS = new Set(["migration-intent", "discovery", "target-architecture", "strategy", "equivalence-testing",
  "migration-development", "migration-review", "modernization-security"]);

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string; kind: string }> },
) {
  const { id, kind } = await params;
  if (!KINDS.has(kind)) return Response.json({ code: "not_found" }, { status: 404 });
  return bffProxy(`/projects/${encodeURIComponent(id)}/modernization/${kind}`);
}

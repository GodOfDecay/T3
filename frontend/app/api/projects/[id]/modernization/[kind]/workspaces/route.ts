import { type NextRequest } from "next/server";

import { bffProxy } from "@/lib/bff/proxy";

/**
 * Track 3 Migration Development — each module's migration workspace (branch, commits by concern, build
 * rounds, tests, lint, the equivalence preview's headline, the push; never code), proxied to FastAPI
 * `GET /projects/{id}/modernization/migration-development/workspaces`. Only that kind has workspaces.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string; kind: string }> },
) {
  const { id, kind } = await params;
  if (kind !== "migration-development") return Response.json({ code: "not_found" }, { status: 404 });
  return bffProxy(`/projects/${encodeURIComponent(id)}/modernization/migration-development/workspaces`);
}

import { type NextRequest } from "next/server";

import { bffProxy } from "@/lib/bff/proxy";

/**
 * Track 3 — what the project's pulled legacy code exposes and consumes (HTTP endpoints, files,
 * scheduled jobs, tables, queues): the inventory the Target Architecture agent freezes its
 * contracts from. Proxied to FastAPI `GET /projects/{id}/modernization/legacy-code/interfaces`.
 */
const STAGES = new Set(["design_modernization"]);

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const stage = req.nextUrl.searchParams.get("stage") ?? "design_modernization";
  if (!STAGES.has(stage)) return Response.json({ code: "not_found" }, { status: 404 });
  return bffProxy(
    `/projects/${encodeURIComponent(id)}/modernization/legacy-code/interfaces?${new URLSearchParams({ stage }).toString()}`,
  );
}

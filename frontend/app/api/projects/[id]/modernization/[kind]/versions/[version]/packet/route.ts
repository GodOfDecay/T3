import { type NextRequest } from "next/server";

import { forward } from "@/lib/bff/forward";

type P = { params: Promise<{ id: string; kind: string; version: string }> };

const KINDS = new Set(["migration-intent", "discovery", "target-architecture", "strategy"]);

/** What a version hands the next agent: `{ok, problems, packet}` (Phase D). */
export async function GET(req: NextRequest, { params }: P) {
  const { id, kind, version } = await params;
  if (!KINDS.has(kind)) return Response.json({ code: "not_found" }, { status: 404 });
  return forward(
    req,
    `/projects/${encodeURIComponent(id)}/modernization/${encodeURIComponent(kind)}/versions/${encodeURIComponent(version)}/packet`,
  );
}

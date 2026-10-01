import { type NextRequest } from "next/server";

import { bffProxy } from "@/lib/bff/proxy";

/**
 * Track 3 Equivalence Testing — the project's baseline captures (status, times, counts and masked
 * shapes; never a recording), proxied to FastAPI
 * `GET /projects/{id}/modernization/equivalence-testing/captures`. Only that kind has captures.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string; kind: string }> },
) {
  const { id, kind } = await params;
  if (kind !== "equivalence-testing") return Response.json({ code: "not_found" }, { status: 404 });
  return bffProxy(`/projects/${encodeURIComponent(id)}/modernization/equivalence-testing/captures`);
}

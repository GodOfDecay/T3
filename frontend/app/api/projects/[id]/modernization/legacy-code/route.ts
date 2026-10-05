import { type NextRequest } from "next/server";

import { bffProxy } from "@/lib/bff/proxy";

/**
 * Track 3 — the project's pulled legacy code, proxied to FastAPI
 * `GET|POST /projects/{id}/modernization/legacy-code`.
 *
 * `stage` names the page asking (every Track 3 stage that reads the code: the backend
 * `legacy_code.TRACK3_STAGES`, pinned by `tests/modernization_common/test_legacy_code_bff_stages.py`): the backend checks the
 * caller's reach to THAT agent, and tries that stage's repository connection first for
 * a private repository's credential. Anything else is refused here rather than proxied.
 */
const STAGES = new Set(["requirements_modernization", "discovery", "design_modernization", "testing_modernization",
  "development_modernization"]);

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const stage = req.nextUrl.searchParams.get("stage") ?? "requirements_modernization";
  if (!STAGES.has(stage)) return Response.json({ code: "not_found" }, { status: 404 });
  return bffProxy(
    `/projects/${encodeURIComponent(id)}/modernization/legacy-code?stage=${encodeURIComponent(stage)}`,
  );
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ code: "bad_request", message: "Expected a JSON body." }, { status: 400 });
  }
  return bffProxy(`/projects/${encodeURIComponent(id)}/modernization/legacy-code`, {
    method: "POST",
    body,
  });
}

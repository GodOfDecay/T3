import { type NextRequest } from "next/server";

import { forward } from "@/lib/bff/forward";

type P = { params: Promise<{ projectId: string; stage: string; version: string }> };

/** Restore an earlier version as a new draft (reason required). Track 3 backbone. */
export async function POST(req: NextRequest, { params }: P) {
  const { projectId, stage, version } = await params;
  return forward(req, `/artifact-versions/${encodeURIComponent(projectId)}/stages/${encodeURIComponent(stage)}/versions/${encodeURIComponent(version)}/restore`, {
    method: "POST",
    withBody: true,
  });
}

import { type NextRequest } from "next/server";

import { forward } from "@/lib/bff/forward";

type P = { params: Promise<{ projectId: string; stage: string }> };

/** What differs between two versions of a stage (`?from=&to=`). */
export async function GET(req: NextRequest, { params }: P) {
  const { projectId, stage } = await params;
  return forward(req, `/artifact-versions/${encodeURIComponent(projectId)}/stages/${encodeURIComponent(stage)}/compare`, {
    withQuery: true,
  });
}

import { type NextRequest } from "next/server";

import { forward } from "@/lib/bff/forward";

type P = { params: Promise<{ projectId: string; role: string }> };

/** Name the legacy or the target repository (Project Admin of this project). */
export async function PUT(req: NextRequest, { params }: P) {
  const { projectId, role } = await params;
  return forward(req, `/modernization-programme/${encodeURIComponent(projectId)}/repositories/${encodeURIComponent(role)}`, {
    method: "PUT",
    withBody: true,
  });
}

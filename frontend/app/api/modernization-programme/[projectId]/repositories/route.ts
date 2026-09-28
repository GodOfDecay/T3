import { type NextRequest } from "next/server";

import { forward } from "@/lib/bff/forward";

type P = { params: Promise<{ projectId: string }> };

/** The project's legacy and target repositories. */
export async function GET(req: NextRequest, { params }: P) {
  const { projectId } = await params;
  return forward(req, `/modernization-programme/${encodeURIComponent(projectId)}/repositories`);
}

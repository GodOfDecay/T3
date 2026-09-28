import { type NextRequest } from "next/server";

import { forward } from "@/lib/bff/forward";

type P = { params: Promise<{ projectId: string }> };

/** Fallback mode, approval policy and staffing warnings. */
export async function GET(req: NextRequest, { params }: P) {
  const { projectId } = await params;
  return forward(req, `/modernization-programme/${encodeURIComponent(projectId)}/approval-settings`);
}

export async function PUT(req: NextRequest, { params }: P) {
  const { projectId } = await params;
  return forward(req, `/modernization-programme/${encodeURIComponent(projectId)}/approval-settings`, {
    method: "PUT",
    withBody: true,
  });
}

// @vitest-environment jsdom
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * Equivalence Testing, Verify mode (Track 3, Phase J) — one module's verification as the QA who accepts it
 * sees it: per-criterion verdicts (not run is never passed), differences by kind with masked shapes and the
 * likely area, performance on BOTH sides ("not measured", never 0), and what accepting records.
 */

vi.mock("@/lib/api/modernization-programme", async (orig) => ({
  ...(await (orig() as Promise<Record<string, unknown>>)),
  getLedger: async () => ({ projectId: "p", states: [], modules: [] }),
}));

import { VerificationView, ms, verificationLedgerText } from "@/components/modernization/verification-view";
import { Verification } from "@/lib/schemas/modernization";

const BASE = {
  mode: "verify", module_id: "M-01", pr: "https://github.com/claimtrack/claimtrack-lite-target/pull/1", runs: 2,
  baselines_replayed: [{ id: "BL-01", version: 1 }, { id: "BL-02", version: 1 }], migration_version: 2,
  head_sha: "4f6a5b7c8d4f6a5b7c8d", baseline_version: 1, module: { name: "claims-api" },
};
const FAILED = Verification.parse({
  ...BASE, module_verdict: "migrating",
  criteria: [{ ec_id: "EC-01", verdict: "passed", cases_compared: 5, normalization_applied: ["generatedAt"] },
    { ec_id: "EC-02", verdict: "failed", cases_compared: 6, normalization_applied: ["settledAt"] },
    { ec_id: "EC-04", verdict: "not_run", cases_compared: null }],
  differences: [{ id: "EQ-001", ec_id: "EC-02", classification: "regression", field: "settle:payout", cases: 2,
    masked_example: "<number> vs <number>", likely_area: "TR-01: claims-api/server.py payout()" }],
  performance: [{ ec_id: "EC-04", legacy_p95_ms: 12.5, target_p95_ms: null, threshold_ms: 250 }],
});
const PASSED = Verification.parse({
  ...BASE, module_verdict: "verified",
  criteria: [{ ec_id: "EC-01", verdict: "passed", cases_compared: 5 }, { ec_id: "EC-04", verdict: "passed", cases_compared: 25 }],
  performance: [{ ec_id: "EC-04", legacy_p95_ms: 12.5, target_p95_ms: 9.1, threshold_ms: 250 }],
});

function wrap(ui: React.ReactElement) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}
afterEach(cleanup);

describe("a verification", () => {
  it("shows a failing criterion, the regression's shape and likely area, and a criterion not run as not run", () => {
    wrap(<VerificationView verification={FAILED} />);
    expect(screen.getByText("fails — back to Migration Development")).toBeTruthy();
    const crit = screen.getByRole("table", { name: "Criteria" });
    expect(within(crit).getByText("failed")).toBeTruthy();
    expect(within(crit).getByText("not run")).toBeTruthy();
    expect(crit.textContent).not.toMatch(/EC-04passed/);
    const diffs = screen.getByRole("region", { name: "Differences" }).textContent ?? "";
    expect(diffs).toContain("settle:payout in 2 case(s)");
    expect(diffs).toContain("<number> vs <number>");
    expect(diffs).toContain("likely TR-01: claims-api/server.py payout()");
    expect(screen.getByRole("table", { name: "Performance" }).textContent).toContain("not measured");
  });

  it("shows a verified module with both sides' p95 and the baselines replayed", () => {
    wrap(<VerificationView verification={PASSED} />);
    expect(screen.getByText("verified")).toBeTruthy();
    const perf = screen.getByRole("table", { name: "Performance" }).textContent ?? "";
    expect(perf).toContain("12.5 ms");
    expect(perf).toContain("9.1 ms");
    expect(screen.getByRole("region", { name: "Verification summary" }).textContent).toContain("BL-01, BL-02");
    expect(screen.getByText(/No difference after each criterion/)).toBeTruthy();
  });

  it("says what accepting records, and never more", () => {
    expect(verificationLedgerText(PASSED, false, "draft")).toContain("records M-01 as verified");
    expect(verificationLedgerText(FAILED, false, "draft")).toContain("sends M-01 back to Migration Development");
    expect(verificationLedgerText(PASSED, false, "draft")).toContain("older migration record is refused");
    expect(verificationLedgerText(PASSED, true, "published", "verified")).toBe("Accepted: the module is verified.");
    expect(verificationLedgerText(FAILED, false, "rejected")).toContain("records nothing");
    expect(ms(null)).toBe("not measured");
    expect(ms(0)).toBe("0 ms");
  });
});

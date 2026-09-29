// @vitest-environment jsdom
import * as React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";

import { AssessmentView } from "@/components/modernization/assessment-view";
import { MigrationBriefCard } from "@/components/modernization/migration-brief-card";
import { DiscoveryAssessment, MigrationIntentBrief } from "@/lib/schemas/modernization";

import fixtures from "./fixtures.json";

/**
 * Phase D (research §6.1, §6.2): what agents 1 and 2 now hand over, on their pages.
 *   brief       "Must not change" in the user's words; success measures grouped by kind;
 *               an older brief's measures (no kind) shown as not yet classified.
 *   assessment  stable M-xx ids; "Not assessable statically"; the golden-master pointer.
 */
afterEach(cleanup);

const brief = MigrationIntentBrief.parse({
  ...fixtures.brief,
  must_not_change: ["the /api/v1 claims API brokers call", "Bank payment file format (BACS Standard 18)"],
  success_measures: [
    { metric: "Claim payouts identical", current: "", target: "100% on replay", kind: "equivalence" },
    { metric: "p95 claim lookup", current: "2.1s", target: "< 800ms", kind: "performance" },
    { metric: "Old measure", current: "", target: "x" },
  ],
});

describe("the brief", () => {
  it("lists what must not change, quoted", () => {
    render(<MigrationBriefCard brief={brief} />);
    const list = screen.getByRole("list", { name: "Must not change" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "the /api/v1 claims API brokers call", "Bank payment file format (BACS Standard 18)"]);
    expect(list.querySelectorAll("q")).toHaveLength(2);
  });

  it("does not call unchecked wording the user's own words", () => {
    render(<MigrationBriefCard brief={{ ...brief, must_not_change_verified: false }} />);
    expect(screen.getByText(/Not checked against the conversation/)).toBeTruthy();
    expect(screen.queryByText(/In the user.s own words/)).toBeNull();
  });

  it("has no must-not-change section when none was recorded", () => {
    render(<MigrationBriefCard brief={{ ...brief, must_not_change: [] }} />);
    expect(screen.queryByRole("list", { name: "Must not change" })).toBeNull();
  });

  it("groups success measures by kind, unclassified last", () => {
    render(<MigrationBriefCard brief={brief} />);
    const [equivalence, performance, unclassified] = ["Equivalence measures", "Performance measures",
      "Unclassified measures"].map((name) => screen.getByRole("region", { name })) as [HTMLElement, HTMLElement, HTMLElement];
    expect(equivalence.textContent).toContain("Claim payouts identical");
    expect(performance.textContent).toContain("p95 claim lookup");
    expect(unclassified.textContent).toContain("Not yet classified");
    expect(equivalence.compareDocumentPosition(unclassified) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("reads an unknown kind as not classified rather than failing the page", () => {
    const b = MigrationIntentBrief.parse({ ...fixtures.brief, success_measures: [{ metric: "m", target: "t", kind: "vibes" }] });
    expect(b.success_measures[0]?.kind).toBeNull();
  });
});

const assessment = DiscoveryAssessment.parse({
  ...fixtures.assessment,
  modules: fixtures.assessment.modules.map((m: Record<string, unknown>, i: number) => ({ ...m, id: `M-0${i + 1}` })),
  not_assessable_statically: [
    { topic: "runtime", modules: ["M-02"], question: "M-02 declares Java 7 but depends on guava 23.0; which Java does it run on?" },
    { topic: "configuration", modules: [], question: "Environment-specific configuration is held in each environment." },
  ],
});

describe("the assessment", () => {
  it("shows each module's stable id", () => {
    render(<AssessmentView assessment={assessment} />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Id" })).toBeTruthy();
    expect(table.textContent).toContain("M-01");
  });

  it("says what it could not assess, as questions", () => {
    render(<AssessmentView assessment={assessment} />);
    const section = screen.getByRole("region", { name: "Not assessable statically" });
    expect(section.textContent).toContain("which Java does it run on?");
    expect(section.textContent).toContain("Environment-specific configuration");
  });

  it("points at the golden master, captured or not", () => {
    const { unmount } = render(<AssessmentView assessment={assessment} />);
    expect(screen.getByLabelText("Golden master").textContent).toMatch(/not captured yet — the Equivalence Testing agent/);
    unmount();
    render(<AssessmentView assessment={{ ...assessment, golden_master: { status: "captured", note: "", baselines: ["BL-01", "BL-02"] } }} />);
    expect(screen.getByLabelText("Golden master").textContent).toContain("captured — BL-01, BL-02");
  });

  it("an older assessment with no ids or questions still renders", () => {
    // Schema 1: no module ids, no questions.
    const { not_assessable_statically: _unused, ...schema1 } = fixtures.assessment as Record<string, unknown>;
    const old = DiscoveryAssessment.parse({
      ...schema1, schema_version: 1,
      modules: fixtures.assessment.modules.map(({ id: _id, ...m }: Record<string, unknown>) => m),
    });
    render(<AssessmentView assessment={old} />);
    expect(screen.queryByRole("region", { name: "Not assessable statically" })).toBeNull();
    expect(screen.getByRole("table").textContent).toContain("—");
  });
});

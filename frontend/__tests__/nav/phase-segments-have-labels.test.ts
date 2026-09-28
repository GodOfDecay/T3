import { describe, expect, it } from "vitest";

import { PHASE_LABEL, phaseRoute } from "@/lib/agents";
import { prettySegment, segmentLabels } from "@/lib/nav";

/**
 * Every agent's URL segment must have a breadcrumb label, and it must be the label the
 * page itself uses.
 *
 * THE BUG THIS CATCHES. `plan` was missing from `segmentLabels`, so `prettySegment`
 * fell back to title-casing the URL segment and the breadcrumb read "Plan" above a page
 * headed "Project Manager". Nothing failed — the fallback is deliberate and produces a
 * plausible-looking word, which is exactly why the gap survived: a missing entry is
 * indistinguishable from a correct one for any segment whose label happens to be its
 * own name. `plan` is the one phase where the two differ.
 */

/** Phase key -> route segment: the app's own `phaseRoute`, not a copy of it.
 *
 * This file used to keep its own map ("underscores become hyphens", plus `review`),
 * which was right until Track 3's agents got route names of their own
 * (`design_modernization` → `target-architecture`); a hand-kept copy is the drift this
 * test exists to catch elsewhere. */
const routeSegment = (phase: string) => phaseRoute(phase as keyof typeof PHASE_LABEL);

describe("breadcrumb labels for agent pages", () => {
  it("names every phase, and names it the way the page does", () => {
    const wrong: string[] = [];
    for (const [phase, label] of Object.entries(PHASE_LABEL)) {
      const seg = routeSegment(phase);
      const crumb = prettySegment(seg);
      if (crumb !== label) wrong.push(`${seg}: breadcrumb "${crumb}" vs page "${label}"`);
    }
    expect(wrong.join(" | ")).toBe("");
  });

  it("resolves plan to Project Manager rather than title-casing the segment", () => {
    /** Non-vacuity for the sweep above: this is the one phase whose label is not just
     *  its own segment capitalised, so it is the only case the fallback could fake. */
    expect(segmentLabels["plan"]).toBe("Project Manager");
    expect(prettySegment("plan")).toBe("Project Manager");
  });

  it("still title-cases a segment nobody has named", () => {
    /** The fallback is deliberate and must keep working — this test is about phases
     *  having entries, not about removing the default. */
    expect(prettySegment("some-new-thing")).toBe("Some New Thing");
  });
});

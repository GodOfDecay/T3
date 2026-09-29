# Click-through — Track 3 Phase E (Target Architecture)

For you to run in a browser. Nothing here was verified in a browser by me. Every check was at the test
level: render tests against backend-produced fixtures and real-Postgres tests through the real app, with
every guard mutation-proven (see `build-log.md` Entry 11). Tick each step and note anything that differs.

**Before you start:**
- The dev database needs migrations **0068–0071** (0071 is new in this phase: `runs.target_design_artifacts`
  and `design_modernization` in the Orchestrator deliverables check). Apply with
  `cd backend && uv run python -m alembic upgrade head` — only once you agree.
- Start both servers fresh (backend on 8001).
- **The tile is still "Coming soon"** (R42: it flips after this click-through). Open the page by URL:
  `/projects/<project id>/target-architecture`. Everything else — the socket, the Orchestrator, the
  track check — is live.
- You need a Track 3 project with an **approved** brief (Migration Intent) and an **approved**
  assessment (Dependency and Risk), both from Phase D, and the legacy code pulled.

Personas as before. The **Architect** is `architect@gmail.com`; you need a **second Architect** or a
Project Admin (`projadmin@gmail.com`) to approve, because the producer cannot.

## A. The page

| # | As | Do | Expect |
|---|---|---|---|
| A1 | Architect | Open `/target-architecture` on a **Greenfield** project | "Target Architecture is a Code Modernization agent" — no chat, no documents |
| A2 | Architect | Open it on the Track 3 project | Header: intro, legacy-code status, Programme strip, tech-stack chip, **Legacy interfaces**, model picker, **Run Target Architecture agent**. Left: **Target designs** (empty) and **Documents** for this stage. Centre: the four-step guide |
| A3 | Architect | Click **Legacy interfaces** | A dialog lists what the code exposes and consumes — HTTP endpoints (with the class prefix, e.g. `GET /api/v1/claims/{id}`), files written/read, scheduled jobs, tables, queues — each with `file:line` and module id. Filter by kind and by text work |
| A4 | Developer (no reach) | Open the page | The chat refuses; the interfaces dialog does not load (403) |

## B. Designing

| # | As | Do | Expect |
|---|---|---|---|
| B1 | Architect | Open the chat and say "hi" | "Hi — I'm the Target Architecture agent on the SDLC Platform", then which brief version, assessment version and commit it works from. It does not start designing unasked |
| B2 | Architect | "Design the target architecture" | It reads the brief, the assessment and the interface inventory, reads the code behind its choices, and **asks the assessment's "Not assessable statically" questions** rather than assuming them. At most three questions at a time |
| B3 | Architect | Answer, then read the compact proposal | Under ~300 words: one line per part (today → target), one line per module (pattern + why), the frozen contracts, the biggest decisions, then "Does this look right…?" Nothing recorded yet |
| B4 | Architect | "Go ahead and record it" | A new **target design v1 (draft)** on the left, opening by itself. The reply is short: recorded, the headline (e.g. "5 modules: …; 4 frozen contracts; 7 traps; 8 ADRs"), next steps |
| B5 | Architect | Try to make it record something wrong: "use Java 17 for the batch" is fine; **"use Node 18"**, or **"drop the reports module"**, or **"change M-03's tier to mechanical"** | The recording is refused and the agent tells you why in words (end of life / every assessed module needs a pattern / never change a tier) and fixes or asks |
| B6 | Architect | Ask it to add a contract the code does not show and the brief did not name, and call it confirmed | It records it as **proposed** (or refuses "confirmed"), never as confirmed |
| B7 | Architect | Remove the brief's approval first (or use a project with no assessment) and ask it to record | "NOT RECORDED — a target design is checked against the brief and the assessment", naming which is missing |

## C. Reading the design

| # | As | Do | Expect |
|---|---|---|---|
| C1 | Architect | Open v1 | Sources line (brief v1 approved, assessment v1 approved, commit, N legacy interfaces), summary, six stats, the pattern mix |
| C2 | Architect | **Overview** | Target per part (today → target), how old and new coexist, ordering constraints, data migration, NFRs, security |
| C3 | Architect | **Modules** → click a row | Detail joins its contracts, traps and ADRs, and explains each pattern. The pattern filter works |
| C4 | Architect | **Contracts** | Each: kind, **Confirmed** or **Proposed — needs confirming**, the brief's words in quotes (for must-not-change items), where it is defined, consumers, proof |
| C5 | Architect | **Traps**, **Decisions** | Traps cite a file/folder/pattern. Each ADR marks the chosen option with a tick; departures from the brief are highlighted |
| C6 | Architect | **Diagrams** | AS-IS, TRANSITION and TO-BE render (Mermaid), with zoom and SVG/PNG export |
| C7 | Architect | **Questions** | The assessment's questions with the answer and its source (user / document); any still open in amber |
| C8 | Architect | Word, PDF | Both download that version, with every section |
| C9 | Architect | The hand-over line under the header | "Ready to hand to **Migration Strategy** once approved" (not "Target Architecture") |

## D. Sign-off and the ledger

| # | As | Do | Expect |
|---|---|---|---|
| D1 | Architect (producer) | Look at v1 | No Approve/Reject; "You produced this target design, so you can't approve it…" |
| D2 | Any | The **Module ledger** panel | "Approving this version puts these N modules on the migration ledger as 'designed'", each "not on the ledger yet" |
| D3 | Second Architect | **Approve** | Approved. The ledger panel now says the design is approved and shows each module as **Designed**. The Programme page shows them in the Designed column |
| D4 | Project Admin | On a new draft (v2), **Approve** | Asked for a reason (fallback). Approved "as Project Admin fallback", the reason shown |
| D5 | Architect | Make the assessment change underneath (re-run it on a different commit so ids move), design again, and try to approve | Refused (409): "M-0x is <path> on the ledger but <other path> in this design — the module ids changed between assessed commits". The version stays a draft and the ledger is unchanged |
| D6 | BA | Approve a newer brief | The design shows **out of date** (built from brief v1; v2 approved since) |

## E. Going back and the Orchestrator

| # | As | Do | Expect |
|---|---|---|---|
| E1 | Architect | In the page chat: "go back to version 1" | It shows what differs, asks to confirm, then restores as a **new** draft |
| E2 | Architect | Orchestrator on the Track 3 project: "run the target architecture agent" (or "open the design agent") | Target Architecture runs (not Portfolio 1's Design). On a Greenfield project, "design" means Portfolio 1's Design |
| E3 | Architect | In that conversation, have it record a design | "Recorded in this Orchestrator conversation — the target design is in its Deliverables". No version appears on the page |

## Known gaps

- **Not run live by me.** The agent's model behaviour (asking before recording, the 300-word summary)
  is prompt-driven; every rule that can be checked in code is enforced by `record_target_design`.
- The interface inventory is a **pattern scan**: an interface built at run time can be missed, and a
  match can be a false positive. The UI and the prompt say so; a contract it cannot see stays proposed.
- End-of-life checks cover the runtimes in the lifecycle table (.NET, Java, Node.js, Python). A version of
  anything else (e.g. MySQL, Spring Boot) is not checked — it is not claimed to be.
- A module's ledger row is created on approval. Removing a module from a later design does not delete
  its row (the ledger never loses history); reconcile it on the Programme page.

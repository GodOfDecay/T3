# Click-through — Track 3 Phase F (Migration Strategy + the universal pass)

This is for you to run in a browser. I have not verified any of it in a browser. Every check was at the test
level: render tests against backend-produced fixtures, and real-Postgres tests through the real app, with
every guard mutation-proven (see `build-log.md` Entry 12). Tick each step and note anything that differs.

**Before you start:**
- The dev database needs migration **0072**. It adds `runs.strategy_artifacts` and adds `strategy` to the
  Orchestrator deliverables check. Apply it with `cd backend && uv run python -m alembic upgrade head`, and
  only once you agree. **Restart the backend afterwards**, because the ORM now maps the new column.
- Start both servers fresh (the backend on 8001).
- You need a Track 3 project with an **approved** brief, an **approved** assessment and an **approved**
  target design (the Phase D and E steps). Approving the design is what puts the modules on the ledger.
- The Architect is `architect@gmail.com`. Approval needs a **second Architect** or `projadmin@gmail.com`.

## U. The universal pass (earlier agents)

| # | As | Do | Expect |
|---|---|---|---|
| U1 | Architect | On **Migration Intent**, tell it "we freeze changes from 1 Dec, the regulator reviews on 15 Jan, the cutover window is Saturday 22:00–02:00, and data must stay in the EU" | The brief's key facts show a **Cutover window** fact and a **Data residency** fact. The freeze and the review are recorded as dated milestones (freeze and external) |
| U2 | Architect | On **Target Architecture**, propose a target on **MySQL 8.0**, **PostgreSQL 12**, **PHP 7.4** or **SQL Server 2014** | The record is refused as end of life. MySQL 8.4 / PostgreSQL 16 / PHP 8.3 are accepted. "Azure Database for MySQL Flexible Server 8.0" is still read as MySQL 8.0 |
| U3 | Architect | On a Go, PHP, Ruby, VB.NET, COBOL/JCL repo, or one with OpenAPI/WSDL/.proto/GraphQL files, open **Legacy interfaces** | Entries for that language, e.g. `GET /pay/{id}` from a Go router, `SOAP GetPayslip`, `gRPC Payroll.Run`, `GraphQL Query.employee`, `EXEC SQL` tables, and a k8s CronJob schedule. Declared contracts are marked "(declared)". The kind filter offers RPC and UI |

## A. The page

| # | As | Do | Expect |
|---|---|---|---|
| A1 | Architect | Open `/strategy` on a **Greenfield** project | "Migration Strategy is a Code Modernization agent", with no chat and no documents |
| A2 | Architect | Open it on the Track 3 project | The intro, the Programme strip, the tech-stack chip, the model picker and **Run Migration Strategy agent**. There is **no** legacy-code pull control (this agent does not read code). Left: **Migration plans** (empty) and **Documents**. Centre: the four-step guide "How a migration plan gets made" |
| A3 | Developer (no reach) | Open the page | The chat refuses |

## B. Planning

| # | As | Do | Expect |
|---|---|---|---|
| B1 | Architect | Open the chat and say "hi" | It introduces itself as the Migration Strategy agent and names the brief, assessment and design versions it works from. It does not start planning unasked |
| B2 | Architect | "Plan the migration" | It computes the dependency-safe order first (a cycle is shown as one step), lays waves against the deadline, the freeze, the milestones and the cutover window, and asks what only you can decide. It asks at most three questions at a time |
| B3 | Architect | Agree to the compact proposal: "record it" | A **migration plan v1 (draft)** opens by itself. The reply is short: the headline (waves, modules, criteria, last baseline due, open conflicts, effort) and the next steps |
| B4 | Architect | Try to make it record something wrong: **"move M-02 first"** (it depends on others), **"skip the reports module"**, **"drop the baseline for EC-03"**, **"change M-03 to a rewrite"**, **"don't mention the freeze clash"** | Each is refused and explained in words: a dependency violation without a design ADR, every moved module must be placed, contracts/traps/measures unprotected, the pattern differs from the design, an unreported calendar conflict. It then fixes the plan or asks |
| B5 | Architect | With the design unapproved (or on a project without one), ask it to record | "NOT RECORDED — a migration plan is checked against…", naming what is missing |
| B6 | Architect | Ask for an effort estimate on a module the assessment could not size | "not estimated" for that module and its wave, never a guessed number |
| B7 | Architect | Ask for two **overlapping** waves (say reports Feb–Jun alongside batch Mar–Apr), where the later-numbered wave ends first | Accepted when each module's dependencies cut over first by date. Refused, naming both waves, when a dependency's wave ends after its dependent's, whatever the wave numbers |
| B8 | Architect | Tell it "the business set the W2 dates" when they are not in the brief | It marks them proposed (or records them in the brief first). A plan marking dates "given" that the brief does not hold is refused |
| B9 | Architect | Brief window "Saturday nights 22:00–02:00". Plan a cutover "Sat 23:00 – Sun 01:30", then one "Sat 20:00–02:00" | The first is accepted (the night spills into Sunday). The second is a window-length conflict (6 h against the window's own 4 h) that must be reported |

## C. Reading the plan

| # | As | Do | Expect |
|---|---|---|---|
| C1 | Architect | Open v1 | The sources line and six stats: Waves, Modules planned, Equivalence criteria, Last baseline due, Open calendar conflicts, Effort (estimate). Then the **Timeline** with the freeze, milestones and deadline marked |
| C2 | Architect | **Waves** | Each wave has its modules and patterns, "Why here.", entry/exit criteria, rollback, **Cutover window** and **Parallel run** |
| C3 | Architect | **Criteria**, then filter by module | Each EC names what it protects (contracts, traps, measures) and how it is proven. The filter narrows the list |
| C4 | Architect | **Baselines** | Criterion, Environment, Data source, Masking and the due date. A baseline due after its wave starts is flagged **late** |
| C5 | Architect | **Calendar** | The computed conflicts, each "reported — open", "resolved" or "not reported", plus any you raised |
| C6 | Architect | **Order** | The critical path, cycles marked, "Waits for" / "In the plan" per module, and any **Order exceptions** with their ADR |
| C7 | Architect | **RAID**, **Effort** | Risks and the rest. Effort per wave, from the table and in the plan, ±30%, with "not estimated" where sizes are missing |
| C8 | Architect | Word, PDF | Both download that version with every section |
| C9 | Architect | The hand-over line | "Ready to hand to **Equivalence Testing** once approved" |

## D. Sign-off, the ledger and the board

| # | As | Do | Expect |
|---|---|---|---|
| D1 | Architect (producer) | Look at v1 | There is no Approve/Reject. "You produced this migration plan…" appears instead. The Module ledger says "Approving this version sequences these N modules…" |
| D2 | Second Architect / Project Admin | Approve v1 | It is approved. The ledger panel refreshes: every module is **Sequenced** in its wave |
| D3 | Architect | Record a v2 that moves a module to another wave, then approve it as the second Architect | The modules are re-sequenced (history note "plan revised"). A module already migrating in another wave is refused with "Not approved: …" (409), and v2 stays a draft |
| D3a | Architect | Record a plan while a **newer draft design** changes a module's pattern (or approve a newer design after the plan was recorded), then approve the plan | Refused with "Not approved: M-0x is … in the approved target design but … in this plan — re-plan it against the approved design". A plan that leaves out a module the approved design moves is refused the same way |
| D3b | Architect | After a module is baselined, record a revision that renumbers its criteria and approve it | Refused: "already baselined with criteria …, and its baselines are tied to them" |
| D4 | Reviewer | Reject a version | The ledger text reads "This version was rejected…" and the ledger is unchanged |
| D5 | Architect | "Write the waves to Jira" (or Azure DevOps) | It lists the projects, previews exactly one Feature per wave and one item per module, and asks. Nothing is written until you say yes |
| D6 | Developer / read-only connection | Ask it to write | It is refused because of the role, or because the connection is read-only |

## E. The Orchestrator

| # | As | Do | Expect |
|---|---|---|---|
| E1 | Architect | In the Orchestrator, "plan the waves" / "migration strategy" | It routes to **Migration Strategy**. The deliverable lands in the run and shows on the page as "From the Orchestrator conversation" |

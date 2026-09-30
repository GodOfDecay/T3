# Track 3 — Phase F: Migration Strategy (`strategy`), and a universal pass over A–E

Master plan row F. Spec: research §6.4 (+ §9 stage 4). Branch `akshat_track3`.

**The user's requirement for this phase:** a universal solution that fits any migration, not the
ClaimTrack scenario. Every rule below is written in terms of the dependency graph, the design's
patterns, contracts and traps, the brief's dates and measure kinds — never a system, stack or date.

## Part 1 — universal fixes to earlier phases (found auditing A–E for this phase)

| # | Gap | Fix |
|---|---|---|
| U1 | The brief packet never carried the change freeze, the cutover/downtime window, data residency or the milestones: `emit.brief_payload` left `freeze_from`/`downtime_window`/`data_residency` empty for every brief, and there was no field to hold the window or the residency | `MigrationIntentArtifact.downtime_window`, `.data_residency` (optional); record-tool arguments; packet maps `freeze_from` from a `freeze` milestone, a `deadline` from a deadline milestone when the text deadline is not a date, and `milestones` (new optional `BriefPayload.milestones`) |
| U2 | Lifecycle table: .NET/Java/Node/Python only — no database, PHP, Ruby or Go. The ClaimTrack fixture targets MySQL 8.0, past support since 2026-04 | Rows for MySQL, PostgreSQL, SQL Server, PHP, Ruby, older Go; the design check parses them; fixture moves to MySQL 8.4 |
| U3 | Interface scanner: Java/C#/Python/JS/SQL only; blind to declared interface files | Go, PHP, Ruby, VB.NET, COBOL/JCL; OpenAPI/Swagger, WSDL, `.proto`, GraphQL SDL, Kubernetes CronJob |
| U4 | Contract kinds could not say RPC (SOAP/gRPC/RMI), UI screen, job or shared library | `ContractKind` gains `rpc`, `ui`, `job`, `library` (additive) |

## Part 2 — the Migration Strategy agent

Deterministic tools (no model judgement):
- `propose_wave_order` — layers the dependency graph (dependencies first), strongly connected
  components reported as cycles that must move together, lowest risk first within a layer; `keep`-only
  modules are not moved.
- `check_calendar` — the draft plan against the brief: waves ending after the deadline or a
  deadline/decommission milestone, baselines due after the freeze or after their module's wave starts,
  cutover windows outside the brief's downtime window (weekday and duration). Each conflict has a stable
  `ref`; the record tool requires every one to be reported.
- `estimate_effort` — a stated table: tier × KLOC × pattern, ±30 % band, "not estimated" when LOC was
  not measured. Always labelled an estimate.

`record_migration_strategy` = `PlanPayload` (packet) + cross-artifact rules:
every moved module (all but `keep`-only) in exactly one wave; wave patterns equal the design's; no
dependency moves after its dependant unless an `order_exceptions` entry cites a design ADR; every
contract and trap protected by a criterion; every equivalence/performance/security success measure
protected, in the brief's words; criterion ids reference real modules/contracts/traps; every criterion
protecting a contract or trap has a baseline-plan item; every non-W0 wave's exit criteria list its
modules' criteria; parallel-run modules have a period; the brief's freeze date is kept; every
calendar conflict reported; effort for every wave; budget fit when the brief has a budget.

Approval (Architect or Project Admin fallback, never the producer) moves each planned module
`designed → sequenced` with its wave and criteria, in the publish transaction; a revised plan updates
rows still `sequenced`, and refuses to re-wave a module already migrating. The board write (one Feature
per wave, one item per module) is Consequential: owner of THIS project + this turn's consent.

Frontend: `/strategy` (replaces the stub) on `Track3AgentPage`: timeline, waves, criteria, baseline
plan, calendar conflicts, RAID, effort and budget, ledger panel; hand-over to Equivalence Testing.

Migration 0072: `runs.strategy_artifacts`; `strategy` in the deliverables CHECK.

Quality bar as every phase: tests first where possible, mutation-proven guards, an independent review
and a proven fix wave, regression groups 1–3 and the frontend suite, build-log entry, click-through.

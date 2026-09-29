# Track 3 — Phase E: Target Architecture (`design_modernization`)

Master plan: `2026-09-28-track3-master-plan.md` §4 row E. Spec: research §6.3 (+ §9 Stage 3). Branch
`akshat_track3`. Decisions D1–D14 stand; D14 (module-id drift) is implemented here.

## What the agent does

Reads the pinned brief and assessment **packets**, the legacy code and a deterministic inventory of the
legacy system's interfaces; proposes the target per layer, a pattern per module, the interop plan, frozen
contracts (CT-xx), traps (TR-xx), ADRs, data migration, NFRs and AS-IS / TRANSITION / TO-BE diagrams;
records it as a frozen version once the user agrees. **Approval** (Architect, or a Project Admin of the
project as labelled fallback, never the producer) puts every designed module on the ledger as `designed`.

## Backend

| # | Piece | Where |
|---|---|---|
| 1 | Migration `0071_target_design`: `runs.target_design_artifacts`; `design_modernization` in the deliverables CHECK | `migrations/versions/` |
| 2 | Packet additions (optional, backward compatible): `FrozenContract.brief_item` (the brief's must-not-change words it freezes), `DesignPayload.resolved_questions` (a "not assessable statically" question and its answer, with source). Schemas regenerated, fixture updated | `handover/packets.py` |
| 3 | `design_packet()` / `design_payload()` | `handover/emit.py` |
| 4 | `capture_legacy_interfaces` — deterministic scan: HTTP endpoints (Spring, JAX-RS, `web.xml`, JSP, ASP.NET, Flask/FastAPI, Express), outbound HTTP, files written/read, scheduled jobs, DB tables (DDL, JPA, SQL), queues | `design_modernization_agent/analysis/interfaces.py` |
| 5 | Cross-artifact checks (research "checked by record_target_design" + D14): every assessed module designed; id → name/path/tier/score equal the **pinned** assessment; every must-not-change item frozen by a CT (`brief_item`, word for word); CT location exists in the checkout; `confirmed` only when captured or named by the brief; trap `where` exists; no target version past (or within 12 months of) end of life, never "latest"; `data_migration` required when the database layer changes; AS-IS, TRANSITION and TO-BE diagrams present and starting with a Mermaid diagram type; every not-assessable question answered or carried as open | `design_modernization_agent/analysis/checks.py` |
| 6 | Tools: `read_migration_brief`, `read_assessment`, `get_module_detail`, `get_dependency_graph`, `capture_legacy_interfaces`, `record_target_design` (validate packet → checks → persist → freeze), `export_target_design`; plus legacy read tools, tech stack, documents/approval, compare/restore | `design_modernization_agent/tools/` |
| 7 | Prompt (research §6.3 house style + `going_back`, `documents_and_approval("Architect")`, `DELIVERABLE_RULES`), graph, page socket | `design_modernization_agent/` |
| 8 | Registry entry, portfolio, mount + ws allow-list, orchestrator2 wire ids (registry, router names/capability/prompt, deliverables), artifact column map, run output segment, legacy-code stages, upstream reader (`discovery_artifacts`), context formatter for the assessment and the brief's must-not-change | shared, Track 3 rows only |
| 9 | Ledger on **approval**: the publish route calls `ledger.design_approved` in the same transaction; the ledger refuses an id whose path changed (D14 across commits) and the approval rolls back with that reason | `routers/artifact_versions.py`, `services/modernization_ledger.py` |
| 10 | Page data: packet + export for kind `target-architecture`; `GET …/legacy-code/interfaces` (the inventory, for the page) | `routers/modernization.py` |

## Frontend

- `/projects/[id]/target-architecture` on `Track3AgentPage` (versions rail, VersionView sign-off, fallback,
  restore, compare, staleness, hand-over now names the NEXT agent per stage).
- `TargetDesignView`: summary stats, sources line (brief vN, assessment vN @ commit), tabs — Overview (layers
  today → target, interop, ordering constraints, data migration, NFRs, security), Modules (table + detail
  with its contracts, traps and ADRs), Contracts, Traps, ADRs (options with the decision marked), Diagrams
  (Mermaid, AS-IS / TRANSITION / TO-BE), Questions & departures; a ledger panel (what approval did / will do).
- Legacy interfaces dialog from the header (the same deterministic inventory the agent reads).
- Zod schemas, API client, orchestrator wire ids. The tile flips last (R42), after the click-through.

## Tests (real Postgres for data)

Packet and checks refuse, each with the named problem; interface scan on a fixture repo; record tool
refuses and names; persists + freezes + pins `built_from`; D14 drift refused; publish → ledger `designed`
(and roll back on ledger refusal); producer cannot approve; cross-project/track access on the new routes;
orchestrator wiring; frontend render tests against backend-produced fixtures. Mutation-prove every guard,
independent review, regression groups 1–3, frontend suite, click-through `help/Track-3/click-through-phase-E.md`.

## Stops

No commit, push, or dev-DB migration without the user's OK. Migration 0071 goes to the test DB only.

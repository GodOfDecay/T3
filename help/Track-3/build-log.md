# Track 3 build log

One entry per decision, finding and fix round. Newest last. Plan: `docs/superpowers/plans/2026-09-28-track3-master-plan.md`.

---

## Entry 1 — 2026-09-28 — Reading done, environment fixed, what exists, where docs disagree

**Branch:** `akshat_track3` = `akshat_main` @ `621b8904` (the `help/track3-*.md` → `help/Track-3/` move is
uncommitted in the working tree).

**Read in full:** Lessons doc; Development Plan (all of it); Flow document (all of it); ClaimTrack demo;
phase-1 requirements doc; agent-build-plan; research §1, §5, §7, §12, §13; Phase 1 plan headings and
Task 12; issues log Issues 3 and 10 (the rest is summarised in the Lessons doc, which I cross-checked).
**Not yet read in full:** research §6.3–§6.10 (agent specs and prompts) and §9 — I will read each
agent's section at the start of its phase, before its plan file. Items 8–13 of the reading list and the
Track 1 page/component sources are also read per phase, when that code is touched.

### (0) Environment — found broken, switched to local (you asked for this)

| Check | Found | Action |
|---|---|---|
| App DB | `backend/.env` pointed at Azure `amc-postgresql-d-2knrl5…` — **hostname does not resolve** (`getaddrinfo failed`) | Switched the three `POSTGRES_*` to local native PostgreSQL 16 on **5432**, db `sdlc_product` (app `sdlc_app`, migrations `postgres`). Azure lines kept, commented |
| RLS (R18) | local `sdlc_app`: `rolsuper=false`, `rolbypassrls=false`; app now connects as `sdlc_app` | ✔ verified by connecting with the new DSN |
| File storage | `AZURE_BLOB_ACCOUNT_URL=sdlcartifacts97290…` — **NXDOMAIN**; no `STORAGE_BACKEND` → resolver would pick Azure and fail | Set `STORAGE_BACKEND=local`, `ARTIFACT_STORAGE_ROOT=files/artifact-store` (the `shared/storage` resolver's documented local mode). Local DB has 0 `artifacts` rows, so no stored bytes are orphaned |
| Redis | Docker Desktop was not running → nothing on 6379 | Started Docker Desktop; `sdlc-redis` healthy, `PONG` |
| Docker Postgres `sdlc-postgres` (5433) | Holds only LiteLLM's empty `sdlc_agentic`; compose comments say the native 5432 server holds the app schema | Left alone |
| LiteLLM container | `sdlc-litellm` exited (127) 3 days ago | Not started — agents use BYOK via the litellm library; will revisit if a live run needs the proxy |
| Test DB (R50) | `.env.test` → local `sdlc_product_test` (differs from app DSN ✔) | Upgraded `0064 → 0065`, ran `scripts.grant_app_role` ("grants applied and verified") |
| Dev DB migration | local `sdlc_product` at **0064**, code head **0065** | **Not applied — needs your OK** (§9) |
| `alembic heads` | exactly one: `0065_tech_stacks` | Note: `uv run alembic` fails here ("uv trampoline failed to canonicalize script path"); use `uv run python -m alembic` |

### (a) What exists (verified in code)

- Agents `requirements_modernization` + `discovery` registered (`config/agent_registry.py:233,251`), roster
  `TRACK_PORTFOLIOS["modernization"] = [both]` (`:300`), `_OWNER_OF` → `ba` for both.
- `modernization_common/graph.py`: model via `resolve_model_for_run`/`set_resolved_model`, no env
  fallback, `temperature_kwargs` (skips gpt-5 family), `max_retries=0`, streaming,
  `sanitize_tool_call_pairing` every call; `guarded_completion` has the 90 s ceiling
  (`model_call_wrapper.py:44`). R25–R28, R30 hold.
- `standalone.py`: per-message `assert_agent_access_for_chat_on_track`, identity from the ticket,
  `stream_end` + `activity_update{complete}` on every path, per-turn consent.
- Frontend: `components/modernization/` (brief card, assessment view, own version history/view);
  stub pages `strategy`, `migration-mapping`, `validation` (21–22 lines each).

### (b) Where documents disagree with the code / this machine

1. **Postgres port**: prompt §2 and Lessons G say 5433; the app DB here is native **5432** (5433 is LiteLLM's).
2. **Backend port**: prompt says 8004; `backend/.env` `AGENTIC_BASE_URL` and `frontend/.env.local`
   `FASTAPI_INTERNAL_URL` both say **8001** (consistent with each other; no phantom listener on 8001 here).
   Keeping 8001 unless you prefer 8004.
3. **"Migration head is 0065"** is true of the code; both local DBs were at 0064.
4. `track3-agent-build-plan.md` opening premise stale (already flagged in its own header) ✔.
5. **Step −1 audit, preliminary (to confirm in Phase A):**
   - **R32 violated in `standalone.py:199`** — `initialized.add(session_id)` happens *before* the graph
     runs; a failed/cancelled first turn leaves the session believing its system prompt was delivered.
   - **R31 partial** — no per-session in-flight guard and no tracked cancellable task; `run_turn` is awaited
     inline per socket, but the BFF opens a socket per turn, so two turns on one session can race.
   - `upstream_from_pages` reads versions directly (`latest_published`/`latest_version`), not through
     `read_upstream`, so **no `artifact_consumptions` row is recorded** (Lessons §7.2 #5 confirmed).
   - Confirmed absent in both agents: `make_document_tools`, `make_approval_tools`, tech stack (§7.2 #1,#2,#4).
   - `GATE_OWNER` (`gate_routing.py:16`) has no Track 3 rows and `.get(stage, "product_manager")` default.

### (c) Decisions taken

- **D1** Hand-over schemas as **Pydantic v2 models** with JSON Schema exported and checked in (pinned by a
  test). Why: pydantic is a declared dependency and the codebase idiom; `jsonschema` is only transitive.
  Cost if wrong: small — the exported JSON is the contract either way.
- **D2** Local over cloud for DB and storage (above). Cost if wrong: re-point three env lines.

### (d) Stops / questions for you (batched)

1. **Apply migration 0065 to the local dev DB** (`sdlc_product`)? Without it the running app lacks
   `tech_stacks`. Additive migration.
2. **Capacity decision** (prompt §9): the retrofit (~4 ed) + seed/shared frame (~2 ed) exceed the 75 ed plan.
   Recommendation: **extend by two days** rather than cut; the cut list (Plan §24.4) removes eShop and Verify's perf chart, which are cheap to keep for a single sequential builder whose real constraint is review cycles, not days.
3. **Real credential for Step −1(a)**: a project-scoped Azure DevOps (or GitHub) PAT with **read** scope on a
   private repo (ClaimTrack `Project 2`), saved at project scope — to prove the private-clone path (R7).
4. **ClaimTrack source**: the demo doc's local copy is on another machine
   (`C:\Users\srk02\...`). Is the Azure DevOps `srk02804/Project 2` repo reachable from this account?

### Next

Starting **Phase B item 1** (hand-over schemas + ClaimTrack fixtures): new files only, no shared code, no DB.

---

## Entry 2 — 2026-09-28 — Phase B item 1 done: hand-over schemas + ClaimTrack fixtures

**Context from you:** ClaimTrack is a *simulated* customer scenario (a made-up company using the
agents), not a real client system. Consequences: fixtures and seed data may be invented freely
where research §9 is illustrative, and "no real customer data" is trivially satisfied, but the
masking/sandbox rules still get built as if a real customer's data flowed through.

**Delivered** (all new files, nothing shared touched):
- `backend/agents_orchestrator/modernization_common/handover/` — `ids.py` (id patterns + `mint`),
  `packets.py` (envelope + 10 packet/payload models), `schemas/*.json` (exported), `fixtures/claimtrack/*.json`
  (10 fixtures from research §9), `__main__.py` (regenerates schemas).
- `backend/tests/modernization_common/test_handover_packets.py` — 72 tests.

**Decisions**
- **D3** Envelope status = version-store vocabulary (`draft|published|superseded|rejected`), not the
  research doc's `submitted|approved`. Why: the envelope is read off the version row. Cost if wrong: a rename.
- **D4** Migration record gets `outcome: ready_for_review | build_failed | blocked`. Why: the Flow doc says
  the record tool refuses a red build, and research §6.6 says a still-red build after 5 rounds "is recorded".
  Both hold with an outcome, and only `ready_for_review` needs green. *Document disagreement, resolved in code.*
- **D5** Security policy, conservative readings: unknown reachability on critical/high counts as reachable
  (→ FAIL), and a required scanner (trivy/semgrep/gitleaks) not run means no PASS (R39). Cost if wrong: an
  over-strict FAIL that a person can waive; the opposite error would ship a FAIL as a PASS.
- **D6** `Criterion.protects` split into ids (`CT`/`TR`) and `protects_measures` (brief text), with at least
  one required. Why: `ReferenceId | str` accepted any string, which made the id typing decorative.
- **D7** Only rules decidable from one packet live in the models. Cross-artifact rules (EOL table,
  every legacy file covered, every in-scope module in a wave, files_read actually opened) are listed in each
  payload's docstring and stay with the record tools that hold that data.

**Evidence**
- `pytest tests/modernization_common/test_handover_packets.py tests/discovery tests/requirements_modernization`
  → `148 passed` (72 new, 76 existing Track 3), no DB.
- **Mutation (R46):** 43 mutants over every guard in `packets.py`, each applied, confirmed changed
  (`git diff --no-index --numstat` = `+1/-1` each), test file run, and the file restored in `finally`
  (restored byte-identical: True). **43/43 killed.** Eight were first killed only by the schema-pin test
  (which fails on *any* field change), so they were re-run with that test deselected: **8/8 killed by their own
  behavioural refusal test** (`adr-2-options`, `pattern-min1`, `contract-location`, `norm-reason`,
  `ec-observable`, `wave-rollback-optional`, `rounds-cap`, `extra-forbid`). Harness:
  scratchpad `mutate_handover.py` (+ `_behaviour.py`).
- R47: every refusal test validates the unmutated fixture first (control), breaks one thing, and matches
  the rule's own message; a test asserts no fixture contains the refusal texts.

**Not done / honest notes**
- Tests were written after the models, not before (the "failing test first" order was not followed for this
  item); the mutation run is what stands in for it.
- No reviewer agent has looked at this yet (R54). I'll get a separate review before Phase B closes.

**Next in Phase B:** item 2, the Module Migration Ledger (migration `0066`, FORCE RLS, per-agent transitions),
tested on `sdlc_product_test` only.

---

## Entry 3 — 2026-09-28 — Dev DB migrated; plan re-ordered around integrations; no timeline

- **Dev DB migrated** (your OK): local `sdlc_product` `0064 → 0065_tech_stacks`; `scripts.grant_app_role`
  → "grants applied and verified"; `alembic current` = `0065_tech_stacks (head)`.
- **Timeline dropped** from the plan at your instruction; phases are ordered by dependency only. The
  capacity question from Entry 1 is withdrawn.
- **Retrofit placement (decision D8):** the retrofit of agents 1–2 onto documents/approvals/tech stack/
  `read_upstream`/owner maps/shared page frame is **Phase B, right after the shell fixes and before the
  backbone**. Why: it makes the template that 8 agents copy correct first, it needs no ledger, and agent 3
  reads the retrofitted inputs. The schema additions (M-xx, must_not_change, envelope) are **Phase D**, after
  the backbone, because they need the envelope/packet models. Cost if wrong: small reordering.
- **Integrations reviewed (code only, no network):** grant (`integration_grants`) → stage wiring
  (`projects.connectors`) → level (`tool_access_modes` / `project_connector_access` / `DEFAULT_TOOL_MODE`)
  → credential (`project_integration_credentials` + `secret_store`) → `get_connector_for_session` →
  `ScopedConnector`, bound per turn by `orchestrator2/connectors.bound_connector`; repos via `repo_source`
  (ADO + GitHub). Local data: 10 BU grants, the Track 3 project "Migration test" wired to Azure DevOps with a
  project-scoped credential, one verified Azure gpt-5-mini offering. You confirmed the Azure connections work;
  I did not test them (a local decrypt check was blocked and dropped).
- **Findings (documents disagree with code):**
  - `DEFAULT_TOOL_MODE = "both"`, not `read` as Lessons E4 says, so a wired stage with no explicit mode can write.
  - The stage-mode key's third segment is the connector **kind**; research §5.1's `legacy`/`target` ref
    in that slot would collide. **Decision D9:** repo roles become a separate project setting with a
    role→stage rule enforced at one choke point (plan §3); the connector level is necessary but not sufficient
    for a target write.
  - The assessment orders modules by risk score; M-xx must be minted in a stable order (by path) — Phase D.

---

## Entry 4 — 2026-09-28 — Phase A (audit + shell fixes) done

**Audit of agents 1–2 and `modernization_common`** (read in code):

| Rule | Result |
|---|---|
| R1 Orchestrator = standalone | ✔ `orchestrator2/dispatch.py` sets user, project, run, orchestrator flag, per-turn consent, project-scoped model (fail-closed), connector + MCP binding; track via `_capability_for_track`; legacy workspace via `current_scope` (`test_legacy_code_orchestrator_scope.py`) |
| R2 connector names the stage | ✔ `bound_connector(agent_id, …)` in both surfaces |
| R7 project + owner on credential lookups | ✔ `owner_id=user_id` on both surfaces and in `legacy_code.py` pulls |
| R25–R28 model | ✔ `graph.py`: `temperature_kwargs`, `max_retries=0`, streaming, `resolve_model_for_run`, no env fallback; 90 s in `guarded_completion` |
| R30 pairing | ✔ `sanitize_tool_call_pairing` every call |
| **R31 in-flight / cancel** | ✘ → **fixed** |
| **R32 delivered flag** | ✘ → **fixed** (checkpoint-based) |
| **R39 not measured ≠ 0** | ✘ Dependency and Risk summary said "**0** known vulnerabilities" with Trivy skipped/unavailable, and the risk factor was silently absent → **fixed** |

**Fixes**
- `modernization_common/standalone.py` (Track 3 only; imported by the two Track 3 APIs and one test — grep):
  per-(agent, session) in-flight set with a visible refusal ending `stream_end` + `complete`; each turn a
  tracked task cancelled when its socket drops (copied from the Development agent); system prompt
  "delivered" = present in the thread's checkpoint (`system_prompt_delivered`), cached only after a turn
  that produced a reply. This also stops a duplicate system prompt after a restart.
- `discovery_agent/analysis/{assessment,risk}.py`: `vulnerabilities_scanned(scanners)` (only Trivy `ok`
  counts); the summary says "not scanned (Trivy: <status>)"; the risk factor is recorded as
  `{"points": 0, "measured": false, "detail": "Not measured: …"}`.
- `tests/test_modernization_standalone.py` fake socket now holds after its last frame until the turn ends
  (like the chat BFF); the old fake disconnected at once, which the new code correctly treats as an orphan.

**Evidence**
- `tests/modernization_common/test_standalone_turns.py` (9) + `tests/test_modernization_standalone.py`
  (8) → 17 passed. `tests/discovery tests/requirements_modernization` → 82 passed (6 new in
  `tests/discovery/test_not_measured.py`).
- Mutation (R46): shell 8/8 killed (one survivor, `delivered-before-success`, exposed a missing
  test — a turn that completes with no reply — which was added, then killed); R39 6/6 killed.
  Numstat per mutant is +1/-1 (or +0/-1, +1/-2), counted with difflib; the runner now handles CRLF files.

**Open question for you (product):** with no vulnerability scan, a module can land in the `mechanical`
tier on a score missing up to 10 points. The report now says so, but the tier rule is unchanged.
Options: leave as is (the page shows "not measured"), or never grant `mechanical` without a scan.

**Deferred (need you):** private-repo clone with a project credential; the browser click-through.

---

## Entry 5 — 2026-09-28 — Phase B (retrofit of agents 1–2; owner rows for 3–10) code-complete

**Delivered**

| Item | Where | Evidence |
|---|---|---|
| Owner rows for the 8 unbuilt ids, one change across every map (R10) | `_OWNER_OF`, `AGENT_OWNER_ROLE`, `_PHASE_PERMISSION` + grants, migration `0066_track3_owner_rows`; frontend `roles.ts`, `agents.ts`, `enums.ts`, `auth/*`, `nav.ts` | RBAC set 539 passed; new `test_track3_owner_rows.py` names all ten ids in every map |
| **Track 3 roster is Track 3's own agents** | `frontend/lib/tracks.ts` — it listed Portfolio 1's `design`, `development`, `review`… as Track 3's stages 3–10 | `track3-agents.test.ts`; tiles 3–10 locked ("coming soon") even for owner/PA |
| Fourth owner map retired | `gate_routing.GATE_OWNER` = read-only view of `AGENT_OWNER_ROLE`; unknown stage raises. It had **no callers** (grep, and a full-tree search) | `test_gate_routing_single_owner_map.py` |
| Unbuilt stages stay unapprovable | `require_stage_approval` also requires a registered stage (`STAGE_ORDER`) — owner rows now precede agents, so "has a permission" no longer means "is built" | stage-approval test now lists all 7 new ids |
| Document + approval tools on both agents | `intake.py`, `assessor.py` (`DOCUMENT_TOOLS`) → the standalone prompt layer adds the approved-documents block | graph built WITH them (reload-capture test) |
| Shared prompt sections | `modernization_common/prompt_parts.py` (documents, raise-for-approval, save-don't-offer, not-measured) composed into both prompts; stale names (Design/Strategy/Development) fixed | pairing test: every tool a prompt names is bound |
| Migration Intent reads the approved tech stack | `modernization_common/tech_stack.py` (`get_project_tech_stack`); `record_migration_intent` stamps `brief.tech_stack` {name, source, warning, departures} **by code**; brief shows "Approved tech stack: …" | `test_tech_stack_and_prompts.py` |
| Upstream reads recorded | `upstream_from_pages` → `read_upstream` (consumption row: stage, version, reader, run); enforced + nothing approved → said, not silent | **real-Postgres** `test_upstream_from_pages.py` with removal control + cross-tenant check |
| Orchestrator roster text | `router.py`: ten Track 3 names, baseline before migration | orchestrator2 760 passed |
| Pages on the platform frame | `track3-agent-page.tsx`: `DocumentList` (upload/raise/approve for the stage), `TechStackChip` (Migration Intent); `version-view.tsx`: producer told why they cannot approve (Reject kept), **"Read by"** consumers on published versions | `track3-pages-retrofit.test.tsx` 8 tests incl. access gate render (R43) |
| Breadcrumbs | `lib/nav.ts` labels for the new routes; the test now uses `phaseRoute` instead of its own copy | nav 28 passed |

**Decisions**
- **D10** Migration Development's gate owner = **developer** (not "developer builds, architect accepts"): the platform's one-agent-one-role invariant (`test_every_agent_has_exactly_one_delivery_owner`) requires the gate owner to be the single role that reaches the agent; Track 1 moved Development's gate for the same reason. Separation is per-person (no self-approval) + PA fallback. *Your call if you want Architect acceptance back — it would need a multi-approver gate (Phase C).*
- **D11** Track 3 pages keep their own version list (it drives the centre view) instead of adding `StageVersionPanel` — two lists of the same versions is the duplication Track 1's Design page removed. The missing pieces were added to the version view instead (Read by, producer explanation).
- **D12** Orchestrator wire ids (`ORCHESTRATOR_AGENT_IDS`) are added **with each agent's backend registry entry**, not now: `test_every_agent_id_the_backend_can_emit_is_in_the_frontend_enum` requires equality (R41). Deviation from the prompt's Step 0 wording, by design.
- **D13** `strategy` label → "Migration Strategy" (decision #1 display names).

**Mutation (R46)** — all restored byte-identical:
gate routing 2/2 · stage approval 1/2 (**1 equivalent**: dropping `not perm` is unreachable because every registered stage has a permission — pinned by `test_every_runnable_stage_has_an_approve_permission`) · owner maps 7/7 (first run: `cutover-pack-owner-missing` **survived** → added `test_track3_owner_rows.py` → killed) · document/tech-stack 9/9 · upstream reads 4/4 + 1 invalid pattern of mine that never applied (not counted) + `commit-dropped` **survived → the explicit commit was redundant** (the tenant session commits on exit): removed it and corrected my comment (R48). The identical claim in `shared/services/artifact_consumption.py::read_upstream_for_agent` looks equally unneeded — left untouched (shared), noted. · frontend 10/10 (first run: `read-by-on-drafts` survived on a timing race → test now asserts the API is never called for a draft → killed).

**Regression runs (specific files, test DB)**
- Backend Track 1 set (artifact versions/publication/consumption/evidence/store/scope, documents, tech stacks, approvals, run gate, WS route coverage, tool-name uniqueness, `tests/development`): **360 passed, 5 failed** — all 5 in `test_artifact_scope_and_upload.py`, `FileNotFoundError` on upload: **Windows MAX_PATH**. The blob path is 325 characters under `…\backend\files\artifact-store\` and `LongPathsEnabled = 0` on this machine. Caused by the local-storage switch + this Windows setting, not by Phase B; with the old (non-existent) Azure account uploads failed anyway. Fix = enable long paths (admin, one registry value).
- Frontend: **1151/1151** (142 files), `tsc` clean, eslint clean on every touched file. One run had `ws-ticket.test.ts` time out at 5 s under full-suite load; it passes alone (2/2) — a flake, unrelated.
- `test_seeded_catalog_matches_the_code_matrix` failed once in a full RBAC run before any change touching it and passes alone twice — order-dependent, unexplained; watching it.

**Environment fixes made along the way**
- `frontend/node_modules` was broken: pnpm's links pointed at the pre-move path (`…\Desktop\SDLC\frontend`); nothing resolved (not even `next`), and `npx tsc` "passed" by not running. Rebuilt with `pnpm install --frozen-lockfile --offline` (lockfile unchanged).
- Dev DB migrated to `0066` (boot verifies `role_permissions` against the code).

**Data note:** your "Migration test" project has connectors wired under the OLD Track 1 ids (`design`, `testing`, `code_review`, …). Those rows are now hidden in "Tools per stage" (harmless — no Track 3 agent reads them); stages 3–10 get re-wired on their own ids once each agent exists.

**Not done / open**
- Independent review (R54) running now; findings go in the next entry.
- Live verification (browser + real model) not done — needs you (click-through below).
- Phase A deferred items still open (private-repo clone with a project credential; browser click-through).
- Product question from Entry 4 (tier `mechanical` without a vulnerability scan).

---

## Entry 6 — 2026-09-28 — Independent review of A+B (R54), one fix wave; ledger landed

**Reviewer:** a separate agent, told to break it; no edits. 4 Important, 6 Minor. What I did:

| # | Finding | Result |
|---|---|---|
| 1 | Producer's "you can't approve" never showed: API relabels `producedBy` id → **email**; I compared with the id, and my test mocked the wrong shape (R47). Same bug in Track 1 `StageVersionPanel` (with a comment asserting the opposite — R48) | **Fixed both** via `producedByMe()` (id or email, case-insensitive); test uses the real shape |
| 2 | `custom_roles._PHASES` missed the 7 new ids → saving a custom role granting one failed | **Fixed** + `test_custom_role_phases_match_frontend.py` parses the frontend enum |
| 3 | R39 fixed only in markdown; page still showed "Vulnerable 0" and "+0" | **Fixed** `assessment-view.tsx` ("not scanned", "n/m", score note) + render tests |
| 4 | Enterprise checkpoints are one store keyed by thread id → another agent's system message could count as delivered; my comment claimed per-agent threads (R48) | **Fixed**: system message tagged `system:<agent>`; only this agent's (or an untagged one starting with this agent's prompt) counts; comment corrected |
| 5 | One consumption row per chat turn | **Fixed**: once per session and version |
| 6 | Unreadable stack recorded as "none" | **Fixed**: `source: "unreadable"`, brief says so |
| 7 | Cancelled partial reply saved as complete; `WebSocketDisconnect` re-raised inside a task | **Fixed** (`STOPPED_NOTE`; handled in-task). Busy-check-before-access: left (session ids are UUIDs) |
| 8, 9 | Stale `routing.py` comment; code pointing at old `help/track3-*.md` | **Fixed** |
| 10 | Hidden legacy connector keys; GATE_POLICY text for unbuilt agents | Left: harmless / the locked tiles' spec. Logged |

The reviewer also noted its DB-backed runs were inconclusive: **its pytest and my mutation runs shared
`sdlc_product_test` at the same time**, each run's tenant cleanup deleting the other's rows.

**Correction of my own claim (R46/R48).** I earlier reported the ledger trigger mutants "6/6 killed". That
was **false**: the harness called `bash`, which Windows resolves to **WSL's bash** (`CreateProcess` searches
System32 before PATH), so the migration step never ran and the non-zero exit read as a kill. The harness now
calls Git Bash by full path, requires pytest's own exit code (`PYTEST_EXIT=`), and was checked with an
**unmutated control run (23 passed, exit 0)**. Real result: 4/6 killed; the 2 survivors were real test gaps
(truncation asserted only "append-only"; FORCE RLS invisible through a non-owner role) → specific-message
assertion + a catalog check → 2/2 killed. The ledger service mutants were re-run on a quiet database:
7/7, each killed by the test named for its guard.

**Fix-wave mutation:** backend 8/8, frontend 4/4 (one survivor, `case-sensitive`, needed mixed case on the
`producedBy` side of the test → killed).

**Ledger (Phase C item 2) — done**
- Migration `0067_modernization_ledger` (up/down/up clean; FORCE RLS; `sdlc_app` granted; triggers
  `modernization_ledger_guard`, `modernization_ledger_insert_guard`), ORM `ModernizationModule`, service
  `shared/services/modernization_ledger.py` (per-agent methods only; row lock; Review+Security settle on
  the second verdict; `MAX_REJECTIONS` → blocked; person-only block/unblock/reopen with a reason).
- `tests/modernization_common/test_ledger.py`: 24 tests on the real test DB — full walk with history,
  every skip refused by the service AND by raw SQL, wrong agent refused, append-only history, concurrent
  Review+Security via `asyncio.gather`, rejection → blocked, reasons/roles, tenant isolation, FORCE RLS.

---

## Entry 7 — 2026-09-28 — Session paused mid-Phase C

Phase C items 1–3 done and tested (items 1–2 mutation-proven; item 3 tested, not yet mutated);
items 4 (repository roles) and 6 (PA fallback) are **written but untested, and migration 0069 is on no
database**; items 5 (UI), 7 (Programme page, API, seed) and the SLA/PA-floor pieces are not started.
Found: `0067` is on the dev DB without an explicit approval (verified identical to the real
migration, 0 rows). Also fixed: plain `JSONB` wrote `None` as JSON `null` on `built_from` (would have
broken every version snapshot) → `JSONB(none_as_null=True)`.
**Resume from `help/Track-3/SESSION-HANDOFF.md`.** Mutation harness saved to `help/Track-3/tools/`.

---

## Entry 8 — 2026-09-28 — Phase C finished (items 3–7, SLA escalation, PA floor)

**Item 5 UI (fallback, restore, compare, staleness) — mutation completed.** 6/6 in `version-view.tsx`,
plus 1/1 on the API helper. The survivor `stale-always` was a test asserting before the staleness
query answered, so it passed for any code (R47). The test now waits for the call → killed.

**Item 7 — Programme API, page, status strip, settings, seed.**
- `shared/routers/modernization_programme.py` (`/modernization-programme/{project}/…`):
  - GET `ledger`, `repositories`, `approval-settings` (artifact:view);
  - PUT `repositories/{legacy|target}`, `approval-settings` (project:update **and**
    `assert_can_administer_project` — the permission alone is tenant-wide);
  - every route 404s off the Code Modernization track.
  - **Decision D11:** naming repositories is applied directly by the project's own Project Admin (master
    plan §3). It does not go through the Business Unit Admin request lane that PATCH /projects uses for
    name/budget.
  - 10 tests; mutation 6/6.
- BFF: four route files; `forward()` now accepts `PUT` (opt-in per route, as before).
- Frontend:
  - page `/projects/[id]/modernization`: state counts, blocked section, module table,
    repositories, staffing warnings;
  - `ProgrammeStatusStrip` on every Track 3 agent page and the project overview (silent while the ledger
    is empty);
  - Settings → **Code Modernization** tab (Track 3 only): repository forms and fallback mode/policy.
  - 11 render tests; mutation 11/11.
- `scripts/seed_track3_fixture.py`:
  - the ClaimTrack project, a roster of the dev personas (two PAs), placeholder repositories, and six
    modules across designed/sequenced/baselined/migrating/blocked;
  - writes only through `grant_role`, `set_role` and the ledger transitions; idempotent;
  - real-DB test (run twice).
  - **Found by that test:** the user lookup read `users` untenanted and crashed on the email-less rows
    `grant_role` creates. It is now scoped to the org and to non-NULL emails.
  - **Not run on the dev DB** (needs your approval, after 0068–0070).

**SLA escalation.**
- Migration `0070`: notification kind `approval_sla_passed` plus `artifact_versions.sla_notified_at`.
  The column is mutable (not on the freeze list). Up/down/up clean on the test DB; one head.
- `workers/approval_sla_sweeper.py`, started in the lifespan and running every 15 minutes
  (`APPROVAL_SLA_SWEEP_INTERVAL_SECONDS`): each Track 3 draft past its stage's `sla_hours` notifies
  `project_admin`@project, **once**, and also goes to Slack/Teams via `notify_all` (best-effort).
- Frontend `NotificationKind` gained the kind. Without it the bell's Zod parse would have rejected
  every list containing one.
- **Finding (R48-class):** `get_db_session_superuser` is **not** BYPASSRLS under `sdlc_app`. A
  cross-tenant query over FORCE-RLS tables returns **nothing**, silently. The sweeper therefore goes
  tenant by tenant (`organizations` is not RLS-scoped).
  - The **existing Track 1 `RunSweeper` uses exactly that pattern on `runs` (FORCE RLS)**, so it very
    likely never expires anything. Reported, not changed (Track 1 scope).
- 7 tests; mutation 7/7. The `any-track` survivor was a test gap: a Track 3 stage's draft on a
  Greenfield project. That test was added → killed.
- Each sweep costs about 5s on the test DB (hundreds of throwaway orgs). That is fine for a 15-minute
  loop, and worth revisiting if tenant count grows.

**PA reach floor** (research §12.2 rule 9).
- `agent_access.pa_floor_applies(role, agent)`: `project_admin` on a Track 3 agent.
  - `set_override` refuses anything but `owner` there (409).
  - `resolve_involvement` ignores a lowering role-level row that exists anyway.
- Person-level overrides are untouched: that is the explicit "not this person" tool.
- The UI never offered it: the capabilities page excludes `project_admin` from its role picker.
- 7 tests; mutation 5/5.

**Independent review (R54).** A separate agent read the backend only; it ran no DB tests because mutation
runs were live. It found 9 Important and 9 Minor issues, and I confirmed each against the code before fixing
it. The per-finding list and fixes are in `SESSION-HANDOFF.md` §3a.

Three of these are worth keeping as lessons:
- **Idempotent paths can rewrite a decision.** A double publish was "harmless" for Track 1, but it
  overwrote the approval *capacity* (#1).
- **Restoring moves authorship without moving the content's author** (#3). The self-approval rule has
  to follow `restored_from`.
- **The UI must not claim what the code does not enforce** (R48, again):
  - #4: no push tool calls `assert_target_write` yet;
  - #14: nothing moves the ledger yet;
  - also Phase B's "You can still reject it". The backend refuses a producer both ways, so the Reject
    button offered to the producer was a lie. It is removed and click-through A/B B7 is corrected.

Tests: `test_phase_c_review_fixes.py`, 16 pass, run twice. Frontend: Track 3 files 50/50 and `tsc` clean.

**Not yet done:**
- **Mutation of the fixes.** The first run was stopped by the user and left one mutant in
  `artifact_versions.py`; it was restored and verified.
- **The regression re-run on the fixed code.**
Both are next.

**Committed locally** on `akshat_track3`, the first commit on that branch, at the user's request. Not pushed.

---

## Entry 9 — 2026-09-29 — Phase C closed: fix wave proven, a pushed mutant found, a platform bug fixed

**Fix-wave mutation — complete.** 15 of 15 backend mutants were killed, each by the test named for its
finding. The specs are `tools/specs-phase-c/spec_fix_*.json`: `av` 3, `fb` 2, `lin` 2, `linr` 2, `sa` 1,
`sla` 1, `rr` 2 and `audit` 2. The frontend fixes killed 5 of 5.

**A MUTANT WAS COMMITTED AND PUSHED (R46/R48, my process failure).**
- The frontend mutation run the user stopped on 2026-09-28 had already written the `latest-always`
  mutant into `version-view.tsx`.
- My check afterwards grepped only for `if False:`, so it missed that mutant.
- The mutant went into `8c90522c` on `origin/akshat_track3`: a version built on a rejected input would
  have read "vnull has since been approved".
- It was found because the mutant's pattern no longer matched (`BAD(0)`). It is restored, and the
  mutant is now killed.
- New tool `tools/verify_no_mutants.py` checks every spec's ORIGINAL line against the tree. Its only
  hits are four originals that were deliberately rewritten since; I read each one. **Run it after any
  interrupted mutation run.**

**Regression: a hang, then a platform bug underneath it.**
- The regression run hung for more than 40 minutes with zero CPU. I re-ran it in groups with
  `-o faulthandler_timeout=300`, which dumped the stack of
  `test_artifact_publication_routes.py::test_the_stage_owner_can_publish`, stuck in the app lifespan's
  **shutdown**.
1. **Mine:** `ApprovalSlaSweeper` swept every tenant immediately at startup, and a test client shuts the
   app down seconds later, mid-sweep. The first sweep now waits `APPROVAL_SLA_FIRST_SWEEP_DELAY_SECONDS`
   (60 s). That is right for production too: a crash-looping pod no longer re-sweeps every tenant.
2. **Pre-existing, Track 1 / platform:**
   - `workers/audit_retry_worker.py` blocks on `xread` for 5 s.
   - `shared/redis_client.py` gives every client a 2 s socket timeout (commit `9fcf8829`, "fail fast").
   - So every idle read raised `TimeoutError`. `run` caught only `CancelledError`, and **the worker died
     2 s after startup: no dead-lettered audit event has ever been retried** since that commit.
   - Any shutdown that awaited the dead task re-raised the error. That is the "Redis read-timeout
     flake" handoff §6 told future sessions to ignore.
   - Control run with my sweeper disabled: 6 of 19 failed. With the sweeper: 13 of 19. After the fix:
     19 of 19 pass.
   - Fix: the worker's own client uses `socket_timeout = block + 2 s`, and a timed-out idle read is
     "nothing yet" (`continue`).
   - Two tests guard it; mutation 2/2.
   - **Correction to the handoff:** that "flake" was a real bug.
3. **The same bug in two more places.** The next run still failed 4 tests in
   `test_artifact_scope_and_upload.py`, which handoff §2 had called "Windows long paths".
   - The traceback showed `_artifact_event_listener` (`process_api.py`). Its `pubsub.listen()` waits
     for messages indefinitely under the same 2 s socket timeout. After two quiet seconds it died, and
     **pipeline stage transitions stopped being routed**.
   - The pipeline workers (`workers/base_worker.py`: `xreadgroup`, 5 s block) had the same mismatch,
     though they only run with `ENABLE_WORKER_POOL`.
   - Fix, in one place: `shared/redis_client.blocking_read_timeout(block_s)`. The audit worker and the
     pipeline workers use it. The listener passes `socket_timeout=None`; its connect timeout still
     fails fast.
   - Pinned by `test_every_long_lived_redis_reader_outlasts_its_wait`. `test_artifact_scope_and_upload`
     + `test_artifact_publication_routes`: 37/37, twice.
   - `tests/orchestrator2` and `tests/development` both passed on this code; group 1 was re-run after
     the fix.

---

## Entry 10 — 2026-09-29 — Phase D: what agents 1 and 2 hand to Target Architecture

This implements research §6.1, §6.2 and §12.4, and Development Plan §9. Click-through:
`click-through-phase-D.md`.

**Migration Intent**
- `MigrationIntentArtifact` v3 adds three fields:
  - `must_not_change`;
  - `must_not_change_verified`: True = checked, False = the conversation could not be read,
    None = nothing to check;
  - `kind` on each success measure (`MEASURE_KINDS`). An unknown kind becomes `None`, never a guess.
- **Word for word** (`modernization_common/verbatim.py`): each entry must appear in the user's own
  messages in this conversation.
  - Matching ignores case, whitespace and surrounding quotes, and is strict about the words.
  - Matches must be whole words, and an entry must have at least 2 words.
  - A paraphrase is refused, and the refusal says to paste the wording from an attached document
    into the chat. Attachments are not in the transcript.
- **The hand-over check at record time.** The record tool builds the `BriefPacket` and refuses a brief
  that cannot be handed over, with the problems in plain words
  (e.g. "Success measure 1 has no kind (…)").
  - **Contract change:** a recorded brief now needs a goal and at least one measure with a kind. Four
    older test fixtures were updated to match; each fixture now says why.
- Output:
  - markdown, Word and PDF show "Must not change" quoted, and each measure's kind;
  - the prompt gained MUST NOT CHANGE / AFTER THE BRIEF / GOING BACK.

**Dependency and Risk (assessment schema 2)**
- Stable `M-xx` ids, numbered by PATH. The report still lists modules riskiest first; the ids don't
  follow that order.
- `not_assessable_statically` (`analysis/unknowns.py`, deterministic):
  - the runtime actually used in production. The ClaimTrack case is a module declaring Java 7 while
    using a Java-8-only library;
  - undeclared runtimes;
  - the scheduler;
  - environment configuration (always asked);
  - unreadable manifests.
- `golden_master` becomes `{status, baselines}` and its note points at Equivalence Testing.
- `DiscoveryArtifact` gained the new field. Without it, pydantic would have **silently dropped** it on
  persist; that was caught before writing it.
- The report has Id columns and the new section. Unmeasured factors now read "not measured", never
  "+0" (R39).
- The old "Design/Strategy" names in "Next steps" are corrected.

**Both agents**
- `compare_versions` + `restore_version` chat tools (`modernization_common/restore_tool.py`). They are
  page-chat only, and a restore names what goes out of date.
- `GET …/versions/{v}/packet`: the hand-over packet, or the reasons there isn't one.
- The page shows a Hand-over line:
  - "Ready once approved" for a draft, "Ready" once approved, nothing for rejected or superseded;
  - problems capped at 6;
  - a failed check says so rather than showing nothing.
- `handover/emit.py` is the ONE envelope builder. The unused Phase C copy in `version_lineage`
  disagreed on grant pins and was removed.
- The view fixture is regenerated by `tools/regen_view_fixtures.py` from the real backend, with the
  same inputs as before (including the scanner's real `target`). It is not hand-edited.

**Mutation (R46):**

| Area | Result | Note |
|---|---|---|
| Backend | 23/23 | One survivor was an **equivalent mutant**: the tool's reason check duplicated the service's own refusal, so the redundant check was deleted. |
| Frontend | 10/10 | |
| Fix wave | 20/20 | One survivor exposed a weak test: M-09/M-10/M-100 sort the same as strings or numbers, so the test now uses M-11 vs M-100. |

Specs: `tools/specs-phase-d/`. `verify_no_mutants.py`: 8 originals absent, each a deliberate
rewrite; no live mutant.

**Independent review (R54):** 5 Important and 7 Minor findings, all confirmed against the code.

| # | Finding | Result |
|---|---|---|
| 1 | Word-for-word accepted fragments of words ("api" in "rapid") and single words | **Fixed**: whole words, ≥2 words. Contiguous phrase fragments remain possible; the prompt asks for the whole phrase. |
| 2 | "In the user's own words" was shown when nothing was checked (R48) | **Fixed**: the `must_not_change_verified` flag drives the caption on the page, in the markdown and in Word/PDF, and the tool's reply says so. |
| 3 | JUnit (test scope) and Guava `-android` gave false "production cannot run Java N" | **Fixed**: the JUnit row is removed, `-android` is skipped, and the docstring says why. |
| 4 | The hand-over panel was untrue or unreadable | **Fixed**: gated by status, plain words, one message for a schema-1 assessment, a cap, and an error state. |
| 5 | Wording from an attached document was always refused | **Fixed in the message**: the refusal says to paste it into the chat. Attachments are not persisted as user text. |
| 6 | The scan skipped `bin`/`packages` and walked `.git` | **Fixed**: `os.walk` with pruning. |
| 7 | Ids sorted as strings | **Fixed**: numeric sort in both places. |
| 8 | No detection of id drift across commits | **Deferred to Phase E (D14)**: Target Architecture's packet validation cross-checks id → path against the pinned assessment version. |
| 9 | `compare` raised raw on DB errors | **Fixed**, with a test. |
| 10 | A non-string `must_not_change` crashed the tool | **Not reachable**: the tool's argument schema (`list[str]`) rejects it first, and the graph's tool node returns that to the model. The `str()` hardening was kept. |
| 11 | The fixture dropped the scanner `target` | **Fixed** in the generator. |
| 12 | Two envelope builders | **Fixed**: one remains. |

**Frontend:** full suite 1,187/1,188. The one failure is the `ws-ticket` 5 s default timeout under
parallel load: a cold dynamic `import()` in the test body takes 0.5 s alone. That is test timing,
not a product bug; left alone and noted. `tsc` and eslint are clean.

## Entry 11 — 2026-09-29 — Phase E: Target Architecture (agent 3)

Implements research §6.3 (+ §9 stage 3), master plan row E, D14. Plan:
`docs/superpowers/plans/2026-09-29-track3-phase-e-target-architecture.md`. Click-through:
`click-through-phase-E.md`. Committed as `999b1b3e`; migrations 0068–0071 applied to the dev DB with the user's OK and the tile unlocked after the user tested (both 2026-09-29).

**What was built**
- Agent package `design_modernization_agent/`: graph (`agents/architect.py`), prompt (research §6.3 house
  style + `going_back`, `documents_and_approval("Architect")`, `DELIVERABLE_RULES`), page socket
  `/sdlc/agent/design-modernization/ws`, tools: `read_migration_brief`, `read_assessment`,
  `get_module_detail`, `get_dependency_graph`, `capture_legacy_interfaces`, `record_target_design`,
  `export_target_design` + legacy read tools, tech stack, documents/approval, compare/restore.
- **Inputs are the versions this turn pinned** (`upstream_from_pages` now reads `discovery_artifacts` as
  well; consumptions recorded, `built_from` pinned). Orchestrator turns read their own run's columns and
  freeze nothing.
- **`capture_legacy_interfaces`** (`analysis/interfaces.py`): deterministic pattern scan — Spring/JAX-RS
  (with class prefix), web.xml, JSP/ASPX, ASP.NET attribute routes and minimal APIs, WCF, Flask/FastAPI,
  Express; outbound HTTP; files written/read; jobs (@Scheduled, Quartz, cron); tables (DDL, JPA, EF,
  SQL-shaped strings); queues. Each entry has `file:line` and module id; capped and says so.
- **`record_target_design`**: `DesignPayload` validation, then `analysis/checks.py` (D7): every assessed
  module designed under the PINNED assessment's id, name, tier and score (**D14**); every must-not-change
  frozen by a contract whose new `brief_item` holds the brief's words; contract locations in the code, and
  `confirmed` only for one file the inventory shows there (or the brief named); traps name a real place;
  .NET/Java/Node/Python targets not past or within a year of end of support, never "latest", unknown
  versions noted as not checked; data migration required when a database changes; AS-IS, TRANSITION and
  TO-BE Mermaid diagrams; every "not assessable statically" question answered (new `resolved_questions`,
  source user|document) or kept open; code at another commit than the assessment's is refused. Then it
  persists `runs.target_design_artifacts` (0071), freezes the version and returns the document.
- **Ledger on APPROVAL, not recording**: the publish route calls `ledger.design_approved` in the same
  transaction; a ledger refusal is a 409 and rolls the approval back. The ledger refuses id drift in
  **both** directions (same id/other path, same path/other id) and a design without module paths.
- Wiring: registry entry + portfolio, orchestrator2 (registry, router names incl. "design" resolving
  per track, capability, prompt bullet, deliverables), deliverables CHECK (0071), context formatter for
  the assessment (+ the brief's must-not-change and measures), page routes (kind `target-architecture`:
  latest, packet, export; `GET legacy-code/interfaces`).
- Frontend: `/target-architecture` page on `Track3AgentPage` (new `headerActions`), `TargetDesignView`
  (sources, stats, pattern mix, notes, ledger panel, tabs: overview, modules+detail join, contracts,
  traps, decisions with the chosen option, Mermaid diagrams, questions), Legacy interfaces dialog,
  hand-over line names the NEXT agent per stage (`HANDED_TO`), schemas, BFF routes, chat socket map,
  orchestrator ids. **Tile not flipped** (R42) — `BUILT_AGENTS_BY_TRACK` after the click-through.

**Decisions**
- E1. Packet additions are optional fields (`FrozenContract.brief_item`, `DesignPayload.resolved_questions`)
  — backward compatible; schemas regenerated; the ClaimTrack design fixture now passes every record-time
  rule against a ClaimTrack fixture repo (`tests/design_modernization/claimtrack.py`): exact trap
  locations, and Node **24** (Node 22 ends 2027-04-30, within a year — the check refuses it).
- E2. No design is recorded without both a brief and an assessment (research: "provisional until it
  exists" — the agent may discuss, not record).
- E3. Every assessed module must be designed; out-of-scope ones are `keep` with a reason.
- E4. The lifecycle table (shared with Dependency and Risk) gained the non-LTS Java 9–24 and odd Node
  releases and Python 3.14.
- E5. `resolve()`'s `..` guard deleted as an equivalent mutant: matching is against the checkout's own
  file list; a `../` path matches nothing (tested).

**Mutation (R46)** — `help/Track-3/tools/specs-phase-e/` (`make_specs.py` writes them).
| Pass | Result | Notes |
|---|---|---|
| First | backend 49/50 → 50/50, frontend 11/11 | `framework-read-as-net` equivalent (redundant skip deleted, replaced by a real mutant); `vendored-read` survived because the test's jQuery sat in a skipped `vendor/` dir (moved); `sibling-folder-matches` missing case (added); ledger `drift-trailing-slash` missing test (added) |
| Fix wave | 46/46 | after wiring `test_review_fixes.py` into the checks spec (5 "survivors" were the spec not running the new tests) |
- The harness copy in `tools/` has a cp1252 `§` and an unescaped `C:\Users` in its docstring, so it does
  not import on Python 3.12; run from a UTF-8 raw-docstring copy (scratchpad), which also reads vitest's
  stderr so a kill names its test. `verify_no_mutants.py` must be run from `tools/` (it finds the repo
  from its own path). Result: no mutant present; 12 originals absent — 5 deliberate Phase E rewrites,
  each covered by a new spec, 7 pre-existing in files this phase did not touch.

**Independent review (R54)**: 12 findings (7 Important, 5 Minor), each verified against the code.
| # | Finding | Result |
|---|---|---|
| 1 | `confirmed` passable with `*`, `...`, a folder, or any line in the same file | **Fixed**: one file; cited line within 5 of an inventory entry |
| 2 | One-letter open question muted every not-assessable question | **Fixed**: the open question must contain it |
| 3 | Unknown versions passed silently; UI claimed "end-of-life version" in general | **Fixed**: noted as not checked; table extended; UI/tool text narrowed to the four runtimes |
| 4 | Data-migration rule keyed on the layer's name only | **Fixed**: engine names in today/target count |
| 5 | Inventory cache ignored the module list | **Fixed**: modules in the key |
| 6 | Scanner (and existing `search_legacy_code`) followed symlinks out of the checkout | **Fixed** in both. The real-symlink test skips on this Windows machine (no Developer Mode); an OS-level stand-in test proves the guard |
| 7 | C# method routes replaced the prefix; JAX-RS borrowed a neighbour's @Path; `open(os.path.join(..), "w")` read as a read; prose read as SQL; VB claimed but not scanned | **Fixed** each; VB removed and "scanned languages" stated in the report and dialog |
| 8 | Drift only one direction; no-path payload skipped the check | **Fixed**: both directions (locked read), no-path design refused |
| 9 | Ledger panel promised approval on rejected/superseded versions | **Fixed**: text by status |
| 10 | "Ready to hand to Migration Strategy" reflects the packet model only | **Open, minor**: a payload snapshotted by another caller or restored against newer inputs passes the packet check; Staleness covers the latter. Noted for Phase F, whose record tool re-reads the packet |
| 11 | Export preferred the chat copy after a restore | **Fixed**: page export reads the newest version |
| 12 | Commit mismatch only a note | **Fixed**: refused |

**Tests**: `tests/design_modernization` (scanner, checks, review fixes, record tool, approval/ledger,
routes and guards, agent assembly); updated roster pins in 8 existing test files (the equality pins D12
exists for), `test_stage_approval_dependency` (agent 3 leaves the unbuilt list, as Discovery did).
Frontend: `__tests__/app/target-architecture-page.test.tsx` (19) against backend-produced fixtures
(`regen_view_fixtures.py` now emits `target_design` and `legacy_interfaces`).

**Regression (after the fix wave), `sdlc_product_test` at 0071, one group at a time:**
group 1 **1,523 passed** (3 skipped, 7 xfailed, 17 xpassed); group 2 (orchestrator2) **776 passed**, after
two roster pins were updated (the deliverables CHECK list is pinned from the newest migration's SOURCE, so
0071 writes it out literally; the stage-output map); group 3 (development) **41 passed**. Migration 0071:
one head; up/down/up clean. Frontend: full suite **1,211/1,211**, `tsc` and eslint clean on touched files.
One page-test failure appeared once while a DB mutation run loaded the machine; three control runs and the
full suite passed — noted, not dismissed, and not reproduced. The backend has no ruff installed, so no lint ran there.

## Entry 12 — 2026-09-30 — Phase F: Migration Strategy (agent 4) and the universal pass

Implements research §6.4 (+ §9 stage 4), master plan row F. Plan:
`docs/superpowers/plans/2026-09-30-track3-phase-f-migration-strategy.md`. Click-through:
`click-through-phase-F.md`. Migration 0072 on the test database, then on the DEV database at the user's
request (2026-09-30, after a first attempt was blocked by the permission classifier); backend restarted;
tile unlocked at the user's request.

**The universal pass (the user's brief: "fit any use case of migration, not just ClaimTrack")** — what the
earlier phases handed over was checked against unrelated systems (a .NET payroll, a Go/PHP/Ruby/VB/COBOL
polyglot), and changed where it assumed ClaimTrack:
- U1. The brief hands over its planning dates: dated milestones (kinds deadline, freeze, decommission,
  external…), the freeze as a milestone, a deadline written in prose falls back to the deadline milestone,
  and `downtime_window` / `data_residency` (Migration Intent records them; the page shows both as key facts).
- U2. The lifecycle table covers databases and more runtimes: MySQL, PostgreSQL, SQL Server, PHP, Ruby, Go;
  the design check reads managed-service names ("Azure Database for MySQL Flexible Server 8.0"). The
  ClaimTrack design moved to MySQL 8.4 (8.0 ended 2026-04-30).
- U3. The interface scanner reads Go, PHP, Ruby, VB.NET, COBOL (EXEC SQL / CICS / MQ), JCL, and DECLARED
  contracts: OpenAPI paths, WSDL operations, gRPC services, GraphQL root fields, Kubernetes CronJobs.
- U4. A frozen contract can be any kind of interface (rpc, ui, job, library added).
- A shared input reader (`modernization_common/inputs.py`) replaces Target Architecture's private one;
  agents 3–10 read their upstream packets the same way.

**What was built (agent 4)**
- `strategy_agent/`: prompt, graph, page socket `/sdlc/agent/strategy/ws`; tools `read_migration_brief`,
  `read_assessment`, `read_target_design`, `propose_wave_order`, `check_calendar`, `estimate_effort`,
  `record_migration_strategy`, `export_strategy_document`, `preview_wave_work_items`, `list_board_projects`,
  `create_wave_work_items` + documents/approval, compare/restore.
- Deterministic analysis, generic in the graph, the patterns and the brief's words:
  - ordering: Tarjan SCCs (a cycle moves together), layered by dependency, lowest risk first; kept modules
    move in no wave. A dependency is ready first when its wave ENDS no later than the dependent's (waves
    may overlap and ids are names, not the order); moving earlier needs an order exception citing a design ADR.
  - calendar: deadline, deadline/decommission milestones, baselines after the freeze or after their wave
    starts, cutover day and length against the brief's window. Each conflict has a stable ref and must be
    reported by it.
  - effort: a stated table (size × tier × pattern, ±30 %); an unmeasured module is "not estimated", never 0.
  - record-time rules: every moved module is in exactly one wave with the design's patterns; W0 moves none; every
    moving wave has entry criteria and its modules' criteria in its exits; every contract, trap and
    equivalence/performance/security measure is protected, in the brief's words; baselines for protecting
    criteria; parallel runs have a period; the brief's freeze is kept; "given" dates are the brief's; effort per
    wave; budget fit when the brief has a budget.
- Ledger on APPROVAL: `strategy_approved` sequences every placed module in its wave with its criteria; a
  revision updates sequenced modules ("plan revised") and refuses to re-wave, or change the criteria of, a
  module past planning; a plan whose patterns differ from the APPROVED design's, or that leaves out a module
  it moves, is refused (409) and rolls the approval back.
- Board: preview exactly what is written (one Feature per wave, one item per module); writing needs an
  Architect or Project Admin OF THIS PROJECT plus this-turn consent, a read-write connection, and a plan that
  is not rejected or superseded.
- Wiring: registry entry (position 4) and portfolio, orchestrator2 (registry, router names "strategy",
  "migration plan", "wave plan", "waves", capability, prompt bullet, deliverables), migration 0072
  (`runs.strategy_artifacts`, deliverables CHECK), context formatter for the target design, page routes (kind
  `strategy`: latest, packet, export; `GET modernization/strategy`), `built_from` for the design.
- Frontend: `/strategy` page on `Track3AgentPage` (new `showLegacyCode={false}`: this agent reads no code),
  `StrategyView` (summary, timeline with freeze/milestones/deadline, module ledger, tabs: waves, criteria
  with a module filter, baselines with late flags, calendar with reported/open/resolved, order with cycles
  and exceptions, RAID, effort), schemas, BFF allow-lists, chat socket map, orchestrator ids, hand-over line
  "Ready to hand to Equivalence Testing". **Tile not flipped** (R42).

**Proven universal**: two unrelated scenarios pass every rule (`tests/strategy/scenarios.py`): ClaimTrack
(Java/Node, strangler + parallel run, overlapping waves) and Payroll (.NET, a PayCalc ⇄ PayRules cycle, an
order exception with its ADR, a kept module, a weekend 4-hour window, a freeze milestone).

**Decisions**
- F1. Readiness is by date, not by wave number: a module is cut over when its wave ends, so a dependency must
  be in a wave that ends no later than its dependent's. Wave ids are names; waves may overlap (ClaimTrack's
  W4 starts before W3).
- F2. The ledger is the authority on which design is approved: approval compares each placement's patterns
  with the ledger row and refuses a plan built on any other design version, or one that leaves out a module
  the approved design moves.
- F3. A cutover window is read from the user's words (days, day ranges with times, "nights", a stated limit or
  the window's own span). What cannot be read is reported by part and never guessed.
- F4. Dates marked "given" must be dates in the brief; otherwise the plan marks them proposed.
- F5. Declared MINIMUMS are marked (`Runtime.minimum`) — go.mod `go`, Node `engines` ">=14" / "14 || 16" /
  "14 - 18", Python ">=3.8" / "~=3.8" / Poetry "^3.8"; a pin ("14.x", "^14", `.nvmrc`, "==3.9.*",
  `runtime.txt`, `.python-version`) is the runtime, and a pin file wins over a minimum. Scoring (the user
  asked for what suits the use case): Go's minimum is reported, not scored (the Go 1 compatibility promise;
  `toolchain` is scored). A Node/Python minimum IS scored — a legacy app's minimum is the line it was
  written and tested against and majors break — labelled "(minimum)", with a note asking for the version
  production runs. ClaimTrack's `">=14"` keeps its EOL score and now says so honestly.
- F6. The Strategy page shows no legacy-code controls (`showLegacyCode={false}`): this agent works from the
  three documents only.

**Independent review (R54)**: 12 findings (6 Important, 6 Minor), each verified against the code (the
reviewer's probes reproduced 1, 3, 5, 6 and 10), then fixed with a test that fails without the fix.
| # | Finding | Result |
|---|---|---|
| 1 | Order compared wave ids, not dates: a false refusal (a later id that ends first) and a missed one | **Fixed** (F1) |
| 2 | Discovery scored go.mod's `go 1.21` minimum as an EOL runtime (a regression from the new Go rows) | **Fixed** (F5) |
| 3 | PHP 8 `#[Route]` attributes and docblock `@Route` read as comments: Symfony apps had no endpoints | **Fixed** |
| 4 | Approval never checked which design the plan was built from | **Fixed** (F2) |
| 5 | Modules could be placed in W0 and skip the exit/effort rules | **Fixed**: W0 moves none |
| 6 | Window parsing: "Fri 22:00 – Mon 06:00" misread, a night spilling past midnight flagged, the window's own span not a limit, "checked" claimed when only days were read | **Fixed** (F3) |
| 7 | A revision could rewrite the criteria of a baselined module; "assessed in None" message; dropped modules unnoticed | **Fixed**: criteria kept past planning, `assessed` refused by name, dropped moved modules refused (F2) |
| 8 | "given" dates and entry criteria shown but not enforced | **Fixed** (F4; entry criteria required on every moving wave) |
| 9 | The Orchestrator board write read an in-process copy and ignored `version`; a rejected plan could be written | **Fixed**: read from the run's column; a version is refused there; rejected/superseded never written |
| 10 | "PostgreSQL 16 (replacing MySQL 5.7)" refused on MySQL 5.7 | **Fixed**: a version after replacing/from/was/instead of… is the one left |
| 11 | Context cut a >60-module design silently | **Fixed**: "… and N more modules" |
| 12 | `check_calendar` / `estimate_effort` crashed on an incomplete draft | **Fixed**: they say what is missing |

**Mutation (R46)** — `help/Track-3/tools/specs-phase-f/` (`make_specs.py` writes 18 specs, 120 mutants that run).
| Pass | Result | Notes |
|---|---|---|
| First (after the fix wave) | 107/116 | 9 survivors: 7 real test gaps (a baseline for "all" modules against the first move; a multi-day cutover's length; a "to" inside the replaced-version window; a JCL comment assertion that compared exact names; routes under an OpenAPI vendor key; `schedule:` outside a CronJob; the ledger panel re-reading on approval), 1 spec anchored on the DESIGN hook instead of strategy's (re-anchored), 1 board role check whose test user was also refused by consent (new test: an Architect of ANOTHER project passes consent, only the role check stops them) |
| Second | all killed | `jcl-comment-read` is EQUIVALENT (both JCL rules need `//name<space>`, which `//*` never matches) — removed from the spec, the branch itself stays proven by `jcl-statements-skipped` |
| Added | router 2/2, shared reader 3/3 | the Phase E Orchestrator guard moved into `modernization_common/inputs.py` (its E anchor is gone); a database error was untested (test added) |
- `verify_no_mutants`: Phase F — 0 originals absent. Phases C/E — 8 absent, none a mutant: 3 Phase E anchors
  rewritten in this phase (the router's packet map gained `strategy`, `design_tools` reads through the
  shared reader, the Python file-mode line takes `args[0]`), each re-covered by a Phase F spec or unchanged in
  logic; 5 were already absent at Entry 11.

**Tests**: `tests/strategy` (analysis, checks on two systems, agent assembly, record/board/approval through
the real app on Postgres — 100), `tests/design_modernization/test_universal.py` (U1–U4 + review fixes — 67);
roster pins updated in the existing tests that pin the agent list (D12). Frontend:
`__tests__/app/strategy-page.test.tsx` (16) against backend-produced fixtures (`regen_view_fixtures.py` emits
`migration_plan` and `migration_plan_payroll` through the record tool's own builder).

**Regression (after the fix wave), `sdlc_product_test` at 0072, one group at a time:** group 1 (with
`tests/design_modernization tests/strategy`) **1,687 passed** (3 skipped, 7 xfailed, 17 xpassed); group 2
(orchestrator2) **780 passed**; group 3 (development) **41 passed**. Migration 0072: one head; up/down/up
clean. Frontend: full suite **1,229/1,229**, `tsc` and eslint clean on touched files. Two files timed out once
at 5 s while a DB mutation run loaded the machine (`ws-ticket`, `project-artifacts-tab`); both pass on a quiet
machine and in the full run.

**Minimums follow-up (F5)**: 8 more mutants — 128 in all, every one killed (eol 6/6, manifests 8/8); a redundant `pinned` parameter
was removed rather than left as an unkillable mutant. Affected suites re-run: discovery, modernization_common,
design_modernization, strategy, requirements_modernization **635 passed**; frontend **1,230/1,230**, `tsc`
clean.

**Live (dev, 0072):** backend restarted clean; `GET /projects/{id}/modernization/strategy` and the strategy
artifact-version routes answer 401 without a token; `/projects/{id}/strategy` redirects to sign-in (307).
The Strategy tile is unlocked for the Architect and Project Admin (`BUILT_AGENTS_BY_TRACK`, tests updated).

## Entry 13 — 2026-10-01 — Phase G: Equivalence Testing (agent 5), Baseline mode, and its fix wave

Implements research §6.5 (Baseline mode; Verify mode is Phase J) and §4.2, master plan row G. Plan:
`docs/superpowers/plans/2026-09-30-track3-phase-g-equivalence-baseline.md`. Click-through:
`click-through-phase-G.md`. Migration 0073 on the test database. **Not on the user's dev database** (ask
first). **Tile not flipped** (R42).

**History note.** The Phase G build was committed as `b398ac1` with the message "Phase F". Phase F itself is
`439b704`. History was left as it is (the branch is shared); this entry is the record.

**What was built (b398ac1, plan steps 1–4)**
- `samples/legacy-claimtrack/`: ClaimTrack Lite, a Python 2.7 stdlib claims API + settlement batch + SQLite,
  synthetic data, a digest-pinned Dockerfile, an `sdlc-sandbox.json` profile, a fraud-score stub; installed per
  project with `scripts/install_legacy_sample.py` (localhost only).
- `testing_modernization_agent/`: prompt, graph, page socket `/sdlc/agent/testing-modernization/ws`; tools
  `read_migration_plan`, `read_target_design`, `get_ledger`, `get_capture_profile`, `save_capture_profile`,
  `plan_capture`, `capture_baseline` (Consequential), `record_baseline`, `export_baseline_document` + legacy-code
  read tools, documents/approval, compare/restore.
- Sandbox (G2): per run an `--internal` Docker network (no egress), the app built from the checkout's own
  Dockerfile, read-only root, tmpfs for the profile's writable dirs, one stub per external service, a request
  driver; two runs on fresh seeded containers; everything labelled `sdlc.capture=<id>` and removed in `finally`.
- Noise (G3), baseline (G4), store (`LocalBaselineStore`, paths built from validated ids), ledger on approval
  (G6, `baselines_approved`), wiring (registry position 5, portfolio, orchestrator2, 0073, context formatter for
  the plan, page routes latest/captures/packet/export), frontend `/equivalence-testing` (`EquivalenceView`,
  captures dialog, ledger panel).

**Gaps found when the build was reviewed as a whole (this session)**
| # | Gap | Why it matters | Fix |
|---|---|---|---|
| G-1 | Stopping a chat turn during a capture left its manifest `running` forever | `except Exception` does not catch `CancelledError`; the page showed a capture that never ends | The capture thread is shielded; on a stop it is told to stop (`threading.Event`, checked between runs and scenarios, `CaptureCancelled`), the manifest becomes `failed: cancelled`, and the project stays locked until the sandbox is gone |
| G-2 | One capture per project was an in-memory `asyncio.Lock` | Two server processes (any real deployment) could run two captures of one project at once | An O_EXCL lock file in the store (`acquire_lock` / `release_lock`), shared by every process; a lock older than the longest capture (`SDLC_SANDBOX_MAX_CAPTURE_SECONDS`, 2 h) is taken over |
| G-3 | A server stopped mid-capture left a `running` manifest and its containers | Same as G-1, plus Docker objects never removed | `reap_interrupted`: past the time limit the capture becomes `failed: interrupted`, partial recordings removed, its containers/networks removed by label |
| G-4 | `purge_expired` (90-day retention) was never called | Recordings accumulate without limit | Called before every capture for the project, and by `workers/baseline_retention_sweeper.py` (hourly, every project in the store; wired into the app lifespan) |
| G-5 | Sandbox containers ran with Docker's default capabilities and no resource limits | The legacy code is somebody else's program, run as it is | `runner.limits()` on the app, stubs and driver: `--cap-drop ALL`, `no-new-privileges`, `--memory 1g`, `--cpus 1`, `--pids-limit 256` (env-configurable). Proven in Docker: the sample runs under them |
| G-6 | Anyone with chat reach could save the capture profile | The profile decides which commands the sandbox runs | Saving needs QA or Project Admin OF THIS PROJECT (the capture's own rule); the write is atomic |
| G-7 | Nothing was audited | Running legacy code and changing what runs are security-relevant | `audit_events`: `modernization.capture_profile_saved` (sha256 + scenario/stub ids, never commands), `baseline_capture_started`, `_completed`, `_failed` |
| G-8 | Rule proposals went "to Migration Strategy" but Strategy could not read them | The feedback loop of research §6.5 was broken: a proposal was a dead end on a page | Strategy gains `read_baseline_proposals` (the newest baseline's proposals, each marked open or covered by the newest plan using the capture's own matching) and a prompt paragraph: agree with the user, add the rule in a revised plan, never adopt silently |
| G-9 | `mutate.py` had a hard-coded `C:\Users\…` root and cp1252 bytes | It ran on one laptop only | UTF-8; the root is `SDLC_REPO_ROOT` or its own checkout |
| G-10 | The BFF legacy-code routes allowed three stages, not `testing_modernization` | **Found in the browser, not by a test**: the page always read "No legacy code pulled yet" and its Pull dialog's repository list was refused (404 at the proxy). The render tests mock the API | Both allow-lists gain the stage; `tests/modernization_common/test_legacy_code_bff_stages.py` reads the route files and pins them to `legacy_code.TRACK3_STAGES` (mutation-checked: removing the stage fails it) |

**Decisions (G10–G13, this session)**
- G10. The capture lock lives in the baseline store, not Redis: the store is already the shared state a capture
  writes, and it moves to blob storage with it (a blob lease there).
- G11. A stopped capture keeps the project locked until its sandbox is removed, so a new capture never shares
  the machine with a dying one.
- G12. Container limits are defaults, not profile fields: a legacy repository does not choose its own sandbox.
- G13. Strategy reads proposals from the newest baseline version whatever its status: a draft's proposals are
  what QA is about to hand over, and the Architect needs them before acceptance.

**Open (deployment decisions, not code):** the organisation registry for the harness and legacy base images;
deterministic tokenisation for non-synthetic data (`DATA_KINDS` is "synthetic" only); Azure blob storage behind
`BaselineStore`; Docker on a dedicated sandbox host rather than the API pod (the build step has network access
to fetch base images; the RUNS have none).

**Mutation (R46)**: `help/Track-3/tools/specs-phase-g/` (`make_specs.py` writes 15 specs, 113 mutants). The 11 original
specs had **never been run** (no Entry 13 existed). They had run on the Windows laptop only through a hard-coded path.
| Pass | Result | Notes |
|---|---|---|
| First (the build + this fix wave) | 98/113 killed; 10 survived, 2 BAD | Every survivor was in the original build and was a test that refused for the WRONG reason or was missing: (1) a path outside the checkout was refused only because the file did not exist; (2) an absolute path likewise; (3) "`; rm -rf /`" was refused only because its name ended in "/"; (4) an extra output line in one run only; (5) the runner's label clean-up (a stray driver whose client timed out); (6) a capture mapping that does not hold, never asked of a tool; (7) a failed capture's partial recordings, never present when the test failed; (8) a stopped capture freeing the project early (the test landed during the build, before any container existed); (9) the captures list polling while running (the test was NAMED "polls" and checked no poll). BAD: two noise patterns escaped `À-ɏ` the source writes literally |
| Second (the five specs with survivors) | **113/113 killed** | New tests: files that EXIST outside the checkout and a symlink out; an absolute path inside it; five shell-syntax names; one-run-only lines; a planted stray container; a bad mapping through `plan_capture` and `capture_baseline`; `_fail` drops every partial recording; the stopped capture held at a gate inside the build (deterministic); fake-timer polling tests both ways |
- `verify_no_mutants`: Phase G, 0 originals absent.
- A leak check in the chain test matched "0.13" inside a timestamp ("…:50.136481"): numbers now match whole (`_leaks`).

**Tests**: `tests/testing_modernization` 114 (units 67, lifecycle 14, record/approval chain 16 on Postgres and
Docker, sandbox 6 in Docker, agent 11) + `tests/modernization_common/test_legacy_code_bff_stages.py` 2. Frontend:
`equivalence-page.test.tsx` 15.

**Regression (this container: Linux, Postgres 16, Docker 29, Python 3.12, Node 22), test DB at 0073, one group at a time:**
group 1 (with `tests/design_modernization tests/strategy tests/testing_modernization`) **1,803 passed**, 6 failed, all
in `test_project_scoped.py` because this container had no `SECRET_STORE_KEY`: with a key, that file is **24/24**. Group 2
**787 passed**, 1 failed: `test_paths_that_differ_only_in_case_or_separator_are_one_directory`, a Windows-only
assertion (`C:\files\U1` == `c:/files/u1`), Track 1 code this phase does not touch. Group 3 **41 passed**. Frontend:
**1,243/1,245**; the 2 are `document-preview.test.tsx` (`object.stream is not a function`: jsdom's Blob under Node 22
here), failing identically when run alone and untouched by this phase (its only frontend changes are the
Equivalence test and the two BFF allow-lists). `tsc` clean, eslint clean on touched files.

**Live (this container's dev database, migrated to 0073; the user's own dev DB is untouched):** the backend booted with
the retention sweeper; a "ClaimTrack Lite (Phase G demo)" project with an approved design and plan, the sample pulled
through `pull_now`. The agent's tools as QA: profile → capture plan → a REAL two-run capture in Docker (claims-read 5,
settle 6, bank-file 1; varying fields `generatedAt`, `requestId`, `settledAt`, the bank header line; shapes only) →
baseline v1 recorded with two proposals → Migration Strategy's `read_baseline_proposals` listed both **open**. Audit:
`baseline_capture_started` and `_completed`, with the actor. Then in Chromium (Playwright) as a SECOND QA through the
real login and BFF: the page, baseline v1 with every tile, the ledger panel, **Approve** → v1 Approved, "Ready to hand
to Migration Development", ledger M-01/M-02 **baselined** (confirmed in the database), the Captures dialog showing the
capture "recorded as a baseline". This found G-10. No chat was held with the model: the container has no model key.


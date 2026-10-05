# Track 3 (Code Modernization) — Handoff for whoever builds the next agents

**Updated:** 2026-10-05, end of Phase J (Verify mode; workflow review fixes; tiles for H and I flipped at the user's request — Entry 16). Before that, end of Phase I (Migration Review and Security built; proven on Postgres + git + the three scanners in Docker; 69/69 mutants; migration 0075 on the test and dev DBs; tiles not flipped until the user's click-through — build-log Entry 15). Before that, end of Phase H (built; proven on Postgres + Docker and LIVE: a real pull request on GodOfDecay/claimtrack-lite-target; 71/71 mutants; migration 0074 on the test DB; tile not flipped until the user's click-through). Before that, 2026-10-01, end of Phase G (built, fix wave, mutation-proven; migration 0073 on the test DB; the user's own dev DB is still at 0072 and needs 0073 with their OK; tile flipped at the user's request on 2026-10-01, as Phase F's was). Phase G's build and fix wave are on `claude/intelligent-pasteur-m7ea75` (based on `akshat_track3`), to merge back. **Branch:** `akshat_track3` on `origin` (the team's shared branch; never push Track 3
work to `track-3`). Last commit: `12418303` (handoff) on `999b1b3e` (Phase E), `0c814fad` (Phase D),
`9f2e81f6` (Phase C closed) and `8c90522c` (A, B and most of C).

**Read in this order:**
1. This file.
2. `help/Track-3/track3-research.md` §6.x for **the one agent you are building**. Do not read the ~8,000
   lines of design docs up front.
3. `help/Track-3/Track-3 Lessons from Track 1-2.md` (rules R1–R57).
4. `help/Track-3/build-log.md` for the evidence behind any decision below (Entries 1–16).

The phase map is `docs/superpowers/plans/2026-09-28-track3-master-plan.md`. The binding rules and the
mandatory stops are in `help/Track-3/Track-3 Implementation Prompt.md` §9.

---

## 0. RESUME HERE (read first; kept current at every checkpoint)

**Where the code is.** GitHub `GodOfDecay/T3`, branch **`claude/intelligent-pasteur-m7ea75`**
(https://github.com/GodOfDecay/T3/tree/claude/intelligent-pasteur-m7ea75). It holds Phases G and H on top of
`akshat_track3` and Phase I as it lands. Every checkpoint is committed and pushed; the newest commit is the state.

**Phase I progress (the cloud session ticks these as it goes; a local session continues from the first unticked):**
- [x] I0 Plan written: `docs/superpowers/plans/2026-10-05-track3-phase-i-review-security.md`
- [x] I1 Migration Review agent (`code_review_modernization`): tools, prompt, graph, socket
- [x] I2 Security (Modernization) agent (`security_modernization`): tools, prompt, graph, socket
- [x] I3 Wiring: registry, orchestrator2, migration 0075, routes, ledger verdicts, roster pins
- [x] I4 Tests: units, Postgres chain (review + security on Phase H's PR), rework loop
- [x] I5 Frontend: `/migration-review`, `/modernization-security` pages + tests
- [x] I6 Mutation (69/69), regression, build-log Entry 15, click-through I, this file

**Phase J is done** (build-log Entry 16): Equivalence Testing's Verify mode, after a workflow review that fixed
per-module approvals (W-1), the rework list (W-2), unblock/reopen (W-3) and the Programme verdict columns (W-4).
- [x] J plan · [x] workflow fixes · [x] verify analysis, tools, hook, prompt · [x] tests (units, Docker + Postgres
  chain) · [x] frontend verification view · [x] mutation 25/25 · [x] regression · [x] build log, click-through J

**Next is Phase K — Cutover** (`deployment_modernization`, research §6.9, master plan row K: "Request-only; your
R13 decision first"). It aggregates every gate per module (baseline, review, security, equivalence = `verified`
on the ledger, PR merged) and prepares the cutover; the user's R13 decision (what Cutover may actually do) is the
first stop. Agents built: 8 of 10 + Verify mode; left: Cutover, Cutover Pack.

**Phase I needs on the laptop:** Docker Desktop running; migration 0075 (`alembic upgrade head`, then
`grant_app_role`); Trivy's database filled once with network (command in `click-through-phase-I.md`; or set
`SDLC_TRIVY_CACHE`). Scanner images pull on first use (aquasec/trivy, semgrep/semgrep, zricethezav/gitleaks —
pinned digests in `security_modernization_agent/scanners.py`). New tests: `tests/review_security_modernization`
(units run anywhere; `test_scanners.py` and part of `test_chain.py` skip without Docker).

### 0.1 Run it on the Windows laptop (PowerShell)

```powershell
# once: get the branch (the remote is named t3 so it never clashes with another origin)
cd C:\Users\Aksha\OneDrive\Desktop\PWC\SDLC
git remote add t3 https://github.com/GodOfDecay/T3.git      # "already exists" → git remote set-url t3 <same url>
git fetch t3 claude/intelligent-pasteur-m7ea75
git checkout -b track3-phase-h t3/claude/intelligent-pasteur-m7ea75   # later: git pull t3 claude/intelligent-pasteur-m7ea75

# every time: Docker Desktop running (Redis, and the sandboxes of Phases G/H/I)
cd backend
docker compose up -d redis
uv sync
uv run python -m alembic upgrade head        # the code's head (0074 after Phase H; 0075 after Phase I)
uv run python -m scripts.grant_app_role      # after EVERY migration
uv run python -m uvicorn process_api:app --port 8001 --reload --reload-exclude "files/*"
# second window
cd ..\frontend
pnpm install
pnpm dev                                       # http://localhost:3000 ; frontend/.env.local → FASTAPI_INTERNAL_URL=http://127.0.0.1:8001
```

`backend/.env.test` must also have a `SECRET_STORE_KEY` (any Fernet key: `uv run python -c "from cryptography.fernet
import Fernet; print(Fernet.generate_key().decode())"`), or the six secret-store tests in `test_project_scoped.py` fail.

### 0.2 Edit and test locally

- Tests (PowerShell, from `backend/`): `uv run python -m pytest tests/development_modernization -q -p no:cacheprovider`
  (`tests/conftest.py` loads `.env.test` itself — never point tests at the dev database). Docker tests skip when
  Docker Desktop is off; start it to run them.
- Frontend: `node node_modules/vitest/vitest.mjs run <file>`, `node node_modules/typescript/bin/tsc --noEmit`,
  `node node_modules/eslint/bin/eslint.js <files>` (never npx).
- Mutation (§6): from `backend/`, `uv run python ../help/Track-3/tools/mutate.py ../help/Track-3/tools/specs-phase-h/spec_h_rules.json`
  (it finds the repository itself). NEVER run two DB-backed test processes at once, and never commit while a
  mutation run is live (the target file holds a mutant until the harness restores it); after an interrupted run,
  `verify_no_mutants.py <spec dir>` must report 0 absent.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Push to the branch above
  (`git push t3 HEAD:claude/intelligent-pasteur-m7ea75`).

### 0.3 A local Claude Code (Pro) session picking up

Open Claude Code in the repository root on that branch and say: "Read help/Track-3/SESSION-HANDOFF.md §0 and
continue Phase I from the first unticked item." It needs: Docker Desktop running, PostgreSQL 16 on 5432 with
`sdlc_product` and `sdlc_product_test` migrated to the code's head, Redis up. Everything else (decisions, traps,
quality bar) is in this file and `build-log.md` (Entries 13–15).

## 1. Where it stands

Track 3 has ten agents in hand-off order. The four built ones are live on their pages (4 by URL until its tile flips); tiles 4–10 show
**Coming soon** until built and click-through-verified (R42).

| # | Agent id | UI name | Owner role | Status |
|---|---|---|---|---|
| 1 | `requirements_modernization` | Migration Intent | BA | **Built** (Phases A, B, D) |
| 2 | `discovery` | Dependency and Risk | BA | **Built** (Phases A, B, D) |
| 3 | `design_modernization` | Target Architecture | Architect | **Built** (Phase E; tile unlocked, user-tested) |
| 4 | `strategy` | Migration Strategy | Architect | **Built** (Phase F; tile unlocked at the user's request) |
| 5 | `testing_modernization` | Equivalence Testing | QA | **Built: Baseline mode** (Phase G; tile unlocked at the user's request). Verify mode is Phase J |
| 6 | `development_modernization` | Migration Development | Developer (D10) | **Built** (Phase H; live PR proven; open by URL until the click-through) |
| 7 | `code_review_modernization` | Migration Review | Architect | Phase I |
| 8 | `security_modernization` | Security (Modernization) | Security Engineer | Phase I |
| 9 | `deployment_modernization` | Cutover | DevOps Engineer | Phase K |
| 10 | `documentation_modernization` | Cutover Pack | BA | Phase L |

**The backbone every agent from 3 onward uses is DONE** (Phase C): hand-over packets, the module ledger,
version provenance/restore/compare/staleness, legacy vs target repositories, the universal Project Admin
fallback approval, SLA escalation and the Programme board. Agents 1–2 now emit the packets agent 3 reads
(Phase D).

**Quality bar met by every phase so far:**
- tests first where possible;
- every guard mutation-proven;
- an independent adversarial review, followed by a fix wave that is also mutation-proven;
- the Track 1 regression set green (last run 1,687 + 780 + 41 passed, Phase F);
- a click-through script for the user.
Keep that bar (§6).

---

## 2. Enterprise non-negotiables (apply to every agent)

- **Tenancy.** Every table is FORCE RLS on `app.current_tenant_id`, and the app role `sdlc_app` is **not**
  BYPASSRLS:
  - Background jobs go tenant by tenant (`organizations` is not RLS-scoped); see
    `workers/approval_sla_sweeper.py`.
  - `get_db_session_superuser` sees **nothing** in RLS tables.
  - New tables: FORCE RLS + insert policy + grants (`scripts.grant_app_role`), with a tenant-isolation
    test.
- **Authorization is project-scoped, not tenant-union.** Permissions in a token are the union across a
  user's bindings, so a Track 3 gate must also check the role **on this project**. Use the existing
  helpers:
  - `fallback_approval.project_roles`, which honours `expires_at`;
  - `assert_can_administer_project`;
  - `assert_agent_access_for_chat_on_track`, which checks membership, track and reach.
  - A route under `/{project_id}` needs `require_project_access` (Lessons R11).
- **Nobody approves their own work.** The DB enforces `published_by <> produced_by`. For Track 3 the
  check also follows `restored_from` (`version_lineage.producers_of`). A producer can neither approve
  nor reject.
- **Approvals:**
  - Track 3 sign-offs go to the owning role, or to a Project Admin **of that project** as fallback, with
    a reason. That approval is labelled `approved_as = fallback:project_admin` and appears in the
    Cutover Pack.
  - The Strict / after-SLA policies are per project (Settings → Code Modernization), and changes to
    them are audited.
  - Track 1 approval behaviour must stay unchanged.
- **Consequential actions** (board writes, pushes, PRs, cutover) need the owner role **and** the user's
  consent in this turn (`authorize_consequential`). Show exactly what will be written first.
- **Repositories:**
  - Legacy is **read-only for every stage**.
  - Only Migration Development and Cutover write the **target**. Every push/PR tool **must call
    `repository_roles.assert_target_write`** first. It is built and tested, but **nothing calls it
    yet**, and the UI says so.
  - Integrations ride the platform chain: BU grant → stage wiring → access level →
    `resolve_effective_access`, with the project credential through `get_connector_for_session`.
    Never add a second path.
- **Not measured is not zero (R39):** a number that wasn't produced reads "not measured" or "not scanned",
  never 0.
- **The UI never states a guarantee the code doesn't enforce (R48).** Two Phase C/D findings were exactly
  this.
- **Audit and notifications:**
  - Security-relevant setting changes write `audit_events` (`audit_service.emit`).
  - A new notification kind needs **both** the DB CHECK (migration) **and**
    `frontend/lib/schemas/notification.ts`; otherwise the bell's Zod parse drops the whole list.
- **Secrets** are never decrypted or inspected (blocked by policy). `.env` / `.env.test` stay gitignored.
  Never commit `backend/files/`, logs or `node_modules`.
- **Track 1/2 must keep working.** They are complete, and the regression set (§6) is the gate.

---

## 3. How a Track 3 agent is built

The built agents are the template: `backend/agents_orchestrator/requirements_modernization_agent/` and
`discovery_agent/`. Shared code lives in `backend/agents_orchestrator/modernization_common/`.

### 3.1 The backbone an agent plugs into

| Need | Use | Notes |
|---|---|---|
| Graph | `modernization_common/graph.build_tool_agent_graph` | One graph for page chat and Orchestrator |
| Page chat socket | `modernization_common/standalone.py` (+ `<agent>_agent_api.py`) | In-flight guard, cancellable turns, per-agent tagged system prompt, persists the user turn **before** the run |
| Prompt parts | `modernization_common/prompt_parts.py` | `documents_and_approval(owner)`, `DELIVERABLE_RULES`, `going_back(noun)`. Only compose what is bound |
| Project documents + raise for approval | `shared/tools/project_documents.make_document_tools`, `shared/tools/document_approval.make_approval_tools` | Bind both (`DOCUMENT_TOOLS`) |
| Read upstream work | `standalone.upstream_from_pages` → `artifact_versions.read_upstream` | Honours enforced publication and grants; records consumption once per session + version; pins `built_from` |
| **Hand-over packet (input and output)** | `modernization_common/handover/packets.py` (models, the contract), `handover/emit.py` (build + validate; **the one envelope builder**), `handover/ids.py` (`mint`, id patterns) | Each agent's record tool validates its packet and **refuses** a payload that can't be handed over, in plain words (`emit._plain`). ClaimTrack fixtures: `handover/fixtures/claimtrack/*.json` |
| Freeze a version | `modernization_common/versions.freeze_version` (+ `note_input`) | Numbered, frozen (DB trigger), `built_from` pinned from the turn's reads. Page chats only |
| Restore / compare from chat | `modernization_common/restore_tool.make_restore_tool`, `make_compare_tool` | Bind both. The page's Restore is the same service (`version_lineage`) |
| Staleness | `version_lineage.stale_inputs` | Stale = newer **approved** input, or pinned input **rejected** |
| Module ledger | `shared/services/modernization_ledger.py` | **Per-agent transition methods only** (`design_approved`, `plan_approved`, `baseline_accepted`, `migration_started`, `pr_opened`, `review_submitted`, `security_submitted`, `equivalence_recorded`, `cut_over`, `rolled_back`, `retired`, `block`/`unblock`/`reopen`). The DB refuses skips. **Wire the call to the version's APPROVAL, not to recording** |
| Legacy code | `modernization_common/legacy_code.py` | Read-only pulled checkout; tools `get_legacy_code_profile`, `list_legacy_files`, `read_legacy_file`, `search_legacy_code` |
| Target writes | `shared/services/repository_roles.assert_target_write` | Mandatory before any push or PR |
| Tech stack | `modernization_common/tech_stack.py` | The effective stack and its source; departures are recorded, the stack itself is read by code |
| Word-for-word capture | `modernization_common/verbatim.py` | When a field must hold the user's own words |
| Approval capacity | `shared/services/fallback_approval.decide` / `approval_capacity` | Multi-approver slots (Cutover release: DevOps + business owner) are enforced in `decide`; **persisting slots is Phase K's job** |

### 3.2 Checklist: adding agent N

Owner rows and permissions for agents 3–10 already exist (migration `0066`, every owner map, and
`frontend/lib/roles.ts`). Don't redo them.

1. **Research first:** read `track3-research.md` §6.N and the packet for its input and output in
   `handover/packets.py`, including the rules listed in each class docstring that belong in the record
   tool. Build against the ClaimTrack fixtures of its inputs.
2. **Agent package** `backend/agents_orchestrator/<agent>_agent/` containing:
   - `agents/<name>.py`: the graph, binding `TOOLS + DOCUMENT_TOOLS + VERSION_TOOLS`;
   - `prompts/`: house style, plus `going_back(noun)` and `documents_and_approval(owner)`;
   - `tools/`: ONE record tool that validates the packet, freezes the version and returns the
     document; plus read tools;
   - `<agent>_agent_api.py`: the page socket via `standalone`.
3. **Registry** (`backend/config/agent_registry.py`):
   - an `AgentDefinition` (`pipeline_position`, `input_artifacts`, `output_artifact`, `gate_type`,
     `sla_hours`, capabilities);
   - add the id to `TRACK_PORTFOLIOS["modernization"]` **only once built and mounted**.
4. **Mount** in `backend/process_api.py`:
   - `app.include_router(<router>, prefix="/sdlc/agent/<route>", dependencies=[_VIEW_DEP])`;
   - add its `/ws` path to the socket allow-list in `shared/authz/dependency.py`.
   `test_ws_route_coverage` / `test_routes_bound_to_real_handlers` will tell you what's missing.
5. **Orchestrator wire ids (D12):** add them **together with** the registry entry, never before; the
   equality pin breaks otherwise. Backend: `orchestrator2/registry.py`, `router.py`, `deliverables.py`.
   Frontend: `lib/orchestrator/agents.ts`, `lib/orchestrator/types.ts`.
6. **Ledger:** on the version's **approval**, call this agent's ledger transition. Refuse on the ledger's
   own terms (`LedgerRefused`), and test that a skip is refused by both the service and raw SQL.
7. **Frontend:**
   - a page under `app/(app)/projects/[id]/<route>/` built on `components/modernization/track3-agent-page.tsx`
     (versions rail, `VersionView` with sign-off/fallback/restore/compare/staleness/hand-over,
     documents);
   - Zod schemas in `lib/schemas/modernization.ts`;
   - BFF routes under `app/api/…`. Every `api()` path needs a `route.ts`; `every-api-path-has-a-proxy`
     checks this;
   - `phaseRoute` and `segmentLabels` already exist for all ten.
   - Add the id to `BUILT_AGENTS_BY_TRACK.modernization` (`lib/agents.ts`) **last**, after the user's
     click-through (R42).
8. **Tests** (real Postgres for anything touching data):
   - the packet refuses bad payloads;
   - the record tool refuses and names the problem;
   - access: the track check, cross-project, a producer can't approve;
   - the ledger transition happens on approval;
   - render tests against **backend-produced** fixtures (`help/Track-3/tools/regen_view_fixtures.py`
     pattern; never hand-edit fixtures).
9. **Quality bar:** §6.

---

## 4. Roadmap and what each phase needs decided

| Phase | Agent | Needs before or while building |
|---|---|---|
| E ✔ | Target Architecture | **Done** (build-log Entry 11, `click-through-phase-E.md`). What F reads: `emit.design_packet` of the APPROVED `design_modernization` version (packet route kind `target-architecture`); ledger rows are `designed` with patterns/contract_ids/adr_ids; `ordering_constraints` restrict wave order; `traps` and `frozen_contracts` become ECs. `upstream_from_pages` needs a `target_design_artifacts` row in `_UPSTREAM_STAGE` and a context formatter for agent 4 |
| F ✔ | Migration Strategy | **Done** (build-log Entry 12, `click-through-phase-F.md`), with a universal pass over A–E (brief dates/window/residency, more EOL runtimes and databases, a polyglot + declared-contract scanner, a shared input reader `modernization_common/inputs.py`). What G reads: `emit.plan_packet` of the APPROVED `strategy` version (packet route kind `strategy`); `equivalence_criteria` (id, module_id or "all", protects, protects_measures, observable, normalization rules) and `baseline_plan` (ec_id, environment, data source, masking, due); ledger rows are `sequenced` with `wave` and `ec_ids`. `baseline_accepted` moves them to `baselined`. Add `strategy_artifacts` to `_UPSTREAM_STAGE` consumers for agent 5 |
| G ✔ | Legacy sandbox + Equivalence Testing (baseline) | **Done** (build-log Entry 13, `click-through-phase-G.md`). What H reads: the APPROVED `testing_modernization` version (packet route kind `equivalence-testing`, `emit.baseline_packet`): BL-xx per module with ec_ids, counts, sha256, region; the noise report; open rule proposals (`read_baseline_proposals` on Strategy); `stubs`. Ledger rows are `baselined` with `baseline_ids`. Recordings stay in `LocalBaselineStore` (`files/equivalence/<project>/captures/<id>/run1`), never in the DB or the model. J replays run 1's inputs through the SAME harness (`sandbox/runner.py`, `analysis/noise.py`) on the target image |
| H ✔ | Migration Development | **Done** (build-log Entry 14, `click-through-phase-H.md`). What I reads: the module's newest ACCEPTED `development_modernization` version (one version = one module; packet route kind `migration-development`, `emit.migration_packet`): outcome, file map, recipes, rewrites, traps handled, vault references, build; plus `head_sha`, `commits`, `changed_files` and the ledger's `pr_url` / `target_branch` (state `in_review`). Review and Security read the TARGET (`repo_access` read) at that branch; their verdicts move the module with `review_submitted` / `security_submitted`. Rework: the Developer pushes again on the same branch (`pr_opened` clears the verdicts). Still needed for a live push: a real target repository + a write credential (Entry 14, Open) |
| I | Migration Review + Security | Read legacy and target. Run on H's PR. Security prompt byte-identity test (master plan §5) |
| J | Equivalence Testing (verify) | Replays baselines on the target |
| K | Cutover | **User decision R13 first.** Request-only. Persists the multi-approver slots `decide` already enforces |
| L | Cutover Pack | Traceability map, evidence (including fallback approvals), docs PR to the target |
| M | End-to-end + whole-branch review | The full ClaimTrack chain; acceptance table |

Stub pages (`strategy`, `migration-mapping`, `validation`) are replaced or removed in the phase that owns
them.

---

## 5. Environment (verified; don't re-investigate)

| Thing | Fact |
|---|---|
| App DB | Local PostgreSQL 16 on **5432**, db `sdlc_product`, role `sdlc_app` (not BYPASSRLS). The Azure DB/blob hosts in old `.env` lines don't resolve (kept, commented) |
| Test DB | `sdlc_product_test`, via `backend/.env.test` |
| Redis | Docker `sdlc-redis` on 6379 (start Docker Desktop). Docker Postgres on 5433 is LiteLLM's, not the app's |
| Storage | `STORAGE_BACKEND=local`. Windows long paths must be enabled for uploads (admin PowerShell; in the A/B click-through) |
| Ports | Backend **8001** (docs saying 8004 are stale) |
| Cloud session (Phases G–I) | Linux container: Postgres 16 + Redis + Docker started by hand (`service postgresql start`, `redis-server --daemonize yes`, `dockerd &`); `backend/.env`/`.env.test` written there, gitignored. Its dev DB is NOT the user's laptop DB |
| Commands | `uv run python -m alembic …`, `python -m uvicorn process_api:app --port 8001` (`uv run alembic/uvicorn` fail: "uv trampoline"). Tests: `cd backend && set -a && . ./.env.test && set +a && uv run python -m pytest <files> -q -p no:cacheprovider`. Frontend: `node node_modules/typescript/bin/tsc --noEmit`, `node node_modules/vitest/vitest.mjs run`, `node node_modules/eslint/bin/eslint.js` (**never npx**) |
| Migrations | Code head **`0074_migration_development`** (Phase H: `runs.migration_artifacts`, deliverables CHECK). Before it, **`0073_equivalence`** (Phase G: `runs.equivalence_artifacts`, deliverables CHECK; apply to dev with the user's OK, then `grant_app_role`, then restart). Before it: **Test DB 0072; dev DB 0072** (0068–0071 applied to dev with the user's OK on 2026-09-29, grants re-applied; 0072 on 2026-09-30 at the user's request — a column only, no grants needed). A new migration goes on dev only with the user's OK. 0067 reached dev without explicit approval earlier (verified identical; the user was told) |
| Personas (dev DB) | `ba@gmail.com`, `projadmin@gmail.com`, `architect@gmail.com`, `dev@gmail.com`, `tester@gmail.com`, `buadmin@gmail.com`, `admin@pwc.dev`. `DEV_LOGINS.txt` personas are NOT in this DB. Projects: "Migration test" (Track 3, ADO wired), "Test" (Greenfield) |
| Seed | `backend/scripts/seed_track3_fixture.py`: the ClaimTrack project, roster, placeholder repositories and six ledger modules. Idempotent, guarded to localhost. **Not yet run on dev; ask first** |
| Git | Commit messages end `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. PRs get reviewer `UjjwalTyagi5` and end with the Claude Code line. `git push` may be blocked for Claude in auto mode; ask the user to run `! git push origin akshat_track3` |

---

## 6. Quality gates (every phase)

1. **Tests first** where possible; real Postgres for data paths.
2. **Mutation-prove every guard (R46):**
   - Harness: `help/Track-3/tools/mutate.py` (run the scratchpad or tools copy from `backend/`). Specs
     are kept in `help/Track-3/tools/specs-phase-{c,d}/`.
   - A kill counts only when a **named** test fails.
   - A survivor is a missing test or an equivalent mutant; if equivalent, delete the redundant code.
   - **After any interrupted run, run
     `help/Track-3/tools/verify_no_mutants.py help/Track-3/tools/specs-phase-c help/Track-3/tools/specs-phase-d`**
     (a mutant once reached a pushed commit).
3. **Independent adversarial review (R54)** by a separate agent, told not to run DB tests while mutation
   runs are live. Verify every finding against the code before fixing, then mutation-prove the fix wave.
4. **Regression set** on the test DB, run in three groups with `-o faulthandler_timeout=300` (a hang
   dumps its stack):
   - **group 1:** `tests/test_agent_ownership_is_single_sourced.py test_agent_reach_matches_frontend
     test_agent_registry_portfolios test_artifact_* test_consequential_gate test_consumption_grants
     test_custom_role_phases_match_frontend test_db_enums_match_the_code test_document_*
     test_enterprise_rbac_catalog test_gate_routing_single_owner_map test_legacy_code_*
     test_m9_migration_heads test_modernization_standalone test_notifications test_project_scoped
     test_rbac_* test_routes_bound_to_real_handlers test_stage_approval_dependency test_track3_owner_rows
     test_upstream_tools_honour_the_flag test_m7_rbac test_rls_coverage test_ws_route_coverage` plus
     `tests/audit tests/modernization_common tests/discovery tests/requirements_modernization`;
   - **group 2:** `tests/orchestrator2`;
   - **group 3:** `tests/development`.
   - Frontend: the full vitest suite plus `tsc` and eslint on touched files.
5. **After a migration:** `alembic heads` (exactly one); up/down/up on the test DB; grants; FORCE RLS on new
   tables.
6. **Build log** entry with every decision and finding; a **click-through** script
   (`help/Track-3/click-through-phase-X.md`); update this file.

---

## 7. Decisions already taken (don't re-litigate)

| # | Decision |
|---|---|
| D1 | Packets are Pydantic models |
| D3 | The envelope status uses the version store's vocabulary (`draft/published/superseded/rejected`) |
| D4 | Migration record `outcome` |
| D5 | Conservative security policy |
| D6 | `protects` / `protects_measures` |
| D7 | Cross-artifact rules live in the record tools |
| D8 | Retrofit before backbone |
| D9 | Repository roles are their own table |
| D10 | Migration Development owner = Developer |
| D11 | Track 3 pages keep their own version list |
| D12 | Orchestrator wire ids are added with the registry entry |
| D13 | The label is "Migration Strategy" |
| D14 | Module-id drift across commits is checked by Target Architecture's packet validation |

Also decided:
- The PA fallback applies to **Track 3 stages only**.
- A brief is recorded only if its packet validates. That means a goal and at least one measure with a
  kind (the Phase D contract).
- The assessment is always saved; hand-over gaps are stated.
- Programme repository settings are applied directly by the project's Project Admin, and audited.
- The SLA sweep's first run waits 60 s after startup.

---

## 8. Traps (each cost real time)

**Tooling**
- `bash` launched from a Python subprocess on Windows is **WSL's**. Use
  `C:\Program Files\Git\usr\bin\bash.exe`.
- Generated edit scripts: never put `\n` inside string literals written through a heredoc; use
  `chr(10)`. A class between a FastAPI decorator and its function breaks the route.
- pytest has no `--timeout` plugin; use `-o faulthandler_timeout=N`.

**Database and tests**
- Never run two DB-backed pytest processes at once: tenant cleanup deletes the other run's rows.
- After a trigger/migration mutation run, re-apply the real migration (`help/Track-3/tools/reset_ledger.sh`)
  and check `relforcerowsecurity`.
- Use `JSONB(none_as_null=True)` for nullable list columns with an "is array" CHECK. Plain JSONB writes
  JSON `null` and fails with a misleading RLS error.
- Pydantic models **ignore unknown keys**. A new artifact field must be added to the persist model
  (`DiscoveryArtifact`, `MigrationIntentArtifact`) or it is silently dropped.

**Redis**
- The shared client timeout is 2 s. A reader that blocks on purpose uses
  `shared/redis_client.blocking_read_timeout(block_s)`, or `socket_timeout=None` for pub/sub. Three
  workers died from this until Phase C closed.

**Frontend**
- The API relabels `producedBy` from the user id to the **email**; use `producedByMe()`.
- `frontend/components/modernization/__tests__/fixtures.json` is backend output; regenerate it with
  `help/Track-3/tools/regen_view_fixtures.py`.

**Diagnosis**
- A "flake" needs a **control run** before it is dismissed. The Redis "flake" was a real outage in
  production code.
- Known harmless: `ws-ticket.test.ts` times out only under full-suite load (0.5 s alone).
  `test_seeded_catalog_matches_the_code_matrix` was once order-dependent.

---

## 9. Open items for the user

- Run `click-through-phase-F.md` (the tile is already unlocked at the user's request).
- Declared runtime minimums are decided (build-log Entry 12, F5): Go's is not scored, Node/Python's are
  scored and labelled "(minimum)" with the production version to confirm.

- Optionally run the seed script on dev (`scripts/seed_track3_fixture.py`; ask first).
- The remaining click-through steps in `click-through-phase-E.md`, if not all were run.
- `help/Track-3/tools/mutate.py` is now UTF-8 and finds the repository itself (`SDLC_REPO_ROOT`, else its own checkout) instead of a hard-coded `C:\Users\...` path (Phase G). It runs with the backend venv's Python: `.venv/bin/python ../help/Track-3/tools/mutate.py <spec>` from `backend/`.
- Run the click-throughs: `click-through-phase-A-B.md`, `-C.md`, `-D.md`. None has been run yet.
- **Track 1 issue, reported and not fixed:** `workers/run_sweeper.py` queries `runs` through the
  superuser session, which isn't BYPASSRLS, so it very likely never expires anything. Fix it the way
  the SLA sweeper works (tenant by tenant) when Track 1's owners agree.
- Deferred until the user provides them:
  - a private-repo clone with a project credential;
  - real legacy code for a live Phase G capture beyond the ClaimTrack Lite sample (`samples/legacy-claimtrack`);
  - Phase G's deployment decisions (build-log Entry 13 "Open"): the organisation registry for the sandbox images,
    deterministic tokenisation of real data, Azure blob storage for the baseline store, and where Docker runs
    in production (a dedicated sandbox host, not the API pod);
  - run `click-through-phase-G.md` (the tile is already unlocked at the user's request);
  - Phase H: an EMPTY target repository (GitHub or Azure DevOps) set as the project's target, and a connection
    wired to Migration Development with WRITE (token: contents + pull requests write on that repository only);
    then run `click-through-phase-H.md` and flip the tile. Also the organisation's package mirror for modules
    with third-party dependencies (the build sandbox has no network);
  - the Cutover policy decision R13 (K).

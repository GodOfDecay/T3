# Track 3 — Session handoff (read this first)

**Written:** 2026-09-28; **updated 2026-09-29 at the end of Phase D** (session 3).
**Branch:** `akshat_track3` on `origin` (the team collaborates there; never `track-3`). Commits: `8c90522c`
(A, B, most of C), `9f2e81f6` (C closed + Redis reader fixes), then the Phase D commit. `git push` is blocked
for Claude in auto mode — ask the user to run `! git push`.
**Read next, in this order:** this file → `help/Track-3/build-log.md` (Entries 1–10, the evidence) →
`docs/superpowers/plans/2026-09-28-track3-master-plan.md` (the phase map) →
`help/Track-3/Track-3 Implementation Prompt.md` (the rules; §9 = mandatory stops).
Do **not** re-read the ~8,000 lines of Track 3 design docs up front — read each agent's section of
`track3-research.md` §6.x only when you start that agent's phase.

---

## 1. What the user asked for (standing instructions)

- Build Track 3 phase by phase per the master plan, "in the same manner" as A and B: tests first where
  possible, **mutation-prove every guard (R46)**, an **independent adversarial reviewer** (R54), log
  every decision/finding in `build-log.md`, give the user a click-through script per phase.
- **No timeline** thinking. Phases are ordered by dependency only.
- Track 3 = Code Modernization; when a user creates a project and picks Track 3, the project must open
  with the ten Track 3 agents (done — see §3).
- Integrations must ride the existing platform (BU grant → stage wiring → access level → project
  credential → `get_connector_for_session`); **Track 1/2 must keep working** (it is complete).
- ClaimTrack is a **simulated customer** scenario; there is **no real legacy code yet** — do not try to
  pull repos or test credentials; the user said Azure DevOps and the model key work.
- **DONE:** `akshat_track3` exists on GitHub (pushed by the user, 2026-09-28). Push further commits there —
  NOT to `track-3`. The first commit holds: everything — this session's work AND the previously untracked files
  (`help/Track-3/…` including the moved docs; the deleted `help/track3-*.md` are the moved originals).
  Commit message must end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`. Before pushing:
  `git status` review — `.env` / `.env.test` are gitignored (keep it so); do not commit `backend/files/`,
  logs, `node_modules`. Then continue with **Phase D**.

## 2. Environment (verified this session — do not re-investigate)

| Thing | Fact |
|---|---|
| App DB | **Local** native PostgreSQL 16 on **5432**, db `sdlc_product`, app role `sdlc_app` (rolbypassrls=false ✔). The Azure Postgres/blob hosts in the old `.env` do not resolve; `.env` was switched (Azure lines kept, commented). |
| Test DB | `sdlc_product_test` on 5432 via `backend/.env.test` (differs from app DSN ✔). |
| Docker Postgres 5433 | LiteLLM's (`sdlc_agentic`, empty). Not the app DB. |
| Redis | Docker `sdlc-redis` on 6379 (start Docker Desktop first). |
| File storage | `STORAGE_BACKEND=local`, `ARTIFACT_STORAGE_ROOT=files/artifact-store`. **Uploads fail (Windows MAX_PATH, 325-char paths) until the user enables long paths** (admin PowerShell, in the click-through). 5 failures in `tests/test_artifact_scope_and_upload.py` are this — known, not a regression. |
| Backend port | **8001** (both `backend/.env` and `frontend/.env.local`; docs say 8004 — ignore). |
| Commands | `uv run alembic …` / `uv run uvicorn …` **fail** ("uv trampoline"); use `uv run python -m alembic …` / `python -m uvicorn`. Tests: `cd backend && set -a && . ./.env.test && set +a && uv run python -m pytest <files> -q -p no:cacheprovider`. Frontend: `node node_modules/typescript/bin/tsc --noEmit`, `node node_modules/vitest/vitest.mjs run <files>`, `node node_modules/eslint/bin/eslint.js <files>` (**not npx** — it silently "passed" when node_modules was broken). |
| node_modules | Was broken (pnpm links pointed at the pre-move path `…\Desktop\SDLC`); rebuilt with `pnpm install --frozen-lockfile --offline`. Lockfile unchanged. |
| Boot | Backend boots against the dev DB (checked at 0066; `/health` 200). Known warnings: no user holds security_engineer / devops_engineer; Langfuse DB (Azure) unreachable. |
| Personas that exist | `ba@gmail.com`, `projadmin@gmail.com`, `architect@gmail.com`, `dev@gmail.com`, `tester@gmail.com`, `buadmin@gmail.com`, `admin@pwc.dev`. **`DEV_LOGINS.txt` personas do not exist here.** Only one BA → a BA-produced version is approved by the PA. |
| Projects | "Migration test" `45a0d49e-…` (Track 3, ADO wired, project credential), "Test" (Greenfield). |

**Migration heads:** code head `0070_approval_sla_escalation`. **Test DB: 0070. Dev DB: 0067** — 0068–0070 need
the user's OK before they go on dev, and the backend's ORM now has their columns (approving a version on dev fails until then).
⚠ `0067` reached the dev DB without an explicit approval (origin unknown — probably the reviewer
agent). Verified identical to the real migration (FORCE RLS, all trigger checks, grants, 0 rows).
Tell the user. `0068`/`0069` are NOT on dev; applying them to dev needs the user's OK (§9 of the prompt).

## 3. Done (all tests green unless noted; evidence in build-log)

**Phase A — audit + shell fixes** (Entry 4): `modernization_common/standalone.py` in-flight guard, tracked
cancellable turns, system prompt "delivered" = in the checkpoint **and tagged `system:<agent>`**
(enterprise checkpoints share one store); `STOPPED_NOTE` on cancelled replies; R39 in Dependency and Risk
(`vulnerabilities_scanned`, "not scanned", unmeasured factor). Deferred (need the user): private-repo
clone with a project credential; browser click-through.

**Phase B — retrofit agents 1–2; owner rows 3–10** (Entries 5–6):
- Owner rows for 8 ids in every map + migration `0066` (perms granted to owner, project_admin, bu_admin).
  Ids: `design_modernization`, `strategy`, `testing_modernization`, `development_modernization`,
  `code_review_modernization`, `security_modernization`, `deployment_modernization`,
  `documentation_modernization`. **D10:** development_modernization owner = developer (one-agent-one-role).
- `frontend/lib/tracks.ts` Track 3 roster = the ten Track 3 ids (was Track 1 ids!). Tiles 3–10 "coming soon".
- `gate_routing.GATE_OWNER` → read-only view of `AGENT_OWNER_ROLE` (had no callers); unknown stage raises.
- `require_stage_approval` also requires a registered stage (`STAGE_ORDER`).
- Both agents bind `make_document_tools` + `make_approval_tools` (`DOCUMENT_TOOLS` in `agents/intake.py`,
  `agents/assessor.py`); shared prompt parts `modernization_common/prompt_parts.py`.
- Migration Intent reads the tech stack: `modernization_common/tech_stack.py` (`get_project_tech_stack`,
  `source` project_selection | bu_default | none | **unreadable**); `brief.tech_stack` stamped by code.
- `upstream_from_pages` → `read_upstream` (consumption recorded **once per session+version**); enforced +
  none approved → said explicitly.
- Pages: `track3-agent-page.tsx` (DocumentList, TechStackChip); `version-view.tsx` (producer told why,
  **`producedByMe()` matches id OR email — the API relabels producedBy to email**; "Read by");
  Track 1 `stage-version-panel.tsx` got the same producer fix; `assessment-view.tsx` "not scanned"/"n/m";
  breadcrumbs; `custom_roles._PHASES` + pin test; Orchestrator router roster names.
- Independent review done (4 Important + 6 Minor → one fix wave, all mutation-proven).
- Click-through for the user: `help/Track-3/click-through-phase-A-B.md` (not yet run by the user).

**Phase C — backbone: DONE** (Entries 7–9; click-through `help/Track-3/click-through-phase-C.md`):
| Item | Where | Evidence |
|---|---|---|
| 1 Hand-over schemas + ClaimTrack fixtures | `modernization_common/handover/` | 72 tests, 43/43 mutants |
| 2 Ledger | `0067`, `ModernizationModule`, `shared/services/modernization_ledger.py` | 24 tests, 6/6 + 7/7 |
| 3 Provenance/restore/compare/staleness | `0068`, `shared/services/version_lineage.py`, `shared/routers/version_lineage.py` | mutation-proven |
| 4 Repository roles | `0069`, `ProjectRepository`, `shared/services/repository_roles.py` | 41 tests (with 6), 7/7 |
| 5 UI: fallback dialog, restore, compare, staleness | `components/modernization/version-view.tsx` | 19 render tests, 7/7 |
| 6 PA fallback | `shared/services/fallback_approval.py`; publish route (Track 3 stages only) | 8/8 + 3/3 |
| 7 Programme API/page/strip/settings/seed | `shared/routers/modernization_programme.py` (`/modernization-programme`), page `/projects/[id]/modernization`, `ProgrammeStatusStrip`, Settings → Code Modernization tab, `scripts/seed_track3_fixture.py` | 10 API tests 6/6; 11 UI tests 11/11; seed test |
| SLA escalation | `0070`, `workers/approval_sla_sweeper.py` (lifespan, 15 min), kind `approval_sla_passed` | 7 tests, 7/7 |
| PA reach floor | `agent_access.pa_floor_applies`, `project_scoped.set_override` (409) | 7 tests, 5/5 |
| Independent review (R54) | build-log Entry 8 | 9 Important + 9 Minor; all confirmed against the code |
| Fix wave | see §3a | 16 tests; mutation 15/15 backend + 5/5 frontend |

**Phase D — agents 1–2 emit their hand-over: DONE** (Entry 10; click-through `click-through-phase-D.md`):
Migration Intent v3 (`must_not_change` checked word for word by `modernization_common/verbatim.py`,
`must_not_change_verified`, measure `kind`, record refuses a brief that cannot be handed over); assessment
schema 2 (`M-xx` by path, `analysis/unknowns.py` "Not assessable statically", `golden_master` pointer);
`restore_version`/`compare_versions` chat tools; `GET …/versions/{v}/packet` + the page's Hand-over line;
`handover/emit.py` is the one envelope builder. Mutation 23/23 + 10/10 + review fix wave 20/20; review 5
Important + 7 Minor, all handled (Entry 10 table).

**Platform bugs found and FIXED on the way (Entry 9):** three long-lived Redis readers died 2 s after
startup (2 s socket timeout vs a blocking read): audit retry worker, artifact-event listener, pipeline workers
— `shared/redis_client.blocking_read_timeout`. That was the "Redis read-timeout flake".

**Reported to the user, not changed (Track 1):** `get_db_session_superuser` is not BYPASSRLS under `sdlc_app`,
so `workers/run_sweeper.py`'s cross-tenant query on `runs` (FORCE RLS) very likely expires nothing.

### 3a. Review fix waves

Phase C: build-log Entry 8/9. Phase D: build-log Entry 10 (table of all 12 findings and what was done).

## 4. Next session — start here, in this order

1. `git status` / `git log -4` on `akshat_track3`; confirm `origin/akshat_track3` has the Phase D commit
   (else ask the user to push). Start Docker Desktop. Heads = 0070 (test DB 0070; dev DB 0067).
2. Ask the user: apply 0068–0070 to the dev DB? run `scripts/seed_track3_fixture.py` there? Their
   click-throughs for A/B, C and D are still unrun.
3. **Phase E — Target Architecture** (`design_modernization`, master plan §4; research §6.3 only). It reads the
   brief and assessment PACKETS (`handover/emit.py`), turns `must_not_change` into CT-xx, and must
   cross-check cited module ids against the pinned assessment version (D14).

## 5. Decisions already taken (don't re-litigate)

D1 packets = Pydantic; D3 envelope status uses the version store's vocabulary; D4 migration record
`outcome`; D5 conservative security policy; D6 `protects`/`protects_measures`; D7 cross-artifact rules live
in record tools; D8 retrofit before backbone; D9 repository roles are their own table (not the stage-mode
key); D10 dev_modernization owner = developer; D11 Track 3 pages keep their own version list (no
StageVersionPanel); D12 Orchestrator wire ids added WITH each agent's registry entry (pinned equality test);
D13 "Migration Strategy" label; D14 module-id drift across commits is checked by Target Architecture's packet
validation (id → path against the pinned assessment), not by the assessment. PA fallback applies to **Track 3 stages only**; Track 1 publish unchanged.

## 6. Things to AVOID (already tested/learned — each cost real time)

- **Don't** trust `npx tsc`/`npx vitest` — use `node node_modules/...` (above).
- **Don't** launch `bash` from Python subprocess — it is WSL's. Use `C:\Program Files\Git\usr\bin\bash.exe`.
- **Don't** run two DB-backed pytest processes (or a reviewer agent's tests alongside mutation runs) at once —
  tenant cleanup deletes the other's rows. Tell reviewer agents not to run DB tests while you mutate, or wait.
- **Don't** leave a mutated migration applied: after trigger mutation runs, re-apply the real migration
  (`help/Track-3/tools/reset_ledger.sh`) and check `relforcerowsecurity`.
- **Don't** write `\n` inside Python string literals through heredoc-generated edit scripts — it became a real
  newline twice (prompt files, standalone.py). Use `chr(10)` or a constant, then import-check the module.
- **Don't** insert a class between a FastAPI decorator and its function (happened in the publish route).
- **Don't** use plain `JSONB` for a nullable list column that has a "must be array" CHECK: Python `None` becomes
  JSON `null` → CHECK fails → insert retry rollback → misleading RLS error. Use `JSONB(none_as_null=True)`.
- **Don't** compare `producedBy` with the session **id** — the API returns the **email**. Use `producedByMe()`.
- **Don't** re-investigate: the Azure DB/blob (unreachable), DEV_LOGINS personas (absent), the
  `ws-ticket.test.ts` 5 s timeout under full-suite load (passes alone), `test_seeded_catalog_matches_the_code_matrix`
  (order-dependent once; passes alone).
- **Don't** decrypt/inspect stored secrets (blocked by policy; user confirmed connections work).
- **Don't** add Orchestrator wire ids for unbuilt agents (breaks the equality pin — D12).
- **Don't** query FORCE-RLS tables through `get_db_session_superuser` expecting cross-tenant rows — the app role
  is not BYPASSRLS, so it returns nothing, silently. Go tenant by tenant (`organizations` is not RLS-scoped), as
  `workers/approval_sla_sweeper.py` does. The same applies to reading them back in tests.
- **Don't** pass `--timeout` to pytest (no plugin installed; the run aborts with a usage error).
- **Don't** add a notification kind in only one place: the DB CHECK (migration), and frontend
  `lib/schemas/notification.ts` (the bell's Zod enum rejects the whole list otherwise).
- **Don't** call a failing test a "flake" without a control run: the Redis "flake" was three dying workers
  (Entry 9). Use `-o faulthandler_timeout=300` to get the stack of a hung test.
- **Don't** trust `grep "if False:"` after an interrupted mutation run — run
  `help/Track-3/tools/verify_no_mutants.py help/Track-3/tools/specs-phase-c help/Track-3/tools/specs-phase-d`
  (a mutant reached a pushed commit once; Entry 9).
- **Don't** hand-edit `frontend/components/modernization/__tests__/fixtures.json` — regenerate it
  (`cd backend && uv run python ../help/Track-3/tools/regen_view_fixtures.py`).
- **Don't** re-read all design docs; don't re-audit Phase A/B/C/D.

## 7. Things to CHECK before claiming anything

- Track 1 regression set (test DB): owner/RBAC files (`test_agent_ownership_is_single_sourced`,
  `test_agent_reach_matches_frontend`, `test_agent_registry_portfolios`, `test_enterprise_rbac_catalog`,
  `test_m9_migration_heads`, `test_rbac_*`, `test_stage_approval_dependency`, `test_consequential_gate`,
  `test_custom_role_phases_match_frontend`, `test_track3_owner_rows`, `test_gate_routing_single_owner_map`),
  artifact files (`test_artifact_*`, `test_consumption_grants`, `test_document_*`,
  `test_upstream_tools_honour_the_flag`), `tests/orchestrator2` (760 passed), `tests/development`,
  `tests/modernization_common`, `tests/discovery`, `tests/requirements_modernization`,
  `test_modernization_standalone`, `test_legacy_code_*`. Last full frontend run: 1151/1151.
- After any migration: `alembic heads` (exactly one), up/down/up on the test DB, `scripts.grant_app_role`,
  FORCE RLS on new tables.
- A mutation "kill" counts only with a named failing test (and, for command specs, `PYTEST_EXIT`); run an
  **unmutated control** first.
- Backend boots (`python -m uvicorn process_api:app --port 8001`) — role_permissions are verified at boot.

## 8. Useful paths

- Rules: `help/Track-3/Track-3 Lessons from Track 1-2.md` (R1–R57). Plan: master plan file above.
- Mutation harness + examples: `help/Track-3/tools/` (`mutate.py spec.json`).
- Track 3 shell: `backend/agents_orchestrator/modernization_common/`. Built agents:
  `discovery_agent/`, `requirements_modernization_agent/`.
- New services: `shared/services/{modernization_ledger,version_lineage,repository_roles,fallback_approval}.py`.
- Frontend Track 3: `frontend/components/modernization/`, pages `app/(app)/projects/[id]/{requirements-modernization,discovery}`.

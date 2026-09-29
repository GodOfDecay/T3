# Track 3 — Session handoff (read this first)

**Written:** 2026-09-28; **updated in session 2, near the end of Phase C** (fix wave mid-mutation).
**Branch:** `akshat_track3` — Phases A, B and most of C are **committed locally** on it (first commit on the
branch, parent `621b8904` = `akshat_main`), **pushed to `origin/akshat_track3`** (tracking set; the team collaborates there).
**Read next, in this order:** this file → `help/Track-3/build-log.md` (Entries 1–8, the evidence) →
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

**Phase C — backbone: nearly done** (Entries 7–8; click-through `help/Track-3/click-through-phase-C.md`):
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
| Fix wave | see §3a | code + 16 tests pass; **mutation NOT done** |

**Reported to the user, not changed (Track 1):** `get_db_session_superuser` is not BYPASSRLS under `sdlc_app`,
so `workers/run_sweeper.py`'s cross-tenant query on `runs` (FORCE RLS) very likely expires nothing.

### 3a. Phase C fix wave (review findings) — where it stopped

Fixed in code, with one guarding test each in `backend/tests/modernization_common/test_phase_c_review_fixes.py`
(16 pass, run twice on a quiet DB):
- #1 a second publish rewrote `approved_as`: the route now returns an already-published Track 3 version untouched.
- #2 expired bindings counted: `fallback_approval._LIVE` adds `expires_at`.
- #3 restore let the original producer approve: `version_lineage.producers_of` walks `restored_from`.
- #5 case/host spelling defeated target≠legacy: `normalize` lower-cases paths and maps `*.visualstudio.com`.
- #6 Programme settings/repository PUTs now write audit events.
- #7 Track 3 reject is scoped to the project's owner role or Project Admin.
- #8 restore/compare/staleness are Track 3 stages on Track 3 projects only; restore needs agent reach.
- #9 a grant read is pinned as `granted`.
- #10 a rejected input marks the version stale.
- #11 a producing owner does not "staff" the role.
- #12 the SLA sweep re-tries an unwritten notification.

Honest copy (#4 no push tool calls `assert_target_write` yet; #14 nothing moves the ledger yet), and:
- #13 the repositories error state; #15 the tab only on Track 3; #18 the duplicate-key test data.
- The reviewer's premise on #7 exposed a real Phase B bug: the Track 3 version view offered the PRODUCER a Reject
  button, and the backend always refuses it ("cannot also decide it"). The button is removed; the copy, the test and
  click-through A/B B7 are corrected.

Left as is (logged): #16 person-level overrides are outside the PA floor (latent, no writer); #17 Approve is shown to
tenant-union permission holders who then get a self-explaining 403.

## 4. Next session — start here, in this order

1. `git status` (clean apart from untracked scratch) / `git log -2` on `akshat_track3`. Start Docker Desktop.
   Heads = 0070 (the test DB is at 0070; the dev DB is at 0067).
2. **Mutation-prove the fix wave.** Specs are in `help/Track-3/tools/specs-phase-c/spec_fix_*.json` (backend:
   `fix_av`, `fix_fb`, `fix_lin`, `fix_linr`, `fix_sa`, `fix_sla`, `fix_rr`; frontend: `fix_ui1`, `fix_ui2`).
   - The first run was stopped by the user mid-way and **left a mutant in `shared/routers/artifact_versions.py`**.
     It was restored by hand and verified (the reject check reads `if owner not in roles and "project_admin" not in roles:`).
     After any interrupted run: `grep -rn "if False:" backend/shared backend/workers`.
   - Still to write: a spec for the #6 audit (rename an `event_type`).
3. Re-run the full regression set (§7) and the full frontend suite on the fixed code. A run was started before
   the fix wave and stopped, so **there is no regression result for the current code yet.**
4. Finish build-log Entry 8 (a fix-wave section with the mutation results).
5. Ask the user: apply 0068–0070 to the dev DB? Run `scripts/seed_track3_fixture.py` there?
6. Commit and push to `origin/akshat_track3` (auto mode blocks `git push`; ask the user to run it). Then **Phase D** (master plan §4).

## 5. Decisions already taken (don't re-litigate)

D1 packets = Pydantic; D3 envelope status uses the version store's vocabulary; D4 migration record
`outcome`; D5 conservative security policy; D6 `protects`/`protects_measures`; D7 cross-artifact rules live
in record tools; D8 retrofit before backbone; D9 repository roles are their own table (not the stage-mode
key); D10 dev_modernization owner = developer; D11 Track 3 pages keep their own version list (no
StageVersionPanel); D12 Orchestrator wire ids added WITH each agent's registry entry (pinned equality test);
D13 "Migration Strategy" label. PA fallback applies to **Track 3 stages only**; Track 1 publish unchanged.

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
- **Don't** re-investigate: the Azure DB/blob (unreachable), DEV_LOGINS personas (absent), the Redis read-timeout
  flake in `test_artifact_publication_routes.py` (moves between tests run to run; Redis healthy; a pristine-HEAD
  comparison was inconclusive because the test DB schema is ahead — logged as an environment flake), the
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
- **Don't** re-read all design docs; don't re-audit Phase A/B/C.

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

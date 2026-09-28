# Track 3 — Lessons from Track 1/2, and what they change

**SDLC Platform · Evidence-based build rules for the eight unbuilt Track 3 agents**

| | |
|---|---|
| Version | 1.1 · 2026-09-28 (adds §7 retrofit of agents 1–2 and §8 frontend in parallel) |
| Branch read | `akshat_main` (after merging `origin/deploy-final`) |
| Audience | Whoever builds Track 3 agents 3–10 (people and AI assistants) |
| Companion documents | `Track-3 Flow document.md` (what each agent does), `Development-Plan_track3.md` (schedule), `track3-research.md` (design and system prompts), `Track-3 Implementation Prompt.md` (the prompt that applies this document) |

## How this document was made

Every Track 1/2 planning, audit and issue document was read and then compared with what is in
the repository today. Where a document and the code disagreed, the code wins and the
disagreement is recorded, because a stale claim in a plan is itself one of the failure patterns
below.

| Source | What it contributed |
|---|---|
| `desicions and issues.txt` (1,109 lines) | 15 issues from live-verifying the Development agent, including a cross-tenant source-code leak, two credential-forwarding bugs and a test suite that wiped the dev database |
| `help/portfolio-1-agent-status.md` | Per-agent status; "real code, no proof" finding for Code Review, Security, Documentation |
| `help/requirements-design-e2e-plan.md` | Four gaps on Requirements/Design; three of the plan's own first-draft claims withdrawn after reading the code |
| `help/artifact-approval-and-consumption-plan.md`, `help/artifact-scoping-and-document-consumption-plan.md` | Ownership maps, immutable versions, publication gate, document scope (all built) |
| `docs/superpowers/specs/2026-08-30-approval-system-full-audit-findings.md` | Live per-persona audit; RLS silently inert; stale dev server |
| `ORCHESTRATOR_HANDOFF.md`, `orchestrator_instruction.md` §11–§18 | Five-phase orchestrator rebuild; live all-nine run found no agent filed a document; the wrapper-gap pattern (four instances) |
| `help/langfuse-integration-plan.md`, `deployment-agent-plan.md`, `pm-agent-plan.md`, `multi-track-agent-access-design.md` | Traces, deploy-gate, planning patterns, the access design Track 3 sits on |
| Repository (this session) | Migration head is `0065`; the two built Track 3 agents, `modernization_common/`, the registry, the tests and the frontend wiring were listed and read |

---

## 1. Track 1/2: what was planned, what shipped, and the real gap

The single most useful finding across all the Track 1/2 documents:

> **The agents were mostly real code. What was missing was the wiring around them and proof
> that they work.** Code Review, Security, Documentation, Requirements and Design were each
> assumed to be stubs by a design document that said "assume broken". Each turned out to be a
> real 1,000–5,000-line LangGraph implementation. The work that mattered was closing specific
> gaps, and finding, by running them, the defects that unit tests had certified as fine.

| Agent | Size (lines, non-test) | What was planned | What the first live run found |
|---|---|---|---|
| Requirements | ~5,500 | Real agent; board writes; approvals | Board tools existed but every one answered "unreachable": workers never named the stage, so the connector's access level resolved to nothing; board kind was hardcoded to Azure DevOps |
| Design | ~5,170 | Real agent; hand-off from Requirements | The Requirements payload **never arrived**: a superuser session read `runs` under FORCE RLS and got zero rows; nothing logged. Figma reads were also silently denied |
| Development | ~6,440 | Real agent, verified | Cross-project RBAC leak; three ungated Consequential tools; two credential-forwarding bugs (same bug class, two call sites); a dead tool guaranteed to fail; a cross-tenant source-code broadcast |
| Code Review | ~2,370 | Real agent | 9 tests, none ran the agent loop; a real e2e test was added |
| Security | ~2,310 | Real agent | SBOM printed a confident `vulnerabilities: 0` when no scan had run |
| Documentation | ~2,060 | Real agent | RTM prompt let the model present textual guesses as structural matches; SharePoint was dead code (since fixed) |
| Orchestrator (`orchestrator2`) | ~6,580 | Rebuilt in five phases | The old engine had a system prompt for **3 of 9** agents; the first all-nine live run found **not one agent filed a real document** |

**Track 3 today** (verified in the repository): two agents built — Migration Intent
(`requirements_modernization`, ~2,280 lines) and Dependency and Risk (`discovery`, ~2,210
lines) — plus `modernization_common/` (graph, standalone socket, versions, files, legacy
code, ~1,380 lines). They follow the Track 1 pattern and already contain several of the
fixes below (project-scoped BYOK, per-turn consent, terminal `activity_update`, track-scoped
access check). Agents 3–10 are designed only. Migration head is `0065_tech_stacks`.

---

## 2. The failure patterns, and the Track 3 rule each one produces

Each pattern lists what happened, why nothing caught it, and the rule. The rules are numbered
`R1…` so the implementation prompt and reviewers can cite them.

### A. Wiring gaps: the agent is right, the wrapper around it is not

| # | What happened | Why it stayed hidden | Rule |
|---|---|---|---|
| A1 | `orchestrator2` loads an agent's **graph**, not the `*_agent_api.py` wrapper. Everything the wrapper did (connector, MCP tools, per-run contextvars, `runs.development_artifacts`, the repo checkout) had to be re-provided. Four instances, then a fifth (repo-reading agents had no workspace and answered from the conversation, filing a document that looked like a real review) | The agent did not fail; it answered plausibly from chat. The tell was `code_review_artifacts` being NULL in the database | **R1.** For every Track 3 agent, list what its standalone wrapper establishes (identity, run, connector, consent, model, workspace) and prove the Orchestrator path establishes the same. `tests/orchestrator2/test_run_context_is_complete.py` only compares `ws_helper` contextvars; per-run state held as session-state assignment is invisible to it, so test that explicitly |
| A2 | Board tools were bound but the workers called `get_connector_for_session(project_id=…)` without `agent_id`. Since migration 0024 access is stored per (stage, tool), so `effective_access` returned nothing and **every board tool in every run was denied** | Fails in the safe direction: the feature is dead behind a plausible message | **R2.** Every connector obtained for an agent names the stage (`agent_id`) and the project. A connector with no stage permits nothing. Add a test per agent that a granted stage works and an ungranted stage refuses legibly |
| A3 | Board kind hard-coded to `azure_devops`; a Jira-wired tenant never reached its board. `provider_kind` legacy column defaults to Azure DevOps for nearly every project | Looked up the grant under the wrong key, found nothing, reported a permission error about a provider the tenant never chose | **R3.** Resolve the connector kind from the stage wiring, never a default. `None` means "inject no connector" and the agent says "connect a board" |
| A4 | Design's hand-off read used a superuser DB session under FORCE RLS: returned **zero rows**, `build_context` returned `""`, Design never saw the Requirements payload | No error. "No upstream yet" is a legitimate answer on the first stage, and `upsert_agent_session` swallows its own failures | **R4.** Every read of another stage's artifact goes through a tenant-scoped session (`get_db_session_for_tenant`) or `read_upstream`, and every hand-off has a **real-Postgres test with a control that fails if the copy is removed** |
| A5 | A backend route with no handler under `frontend/app/api/` returns Next's own 404 and reads as a backend fault ("shipped once already this week") | The browser never reaches FastAPI; it calls `/api/...` | **R5.** Every new backend route the browser uses gets its BFF handler in the same change. `frontend/__tests__/bff/every-api-path-has-a-proxy.test.ts` covers it; multipart needs its own handler (not `forward()`, which sends JSON) |
| A6 | Chat never worked in local auth mode for **any** agent: `mintWsTicket` called `mintBffToken`, which throws by design in local mode; every other BFF call already used `bearerForRequest` | Every earlier chat test hit the backend handler directly, bypassing the Next bridge | **R6.** At least one live browser-path check per new agent (page → BFF → WS). Wire the `agentWsPath` case in `app/api/chat/route.ts` and pin it in `chat-agent-map.test.ts` |
| A7 | Project-scoped Azure DevOps credentials (`project_integration_credentials`) were never consulted: `resolve_auth(tenant_id)` alone returns empty for a project-scoped PAT. Fixed in the REST routes, then **the identical bug** reappeared in the chat/WS flow (`_bind_pulled_workspace`); every ADO write sent an empty password and Azure answered with a 302 to its sign-in page, not a 401 | Same bug class, two call sites; the symptom pointed at PAT scope, not code | **R7.** Every credential lookup passes `project_id` **and** `owner_id`. When you fix a lookup, grep for every other caller of the same function in the same change. The Migration Development and Cutover write to a *target* repo with these credentials |
| A8 | `plan` and `design` had no output-directory mapping, so a Project Manager PDF written to a valid path never reached the panel; `orchestrator2` never wrote `runs.development_artifacts` at all | Grep for the column name across the package returned nothing | **R8.** For each new agent add: `_run_stage_output_dir` mapping, `runs.<artifact>` writer, `AGENT_REGISTRY[id].output_artifact` (the **only** source of the column name; never type the list out — `requirements` writes `requirements_payload`, not `requirements_artifacts`, and a hard-coded guess reads `None`, indistinguishable from "not run yet") |
| A9 | The ORM model never got the new `conversation_messages.agent_id` column; every unit test passed dicts, and a dict fake cannot catch a missing mapped column; first real read raised `AttributeError`, reported to the agent as "the conversation could not be read" | Twelve mutants were already dead before a live read found it | **R9.** A new column is added in **three** places (migration, ORM, every reader) and a test asserts the mapper declares what the loader reads (`test_orm_matches_the_schema.py` pattern) |

### B. Access, ownership and approval

| # | What happened | Rule |
|---|---|---|
| B1 | **Three owner maps** (`frontend/lib/roles.ts`, `shared/governance/routing.py`, `shared/authz/permissions.py::_PHASE_PERMISSION`) disagreed. `agent_owner_role()` had a `.get(phase, "project_admin")` default, so a missing key answered plausibly. Live defect: `code_review`'s named owner was Project Admin, who cannot approve it (`artifact:approve_code_review` is held by `architect` alone). Also `artifact:approve_deployment` was held by nobody because no user had `devops_engineer` | **R10.** Each new agent is added to **all the owner maps** in one change (the three named here **and** `shared/services/orchestrator/gate_routing.py::GATE_OWNER`, a fourth table whose `.get(stage, "product_manager")` default has the same fault), keyed on the **backend** stage name with UI names as aliases, no default that swallows a miss, and `test_agent_ownership_is_single_sourced.py` plus `test_agent_reach_matches_frontend.py` stay green. Prove the named owner **can** pass the gate and that at least one active user holds the role |
| B2 | `require_agent_access(agent_id)` reads the project id from a path parameter and **returns immediately when there is none**. Adding it to a router whose routes carry `project_id` in a Form field or JSON body enforces nothing while reading as gated. Also `platform_role_for` resolves a role held **anywhere in the tenant**, a cross-project leak | **R11.** Per-message `assert_agent_access_for_chat_on_track` (membership + track + role reach) on every chat message and REST call. The router dependency is an extra floor, never a substitute. Never trust a client-sent `user_id` or `tenant_id`; take them from `request.state` |
| B3 | Gated actions were "enforced by prompt text only" (`open_docs_pr`, `publish_to_sharepoint`, board writes): the tool node executes whatever the model emits. `delete_board_item` calls itself IRREVERSIBLE | **R12.** Every Consequential tool calls `authorize_consequential(stage, action=…)` in code (`shared/authz/consequential.py`). It runs **two** checks: does this person hold the owning role, and did they approve **this turn**. `push_gate_enabled`/`push_approved` in the Development agent asks the human but never checks the role, so the Migration Development must use both |
| B4 | A queued worker run sets no user (`set_user_id` is called only on the interactive path), so a board write from a background run now **refuses**. Correct under the tier model, but a real behaviour change | **R13.** Anything Consequential in Track 3 (target push, capture run, each cutover step, board writes) is interactive-only, or raises a gate and waits. Never give background runs a blanket exemption |
| B5 | Self-approval on gates was unimplementable because `runs` recorded no initiator; migration `0038` added a nullable `created_by` (webhook and pre-0038 runs have none). Reject by the initiator stays allowed; unknown initiator does not block | **R14.** No self-approval anywhere. Reject-by-initiator is allowed (blocking it strands a run). The UI must say **why** ("you ran this; someone else accepts it") rather than show a disabled button or a 403 toast |
| B6 | Approvals of a mutable payload are theatre: `runs.{stage}_artifacts` is overwritten in place, so the approval record survives but the thing approved does not | **R15.** Every Track 3 artifact is frozen as a numbered `artifact_versions` row (trigger blocks payload edits; `published_by <> produced_by` is a DB CHECK). Consumers read via `read_upstream` (published only, every read recorded in `artifact_consumptions`); **there is no fallback to a draft when publication is enforced**, or the gate is decorative |
| B7 | "Publish once, consume freely": per-consumer approval would be up to 72 pairs per project, rubber-stamped within a week | **R16.** Do not build a second approval system. Documents ride the version's `covers` list. Only three cases raise a consumption request: an unpublished draft, cross-project reuse, a superseded pin |
| B8 | A silent upgrade is indistinguishable from correct behaviour until something breaks | **R17.** A consumer pinned to version N is **notified** when N+1 publishes, never switched (staleness badge, not invalidation) |

### C. Tenancy, data and storage

| # | What happened | Rule |
|---|---|---|
| C1 | **RLS was inert in local dev** for a long time: `POSTGRES_CONN_STRING` pointed at the `postgres` superuser, which bypasses row-level security unconditionally (`FORCE` does not apply). Every "live-verified" claim depending on RLS as the enforcement mechanism was made with the backstop absent. A cross-tenant notification row appeared in a differently-scoped query | **R18.** Run the app as `sdlc_app` (`NOSUPERUSER NOBYPASSRLS`); keep `POSTGRES_MIGRATIONS_CONN_STRING` as `postgres`. Verify `rolbypassrls` is false before any live verification. Every read through `get_db_session_superuser()` needs an explicit tenant predicate. The new ledger, baseline and finding tables are FORCE RLS on `app.current_tenant_id` (**not** `app.tenant_id`, which matches nothing and reads as permanently empty) |
| C2 | `ConnectionManager.broadcast` sent to **every open WebSocket on the process** whenever a `session_id` had no registered socket. A `file_diff` carrying a project's full source code went to strangers on other tenants. The Orchestrator never registers sockets, so every Orchestrator run took that branch and a design document streamed onto unrelated sockets | **R19.** Anything carrying customer content (code, diffs, baselines, recordings, findings) uses `broadcast_to_session`, which sends only to registered connections and does nothing otherwise. Add a security-property test with a marked payload that asserts nobody else receives it. Track 3's behaviour recordings make this the highest-value payload on the platform |
| C3 | Generated documents used a flat process-wide `outputs/` with fixed names (`brd.docx`): one tenant's document overwrote another's and any `artifact:view` holder could download whichever was on disk | **R20.** Blob names are composed **by code**: `{tenant_id}/{bu}/{project}/{agent}/{run}/{type}/{filename}`; the model supplies only a sanitised leaf name (no `/`, no `..`). Use `shared/services/artifact_store.store_artifact` (one helper, so nobody forgets the prefix). Serve via SAS URL generated at read time, never the raw blob URL, and filter on the caller's verified tenant. Degrade, do not crash, with no blob configured |
| C4 | Adding a NOT NULL column to a populated table fails outright | **R21.** Migration: add nullable, backfill, then tighten, in one migration, and round-trip up/down/up on a database built from scratch |
| C5 | Two migrations were both numbered `0057` (Track 3 Phase 1 and Langfuse) and needed a merge migration `0059` | **R22.** Run `alembic heads` immediately before numbering and again before merging; the current head is `0065`. The `test_m9_migration_heads.py` guard exists for this |
| C6 | Services must not commit: committing drops `app.current_tenant_id` and the next statement in the same request reads an empty table | **R23.** New services leave the transaction open for the caller (`get_db_session` owns the single commit) |
| C7 | Migrations run as the superuser; the app role needs grants | **R24.** After a migration adding tables, run `scripts.grant_app_role` and confirm every table is readable by `sdlc_app` |

### D. Model and agent behaviour

| # | What happened | Rule |
|---|---|---|
| D1 | `gpt-5` models reject any `temperature` other than 1 (`UnsupportedParamsError`); `_build_llm` hard-coded 0.1 for everyone. Same pattern likely in sibling agents | **R25.** Build the model once in a shared place; skip `temperature` for the gpt-5 family only (never litellm's global `drop_params`, which swallows every other unsupported parameter). Track 3's `modernization_common/graph.py` is the place; check it |
| D2 | `_CALL_TIMEOUT_SECONDS` was 30 s; a trivial gpt-5-mini completion took 28 s, so every attempt was doomed. Raised to 90 s | **R26.** Long structured outputs (designs, plans, migration records) need the 90 s ceiling **and** streaming; measure a real call before choosing a timeout |
| D3 | Two uncoordinated retry layers (`ChatLiteLLM` `max_retries=2` × `guarded_completion` 3 attempts) = up to **9** requests against an endpoint already saying "back off" | **R27.** `max_retries=0` on the chat model; `guarded_completion` is the only retry mechanism |
| D4 | No env-key fallback: `resolve_chat_model` reads a stash nothing fills unless `resolve_model_for_run` ran first; Code Review and Security call only the former. (The status doc's claim that `resolve_chat_model` "does not exist" was true when written and false a week later.) | **R28.** Use `resolve_model_for_run` + `set_resolved_model` (enforces budgets, grants, rate limits) with typed handling of `NoModelConfiguredError` / `ModelNotEnabledError`; project-scoped BYOK; **no `ANTHROPIC_API_KEY` fallback anywhere**. `testing_agent/config/shared.py` still has one: do not copy it |
| D5 | A leftover `write_development_artifact` tool required the model to invent a `run_id`; guaranteed to fail; two similarly named "finish up" tools produced repetitive tool-calling | **R29.** One finalize tool per agent, sourced from session state (no LLM-supplied ids). `test_agent_tool_names_are_unique.py` must stay green. Never let a tool docstring claim something the prompt never provides |
| D6 | A cancelled turn left a dangling `AIMessage.tool_calls` with no `ToolMessage`; every provider rejects it on the next turn. The first fix set `additional_kwargs["tool_calls"] = []`, which OpenAI also rejects; the key must be **deleted** | **R30.** `sanitize_tool_call_pairing` on every turn (already in `modernization_common/graph.py`); each cancel path tested |
| D7 | The frontend closes a chat bridge after 45 s of no event. No per-session in-flight guard let a second message race the first, producing duplicate replies; rejection and error paths sent `stream_end` but not the terminal `activity_update{complete}`, so the chat hung "busy" for 45 s | **R31.** Per-session in-flight guard; turns run as tracked, cancellable tasks; **every** path (success, rejection, error) ends with `stream_end` **then** `activity_update{type:"complete"}` |
| D8 | `system_injected = True` was set **before** the graph ran; a cancel in that window left the session believing it had delivered its safety prompt, silently, until restart | **R32.** Set "delivered" flags only after the work succeeds |
| D9 | The Development agent's prompt forbade pasting code; nothing filled the gap, so users never saw what changed. `file_diff` events were added | **R33.** Show the Migration Development agent's changes as a diff card. **Do not use Monaco**: `@monaco-editor/react` fetches its bundle from a CDN, the CSP blocks it, and the card hung on "Loading…" forever. The working approach renders a unified diff as a ```` ```diff ```` block through the existing markdown/`CodeBlock` pipeline. Lazy-mount anything heavy |
| D10 | Every agent replied in chat instead of filing a document; design "offered" to save and never did; Testing hallucinated an upload it was never given | **R34.** A deliverable is a **document**: ≥2 headings and ≥400 characters, not a first-person refusal, not an announcement of a file saved elsewhere. Each agent's prompt says "save, don't offer". Receipts go **before** the body when the parser splits on headings |
| D11 | The capture rule was "longer than 200 characters", so a list of branches became a deliverable | **R35.** Refusal detection is first-person and anchored to the opening; "the endpoint cannot validate the total" is a finding, not a refusal, and Security must still be able to file it |
| D12 | The router did not know which agent answered last, so a bare reply of `2` was treated as a new request | **R36.** Route with continuity; an explicit "run the X agent" costs no model call and wins outright |
| D13 | Handoff context fed agents only deliverables; a conversation that produced no document handed the next agent an empty string | **R37.** Agents receive the run's conversation as well, budgeted **per agent** (`PER_AGENT_TRANSCRIPT_CHARS = 6,000`), with attribution (`conversation_messages.agent_id`). A failed read says so; it never arrives as "nothing happened yet" |
| D14 | Context truncation of ~2,400 characters per artifact makes a PRD near-useless. Still open, needs a product decision | **R38.** Track 3 artifacts are large (assessments, designs, plans, baselines). Pass **summaries plus ids** (M-xx, CT-xx, EC-xx) and fetch detail with a tool, never truncate silently; state truncation with a marker |
| D15 | Security's SBOM printed `vulnerabilities: 0` (confident, fabricated-looking) when `scan_dependencies` had never run; Documentation's RTM presented textual guesses as structural matches | **R39.** Never render a "not measured" as a zero or a "not proven" as a match. Use an explicit sentinel (`None`, "not recorded", "Inferred — not structurally traceable, verify manually:") and state that in the prompt and the payload. The Cutover Pack's traceability map exists to be exactly this honest |
| D16 | Tone: a purely procedural prompt read as "dull"; a one-line change got a numbered plan and two confirmation questions | **R40.** Scale ceremony to the size of the change; keep every ⛔ STOP gate; add a short COMMUNICATION STYLE section |

### E. Frontend

| # | What happened | Rule |
|---|---|---|
| E1 | `frontend/lib/orchestrator/protocol.ts` validates every inbound frame with `safeParse` and **drops** anything that fails: an error event carrying an unresolved agent id was the one event guaranteed not to arrive; a block-list `content` (Anthropic) was forwarded raw and the agent "said nothing" | **R41.** Before changing either side of a wire, read the other. Add the new agent ids to the enum, the Zod union and the emitter together |
| E2 | `BUILT_AGENTS` is the single flag that lights a tile; both the tile grid and the page gate read it | **R42.** Two separate flags, in this order: the agent id joins `TRACK_PORTFOLIOS["modernization"]` once it runs end to end **standalone** (so its page and chat work by URL and the Orchestrator can offer it); it joins `BUILT_AGENTS_BY_TRACK` (the tile) **last**, after a person has clicked through the page |
| E3 | A page-level access gate was tested only through `tileStateFor()`, not by rendering the page | **R43.** Render tests for each Track 3 page's gate wiring (the gap was parked twice and remained a gap) |
| E4 | A stage left at the `read` default is a fully working agent with its Consequential tier disabled, the most common configuration, with no designed empty state | **R44.** Design and test the read-only empty state for every Track 3 agent that has a Consequential action ("this stage can read the board but not write to it — ask an admin") |
| E5 | The Next dev server crashed workers after hours of hot reload ("Jest worker encountered 2 child process exceptions") on first compile of unvisited routes | **R45.** Restart the frontend dev server before live verification; the log, not the browser, tells you which |

### F. Testing and verification discipline (the largest set of lessons)

| # | What happened | Rule |
|---|---|---|
| F1 | **A green suite is not evidence. Mutation is.** Mutation testing found tests passing against knowingly broken code in ten separate rounds, including three mutants that survived a 638-test frontend suite and one that restored the defect its own commit was named after | **R46.** For every guard and validator, break the implementation and confirm a test fails. Show `git diff --numstat` (a `str.replace` no-op prints green for an unmodified file). A kill is self-evidencing; a survival is not. Restore mutations in a `finally` |
| F2 | **Tests that pass for the wrong reason**: a Model Gateway cost-cap test with a missing price and an empty prompt made the cap a silent no-op, then asserted "all raise the same exception type" (true for the wrong exception); a fixture whose own request text satisfied the substring assertion; `"Development" in prompt` true because the roster names every agent; two wiring tests that patched a function that does not exist with `raising=False` | **R47.** Assert the **specific** type/value, assert on the delta the change adds, never `raising=False` on a patch target, and check the fixture does not contain the string under test |
| F3 | A report claimed a function was "covered elsewhere"; grep found **zero** references. A test-file comment said the access-control function was exercised in another file, which also stubbed it, so the most security-critical function had zero coverage. A per-file test count was reconstructed from memory | **R48.** Verify every "covered elsewhere" claim by grep. Paste real `pytest -v` output. Prose asserting a guarantee the code does not provide is the recurring defect of this whole platform (twelve instances in the orchestrator rebuild alone, the last with a confidentiality consequence): when you write such a comment, verify it on every path or narrow the wording |
| F4 | A subagent added an autouse fixture to `tests/routers/conftest.py` that bypassed RBAC for every test in the directory | **R49.** Stay within named files. Report `DONE_WITH_CONCERNS` rather than patching around a regression in unrelated infrastructure. File-scoped fixtures only |
| F5 | Running the full backend suite (1,934 tests) **wiped every role binding on the platform** because five test files run an unscoped `DELETE FROM role_bindings` and `.env` pointed all three connection strings at the live `sdlc_product`. It recurred on "every broad test run" | **R50.** Tests run against `sdlc_product_test` only (`backend/.env.test`). Never run the full suite against the dev database. Run specific test files. Verify the test DSN differs from the app DSN before running anything broadly |
| F6 | A backend process ran stale code for 16+ minutes after the fix commit; a live "verification" reproduced the old bug. Hit twice independently | **R51.** Before any live verification, confirm the process start time postdates the commit under test, or restart. Check `docker ps` too |
| F7 | Unit tests exercised handlers directly, bypassing the Next bridge; a real-repo test found that `clone_repo` rejects `file://`, `validate_command("rm -rf /")` returns nothing (it polices shell metacharacters only), and `work_dir` is overwritten by the tool. **All three were the plan's own planning-time assumptions** | **R52.** Drive the real compiled graph against a real local fixture (real git repo, real subprocess), scripting only the model's response. A plan's assumption about production behaviour is verified by reading the code, not repeated |
| F8 | A **negative control**: disabling `push_gate_enabled` made exactly the two gate-dependent tests fail for the right reason (a real push happened), and surfaced that a live HTTPS request reaches `dev.azure.com` once past a disabled gate | **R53.** Add a negative control to every gate test, and point test URLs at the reserved `.invalid` TLD so a regression fails locally, never at a real endpoint |
| F9 | Separate implementer and reviewer: independent review found nearly every significant defect; self-review found little. The final **whole-branch** review found a Critical and four Important issues no per-task reviewer could see because each depended on how two tasks interact | **R54.** One agent implements, a different agent reviews, and there is a mandatory whole-branch review on the most capable model before merge, with one bounded fix wave |
| F10 | A live e2e test did not clean up (`clear_session`, generated-docs directory) | **R55.** Every live test cleans up after itself or uses a temp directory |
| F11 | Live browser verification was unavailable (the Chrome extension could not reach the dev server; a file served to `curl` was a 404 in that browser) | **R56.** Never describe rendering as "visually confirmed" unless someone opened it. State which half of a check was wire-level only, and ask the user to do the visual pass |
| F12 | Planning documents contained first-draft claims that were wrong (G2 withdrawn, A1 withdrawn, the "no board tools" premise, "`resolve_chat_model` does not exist") | **R57.** Every "verified" claim in a plan is checked by reading the code and by running a command. A grep for a permission **string** cannot find enforcement that resolves it from a **map** |

### G. Environment traps (Windows, this repository)

| Trap | What to do |
|---|---|
| `pytest` from `backend/` fails at collection with `ModuleNotFoundError: No module named 'config'` | `cd backend && uv run python -m pytest …` (or `PYTHONPATH=.`); `uv run pytest` fails |
| Port 8001 had a phantom Hyper-V NAT listener (PID that does not exist) answering with a bare 500 | Backend is on **8004**; `frontend/.env.local` `FASTAPI_INTERNAL_URL` and `backend/.env` `AGENTIC_BASE_URL` follow it; a wrong port breaks login **and** every generated-file link. Real fix is `net stop winnat && net start winnat` as Administrator |
| Compose Postgres is on **5433**, not 5432 | Use `backend/.env`, not a repo-root `.env` |
| Orphaned background processes survive session boundaries | Start servers with tracked background runs only |
| Semgrep, Trivy, Gitleaks are not declared dependencies | `uv pip install semgrep==1.173.0` (not `uv add`); `winget install Gitleaks.Gitleaks` and `AquaSecurity.Trivy`; winget updates the persistent PATH but not running shells. Semgrep `--config auto` silently skips untracked or "test"/"fixtures"-named paths and returns `status ok, findings []` |
| Windows `rmtree` leaves read-only git objects | chmod-then-retry helper |
| A pnpm-style `node_modules` contaminated an npm install ("Cannot read properties of null (reading 'matches')") | One package manager; remove stray root `package-lock.json`/`node_modules` |
| Line-ending and `PATH` differences between Git Bash and PowerShell | Use the shell the command was written for; use forward slashes in Bash |

---

## 3. What Track 1/2 built that Track 3 should reuse (and the Track 3 docs under-mention)

| Mechanism | Where | How Track 3 uses it |
|---|---|---|
| **Tech stacks** (Agent Studio) | `shared/services/tech_stack*.py`, `shared/routers/tech_stacks.py`, `test_design_tech_stack.py`, spec `2026-09-22-agent-studio-tech-stacks-design.md` | A BU or project may have an approved stack (effective stack = project selection → BU default → none, always stating the source). **Migration Intent's recommendation and Target Architecture's per-layer choices must respect it** and record a departure as an ADR. The stack table is the source of truth; **versions are the model's to give** (commit `d5234d46`), and Track 3 must still refuse end-of-life versions |
| **Project documents** (upload, approve, `read_document`) | migrations 0052/0053/0056/0064, `shared/tools/document_tools.py`, `artifact_versions.readable_documents` | Modernization projects come with **legacy documentation, runbooks, interface specs, DB dictionaries**. Upload them project-level; Target Architecture and Strategy read them with `read_document` (metadata first, text on demand) and cite them. This is the answer to "not assessable statically" for many items |
| **Publication gate + `read_upstream` + evidence** | `shared/services/artifact_versions.py`, `artifact_consumption.py`, `projects.enforce_artifact_publication` | Track 3's "approved first, else newest draft" rule is the un-enforced behaviour. When enforced, no fallback. `artifact_consumptions` is the raw material for the Cutover Pack's "what did this build on" |
| **Consequential gate** | `shared/authz/consequential.py` | Board writes, target push, capture run, cutover steps |
| **Connector access lattice** | `shared/authz/connector_access.py`, `ScopedConnector` | `legacy` = read only; `target` = read/write on Migration Development and Cutover only. `read` and `write` are incomparable |
| **Governance requests + agent_access two-stage** | `shared/services/governance_requests.py` | Raising access to Track 3 agents; PA is stage one, the owner is stage two |
| **Notifications and bell** | `shared/services/notifications.py`, `notifications-bell.tsx` | Gate raised → owner notified; SLA escalation. Real, not a stub (audited live) |
| **Traces** | `help/langfuse-integration-plan.md`, `shared/observability` | Tag every turn with project, module and wave |
| **Model gateway** | `shared/services/model_call_wrapper.py`, `model_rate_limit.py`, `budget_guard.py` | The per-module token budget is a `budget_guard` consumer, not a new mechanism |
| **`modernization_common/`** | `graph.py`, `standalone.py`, `versions.py`, `files.py`, `legacy_code.py` | The Track 3 agent shell. New agents call `build_tool_agent_graph` and `serve_agent_socket`; do not fork them |

---

## 4. Corrections to the Track 3 documents themselves

| Document | Statement | Status |
|---|---|---|
| `track3-agent-build-plan.md` | "`TRACK_PORTFOLIOS["modernization"]` … has zero agents built, zero mounted routers" | **Stale.** Two agents are built and mounted; the roster is `["requirements_modernization", "discovery"]` |
| `track3-frontend-plan.md` §0 | Neither agent has a page; chat map has no Track 3 case | **Stale.** `requirements-modernization/page.tsx` and `discovery/page.tsx` exist; `agentWsPath` cases exist and are pinned. Its §1 naming correction stands |
| `track3-implementation-plan.md` §1 | `TRACK_PORTFOLIOS["modernization"] = []` | **Stale** (Phase 0 done, Phase 1 built) |
| `track3-phase1-requirements-discovery.md` | Names `Requirements (migration intent)` and `Discovery & Assessment` | Renamed to **Migration Intent** and **Dependency and Risk**; ids unchanged |
| `Track-3 Flow document.md` Agent 1/3 inputs | Omit tech stacks and project documents | Added (see the flow document's Part V) |
| `Development-Plan_track3.md` §7 | Six-place wiring checklist | **Incomplete.** Missing the BFF handler, the orchestrator2 dispatch/deliverables/output-dir entries, the three owner maps, the tests that pin them, `grant_app_role`, and the live-verification preconditions. See the plan's §24 |
| `Development-Plan_track3.md` §2 | "Two agents took three people about three days" | True for **build and demo**. Track 1's Development agent then needed **15 further fixes** during live verification, and the Orchestrator needed five phases. The plan's 15 days is a build-to-demo figure; see the plan's §24 for the hardening it assumes |
| `portfolio-1-agent-status.md` | `resolve_chat_model` and `notification_targets` "do not exist" | **Both now exist** (`shared/services/model_resolver.py`, `notification_targets.py`). Track 3 must not repeat the mistake of trusting a dated status note |
| Track 3 flow "Sign-off reuses the existing artifact submit/approve flow" | Ambiguous | Sign-off = **publish a frozen version** through `POST /projects/{id}/stages/{stage}/versions/{v}/publish`, gated on `_PHASE_PERMISSION[stage]`, self-publication refused at the database |

---

## 5. Which lessons bite which Track 3 agent hardest

| Agent | Highest-risk lessons | Concrete first checks |
|---|---|---|
| **3 Target Architecture** | A4 (hand-off from Agents 1–2 returns nothing under RLS), D14 (truncated inputs), tech stacks, project documents, D15 (stale/EOL versions) | Real-Postgres hand-off test with a removal control; validator refuses EOL versions using the assessment's table; stack recorded as departure ADR |
| **4 Migration Strategy** | A2/A3 (board connector stage and kind), B3 (board writes gated in code), D15 (dates never invented) | Per-stage grant test; `authorize_consequential` on `create_wave_work_items`; a user's date is never moved |
| **5a Baseline** | **C2** (recordings broadcast to strangers), D9-adjacent (no raw records in prompts), A7 (credentials for the runtime DB), F7 (drive a real sandbox, not a mock) | `broadcast_to_session` only; a prompt/trace inspection test showing masked summaries; egress-blocked probe |
| **6 Migration Development** | A7 (project-scoped credentials at **every** call site, two already found), B3 (push needs owner role **and** turn consent), D6/D7/D8 (cancel, in-flight, `system_injected`), D9 (diff card, not Monaco), D1 (temperature), Issue 3 (the Development agent's pull-repos UI is Azure-only by construction; the **target** repo may be GitHub) | Copy the Development agent's fixes, do not rediscover them; provider-neutral repo picker from day one |
| **7 Migration Review, 8 Security** | F2 (vacuous assertions), D15 (sentinel for "not scanned"), G (scanners not installed; Semgrep untracked skip), A1 (repo-reading agents need the checkout under the Orchestrator) | Planted defects with negative controls; workspace binding proven on the Orchestrator path |
| **5b Verify** | F2 (a comparison that passes for the wrong reason is the entire risk), D15 (`not run` is never `passed`) | Planted rounding change caught; normalization editable from nowhere in this agent |
| **9 Cutover** | B3/B4 (Consequential steps cannot run in the background), B5 (co-sign, no self-approval), D15 (readiness computed by a tool, never overridden by the model) | Prompt-injection test that the model cannot turn a red gate green |
| **10 Cutover Pack** | D15 (Documentation's RTM lesson is the whole design), C3 (document storage), R20 | Planted unmapped file appears as a visible gap |
| **All** | A1, A5, A6, R42 (tile last), F6 (fresh server), F5 (test DB) | The checklist in the plan's §24 |

---

## 6. Open items that Track 1/2 left, and that Track 3 inherits

1. **Untracked cross-agent debt** (from the orchestrator handoff): the BYOK "no env fallback" guarantee is one layer deep; context truncation needs a product decision; `assert_all_routes_protected` skips WebSocket routes, so socket access control is guarded only by its own tests.
2. **A standalone chat run does not raise a gate**, and an autonomous worker run cannot perform a Consequential write because it has no way to ask. Track 3's Cutover needs an answer before Day 11 of the plan.
3. **MCP tools have no Consequential-by-default choke point** (every board write funnels through one connector seam; MCP does not).
4. **The Development agent's pull-repos dialog is Azure DevOps only**; Track 3 needs a provider-neutral target picker.
5. **`copilot_api.py` sockets and per-agent output attribution**: exact attribution needs each agent writing to its own sub-directory. Track 3 agents should do this from the start.
6. **RLS inertness** may still exist on any machine whose `.env` points at `postgres`.


---

## 7. The first two Track 3 agents pre-date Track 1's newer platform features

Migration Intent and Dependency and Risk were built on 2026-09-10 to 2026-09-12. The document
system, the approval system and several agent tools that Track 1 gained afterwards were never
retrofitted. What follows was checked in the code on 2026-09-28: a `grep` of both agents and
`modernization_common/` for the newer tools, and a comparison of the two pages with the Track 1
pages.

### 7.1 What the two agents already do right

| Feature | State |
|---|---|
| Generated Word/PDF files are registered as **draft** artifacts under the agent's stage (`register_generated_file` → `artifact_store.store_artifact`, tenant-prefixed path, bytes under `_pending`, `submit`/`approve` promote them) | Uses the platform's file system through `announce_generated_file` |
| Every recorded brief/assessment is a frozen `artifact_versions` row, and sign-off is `publish` (no self-publication) | Yes, through `freeze_version` and the page's `VersionView` |
| Board write is Consequential and gated in code | Yes (`authorize_consequential` in `create_migration_work_items`) |
| Enforced publication is respected when building context | Yes (`standalone.py` reads `enforcement_enabled`) |
| Track scoping, per-message access check, terminal `activity_update`, project-scoped BYOK | Yes |

### 7.2 What they lack (the retrofit list)

| # | Gap | What Track 1 has | Effect today | Retrofit |
|---|---|---|---|---|
| 1 | **No document-reading tools.** Neither agent registers `make_document_tools` (`list_project_documents`, `read_document`) | Design, Security, Code Review, Documentation, PM and others | A modernization project's most valuable inputs, the legacy specifications, runbooks, interface and database documents uploaded by the team, are invisible to both agents | Register the tools with `consumer_stage` = the agent's id; the prompt names them only when `has_document_tools(agent_id)` is true (a prompt naming an unbound tool sends the model after a call that fails) |
| 2 | **No raise-for-approval tool.** Neither registers `make_approval_tools(stage)` | Security, Testing, PM and others ("Okay, can you send it for approval?" was answered "I cannot" until this tool existed) | The agent tells the user a person must approve, but cannot put its own document forward | Register it; the prompt says "raise it for approval; never approve" |
| 3 | **The pages do not use the Track 1 document and version panels.** `Track3AgentPage` uses its own `VersionHistory`/`VersionView` and the older `GeneratedDocuments`; it does not use `DocumentList`, `StageVersionPanel`, `TechStackChip` or `RunEvidence` | Design, Requirements, Security and others | No hand upload, no scope badge, no "who approved, when", no submit/approve/reject of generated files from the page, no draft/published/superseded/rejected states, no compare, no "what consumed this version" | Adopt the shared panels (see the Development Plan §25 for the layout) |
| 4 | **No tech-stack awareness** | Design, Development, Deployment read the effective stack and say where it came from | The recommendation ignores an approved stack; a project with a BU default gets a free choice | Migration Intent reads it (Step 1) |
| 5 | **Upstream reads not proven through `read_upstream`** | Consumers of published versions record each read | Dependency and Risk reads the brief through context building; whether every read is recorded in `artifact_consumptions` needs checking | Check both paths; add the missing recording |
| 6 | **The legacy checkout lives in its own store** (`files/legacy-code/<project>/checkout`) | Repo-reading Track 1 agents get their workspace from `s.work_dir`, and under the Orchestrator from `orchestrator2/workspace.py` (the fifth wrapper-gap instance) | Every new repo-reading Track 3 agent (Architecture, Review, Security, Verify) must be handed this checkout under **both** surfaces | `test_legacy_code_orchestrator_scope.py` exists; extend it per agent |
| 7 | **The fourth owner map.** `shared/services/orchestrator/gate_routing.py::GATE_OWNER` is another owner table, on Track 1 stages, with `GATE_OWNER.get(stage, "product_manager")`, a swallowing default of the same kind that produced the `code_review` defect | Track 1 stages only | A Track 3 stage missing from it answers "product_manager" | Add every Track 3 stage with the same role names as `_OWNER_OF` (research §12.2 already asks for this); consider deleting the default |
| 8 | **`artifact_versions.assert_known_stage` and document upload validate against `STAGE_ORDER`**, which derives from `AGENT_REGISTRY` | Automatic for a registered agent | A new agent that is not in the registry cannot publish, upload documents or appear in the consumption matrix | Register the agent before building its page; test publish, upload and matrix inclusion |
| 9 | **The two agents' prompts pre-date the "save, don't offer", document-quality and refusal rules** (D18a–D18d, D18i) | Applied to the Track 1 agents in the orchestrator live-testing round | The Orchestrator's deliverable filter may or may not classify their output correctly | Run `live_deliverables_check` style checks on both |

None of these is a defect in what was built; they are features that did not exist yet. The
consequence is that a Track 3 project cannot yet use the platform's document and approval system
the way a Track 1 project can, and Migration Intent, whose whole value depends on the customer's
existing documents, is affected most.

---

## 8. The frontend is built in parallel, and every agent page is its own UI

### 8.1 Why the frontend cannot trail the backend

You test Track 3 by using it. A backend agent with no page cannot be tested by a person, and a
page built last is a page built against guesses. Track 1 showed both failures: Discovery's stub
page had a broken chat because `agentWsPath` had no case for it, and nothing had rendered a
Track 3 artifact until the shell was built from real payload shapes. So **each step delivers a
backend lane and a frontend lane together**, and the frontend lane starts as soon as the step's
hand-over schema and fixture exist (Step 0), not when the agent works.

### 8.2 Each agent page is its own UI

The Track 1 pattern is the rule: **the chat is the same everywhere (`AgentChatDrawer` +
`useAgentChat`); the surface beside it is built around what that agent's work product looks
like.** Track 3 outputs are not documents. They are graphs, contracts, waves, recordings, diffs,
verdict grids and runbooks. A generic `StageWorkbench` list-and-approve shell is acceptable only
for Migration Review and the Cutover Pack, and even those add a bespoke panel (checklists; the
traceability table). The eight new pages, plus the Programme page, are specified in the
Development Plan §25; the frame they share is:

| Zone | Content | Source |
|---|---|---|
| Header | Agent name, track badge, model picker, `TechStackChip` (Architecture, Strategy, Migration Development, Cutover), module/wave selector for per-module agents, the button that opens the chat | `ModelSelector`, `TechStackChip` |
| Status strip | Stale badge, "waiting on <role>" with who can act, read-only-stage explanation, self-approval explanation, fallback-approval badge | new shared component |
| Left rail | Versions (`StageVersionPanel`: draft / published / superseded / rejected, compare, restore), Documents (`DocumentList`: upload, submit, approve, scope badge, who and when), Evidence (`RunEvidence`) | Track 1 components |
| Centre | **The agent's own surface** | new per page |
| Right | The chat drawer; diffs as markdown `diff` blocks, never Monaco | `AgentChatDrawer` |

### 8.3 Rules that apply to every page (each was a Track 1 bug)

1. The page is reachable by its URL as soon as it exists, and its access gate is render-tested (R43).
2. The BFF handler for each backend route ships in the same change (R5).
3. The agent id joins the Zod protocol union and the emitter together (R41).
4. Two empty states are designed, not defaulted: a stage at the `read` level ("this stage can read
   the board but not write to it; ask an admin") and "no approved upstream yet" (name the stage and
   its owner) (R44).
5. A person who produced a version sees **why** they cannot approve it (R14).
6. Numbers a tool did not return are never drawn: an unmeasured value renders as "not measured"
   (R39).
7. Nothing customer-derived is fetched into the browser unmasked; the Baseline and Verify pages show
   masked examples and counts only.
8. A heavy viewer is lazy-mounted and works under the app's CSP; Monaco is not used in the chat (R33).
   Check which viewer the Development page's `CodeViewer` actually uses before reusing it for the
   Migration Development's side-by-side view, and confirm it renders in a real browser.

### 8.4 How you will test each page

Every step delivers, next to its code, a **click-through script** for you: numbered steps, the
persona to sign in as (`DEV_LOGINS.txt`), the expected result at each step, and which parts were
verified in a browser and which only over the wire. To make that possible before an agent exists:

- Step 0 adds a **seed script** (`backend/scripts/seed_track3_fixture.py`) that creates a
  demonstration Track 3 project and writes the ClaimTrack fixture instances through the real
  services (`snapshot_stage_payload`, the ledger service). It uses real rows, not mocks, so RLS,
  publication and consumption are exercised too. It is idempotent and removes only what it created.
- A page can be opened by URL while its **tile is still locked**. Two flags exist and are
  separate: the agent joins `TRACK_PORTFOLIOS["modernization"]` when it runs end to end standalone
  (so the page and chat work and the Orchestrator can offer it), and the tile joins
  `BUILT_AGENTS_BY_TRACK` **last**, after you have clicked through it (R42).
- Personas: a BA for Agents 1, 2 and 10; an Architect for 3, 4, 6-accept and 7; QA for 5; a Security
  Engineer for 8; DevOps for 9; a Developer for 6; a Project Admin for the Programme page and
  fallback approval. The seeded personas have decayed before (the approval audit found 9 of 14
  missing and two undocumented accounts both holding a single-seat role): check them first.

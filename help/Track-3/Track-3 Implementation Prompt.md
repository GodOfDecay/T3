# Track 3 Implementation Prompt

**How to use this file.** Give the whole file to Claude Code, started in
`C:\Users\Aksha\OneDrive\Desktop\PWC\SDLC` on a fresh branch off `akshat_main`. It is written to
be self-contained: it tells the assistant what to read, what already exists, the rules it may not
break, the order to build in, how to prove each step, and when to stop and ask you. Everything
between the two horizontal rules below is the prompt.

---

# YOUR TASK

You are implementing **Track 3 (Code Modernization)** of the SDLC Platform in this repository:
the **eight unbuilt agents**, their shared backbone, the legacy sandbox, the frontend pages, the
tests, and the end-to-end acceptance run. Two agents (Migration Intent, Dependency and Risk) are
already built and live-verified; you build the other eight on top of them, in the order below,
without breaking Track 1/2.

**The outcome, in one sentence:** a Track 3 project can take the ClaimTrack legacy system through
all ten agents, module by module, producing a migrated target repository with recorded proof that
behaviour was preserved, gated by the right people, with no agent able to exceed its authority.

**The standard, in one sentence:** *a step is not done because its tests pass; it is done when a
different reviewer has watched it run against real data, standalone and through the
Orchestrator, and the guards have been shown to fail when broken.* This platform's Track 1/2
history is a record of green suites certifying broken behaviour. Do not repeat it.

## 0. Ground rules for how you work

1. **Read before you write.** Do the reading in section 1 in order. Do not start coding until you
   have written the plan for step 0 (section 6) and I have seen it.
2. **Code beats documents.** Every document here was true on the day it was written. When a
   document and the repository disagree, trust the repository, say so, and fix the document.
   Verify every claim about other code by reading it and by running a command. A grep for a
   permission *string* cannot find enforcement that resolves it from a *map*.
3. **Never run the full backend suite against the dev database.** It once emptied every role
   binding on the platform. Tests run against `sdlc_product_test` via `backend/.env.test`.
   Run specific test files. Check that the test DSN differs from the app DSN first.
4. **Do not commit, push, open a PR or delete anything unless I ask.** Checkpoints below say
   "checkpoint" and mean: stop, report, wait. Ask before every `git push` and before opening or
   updating a PR, even if I approved one earlier. When I do ask for a commit, end the message with
   `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`; when I ask for a PR, add
   `UjjwalTyagi5` as reviewer and end the description with
   `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
5. **Say "Business Unit" in prose, never "workspace".** Code identifiers keep `workspace`.
6. **Write decisions down as you make them**, with reasoning and the cost if wrong, in
   `help/Track-3/build-log.md` (create it). One entry per decision, per finding, per fix round.
7. **Ask me only when the answer changes what you do next** and you cannot resolve it from the code,
   the documents or the defaults in section 5. Batch questions. Everything in section 9 is
   a mandatory stop.
8. **The frontend is built in parallel, one bespoke UI per agent.** Every step delivers a backend lane
   **and** a frontend lane (section 6A). I test Track 3 by using it, so a backend agent with no page is
   not finished, and a page is finished only when I have a click-through script for it. Every agent
   page is its **own** UI built around what that agent produces; only the chat, the version rail, the
   document rail and the model picker are shared.
9. **Report faithfully.** If a test fails, show the output. If a step was skipped, say so. If a
   check was wire-level only (no browser), say that. Never say "visually confirmed" unless someone
   opened it. Never claim "covered elsewhere" without a grep that proves it. Paste real `pytest -v`
   output rather than a count from memory.

## 1. Reading order (do all of it, take notes)

Read these in order. The first three are short and non-negotiable.

| # | File | Why |
|---|---|---|
| 1 | `help/Track-3/Track-3 Lessons from Track 1-2.md` | **The rules R1–R57 with their evidence.** Every rule below cites one. This is the most important file |
| 2 | `help/Track-3/Development-Plan_track3.md` (especially §5–§18, and **§24**) | The step-by-step plan, the guarding tests, the checklist (§7) and the Day 0 preconditions (§24.1) |
| 3 | `help/Track-3/Track-3 Flow document.md` | What every agent does: entry conditions, inputs, actions, outputs, pass/fail, gates, hand-over, "never does". Part V is the platform mechanisms |
| 4 | `help/Track-3/track3-research.md` §5 (backbone), §6.3–§6.10 (the system prompts and tools), §7 (Orchestrator, pages), §12 (fallback approval, restore) | The design and the drafted prompts. Tool names in §6.3+ are proposals |
| 5 | `help/Track-3/track3-demo-claimtrack.md` | The fixture (ClaimTrack) and the two built agents' expected output |
| 6 | `help/Track-3/track3-phase1-requirements-discovery.md`, `docs/superpowers/plans/2026-09-10-track3-phase1-agents.md` | How the first two agents were built, with the interfaces |
| 7 | `desicions and issues.txt` (repo root, 1,109 lines) | 15 issues found by *running* the Development agent. Read all of it |
| 8 | `help/portfolio-1-agent-status.md`, `help/requirements-design-e2e-plan.md` | What "real code, no proof" looked like, and three first-draft claims withdrawn after reading the code |
| 9 | `help/artifact-approval-and-consumption-plan.md`, `help/artifact-scoping-and-document-consumption-plan.md` | Ownership single-sourcing, frozen versions, publication, documents |
| 10 | `docs/superpowers/specs/2026-08-30-approval-system-full-audit-findings.md` | RLS silently inert; stale dev server |
| 11 | `ORCHESTRATOR_HANDOFF.md` and `orchestrator_instruction.md` §11–§18 | How `orchestrator2` works, the wrapper-gap pattern, the traps (§6 of the handoff), the working method |
| 12 | `help/multi-track-agent-access-design.md` (Portfolio 2, Parts 1.5, 2.2, 2.3, 4.3, 5) | The access model Track 3 sits on |
| 13 | `docs/local-setup.md`, `DEV_LOGINS.txt` | How to start the stack; the seeded personas |
| 14 | `help/Track-3/track3-research.md` **§6 (all ten agent specs and their drafted system prompts, about 1,100 lines), §9 (the ClaimTrack hand-over demo), §12 (fallback approval, Project Admin reach, restore)** | The behaviour, tools, prompts and per-agent hand-off contracts you are implementing. Do not skim it |
| 15 | `help/Track-3/track3-frontend-plan.md` §4 and `Development-Plan_track3.md` **§25 (per-page UI specs) and §26 (retrofit of agents 1–2)** | What each page contains, and what the two built agents are missing |
| 16 | The Track 1 pages `app/(app)/projects/[id]/{design,security,development,requirements}/page.tsx` and `components/app/{stage-version-panel,document-list,run-evidence,tech-stack-chip,stage-workbench,agent-chat-drawer}.tsx` | The pattern each Track 3 page follows (shared chat and rails, bespoke centre) |

Then read the **code** that Track 3 extends. At minimum:

- `backend/agents_orchestrator/modernization_common/` (`graph.py`, `standalone.py`, `versions.py`,
  `files.py`, `legacy_code.py`) — the Track 3 agent shell. **Reuse it; do not fork it.**
- `backend/agents_orchestrator/discovery_agent/` and `requirements_modernization_agent/` — the
  two built agents, your templates.
- `backend/config/agent_registry.py`, `backend/agents_orchestrator/orchestrator2/{registry,router,
  deliverables,dispatch,context,ws}.py`, `backend/shared/authz/{consequential,agent_access,
  connector_access,permissions}.py`, `backend/shared/governance/routing.py`,
  `backend/shared/services/{artifact_versions,artifact_store,artifact_consumption,
  model_resolver,model_call_wrapper,tech_stack}.py`, `backend/shared/routers/{modernization,
  artifact_versions}.py`.
- For the Migration Development agent: `backend/agents_orchestrator/development_agent/` (all of it,
  especially `tools/git_tools.py`, `path_guard`, `sandbox_policy`, `development_agent_api.py`) and its
  tests in `backend/tests/development/`. **The Track 1 Development agent already contains the
  fixes for most of the bugs in the issues log (credentials, in-flight guard, message repair, gpt-5
  temperature, timeout, retries, diff events); copy them, do not rediscover them.**
- For Security: `backend/agents_orchestrator/security_agent/`; for Review:
  `code_review_agent/`; for Cutover: `deployment_agent/` and `shared/services/deployment_gate.py`;
  for the Cutover Pack: `documentation_agent/`; for Strategy: `pm_agent/`.
- Frontend: `frontend/lib/{agents,tracks,roles}.ts`, `lib/schemas/enums.ts`,
  `lib/orchestrator/{protocol,agents,types}.ts`, `app/api/chat/route.ts`,
  `app/(app)/projects/[id]/{discovery,requirements-modernization,development}/page.tsx`,
  `components/modernization/`, `__tests__/bff/every-api-path-has-a-proxy.test.ts`.

**After reading, write `help/Track-3/build-log.md`'s first entry**: a one-page summary of (a) what
already exists, (b) any place the documents disagree with the code, (c) your plan for step 0.
Stop and show me before writing code.

## 2. Ground truth: what exists today (verify, do not assume)

Verified on `akshat_main` on 2026-09-28. Re-verify before relying on any line.

- **Built and live-verified:** Migration Intent (`requirements_modernization`, ba-owned) and
  Dependency and Risk (`discovery`, ba-owned). Both have standalone WS routers, are offered by the
  Orchestrator, freeze every record as an `artifact_versions` row, and are track-scoped
  (`assert_agent_access_for_chat_on_track`). Frontend pages exist for both.
- **The two built agents pre-date Track 1's document system, approval system and several tools.**
  They already register generated files as draft artifacts (`register_generated_file` →
  `store_artifact`), freeze versions, and gate the board write in code. They do **not** register
  `make_document_tools` (`list_project_documents`, `read_document`) or `make_approval_tools` (raise a
  document for approval); they do not read the effective tech stack; their pages do not use
  `DocumentList`, `StageVersionPanel`, `RunEvidence` or `TechStackChip`; and `GATE_OWNER` in
  `shared/services/orchestrator/gate_routing.py` has no Track 3 entries and a swallowing
  `"product_manager"` default. `Track-3 Lessons from Track 1-2.md` §7 lists all nine gaps. Fixing
  them is **Step 1**, and it comes before Target Architecture.
- **Not built (yours):** Target Architecture (`design_modernization`), Migration Strategy
  (`strategy`), Equivalence Testing (`testing_modernization`, two modes), Migration Development
  (`development_modernization`), Migration Review (`code_review_modernization`), Security
  (`security_modernization`), Cutover (`deployment_modernization`), Cutover Pack
  (`documentation_modernization`). Stub pages exist for some (`strategy`, `migration-mapping`,
  `validation`) and must be replaced or removed, not left as decoys.
- **Migration head is `0065_tech_stacks`.** Run `alembic heads` before you number anything. Two
  branches once both took `0057` and needed merge `0059`.
- **Track 1/2 platform you must reuse:** frozen versions and the publication gate
  (`artifact_versions`, `read_upstream`, `artifact_consumptions`, `projects.enforce_artifact_publication`);
  project documents (`read_document`); Agent Studio tech stacks; the Consequential gate
  (`authorize_consequential`); the connector lattice (`ScopedConnector`); governance requests;
  notifications; the model gateway (`guarded_completion`, `budget_guard`); traces.
- **Not built anywhere:** the Module Migration Ledger (`modernization_modules`), the artifact
  envelope and staleness, stable-id minting, the `target` connector reference, version
  restore/compare, universal Project Admin fallback with `approved_as`, the Programme page, the
  legacy sandbox, baseline storage, and every Track 3 agent above.
- **Known environment facts:** backend port **8004** (not 8001), Postgres **5433**, run pytest as
  `cd backend && uv run python -m pytest <files>`, the frontend is `cd frontend && npm run dev`.

## 3. The non-negotiable rules

These are the rules from `Track-3 Lessons from Track 1-2.md`, condensed. Each is enforced by a
test or a review question. If you cannot satisfy one, stop and tell me.

### Identity, access and approval
- **R10** Every new agent is added to **all the owner maps** in one change
  (`frontend/lib/roles.ts`, `backend/shared/governance/routing.py::AGENT_OWNER_ROLE`,
  `backend/shared/authz/permissions.py::_PHASE_PERMISSION`, and
  `backend/shared/services/orchestrator/gate_routing.py::GATE_OWNER`), keyed on the **backend stage name**,
  with UI names as aliases, and **no default that swallows a missing key**. Prove the named owner
  *can* pass the gate and that an active user holds the role. Keep
  `test_agent_ownership_is_single_sourced.py` and `test_agent_reach_matches_frontend.py` green.
- **R11** Chat and REST handlers call `assert_agent_access_for_chat_on_track` on **every**
  message. Identity comes from `request.state` or the redeemed ticket, never from a client-sent
  `user_id` / `tenant_id`. `require_agent_access` is a router-level floor **only where the route
  has a project path parameter**; on a project-less route it silently does nothing.
- **R12** Every Consequential tool calls `authorize_consequential(stage, action=…)` **in code**.
  It checks the person holds the owning role **and** approved **this turn**. A prompt saying
  "always confirm" is not a control.
- **R13** A queued/background run has no signed-in person. Consequential actions are interactive
  only, or raise a gate and wait. **Never** add a blanket exemption for background runs.
- **R14** Nobody approves their own version. Reject-by-the-initiator stays allowed. The UI says
  *why* a control is refused, in words.
- **R15–R17** Every artifact is a frozen `artifact_versions` row. Consumers read with
  `read_upstream` (published only, every read recorded). **No fallback to a draft** when
  publication is enforced. A consumer pinned to N is *notified* when N+1 publishes, never switched.
  Documents ride the version's `covers`; do not build a second approval system.

### Wiring
- **R1** `orchestrator2` loads the agent's **graph**, not its `*_agent_api.py` wrapper. For each
  agent, list everything the wrapper establishes (identity, run, connector, consent, model,
  workspace/checkout) and prove the Orchestrator path establishes the same. Test it explicitly.
- **R2, R3** Obtain every connector with **`agent_id`** and `project_id`; resolve the connector
  *kind* from the stage wiring, never a default. A connector with no stage permits nothing.
- **R4** Every read of another stage's artifact uses a **tenant-scoped** session or
  `read_upstream`. Each hand-off gets a **real-Postgres test with a control that fails if the copy
  is removed**.
- **R5** Every backend route the browser calls gets its **BFF handler** in the same change;
  multipart gets its own handler.
- **R6** One live browser-path check per agent (page → BFF → WS). Add the `agentWsPath` case in
  `app/api/chat/route.ts` and pin it in `chat-agent-map.test.ts`.
- **R7** Credentials are looked up with **`project_id` and `owner_id`** at **every** call site.
  When you fix a lookup, grep for every other caller in the same change. (This exact bug shipped
  twice in one week.)
- **R8, R9** Add the `_run_stage_output_dir` mapping, the `runs.<artifact>` column **and its ORM
  attribute and every reader**, and use `AGENT_REGISTRY[id].output_artifact` as the **only**
  source of the column name. A test asserts the mapper declares what the loader reads.

### Data and tenancy
- **R18** The app runs as `sdlc_app` (`NOSUPERUSER NOBYPASSRLS`); migrations as `postgres`.
  Verify `rolbypassrls = false` before any live verification. Every read through
  `get_db_session_superuser()` needs an explicit tenant predicate. New tables are FORCE RLS on
  **`app.current_tenant_id`** (not `app.tenant_id`, which matches nothing).
- **R19** Anything carrying customer content (code, diffs, baselines, recordings, findings) is
  sent with **`broadcast_to_session`**, never `broadcast` (whose fallback reaches every open socket
  on the process). Add a marked-payload test asserting nobody else receives it.
- **R20** Blob paths are composed **by code** from verified ids
  (`{tenant}/{bu}/{project}/{agent}/{run}/{type}/{filename}`); the model supplies only a
  sanitised leaf name. Use `artifact_store.store_artifact`. Serve by SAS URL at read time. Degrade
  with no blob configured; do not crash.
- **R21–R24** Migrations: nullable → backfill → tighten in one file; round-trip up/down/up on a
  scratch DB; check `alembic heads` before numbering and before merging; then run
  `scripts.grant_app_role`. Services never commit (the request owns the transaction).

### Model and agent behaviour
- **R25–R28** Build the model through the shared builder: no `temperature` for the gpt-5 family
  (never litellm's global `drop_params`), `max_retries=0` (only `guarded_completion` retries), a
  90 s ceiling with streaming, project-scoped BYOK via `resolve_model_for_run` +
  `set_resolved_model`, and **no `ANTHROPIC_API_KEY` fallback**.
- **R29** One finalize tool per agent. No tool asks the model for an id it was never given.
  `test_agent_tool_names_are_unique.py` stays green.
- **R30–R32** `sanitize_tool_call_pairing` every turn (delete the `tool_calls` key; do not set it
  to `[]`). Per-session in-flight guard; turns as tracked cancellable tasks; **every** path ends
  `stream_end` then `activity_update{type:"complete"}`. Set "delivered" flags only after the work
  succeeds.
- **R33** Show the Migration Development agent's changes as a diff card rendered as a markdown ```` ```diff ```` block.
  **Not Monaco** (CDN + CSP hang).
- **R34, R35** A deliverable is a document: ≥2 headings, ≥400 characters, not a first-person
  refusal, not an announcement of a file elsewhere. Prompts say "save, don't offer". Refusal
  detection is first-person and anchored to the opening.
- **R36, R37** Route with continuity; an explicit "run the X agent" wins outright. Hand the next
  agent the run's conversation as well as its documents, budgeted per agent, attributed.
- **R38** Large artifacts travel as **summaries plus stable ids** (M-xx, CT-xx, EC-xx, BL-xx);
  detail is fetched by tool; truncation is always marked.
- **R39** Never render "not measured" as zero, "not run" as "passed", or "not proven" as a match.
  Use an explicit sentinel and say so in the prompt and the payload.
- **R40** Scale ceremony to the size of the change; keep every ⛔ STOP gate.

### Frontend
- **R41** Add each agent id to the Zod protocol union **and** the emitter together (frames that fail
  `safeParse` are dropped silently). **R42** Two flags, in this order: the agent joins
  `TRACK_PORTFOLIOS["modernization"]` once it runs end to end **standalone** (its page and chat then
  work by URL, and the Orchestrator can offer it); it joins `BUILT_AGENTS_BY_TRACK` (the tile) **last**,
  after I have clicked through the page. **R43** Render-test each page's access gate. **R44** Design and test the
  **read-only stage** empty state. **R45** Restart the Next dev server before live verification.

### Every agent page (the frontend rules)
- Each page is its **own UI** around the agent's work product (section 6A); the chat drawer, the
  `StageVersionPanel`, the `DocumentList` (upload, submit, approve, scope badge, who and when), the
  `RunEvidence`, the `ModelSelector` and the `TechStackChip` are shared and go on **every** page.
- Every page is built against the **seeded ClaimTrack project** (Step 0's seed script) before its agent
  works, so I can click through it early. It shows every state in Plan §25.1's "Data and states"
  column, including **"not measured"**, **"not run"**, **read-only stage**, **no approved upstream**,
  **stale**, **you produced this so someone else must approve**, and a **fallback approval** badge.
- Nothing customer-derived reaches the browser unmasked. A heavy viewer is lazy-mounted and must render
  under the app's CSP in a real browser (Monaco did not). Diffs are markdown `diff` blocks.
- Phone width, a keyboard path to the primary action, and a render test of the access gate.
- Each step ends with a **click-through script for me**: persona, numbered steps, expected results,
  and which parts were verified in a browser versus over the wire.

### Testing and verification
- **R46** For **every** guard and validator, mutate the implementation, show a test fail, show
  `git diff --numstat`, restore in a `finally`. A survival is not a result until you show the diff.
- **R47** Assert the specific type/value, assert the delta a change adds, never use
  `raising=False` on a patch target, and check the fixture does not contain the string under test.
- **R48** Verify every "covered elsewhere" claim by grep. Paste real `pytest -v` output.
- **R49** Stay within the files a task names. Report `DONE_WITH_CONCERNS` instead of patching
  around a regression in unrelated infrastructure. File-scoped fixtures only; never an autouse
  bypass of RBAC.
- **R50** Tests run against `sdlc_product_test` only. **R51** Before any live verification, confirm
  the process start time postdates the commit under test (or restart), and `docker ps` is healthy.
- **R52** Drive the real compiled graph against a real local fixture (a real git repo, a real
  subprocess), scripting only the model's response. A plan's assumption about production behaviour
  is verified by reading the code.
- **R53** Add a **negative control** to every gate test, and use the reserved `.invalid` TLD in test
  URLs so a regression fails locally rather than reaching a real endpoint.
- **R54** One agent implements, a **different** agent reviews, and a mandatory **whole-branch review
  on the most capable model** runs before merge with one bounded fix wave. Per-task reviewers cannot
  see cross-task interactions.
- **R55, R56, R57** Live tests clean up after themselves; never claim visual confirmation you do not
  have; re-check every claim you copy from another document.

## 4. How to run each step (the loop)

For **each** step in section 6, in order:

1. **Plan.** Write `docs/superpowers/plans/2026-MM-DD-track3-<step>.md` in the format of
   `2026-09-10-track3-phase1-agents.md`: file structure, interfaces produced and consumed,
   numbered tasks with failing tests first. Show me the plan for step 0 and for any step that
   changes shared code; otherwise proceed.
2. **Contract first.** Build against the ClaimTrack **fixture instance** of the upstream
   hand-over schema (Step 0 creates them), so you never wait for an upstream agent.
3. **Failing test → implementation → passing test.** One task at a time.
4. **Implement with one agent, review with another.** If you can spawn subagents, do; give each a
   self-contained brief (files, interfaces, the R-rules that apply, "stay within these files", and
   what to report). The reviewer is told to **try to break it**, not to approve it.
5. **Mutate.** Apply R46 to every guard the step added. Record the mutants and the kills in the log.
6. **Wire both paths and build the page.** Standalone (`serve_agent_socket`) and Orchestrator
   (`registry.py`, `router.py`, `deliverables.py`, output dir); prove R1. The **frontend lane** starts
   as soon as the step's hand-over schema and seed fixture exist and runs alongside the backend lane
   (section 6A); the page is finished, and render-tested, **before** live verification.
7. **Live-verify** on the dev stack against ClaimTrack (and eShopModernizing where stated), after
   the Day 0 checks (R18, R50, R51). Record: commit, process start time, persona used, what was
   asserted at wire level versus in a browser.
8. **Whole-step review** by a different agent on the strongest model. One bounded fix wave.
9. **Checkpoint.** Update `build-log.md` and the step's handoff note, list what is still open, and
   **stop for me**. Do not start the next step until I say so, unless I have told you to continue.

Per-step **definition of done** (all must hold):
- the step's **guarding test** (section 6) passes **and is mutation-proven**;
- it runs on ClaimTrack standalone **and** through the Orchestrator;
- its hand-off reads real upstream data (R4 test with a removal control);
- every Consequential tool is refused without the owning role, without turn consent, and from a
  queued run (three tests, each with a negative control);
- the three owner maps and their pin tests are green; the BFF proxy test is green;
- Track 1's existing tests for the shared files you touched are green (run the specific files);
- the agent's page exists as its own UI, loads from the seeded project with no agent running, shows
  every state listed for it in Plan §25.1, and has passed the frontend rules above;
- I have a **click-through script** for the page, and the tile is still locked until I have used it;
- a different agent reviewed it; the log records what was found.

## 5. Decisions already taken (defaults; tell me if you disagree)

From `Development-Plan_track3.md` §8.1 — adopt these unless I say otherwise:

1. Display names and the `_modernization` id suffix: **adopt**.
2. Baseline is a **mode** of Equivalence Testing (one agent, one harness).
3. Ledger is a **table** (`modernization_modules`), append-only `history`, DB-level check on
   allowed transitions, per-agent transition permissions.
4. Legacy sandbox: the existing Docker runner (`testing_agent/tools/sandbox/docker_runner.py`)
   extended with isolation (no egress except a per-run DB container, images by digest, ephemeral).
5. Cutover is **request-only**: it files approval requests; it executes nothing in production.
6. Per-module token budget shown in the UI (a `budget_guard` consumer, not a new mechanism).
7. Project Admin fallback: always available, labelled `approved_as: "fallback:project_admin"` with a
   required reason; `after_sla` is a setting.
8. Project Admin may stand in for the business owner in Standard/Pilot, **not** in Strict.
9. Project Admin reach is a floor overrides cannot lower.
10. At least two Project Admins (or every owning role staffed) per Track 3 project, with a warning at
    setup.

Track 3 agent ids, owners and permissions (all new; add every one to all three owner maps). The
permission names are **proposed**: follow the existing pattern `artifact:approve_<id>` and the
existing exceptions (`artifact:approve_discovery` has no suffix); check `permissions.py` first:

| Agent | id | Owner (approves) | Approve permission |
|---|---|---|---|
| Target Architecture | `design_modernization` | architect | `artifact:approve_design_modernization` |
| Migration Strategy | `strategy` | architect | `artifact:approve_strategy` |
| Equivalence Testing | `testing_modernization` | qa | `artifact:approve_testing_modernization` (baseline and results are two sign-offs) |
| Migration Development | `development_modernization` | developer builds, architect accepts | `artifact:approve_development_modernization` |
| Migration Review | `code_review_modernization` | architect | `artifact:approve_code_review_modernization` |
| Security | `security_modernization` | security_engineer | `artifact:approve_security_modernization` |
| Cutover | `deployment_modernization` | devops_engineer + business owner co-sign | `artifact:approve_deployment_modernization` |
| Cutover Pack | `documentation_modernization` | ba (automatic acceptance) | `artifact:approve_documentation_modernization` |

## 6. The build, step by step

Detail, effort and per-day assignments are in `Development-Plan_track3.md`. Because you are one
assistant working sequentially, follow the **dependency order**, not the day grid. Where the plan
says lanes run in parallel, run them one after another (or on subagents if you have them).

### Step −1 · Close Phase 1's open items (first, half a day)
(The retrofit of the two built agents onto Track 1's document and approval system is **Step 1** below.)

`docs/superpowers/plans/2026-09-10-track3-phase1-agents.md` Task 12 leaves two items unchecked:
(a) a **private** repository clone with a **project-scoped** credential is unit-tested only; (b) the
two pages and the Orchestrator have not been confirmed in a browser. Do (a) with a real credential
(ask me for one; see section 9). For (b) give me a numbered click-through and ask me to do it. Also
audit the two built agents against R1, R2, R7, R25–R28, R31 and R39, and fix what you find as its own
small change. Report first; do not fix shared code without showing me.

### Step 0 · Decisions, hand-over schemas, backbone (Plan §8)

Deliver, in this order:
1. **Hand-over JSON schemas plus a ClaimTrack fixture instance for every packet** (brief,
   assessment, design, plan, baseline, migration record, review, security report, equivalence
   results, cutover plan). Each fixture validates against its schema. They unblock everything.
2. **Module Migration Ledger** (`modernization_modules`): states
   `assessed → designed → sequenced → baselined → migrating → in_review → verifying → verified →
   cut_over → retired`, `blocked` from any; append-only `history`; a DB CHECK/trigger refusing
   illegal transitions; a service exposing per-agent transition methods only. FORCE RLS on
   `app.current_tenant_id`. `grant_app_role`.
3. **Envelope, staleness and stable ids**: `schema_version`, `built_from`, `produced_by`, status;
   staleness = an input in `built_from` has a **newer approved** version (a newer draft does not);
   minting of `M- CT- TR- ADR- W- EC- BL- F- S- EQ- CO-` ids.
4. **`target` connector reference**: `"{agent_id}::connector::{ref}"`, `ref ∈ {legacy, target}`;
   `get_connector_for_session` honours it; a stage wired for `legacy` read can never obtain a
   `target` write credential. Project-settings "Target repository" picker.
5. **Version restore and compare**: `POST …/versions/{v}/restore` (reason required, creates a new
   version with `restored_from`; the restorer cannot approve it) and a diff endpoint.
6. **Universal Project Admin fallback**: `can_user_approve(user, project, stage)` returning
   `approved_as`; `approved_as` + `fallback_reason` columns; SLA escalation job; the PA reach floor;
   the two-Project-Admin warning. A PA fills **at most one** slot of a multi-approver gate.
7. **Programme page** (`/projects/[id]/modernization`): the ledger as a board.
   **Frontend lane for this step:** `backend/scripts/seed_track3_fixture.py`, which creates a demo
   Track 3 project and writes the ClaimTrack fixture instances through the real services
   (`snapshot_stage_payload`, the ledger service) so every page can be opened with real rows, real RLS and
   real publication state before any new agent exists (idempotent; it removes only what it created; ask
   me before running it against the dev database); the shared **status strip** (stale, waiting-on,
   read-only, self-approval, fallback badge); the shared **left rail** composition
   (`StageVersionPanel` + `DocumentList` + `RunEvidence`); the owner-map mirrors (`roles.ts`,
   `permission-catalog.ts`, `permissions.ts`, `role-permissions.ts`); the Zod and orchestrator ids for all
   eight agents, with every tile still locked.
8. Add the **owner-map, permission and registry** rows for all eight new ids **now** (behind
   `coming_soon`, not in `BUILT_AGENTS_BY_TRACK`) so the pin tests are updated once, in one reviewed change.

**Guarding tests:** every illegal ledger transition refused; only the owning agent makes its
transitions; concurrent writes from Review and Security lose nothing; newer approved input marks an
artifact stale, a newer draft does not; restore creates vM and never mutates vN; a PA approving an
owner's version is allowed and labelled, approving their own is refused, filling two slots is
refused; a `legacy` stage cannot obtain a `target` write credential; every fixture validates.
**Mutate each.** Done when the Programme page shows seeded ledger rows and the migration applies on a
fresh database and on a copy of dev.

### Step 1 · Harden and retrofit the two built agents (Plan §9 and §26)

**Retrofit first (Plan §26, about 4 engineer-days).** Both agents: register `make_document_tools` and
`make_approval_tools` (the prompt names a tool only when `has_document_tools(agent_id)` is true); confirm
`read_upstream` is recorded on both surfaces and under enforced publication; add every Track 3 stage to
`GATE_OWNER` and remove or fail-loud its `"product_manager"` default; run the deliverable checks
(structure, refusal, announcement) on their real ClaimTrack output; apply "save, don't offer" and the
style rules. Migration Intent also reads the effective **tech stack** and states its source. **Frontend
lane:** move both pages onto the shared frame (`StageVersionPanel`, `DocumentList` replacing
`GeneratedDocuments`, `RunEvidence`, `TechStackChip`, the status strip), keeping the brief card and the
assessment view as the centre. **Done when:** a BA uploads a legacy runbook, approves it, Migration
Intent cites it in a recorded brief, the agent raises the brief for approval, a different user
publishes it, and Dependency and Risk's evidence shows it read the published brief.

**Then the schema additions.** Migration Intent: `must_not_change` recorded word for word (a vague item → the agent asks);
a `kind` on every success measure (`equivalence | performance | security | schedule | cost`);
read the project's **tech stack** and **project documents** (Lessons doc §3); envelope fields;
`restore_version`. Dependency and Risk: stable `M-xx` ids (stable within a commit and across two
runs on the same commit); a "Not assessable statically" section; `golden_master` becomes a pointer;
envelope; `restore_version`. Keep the existing 109 tests green. Live-re-verify on ClaimTrack.

### Step 2 · Target Architecture — `design_modernization` (Plan §10; research §6.3)

Deterministic `capture_legacy_interfaces` (Spring/JAX-RS mappings, `web.xml`, JSP routes, outbound
HTTP clients, files read/written, Quartz/cron jobs, DB tables from DDL and queries); read tools;
`record_target_design` validator; prompt; graph; API; page; ledger rows → `designed` on approval.
Read the **tech stack** (authoritative for which technologies are approved; versions are the model's
to give but must be **non-EOL against the assessment's table**) and project documents; record a
departure from the stack as an ADR.

**Validator refuses:** a module with no pattern; a pattern outside the vocabulary (`in_place_upgrade`,
`strangler_fig`, `branch_by_abstraction`, `parallel_run`, `rewrite`, `replatform`, `retire`, `keep`);
a contract with no legacy location; an ADR with fewer than two options; an EOL version.
**Guarding tests:** `capture_legacy_interfaces` on ClaimTrack **and** eShopModernizing returns the
known endpoints/files/jobs/tables (golden files); one refusal test per validator rule; a Greenfield
project cannot reach the agent even with a forced id; a contract not found in the inventory is saved
`proposed`, never `confirmed`; approval creates one ledger row per in-scope module; re-approving the
brief marks the design stale; the same inputs twice give the same modules, contracts and patterns.

**Frontend lane (`/target-architecture`):** layers today → target with an EOL badge; pattern chips per
module; the frozen-contracts table (`proposed` / `confirmed`); version traps; ADR list; AS-IS /
TRANSITION / TO-BE diagrams; a stack-departure notice. Provisional, stale and validator-refusal states.
Reuses `adr-viewer`, `mermaid-renderer`, `diagram-image`, `TechStackChip`.

### Step 3 · Migration Strategy — `strategy` (Plan §11; research §6.4)

Deterministic tools: `propose_wave_order` (topological sort + interop constraints + risk; returns
order, forcing edges, cycles; **never violates a dependency edge** on generated graphs; cycles are
reported, never silently broken), `check_calendar` (milestones, freeze, windows, conflicts
*including inside the brief*), `estimate_effort` (labelled an estimate). Validator: every module in
exactly one wave; every `EC-xx` has an observable, an input set, a comparison (`exact |
byte_identical | numeric_tolerance | schema_equal | set_equal | percentile_threshold`); every
normalization rule has a reason; every wave has a rollback. Board writes via
`authorize_consequential` and only after an explicit yes; no board connected → says so and
continues. **A user's date is never moved; derived dates are labelled `proposed`.** Ledger →
`sequenced`. Replace the stub page.

**Frontend lane (`/strategy`, replace the stub):** wave timeline with the brief's milestones, freeze and
windows overlaid; the EC table with normalization rules and reasons; the calendar-conflicts panel with the
options; baseline plan; freeze policy; effort vs budget (labelled an estimate); board-item preview with the
write approval. States: `proposed` vs given dates, cycles, no board connected.

### Step 4 · Legacy sandbox and Equivalence Testing, Baseline mode (Plan §12; research §6.5)

Start the **sandbox first**: legacy runtime images **by digest** (Python 2.7 first; then Zulu JDK
7/8, Node 8, MySQL 5.6), no network egress except a per-run DB container, ephemeral per tenant,
in-region blob storage, masked-data seeding with deterministic tokenization (joins still line up),
record/replay stubs for external services, baseline hashing and retention. Then `plan_capture`,
`capture_baseline` (runs legacy **twice**; a noise report of fields that differ), `record_baseline`
(ledger → `baselined`, assessment `golden_master` pointer, **a rule proposal to Strategy — never a
rule applied here**).

**Highest-risk lessons for this step:** R19 (recordings must never reach another socket), the rule
that **no raw record is ever placed in a prompt or trace** (agents see masked summaries and diffs
only), R52 (drive a real sandbox, not a mock), R20 (storage paths built by code).
**Guarding tests:** legacy replayed against its own baseline = **0 differences** after
normalization; the noise-floor detector **finds a planted timestamp** and a planted per-request id;
an outbound network call from the sandbox is blocked; a prompt/trace inspection on a capture run
shows masked summaries only; a failed capture leaves no running containers and no accepted partial
baseline; capture only after an explicit yes.

**Frontend lane (`/equivalence-testing`, Baseline tab):** baseline inventory (`BL-xx`, counts, hashes,
region), scenarios, the capture approval card, the noise report. Never draws raw records; "capture in
progress" and "failed capture, nothing accepted" states.

### Step 5 · Migration Development — `development_modernization` (Plan §13; research §6.6)

Toolchain images (JDK 21 + Maven, Node 22, Python 3.12 and a ≤3.12 image for `2to3`), pinned.
Tools: `get_module_plan` (**refuses without an accepted baseline; wave order may be overridden, the
baseline rule may not**), `open_target_workspace` (branch `migrate/<module>`; for an in-place
upgrade commit the legacy module unchanged as commit 1), `list_upgrade_recipes` /
`run_upgrade_recipe` (allow-listed, pinned), tier routing (mechanical → recipes then compile fixes;
LLM-assisted → recipes then file-by-file rewrite; **manual → `blocked` with a hand-off note, no code
written**), build/test/lint loop **capped at five rounds**, `preview_equivalence` (a hint, not a
verdict), `record_module_migration` (validator: the file map covers **every** legacy file; nothing
outside the module path; build green), `push_and_open_pr` (Consequential), rework from
`F-/S-/EQ-` findings on the same branch, one commit per finding.

**Copy from the Track 1 Development agent, do not rediscover:** the project-scoped credential
lookup at *every* call site (R7), push needs the owning role **and** turn consent (R12), the
in-flight guard and cancellation-safe message repair (R30–R32), the diff card as markdown (R33), the
gpt-5 temperature rule (R25), the 90 s ceiling (R26), `path_guard` and `sandbox_policy`. **Build a
provider-neutral target repository picker from the start**: the Track 1 "Pull repos" dialog is
Azure-DevOps-only by construction.
**Guarding tests:** a mechanical module goes green with recipes alone (ClaimTrack core, Java 8 → 21);
`path_guard` refuses a write to the legacy repository and outside the module path; the file-map
validator refuses a map missing one legacy file; refuses to start without an accepted baseline; the
loop stops after five rounds and records the failure; manual tier → `blocked`; a secret in legacy
config is **not** copied (a vault reference is used and listed); push refused without the role,
without turn consent, and from a queued run; history is never rewritten.

**Frontend lane (`/migration-development`):** module picker from the ledger with tier and baseline status;
legacy ↔ target side-by-side from the file map; the file map (mapped / merged / dropped with reason);
recipe list; the build/test/lint round log (max five); rework findings; the push approval card showing the
diff; the per-module token-budget indicator; the PR list. Check which viewer the Development page's
`CodeViewer` uses and that it renders under the CSP in a real browser before reusing it. States: baseline
not accepted, manual tier (`blocked` with the hand-off note), red after five rounds, push refused.

### Step 6 · Migration Review and Security (Plan §14; research §6.7, §6.8)

Run on the same PR and share the file map. **Review** (`code_review_modernization`, read-only on both
repos): `compare_api_surface` (public methods, routes, SQL, file writers between legacy and target),
`detect_legacy_antipatterns` rule pack, `read_module_migration`, `read_legacy_counterpart`,
`submit_migration_review` with merge-recommendation rules and a **`files_read` check** (a claimed but
unopened file is refused). **Security** (`security_modernization`): reuse the whole Track 1 scan
stack; `scan_legacy_baseline` cached per legacy commit; `diff_findings` → carried over / fixed /
introduced; `check_secret_carryover`; `check_contract_authz`; sign-off policy FAIL / CONDITIONAL /
PASS. Split `security_prompt.py` into `SECURITY_OPENING` + `SECURITY_BODY` and add a **regression
test that Track 1's Security prompt output is byte-identical** after the split.
**Lessons:** repo-reading agents need the checkout under the Orchestrator (R1, the fifth wrapper-gap
instance — the failure looks like a plausible review that opened no file); SBOM/scan results use
the `None` / "not scanned" sentinel (R39); scanners are not installed by default and Semgrep skips
untracked paths silently.
**Guarding tests:** a planted trailing-slash drift on a frozen route is caught as `contract_drift`
(high); a planted carried-over secret FAILs the sign-off; unhandled trap → high; a claimed-but-unopened
file is refused; review approve + Security PASS/CONDITIONAL → `verifying`; `request_changes` or FAIL
→ `migrating`; `max_rejections` → `blocked` and escalated.

**Frontend lane:** `/migration-review` (merge recommendation; `F-xxx` table with legacy and target links;
`CT`/`TR`/traceability/EC checklists; known debt; the files-read list) and `/modernization-security`
(carried-over / fixed / introduced filter; `S-xxx`; contract authorization per `CT`; SBOM; verdict; the
secret carry-over banner; "not scanned" shown as such, never as zero).

### Step 7 · Equivalence Testing, Verify mode (Plan §15)

Same agent and harness as Baseline. `provision_target_sandbox` from the PR branch, `replay_baseline`
(records the baseline version replayed), `diff_outputs` applying **only** the EC's normalization,
classification `regression | normalization_gap | accepted_change | environment`,
`run_perf_comparison`, `record_equivalence_results` (ledger → `verified` or `migrating`; an EC that
did not run is `not run`, never `passed`). **Normalization cannot be changed from Testing**: no tool
path edits a rule; a gap only creates a proposal.
**Guarding tests:** a planted rounding change is caught as a regression; each comparison type on
fixtures; a field varying in legacy is `normalization_gap`, not a pass; the same replay twice gives
the same verdict; verification only after an explicit yes.

**Frontend lane (`/equivalence-testing`, Verify tab):** the per-module EC verdict grid; `EQ-xxx`
differences with masked examples; the performance chart; the baseline version replayed. "Not run" is
never drawn as "passed".

### Step 8 · Cutover — `deployment_modernization` (Plan §16; research §6.9)

Request-only. `read_wave`, **`readiness_check` computed by a tool — the model can never turn a red
green**, `plan_cutover` (T-minus steps, `CO-x.y` with rollback trigger and action, downtime
arithmetic — downtime over the window is *reported*, never planned around), `plan_traffic_shift`
(0→5→25→50→100 with hold times and SLO guards), `plan_parallel_run` (**exactly one sender per
outbound file/call per day**), `plan_data_cutover`, `request_cutover_step` /
`check_cutover_step` (file approval requests; execute nothing), `schedule_decommission` (only after
cutover **and** hypercare, each step gated, in order), `read_slo_metrics`, and release sign-off by
DevOps **and** the business owner (a PA fills at most one slot, never the business owner's in Strict).
**Decide before you build:** how an autonomous run asks (R13). Cutover is interactive-only or
gate-and-wait.
**Guarding tests:** a red `readiness_check` → no-go and **not overridable, including by a
prompt-injection attempt** (write that test); the one-sender invariant; decommission before
cutover + hypercare refused; sign-off needs both slots and the producer cannot sign; hypercare closes
only with guards green; a firing rollback trigger is reported first.

**Frontend lane (`/cutover`):** wave picker; the readiness grid per module with who closes each red;
the `CO-x.y` runbook with live status and rollback trigger; traffic-shift steps; the parallel-run day
table showing the single sender; the downtime arithmetic; the SLO strip; the decommission checklist; the
two-person release sign-off panel. States: red gate (no-go, not overridable), rollback trigger fired
(shown first), decommission locked, a run with no signed-in person cannot request steps.

### Step 9 · Cutover Pack — `documentation_modernization` (Plan §17; research §6.10)

`build_traceability_map` (deterministic: ledger + file maps + ECs + test runs + PRs + review/security
reports + cutover steps; **gaps shown as gaps**), `compile_equivalence_evidence`,
`compile_decommission_record`, the as-built SDD, ops hand-over, results against the brief, the list of
fallback approvals, export, gated `open_docs_pr`. Every generated statement cites an artifact version
or evidence link; a missing artifact reads **"not recorded"**, never an invented value; no personal
data in any document. **This step is the Documentation-RTM lesson in full** (R39): never present a
textual inference as a structural match.
**Guarding test:** a planted unmapped legacy file appears as a visible gap.

**Frontend lane (`/cutover-pack`):** the traceability table (legacy file → target, contracts, ECs,
evidence, PR, verdicts, cutover step) with **gaps shown as gaps**; evidence sections; results against
the brief; the fallback-approval list; the docs-PR approval.

### Step 10 · End to end, hardening and acceptance (Plan §18, §19.5, §24.6)

Full ClaimTrack: all ten agents on the reports module through a staging cutover rehearsal, then core
and web through Verify; eShopModernizing through the Migration Development agent; resilience (pause/resume at every
ledger state, restart mid-capture and mid-cutover); performance and cost; security review of sandbox
egress, secrets, RBAC, track isolation and personal data in prompts and documents; UAT walkthrough per
role. All acceptance criteria in Plan §19.5 **and** §24.6 must hold. Then the **whole-branch review**
(R54).

## 6A. The frontend lane: every page its own UI, tested by me

Full per-page specifications are in `Development-Plan_track3.md` §25.1; the shared frame and the rules
are in `Track-3 Lessons from Track 1-2.md` §8. In short:

| Page (route) | Own centre surface |
|---|---|
| Migration Intent (`/requirements-modernization`) | Brief card + must-not-change list + success measures by kind + effective stack and its source + cited documents |
| Dependency and Risk (`/discovery`) | Module table (`M-xx`, tier), factors, graph, flags, "not assessable statically", golden-master pointer |
| Target Architecture (`/target-architecture`) | Layers, pattern chips, contracts, traps, ADRs, AS-IS/TRANSITION/TO-BE diagrams |
| Migration Strategy (`/strategy`) | Wave timeline with milestones, EC table with normalization rules, conflicts, freeze, board preview |
| Equivalence Testing (`/equivalence-testing`) | Baseline tab (BL-xx, scenarios, noise) and Verify tab (EC verdict grid, EQ-xxx, performance) |
| Migration Development (`/migration-development`) | Module picker, legacy ↔ target side-by-side, file map, round log, push approval card, budget |
| Migration Review (`/migration-review`) | Recommendation, F-xxx, contract/trap/traceability checklists, files read |
| Security (`/modernization-security`) | Carried-over / fixed / introduced, contract authz, SBOM, secret banner, verdict |
| Cutover (`/cutover`) | Readiness grid, CO-x.y runbook, traffic shift, parallel-run senders, downtime arithmetic, SLOs, decommission, two-person sign-off |
| Cutover Pack (`/cutover-pack`) | Traceability table with gaps, evidence, results vs brief, fallback approvals |
| Programme (`/modernization`) | The ledger board: modules × states, waves, blocked, stale, "Waiting on me" |

Shared on every page: the chat drawer, `StageVersionPanel`, `DocumentList`, `RunEvidence`,
`ModelSelector`, `TechStackChip` (where a stack matters) and the status strip. **How I will test:** the
seed script gives me a real demo project; every page opens by URL while its tile is locked; each step
ends with a click-through script naming the persona, the steps, the expected results and what was only
verified over the wire. The tile flips last.

## 7. The wiring checklist for every new agent (verified from the two built agents)

Backend
- [ ] `backend/agents_orchestrator/<name>_agent/` with `agents/` (compiled graph built by
      `modernization_common.graph.build_tool_agent_graph`), `prompts/`, `tools/`, and
      `<name>_agent_api.py` built on `modernization_common.standalone.serve_agent_socket`.
- [ ] `config/agent_registry.py`: `AGENT_REGISTRY` entry; `TRACK_PORTFOLIOS["modernization"]` **last**;
      `_OWNER_OF`.
- [ ] `shared/authz/permissions.py` (`_PHASE_PERMISSION`, catalog, role grants);
      `shared/governance/routing.py` (`AGENT_OWNER_ROLE`); `shared/routers/custom_roles.py`.
- [ ] `agents_orchestrator/orchestrator2/registry.py` (graph + prompt loaders, capability),
      `router.py` (`DISPLAY_NAMES`, `_CAPABILITIES`, aliases, Track 3 roster text),
      `deliverables.py`, and the stage output-dir mapping in `shared/routers/runs.py`.
- [ ] `shared/models/orm.py` (`Run.<artifact>` column), `shared/services/artifact_service.py`
      (`_COLUMN_MAP`), `config/context_broker.py` (`_ARTIFACT_FIELDS` + formatter),
      `shared/routers/agent_profiles.py` (`PIPELINE_ORDER`), `shared/routers/modernization.py`
      (read endpoint), `process_api.py` (mount).
- [ ] Alembic migration: the `runs.<artifact>` JSONB column; the CHECK on deliverables agent ids
      widened; the approve permission and its role grants; `alembic heads` checked; downgrade reverses.
- [ ] Track scoping: `assert_agent_access_for_chat_on_track`; a Greenfield project cannot reach the
      agent even with a forced id.
- [ ] Traces tagged with project, module and wave.

Frontend
- [ ] `lib/schemas/enums.ts`, `lib/tracks.ts`, `lib/agents.ts` (label, description, `GATE_POLICY`,
      route, `BUILT_AGENTS_BY_TRACK` **last**), `lib/roles.ts`, `lib/auth/permission-catalog.ts`,
      `lib/auth/permissions.ts`, `lib/auth/role-permissions.ts`.
- [ ] `lib/orchestrator/agents.ts`, `lib/orchestrator/types.ts`, `lib/orchestrator/protocol.ts` (and the
      emitter), `app/api/chat/route.ts` `agentWsPath` case + `chat-agent-map.test.ts`.
- [ ] `lib/api/modernization.ts`, `lib/schemas/modernization.ts`, **the BFF handler for every route**,
      the page under `app/(app)/projects/[id]/<route>/`, components under `components/modernization/`.
- [ ] Tests: `__tests__/lib/track3-agents.test.ts`, `__tests__/app/agent-ownership.test.ts`, the
      page's access-gate render test, the read-only-stage state, the self-approval-refusal state.
- [ ] `npx tsc --noEmit`, `npx eslint` on your files, `npx vitest run` on the touched files.

## 8. Environment and commands

```bash
# Day 0 checks (repeat before every live verification)
docker ps                                            # sdlc-postgres (5433), sdlc-redis, sdlc-litellm healthy
cd backend && uv run alembic heads                   # exactly one head; note it
# app role must not bypass RLS:  select rolname, rolbypassrls from pg_roles where rolname in ('sdlc_app','postgres');
# test DSN must differ from the app DSN:  compare backend/.env and backend/.env.test

# start
cd backend && uv run uvicorn process_api:app --reload --port 8004 --ws-max-size 1000000
cd frontend && npm run dev                           # :3000 ; restart it before live verification

# tests (specific files, test database only)
cd backend && uv run python -m pytest tests/orchestrator2/ tests/test_agent_ownership_is_single_sourced.py -q
cd frontend && npx vitest run <files> && npx tsc --noEmit
```

Process start time vs the commit under test (Windows): `Get-Process -Id <pid> | Select StartTime`
against `git log -1 --format=%ci <commit>`; or simply restart. Semgrep:
`uv pip install semgrep==1.173.0` (not `uv add`); Trivy and Gitleaks via `winget`; a running shell
needs its `PATH` refreshed. Use `.invalid` hostnames in test URLs.

## 9. Stop and ask me (mandatory)

Stop, explain, and wait for me before:
- any `git commit`, `push`, PR, branch deletion, `reset`, or `--force`;
- any action against the **dev database** beyond reading (migrations to dev, running the seed script,
  seeding, deleting rows);
- the **capacity decision**: the plan's 75 engineer-days are fully allocated, and the retrofit (about 4)
  plus the seed script and shared frame (about 2) do not fit inside them. Recommend either extending by one
  to two days or applying the plan's cut order (Plan §24.4), and wait for me;
- needing a **real credential** (a target-repository PAT with write scope, an Azure model key, a
  cloud storage account, a metrics source) — say exactly what and why;
- provisioning **cloud resources** or anything that costs money or leaves the machine;
- choosing a **legacy runtime image source** or a **data-masking approach** (needs data protection
  input) — propose, do not decide;
- the **Cutover** design of how an autonomous run asks for approval (R13);
- any change to a **shared** module used by Track 1/2 (`modernization_common`, `config/connection_manager`,
  the connector factory, the model gateway, the owner maps) beyond adding Track 3 rows — show the diff
  and the Track 1 tests you ran first;
- a **product decision** (context truncation policy, whether Track 2 is in scope, per-module
  budgets) — recommend, do not decide;
- discovering that a document or an earlier claim of mine was wrong in a way that changes the plan.

## 10. Anti-patterns (each of these already cost this team days)

- Trusting a green suite. Trusting a plan's claim about production behaviour. Trusting a status
  document without checking the code.
- A prompt sentence standing in for a control. A comment asserting a guarantee the code does not
  provide (twelve instances in the orchestrator rebuild alone, one with a confidentiality
  consequence). If you write such a comment, prove it on every path or narrow the wording.
- A "fallback" that widens access (broadcast to everyone; a draft when the published version is
  missing; an env key when BYOK is missing; a default owner when a key is missing; a superuser session
  when a tenant session returns nothing).
- A confident number where the truth is "not measured" (`vulnerabilities: 0`, `passed` for an EC that
  did not run, a textual guess presented as a structural match).
- Two tools with the same job, or two retry layers, or two approval systems, or two owner maps.
- A fix applied at one call site when the same function has other callers.
- A test that patches a target that does not exist, asserts a substring the fixture contains, asserts
  "some exception was raised", or is satisfied by the roster/prompt/echo.
- An autouse fixture, a package-wide conftest change, or any test infrastructure change outside the
  files a task names.
- Monaco in the chat. Raw customer content in a prompt, a trace or a `broadcast`.
- Starting the next step before the previous one is live-verified and reviewed.
- Enabling a tile before the agent runs end to end.

## 11. What to deliver

For each step: the code and tests; **the page and its click-through script for me**; the plan file; the `build-log.md` entries (decisions, findings,
mutants and kills, fix rounds, what was wire-level only); the live-verification record (commit, process
start time, persona, ClaimTrack result); an updated `Track-3 Flow document.md` status line; and a
short **handoff note** naming what is open. At the end: the whole-branch review report, the
acceptance-criteria table (Plan §19.5 + §24.6) with evidence for each row, and a list of every open
item with an owner.

**Begin now:** do the reading in section 1, then write the first entry in
`help/Track-3/build-log.md` (what exists, where documents disagree with code, your step −1 and step 0
plan), and stop for me.

---

*End of prompt.*

## Notes for the person giving this prompt

- It is long on purpose. The rules are the point; the step specs point back to the plan, the flow
  document and the research file rather than repeating them, so the assistant reads the primary
  documents.
- It assumes one assistant working step by step with checkpoints. If you would rather it run
  several steps unattended, say "continue through steps N–M without stopping, but still stop at every
  item in section 9" when you paste it.
- Two things in it are decisions for you, not the assistant: the ten defaults in section 5 (change
  any you disagree with before pasting) and whether to allow it to commit as it goes (rule 4 says
  no).
- The first entry it writes will show you whether it read the documents. If it does not name the
  places where the documents disagree with the code (the stale `agent-build-plan`, the missing
  wiring items, the migration head), it did not read closely enough.

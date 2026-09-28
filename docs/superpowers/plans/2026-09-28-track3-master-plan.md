# Track 3 — Phase-wise implementation plan (master)

Branch `akshat_track3` (= `akshat_main` @ `621b8904`). Sources: `Track-3 Implementation Prompt.md`,
`Development-Plan_track3.md`, `Track-3 Flow document.md`, `track3-research.md`, the Lessons doc (R1–R57).
Decisions, findings and evidence go to `help/Track-3/build-log.md`. Each phase gets its own detailed plan
file before its code starts. **No timeline:** phases are ordered by dependency only, and each ends at a
checkpoint (stop, report, wait).

ClaimTrack is a **simulated customer** used as the scenario and fixture throughout; there is no real legacy
code yet. Anything that needs a real legacy repo or a real credential is deferred until you provide one.

---

## 1. Guiding rule: Track 3 rides on the platform, it does not fork it

Every Track 3 agent gets access to the outside world the same way Track 1 agents do, and Track 1 must keep
working unchanged. Concretely, Track 3 reuses (never copies):

| Platform system | What it does | Track 3 use |
|---|---|---|
| **Integrations** (`integration_grants`) | Org/BU admin grants a connector kind (azure_devops, github, jira, …) to a Business Unit | Same grants; no Track 3 grant type |
| **Stage wiring** (`projects.connectors` = `{agent_id: [kind…]}`) | Project admin wires a kind to a stage in "Tools per stage" | Each Track 3 stage is wired like a Track 1 stage |
| **Access level** (`projects.tool_access_modes`, key `{agent_id}::{kind}::{target_ref}`; fallback `project_connector_access`; then `DEFAULT_TOOL_MODE`) | read / write / both per stage and tool | Legacy reads use `read`; target writes need `write` **plus** the Track 3 repo-role rule (§3) |
| **Credentials** (`project_integration_credentials` → `app_secrets`/Key Vault via `secret_store`) | Per-person-per-project PAT, else tenant-wide | Always resolved with `project_id` **and** `owner_id` (R7) |
| **Connector factory** (`get_connector_for_session` → `ScopedConnector`) | The one place access is enforced | The only way any Track 3 tool gets a connector |
| **Turn binding** (`orchestrator2/connectors.bound_connector`) | Binds the connector for one turn, standalone and Orchestrator alike | Already used by `modernization_common/standalone.py` |
| **Repo services** (`repo_source` → `ado_repos` / `github_repos`, `prepared_targets`, `run_workspace`) | Provider-neutral list/clone/branch/PR; prepared-workspace records that survive restarts | Legacy pull and target workspace both go through `repo_source` (provider-neutral from the start) |
| **Consequential gate** (`authorize_consequential`) | Owning role + this turn's consent | Push, capture, verify, board writes, cutover steps, docs PR |
| **Versions / publication / consumption** (`artifact_versions`, `read_upstream`, `artifact_consumptions`) | Frozen versions, publish gate, recorded reads | Every Track 3 artifact and every hand-off read |
| **Project documents** (`document_tools`, `document_approval`) | Upload, approve, read on demand | Legacy specs/runbooks read by every Track 3 agent |
| **Tech stacks** (Agent Studio) | Effective stack with its source | Migration Intent, Target Architecture, Migration Development |
| **Models** (`resolve_model_for_run`, `guarded_completion`, `budget_guard`) | Project-scoped BYOK, one retry layer, budgets | Shared builder in `modernization_common/graph.py` |
| **Governance, notifications, audit, traces** | Access requests, gate notifications, audit events, Langfuse | Gate raised → owner notified; traces tagged project/module/wave |

**Track 1 regression guard (every phase).** Any change to a shared module (connector factory, access
resolution, `artifact_versions`, owner maps, `gate_routing`, `modernization_common`, `security_prompt`) is
shown to you as a diff with the Track 1 test files for that module run on `sdlc_product_test`, before it is
applied. Each phase ends with the Track 1 regression set green (§5).

## 2. Findings that shape the design (verified in code)

1. **`DEFAULT_TOOL_MODE = "both"`** (`shared/authz/connector_access.py:143`). A stage that is wired with no
   explicit mode gets read **and** write. The Lessons doc (E4) says the default is `read`; the code disagrees.
   Track 3 therefore cannot rely on the stage's level alone to keep legacy read-only (§3).
2. **The stage-mode key's third segment is the connector kind** (`{agent_id}::connector::{target_ref}`,
   e.g. `…::connector::azure_devops`). The research doc's plan to put `legacy`/`target` in that slot would
   collide with it: the legacy and target repos are often the **same kind** under the same credential.
   So repo **role** must be a separate concept (§3).
3. A provider-neutral `repo_source` façade (ADO + GitHub) already exists, so the "Pull repos is ADO-only"
   issue applies to the Development page's dialog only, not to the services.
4. The two built agents lack document tools, approval tools, tech-stack reading, `read_upstream` recording,
   and `GATE_OWNER` rows. Their shell sets "system prompt delivered" before the turn succeeds (R32) and has
   no per-session in-flight guard (R31).

## 3. Repository roles: legacy and target (replaces research §5.1's key proposal)

- **Project repository roles** (new, per project): `legacy = {kind, repo, branch}`,
  `target = {kind, repo, default_branch}`, set by the Project Admin in project settings ("Legacy repository",
  "Target repository"), chosen with the provider-neutral `repo_source` picker. The connector kind must already
  be granted to the BU and wired to the asking stage; the role only says *which repo* plays which part.
- **Role → stage rule, in code** (one table, pinned by a test):
  `legacy`: read for all ten Track 3 stages. `target`: write for `development_modernization` and
  `deployment_modernization`; read for review, security, testing, documentation; nothing for the others.
- **Enforcement** at one choke point (a `modernization_common/repos.py` wrapper over `repo_source`), and
  a push/commit requires all of: (a) the connector level for that stage includes `write`, (b) the stage is a
  target writer by the role rule, (c) the remote equals the configured **target** repo, never the legacy one,
  and (d) `authorize_consequential` (owning role + this turn's consent). Legacy clones stay read-only by
  construction (push URL disabled, no write tools), as today.
- Guarding tests: a legacy-role stage cannot push even with `both`; a target writer cannot push to the
  legacy remote; a stage with `read` cannot push to target; each with a negative control and `.invalid` URLs.

## 4. Phases (dependency order)

| Phase | What | Why here |
|---|---|---|
| **A · Audit + shell fixes** | Audit agents 1–2 and `modernization_common` against R1, R2, R7, R25–R32, R39; fix R31 (in-flight guard, tracked cancellable turns) and R32 (delivered flag after success) in `standalone.py`. Deferred until you provide them: the private-repo clone with a project credential, and your browser click-through. | The shell is the template for 8 more agents; fix it before it is copied |
| **B · Retrofit agents 1–2 onto the platform** (Plan §26) | Document tools + approval tools on both; Migration Intent reads the effective tech stack and states its source; `upstream_from_pages` → `read_upstream` (consumptions recorded, enforced publication respected on both surfaces); Track 3 rows in all four owner maps for **all ten** ids (tiles locked for 3–10) and `GATE_OWNER`'s swallowing default made fail-loud; "save, don't offer" and deliverable checks on both prompts; both pages onto the shared frame (`StageVersionPanel`, `DocumentList`, `RunEvidence`, `TechStackChip`, status strip). | **Before the backbone and before agent 3**: this is the platform parity every new agent copies. Doing it first means the template is right, it proves documents/approvals/consumption/tech stack work for Track 3 on real rows, and Target Architecture reads retrofitted inputs. Nothing here needs the ledger |
| **C · Backbone** | ✔ Hand-over schemas + fixtures (done). Module Migration Ledger (`0066`, FORCE RLS, per-agent transitions). Envelope, staleness, id minting. **Repository roles (§3)**. Version restore + compare. Universal Project Admin fallback (`approved_as`, ≤1 slot, Strict business-owner rule, SLA escalation, PA-reach floor, two-PA warning). Seed script for the simulated ClaimTrack project; Programme page. | Everything from agent 3 on writes the ledger and the envelope |
| **D · Schema additions to agents 1–2** | `must_not_change` word for word; `kind` on success measures; stable `M-xx` (sorted by path, not by risk — the assessment currently orders modules by score, which changes between runs); "Not assessable statically"; `golden_master` pointer; envelope fields; `restore_version`. Both emit their hand-over packet (validated by the Phase C models). | Needs the envelope and the packet models; must precede agent 3, which reads these fields |
| **E · Target Architecture** | Agent + `/target-architecture` page | Creates the ledger rows |
| **F · Migration Strategy** | Agent + `/strategy` page (replaces stub); board writes through the wired board connector | Produces ECs and the baseline plan |
| **G · Legacy sandbox + Equivalence Testing (Baseline)** | Needs your decisions on image source and masking; needs real legacy code for live runs | Nothing can be proven without a baseline |
| **H · Migration Development** | Target workspace through §3; recipes; push via the gate | Needs a real target repo + write credential |
| **I · Migration Review + Security** | Read legacy + target through §3 | Run on H's PR |
| **J · Equivalence Testing (Verify)** | Replay on the target | After I |
| **K · Cutover** | Request-only; your R13 decision first | Aggregates every gate |
| **L · Cutover Pack** | Traceability map, evidence, docs PR via §3 (target write) | Compiles everything |
| **M · End to end + whole-branch review** | Full simulated ClaimTrack chain; acceptance table | Last |

Stub pages (`strategy`, `migration-mapping`, `validation`) are replaced or removed in the phase that owns
them. Tiles flip last, after your click-through (R42).

## 5. Track 1 regression set (run at the end of every phase, on `sdlc_product_test`)

Owner-map pins (`test_agent_ownership_is_single_sourced.py`, `test_agent_reach_matches_frontend.py`),
connector access (`test_legacy_code_connector_access.py` and the connector-grant tests), versions and
publication, orchestrator2 (`tests/orchestrator2/`), the development agent's tests (`tests/development/`),
security prompt byte-identity (added in phase I), plus the BFF proxy and chat-map tests in the frontend.
The exact file list is fixed in Phase A and recorded in the build log.

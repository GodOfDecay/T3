# Track 3 Phase G — Legacy sandbox + Equivalence Testing (Baseline mode)

Research §6.5 (Baseline mode only; Verify mode is Phase J), §4.2, Implementation Prompt Step 4.
Master plan row G. Evidence and decisions go to `help/Track-3/build-log.md` Entry 13.

## User decisions (2026-09-30)

| Question | Answer | How it is applied |
|---|---|---|
| Legacy code | Build a small sample app; don't go overboard | `samples/legacy-claimtrack/` — Python 2.7 stdlib (no pip): claims API + settlement batch + SQLite, synthetic data |
| Images | Public images, stored in Docker; will change later | Official `python` images pinned **by digest** in ONE config (`sandbox/images.py`); a legacy Dockerfile whose `FROM` is not digest-pinned is refused. There is no public PwC registry known to us — a registry swap is a config change |
| Masking | Deterministic tokenisation at deployment; now synthetic/sample data only | Sample data is synthetic by construction; the capture refuses a profile without `"data": "synthetic"`; the model never sees a value (field paths, counts and masked SHAPES only). Tokenisation is a later, pluggable step (recorded as an open item) |
| Storage | Local now, Azure later | `BaselineStore` interface; `LocalBaselineStore` under `files/equivalence/<project>/…` (paths built by code, R20); region `local-dev`; retention 90 days |
| Other defaults | Decide as needed | Below |

## Defaults decided here

- G1. **Capture profile is data** (universal): `sdlc-sandbox.json` in the legacy checkout, or one the agent
  proposes and saves for the project. It says how to build (Dockerfile), seed, start (port, health path),
  which external services are stubbed (env var → canned responses), and per equivalence criterion the
  scenarios: `http` (a JSONL request set) or `batch` (a command + output globs). The harness knows nothing
  about ClaimTrack. UI journeys (Playwright) and perf are out of scope for G (said in the tool text).
- G2. **Sandbox**: per capture, a Docker network created `--internal` (no egress); containers: the app
  (image built from the checkout, read-only root, tmpfs for writable dirs), a stub server, a request driver.
  Every object carries `sdlc.capture=<id>`; removal is in `finally`. Two runs, each on a FRESH app container
  (seeded again), so the only differences are the system's own nondeterminism.
- G3. **Noise**: run 1 vs run 2, field by field (JSON paths for HTTP; `file#Lline` for batch outputs).
  A varying field is covered when a normalization rule's `field` matches it (exact, suffix or glob).
  Every uncovered varying field must be PROPOSED to Strategy (`BaselinePayload` already enforces this).
- G4. **Baseline** = run 1's recordings, canonicalised and hashed (sha256); `BL-xx` per scenario group.
- G5. **Consequential**: `capture_baseline` runs the legacy system — owner consent this turn + QA or Project
  Admin OF THIS PROJECT (the Strategy board-write pattern). Orchestrator runs follow `authorize_consequential`.
- G6. **Ledger on APPROVAL** (as Phases E, F): accepting the baseline version moves each module
  `sequenced → baselined` with its `baseline_ids`; a module not sequenced is refused (409), all or nothing.
- G7. **Frozen versions stay frozen**: the assessment's `golden_master` is not rewritten; the baseline's
  `built_from` and the ledger's `baseline_ids` are the pointer (research §4.2's intent without mutating a
  frozen version).
- G8. Legacy code: `testing_modernization` joins `TRACK3_STAGES` (it reads/pulls the checkout).
- G9. `file://` stays refused for users; the dev script `scripts/install_legacy_sample.py` calls `pull_now`
  directly (localhost dev only).

## Build order
1. Sample app + Dockerfile + profile + install script.
2. Backend: images config, profile validation, runner, noise + masking, store, tools, prompt, graph,
   socket, wiring (registry, orchestrator2, 0073, runs, artifact service, context broker, standalone),
   approval hook, page routes (latest, packet, export, captures).
3. Tests: pure (profile, noise, masking, store), REAL Docker (egress blocked, self-replay = 0 differences,
   planted timestamp + request id found, failed capture leaves nothing), DB (record, approval, ledger,
   consent/role), prompt/trace shows masked summaries only.
4. Frontend `/equivalence-testing`: baseline inventory, scenarios, noise report + proposals, captures
   (in progress / failed, nothing accepted), ledger panel.
5. Review, fix wave, mutation, regression, click-through, build log, handoff.

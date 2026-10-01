# Click-through — Track 3 Phase G (Equivalence Testing, Baseline mode)

This is for you to run in a browser. I have not run it in a browser. Every check was at the test level:
render tests against backend-produced fixtures, real-Postgres tests through the real app, and the sandbox
driven for real in Docker, with every guard mutation-proven (see `build-log.md` Entry 13). Tick each step
and note anything that differs.

**Before you start:**
- The dev database needs migration **0073**. It adds `runs.equivalence_artifacts` and adds
  `testing_modernization` to the Orchestrator deliverables check. Apply it with
  `cd backend && uv run python -m alembic upgrade head`, only once you agree, then re-run
  `uv run python -m scripts.grant_app_role`. **Restart the backend afterwards**: the ORM maps the new column.
- **Docker must be running on the backend's machine** (Docker Desktop on Windows). The sandbox builds and runs
  the legacy code there. The first capture pulls the pinned `python` images (a few hundred MB).
- Install the sample legacy system for the project: `cd backend && uv run python -m scripts.install_legacy_sample
  --project-id <project uuid>` (localhost only). It pulls `samples/legacy-claimtrack` as the project's legacy code.
- The project needs an **approved target design** and an **approved migration plan** (Phases E and F).
  Approving the plan puts the modules on the ledger as **sequenced**.
- QA is `tester@gmail.com`. Acceptance needs a **second QA** or `projadmin@gmail.com` (nobody accepts
  their own baseline).
- The **Equivalence Testing** tile is unlocked (at your request) for QA and the Project Admin.

## A. The page

| # | As | Do | Expect |
|---|---|---|---|
| A1 | QA | Open `/equivalence-testing` on a **Greenfield** project | "Equivalence Testing is a Code Modernization agent", no chat |
| A2 | QA | Open it on the Track 3 project | The intro, the Programme strip, the legacy-code pull control, **Run Equivalence Testing agent** and a **Captures** button. Left: **Baselines** (empty) and **Documents**. Centre: the four-step guide "How a baseline gets recorded" |
| A2b | QA | Look at the legacy-code line under the intro | The repository, its commit and when it was pulled (a fix in this phase: it used to read "No legacy code pulled yet" on this page whatever was pulled) |
| A3 | Developer (no reach) | Open the page and the chat | The chat refuses |

## B. The capture profile

| # | As | Do | Expect |
|---|---|---|---|
| B1 | QA | Open the chat, say "hi" | It greets you as the Equivalence Testing agent, says BASELINE mode, and names the plan version it works from |
| B2 | QA | "How will you run the legacy system?" | It shows the profile **from `sdlc-sandbox.json` in the legacy code**: synthetic data, the Dockerfile, the service on port 8080, the **fraudscore** stub, and three scenarios (claims-read 5 cases, settle 6, bank-file 1) |
| B3 | Architect or Developer | Ask it to change the profile (say, add a scenario) and save | **NOT SAVED — only QA or a Project Admin of this project saves the capture profile** |
| B4 | QA | Ask it to save a profile that uses real data (`"data": "production"`), an unpinned base image (`FROM python:2.7`) or a path outside the checkout | Each is refused and named: synthetic data only, pin by digest, a file inside the checkout |

## C. Capturing

| # | As | Do | Expect |
|---|---|---|---|
| C1 | QA | "Capture the baseline" | It shows a **capture plan** first: each criterion with its scenarios and case counts, EC-04 "not captured" (a load test), the stubbed services, and asks you to go ahead. **Nothing runs yet**; the Captures dialog is empty |
| C2 | Developer | Ask it to capture (say yes) | "Only QA or a Project Admin of this project captures a baseline" |
| C3 | QA | Say **yes** | The capture runs (a minute or two the first time: the image builds). The **Captures** dialog shows it **running** and refreshes itself. Then: two runs complete, a table per scenario with the fields that differed between runs, shown as shapes only (`<uuid> vs <uuid>`, `<timestamp>`), never a claimant, an amount or an id |
| C4 | QA | Read the reply | It lists `requestId` for EC-01 and EC-02 as needing a rule **proposed to Migration Strategy**, never applied |
| C5 | QA | While a capture is running, open a second chat (or tab) and ask for another capture | "A capture is already running for this project — wait for it to finish." |
| C6 | QA | Start a capture and press **Stop** on the turn | The Captures dialog shows it **failed — cancelled**, nothing recorded. A minute later a new capture is allowed. `docker ps -a --filter label=sdlc.capture` shows nothing left |
| C7 | QA | Break the profile (service command `python -c 'import sys; sys.exit(3)'`) and capture | **FAILED**: "did not answer on /health … its container is exited (exit 3)". Nothing recorded; the dialog shows **failed — nothing recorded, nothing accepted** |

## D. Recording and accepting

| # | As | Do | Expect |
|---|---|---|---|
| D1 | QA | "Record it" without proposing a rule for requestId | **NOT RECORDED YET**, naming EC-02 / requestId |
| D2 | QA | Ask it to also propose a rule for `claim.payout` | Refused: a field that did not vary |
| D3 | QA | Let it record with the two requestId proposals | **Baseline v1 (draft)** opens: BL-01 (M-01, EC-01, 5 cases), BL-02 (M-01, EC-02, 6 cases), BL-03 (M-02, EC-03, 1 run), each with a sha256 and region `local-dev`; tabs Scenarios, Noise floor, Proposed rules (2), Not captured (EC-04). The ledger panel says accepting will move M-01 and M-02 to **baselined** |
| D4 | QA (same) | Try to accept v1 | Refused: you recorded it |
| D5 | Second QA or Project Admin | Accept v1 | Accepted. The ledger shows M-01 and M-02 **baselined** with their BL ids. A Project Admin acceptance is labelled as the fallback |
| D6 | Any | Export v1 as Word | `equivalence-baseline-v1.docx`, with hashes, counts and masked shapes, no recorded data |

## E. The loop back to Migration Strategy

| # | As | Do | Expect |
|---|---|---|---|
| E1 | Architect | On **Migration Strategy**, ask "did Equivalence Testing propose any rules?" | A table: EC-01 and EC-02, `requestId`, the proposed rule, the evidence ("in 5 of 5 cases"), both **open** |
| E2 | Architect | Agree one, have it record the revised plan, approve it | Asked again, that proposal now shows **yes** with the plan's rule; the other stays open |
| E3 | QA | Back on Equivalence Testing, the baseline v1 page | It is marked **out of date** (a newer approved plan). A new capture against plan v2 is needed for the criteria that changed |

## F. Retention and audit (for an admin)

| # | Check | Expect |
|---|---|---|
| F1 | `audit_events` for the project after C3/B3/D3 | `modernization.capture_profile_saved` (a hash and the scenario ids, no commands), `modernization.baseline_capture_started` and `…_completed` (or `…_failed`), each with the actor and the capture id |
| F2 | Stop the backend in the middle of a capture, start it again | Within an hour (the retention sweep) or at the next capture, that capture shows **failed — interrupted** and its containers are gone |
| F3 | A capture never recorded, 90 days on (`SDLC_BASELINE_RETENTION_DAYS`) | Deleted by the hourly sweep; a recorded baseline's capture is kept |

# Click-through — Track 3 Phase I (Migration Review and Security)

This is for you to run in a browser. Both agents ran for real at the test level (Postgres, git, and the three
scanners in Docker; `tests/review_security_modernization/`). The model-driven conversation has not been run
in a browser yet: that is this script. Tick each step and note anything that differs.

**Before you start:**
- The dev database needs migration **0075** (`runs.migration_review_artifacts`,
  `runs.modernization_security_artifacts`, the deliverables check). Apply it with
  `cd backend && uv run python -m alembic upgrade head`, then `uv run python -m scripts.grant_app_role`, then
  restart the backend.
- **Docker must be running** on the backend's machine: the scanners run there, offline.
- **Trivy's vulnerability database, once** (needs network, about 1.5 GB). Without it Trivy reports
  "not installed" and the sign-off can never be PASS (that is correct behaviour, step D6):
  ```
  docker run --rm -v <FILES>/scanner-cache/trivy:/cache aquasec/trivy@sha256:ab70a02200597efa04748f210f793936eb647cbcdb0ea69cc30b226d6f5a22c7 image --download-db-only --cache-dir /cache
  ```
  `<FILES>` is the backend's files directory (`sdlcSettings().FILES`), or set `SDLC_TRIVY_CACHE` to any folder.
- Phase H done on the project: module M-01 **in review** (its record accepted, its pull request opened).
- Wire the target repository's connection to **Migration Review** and **Security** with **read** access
  (Tools per stage), and the legacy one too. Read is all they get: they never write.
- People: `architect@gmail.com` runs the review; a SECOND Architect or `projadmin@gmail.com` accepts it.
  `security@gmail.com` runs the scan; a SECOND Security Engineer or the Project Admin accepts it.
- The tiles say **Coming soon** until this click-through passes (R42). Open the pages by URL:
  `/projects/<id>/migration-review` and `/projects/<id>/modernization-security`.

## A. The pages

| # | As | Do | Expect |
|---|---|---|---|
| A1 | Architect | Open `/migration-review` on a **Greenfield** project | "Migration Review is a Code Modernization agent", no chat |
| A2 | Architect | Open it on the Track 3 project | The intro, the legacy-code line, **Run Migration Review agent**. Left: **Migration reviews** and **Documents**. Centre: "How a migration gets reviewed" |
| A3 | Security Engineer | Open `/modernization-security` | The same frame; "How a module gets its security sign-off" |
| A4 | Developer | Ask the review agent to submit a review | "Only an Architect or a Project Admin of this project submits a migration review" |

## B. The review

| # | As | Do | Expect |
|---|---|---|---|
| B1 | Architect | "hi", then "review M-01" | It greets you, names M-01, the pull request and the design and plan versions. It reads the migration record v1 (accepted), the contract CT-01 and the traps TR-01, TR-02 |
| B2 | Architect | Let it work | It reads `claims-api/server.py` on BOTH sides, compares the API surface (only an encoding and an import change on CT-01; no route, status or SQL changed), scans for anti-patterns (1 carried over: the fraud-service host default; 2 fixed: the Python 2 imports) |
| B3 | Architect | Watch the submission | **Approve**, no findings, every contract / trap / criterion / legacy file answered; "Files read: 1 target, 1 legacy". If it first forgets a reason for CT-01 being unchanged, the submission is refused and it adds one |
| B4 | Architect (the one who ran it) | Click **Approve** on the version | Refused: you produced it |
| B5 | Second Architect or PA | Click **Approve** | The ledger panel: "Accepted and recorded. Waiting for Security." The Programme ledger shows review **approve**, M-01 still **in review** |

## C. A review that catches something (optional, needs a broken migration)

| # | As | Do | Expect |
|---|---|---|---|
| C1 | Developer | On a test project, have Migration Development leave `round(amount * rate, 2)` and change the 409 to 400, record, accept, push | — |
| C2 | Architect | Review it | **Request changes**: a high *trap unhandled* (TR-01) and a high *contract drift* (409 → 400), each citing the target line AND the legacy line; the API diff tab shows "removed status 409", "added status 400" |
| C3 | Second Architect | Accept it | M-01 goes back to **migrating** (rejected 1 of 3) |
| C4 | Architect | Accept an older review after the module was re-recorded | Refused: "the module has been migrated again since" |

## D. Security

| # | As | Do | Expect |
|---|---|---|---|
| D1 | Security Engineer | "hi", then "security-scan M-01" | It names M-01, the pull request and the legacy commit |
| D2 | Security Engineer | Let it scan | Trivy 0.58.1, Semgrep 1.99.0, Gitleaks 8.21.2 **ran** on the target, then on the legacy (a second legacy scan says "from the cache") |
| D3 | Security Engineer | Let it compare | 0 introduced; the bind-all-interfaces note carried over; no legacy secret in the target; CT-01 authorization "same" (no authentication on either side) |
| D4 | Security Engineer | Watch the submission | **PASS** (or **CONDITIONAL** if it lists the low finding, with a date inside wave W1). Never a secret's value anywhere on the page |
| D5 | Second Security Engineer or PA | Click **Approve** | With the review already approved: the ledger panel says "Both sign-offs are good"; M-01 is **verifying** |
| D6 | Anyone | On a machine without Trivy's database | The report page warns "Not scanned by trivy (not installed) … cannot be PASS"; SBOM "not generated", dependencies "not scanned" (never 0). A PASS submission is refused |

## E. Orchestrator

| # | As | Do | Expect |
|---|---|---|---|
| E1 | Architect | In the Orchestrator: "review the M-01 pull request" | It routes to Migration Review, which explains but says reviews are submitted on the Migration Review page |
| E2 | Security Engineer | "any vulnerabilities in M-01?" | It routes to Security |
| E3 | Anyone | "what's not built yet?" | Cutover and Cutover Pack |

When all of A, B, D and E pass, tell me and I flip the two tiles (`BUILT_AGENTS_BY_TRACK`), as for G and H.

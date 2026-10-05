# Click-through — Track 3 Phase H (Migration Development)

This is for you to run in a browser. The full chain ran for real at the test level (Postgres, Docker, git;
`tests/development_modernization/test_chain.py`) and live on this session's dev database, pushing to a LOCAL
target repository. It has not pushed to a real GitHub or Azure DevOps repository yet — that needs the target
repository and its credential below. Tick each step and note anything that differs.

**Before you start:**
- The dev database needs migration **0074** (`runs.migration_artifacts`, the deliverables check). Apply it with
  `cd backend && uv run python -m alembic upgrade head`, then `uv run python -m scripts.grant_app_role`, then
  restart the backend.
- **Docker must be running** on the backend's machine: builds, recipes and the preview run there.
- Phases E, F and G done on the project: an approved target design and plan, and an **accepted baseline**
  (Equivalence Testing) — accepting it is what makes the modules `baselined`.
- **A target repository**: create an EMPTY repository (for example `claimtrack-lite-target` on GitHub). As a
  Project Admin: Programme → Repositories → set it as the **target** (the legacy one stays the legacy); then
  Tools per stage → wire the GitHub connection to **Migration Development** with **write** access. The
  connection's token needs `contents: write` and `pull requests: write` on that repository only.
- Developers: `dev@gmail.com` drives; a SECOND Developer or `projadmin@gmail.com` accepts.
- The tile says **Coming soon** until this click-through passes (R42). Open the page by URL:
  `/projects/<id>/migration-development`.

## A. The page

| # | As | Do | Expect |
|---|---|---|---|
| A1 | Developer | Open `/migration-development` on a **Greenfield** project | "Migration Development is a Code Modernization agent", no chat |
| A2 | Developer | Open it on the Track 3 project | The intro, the legacy-code line (repository, commit), a **Workspaces** button, **Run Migration Development agent**. Left: **Migration records** and **Documents**. Centre: "How a module gets migrated" |
| A3 | QA or Architect | Ask the agent to start a module | "Only a Developer or a Project Admin of this project migrates a module" |

## B. Starting a module

| # | As | Do | Expect |
|---|---|---|---|
| B1 | Developer | "hi", then "migrate M-01" | It greets you, then shows M-01's plan: tier, pattern in-place upgrade, Python 2.7 → 3.12, the contract CT-01, the traps TR-01 (rounding) and TR-02 (bytes vs text), and that the baseline is ACCEPTED |
| B2 | Developer | On a project whose baseline is NOT accepted | It refuses: "the baseline must exist before the code changes, or nothing can prove the migration" |
| B3 | Developer | If the module's wave starts later | It says the date and starts only if you explicitly override the wave order |
| B4 | Developer | Let it open the workspace | Branch `migrate/claims-api` on the target. The first commit is the legacy module copied **unchanged**. On an empty target, `main` is started too. The ledger shows M-01 **migrating** |

## C. Migrating

| # | As | Do | Expect |
|---|---|---|---|
| C1 | Developer | Let it build first | **Round 1 of 5: RED** — `cannot import BaseHTTPServer` / `urllib2` on this runtime |
| C2 | Developer | Let it run the recipe | `lib2to3` (pinned to CPython 3.12.14) changes `claims-api/server.py`, committed as a **recipe** commit. Round 2: GREEN |
| C3 | Developer | Ask for the equivalence preview | It cannot start the module under the legacy (2.7) image: "its container is exited". The agent moves the build: a pinned 3.12 Dockerfile and runtime files, as a **build** commit |
| C4 | Developer | Preview again | "did not answer on /health … container is running": every request fails (TR-02 — the socket needs bytes) |
| C5 | Developer | Let it fix TR-02 only, then preview | claims-read identical; **settle: payout (2; `<number>` vs `<number>`)** — the two half-cent claims. No claimant, amount or id is shown |
| C6 | Developer | Let it fix TR-01 (the legacy rounding) | Round 5 GREEN; tests "not run (the module has no tests)"; lint GREEN; preview **11 cases identical after normalization** |
| C7 | Developer | Ask it to write a config file with `Password=…` in it, or to edit `settlement-batch/run.py` while on M-01 | Refused: a secret is never copied (use a vault reference); a file outside the module is never touched |
| C8 | Developer | Ask for a sixth build | "Five build rounds are used": record it (build_failed if red) |

## D. Recording, accepting, pushing

| # | As | Do | Expect |
|---|---|---|---|
| D1 | Developer | Ask it to record with a file left out of the map, or a trap not handled | NOT RECORDED, naming the missing file / trap |
| D2 | Developer | Let it record | **Migration record v1 (draft)** opens: ready for review, build green 5/5, tests not run, the preview line (a hint), Legacy → target (3 files), Traps 2/2 with where, Commits (copy, recipe, build, fix, fix) |
| D3 | Developer | Ask it to push now | "not accepted yet": another Developer or a Project Admin accepts it first |
| D4 | Developer (same) | Try to Approve v1 | Refused: you recorded it |
| D5 | Second Developer or Project Admin | Approve v1 | Accepted. The ledger panel: "the Developer pushes the branch … after confirming it" |
| D6 | Developer | "push it" | It shows the branch, the commits and the pull request title and body, and asks. Say **yes** |
| D7 | — | Look at the target repository | Branch `migrate/claims-api` with the commits by concern, and a pull request into `main` whose description lists the file map, the traps, the recipe and the preview. The LEGACY repository is unchanged |
| D8 | — | The page | The ledger: M-01 **in review**, with a link to the pull request. Workspaces: builds #1 red … #5 green, pushed |
| D9 | Project Admin | Set the stage's wiring to **read** only, record + accept again, push | NOT PUSHED — "has no write access to github" |

## E. A manual module

| # | As | Do | Expect |
|---|---|---|---|
| E1 | Developer | On a module the design marks **manual** | It does not migrate it; it records it as **blocked** with what a person must redesign; the ledger shows it blocked with that reason |

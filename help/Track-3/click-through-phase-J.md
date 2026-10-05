# Click-through — Track 3 Phase J (Equivalence Testing, Verify mode) and the workflow fixes

This is for you to run in a browser. Verify mode ran for real at the test level (Postgres, git and the Docker
sandbox; `tests/testing_modernization/test_verify_chain.py`). Tick each step and note anything that differs.

**Before you start:**
- No new migration (0075 is still the head). Restart the backend after pulling.
- **Docker must be running**: the verification runs the migrated module in the sandbox.
- A module **verifying** on the ledger: its migration accepted and pushed (Phase H), Review **approve** and
  Security **PASS / CONDITIONAL** accepted (Phase I). The accepted baseline from Phase G must still be in the
  baseline store.
- People: `qa@gmail.com` runs the verification; a SECOND QA or `projadmin@gmail.com` accepts it.

## A. The workflow fixes (Programme page and rework)

| # | As | Do | Expect |
|---|---|---|---|
| A1 | Anyone | Open **Programme** (`/projects/<id>/modernization`) | The module table has **Review**, **Security** and **Rejected** columns |
| A2 | Developer | Migrate two modules (M-01 and M-02), accept M-02's record first, then M-01's | Both accepted; M-01 can still be pushed (before the fix, accepting M-02 superseded M-01) |
| A3 | Developer | After a review asking for changes is accepted: "what did review find on M-01?" | The findings with file and line, unhandled traps, the rejection count (1 of 3) |
| A4 | Architect or PA | A module rejected three times shows under **Blocked** with **Unblock M-0x** | The dialog asks for a reason; **Send for rework** moves it to Migrating, rejections back to 0 |
| A5 | Developer | Try Unblock | "Only an Architect or a Project Admin of this project…" shown in the dialog |

## B. Verifying a module

| # | As | Do | Expect |
|---|---|---|---|
| B1 | QA | On Equivalence Testing: "verify M-01" | The plan: migration record (accepted), head, pull request, baseline v1; EC-01 / EC-02 with their scenarios and rules; EC-04 (p95 ≤ 250 ms) timed on `claims-read`. It asks before running |
| B2 | QA | Say yes | The module from the accepted head overlaid on the legacy system, run twice; a table: EC-01 passed (5), EC-02 passed (6), EC-04 legacy and target p95 in ms; "No difference" |
| B3 | QA | "record it" | A new version **verification**, module verdict *verified*. The baseline version stays **approved** |
| B4 | QA (the one who ran it) | Approve the verification version | Refused: you produced it |
| B5 | Second QA or PA | Approve | The ledger panel: "Accepted: the module is verified." Programme shows M-01 **Verified** |

## C. A verification that catches something (needs a broken migration on a test project)

| # | As | Do | Expect |
|---|---|---|---|
| C1 | Developer | Leave `round(amount * rate, 2)` in `payout()`; record, accept, push; Review and Security accept | M-01 verifying |
| C2 | QA | Verify M-01 | **EC-02 failed**: `settle:payout` differs in 2 cases, `<number> vs <number>`, likely *TR-01 claims-api/server.py payout()*. No claim id or amount anywhere |
| C3 | QA | "accept that difference" without an ADR | Refused: an accepted change needs an ADR on this module |
| C4 | QA, then a second QA | Record and accept | M-01 back to **Migrating**; the Developer's "what did review find" now lists the verification difference too |
| C5 | QA | Accept an older verification after the module was migrated again | Refused: "the module has been migrated again since" |

## D. Honesty checks

| # | As | Do | Expect |
|---|---|---|---|
| D1 | QA | Verify without naming a scenario for EC-04 | EC-04 **not run** (never passed), latency "not measured"; the module stays verifying (open) |
| D2 | QA | Ask to verify a module that is in review | "verified once Review approves it and Security signs it off (verifying)" |
| D3 | Developer | Ask Equivalence Testing to verify | "Only QA or a Project Admin…" |

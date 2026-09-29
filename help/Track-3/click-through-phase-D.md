# Click-through — Track 3 Phase D (what agents 1 and 2 hand to Target Architecture)

For you to run in a browser. As before, nothing here was verified in a browser by me. Every check was at
the test level: render tests and real-Postgres tests, with every guard mutation-proven (see
`build-log.md` Entry 10). Tick each step and note anything that differs.

**Before you start:**
- The dev database needs migrations 0068–0070 (see `click-through-phase-C.md`).
- Start both servers fresh.
- Phase D needs no new migration.

Personas are as in the earlier click-throughs. BA is `priya@abcbank.com` or `ba@gmail.com`.

## A. Migration Intent — "must not change", word for word

| # | As | Do | Expect |
|---|---|---|---|
| A1 | BA | Migration Intent → tell the agent the ClaimTrack story, including: *"the /api/v1 claims API brokers call and the BACS Standard 18 payment file must not change"* | It records both **in your words**. The brief's **Must not change** section lists them in quotes |
| A2 | BA | In a new chat, say only *"the API can't change"* | It asks **which** API and who uses it before recording. It does not record "the API" |
| A3 | BA | Ask it to record a must-not-change item you never said (e.g. "also add the reporting database") | The recording is refused ("not the user's own words"), and it asks you instead |
| A4 | BA | Give success measures, e.g. "payouts identical on replay", "p95 lookup under 800 ms" | The brief groups them under **Equivalence** and **Performance** |
| A5 | BA | Leave out any measurable success measure | It is **not recorded yet**. It says it cannot be handed to the next agents and asks for a measure |
| A6 | BA | Open the recorded version | A quiet line: **Ready to hand to Target Architecture** |
| A7 | BA | Open a brief recorded **before** today (an older version) | Measures show under **Not yet classified**. An amber box lists why it cannot be handed over (e.g. `success_measures.0.kind`) |
| A8 | BA | Download it as Word, then PDF | Both show **Must not change** (quoted) and each measure's kind |

## B. Dependency and Risk — ids, what it could not assess, the golden master

| # | As | Do | Expect |
|---|---|---|---|
| B1 | BA | Dependency and Risk → run the assessment on the pulled code | The module table has an **Id** column (M-01, M-02, …) |
| B2 | BA | Run it again on the same commit | The **same ids for the same modules**, even though the table is ordered by risk |
| B3 | BA | Scroll below the tabs | **Not assessable statically**: always the configuration question; the scheduler question for a batch/job module; a specific runtime question when a module declares an older Java than one of its libraries needs |
| B4 | BA | Look at the golden-master line | *"not captured yet — the Equivalence Testing agent records the legacy system's behaviour baseline"* |
| B5 | BA | In chat: "tell me about M-02" | It answers about that module (ids work as well as names) |

## C. Going back from the chat

| # | As | Do | Expect |
|---|---|---|---|
| C1 | BA | With two brief versions, say *"go back to version 1"* | It first shows what differs between v1 and the current version, then asks you to confirm |
| C2 | BA | Confirm, giving a reason | A **new** version (v3) appears as a draft: "Restored from v1 — your reason". It says someone else must approve it, and which later work (e.g. Dependency and Risk) goes out of date once it is approved |
| C3 | BA | Try the same inside an Orchestrator conversation | It says restoring is done on the agent's page |

## Known gaps

- Target Architecture (agent 3), which reads these packets, is the next phase (E). Until then, "Ready to
  hand to Target Architecture" is a validation result, not a hand-over that happened.
- If the conversation cannot be read, the word-for-word check is skipped, not failed. "Could not check"
  is not "not said", and the brief is recorded.

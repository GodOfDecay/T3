# Click-through — Track 3 Phase C (the backbone)

For you to run in a browser. Nothing below was verified in a browser by me: every check was at the
test level (render tests and real-Postgres tests, each guard mutation-proven). See `build-log.md`
Entries 7–8. Tick each step and note anything that differs.

## Before you start

1. **The dev database needs migrations 0068, 0069 and 0070** (it is at 0067). The backend's ORM now
   has their columns, so without them approving any version, and the new pages, fail. After you
   approve it:
   ```
   cd backend && uv run python -m alembic upgrade head
   ```
2. **Optional: the ClaimTrack fixture.** It puts a Code Modernization project with a roster,
   placeholder repositories and six ledger modules on the dev DB, so the Programme board has
   something to show without running agents 3–10 (which don't exist yet). It needs the dev personas
   (`python -m scripts.seed_dev_personas`) and binds those accounts. It creates none. It refuses a
   non-localhost database:
   ```
   cd backend && uv run python -m scripts.seed_track3_fixture
   ```
   Without it, use **Migration test** and the personas from the A/B click-through. The board will
   say "No modules yet" there, which is correct until Target Architecture exists.
3. Start both servers fresh, as in `click-through-phase-A-B.md`.

Personas below: **PA** = a Project Admin of the project, **PA2** = the other Project Admin
(fixture: `ana@abcbank.com`, `sofia@abcbank.com`), **BA** = `priya@abcbank.com` (or `ba@gmail.com`).

## A. Project Admin fallback on a sign-off

| # | As | Do | Expect |
|---|---|---|---|
| A1 | BA | Migration Intent → record a brief (as in the A/B click-through) | A draft version; you see "you can't approve it" |
| A2 | PA | Open that version → **Approve** | A dialog: **Approve … as Project Admin**. It asks for a reason and says it is recorded and listed in the Cutover Pack. **Approve as fallback** stays disabled until you type a reason |
| A3 | PA | Type "BA on leave" → Approve as fallback | Published. Badge **Approved by Project Admin (fallback)** and the line "Fallback reason: BA on leave" |
| A4 | BA (another BA, if you have one) | Approve a different BA draft | Approves straight away, with no dialog and no fallback badge |
| A5 | PA | Record something yourself (e.g. restore a version, section B), then try to approve it | Refused: you produced it |

## B. Restore, compare, out of date

| # | As | Do | Expect |
|---|---|---|---|
| B1 | BA | With two brief versions, open **v1** | **Restore this version** and **Compare with v…** (on v2) are shown. There is no Restore on the newest version |
| B2 | BA | Restore v1 → reason "v2 widened the scope" | A new draft (v3) opens: "Restored from v1 — v2 widened the scope". You cannot approve it yourself |
| B3 | anyone | On v2 → **Compare with v1** | "Changes from v1 to v2", listing changed fields as *before → after* |
| B4 | BA/PA | Approve a newer brief, then open the Dependency and Risk version built on the older one | Amber: **This assessment is out of date.** It says which input and version changed. A newer *draft* brief does **not** trigger this |

## C. Programme board and settings

| # | As | Do | Expect |
|---|---|---|---|
| C1 | any member | Open a Track 3 agent page | Under the intro, a strip such as "6 modules · Designed 1 · Sequenced 2 · Baselined 1 · Migrating 1 · 1 blocked · Programme". **Nothing** is shown when the ledger is empty |
| C2 | any member | Click **Programme** (or go to `/projects/<id>/modernization`) | Counts per state, a **Blocked** section (fixture: M-06 "…no captured outputs…"), the module table, and the legacy/target repositories |
| C3 | any member | `/projects/<greenfield id>/modernization` | "No Programme on this project" |
| C4 | PA | Settings → **Code Modernization** tab (Track 3 projects only) | Legacy and target repository forms, and **Sign-off fallback** with any staffing warnings |
| C5 | PA | Set the target to the same URL as the legacy one (with a trailing `/` or `.git`) | Refused: "the target repository cannot be the legacy repository…" |
| C6 | PA | Change **Policy** to Strict and **When a Project Admin may stand in** to "Only after … SLA" → Save | Saved. A2 is now refused until the stage's SLA has passed (48h by default) |
| C7 | PA of a **different** project | Same tab on this project | You can see it but cannot save (the backend says not found) |
| C8 | anyone | The Code Modernization tab on a Greenfield project | Not shown |

## D. SLA escalation and the PA floor

| # | As | Do | Expect |
|---|---|---|---|
| D1 | — | Leave a Track 3 draft for longer than its SLA (48h by default; the sweep runs every 15 min, set by `APPROVAL_SLA_SWEEP_INTERVAL_SECONDS`) | Each Project Admin of the project gets **one** bell item: "Requirements modernization vN has waited 48h for approval", linking to the agent page. It is never repeated for that version |
| D2 | PA | Project → Agents & Capabilities → add an override | The role list does not offer Project Admin. Through the API, lowering `project_admin` on a Track 3 agent returns 409 ("…fallback approver…") |

## Known gaps (by design at this point)
- Agents 3–10 are still **Coming soon**. The ledger moves only through their approvals, so outside
  the fixture the board stays empty.
- Multi-approver slots (the Cutover release sign-off) are enforced in `fallback_approval.decide`,
  but are only persisted with the Cutover agent (Phase K).

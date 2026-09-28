# Click-through — Track 3 Phases A and B

For you to run in a browser. Nothing below was verified in a browser by me: every check was
at the test level (unit, render and real-Postgres tests) — see `build-log.md` Entries 4–5.
Tick each step, and note anything that differs.

## Before you start

1. **Enable Windows long paths** (once; needs an *administrator* PowerShell), or every locally
   stored document fails to save — Track 1's too (the path is 325 characters):
   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
   ```
   Then close and reopen your terminals.
2. Docker Desktop running (`sdlc-redis` healthy). Local Postgres on 5432.
3. Start the backend and frontend **fresh** (R51):
   ```
   cd backend && uv run python -m uvicorn process_api:app --port 8001 --ws-max-size 1000000
   cd frontend && pnpm dev
   ```
   (`.env` and `frontend/.env.local` both say 8001.) `uv run uvicorn …` and `uv run alembic …`
   fail on this machine ("uv trampoline failed to canonicalize script path"); `python -m` works.
   Verified 2026-09-28: the backend boots against the dev DB at 0066 and `/health` answers 200.
   Expect two known warnings: no user holds security_engineer / devops_engineer, and the
   Langfuse database (Azure) is unreachable.

**Personas** (the ones that exist in this database): `ba@gmail.com` (BA),
`projadmin@gmail.com` (Project Admin), `architect@gmail.com`, `dev@gmail.com`,
`tester@gmail.com`. Project: **Migration test** (Code Modernization).

## A. A Track 3 project opens with Track 3's agents

| # | As | Do | Expect |
|---|---|---|---|
| A1 | projadmin | Open **Migration test** | Ten tiles in this order: Migration Intent, Dependency and Risk, Target Architecture, Migration Strategy, Equivalence Testing, Migration Development, Migration Review, Security (Modernization), Cutover, Cutover Pack. First two open; the other eight say **Coming soon** — none of them is a Track 1 agent (no "Design", "Development", "Code Review", "Deployment", "Documentation") |
| A2 | projadmin | Open project **Test** (Greenfield) | The Track 1 roster exactly as before |
| A3 | projadmin | Settings → Tools per stage on **Migration test** | The stage list is the ten Track 3 stages. (Connectors you wired earlier under Design/Testing/… no longer show — expected, see build log) |
| A4 | projadmin | Create a new project, choose **Code Modernization (Track 3)** | The track picker lists the ten Track 3 names; once approved, the project opens as in A1 |
| A5 | architect | Open Migration test | Target Architecture, Migration Strategy and Migration Review tiles are *yours* but still **Coming soon** |

## B. Migration Intent (BA)

| # | As | Do | Expect |
|---|---|---|---|
| B1 | ba | Open Migration Intent | Header shows a **Tech stack** chip ("No tech stack set" unless one is chosen in Agent Studio). Left rail: the versions list, then a **Documents** panel |
| B2 | ba | Documents → upload a small `.docx` (e.g. "ClaimTrack batch runbook") | It appears as **waiting for approval** with who uploaded it and when |
| B3 | projadmin | Approve that document (Documents panel or Requests & Approvals) | Approved, with approver and time |
| B4 | ba | Run Migration Intent → "Hi" | Greeting; says what it found in the code (or offers to pull it); mentions the approved runbook exists or cites it when relevant |
| B5 | ba | (Optional) Agent Studio → choose a tech stack for the project → back, ask it to recommend a target | It says the approved stack and its source first, and names any departure with a reason |
| B6 | ba | Give it the ClaimTrack story (demo doc Prompt 1), then "Looks good, record the brief" | A new brief version opens; its **Recommended target stack** section has an **Approved tech stack:** line (the stack and source, or "none — recommended freely") |
| B7 | ba | Open that version | Amber note: *"You produced this brief, so you can't approve it — a Business Analyst who didn't produce it, or a Project Admin, approves or rejects it. The one who produced a version decides it neither way."* **No** Approve and **no** Reject button (corrected in Phase C: the backend refuses a producer's reject too) |
| B8 | ba | In chat: "send the brief for approval" (after exporting it as Word) | It raises the document (never says it approved it); the doc shows as waiting for approval |
| B9 | projadmin | Open the brief version → **Approve** | Published; "Read by: No agent has built on this brief yet." |

## C. Dependency and Risk reads the published brief — and it is recorded

| # | As | Do | Expect |
|---|---|---|---|
| C1 | ba | Open Dependency and Risk | Documents panel for **this** stage; **no** tech-stack chip |
| C2 | ba | Run it → "Assess the legacy code that is already pulled" (needs pulled code) | Report; if Trivy is not installed the summary says *"known vulnerabilities **not scanned** (Trivy: unavailable)"* — **never "0 known vulnerabilities"** |
| C3 | ba | Back to Migration Intent → open the published brief | **Read by: Dependency and Risk**, with the time |
| C4 | projadmin | Project settings → turn on *enforce artifact publication*; record a NEW brief (draft) as ba; ask Dependency and Risk anything | It works from the **published** brief only; with none published it says the brief must be approved first (it does not quietly use the draft) |

## D. The Orchestrator

| # | As | Do | Expect |
|---|---|---|---|
| D1 | projadmin | Orchestrator on Migration test → "what can you do?" | Names the ten Track 3 agents in hand-off order, with Equivalence Testing (baseline) **before** Migration Development, and says which are not built yet |
| D2 | projadmin | "Run the target architecture agent" | Says plainly it is not available yet for Code Modernization; does not send it to another agent |

## E. What to tell me

For each step: ✔, or what you saw instead (a screenshot helps). Specifically note any error
toast, any page that shows a Track 1 agent on the Track 3 project, and whether B7's
explanation reads clearly.

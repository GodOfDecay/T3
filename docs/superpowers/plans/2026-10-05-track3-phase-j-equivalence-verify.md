# Track 3 Phase J — Equivalence Testing, Verify mode (agent 5, second mode)

Research §6.5 (Verify mode), master plan row J. Evidence and decisions go to `help/Track-3/build-log.md`
Entry 16. Built on Phase I and the workflow review that preceded J (per-module approvals, rework findings,
unblock/reopen). Owner: QA. Gate: "accept the equivalence results" (mandatory, per module); running the
target is Consequential.

## The use case

ClaimTrack Lite M-01 `claims-api` has Review `approve` and Security `PASS`: the ledger has it `verifying`.
QA replays the ACCEPTED baseline's scenarios on the migrated module, twice, and the tools compare each
criterion: EC-01 claim reads and EC-02 settlement payouts (exact, after their own normalization), and EC-04
p95 of claim reads (≤ 250 ms, measured on both sides under the same load). A faithful migration is
`verified`; one with the rounding trap left in fails EC-02 with `payout` in 2 cases and goes back to
`migrating`, the finding visible to Migration Development.

## Decisions

- J1. **One agent, two modes, one stage.** A verification is a `testing_modernization` version with
  `mode: "verify"`, one version = one module. Versions are approved PER SUBJECT (the workflow review's
  fix): the baseline and each module's verification never supersede one another, and every reader of the
  stage that names no subject reads the BASELINE.
- J2. **What is verified** is the module's newest ACCEPTED migration record (the head Review and Security
  signed off), while the ledger has it `verifying`; its target code is the read-only checkout of Phase I
  (`review_checkout`, stage `testing_modernization`, `read` on the target).
- J3. **The system under test** is Phase H's overlay — the legacy checkout with the module and the root
  shared build files from that head — run with the SAME capture profile and harness as the baseline,
  TWICE (`runs: 2`). The accepted baseline's run 1 is the reference.
- J4. **diff_outputs is deterministic** and applies ONLY each criterion's own normalization rules. Every
  remaining differing field is classified by the tool: in the legacy's noise floor → `normalization_gap`
  (a rule proposal for Migration Strategy); differs in one target run and not the other → `environment`;
  otherwise `regression`. The agent may only re-classify a regression as `accepted_change`, citing an ADR
  that is on the module in the approved design.
- J5. **Verdicts are computed, never stated**: per criterion `passed` (compared, nothing left),
  `failed` (a regression), `open` (a normalization gap, an environment difference), `not_run` (no scenario,
  or not measured); the module verdict is the packet's (`verified` / `migrating` / `open`).
- J6. **Performance**: a `percentile_threshold` criterion is measured on both sides — the legacy image and
  the overlay — with the same requests, repetitions and container limits (driver `perf` mode: latencies
  only, no bodies). Not measured stays `not_run`, never 0 (R39).
- J7. **Masked shapes only**: no recorded value reaches the model or the page (the baseline's rule).
- J8. **Ledger on ACCEPTANCE** (QA who did not record it, or a Project Admin): `equivalence_recorded` with
  the module verdict; refused when the module was migrated again since (the record version and head).
- J9. **Rework sees it**: Migration Development's `read_review_findings` lists the verification's
  differences too.
- J10. **The page** shows a verification version per module: criteria verdicts, differences (field,
  cases, masked example, likely area), performance both sides, the runs; what accepting records.

## Build order
1. Driver perf mode; `analysis/verify.py` (diff, classify, verdicts, perf); the tools (plan, run, record).
2. Prompt (verify section), acceptance hook branch, rework list, routes.
3. Tests: pure; Docker (faithful = verified, broken = regression caught, legacy-on-itself = zero
   differences, same replay twice = same verdict); Postgres chain to the ledger.
4. Frontend verify view on `/equivalence-testing`.
5. Mutation, regression, build log, click-through, handoff.

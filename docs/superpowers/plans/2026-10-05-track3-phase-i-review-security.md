# Track 3 Phase I — Migration Review (agent 7) and Security (agent 8)

Research §6.7 and §6.8, master plan row I. Evidence and decisions go to `help/Track-3/build-log.md`
Entry 15. Built on Phase H (`eac87bb`). Both agents run on the pull request Phase H opened, in either
order (`can_parallel_with` each other). Owners: Migration Review = Architect (gate "accept the migration
review"); Security = Security Engineer (mandatory sign-off).

## The use case

ClaimTrack Lite M-01 `claims-api` is `in_review` with a pull request on the target. The review reads it
side by side with the legacy code: are CT-01 (the claims HTTP API) and the rounding trap TR-01 kept? The
security agent scans the migrated module AND the legacy module with the same pinned scanners and says,
for every finding, whether the migration carried it over, fixed it or introduced it. Both verdicts on
the ledger move the module to `verifying` (both good) or back to `migrating` (either bad; blocked after
three rejections).

## Decisions

- I1. **One read-only review checkout per stage, module and head**: `files/review-checkouts/<project>/
  <stage>/<module>/<sha>/`, a clone of the TARGET at the head the ACCEPTED migration record names (what
  was accepted is what is reviewed), push URL disabled. Allowed only when `repository_roles.repo_access(
  stage, "target") == "read"`; the credential is the connection wired to THIS stage (H's `remote`, the
  stage named in its errors). The legacy side is the stage's legacy pull, as everywhere.
- I2. **What is reviewed** is the module's newest ACCEPTED migration record (`ready_for_review`) while
  the ledger has the module `in_review`. A module with no record is refused (research: "review the diff
  alone" is not offered: without the record there is no head that was accepted).
- I3. **compare_api_surface is deterministic**: Phase E's `capture_interfaces` on the legacy module and
  on the target module, plus a small surface reader for what it does not see (public functions with
  their parameters, routes matched on `self.path`, HTTP status codes, SQL statements, file writers and
  their encodings). Each difference names the frozen contract whose location it falls in.
- I4. **detect_legacy_antipatterns is a built-in rule pack** (string-built SQL, swallowed exceptions,
  Python 2 idioms, hard-coded hosts and credentials, static mutable state, Log4j 1, SimpleDateFormat,
  AngularJS `$scope`), run on both sides; each hit is classified by the file map and a normalized-line
  fingerprint: carried_over or introduced. Pure Python, so it runs where Docker does not.
- I5. **files_read is recorded by the tools**, not stated: the submit tool refuses a `files_read` entry
  the run did not open and a finding citing a file not opened.
- I6. **Review submit checks** beyond the packet's own rules: every frozen contract of the module in
  `contract_check`, every trap in `trap_check`, every legacy file of the record's file map in
  `traceability`, every module criterion in `equivalence_coverage`; a contract the API diff shows
  changed cannot be `unchanged`.
- I7. **Scanners are digest-pinned Docker images, offline** (`--network none`, `runner.limits()`, the
  checkout read-only): Trivy (SCA + CycloneDX SBOM, its vulnerability DB a read-only mount refreshed by
  a separate step), Semgrep (the platform's local rule file, `--metrics=off`), Gitleaks. A scanner that
  cannot run is `not_installed` / `failed`, never "clean" (R39), so the sign-off cannot be PASS.
- I8. **scan_legacy_baseline** runs the same three on the legacy module, cached per legacy commit (the
  cache says when it was used). **diff_findings** is deterministic: CVE + package; rule + file (through
  the file map) + normalized line; secret hash. **check_secret_carryover** hashes every legacy secret
  value and looks for it in the target: values are never shown, only the files.
- I9. **check_contract_authz** reads the auth markers (decorators, Authorization/API-key checks, role
  checks) on each frozen HTTP contract's code on both sides and reports same / stricter / weaker /
  none-found with the lines; the agent states the status, and `weaker` is a high finding by the packet's
  policy.
- I10. **Security submit**: the scans, SBOM counts and the target's critical/high hits come from the
  tools' state, never from the model's words; every critical/high target hit must appear as a finding
  (by CVE, secret file or rule + file), and its origin must match `diff_findings`. The packet computes
  the Track 3 policy verdict (FAIL / CONDITIONAL / PASS; PASS impossible with a scanner not run).
- I11. **Ledger verdicts on acceptance**, not on submit (like G's baseline): accepting a review version
  writes `review_submitted`, accepting a security version `security_submitted`, in the same transaction
  (a ledger refusal rolls the acceptance back). The producer cannot accept their own version (existing
  rule). A version for a head other than the PR's current record is refused at acceptance.
- I12. **Track 1 stays untouched.** The Track 3 security prompt is standalone: Track 1's body tells the
  agent to fall back to AI analysis when scanners are missing and has a different payload, both of which
  contradict Track 3's policy. A byte-identity test pins Track 1's prompt (master plan §5).

## Build order
1. Shared review checkout; review analysis (surface, antipatterns); scanners + diff + carryover + authz.
2. Both agents: tools, prompts, graphs, sockets; registry, orchestrator2, migration 0075, routes, hooks.
3. Tests: pure, Docker scanners on ClaimTrack, Postgres chain on Phase H's PR, rework loop.
4. Frontend `/migration-review`, `/modernization-security`.
5. Mutation, regression, build log, click-through, handoff.

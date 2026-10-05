# Track 3 Phase H — Migration Development (agent 6)

Research §6.6, master plan row H. Evidence and decisions go to `help/Track-3/build-log.md` Entry 14.
Built on Phase G (`Phase-G` / `140ae0b`). Owner: Developer (D10). Gate: "accept the migrated module"
(sign-off); pushing and opening the pull request is a separate Consequential action.

## The use case

ClaimTrack Lite (`samples/legacy-claimtrack`): Python 2.7 → Python 3.12, one module at a time, into a
TARGET repository the platform writes and the legacy repository is never written. M-01 `claims-api`
holds the rounding trap (Python 2 `round()` rounds halves away from zero; Python 3 to even: CLM-0004
and CLM-0007 pay a cent differently). M-02 `settlement-batch` writes a cp1252 fixed-width bank file.
Phase G's accepted baseline is what the migrated module is previewed against.

## Decisions

- H1. **Workspace** per project and module: `files/migration-workspaces/<project>/<module>/repo`, a clone
  of the project's TARGET repository (credential: the connection wired to THIS stage), on branch
  `migrate/<legacy path>`. An empty target repository is supported (first commit creates the base branch).
- H2. **In-place upgrade copies the legacy module in as the FIRST commit**, unchanged, so the recipe diff
  is reviewable on its own (research §6.6).
- H3. **Commits by concern**, written by the tools, never by the model: `copy`, `recipe`, `build`, `fix`.
  A commit that mixes build files (Dockerfile, requirements, pyproject, CI…) with code is refused.
- H4. **Where the agent may write**: the module's path in the target, and the repository's shared build
  files (root Dockerfile, CI definitions). Anything else is refused at the write, and the record tool
  re-checks the whole branch diff.
- H5. **Toolchains are data** (`toolchains.py`): per ecosystem a digest-pinned image, the build / test /
  lint commands and the upgrade recipes, each pinned (Python: `lib2to3` of CPython 3.12 in the pinned
  image). Every command runs in a Docker container: no network, no capabilities, bounded resources, the
  workspace mounted. Ecosystems with no catalogued toolchain say so; nothing is claimed.
- H6. **The build-and-fix loop is capped at 5 rounds**, counted by the tool. After the fifth red build
  the module can only be recorded as `build_failed`. Build/test/lint results come from the tool's own
  state, never from the model's words.
- H7. **Secrets**: a write whose content looks like a credential (private key, password= with a value,
  a connection string with a password, cloud keys) is refused; the agent uses a vault reference instead.
- H8. **preview_equivalence**: the legacy checkout with the module (and shared build files) replaced
  by the workspace's, run ONCE in the Phase G sandbox, compared with the ACCEPTED baseline's run 1 for
  the module's criteria, ignoring the legacy's own noise floor and the criterion's normalization fields.
  Masked shapes only. A hint, never a verdict.
- H9. **record_module_migration** validates the packet, that the file map covers EVERY legacy file of
  the module, that the branch diff stays in bounds, and takes recipes / build state from the workspace.
  Frozen as the next version of the stage (one version = one module's record).
- H10. **Ledger**: `baselined → migrating` when the workspace is opened; `migrating → in_review` when
  the pull request is opened (with the record version). A module whose baseline is not accepted is
  refused. A manual-tier module is blocked with the hand-off note, no code written.
- H11. **Push** (Consequential): Developer or Project Admin OF THIS PROJECT, this turn's consent,
  `repository_roles.assert_target_write` (the first caller), the newest record for the module ACCEPTED
  (4-eyes before anything leaves the platform) and the branch exactly as recorded. Never a force push;
  a revert is a new commit. PR body generated from the record. Audited.
- H12. **Local development remote**: with `ENV=dev|test` only, `SDLC_TARGET_REMOTE_MAP` maps a target
  URL to a local bare repository (pull requests recorded beside it). Never honoured in production.

## Build order
1. Toolchains + workspace (git) + path/secret rules + sandboxed command runner.
2. Tools, prompt, graph, socket; registry, orchestrator2, migration 0074, context broker, routes.
3. Tests: pure, Docker (recipe, build, rounds), Postgres chain to a local bare remote.
4. Frontend `/migration-development` (records, file map, build, recipes, traps, PR, ledger).
5. Mutation, regression, live run, build log, click-through, handoff.

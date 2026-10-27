---
status: canonical
sources:
  - nexus.toml
  - CLAUDE.md
  - pytest.ini
verified_commit: "b75f6241cf98aff251b100b776d50f3003c872cb"
---

# 0076: The Offline Merge Gate

**Kind:** decision
**Links:** #816, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/816#issuecomment-6423096474.

> - **816-D1.** What are the check name, triggers and interpreter set of the offline CI workflow that becomes the required status check? Decision: Workflow `.github/workflows/offline-tests.yml`, job and check name `offline-tests`, on push to main and pull_request to main, no path filter, timeout 60 minutes, running the two offline suites (`tests --ignore=tests/test_api --ignore=tests/test_orrery`, then `tests/test_api tests/test_orrery`) with `NEXUS_RUN_POSTGRES` unset and `-m 'not requires_local_models'`. A second job `ui-tests` runs `npm --prefix ui ci` and `npm --prefix ui test` (with Git LFS fetched for the receipt) and reports but is not required. Basis: Ruling 43 816-Q1 plus critique items on timeout and the UI suite. Reversal cost: Edit the workflow.
> - **816-D2.** Is enforcement done through the existing repository ruleset or through classic branch protection, and with which bypass actors? Decision: Enforcement (816-S3, coordinator-only after a green run on main) extends the existing ruleset `main` (id 12230861) with pull_request (0 approvals, required_review_thread_resolution false) and required_status_checks [`offline-tests`], strict false, bypass_actors empty. Basis: Ruling 43 block_all; the owner's note "choose for me". Reversal cost: One ruleset edit.
> - **816-D3.** Is the required check strict, so that a branch must be up to date with main before it merges? Decision: Not strict (no up-to-date requirement). Basis: Map default. Reversal cost: Trivial.
> - **816-D4.** In which order do the workflow and the ruleset change land? Decision: S2 lands first; S3 only after `offline-tests` is green on a push to main. Basis: Map default. Reversal cost: None.
> - **816-D5.** What happens to offline tests that fail only on Linux CI? Decision: Tests that fail only on Linux CI are made portable; a skip is allowed only for genuinely Darwin-only behavior. Basis: Map default. Reversal cost: None.
> - **816-D6.** What are the unit, value and home of the live-tier per-run spend cap that ruling 43 left to the coordinator? Decision: The live-tier per-run cap is a `nexus.toml` tunable `[runtime.live_tier] max_frontier_calls` (default 60, about twice the 2026-06 measurement, enforced before each turn) and belongs to 816-S5 (later); the coordinator records the measured cost on #816 after the first run. Basis: CLAUDE.md: tunables in nexus.toml; critique objections on D6/D7. Reversal cost: Edit the tunable.
> - **816-D10.** What are the name and semantics of the model-dependent marker from Decision 816-Q7? Decision: Marker `requires_local_models`, registered in `pytest.ini`, applied to PostgreSQL and offline tests that load a production local embedding or reranker artifact; excluded only by CI `-m` expressions; no local skip. Basis: Decision 816-Q7. Reversal cost: Trivial.
> - **816-D11.** Is the CI PostgreSQL step a required status check? Decision: The CI PostgreSQL step (816-S4b, later with #810-S5) is not a required check. Basis: Map default. Reversal cost: Trivial.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.

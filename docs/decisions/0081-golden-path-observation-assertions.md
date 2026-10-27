---
status: canonical
sources:
  - tests/test_golden_path_live.py
  - nexus/api/backstage_endpoints.py
verified_commit: "d295eef0928706cda3a9f7c5a8b4dc103929e1ed"
---

# 0081: Golden-Path Observation Assertions

**Kind:** decision
**Links:** #802, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/802#issuecomment-6423123761.

> - **802-D6.** In Backstage, should a pending incubator turn whose session has no generation-session row read as unavailable with an explanation, or should the read refuse (the 2026-10-14 owner question, UI-B item 5)? Decision: A pending incubator turn whose session_id has no narrative_generation_sessions row reads as 'unavailable' with its detail string in Backstage, as the code does now. Basis: The explicit pending analogue of 802-Q1; reproduced on the fleet. Reversal cost: Trivial.
> - **802-D7.** How strict should the golden-path observation assertions be about background job usage? Decision: Background assertions: after a settle loop extended to every PROVIDER_JOB_SEATS queue, jobs_open == 0; every terminal job that made a provider call has ledger usage; jobs that ended without a call are listed by queue and state in the evidence, not failed. Basis: Critique objection: provider-backed queues end without a call by design. Reversal cost: Test-only.
> - **802-D8.** Should the golden-path proof read the observation in process or through the dev-gated HTTP Backstage endpoint? Decision: The observation is read in process through the same public functions the CLI and the Backstage endpoint call; the dev dashboard stays off. Basis: Ship-off invariant. Reversal cost: Test-only.
> - **802-D9.** Which usage ledger should the golden-path gateway child write and the in-process stage test read, given that pytest points the in-process recorder at a temporary directory? Decision: The golden-path run gets its own absolute usage.usage_dir in the temporary runtime config written on every run (not only with a model override), inherited by the child through NEXUS_RUNTIME_CONFIG; the stage test reads the same recorder config. Basis: Critique item 1; keeps clone job events out of the owner's ledger. Reversal cost: Test-only.
> - **802-D10.** How strict should the critical-path usage assertion be, given that a real-provider retry can create an attempt that received no response? Decision: Critical-path assertion: every attempt whose provider_outcome shows a response has ledger usage with integer tokens; attempts_without_usage equals the number of attempts with no response. Basis: Critique item 4. Reversal cost: Test-only.
> - **802-D11.** Who runs the paid golden-path gate, where, and under what limit? Decision: The builder runs the paid golden-path gate once on this Mac (cap 40 frontier calls, NEXUS_RUN_LIVE_LLM=1 NEXUS_RUN_POSTGRES=1 NEXUS_GOLDEN_PATH_E2E=1, on a free lane) and records exact usage; this is the paid tier under ruling 43 on #816. Basis: The issue's close condition. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.

# Trait Derivation Wait Tests: Source Checkpoint

The original tests-first checkpoint contains tests and evidence only. Its product baseline is
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. Actual initial Python and UI red results on this unchanged product are now recorded below. No green, type check, build, browser capture or fleet survey has run for this order. The original tests-first source checkpoint remains immutable. No push or PR is authorized at this stage.

The frozen order is `temp/orders_2026_10_07/776-S6.md` in the primary checkout.
The coordinator scheduled this tests-first preparation before the preceding
lanes land. That scheduling does not waive their later normal merges or any
proof gate.

## Tests Authored

- `test_genesis_ledger_pg.py` adds the required running and skipped derivation
  proofs, retains derivation in the full projected stage list, and requires its
  failure detail and trailing failure record. The stage-less refusal remains
  idle. These use the existing migrated disposable fixture and its existing
  provider-boundary substitutions; the new running case releases and joins its
  held thread in `finally`.
- `test_cli.py` names running and failed derivation in two parameterized cases.
- `narrative-api.retrograde.test.ts` adds all seven ledger-derived skip cases
  and the failed-derivation parser case. Its Python/TypeScript vocabulary
  parity assertion is unchanged.
- `InteractiveWizard.transition.test.tsx` now supplies actual stage-history
  shapes, including terminal records, and pins seven displayed pips. It covers
  derivation running/failure, derivation disabled, skipped Retrograde with and
  without derivation both after the answer and on reattach, and a successful
  answer disagreeing with an unfinished or differently skipped ledger record.
  Successful transition fixtures expose their settled done record before
  answering. Existing cancellation, retry, previous-run and strangeness
  assertions remain.

## Stage Count Clarification

The frozen sentence “the seven stages plus bootstrap” conflicts with the same
order's seven-pip requirement. The exact intended arrays resolve it without
adding a stage: the Python tuple has **seven names including terminal `done`**;
the TypeScript pipeline has **six stages** (`derivation`, `packet`,
`seed_candidates`, `expansion`, `persistence`, `embedding`); and the display has
**seven pips**, those six followed by `bootstrap`. A skipped run with derivation
therefore has one done pip, five skipped pips and active bootstrap. A TEST skip
has six skipped pips and active bootstrap. Tests assert these complete arrays.

## Initial Red Plan: Not Executed

The exact selectors are also retained in `initial-red-selectors.json`. Run
only after the coordinator grants the sole heavy slot. First verify the
committed head, clean tree, unchanged product boundary and worktree import
path. Use the shared `/Users/pythagor/nexus/.venv/bin/python`, exact worktree
`PYTHONPATH`, `nice -n 15`, load at most 24, bounded process-group deadlines
and private test artifacts. Clear inherited `NEXUS_*`, `PG*`, `PYTEST_*`,
`PYTHONPATH` and `PYTHONHOME` overrides, then explicitly set the required test
flags and private receipt locations; keep live, corpus and secret-store
opt-ins unset. No gateway, API URL or slot override may leak into pytest.

From this worktree, the planned Python session is:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH="$PWD" nice -n 15 "$PY" -m pytest -q \
  -p tests.dbname_audit \
  tests/test_api/test_genesis_ledger_pg.py::test_stage_rows_and_outputs_persist \
  'tests/test_api/test_genesis_ledger_pg.py::test_failure_is_recorded_at_each_stage[derivation]' \
  tests/test_api/test_genesis_ledger_pg.py::test_running_derivation_reports_its_stage \
  tests/test_api/test_genesis_ledger_pg.py::test_skipped_retrograde_keeps_its_derivation_record \
  'tests/test_api/test_genesis_ledger_pg.py::test_failure_is_recorded_at_each_stage[None]' \
  tests/test_cli.py::test_retrograde_status_stage_names_derivation
```

Source inspection predicts six assertion/refusal failures and one stage-less
parity pass; these are expectations, **not measured results**. Inspect every
failure reason and retain the complete secret-store, receipt and database
audit summaries. A collection, dependency, connection or guard failure is not
the required red proof.

After the separately admitted local `npm --prefix ui ci`, the planned UI red
session is:

```sh
nice -n 15 npm --prefix ui test -- \
  client/src/lib/narrative-api.retrograde.test.ts \
  client/src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx
```

The absent skip helper, rejected derivation vocabulary, old six-pip track and
missing settled-record check should be exposed. Retain actual test names and
failure reasons; do not report a predicted UI result count as observed.

## Source Boundary and Remaining Proof

`tests-first-source-boundary.json` records SHA-256 equality with the baseline
for the affected production files, `nexus.toml`, the design preview, and both
`WaitScreen.tsx` and `WaitScreen.test.tsx`. All production files remain
unchanged; only the four test files and this evidence directory are in scope.
Black ran on the two changed Python test files and left both unchanged.
Normal commit hooks are part of the source checkpoint, not behavioral proof.

After red is recorded, the ordered implementation, focused PostgreSQL union,
CLI proof, static comparisons, exception check, canonical closure and freshness
checks remain due. Preserve 776-S1b's new stage-output/fingerprint tests and
reused derivation rows when normally merging that predecessor. Its current
source checkpoint records reused derivation in the reported run; this branch
has not merged it or claimed runtime verification of it.

Final UI validation must use the then-current 777 → 809 → 824 baseline and
regenerate the state-surface receipt before the full UI run. No measured
surface change is intended. The coordinator owns combined full PostgreSQL
coverage; no standalone whole-suite or offline gate has run here. Fleet counts
from October 7 are historical, not a current survey. No owner database,
service, credential, model or paid provider was used by this preparation.

At eventual landing: no migration or fleet application, unchanged
`nexus.toml`, owner UI rebuild due, and new Python must be used at the next
authorized gateway startup. Services stay stopped until separately authorized.

Codex — GPT-6

## Actual initial red admission

At clean tests-only `6111594741bf2006c9c706afe09b4861b29dc1d7`, the exact worktree import was admitted and Python reported **6 failed, 1 passed, 5 warnings in 11.47s**, with all three isolation guards present. All failures are the intended hidden derivation stage or rejected CLI vocabulary; the stage-less refusal parity passed. The ordinary template reads by clone tooling and unaudited C connection class remain the stated audit limits.

Local `npm --prefix ui ci` succeeded without changing the lock (SHA-256 in `initial-ui-red/results.json`). The two requested Vitest files reported **39 failed, 43 passed in 25.51s**. Failures expose the absent skip helper, rejected derivation failure, six-pip track and missing settled-record disagreement guard, rather than dependency or collection errors. Product, generic WaitScreen and preview code stayed at the tests-first base throughout both runs. Source implementation is now admitted; no passing feature claim is made.

Codex — GPT-6

## Implementation source checkpoint

After actual initial red admission, the source adds derivation to the shared vocabulary and status projection, computes skipped pips from recorded ledger stages, applies full status updates before settlement, and checks the terminal ledger against the successful response before bootstrap. Cancel, Retry, the generic WaitScreen and its test remain unchanged. The design preview changes only its stage-position comment.

Independent source review found no blocker across all six implementation files. Black left the two Python source files unchanged. Decisions0016 and0017 remain parked; their source spec edit only exposes an already-recorded stage. The turn-flow body does not describe the wait screen and needs no prose change. These three canonical stamps name the actual merge base4ae8b8d2; later main merges must reverify them and retain812s boot paragraph.

Green execution, static-baseline comparisons, owner read-only ledger survey, final predecessor merges and state-surface/fullUI acceptance remain pending. S1b source95a45ca1 now records a reused derivation in its reported run; this branch has not yet merged or validated that predecessor. The poll still skips its pre-post run identity as ordered; S1b owns any reconciliation, and this change adds no same-run rejection to the settled read.

Codex — GPT-6

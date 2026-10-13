# Trait Derivation Wait Tests: Source Checkpoint

The original tests-first checkpoint contains tests and evidence only. Its product baseline is
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The initial Python and UI red results on this unchanged product are recorded below. The sections up to "Implementation Source Checkpoint" are the lane author's record on the lane source and are kept as written, except for retitled headings and corrected claims. The green proof on the integrated wave-B tree (focused PostgreSQL set, offline suites, front-matter and reachability, vitest, UI check and build, static comparisons, the exception-disposition check and the read-only fleet survey) is in "Integrated-Tree Proof (2026-10-13)" at the end. The state-surface regeneration, the full `npm --prefix ui test` and the whole-tree gate are the coordinator's steps.

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

## Initial Red Plan

This plan was executed; its results are in "Actual Initial Red Admission" below.

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
The lane author stated that Black left the two changed Python test files
unchanged; no Black output was recorded for that run. The 2026-10-13 Black run
below covers all four changed Python files. Normal commit hooks are part of the source checkpoint, not behavioral proof.

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

## Actual Initial Red Admission

At clean tests-only `6111594741bf2006c9c706afe09b4861b29dc1d7`, the exact worktree import was admitted and Python reported **6 failed, 1 passed, 5 warnings in 11.47s**, with all three isolation guards present. All failures are the intended hidden derivation stage or rejected CLI vocabulary; the stage-less refusal parity passed. The ordinary template reads by clone tooling and unaudited C connection class remain the stated audit limits.

Local `npm --prefix ui ci` succeeded without changing the lock (SHA-256 in `initial-ui-red/results.json`). The two requested Vitest files reported **39 failed, 43 passed in 25.51s**. Failures expose the absent skip helper, rejected derivation failure, six-pip track and missing settled-record disagreement guard, rather than dependency or collection errors. Product, generic WaitScreen and preview code stayed at the tests-first base throughout both runs. Source implementation is now admitted; no passing feature claim is made.

Codex — GPT-6

## Implementation Source Checkpoint

After actual initial red admission, the source adds derivation to the shared vocabulary and status projection, computes skipped pips from recorded ledger stages, applies full status updates before settlement, and checks the terminal ledger against the successful response before bootstrap. Cancel, Retry, the generic WaitScreen and its test remain unchanged. The design preview changes only its stage-position comment.

The lane author stated that an independent source review found no blocker across the six implementation files and that Black left the two Python source files unchanged; neither a review record nor Black output is in this directory. The assembly's source review (`docs/qa/wave-b-source-assembly-2026-10-09/independent-source-review.md`) covers the S1b/S6 merge, including the restored `derivation -> packet -> seed_candidates` spec line, and the 2026-10-13 Black run below covers both files. Decisions 0016 and 0017 remain parked; their source spec edit only exposes an already-recorded stage. The turn-flow body does not describe the wait screen and needs no prose change. On the lane source these three canonical stamps named the merge base 4ae8b8d2; the wave-B assembly (894d8c88) moved all three to f073b371, which the integrated tree carries, and later main merges must reverify them and retain 812's boot paragraph.

At this checkpoint green execution, the static-baseline comparisons, the read-only ledger survey, the predecessor merges and the state-surface and full UI acceptance were pending; the integrated-tree section below records all but the coordinator's steps. S1b (source 95a45ca1) is now merged into the integrated tree, and its resume path records a reused derivation row in the reported run: `_reuse_genesis_stage` (`nexus/api/new_story_flow.py:459-471`) calls `record_retrograde_progress` and `record_genesis_stage_output` for the new run, and `reuse("derivation")` (`:609`) applies it to a saved derivation output. The poll still skips its pre-post run identity as ordered; S1b owns any reconciliation, and this change adds no same-run rejection to the settled read.

Codex — GPT-6

## Integrated-Tree Proof (2026-10-13)

Fixer: Claude Opus 5.5 on branch `claude/waveb-fix-776-s6`, cut from the
integration head `a563203a` (origin/main `f073b371` plus the wave-B lanes and
nine lane fixes, including 776-S1b). One fix commit preceded the runs:
`6e9629ae` rewords the `RetrogradeStatus` comment
(`ui/client/src/lib/narrative-api.ts:318-323`) so that "idle" also covers a run
that skipped Retrograde and keeps its derivation record. Every proof below ran
at `6e9629ae`; the commit that adds this section changes only this file. The
import check printed
`/Users/pythagor/nexus/.claude/worktrees/fix-776-s6/nexus/__init__.py`. Every
command ran from the worktree root with `PY=/Users/pythagor/nexus/.venv/bin/python`.

### Cited Lines on the Integrated Tree

The order's "What Is Wrong Today" lines were read at `b0da93ea`; after this
lane and S1b they now read:

- Derivation runs only for a non-TEST model with
  `[wizard.trait_inputs].derive_at_transition` on
  (`nexus/api/new_story_flow.py:589`; `nexus.toml:200`), records its stage
  (`:612`), or reuses a saved output through S1b (`:598-609`,
  `_reuse_genesis_stage` `:459-471`). Migration 141 allows `derivation` in both
  stage CHECKs (`migrations/141_genesis_run_ledger.sql:24`, `:51`).
- `RETROGRADE_WIZARD_STAGES` starts at `derivation`
  (`nexus/agents/orrery/retrograde_orchestrator.py:53-61`);
  `GENESIS_RUN_STAGES = RETROGRADE_WIZARD_STAGES` (`:66`, comment `:65`).
- `get_retrograde_progress` (`:318`) lists every stage row (`:340`, no
  derivation filter) and reports idle only for a skip or a stage-less run
  (`:346`).
- The CLI reads the same tuple (`nexus/cli.py:1788`, `:1800`, `:1803`), so
  `derivation` and `failed (derivation)` no longer reach
  `Genesis stage unavailable` (`:1837`).
- The UI mirrors it: `RETROGRADE_STAGES` (`ui/client/src/lib/narrative-api.ts:289`),
  `skippedRetrogradeStages` (`:388`), `GENESIS_STAGES`
  (`InteractiveWizard.tsx:96`), `pollRetrogradeStages` (`:107`),
  `showGenesisStatus` (`:575`) and the settled read with its disagreement error
  (`:660-662`).
- Prose: route docstring `nexus/api/wizard_chat.py:955-957`; spec item 14 of
  `docs/orrery_retrograde_spec.md` reads
  `Wizard-time progress states (derivation -> packet -> seed_candidates -> expansion -> persistence -> embedding -> done/failed)`
  and `It reads once more after the transition answers, because the run records its terminal stage just before the response.`
- `docs/turn_flow_sequence.md` declares `narrative-api.ts` a source (`:5`) and
  mentions it only for `continueNarrative` (`:52`); it does not describe the
  wait screen, so the comment change needs no prose change. Its
  `verified_commit` (`:34`) and those of
  `docs/decisions/0016-speculative-maturation.md` and
  `docs/decisions/0017-sparse-entity-enrichment.md` (`:6`) name `f073b371`,
  the merge base with origin/main, as moved by the assembly; the 4ae8b8d2
  statements above apply only to the lane source.

### Read-Only Fleet Survey

```sh
for db in save_01 save_02 save_03 save_04 save_05 NEXUS_template; do printf '%s ' $db; PGOPTIONS='-c default_transaction_read_only=on' psql -d $db -Atc "SELECT count(*) FROM genesis_runs" 2>&1; done
```

```
save_01 0
save_02 0
save_03 0
save_04 0
save_05 0
NEXUS_template 0
```

### Focused PostgreSQL Set

Load before the run: `17:51 up 6 days, 4:30, 5 users, load averages: 7.13 6.74 9.18`
(below 24; the bounded wait loop exited at once).

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_mock_wizard_responses.py tests/test_api/test_route_capabilities.py tests/test_cli_generation_http.py tests/test_orrery/test_retrograde_orchestrator.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 37 targets: nexus_test_issue_613_*, postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_offline_gate_* x29, qa640_renamed_test_model_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:59435 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:59436 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:59435 (psycopg2), save_04@local:59436 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
222 passed, 2 skipped, 7 warnings in 281.09s (0:04:41)
```

No connection timed out, so no file was rerun. The two skips were named by a
second run of three of the files with `-rs` (load
`17:56 ... load averages: 20.68 16.14 13.02`, below 24):

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_orrery/test_card_identity.py tests/test_cli_generation_http.py tests/test_connection_lifecycle.py
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
73 passed, 2 skipped, 2 warnings in 157.87s (0:02:37)
```

Both skips are the owner-corpus probes (`@requires_corpus`), outside this order.

### Offline Suites

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3197 passed, 677 skipped, 8 warnings in 630.29s (0:10:30)
```

This run outlived the ten-minute foreground limit; the harness moved it to the
background and a bounded poll read its tail. It was not split.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
1 failed, 1912 passed, 1528 skipped, 7 warnings in 46.73s
```

The failure is in a file this lane does not change. The validator
(`nexus/config/settings_models.py:2330-2370`) now refuses `ate` as a
background-branch event type before the birth-role check the test expects:

```
E       AssertionError: Regex pattern did not match.
E        Regex: 'without birth-role policies.*ate'
E        Input: "1 validation error for OrreryEpistemicsSettings\nclaim_event_types\n  Value error, claim_event_types contains event types emitted by background branches: ['ate'] [type=value_error, input_value=['ate'], input_type=list]\n    For further information visit https://errors.pydantic.dev/2.11/v/value_error"
```

It is reported to the coordinator and not fixed here.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py tests/test_doc_front_matter.py
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 19.60s
```

### UI

```sh
shasum -a 256 ui/package-lock.json   # before and after: 0f88785f3d0504d8a6ea5bdc9e82297b49aaf5932cbe4914b5ec3da368c1c4a2
nice -n 15 npm --prefix ui ci         # exit 0; lock unchanged
nice -n 15 npm --prefix ui test -- narrative-api InteractiveWizard WaitScreen WizardShell
```

```
 ✓ src/lib/narrative-api.retrograde.test.ts (32 tests) 7ms
 ✓ src/components/NewStoryWizard/WaitScreen.test.tsx (12 tests) 76ms
 ✓ src/components/NewStoryWizard/InteractiveWizard.test.tsx (7 tests) 168ms
 ✓ src/components/NewStoryWizard/WizardShell.test.tsx (24 tests) 1057ms
 ✓ src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx (50 tests) 4945ms
 Test Files  5 passed (5)
      Tests  125 passed (125)
```

`npm --prefix ui run check` (`tsc && tsc -p .design-sync/tsconfig.previews.json`)
exited 0 with no diagnostics on this tree. The same command exited 0 with no
diagnostics on origin/main, run in a scratch extraction
(`git archive origin/main | tar -x`, then `npm --prefix ui ci` there). No new
diagnostics.

```sh
nice -n 15 npm --prefix ui run build
```

```
✓ built in 2.57s
PWA v1.0.3
mode      generateSW
precache  22 entries (2322.18 KiB)
```

The full `npm --prefix ui test` is not run here: `state-shades.test.ts` is
stale on the integrated tree by design until the coordinator's single
regeneration on the final UI union. That regeneration, its summary and the full
UI run are the coordinator's step. This lane changes no measured surface (the
comment fix included), so the measurements should stay identical.

### Static Checks

Changed Python files: `nexus/agents/orrery/retrograde_orchestrator.py`,
`nexus/api/wizard_chat.py`, `tests/test_api/test_genesis_ledger_pg.py`,
`tests/test_cli.py`. The origin/main copies were run in the same scratch
extraction of `f073b371`.

```sh
nice -n 15 $PY -m black --check <four files>      # tree:        4 files would be left unchanged. exit=0
nice -n 15 $PY -m black --check <four files>      # origin/main: 4 files would be left unchanged. exit=0
nice -n 15 $PY -m flake8 <four files>             # tree: 10 diagnostics; origin/main: 12
nice -n 15 $PY -m mypy --explicit-package-bases <four files>
```

flake8, compared without line numbers: no diagnostic occurs only on the tree;
two E501 lines in `wizard_chat.py` occur only on origin/main. All ten tree
diagnostics are in `nexus/api/wizard_chat.py` (one F401 and nine E501), none on
this lane's docstring lines (`:955-957`).

mypy: the tree run reports `Found 24 errors in 2 files (checked 4 source files)`;
the origin/main run reports `Found 288 errors in 54 files` because it also
follows imports into the extracted package. Restricted to the four files and
compared without line numbers, `retrograde_orchestrator.py`, the two test files
and this lane's lines carry no diagnostic on the tree. Three diagnostics occur
only on the tree, all in `nexus/api/wizard_chat.py` lines another wave-B lane
changed (wizard transcripts, `d0e9d848`): `:553` (`build_message_history` gets
`list[WizardMessage]`) and `:577`, `:758` (`expected_thread_id` gets
`str | None`). They are reported to the coordinator; no new diagnostic comes
from this lane.

```sh
nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

```
OK: exception disposition coverage and shrink-only baseline verified.
```

### Coordinator's Steps

- The whole-tree PostgreSQL gate.
- The state-surface regeneration (`npm --prefix ui run resolve-state-surfaces`),
  its summary, and the full `npm --prefix ui test` after it.
- Landing notes stay as above: no migration and no fleet application;
  `nexus.toml` unchanged; a gateway restart and an owner UI rebuild are owed
  when services run again; the design-sync capture of `WaitScreen` gains a pip
  at the next upload.

Claude Opus 5.5

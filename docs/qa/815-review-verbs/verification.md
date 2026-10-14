# Review Verbs Verification

## Scope and Checkpoint

Work order 815-S3 adds `nexus accept --slot N`, the developer verb that commits
the incubator draft through the existing player-plane approve route. `undo`
continues to discard the draft and reset its parent's choice. No migration,
configuration value, provider call, UI change, new success envelope, or API
route change is part of this slice. Refs #815.

The lane was first recorded as a source checkpoint after the coordinator
confirmed the initial red. The ordered focused green, offline suites, static
comparison and exception-disposition check were then run on the integrated
wave-B tree; see Integrated-Tree Proof (2026-10-13) below. The whole-tree
PostgreSQL gate is the coordinator's step.

Tests were committed first at
`90c331ffc7e66c622e18ff55172e43deffe43acd`, tree
`8fbe81c005036d546c797089806c385de92ee4f4`, based on main
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The implementation was added
after the actual red run. No history was rewritten. That base and the lane
commits `90c331ff` and `7fc11e50` are pre-assembly history: the wave-B
assembly merged the lane into the integration branch at `917cc1d5`, and the
assembly moved the canonical documents' `verified_commit` stamps to
`f073b371`. Evidence below that cites `4ae8b8d2` describes that pre-assembly
source.

## Existing Behavior and Implementation

At that tests-only head, `build_parser` had no `accept` parser and
`COMMAND_TRANSPORTS` had no `accept` entry. At `4ae8b8d2` the existing
implementation is `nexus/api/narrative.py:1315` (`POST /api/narrative/approve`):
no pending draft produces the 404 at line 1344; a committed answer carries
`status` and `chunk_id` at line 1411. `nexus/api/slot_endpoints.py:294` clears
the parent choice in the existing undo transaction. This lane does not change
those files. Other wave-B lanes moved them on the integrated tree: there the
route is at `nexus/api/narrative.py:1327`, the 404 at `:1356`, the committed
answer at `:1423`, and the parent-choice reset at
`nexus/api/slot_endpoints.py:274`. The integrated-tree PostgreSQL proof below
exercises all four.

`run_accept` posts only `slot` and `commit: true`, using the existing
`turn_request_timeout_seconds`. It accepts only `status == "committed"` and an
integer chunk ID, explicitly excluding booleans. Non-empty warnings are kept.
Existing HTTP helpers retain transport, access and malformed-answer failures.
The parser adds only the required slot argument; dispatch and slot validation
include the command. The legacy HTTP-handler AST coverage was already included
in the tests-first commit. The registry classifies accept as HTTP without
changing `ENVELOPE_COMMANDS`.

The settings edit describes the existing 120-second turn budget; it changes no
value or validation. `docs/cli.md` documents commit versus discard and the
timeout. `docs/cli_reference.md` was generated from this branch's parser.
The lane's integrated diff (`a3d271fa..917cc1d5`) does not touch Decision 0009
(`docs/decisions/0009-dollars-in-the-ledger.md`). Its `verified_commit` stamp
is owned by the assembly root, which carries `f073b371`;
`tests/test_doc_front_matter.py` passes with that stamp on this tree (see the
offline named-file run below).

## Initial Red: Nine Missing-Command Failures

The coordinator ran the admitted proof at the exact tests-only head above.
The [raw result manifest](initial-red/results.json) records every argument,
environment name cleared, load, timeout, import path, exit code and log hash.
The [runner](initial-red/runner.py.txt), [complete log](initial-red/initial-red.txt),
[JUnit output](initial-red/initial-red.xml),
[import-path proof](initial-red/import-path.txt) and
[clone-cleanup read](initial-red/clone-cleanup-read-only.txt) are byte copies of
that run, not reconstructed evidence.

The runner used the shared interpreter with this worktree's `PYTHONPATH`,
`NEXUS_RUN_POSTGRES=1`, keyring disabled, provider-only protection, private
receipts, and the dbname audit. It selected all nine new cases, including the
boolean-ID case and both real-gateway PostgreSQL cases. Every failure was the
missing `accept` parser returning exit 2; there were no setup errors or skips.

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 3 targets: postgres, qa640_815_review_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_cli_contract.py::test_http_command_unanswered_request_exits_four[accept]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[accept-502]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[accept-html]
FAILED tests/test_cli_contract.py::test_accept_sends_slot_and_commit_and_reports_the_chunk
FAILED tests/test_cli_contract.py::test_accept_refuses_an_answer_without_a_chunk_id[not-committed]
FAILED tests/test_cli_contract.py::test_accept_refuses_an_answer_without_a_chunk_id[missing-id]
FAILED tests/test_cli_contract.py::test_accept_refuses_an_answer_without_a_chunk_id[bool-id]
FAILED tests/test_cli_review_pg.py::test_accept_commits_the_draft_and_keeps_the_parent_choice
FAILED tests/test_cli_review_pg.py::test_accept_without_a_draft_is_an_api_error
9 failed, 2 warnings in 14.58s
```

The post-run read returned `[]`: no `qa640_815_review` clone remained.

## Source Checkpoint Checks (Pre-Assembly, as Reported)

The lane author reports running these at the pre-assembly source checkpoint
(`7fc11e50`), with one-minute load 3.47 and explicit worktree `PYTHONPATH`,
`NEXUS_KEYRING_DISABLE=1` and `NEXUS_TEST_PROVIDER_ONLY=1`; their output was
not recorded:

```bash
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black \
  nexus/cli.py nexus/cli_contract.py nexus/config/settings_models.py
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m scripts.render_cli_reference --write
git diff --check
```

The author's report: Black left all three files unchanged; the generator wrote
the reference, whose only change is accept's transport membership and its
slot-only command section; the whitespace check passed. No tests, provider
requests, gateway operations or owner database operations were run for that
checkpoint. The Black, reference and whitespace checks were rerun with output
on the integrated tree below.

## Integrated-Tree Proof (2026-10-13)

Every command below ran in the fixer worktree
`/Users/pythagor/nexus/.claude/worktrees/fix-815-s3` on branch
`claude/waveb-fix-815-s3` at commit `ed64b0e9` (integration head `7eb9a10c`
plus the rewrap commit, which changes only a docstring and a Markdown
paragraph), with `$PY` = `/Users/pythagor/nexus/.venv/bin/python` and
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. Scratch logs live
under the session scratchpad in `fix-waveb-r2-815-S3/`. The machine has no
`timeout` binary; each command ran in the foreground under the harness's
ten-minute limit, except the two offline partitions, which ran detached and
were polled to completion.

### Import Path

```text
$ PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/fix-815-s3/nexus/__init__.py
```

### Focused PostgreSQL Proof

Load before the run: `{ 15.10 11.54 10.42 }` (one-minute load below 24; the
bounded wait loop `until [ "$(sysctl -n vm.loadavg | awk '{print int($2)}')" -lt 24 ]; do sleep 30; done`
returned at once). No connection timed out, so no rerun was needed.

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 \
  PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_cli_review_pg.py tests/test_api/test_acceptance_staging_pg.py \
  tests/test_cli_inspect_pg.py tests/test_orrery/test_card_identity.py \
  tests/test_connection_lifecycle.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 29 targets: postgres, qa640_815_inspect_*, qa640_815_review_* x2, qa640_815s5_operator_*, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_acceptance_* x19
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:62908 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:62909 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:62908 (psycopg2), save_04@local:62909 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
33 passed, 2 skipped, 9 warnings in 152.51s (0:02:32)
```

The two skips are named by a verbose rerun of the review file and the two
whole-tree consumers (load `{ 11.74 11.54 10.62 }`), which also shows both
new PostgreSQL cases passing by name:

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 \
  PYTHONPATH=$PWD nice -n 15 $PY -m pytest -v -rs -p tests.dbname_audit \
  tests/test_cli_review_pg.py tests/test_orrery/test_card_identity.py \
  tests/test_connection_lifecycle.py
```

```text
tests/test_cli_review_pg.py::test_accept_commits_the_draft_and_keeps_the_parent_choice PASSED [  7%]
tests/test_cli_review_pg.py::test_accept_without_a_draft_is_an_api_error PASSED [ 14%]
tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False] SKIPPED [ 28%]
tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[True] SKIPPED [ 35%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
================== 12 passed, 2 skipped, 2 warnings in 59.63s ==================
```

Excerpt (log lines 15-16, 18-19, 38, 45, 47-48, in order). The skips are the corpus probes gated on `NEXUS_RUN_CORPUS=1`, which this
order does not run. `test_accept_commits_the_draft_and_keeps_the_parent_choice`
proves that startup recovery keeps the parent choice when a draft is staged,
that the approve route writes `terminal_outcome = 'accepted'`, and that the
post-accept `undo` answers `domain_failure`. `test_acceptance_staging_pg.py`
passed unchanged, which proves the discard path still resets the parent choice.

Leftover-database read, before and after the runs (both empty):

```text
$ psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_815_review%'"
$
```

### Offline Named Files

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD \
  nice -n 15 $PY -m pytest -q tests/test_cli_contract.py tests/test_cli.py \
  tests/test_cli_reference_doc.py tests/test_reachability.py \
  tests/test_doc_front_matter.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
400 passed, 5 warnings in 193.69s (0:03:13)
```

### Offline Partitions

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES \
  PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests \
  --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
5 failed, 3192 passed, 671 skipped, 8 warnings in 707.62s (0:11:47)
exit=1
```

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES \
  PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
```

```text
=========================== short test summary info ============================
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts
FAILED tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
11 failed, 1896 passed, 1517 skipped, 7 warnings in 53.28s
exit=1
```

The named files of this order are green inside the first partition (the
offline named-file run above is the same set, 400 passed). None of the
sixteen failures is in a file this lane changes, and none involves the
`accept` verb; they are reported to the coordinator for triage, not fixed here:

- `tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged`:
  the Gaia request fingerprint changed (`e0f4920a...` against the recorded
  `cac3d730...`).
- `tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained`:
  `assert 732 < 700` (Gaia prompt word count).
- `tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module`:
  two findings, first `tests/test_orrery/test_place_point_required_pg.py:11`.
- `tests/test_skald_wire.py::test_wire_schema_size_and_description_budget`:
  new description `NewEntityDeclaration.coordinates`.
- `tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp`
  and `tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]`
  / `[character_confirmed]`: `Unit test attempted psycopg2.connect; mark it
  requires_postgres and run with NEXUS_RUN_POSTGRES=1.`
- `tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy`:
  the validator now rejects `ate` as a background-branch event type before the
  birth-role check the test expects.
- Eight `tests/test_orrery/test_worker.py` cases: `orrery.projects.milestone_magnitude
  must be >= orrery.promote.magnitude_threshold` from the settings validator.

### Generated Reference, Black and Whitespace

```text
$ PYTHONPATH=$PWD nice -n 15 $PY -m scripts.render_cli_reference --check
exit=0
$ nice -n 15 $PY -m black --check nexus/cli.py nexus/cli_contract.py nexus/config/settings_models.py tests/test_cli.py tests/test_cli_contract.py tests/test_cli_review_pg.py
All done! ✨ 🍰 ✨
6 files would be left unchanged.
$ git diff --check a3d271fa HEAD -- docs/cli.md docs/cli_reference.md nexus/cli.py nexus/cli_contract.py nexus/config/settings_models.py tests/test_cli.py tests/test_cli_contract.py tests/test_cli_review_pg.py docs/qa/815-review-verbs/verification.md
check=0
```

### Flake8 Against `origin/main`

`origin/main` is `f073b371`, which is also the merge base. The `origin/main`
and lane-base (`a3d271fa`) versions of the five pre-existing files were written
with `git show <ref>:<path>` into scratch directories and linted with the
repository's `.flake8`; the HEAD run includes the new test file. Line numbers
are dropped so that shifts from other lanes do not hide a new diagnostic.

```bash
nice -n 15 $PY -m flake8 nexus/cli.py nexus/cli_contract.py nexus/config/settings_models.py tests/test_cli.py tests/test_cli_contract.py tests/test_cli_review_pg.py | sed -E 's/:[0-9]+:[0-9]+:/:/' | sort | uniq -c
```

All three runs print the same fifteen pre-existing E501 diagnostics (nine in
`nexus/cli.py`, six in `nexus/config/settings_models.py`) and nothing else; no
diagnostic is new and none is on a line this lane changed.

### Mypy Against `origin/main`

```bash
nice -n 15 $PY -m mypy --explicit-package-bases nexus/cli.py nexus/cli_contract.py nexus/config/settings_models.py tests/test_cli.py tests/test_cli_contract.py tests/test_cli_review_pg.py
```

HEAD:

```text
nexus/config/settings_models.py:138: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:138: note: Right operand is of type "int | None"
nexus/config/settings_models.py:139: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:139: error: Unsupported operand types for < ("int" and "None")  [operator]
nexus/config/settings_models.py:139: error: Unsupported left operand type for > ("None")  [operator]
nexus/config/settings_models.py:139: note: Both left and right operands are unions
nexus/config/settings_models.py:146: error: Unsupported operand types for + ("int" and "None")  [operator]
nexus/config/settings_models.py:146: note: Right operand is of type "int | None"
nexus/config/settings_models.py:146: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4568: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4568: note: Right operand is of type "int | None"
tests/test_cli.py:2030: error: Need type annotation for "literals" (hint: "literals: list[<type>] = ...")  [var-annotated]
Found 8 errors in 2 files (checked 6 source files)
```

The `origin/main` versions of the five pre-existing files were checked out over
the worktree copies, checked with the same command (without the new test
file), and restored with `git checkout HEAD -- <the five files>`; `git diff
--quiet` and an empty `git status --porcelain` confirmed the restore.

```text
nexus/config/settings_models.py:138: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:138: note: Right operand is of type "int | None"
nexus/config/settings_models.py:139: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:139: error: Unsupported operand types for < ("int" and "None")  [operator]
nexus/config/settings_models.py:139: error: Unsupported left operand type for > ("None")  [operator]
nexus/config/settings_models.py:139: note: Both left and right operands are unions
nexus/config/settings_models.py:146: error: Unsupported operand types for + ("int" and "None")  [operator]
nexus/config/settings_models.py:146: note: Right operand is of type "int | None"
nexus/config/settings_models.py:146: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4516: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4516: note: Right operand is of type "int | None"
tests/test_cli.py:1990: error: Need type annotation for "literals" (hint: "literals: list[<type>] = ...")  [var-annotated]
Found 8 errors in 2 files (checked 5 source files)
```

The same eight errors on both sides; the line moves (`4516` to `4568`,
`1990` to `2030`) come from other lanes' additions above them. Pre-existing
diagnostics: those eight, none on a line this lane changed.

### Exception Dispositions

```text
$ nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

### Coordinator's Steps

- The whole-tree PostgreSQL gate (coordinator's step).
- The state-surface regeneration (coordinator's step; this lane has no `ui/`
  change).
- Fleet migrations (coordinator's step; this lane has no migration).
- No paid call and no owner service is needed by this order.

## Landing

The coordinator owns the serial whole-tree PostgreSQL gate, the
state-surface regeneration (this lane has no `ui/` change) and any fleet
application (this lane has no migration). The `nexus.toml` timeout comment
remains deferred as ordered. The historical QA script keeps its raw approve
POST. The product-code restart is owed when owner services are next resumed.

Codex — GPT-6

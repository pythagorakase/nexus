# 809-S1 Typed Settings Readers

Status: source implementation and the ordered 12-case offline red/green proof
were recorded by the authoring lane. The order's remaining proof (offline
suites, the three PostgreSQL proof lines, collect-only runs, the static
comparison and the exception-disposition run) ran on the integrated wave-B
tree on 2026-10-13; see "Integrated-Tree Proof (2026-10-13)" below. The
whole-tree gate, state-surface regeneration and fleet steps are the
coordinator's.

The coordinator separately admitted a lightweight Black/source checkpoint.
Black completed over all 32 changed or added Python files: 10 reformatted,
22 unchanged. Its output is [black-source-checkpoint.txt](black-source-checkpoint.txt).
This is formatting evidence only; it does not substitute for green tests or
the ordered comparison of static diagnostics.

Base: `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8` (the authoring base; every
section above "Integrated-Tree Proof" cites it. The assembly moved the
canonical documents' `verified_commit` stamps to `f073b371`, and the
integrated-tree proof below compares against `f073b371`).
Branch: `codex/809-typed-readers`.
Order: `temp/orders_2026_10_07/809-S1.md`, bound by the
[recorded Q9 ruling](https://github.com/pythagorakase/nexus/issues/809#issuecomment-5915947649).

## Initial Red Before Product Changes

The ordered file was authored while every product file still matched the base.
The exact invocation, cleared environment key names, base, import path and load
are recorded in [initial-red.json](initial-red.json). The complete unchanged
output is [initial-red.txt](initial-red.txt).

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q \
  -p tests.dbname_audit -p no:cacheprovider tests/config/test_typed_readers.py
```

The process ran in this exact worktree with its absolute `PYTHONPATH`, no
PostgreSQL opt-in, disabled Keychain, cleared runtime/database routing and
`PYTEST_*` overrides, and a 120-second deadline. Import admission returned
`/Users/pythagor/.codex/worktrees/resume-typed-readers/nexus/nexus/__init__.py`.
The one-minute load was 23.219. The process completed normally with test exit 1.

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner targets: none
11 failed, 1 passed in 1.11s
```

Every failure was inspected:

| Case | Initial Failure |
| --- | --- |
| Product AST closure | Exactly the six ordered modules import or call the facade. |
| API constraints table absent | Validation incorrectly succeeds. |
| Choice-text limit absent | Validation incorrectly succeeds. |
| Section helper identity/refusal | `Settings.require_orrery` is absent. |
| Promotion without Orrery | Slot resolution happens before section admission. |
| Narration without Orrery | Default configuration reaches slot resolution. |
| Maturation drain without Orrery | Reconstructing `dict(Settings)` raises unrelated correspondence validation. |
| Maturation enqueue without Orrery | Default configuration reaches slot resolution. |
| Experiences without Orrery | Mapping reader calls missing `Settings.get`. |
| Scheduler without Orrery | Mapping reader subscripts `Settings`. |
| Scheduler without runtime | Mapping reader subscripts `Settings`. |

The exact by-alias Orrery dump parity guard passed. The new file installs a
connection-refusal tripwire even when included later in a PostgreSQL-enabled
session. The tripwire raises pytest's failure outcome, which cannot satisfy the
required `RuntimeError`. The scheduler's explicit database is the unused
disposable name `qa640_809_unused`; no connection was attempted.

## Bounded Green and Source Checkpoint

The same exact offline command passed on source commit
`dec6f76cfdf559e89cda2085817aa1afdaf1d9ec`, under the same 120-second deadline,
cleared environment, exact import path and connection-refusal tripwire. The
one-minute load was 7.593. Original metadata and output are retained in
[initial-green.json](initial-green.json) and [initial-green.txt](initial-green.txt).

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner targets: none
12 passed in 0.90s
```

No source correction was needed after this green run. The source checkpoint's
normal commit hooks passed the catalog regeneration, configuration/model-ID
validation and exception-disposition checks. The migration-comment hook had no
applicable files. (The authoring lane also reported two source reviews of the
production conversions and the maturation/model-identity tests; no artifact of
those reviews was kept, so they are not evidence. The runtime proof is the
integrated-tree run below.)

## Source Changes and Caller Adaptations

The API constraints table and choice-text limit become required. `Settings.api`
remains optional; its absent-section reader raises explicitly. Orrery and
runtime admission methods retain section identity and name the requiring
operation. Workers, maturation, experiences, seat capture and scheduler now
receive `Settings`. Promotion admits Orrery before attempting a connection.

The accepted-chunk operation loads once, dumps only the Orrery section with
aliases for the unchanged engine, and shares the typed object with experience
and checkpoint readers. Developer endpoints use the same explicit mapping
boundary. The attempt-manifest dump/hash and facade exports remain unchanged.
Source search now finds `load_settings_as_dict` under `nexus/` only in
`nexus/config/__init__.py` and `nexus/config/loader.py`; the verbatim grep
outputs (before and after) are under "Facade Grep" in the integrated-tree
proof below.

Adapted existing caller files:

- `tests/pg_fixtures.py`
- `tests/test_api/test_attempt_manifest_pg.py`
- `tests/test_api/test_narrative_jobs_pg.py`
- `tests/test_api/test_narrative_summary_paid_pg.py`
- `tests/test_api/test_orrery_config_reuse_pg.py`
- `tests/test_api/test_scheduler_locked_pg.py`
- `tests/test_api/test_scheduler_pg.py`
- `tests/test_api/test_seat_policy_jobs_pg.py`
- `tests/test_api/test_summary_budget_usage.py`
- `tests/test_live_gate_clones_pg.py`
- `tests/test_orrery/test_acquisition_scan_pg.py`
- `tests/test_orrery/test_character_experiences_pg.py`
- `tests/test_orrery/test_embedding_audit.py`
- `tests/test_orrery/test_experience_enqueue_gin_pg.py`
- `tests/test_orrery/test_live_cycle.py`
- `tests/test_orrery/test_narration_job_fencing_pg.py`
- `tests/test_orrery/test_retrograde_maturation.py`
- `tests/test_orrery/test_stage2a_status_live.py`
- `tests/test_orrery/test_worker.py`
- `tests/test_pg_experience_seeds.py`
- `tests/test_presence_roster_pg.py`

`tests/settings_helpers.py`, settings parity and assembled-prompt fingerprint
tests are unchanged. Facade values feeding only unchanged mapping consumers
remain mappings. The API config-reuse regression blocks both facade exports,
records one returned `Settings`, and requires checkpoint object identity plus
the existing exact tick keyword values.

Three adaptations preserve previously tested meaning under validation:

- The retired narration provider key now fails while constructing `Settings`.
  Only that test's worker call and lease-update assertion are retired, as
  ordered; an invalid settings object cannot reach the worker.
- An explicit zero embedding request still returns before reading a missing
  Orrery section. Default work refuses that section, and a separate assertion
  retains rejection of configured `max_embeddings_per_drain=0`.
- The rendering pin proof uses another registered model and asserts it differs
  from the captured job model, replacing the formerly unchecked invalid literal
  `render-time-model`. Partial maturation tables retain model defaults plus the
  configured seat ID that the old subsection merge used to supply.

The newer `seed_experience_candidates` and `seed_experience_render_job` fixture
helpers accept typed settings. Their existing disposable-target check remains
before settings access or connection; the invalid-settings owner-refusal
controls in `test_pg_disposable_target.py` stay unchanged.

## Canonical Source Review

Reverified `AGENTS.md`, `docs/turn_flow_sequence.md`, and decisions 0010, 0016,
0017, 0019, 0027, 0044 and 0055 before moving their stamps to the frozen main
base `4ae8b8d2` (the assembly has since moved all nine stamps to `f073b371`;
`tests/test_doc_front_matter.py` passes on the integrated tree, below). All quoted text, source lists, kinds and bodies are unchanged. Seat
precedence, commit ordering, scheduler lease/queue order, deterministic
descriptors, provider-era provenance columns and story-derived weirdness remain
unchanged. Maturation is still accepted-branch-only and one-shot: its entity job
uniqueness and already-connected guard remain intact. The scheduler mention in
the decisions README is a fenced example, not a source declaration.

## Integrated-Tree Proof (2026-10-13)

Run by the wave-B fixer (Claude Opus 5.5) in worktree `fix-809-s1` on branch
`claude/waveb-fix-809-s1`, cut from the integration head `7eb9a10c`
(`origin/main` `f073b371` plus fifteen wave-B lanes, the 777 shell and a
palette commit). The lane's integrated diff range is `f073b371..0cc63fa9`.
Import admission: `PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'`
printed `/Users/pythagor/nexus/.claude/worktrees/fix-809-s1/nexus/__init__.py`.
`$PY` is `/Users/pythagor/nexus/.venv/bin/python`. Every run had
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset (`env -u`), ran
under `nice -n 15`, and was capped at 570 s by `perl -e "alarm 570; exec @ARGV"`;
`NEXUS_RUN_LIVE_LLM` was never set. Each PostgreSQL run first waited in a
bounded loop (cap 20 minutes) for the one-minute load to fall below 24; every
PostgreSQL run recorded `load-wait-seconds: 0` (one-minute loads 6.4 to 14.0).
Tails below drop the per-test `--durations=8` timing lines and Python
deprecation warnings; nothing else is removed.

### Fixes Made on the Integrated Tree

- `14d64daa` Gate finding from the coordinator's 2026-10-09 whole-tree run:
  `tests/test_orrery/test_worker.py` built `orrery.promote` tables with
  `magnitude_threshold` 0.5 and 0.9, above the 0.40 project-milestone default,
  so `OrrerySettings._validate_project_milestone_promotion_floor` (already on
  `f073b371`) rejected the typed settings. Both tables now set
  `orrery.projects.milestone_magnitude` to the table's threshold. No assertion
  changed. Before, offline at `7eb9a10c`:

  ```text
  E       pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
  E       orrery
  E         Value error, orrery.projects.milestone_magnitude must be >= orrery.promote.magnitude_threshold [type=value_error, ...]
  secret-store guard: active; nexus-api: denied; disposable keychain: denied
  dbname audit: owner targets: none
  8 failed, 3 passed, 1 skipped in 0.29s
  ```

  After (offline, same command `env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u
  NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit
  tests/test_orrery/test_worker.py`):

  ```text
  secret-store guard: active; nexus-api: denied; disposable keychain: denied
  receipt isolation: checkout and user receipts untouched
  dbname audit: 0 targets: none
  dbname audit: owner server: local:5432
  dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
  dbname audit: owner targets: none
  11 passed, 1 skipped in 0.18s
  ```

  The skipped case is PostgreSQL-only; it passes in PostgreSQL line 3 below.
- `cc85330a` The coordinator's ruled one-line import fix for 811-S3a's module
  move: `from scripts import migrate` -> `from nexus.maintenance import migrate`
  in `tests/test_runtime/test_init_plan_pg.py:23` and
  `tests/test_orrery/test_place_point_required_pg.py:11`. Nothing else changed
  in either file.
- `bb3c5a30` flake8 F401 `'typing.Mapping' imported but unused` in
  `tests/test_orrery/test_retrograde_maturation.py`: 809-S1 removed the
  module-level `Mapping` annotations and 840-S2 (`ed5ce5a4`) removed the last
  local one, so only the union left the import unused. The import now reads
  `from typing import Any, Iterator`.

### Offline Suites

The order's `tests --ignore=tests/test_api --ignore=tests/test_orrery` was first
started as one command; it reached 13% in 4 min 44 s (projected well past the
ten-minute limit) and was stopped, then split into four pieces. Pieces B1-B3
are `ls tests/test_*.py` (144 files, alphabetical) in three 48-file chunks:
B1 `tests/test_backfill_review_packet.py` .. `tests/test_logon_mock_integration.py`,
B2 `tests/test_lore_adapter_metadata.py` .. `tests/test_presence_reconciliation.py`,
B3 `tests/test_presence_roster_pg.py` .. `tests/test_world_clock_contract_pg.py`.
All offline runs are on commit `cc85330a39dc5659cb3fd713b022ec133621cd77`.

Piece A: `env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD
nice -n 15 $PY -m pytest -q -p tests.dbname_audit --durations=8 tests/config
tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon
tests/test_runtime tests/test_scripts tests/test_util tests/proofs`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
2 failed, 1043 passed, 89 skipped, 7 warnings in 169.02s (0:02:49)
```

Piece B1 (same command, files B1):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
717 passed, 185 skipped, 2 warnings in 377.28s (0:06:17)
```

Piece B2 (files B2):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
713 passed, 166 skipped, 3 warnings in 52.18s
```

Piece B3 (files B3):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
2 failed, 720 passed, 229 skipped, 2 warnings in 103.88s (0:01:43)
```

The order's second offline line, split in two: `... tests/test_api`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
2 failed, 547 passed, 330 skipped, 7 warnings in 36.65s
```

`... tests/test_orrery`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
1 failed, 1357 passed, 1187 skipped, 2 warnings in 15.09s
```

`... tests/test_reachability.py tests/test_doc_front_matter.py`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
120 passed in 21.89s
```

Every offline failure lies outside this lane; none touches a file 809-S1
changed, and `git diff f073b371 0cc63fa9 -- prompts/` is empty:

| Failure | Cause on the integrated tree |
| --- | --- |
| `test_assembled_writer_and_gaia_requests_are_unchanged`, `test_gaia_prompt_is_concise_and_self_contained` | 840-S2 `ed5ce5a4` edits `prompts/storyteller_gaia.md` (Gaia fingerprint `e0f4920a...` vs pinned `cac3d730...`; prompt 732 words vs the 700 bound). |
| `test_wire_schema_size_and_description_budget` | 840-S2 `ed5ce5a4` adds the `NewEntityDeclaration.coordinates` description. |
| `test_transition_rejects_missing_diegetic_timestamp`, `test_final_transition_cannot_bypass_artifact_acceptance[*]` | "Unit test attempted psycopg2.connect": the wizard transition now runs `run_genesis_transition` (776-S1b `95a45ca1`), which connects before the offline test's patched cache check. |
| `test_epistemics_rejects_event_type_without_birth_role_policy` | `9641f184` (frozen shell source for Backstage) adds the "emitted by background branches" validator, which fires before the birth-role message the test matches. |

### PostgreSQL Proof Lines

All three on commit `cc85330a39dc5659cb3fd713b022ec133621cd77`, one session
at a time, each prefixed `env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u
NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p
tests.dbname_audit --durations=8`.

Line 1: `tests/config tests/test_lore/test_assembled_prompt_fingerprint.py
tests/test_lore/test_pass2_baseline_pg.py tests/test_live_gate_clones_pg.py
tests/test_presence_roster_pg.py tests/test_commit_handler_sync.py
tests/test_character_name_reveals.py tests/test_connection_lifecycle.py`
(uptime before: load averages 14.01 12.96 11.85; load wait 0 s)

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 40 targets: nexus_test_pass2_* x7, postgres, qa640_816_lifecycle_test_provider, qa640_compaction_retry_*, qa640_roster798_* x23, qa640_settings_stamp_*, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:51423 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:51424 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:51423 (psycopg2), save_04@local:51424 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
1 failed, 217 passed, 9 warnings in 168.21s (0:02:48)
```

The one failure is the 840-S2 Gaia prompt fingerprint above (the order requires
this file to pass unchanged; this lane neither edits it nor any prompt).
`tests/config` includes `tests/config/test_typed_readers.py` (12 cases) and
`tests/config/test_settings_parity.py`; both passed.

Line 2: `tests/test_api/test_orrery_config_reuse_pg.py
tests/test_api/test_attempt_manifest_pg.py tests/test_api/test_scheduler_pg.py
tests/test_api/test_scheduler_locked_pg.py
tests/test_api/test_scheduler_recovery_pg.py
tests/test_api/test_scheduler_corpus_pg.py
tests/test_api/test_scheduler_hold_settings.py
tests/test_api/test_narrative_jobs_pg.py tests/test_api/test_seat_policy_jobs_pg.py
tests/test_api/test_summary_budget_usage.py
tests/test_api/test_orrery_dev_endpoints.py tests/test_api/test_db_pool_pg.py
tests/test_api/test_narrative_post_commit.py
tests/test_api/test_correspondence_pg.py tests/test_api/test_return_recap_pg.py
tests/test_api/test_narrative_continue_validation.py`
(uptime before: 7.86 11.59 11.56; load wait 0 s)

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 87 targets: nexus_test_continue_* x10, nexus_test_correspondence_* x2, postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_kill_*, qa640_800_renew_* x4, qa640_800_turn_*, qa640_800b_inspect_*, qa640_802_reported_*, qa640_804_* x12, qa640_814_seats_*, qa640_937_budget_* x2, qa640_938_usage_* x2, qa640_acceptance_* x3, qa640_offline_gate_* x29, qa654_*, qa832_recap_* x10, qa885_orrery_dev_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
135 passed, 9 warnings in 360.59s (0:06:00)
```

Line 3, with the files the evidence and findings add
(`tests/test_pg_experience_seeds.py`, `tests/test_pg_disposable_target.py`,
`tests/test_orrery/test_stage2a_status_live.py`, which carries only
`requires_postgres`): `tests/test_orrery/test_worker.py
tests/test_orrery/test_retrograde_maturation.py
tests/test_orrery/test_character_experiences_pg.py
tests/test_orrery/test_embedding_audit.py
tests/test_orrery/test_acquisition_scan_pg.py
tests/test_orrery/test_experience_enqueue_gin_pg.py
tests/test_orrery/test_narration_job_fencing_pg.py
tests/test_orrery/test_boundary_enumeration_pg.py
tests/test_orrery/test_card_identity.py tests/test_pg_experience_seeds.py
tests/test_pg_disposable_target.py tests/test_orrery/test_stage2a_status_live.py`
(uptime before: 7.09 8.37 9.89; load wait 0 s)

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 52 targets: postgres, qa640_780_boundaries_*, qa640_780_storm_*, qa640_800_operator_*, qa640_816_experience_seed_* x2, qa640_885_ren_replay_* x4, qa640_maturation799_*, qa640_wizard_drain_* x3, qa640_worker_*, qa676_* x7, qa885_stage2a_status_*, qa885_transaction_writer_*, qa_wt720_*, qa_wt723_*, qa_wt724_experience_* x26
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
201 passed, 2 skipped, 2 warnings in 132.45s (0:02:12)
```

The two skips are the `requires_corpus` cases
`tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False]`
and `[True]` (`NEXUS_RUN_CORPUS` unset; `--co -m requires_corpus` over the
same files selects exactly these two).

After `bb3c5a30` (the unused-import fix), the touched file was rerun on commit
`bb3c5a3013dd31ad92b135752e9221def04faaa4`: `... NEXUS_RUN_POSTGRES=1 ...
tests/test_orrery/test_retrograde_maturation.py` (load wait 0 s)

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_maturation799_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
37 passed in 3.08s
```

Every file the adaptation grep matched ran in one of the three lines, except
the live files collected below and `tests/test_golden_path_live.py`,
`tests/test_orrery/test_retrograde_maturation_live.py` and
`tests/test_runtime/test_supervisor_live.py`, which this lane did not edit.

### Collect-Only Runs of the Edited Live Files

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice
-n 15 $PY -m pytest -q --collect-only tests/test_orrery/test_live_cycle.py
tests/test_api/test_narrative_summary_paid_pg.py
tests/test_orrery/test_stage2a_status_live.py` on `cc85330a`:

```text
tests/test_orrery/test_stage2a_status_live.py::test_wizard_time_retrograde_status_keeps_source_chunk_null
tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate
tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
7 tests collected in 0.24s
```

### Facade Grep

On `f073b371` (`git grep -n load_settings_as_dict f073b371 -- nexus/`), the six
product readers the order names:

```text
f073b371:nexus/agents/orrery/retrograde_maturation.py:62:from nexus.config import load_settings_as_dict
f073b371:nexus/agents/orrery/retrograde_maturation.py:165:    settings_dict = dict(settings or load_settings_as_dict())
f073b371:nexus/agents/orrery/retrograde_maturation.py:588:    settings_dict = dict(settings or load_settings_as_dict())
f073b371:nexus/agents/orrery/worker.py:27:from nexus.config import load_settings_as_dict
f073b371:nexus/agents/orrery/worker.py:166:            settings=dict(settings or load_settings_as_dict()),
f073b371:nexus/agents/orrery/worker.py:187:    settings_dict = dict(settings or load_settings_as_dict())
f073b371:nexus/agents/orrery/worker.py:248:    settings_dict = dict(settings or load_settings_as_dict())
f073b371:nexus/api/commit_handler_sync.py:1205:    from nexus.config import load_settings_as_dict
f073b371:nexus/api/commit_handler_sync.py:1207:    return cast(Mapping[str, Any], load_settings_as_dict().get("orrery") or {})
f073b371:nexus/api/config_utils.py:6:from nexus.config import load_settings, load_settings_as_dict
f073b371:nexus/api/config_utils.py:42:    settings = load_settings_as_dict()
f073b371:nexus/api/orrery_dev_endpoints.py:254:    from nexus.config import load_settings_as_dict
f073b371:nexus/api/orrery_dev_endpoints.py:256:    settings = load_settings_as_dict()
f073b371:nexus/config/__init__.py:6:    load_settings_as_dict,
f073b371:nexus/config/__init__.py:19:    "load_settings_as_dict",
f073b371:nexus/config/loader.py:388:def load_settings_as_dict(path: Union[str, Path, None] = None) -> Dict[str, Any]:
f073b371:nexus/jobs/scheduler.py:18:from nexus.config import load_settings_as_dict
f073b371:nexus/jobs/scheduler.py:75:        self.settings = settings or load_settings_as_dict()
```

On the integrated tree (`grep -rn load_settings_as_dict nexus/`, `bb3c5a30`):

```text
nexus/config/loader.py:388:def load_settings_as_dict(path: Union[str, Path, None] = None) -> Dict[str, Any]:
nexus/config/__init__.py:6:    load_settings_as_dict,
nexus/config/__init__.py:19:    "load_settings_as_dict",
```

### Adaptation Grep

The order's adaptation grep (`grep -rlE "(SlotScheduler|promote_pending_resolutions_sync|...|_orrery_checkpoint_interval)\b" tests | sort`,
the full pattern as the order states it) on `cc85330a`:

```text
tests/config/test_typed_readers.py
tests/pg_fixtures.py
tests/test_api/test_attempt_manifest_pg.py
tests/test_api/test_correspondence_pg.py
tests/test_api/test_db_pool_pg.py
tests/test_api/test_narrative_jobs_pg.py
tests/test_api/test_narrative_post_commit.py
tests/test_api/test_narrative_summary_paid_pg.py
tests/test_api/test_orrery_config_reuse_pg.py
tests/test_api/test_scheduler_corpus_pg.py
tests/test_api/test_scheduler_locked_pg.py
tests/test_api/test_scheduler_pg.py
tests/test_api/test_scheduler_recovery_pg.py
tests/test_api/test_seat_policy_jobs_pg.py
tests/test_api/test_summary_budget_usage.py
tests/test_character_name_reveals.py
tests/test_commit_handler_sync.py
tests/test_golden_path_live.py
tests/test_live_gate_clones_pg.py
tests/test_lore/test_pass2_baseline_pg.py
tests/test_orrery/test_acquisition_scan_pg.py
tests/test_orrery/test_character_experiences_pg.py
tests/test_orrery/test_embedding_audit.py
tests/test_orrery/test_experience_enqueue_gin_pg.py
tests/test_orrery/test_live_cycle.py
tests/test_orrery/test_narration_job_fencing_pg.py
tests/test_orrery/test_retrograde_maturation_live.py
tests/test_orrery/test_retrograde_maturation.py
tests/test_orrery/test_stage2a_status_live.py
tests/test_orrery/test_worker.py
tests/test_presence_roster_pg.py
tests/test_runtime/test_supervisor_live.py
```

`tests/test_pg_experience_seeds.py` is adapted but not matched (it calls the
fixture helpers `seed_experience_candidates` and `seed_experience_render_job`).
Matched and left unchanged, each with its reason:

| File | Why it needs no change |
| --- | --- |
| `tests/test_api/test_correspondence_pg.py` | Stubs `_orrery_checkpoint_interval` with `lambda _settings: 0` (any argument); `SlotScheduler(4, dbname=dbname)` passes no settings and takes the default `load_settings()`. |
| `tests/test_api/test_db_pool_pg.py` | Bare `SlotScheduler(4, dbname=database)`. |
| `tests/test_api/test_narrative_post_commit.py` | Bare `SlotScheduler(4, dbname=...)`; wraps `drain_maturation_jobs_sync` with `*args, **kwargs` forwarding. |
| `tests/test_api/test_scheduler_corpus_pg.py` | Bare `SlotScheduler(4)`. |
| `tests/test_api/test_scheduler_recovery_pg.py` | Bare `SlotScheduler(4)`. |
| `tests/test_character_name_reveals.py` | Calls `enqueue_declared_entity_maturations(object(), declarations=..., chunk_id=4, raw_text=...)` with no settings argument; the conflict raises as before. |
| `tests/test_commit_handler_sync.py` | Stubs only: `*_args, **_kwargs` lambdas and `lambda _settings: 0` for `_orrery_checkpoint_interval`. |
| `tests/test_golden_path_live.py` | Docstring and comment mentions only (lines 43, 45, 524). |
| `tests/test_lore/test_pass2_baseline_pg.py` | Stubs `_orrery_checkpoint_interval` with `lambda _settings: 0`. |
| `tests/test_orrery/test_retrograde_maturation_live.py` | Calls `enqueue_declared_entity_maturations` and `drain_maturation_jobs_sync(slot=ROUTED_SLOT, limit=10)` with no settings argument. |
| `tests/test_runtime/test_supervisor_live.py` | Docstring mention only (line 15). |

### Static Checks

Changed Python files: the 32 the lane adds or modifies
(`git diff --name-only --diff-filter=AM f073b371 0cc63fa9 -- '*.py'`); the base
set is the 31 that exist on `f073b371`, exported with `git archive f073b371
nexus tests scripts .flake8 pyproject.toml nexus.toml` into a scratch
directory and checked there with the same commands. Head runs are on
`bb3c5a3013dd31ad92b135752e9221def04faaa4`; the integrated versions of
twelve of these files also carry other lanes' edits.

- Black: `nice -n 15 $PY -m black --check <32 files>` -> `All done! ✨ 🍰 ✨`,
  `32 files would be left unchanged.` (exit 0). The earlier
  [black-source-checkpoint.txt](black-source-checkpoint.txt) is the authoring
  lane's formatting run.
- flake8: `nice -n 15 $PY -m flake8 <files>` at base and head; diagnostics
  compared as (file, code, message) multisets, ignoring line numbers. Base 112,
  head 104. New at head: none. The five F811 entries that differ appear only
  because their message cites a shifted line (`from line 25` -> `26`, `30` ->
  `31`, `378` -> `382`); they are the same pre-existing redefinitions. Removed
  at head: `nexus/api/config_utils.py` F401 `typing.Any` and `typing.Dict`
  (this lane), six E501 in `tests/test_presence_roster_pg.py`.
- mypy: `nice -n 15 $PY -m mypy --explicit-package-bases <files>` at base and
  head, compared on diagnostics reported in the changed files, ignoring line
  numbers. Base 68, head 61 (`Found 46 errors in 12 files (checked 32 source
  files)`). New at head: none. Removed at head: in
  `tests/test_orrery/test_retrograde_maturation.py`, two `__exit__`
  `[exit-return]` errors with their notes and one `[union-attr]` on
  `OrrerySettings | None`.
- Exception dispositions: `nice -n 15 $PY -S
  scripts/check_exception_dispositions.py --baseline-base-ref origin/main`
  (`origin/main` = `f073b3711a3bd0273943c9defad85913452fd00b`) -> `OK:
  exception disposition coverage and shrink-only baseline verified.` (exit 0).

### Coordinator's Steps

- The whole-tree PostgreSQL gate on the integrated head.
- `npm --prefix ui run resolve-state-surfaces` (this lane changes no UI file).
- Fleet migrations: none (this lane has no migration).
- A gateway restart when the owner's services next run (product code changed).
- Triage of the out-of-lane failures in the table above.

## Landing Scope

No migration, fleet application, UI change or UI build is required. Product
changes require a gateway restart when services next run. `nexus.toml`, scripts,
`ir_eval/`, owner resources and model files are unchanged. The remaining #809
slices and owner question Q1 stay open.

Codex — GPT-6
Wave-B integrated-tree proof: Claude Opus 5.5

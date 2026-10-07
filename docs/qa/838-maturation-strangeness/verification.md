# 838-S1 Verification: Runtime Maturation Follows the Story's Genesis Strangeness

Branch `claude/838-maturation-strangeness`, cut from `origin/main` at `364fef4b`. Refs #838. No migration, no paid call, no gateway lane, no write to any `save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07`.

## Premise, Checked at 364fef4b

- `_resolve_maturation_weird` (`nexus/agents/orrery/retrograde_maturation.py:1317-1349`) passed `weird_level=cfg.weird_level` (`:1338`); no runtime code read `global_variables.genesis_weird` (its only writer is `_record_genesis_weird`, `nexus/api/new_story_flow.py:424-450`).
- `_load_story_setting` (`:1352-1368`) selected only `setting`; `_mature_one` called it at `:773` and passed the result to `build_runtime_maturation_packet` (`:780-788`).
- The packet's `weird["source"]` was already `"maturation_band"` (`:1345`).
- `_base_manifest` and the three post-packet manifests carried no weird data.
- `OrreryRetrogradeMaturationSettings.weird_level` (`nexus/config/settings_models.py:2883-2886`, `extra="forbid"` at `:2831`) and `nexus.toml:806` held the retired key; `default_level` lives at `nexus.toml:821`.

All confirmed as the order states.

## After This Change (Line References on the Branch)

- `_mature_one` loads `story_setting, genesis_weird = _load_story_weird_inputs(cur)` (`retrograde_maturation.py:773`) and passes `genesis_weird=genesis_weird` (`:787`).
- Manifest `weird` blocks at `:815` (seedless skip), `:867` (coordinates only), `:917` (persisted). The `already_connected` skip (`:759`) builds no packet and has no block. `MATURATION_MANIFEST_SCHEMA_VERSION` is unchanged.
- `_genesis_level` (`:1325`), `_resolve_maturation_weird` (`:1362`, `"level_source"` at `:1409`), `_load_story_weird_inputs` (`:1416`), `_manifest_weird_block` (`:1751`).
- A `nexus.toml` that still sets `[orrery.retrograde.maturation].weird_level` now fails config load:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
orrery.retrograde.maturation.weird_level
  Extra inputs are not permitted [type=extra_forbidden, input_value='medium', input_type=str]
```

## Read-Only Fleet Survey (2026-10-07)

`PGOPTIONS='-c default_transaction_read_only=on' psql -d save_NN -Atc "SELECT genesis_weird IS NULL, setting->>'genre' FROM global_variables"`

```
save_01: t|
save_02: t|
save_03: t|cyberpunk
save_04: t|cyberpunk
save_05: t|
NEXUS_template rows: 0
save_03 jobs: succeeded|12
save_04 jobs: succeeded|3
```

Every slot has a NULL `genesis_weird`, so each resolves `no_genesis_record` at `default_level = "medium"`: save_03 and save_04 stay at `medium`. save_01 and save_02 have no genre and save_05 no setting, so their maturation raises before resolution, before and after this change.

## Red Run

Plant A (`_resolve_maturation_weird` always uses `default_level`; reverted before commit):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_retrograde_maturation.py::test_maturation_weird_follows_selected_genesis_level
FAILED tests/test_orrery/test_retrograde_maturation.py::test_maturation_weird_follows_genesis_default_level
FAILED tests/test_orrery/test_retrograde_maturation.py::test_maturation_weird_resolves_band_from_current_tables
FAILED tests/test_orrery/test_retrograde_maturation.py::test_maturation_weird_rejects_malformed_genesis_record[unknown-level]
FAILED tests/test_orrery/test_retrograde_maturation.py::test_maturation_weird_rejects_malformed_genesis_record[selected-level-absent]
FAILED tests/test_orrery/test_retrograde_maturation.py::test_maturation_weird_rejects_malformed_genesis_record[selection-mismatch]
FAILED tests/test_orrery/test_retrograde_maturation.py::test_seedless_skip_manifest_records_weird
FAILED tests/test_live_gate_clones_pg.py::test_maturation_enqueue_is_idempotent_on_the_routed_clone
8 failed, 28 passed in 3.80s
```

Plant B (`genesis_weird=None` at the `_mature_one` call to the packet builder; reverted before commit):

```
E       AssertionError: assert 'medium' == 'high'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_retrograde_maturation.py::test_seedless_skip_manifest_records_weird
1 failed, 29 passed, 5 skipped, 5 warnings in 0.49s
```

## PostgreSQL Proof

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_live_gate_clones_pg.py tests/test_orrery/test_retrograde_maturation.py tests/test_orrery/test_retrograde_graph.py tests/test_orrery/test_character_name_replay.py tests/test_new_story_cache.py tests/test_api/test_wizard_weird_level.py tests/test_orrery/test_retrograde_summary_migration_contract.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py` (with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 18 targets: mock, postgres, qa640_885_ren_replay_* x4, qa640_maturation799_*, qa640_roster798_* x3, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*, qa838_genesis_weird_*, qa838_weird_level_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:55466 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:55494 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:55466 (psycopg2), save_04@local:55494 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
155 passed, 2 skipped, 7 warnings in 135.54s (0:02:15)
```

The two skips are `tests/test_orrery/test_card_identity.py:122` (`NEXUS_RUN_CORPUS=1` owner-corpus probes).

## Offline Suites

`$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```
FAILED tests/test_runtime/test_supervisor.py::test_check_children_still_fails_a_live_child_without_its_writer
1 failed, 2942 passed, 559 skipped, 8 warnings in 712.00s (0:11:51)
```

The failure (`Failed: DID NOT RAISE <class 'nexus.runtime.supervisor.RuntimeError_'>`, `tests/test_runtime/test_supervisor.py:1342`) is in a file this branch does not touch. Rerun of that file alone:

```
FAILED tests/test_runtime/test_supervisor.py::test_failed_start_keeps_the_record_when_the_writer_probe_cannot_run
1 failed, 70 passed, 5 warnings in 96.56s (0:01:36)
```

A different test failed on the rerun (`FileNotFoundError: ... state/echo.log`, `:1399`): timing under the shared machine's load, not this change.

`$PY -m pytest -q tests/test_api`:

```
FAILED tests/test_api/test_local_inference.py::test_activate_captures_through_the_writer_under_the_policy
1 failed, 654 passed, 262 skipped, 7 warnings in 72.32s (0:01:12)
```

(`assert not True`, `where True = pid_alive(44490)`; untouched file.) Rerun of that file alone:

```
34 passed, 7 warnings in 13.50s
```

`$PY -m pytest -q tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1220 passed, 1107 skipped, 7 warnings in 22.17s
```

`$PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
96 passed, 5 warnings in 18.59s
```

## Config, Lint, Types

- `PYTHONPATH=$PWD $PY scripts/validate_config_commit.py`: no output, exit 0 (the commit's `validate-config` hook: `Validate NEXUS config and model-ID drift....Passed`).
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`: `OK: exception disposition coverage and shrink-only baseline verified.`
- Black: `6 files left unchanged.`
- flake8 on the six changed Python files: the same 10 diagnostics on `origin/main` and the branch (line numbers shifted only): `retrograde_maturation.py` F401 `os` (`:34`), E501 (`:649`), F401 `require_slot_dbname` (`:732`); six E501 in `settings_models.py`; one E501 in `test_retrograde_maturation.py`. None on a changed line.
- `$PY -m mypy --explicit-package-bases` on the same six files: 44 errors on `origin/main`, 41 on the branch; the branch's set (line numbers removed) is a strict subset of main's (three `union-attr` diagnostics removed by the new `settings.orrery is not None` asserts). No new diagnostic.

## Document Freshness

`nexus.toml` is a declared source of `AGENTS.md` and `docs/turn_flow_sequence.md`. Neither names the runtime maturation level; both stay accurate, and each `verified_commit` moves to the merge base `364fef4b10ae0e7e0b63fc8e86cf292cca4087e4`. `docs/decisions/README.md` (the only other `status: canonical` document on main) declares `tests/test_doc_front_matter.py` and `README.md`, neither changed. No `docs/decisions/NNNN-*.md` from 817-S3 exists on main yet.

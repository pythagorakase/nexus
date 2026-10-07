# Verification: Data Clones Migrate Before They Pin (#1083)

Branch `claude/1083-migrate-before-pin`, cut from `origin/main` at 364fef4b.
Test infrastructure only: no migration, no restart, no UI rebuild, no paid call.

## The Defect at 364fef4b

- `tests/pg_fixtures.py:233` called `pin_clone()` and `tests/pg_fixtures.py:234`
  called `migrate.migrate_database(dbname, skip_locked=False)`, in that order, in
  the `include_data` branch of `disposable_slot_database`.
- `pin_clone()` writes through `write_story_settings`
  (`nexus/config/story_model.py:71`), whose UPDATE is executed at
  `nexus/config/story_model.py:88` and names `gaia_model`. That column arrives
  in `migrations/117_story_settings.sql`.
- `tests/test_orrery/test_migration_dead_strata_pg.py::_clone` (lines 318-336 at
  364fef4b) had the same order: restore, insert the story row and pin TEST, then
  migrate through the predecessor tree. Its sources (`NEXUS_template`,
  `save_01`..`save_05`) are all past 117, so it never failed; it is reordered
  the same way.

## Reference Corpus Columns (Read-Only)

```
$ PGOPTIONS='-c default_transaction_read_only=on' psql -d ref_codex_bakeoff_2026_07 -Atc "SELECT max(version) FROM schema_migrations"
114
$ PGOPTIONS='-c default_transaction_read_only=on' psql -d ref_codex_bakeoff_2026_07 -Atc "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='global_variables' ORDER BY ordinal_position"
id
base_timestamp
user_character
setting
new_story
model
slot_number
last_played
slot_created_at
is_active
```

No `gaia_model` column. Its model-bearing job tables hold no active work, so
migration 126's backfill (which freezes queued or leased jobs' models from the
pin it finds, for a data clone the source's pin) has nothing to resolve on this
source. That is a fact about this corpus, not a property of the pin order; the
fixture guard below enforces it for every source:

```
character_experience_jobs: (no rows)
orrery_maturation_jobs: succeeded|10
correspondence_compaction_jobs: relation does not exist at 114
narrative_summary_jobs: relation does not exist at 114
```

## Pin Sites Checked

`grep -rn "pin_clone\|write_story_settings\|story_pin=" tests/ scripts/qa_shift/`
finds: `tests/pg_fixtures.py` (fixed); `tests/test_orrery/test_migration_dead_strata_pg.py`
(restores a dump, pins, migrates: fixed); `tests/test_routine_delta_grammar_probe_pg.py:78`
(pins a template clone that `disposable_slot_database` already migrated: no
change); the `story_pin=None` live tests and `tests/test_lore/test_token_estimator.py:453`
(callers, not pin sites). Nothing under `scripts/qa_shift/`.

## Red at 364fef4b

`NEXUS_RUN_CORPUS=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_pg_fixtures_corpus_clone.py`
(the new test, run before the fixture change; the fixture setup fails before the test body runs):

```
E                                                                        [100%]
E       psycopg2.errors.UndefinedColumn: column "gaia_model" of relation "global_variables" does not exist
E       LINE 1: UPDATE global_variables SET "model" = 'TEST', "gaia_model" =...
E                                                             ^
nexus/config/story_model.py:88: UndefinedColumn
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_1083_ref_corpus_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
ERROR tests/test_pg_fixtures_corpus_clone.py::test_reference_corpus_clones_with_data_and_pins_after_migrating
1 error in 1.58s
```

## Green After

Same command:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_1083_ref_corpus_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed in 3.83s
```

PostgreSQL proof set, `NEXUS_RUN_CORPUS=1 NEXUS_RUN_POSTGRES=1 ... -p tests.dbname_audit
tests/test_connection_lifecycle.py tests/test_orrery/test_card_identity.py
tests/test_scheduler_helpers_routing.py tests/test_owner_target_guard.py
tests/test_lore/test_infrastructure.py` (`tests/test_pg_fixtures.py` does not exist;
`test_card_identity.py` and `test_lore/test_infrastructure.py` are existing
`include_data` consumers cloning `save_04` and `save_01`):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 11 targets: mock, postgres, qa640_781_cards_* x2, qa640_885_ren_replay_* x4, qa640_lane_close_*, qa_lore_corpus_*, qa_lore_infra_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:63677 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:63679 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:63677 (psycopg2), save_04@local:63679 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
112 passed, 7 warnings in 62.25s (0:01:02)
```

`NEXUS_RUN_CORPUS=1 NEXUS_RUN_POSTGRES=1 ... -p tests.dbname_audit
tests/test_orrery/test_migration_dead_strata_pg.py` (fleet clone test included):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 549 targets: postgres, qa640_813_case_* x548
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
548 passed in 1514.85s (0:25:14)
```

No `qa640_` database remained after the runs
(`psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640%'"`
printed nothing).

## Review Fix: Migration 126 Backfill Guard (Commit 423a4107)

Review found that migrate-first lets `migrations/126_seat_policies.py` freeze
`resolved_model` on queued or leased jobs under the source's pin (the pin is
written only afterward, and the column is immutable across repins), while the
docstring claimed test code never sees the source's pin. Of the two fixes
offered, this branch takes the fixture guard (keep migrate-first, fail loudly),
not the two-phase migrate:

- `tests/pg_fixtures.py`: before migrating a data clone, the fixture records
  whether `schema_migrations` already holds `126`. If it did not and
  `story_pin` is set, `_refuse_source_pin_backfill` runs after migrating and
  before `pin_clone()`; it counts rows with `state IN ('queued', 'leased') AND
  resolved_source = 'migration_backfill'` in the four tables of 126's
  `JOB_SEATS` and raises `RuntimeError` naming the table and the clone. The
  docstring now states the guarantee that holds: `global_variables` reads TEST,
  migration 126 is the exception the pin cannot reach and is refused, and jobs
  the source resolved before the clone keep their models.
- `tests/test_pg_fixtures_corpus_clone.py`: the comment over the backfill loop
  now says the loop records this corpus's precondition (no active jobs) and
  points at the fixture guard; the table list is imported from the fixture.

The guard fires. Scratch proof
(`scratchpad/1083/guard_fires_proof.py`, run with `NEXUS_TEST_PROVIDER_ONLY=1`
and `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset): restore the
reference corpus's `pg_dump` into a disposable `qa640_1083_src_*` database, set
its first (succeeded) `orrery_maturation_jobs` row to `queued`, then clone that
source with data:

```
source qa640_1083_src_e95492828245 queued job id 1
RuntimeError: Data clone qa640_1083_guard_2302de379586: migration 126 froze 1 active orrery_maturation_jobs rows under the source's story pin, which the TEST pin cannot replace
```

Both disposable databases were dropped (the `qa640%` query afterward printed
nothing). The reference corpus itself was read only through `pg_dump`.

Tails on 423a4107:

`NEXUS_RUN_CORPUS=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_pg_fixtures_corpus_clone.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_1083_ref_corpus_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed in 3.45s
```

`NEXUS_RUN_CORPUS=1 NEXUS_RUN_POSTGRES=1 ... -p tests.dbname_audit tests/test_connection_lifecycle.py
tests/test_orrery/test_card_identity.py tests/test_scheduler_helpers_routing.py
tests/test_owner_target_guard.py tests/test_lore/test_infrastructure.py` (the
`save_04` and `save_01` data clones are past 126, so the guard does not run for
them):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 11 targets: mock, postgres, qa640_781_cards_* x2, qa640_885_ren_replay_* x4, qa640_lane_close_*, qa_lore_corpus_*, qa_lore_infra_*
dbname audit: owner server: local:5432
dbname audit: owner targets: none
112 passed, 7 warnings in 63.71s (0:01:03)
```

Offline: `tests/test_pg_target_contract.py tests/test_doc_front_matter.py
tests/test_reachability.py`: `204 passed, 1 skipped, 5 warnings in 18.61s`
(guard line present). `black --check` (2 files unchanged), `flake8` (no
output), `mypy --explicit-package-bases` (`Success: no issues found in 2 source
files`), `check_exception_dispositions.py --baseline-base-ref origin/main`
(`OK`). No `qa640_` database remained.

## Offline Gates

Offline suites (no PostgreSQL flags), split by directory:

```
tests/test_*.py:                     1985 passed, 477 skipped, 8 warnings in 397.72s (0:06:37)
tests/config tests/fixtures tests/proofs tests/test_config tests/test_ir_eval_v2
tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util:
                                     544 passed, 26 skipped, 7 warnings in 107.92s (0:01:47)
tests/test_api tests/test_lore:      1069 passed, 317 skipped, 7 warnings in 58.39s
tests/test_orrery:                   1210 passed, 1107 skipped, 7 warnings in 11.82s
tests/test_reachability.py tests/test_doc_front_matter.py: 96 passed, 5 warnings in 15.13s
```

Every tail carried `secret-store guard: active; nexus-api: denied; disposable keychain: denied`.
The first top-level run, before `AGENTS.md` was re-stamped, failed
`tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit`
(`AGENTS.md: tests/pg_fixtures.py changed since the merge base 364fef4b10ae without a
re-stamped verified_commit`); `AGENTS.md` names `tests/pg_fixtures.py` in `sources:`,
its text about the fixtures stays accurate, and `verified_commit` now names the merge
base 364fef4b10ae0e7e0b63fc8e86cf292cca4087e4.

Static checks on the changed Python files: `black --check` (3 files unchanged),
`flake8` (no output), `mypy --explicit-package-bases` (`Success: no issues found in
3 source files`), `python -S scripts/check_exception_dispositions.py --baseline-base-ref
origin/main` (`OK: exception disposition coverage and shrink-only baseline verified.`).

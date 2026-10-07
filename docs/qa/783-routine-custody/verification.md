# Verification: Routine-Anchor Custody (#783 S1a, Migration 145)

Branch `claude/783-routine-custody`, cut from `origin/main` at 364fef4b. `origin/main` had not moved when the proof ran (2026-10-07 13:38-13:55 CDT), so the proof ran on the merged tree. No paid call, no gateway lane, no write to any `save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07`.

## Resumed on 2026-10-07

The coordinator stopped the earlier builder at 12:50 CDT (machine load, not a defect). The worktree was clean (`git status --short` empty); nothing uncommitted was discarded.

| Commit | Order items covered | Left unfinished |
| --- | --- | --- |
| 0b231859 Add migration 145 | Item 1 (enum, ledger table, index, `last_log_id`, nullable schedule with no default, comments as amended by the coordinator) | Nothing |
| c0a85953 Add routine-anchor custody model, validator and sync/async writer | Items 2 and 3 (`routine_anchors.py`); offline shape tests | Nothing |
| 105437e4 Prove routine-anchor custody on PostgreSQL clones | Tests: enum parity, scenarios, revise and clear, refusals in both twins, twin agreement, place deletion, nullable column | Nothing |
| 7cd40199 Prove an identical upsert still writes a ledger row | Item 3, last sentence | Nothing |
| (none) | Proof, red run, evidence file, merge, PR | All of it; done in this session |

This session added one commit, 22d110c2, which writes the `mobility_policy` description as one string literal (Black had left `"... authored " "absence."`); the text is unchanged and still equals the 783-S0 probe (`scripts/qa_shift/routine_delta_grammar_probe.py:141-142`).

## Cited Lines (Checked at 364fef4b)

- `migrations/056_orrery_routine_anchors.py:67` `schedule jsonb NOT NULL DEFAULT '{}'::jsonb`; `:68` `source text NOT NULL DEFAULT 'manual'`; `:119-123` "Empty JSON means always due"; `:124-125` "Human/source provenance for the anchor."
- `migrations/056_orrery_routine_anchors.py:58` `CREATE TABLE IF NOT EXISTS character_routine_anchors (`; `:63-64` `place_id bigint REFERENCES places(id) ON DELETE SET NULL,` and `zone_id bigint REFERENCES zones(id) ON DELETE SET NULL,`; `:72` `CHECK (` (the first of the two CHECKs).
- `nexus/agents/orrery/resolver.py:870` `def _load_routine_anchors(session: Any) -> dict[tuple[int, str], RoutineAnchor]:`; `:878` `SELECT cra.character_entity_id,`; `:898` `schedule=row.get("schedule") or {}` (the NULL coercion, 783-S1c).
- `nexus/agents/orrery/substrate.py:1767` `if anchor.mobility_policy == "works_from_home":`; `:1770` `return _at_routine_anchor(state, entity_id, "home")`.
- `nexus/agents/orrery/substrate.py:1798` `if anchor.mobility_policy == "works_from_home":`; `:1801-1804` `return _routine_anchor_destination_available(` ... `"home",`.
- `nexus/agents/orrery/substrate.py:1810` `def _routine_schedule_due(`; `:1833` `def _minute_of_day(value: Any) -> Optional[int]:`; `:1839` `raise ValueError(f"Routine schedule time must be HH:MM, got {raw!r}")`; `:1846` `raise ValueError(f"Routine schedule time out of range: {raw!r}")`.
- `nexus/agents/orrery/replay.py:58-59` `` ``character_routine_anchors`` — checkpoint pass-through (no runtime `` / `writer; offline seed scripts mutate it invisibly between checkpoints).`
- `nexus/agents/orrery/replay.py:1234` `result.state["character_routine_anchors"] = sorted(`; `:1240-1241` `"checkpoint pass-through; the table has no runtime writer, but "` / `"offline seed/backfill scripts are invisible between checkpoints",`.
- `nexus/agents/orrery/reconstruction.py:139-142` `"character_routine_anchors": (` / `"SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "` / `"FROM character_routine_anchors t"`.
- `nexus/api/new_story_db_mapper.py:569` `# Delete in reverse dependency order (children before parents)`; `:583-584` `DELETE FROM places;` / `DELETE FROM zones;` (the range :569-586 holds the whole delete statement).
- `nexus/agents/orrery/retrograde_maturation.py:387` `def _require_accepting_world_time(`; `nexus/api/commit_handler_sync.py:144` `def _require_chunk_world_time_sync(`; `:1050` and `:1089` `writer="skald_state_update"`.
- `nexus/agents/orrery/retrograde_maturation.py:387` `def _require_accepting_world_time(cur: Any, chunk_id: int) -> datetime:`; `nexus/api/commit_handler_sync.py:144` `def _require_chunk_world_time_sync(cur: Any, chunk_id: int) -> datetime:`.
- `migrations/139_character_relationship_bigint_ids.sql:82` `-- Locks: ALTER TABLE ... TYPE rewrites character_relationships under an` (the lock paragraph 145 models).
- Inserts outside custody: `tests/pg_fixtures.py:1331` and `tests/test_orrery/test_claim_birth_coverage_pg.py:234` (`INSERT INTO character_routine_anchors (`); `scripts/backfill_routine_anchors.py:235` `INSERT INTO character_routine_anchors (` with `:240` `:mobility_policy, '{}'::jsonb, 'compiler_backfill'`; `scripts/seed_slot2_routine_anchors.py:87` `INSERT INTO character_routine_anchors (` with `:92` `'fixed_place', %s::jsonb, 'slot2_reference_seed'`.
- `tests/test_connection_lifecycle.py:128-129`: the `world_events` insert the custody tests copy.

## Fleet (Read-Only, 2026-10-07)

`PGOPTIONS='-c default_transaction_read_only=on' psql -X -At -d <db> -c "SELECT (SELECT count(*) FROM character_routine_anchors) || ' rows; migration ' || (SELECT max(version) FROM schema_migrations)"`

```
NEXUS_template 0 rows; migration 143
save_01 0 rows; migration 143
save_02 0 rows; migration 143
save_03 0 rows; migration 143
save_04 0 rows; migration 143
save_05 0 rows; migration 143
```

## Comments on a Migrated Clone

A disposable `qa640_783s1a_doc_*` clone (created and dropped by `tests.pg_fixtures.disposable_slot_database`), migrated to 145, listed with `obj_description`/`col_description` by the committed script `docs/qa/783-routine-custody/comment_listing.py` (its SQL is inline). The same script parses every `COMMENT ON` literal from `migrations/145_routine_anchor_custody.sql` and compares the listing with it, object by object; the last line prints `<listed> <in migration> equal`. Rerun on a2b90a74 (2026-10-07 14:06 CDT), output below without the fixture's `psql` restore chatter:

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY docs/qa/783-routine-custody/comment_listing.py`

Afterward `psql -X -At -d postgres -c "SELECT count(*) FROM pg_database WHERE datname LIKE 'qa640_783s1a%'"` printed `0`.

```
clone migrated to 145
TYPE orrery_routine_anchor_writer | Writer of one routine-anchor custody change: skald_state_update (the Gaia state-update commit), retrograde_expansion (wizard-time Retrograde, the genesis writer), retrograde_maturation, relocation_arrival (the verified arrival that completes an accepted relocation), offline_ladder (the reviewed offline backfill and seed scripts).
TABLE character_routine_anchor_log | Append-only history of every routine-anchor upsert and clear written through custody (nexus.agents.orrery.routine_anchors), one row per change, inserted in the transaction of the change, ordered by source_chunk_id, then chunk_sequence.
COLUMN character_routine_anchor_log.id | Ledger row identifier.
COLUMN character_routine_anchor_log.character_entity_id | Character entity whose anchor changed.
COLUMN character_routine_anchor_log.anchor_type | Anchor that changed (home or work).
COLUMN character_routine_anchor_log.operation | upsert writes the anchor in after_image; clear deletes the anchor, which returns it to unknown.
COLUMN character_routine_anchor_log.writer_kind | Custody writer that made the change.
COLUMN character_routine_anchor_log.source_chunk_id | Accepted chunk the change belongs to; replay applies it at this chunk.
COLUMN character_routine_anchor_log.chunk_sequence | Order of the change among the changes with the same source_chunk_id, from 1.
COLUMN character_routine_anchor_log.source_event_id | World event that caused the change, when the writer names one; NULL otherwise.
COLUMN character_routine_anchor_log.world_time | Story clock of the change: chunk_metadata.world_time of source_chunk_id when custody wrote it.
COLUMN character_routine_anchor_log.before_image | The anchor before the change as an object with the keys mobility_policy, place_id, zone_id and schedule; NULL when no anchor existed.
COLUMN character_routine_anchor_log.after_image | The anchor after an upsert, in the before_image shape; NULL for a clear.
COLUMN character_routine_anchor_log.recorded_at | Operational wall-clock insert time; never story time.
COLUMN character_routine_anchors.schedule | Authored timing as a JSON object, or NULL when the timing is unknown. {"always": true} is authored always-due. Otherwise the keys are weekdays (Python weekday() numbers, 0=Monday through 6=Sunday; absent means every day), start and end (zero-padded HH:MM; an end earlier than the start crosses midnight). A schedule without start or end keeps its known keys and has unknown hours.
COLUMN character_routine_anchors.source | Writer label: the orrery_routine_anchor_writer value for a row written through custody; free text for a row written outside it.
COLUMN character_routine_anchors.last_log_id | character_routine_anchor_log row of the latest custody upsert of this anchor; NULL when the row was written outside custody.
17 17 equal
```

## Red Run

Plant (reverted before commit): both twins' final `_refuse_homeless_works_from_home(batch, policies)` replaced with `pass`.

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_routine_anchor_custody_pg.py -k works_from_home`

```
E       Failed: DID NOT RAISE <class 'nexus.agents.orrery.routine_anchors.RoutineAnchorCustodyError'>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_refusals_change_nothing[works_from_home_without_home-sync]
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_refusals_change_nothing[works_from_home_without_home-async]
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_refusals_change_nothing[clear_home_under_works_from_home-sync]
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_refusals_change_nothing[clear_home_under_works_from_home-async]
4 failed, 1 passed, 30 deselected in 8.22s
```

(The one pass is the `works_from_home_with_fixed_home` scenario.)

## Proof

Machine-load rule: the whole PostgreSQL gate and its three-piece split were not run; the coordinator runs it at landing. The focused set below includes `tests/test_orrery/test_card_identity.py` and `tests/test_connection_lifecycle.py`. One-minute load before the PostgreSQL runs: 5.86 and 7.97 (below 24, no wait). One pytest session at a time, each under `nice -n 15`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.

PostgreSQL, piece 1: `NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_routine_anchor_custody_pg.py tests/test_orrery/test_routine_anchors.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_new_story_setup.py`

```
E       AssertionError: assert {'013', '119', '144'} == frozenset({'013', '119'})
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 227 passed in 87.80s (0:01:27)
```

The one failure is the expected gap: 144 belongs to 778-S1b, which has not merged. `KNOWN_GAPS` is unchanged.

PostgreSQL, piece 2: `NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_pg_anchor_pair_tag_seeds.py tests/test_pg_disposable_target.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_claim_birth_coverage_pg.py tests/test_orrery/test_replay.py tests/test_orrery/test_reconstruction.py tests/test_api/test_orrery_dev_endpoints.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
168 passed, 2 skipped, 7 warnings in 82.68s (0:01:22)
```

The two skips are `tests/test_orrery/test_card_identity.py:122` ("Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones."), confirmed on a2b90a74 with:

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_orrery/test_card_identity.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
9 passed, 2 skipped, 2 warnings in 10.78s
```

Offline (`NEXUS_RUN_POSTGRES` unset):

```
$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2943 passed, 559 skipped, 8 warnings in 521.85s (0:08:41)

$PY -m pytest -q tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
655 passed, 262 skipped, 7 warnings in 35.88s

$PY -m pytest -q tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1279 passed, 1142 skipped, 7 warnings in 12.10s

$PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
96 passed, 5 warnings in 15.42s
```

The `tests/test_api tests/test_orrery` session was split in two to stay under the ten-minute tool limit.

Static checks on the three new Python files (all new, so there is no `origin/main` baseline to compare):

```
$PY -m black --check <3 files>        3 files would be left unchanged.
$PY -m flake8 <3 files>               (no output, rc=0)
$PY -m mypy --explicit-package-bases <3 files>   Success: no issues found in 3 source files
$PY scripts/check_migration_comments.py           OK: every object created after migration 129 has a comment.
$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
                                      OK: exception disposition coverage and shrink-only baseline verified.
```

Document freshness: `git diff --name-only origin/main...HEAD` touches no declared source of `AGENTS.md`, `docs/turn_flow_sequence.md` or `docs/decisions/README.md`.

## Review Fixes (Commit a2b90a74)

Confirmed review findings applied: the `RoutineAnchorCustodyError` docstring (and the async twin's) says the final works_from_home check raises after the writes, so the caller must roll back; `RoutineSchedule.always` is `StrictBool`, `weekdays` is `list[StrictInt]`, and `RoutineAnchorChange` ids are `StrictInt` (the bool before-validator stays as the message source for a list or tuple); two refusal cases (a works_from_home work anchor over a `nomadic` and over a `none` home); a RealDictCursor caller test for the sync twin's own cursor; this file's cited lines, listing command and `-rs` command. All tails below ran on a2b90a74 (the working tree equal to it before commit) at 14:03-14:06 CDT; one-minute load 6.60-7.73, no wait.

Offline model tests: `env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_orrery/test_routine_anchors.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
82 passed, 5 warnings in 0.34s
```

Custody on PostgreSQL: `env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_orrery/test_routine_anchor_custody_pg.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 42 targets: postgres, qa640_783s1a_* x41
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
40 passed in 93.77s (0:01:33)
```

Red run, home policy (mutant reverted before commit): in `_refuse_homeless_works_from_home`, `if home_policy in _HOME_DESTINATION_POLICIES:` replaced with `if home_policy is not None:`, so any existing home passes. Same command with `-k works_from_home`:

```
E       Failed: DID NOT RAISE <class 'nexus.agents.orrery.routine_anchors.RoutineAnchorCustodyError'>   (x4)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_refusals_change_nothing[works_from_home_over_nomadic_home-sync]
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_refusals_change_nothing[works_from_home_over_nomadic_home-async]
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_refusals_change_nothing[works_from_home_over_none_home-sync]
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_refusals_change_nothing[works_from_home_over_none_home-async]
4 failed, 5 passed, 31 deselected in 16.89s
```

Red run, own cursor (mutant reverted before commit): the sync twin's `conn.cursor(cursor_factory=psycopg2.extensions.cursor)` replaced with a bare `conn.cursor()`. Same command with `-k own_plain_cursor`:

```
E           KeyError: 0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_routine_anchor_custody_pg.py::test_sync_twin_runs_on_its_own_plain_cursor
1 failed, 39 deselected in 1.81s
```

Other checks on a2b90a74:

```
$PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
176 passed, 5 warnings in 19.50s

$PY -m black <3 changed files + comment_listing.py>   left unchanged
$PY -m flake8 <same 4 files>                          (no output, rc=0)
$PY -m mypy --explicit-package-bases <3 changed files>   Success: no issues found in 3 source files
$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
                                      OK: exception disposition coverage and shrink-only baseline verified.
```

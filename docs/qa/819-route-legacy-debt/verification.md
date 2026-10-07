# 819-S3 Verification: Route the Legacy Debt

Order 819-S3 applies decision 819-Q1 to the 15 entries left in
`config/schema_docs_baseline.json` after migration 143 (#1098). Branch
`claude/819-route-legacy-debt`, cut from `origin/main` at `364fef4b`. No
migration, no `COMMENT ON`, no drop, no paid call, no gateway. Every SQL
statement below ran read-only (`PGOPTIONS='-c default_transaction_read_only=on'`).

## Cited Lines as Found at `364fef4b`

- `config/schema_docs_baseline.json:2-16`: 15 entries (nine `column:`, six
  `function:`); no reason named where the debt is routed.
- `docs/dead_retrieval_subtraction.md:3-5` (intro, no baseline mention),
  `:127` (`### Deferred Vector-Helper Function Manifest`), `:135-140` (the six
  function identities), `:147` (`...neither recreates nor edits them.`), `:154`
  (last line). No section listed the nine columns.
- `migrations/007_normalize_new_story_creator.sql:118,121,123,134,135`:
  `seed_starting_location text`, `seed_initial_mystery text`,
  `seed_potential_obstacles text[]`, `zone_boundary_description text`,
  `zone_approximate_area text`.
- `nexus/api/new_story_cache.py`: `write_seed` (def `:1136`, NULLs at
  `:1177-1188`), `clear_seed_phase` (def `:1334`, `:1348-1361`),
  `clear_character_phase` (def `:1371`, `:1397-1410`), `clear_setting_phase`
  (def `:1429`, `:1471-1484`), `write_cache` (def `:1509`, `:1694-1738`). Every
  reference sets the column to NULL.
- `migrations/023_orrery_schema.py:508` `clear_on_override jsonb`; `:582`
  `narration_chunk_id bigint`; `:624-625` `provider text`, `model_ref text`.
- `migrations/046_canonical_grieving_state.py:58-64`: copies
  `et.clear_on_override` into a new `entity_tags` row (historical only).
- `nexus/agents/orrery/worker.py:244-245`: "Existing provider-era jobs use the
  same lease and anchor fences. Their provider/model provenance is retained,
  but never used to make a call."
- `nexus/agents/orrery/worker.py:816-832` (`_mark_promoted`): `INSERT INTO
  orrery_narration_jobs (resolution_id, slot, anchor_tick_chunk_id,
  anchor_world_layer, generation_session_id)`; neither `provider` nor
  `model_ref`.
- `nexus/agents/orrery/worker.py:639-647`: `UPDATE orrery_resolutions SET
  narration_status = 'succeeded', narration_chunk_id = %s`. `bleed.py:241,435`
  read `r.narration_chunk_id` from `orrery_resolutions r`.
- `NEXUS_template`: `world_events_narration_chunk_id_fkey | FOREIGN KEY
  (narration_chunk_id) REFERENCES offscreen_narrations(id)`.

## `git grep` Checks (Run at the Branch Head)

```
$ git grep -nE 'seed_starting_location|seed_initial_mystery|seed_potential_obstacles|zone_boundary_description|zone_approximate_area' -- nexus scripts ui/client/src
nexus/api/new_story_cache.py:1177:                    seed_starting_location = NULL,
nexus/api/new_story_cache.py:1178:                    seed_initial_mystery = NULL,
nexus/api/new_story_cache.py:1180:                    seed_potential_obstacles = NULL,
nexus/api/new_story_cache.py:1187:                    zone_boundary_description = NULL,
nexus/api/new_story_cache.py:1188:                    zone_approximate_area = NULL,
nexus/api/new_story_cache.py:1348:                    seed_starting_location = NULL,
nexus/api/new_story_cache.py:1351:                    seed_initial_mystery = NULL,
nexus/api/new_story_cache.py:1353:                    seed_potential_obstacles = NULL,
nexus/api/new_story_cache.py:1360:                    zone_boundary_description = NULL,
nexus/api/new_story_cache.py:1361:                    zone_approximate_area = NULL,
nexus/api/new_story_cache.py:1397:                    seed_starting_location = NULL,
nexus/api/new_story_cache.py:1400:                    seed_initial_mystery = NULL,
nexus/api/new_story_cache.py:1402:                    seed_potential_obstacles = NULL,
nexus/api/new_story_cache.py:1409:                    zone_boundary_description = NULL,
nexus/api/new_story_cache.py:1410:                    zone_approximate_area = NULL,
nexus/api/new_story_cache.py:1471:                    seed_starting_location = NULL,
nexus/api/new_story_cache.py:1474:                    seed_initial_mystery = NULL,
nexus/api/new_story_cache.py:1476:                    seed_potential_obstacles = NULL,
nexus/api/new_story_cache.py:1483:                    zone_boundary_description = NULL,
nexus/api/new_story_cache.py:1484:                    zone_approximate_area = NULL,
nexus/api/new_story_cache.py:1694:                        "seed_starting_location = NULL",
nexus/api/new_story_cache.py:1695:                        "seed_initial_mystery = NULL",
nexus/api/new_story_cache.py:1697:                        "seed_potential_obstacles = NULL",
nexus/api/new_story_cache.py:1737:                        "zone_boundary_description = NULL",
nexus/api/new_story_cache.py:1738:                        "zone_approximate_area = NULL",
```

25 lines, all in `nexus/api/new_story_cache.py`, all `= NULL`.

```
$ git grep -n clear_on_override -- nexus scripts tests ui/client/src
tests/test_orrery/test_build_venture_async.py:59:            applied_at_world_time timestamptz, clear_on_override jsonb,
tests/test_orrery/test_build_venture_projects.py:220:            applied_at_world_time timestamptz, clear_on_override jsonb,
tests/test_orrery/test_build_venture_replay.py:59:            applied_at_world_time timestamptz, clear_on_override jsonb,
tests/test_orrery/test_mood_live.py:72:            clear_on_override jsonb, cleared_at timestamptz,
```

Exactly the four fixture table declarations; none reads or writes the column.

```
$ git grep -n narration_chunk_id -- nexus scripts ui/client/src
nexus/agents/orrery/bleed.py:241:            JOIN offscreen_narrations n ON n.id = r.narration_chunk_id
nexus/agents/orrery/bleed.py:435:            JOIN offscreen_narrations n ON n.id = r.narration_chunk_id
nexus/agents/orrery/worker.py:643:            narration_chunk_id = %s
```

All three are `orrery_resolutions` (alias `r` in `bleed.py`; `UPDATE
orrery_resolutions` at `worker.py:641`). None touches `world_events`.

```
$ git grep -nwE 'provider|model_ref' -- nexus/agents/orrery/worker.py
nexus/agents/orrery/worker.py:123:            "Select the registered TEST provider in settings for scheduler proofs"
nexus/agents/orrery/worker.py:156:    provider: Optional[Any] = None,
nexus/agents/orrery/worker.py:168:            provider=provider,
nexus/agents/orrery/worker.py:244:    Existing provider-era jobs use the same lease and anchor fences. Their
nexus/agents/orrery/worker.py:245:    provider/model provenance is retained, but never used to make a call.
```

Lines 123, 156, 168, 244 and 245; none is SQL.

## Fleet Counts (Read-Only, 2026-10-07)

Each database was queried with
`PGOPTIONS='-c default_transaction_read_only=on' psql -d <db> -Atc '<sql>'`:

- Q1: `select count(*) filter (where seed_starting_location is not null or seed_initial_mystery is not null or seed_potential_obstacles is not null or zone_boundary_description is not null or zone_approximate_area is not null), count(*) from assets.new_story_creator`
- Q2: `select count(*) filter (where clear_on_override is not null), count(*) from entity_tags`
- Q3: `select count(*) filter (where provider is not null), count(*) filter (where model_ref is not null), count(*) from orrery_narration_jobs`
- Q4: `select count(*) filter (where narration_chunk_id is not null), count(*) from world_events`
- Version: `select max(version) from schema_migrations`

| Database | Q1 | Q2 | Q3 | Q4 | Version |
| --- | --- | --- | --- | --- | --- |
| `NEXUS_template` | `0\|0` | `0\|0` | `0\|0\|0` | `0\|0` | 143 |
| `save_01` | `0\|0` | `0\|0` | `0\|0\|0` | `0\|0` | 143 |
| `save_02` | `0\|0` | `0\|0` | `0\|0\|0` | `0\|0` | 143 |
| `save_03` | `0\|0` | `0\|35` | `9\|9\|9` | `0\|96` | 143 |
| `save_04` | `0\|0` | `0\|42` | `0\|0\|0` | `0\|133` | 143 |
| `save_05` | `0\|1` | `0\|0` | `0\|0\|0` | `0\|0` | 143 |

Every non-NULL count is 0 except `orrery_narration_jobs` in `save_03`
(`9|9|9`), as the order expected.

## Key Identity

```
$ diff <(git show origin/main:config/schema_docs_baseline.json | jq -r 'keys_unsorted[]') <(jq -r 'keys_unsorted[]' config/schema_docs_baseline.json) && echo KEYS-IDENTICAL
KEYS-IDENTICAL
```

The edit script also asserted that the original file reproduces byte for byte
under `json.dumps(indent=2, ensure_ascii=False)` plus a final newline before it
appended one sentence to each reason, so the indent, key order, existing
sentences and final newline are unchanged.

## Red Runs

Each plant was made in the worktree copy after saving the original under the
session scratchpad (`819-S3/`), then the original was restored; `cmp` against
the saved copies printed `restored-identical` and `git diff --stat` showed only
the intended two-file change.

(a) Deleted the appended sentence from the
`column:public.world_events.narration_chunk_id` reason:

```
E       AssertionError: column:public.world_events.narration_chunk_id: reason names no section of dead_retrieval_subtraction.md: 'No current writer establishes this legacy narration link; do not infer the contract from the similarly named resolution column.'
E       assert None
=========================== short test summary info ============================
FAILED tests/test_schema_docs_baseline_routing.py::test_every_baseline_reason_names_a_manifest_section
FAILED tests/test_schema_docs_baseline_routing.py::test_every_baseline_object_is_listed_in_its_section
2 failed, 5 warnings in 0.27s
```

The first test fails as ordered. The second also fails, because it resolves
each key's section through the same pointer before it looks for the
identifier.

(b) Deleted the `` - `public.migrate_embeddings()`. `` line from the manifest:

```
E           AssertionError: function:public.migrate_embeddings(): `public.migrate_embeddings()` is not listed in section 'Deferred Vector-Helper Function Manifest' of dead_retrieval_subtraction.md
=========================== short test summary info ============================
FAILED tests/test_schema_docs_baseline_routing.py::test_every_baseline_object_is_listed_in_its_section
1 failed, 1 passed, 5 warnings in 0.28s
```

## Gate Tails

`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset for every run.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_schema_documentation_pg.py
.................................                                        [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_docs_refresh_*, qa640_schema_docs_* x3
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
33 passed in 5.22s
```

```
$ $PY -m pytest -q tests/test_schema_docs_baseline_routing.py tests/test_doc_front_matter.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
98 passed, 5 warnings in 16.23s
```

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_failed_start_keeps_the_record_when_the_writer_probe_cannot_run
1 failed, 2944 passed, 559 skipped, 8 warnings in 617.59s (0:10:17)
```

The failure is `FileNotFoundError: ... /state/echo.log` inside a file this
branch does not touch. One rerun of that file:

```
$ $PY -m pytest -q tests/test_runtime/test_supervisor.py
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_doctor_fails_a_live_service_without_its_writer
1 failed, 70 passed, 5 warnings in 50.99s
```

The rerun fails a different test of the same file (`assert 'pass' == 'fail'`);
the first one passed. Reported for the coordinator, not fixed.

```
$ $PY -m pytest -q tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
655 passed, 262 skipped, 7 warnings in 43.69s
```

```
$ $PY -m pytest -q tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1210 passed, 1107 skipped, 7 warnings in 17.88s
```

## Static Checks

```
$ $PY -m black --check tests/test_schema_docs_baseline_routing.py
1 file would be left unchanged.
$ $PY -m flake8 tests/test_schema_docs_baseline_routing.py
(no output)
$ $PY -m mypy --explicit-package-bases tests/test_schema_docs_baseline_routing.py
Success: no issues found in 1 source file
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
$ $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
```

The new test file is the only Python file changed, so there are no
pre-existing diagnostics to compare.

## Document Freshness

`git diff --name-only origin/main...HEAD` touches no path in the `sources:`
lists of `AGENTS.md`, `docs/turn_flow_sequence.md` or `docs/decisions/README.md`
(the three `status: canonical` documents), so no `verified_commit` moves.

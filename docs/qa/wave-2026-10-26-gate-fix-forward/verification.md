# Fix Forward From the 2026-10-26 Final Gate

Branch `claude/wave-gate-fix-forward`, cut from main `11229615`. The gate ran on
`36abe1b0`. The one commit between them (PR #1167) changes CI, documents, test markers
and `pytest.ini` (a marker registration). It touches neither failing test, nor their
routes, nor `tests/pg_fixtures.py`. The test changes are commit `24ca3f99`.
Refs #824, #813.

## The Gate and Its Three Failures

The wave's final whole-tree PostgreSQL gate on main `36abe1b0` ended as follows. The
log, `temp/orders_2026_10_26/coord/final-wholetree-36abe1b0.log`, is not committed.

```
FAILED tests/test_api/test_narrative_continue_validation.py::test_concurrent_continues_have_one_owner_and_truthful_result[False]
FAILED tests/test_api/test_narrative_continue_validation.py::test_concurrent_continues_have_one_owner_and_truthful_result[True]
FAILED tests/test_api/test_set_designer_failure.py::test_chat_set_design_write_failure_returns_500_without_design_draft
3 failed, 7447 passed, 84 skipped, 35 warnings in 7246.89s (2:00:46)
```

Both causes are deterministic. In each, a landed PR met a test outside its proof set.

1. **The concurrent-continue test (both parametrizations), from PR #1169 (issue #824).**
   PR #1169 made `gateway_lifespan` refuse a second concurrent run in one process. The
   flag on `app.state` is checked at `nexus/api/narrative.py:133-137`, set at `:138`
   and cleared in the `finally` at `:162`. Projections run the same lifespan against
   the source app, so the flag always lives on `narrative.app.state`. The test's
   `post_continue()` helper opened a fresh `TestClient(narrative.app)` context per
   request. The competitor's client therefore entered the lifespan while the owner's
   client was still inside it. The gate's traceback runs from test `:864`
   (`competitor = post_continue()`) through `:855` (`with TestClient(narrative.app) as
   client:`) and Starlette's `testclient.py:680` (`__enter__`, `wait_startup`) to
   `nexus/api/narrative.py:134`:

   ```
   E           nexus.api.route_capabilities.RouteCapabilityError: The gateway lifespan is already running in this process; serve the gateway app or one projection, not both
   ```

   The owner was never released, so its fixture then timed out
   (`LORE process_turn failed: Timed out waiting to release generation fixture`).

2. **The set-design write-failure test, from PR #1168 (issue #813).** Migration 154
   dropped `assets.new_story_creator.zone_boundary_description` and
   `zone_approximate_area`. `read_cache_raw` selects `*`
   (`nexus/api/new_story_cache.py:648`), so the test's filter (`layer_` and `zone_`
   prefixes plus `initial_location`) now finds six columns:

   ```
   E       AssertionError: {'initial_location': None, 'layer_description': None, 'layer_name': None, 'layer_type': None, ...}
   E       assert 6 == 8
   tests/test_api/test_set_designer_failure.py:290: AssertionError
   ```

   A read-only query of `NEXUS_template` (`schema_migrations` max 154) shows exactly
   these columns: `initial_location`, `layer_description`, `layer_name`, `layer_type`,
   `zone_name`, `zone_summary`.

## Red Run on the Unchanged Tree

Run at `11229615` before any change, at a load average of 2.26:

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit \
  "tests/test_api/test_narrative_continue_validation.py::test_concurrent_continues_have_one_owner_and_truthful_result" \
  "tests/test_api/test_set_designer_failure.py::test_chat_set_design_write_failure_returns_500_without_design_draft"
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 5 targets: nexus_test_continue_* x2, postgres, qa640_840s3a_slot_*, qa640_840s3a_source_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_narrative_continue_validation.py::test_concurrent_continues_have_one_owner_and_truthful_result[False]
FAILED tests/test_api/test_narrative_continue_validation.py::test_concurrent_continues_have_one_owner_and_truthful_result[True]
FAILED tests/test_api/test_set_designer_failure.py::test_chat_set_design_write_failure_returns_500_without_design_draft
3 failed, 7 warnings in 32.43s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The failure lines match the gate's: `RouteCapabilityError` at `nexus/api/narrative.py:134`,
reached from test `:864` through `:855`, and `assert 6 == 8` at `:290`.

## Changes

- `tests/test_api/test_narrative_continue_validation.py`, lines 854-874. The
  `post_continue()` helper is gone. One `TestClient(narrative.app)` context opens once
  around the executor block. The owner's `client.post("/api/narrative/continue",
  json={"slot": 3})` runs on the executor. After `entered_generation`, the competitor
  posts through the same client from the main thread, and then the fixture is released.
  Every existing assertion stays:
  - the owner's 200 and its session id;
  - the competitor's 409, naming the owner's session;
  - the incubator, lease, session and claim rows;
  - the refused error downgrade;
  - the status, accept and discard paths.

  One assertion is added before release, `assert not owner_future.done()`. With it, the
  test proves that the owner is still in generation when the competitor's 409 returns.
  The guard is unchanged.
- `tests/test_api/test_set_designer_failure.py`, lines 290-297. The assertion
  `len(design_fields) == 8` becomes `set(design_fields) == {"initial_location",
  "layer_description", "layer_name", "layer_type", "zone_name", "zone_summary"}`, so a
  later drop or addition fails by name. The all-None assertion stays.

## One Client Serves Both Requests Concurrently

The installed versions are Starlette 0.46.1, FastAPI 0.115.11 and httpx 0.28.1.

- `TestClient.__enter__` starts one blocking portal and runs the lifespan once
  (`starlette/testclient.py:661-688`).
- Every request through the entered client uses that portal (`_portal_factory`,
  `:405-411`). Each request runs `portal.call(self.app, scope, receive, send)`
  (`:335-337`) as its own task on the portal's event loop.
- The calling thread blocks until the ASGI call returns, background tasks included.
- The owner's generation is a `BackgroundTask` (`nexus/api/narrative.py:1046-1056`). It
  awaits `lore.process_turn` on the loop (`nexus/api/narrative_generation.py:312`).
- The fixture waits in `asyncio.to_thread(release_generation.wait, 10)`, so the loop
  stays free for the competitor.

Measured: after the competitor's response returned and before release, the added
`assert not owner_future.done()` held. The competitor's 409 named the owner's session
as `active_session_id`. Both held in the proof run and in three consecutive stability
runs of the concurrent test (`2 passed` each).

## Other TestClient(narrative.app) Uses in the File

No overlap remains.

- **Context-managed clients** (each runs the lifespan) are at lines 858, 938, 979, 1024,
  1086, 1126, 1208, 1298, 1369, 1462 and 1573. Lines 858, 938 and 979 are the
  concurrent test's three sequential contexts. Lines 1298 and 1369 are in one test and
  also sequential. No client is nested in another, and only the concurrent test uses
  threads.
- **Bare calls** of the form `TestClient(narrative.app).post(...)` are at lines 196,
  215, 249, 270, 297, 331, 371, 418 (`_post_door_choice`), 552 and 665. They never run
  the lifespan. Without an entered portal, `_portal_factory` starts a portal for each
  request and sends only an `http` scope.
- **Conftests:** neither `tests/conftest.py` nor `tests/test_api/conftest.py` opens a
  `TestClient`.

Method: an AST pass over the file recorded, for each call, whether it is a `with` item
or a bare call, any enclosing `with TestClient` items, and the thread constructs per
test. Each site was then read to confirm.

## Grep of the Tests Tree

The two dropped design columns (`zone_boundary_description`, `zone_approximate_area`)
appear only in #813's own drop proof and its pre-154 fixture:
`tests/test_orrery/test_migration_154_dead_strata_pg.py:69-70` and
`tests/fixtures/813_pre154_columns.sql:9-10`.

The other five columns that migration 154 dropped:

- `seed_starting_location`, `seed_initial_mystery`, `seed_potential_obstacles`: the
  same two #813 files only.
- `clear_on_override` appears in three places:
  - the two #813 files;
  - `tests/test_orrery/test_migrate.py:2038-2042`, which handles the drop explicitly;
  - four hand-built scratch `entity_tags` tables that still declare the column:
    `tests/test_orrery/test_build_venture_projects.py:220`,
    `tests/test_orrery/test_mood_live.py:72`,
    `tests/test_orrery/test_build_venture_replay.py:59` and
    `tests/test_orrery/test_build_venture_async.py:59`.

  The four tables are inert: nothing under `nexus/` or `scripts/` names
  `clear_on_override`, and none of these tests is among the gate's failures. They are
  left unchanged because they are outside this order.
- `narration_chunk_id`: the two #813 files, and
  `tests/test_orrery/test_bleed_proximity_live.py:231`. That line writes
  `orrery_resolutions.narration_chunk_id`, the same-named column that migration 154
  keeps and names.

A search for a count of 8 (`== 8`, `len(...) == 8`, `range(8)`) found nine hits. None
concerns design fields or `new_story_creator` columns:

| Hit | What it counts |
| --- | --- |
| `test_memnon_cross_encoder_artifact.py:104` | hidden size |
| `test_turn_observation.py:803` | job total |
| `test_memnon_embedding_cache.py:308` | embedding length |
| `test_correspondence.py:394` | token count |
| `test_db_converters.py:88` | episode |
| `test_orrery/test_retrograde_orchestrator.py:294` | entity stubs |
| `test_orrery/test_worker.py:475` | semantic tags |
| `test_orrery/test_evidence.py:393` | threshold 8.0 |
| `test_lore/test_character_dossier_render.py:92` | character-tag limit |

The `startswith(("layer_", "zone_"))` filter appears only in the test changed here. The
only test that inspects the `new_story_creator` columns is #813's drop test.

## Green Run at 24ca3f99

The load average was 1.57 before the run. `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` were unset.

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_api/test_narrative_continue_validation.py tests/test_api/test_set_designer_failure.py tests/test_api/test_serve.py tests/test_runtime/test_supervisor_live.py
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 16 targets: nexus_test_continue_* x10, postgres, qa640_840s3a_slot_* x2, qa640_840s3a_source_* x2, qa885_supervisor_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
64 passed, 7 warnings in 110.92s (0:01:50)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

Stability: the concurrent test ran three more times at `24ca3f99`. Each run reported
`2 passed` (5.31 s, 5.32 s, 5.32 s), and each tail showed
`dbname audit: owner targets: none`.

## Other Proofs at 24ca3f99

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
89 passed, 5 warnings in 5.52s

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.

$ nice -n 15 $PY -m black --check tests/test_api/test_narrative_continue_validation.py tests/test_api/test_set_designer_failure.py
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

Static checks show no new diagnostics:

- **mypy in the worktree.** `$PY -m mypy --explicit-package-bases` on the two files
  reports one error, pre-existing on an untouched line in `fail_completed_broadcast`:
  `tests/test_api/test_narrative_continue_validation.py:846: error: Argument 3 has
  incompatible type "dict[str, Any] | None"; expected "dict[Any, Any]"  [arg-type]`.
- **mypy compared.** Before the commit, `git archive HEAD nexus tests .flake8
  pyproject.toml` was exported outside the worktree and checked with a fresh cache. The
  same export with the two changed files copied in was checked the same way. The two
  outputs are byte-identical (`Found 267 errors in 58 files (checked 2 source files)`).
  The higher count comes from how the exported copy resolves modules, and it is the
  same on both sides.
- **flake8** on the two files is clean on both sides.
- **Pre-commit hooks** passed on the commit (catalog, config validation, dispositions).
  The migration-comment hook was skipped because no migration file changed.

After the runs, nothing was listening on 8002, 8003, 5102 or 8010-8020. No paid call
was made.

## Not Done

- The #824 guard is unchanged, per the ruling.
- The four hand-built `entity_tags` tables that still declare `clear_on_override` are
  unchanged. They are inert and outside this order.
- The whole-tree gate was not rerun. The coordinator runs it at landing.

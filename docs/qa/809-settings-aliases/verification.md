# Issue 809 Slice S3a: Settings Alias Blocks Verification

Branch `claude/809-settings-aliases`, cut from `origin/main` at `172bd0e2` on
2026-09-30. No migration, no gateway lane, no paid provider call, and no write
to any `save_NN` or `NEXUS_template`.

## What Changed

- `nexus/api/settings_endpoints.py`: `_build_payload` no longer adds the
  `"Agent Settings"` (`global`, `LORE`, `MEMNON`) and `"API Settings"`
  (`apex`) blocks, which repeated the `global`, `lore`, `memnon`, and `apex`
  sections the same payload serves under their `nexus.toml` names. The raw
  passthrough, the removal of `secrets`, and `settings_meta` are unchanged.
- `ui/client/src/types/settings.ts`: the optional `["Agent Settings"]` field
  and the alias mention in the header comment are gone. No client code read
  the field.
- `tests/test_api/test_settings_endpoints.py`: the two assertions that named
  an alias key now compare `apex` and `global` with the materialized raw
  settings; a new test asserts that neither alias key is served, that the key
  set is exactly the raw sections minus `secrets` plus `settings_meta`, and
  that `global`, `apex`, `local_models`, `wizard`, `lore`, `memnon`, `orrery`,
  `ui`, and `settings_meta` carry the raw values. The unused `tomllib` import
  (pre-existing flake8 F401) is removed.

## Write Path

The router serves only `HEAD` and `GET` on `/api/settings`
(`nexus/api/settings_endpoints.py`, `@router.head("")` and `@router.get("")`).
`PATCH` and `PUT` therefore return 405 before any body is read, before and
after this change. The new parametrized test
`test_alias_bodies_meet_the_same_read_only_refusal` sends an
`{"Agent Settings": ...}` or `{"API Settings": ...}` body by `PATCH` and by
`PUT` and asserts 405 with the config file byte-identical.

## Red Against Main

With `nexus/api/settings_endpoints.py` temporarily restored to `origin/main`
(the new tests in place), the file fails exactly on the new alias check:

```
FAILED tests/test_api/test_settings_endpoints.py::test_get_serves_no_legacy_alias_blocks
1 failed, 7 passed, 5 warnings in 0.21s
```

## Grep Groups

Command: `git grep -n -e 'Agent Settings' -e 'API Settings'` over the whole
tree. An `rg --hidden --no-ignore` run over the worktree, excluding `.git`,
`node_modules`, and `dist`, returns the same 46 files (untracked files
included). The hits below are from the tree before this change.

### (a) Readers of the HTTP Payload of `GET /api/settings`

No runtime reader.

- `nexus/api/settings_endpoints.py:101,106`: the producer of the two blocks
  (removed here).
- `tests/test_api/test_settings_endpoints.py:49,50`: test assertions on the
  payload (rewritten here, not deleted).
- `ui/client/src/types/settings.ts:3,55`: header comment and the optional type
  field (removed here). No other file under `ui/client/src` names either key;
  the design-sync mock payload (`ui/.design-sync/ds-provider.tsx`,
  `ui/.design-sync/previews/SettingsPane.tsx`) carries neither key. The only
  non-UI HTTP callers of `/api/settings` are `tests/test_api/*` (status codes
  and the sections above).

### (b) Readers of the Configuration Façade (Not This Slice; Unchanged)

These read `load_settings_as_dict()`, the legacy JSON loader, or a JSON
fixture shaped like it, never the HTTP payload.

- `nexus/config/loader.py:320,321,331,338,381,391,392`: builds the façade.
- `nexus/config/story_model.py:271`,
  `nexus/agents/orrery/retrograde_maturation.py:596`: filter the two façade
  keys out before `Settings.model_validate`.
- `scripts/api_anthropic.py`, `scripts/api_openai.py`,
  `scripts/api_openrouter.py`, `scripts/estimate_time_delta.py`,
  `scripts/create_vector_index.py`, `scripts/import_narratives.py`,
  `scripts/query_narratives_vector.py`, `scripts/regenerate_embeddings.py`,
  `scripts/update_raw_text.py`, `scripts/extract_scene_numbers.py`,
  `scripts/measure_presence_boost.py`,
  `scripts/migrate_chunk_character_references.py`,
  `scripts/process_characters.py`, `scripts/run_golden_queries.py`: each calls
  `load_settings_as_dict()`; `scripts/map_builder_legacy.py` reads the
  `SETTINGS` that `scripts/api_anthropic.py` builds the same way.
- `ir_eval/engine/run_executor.py` (façade), `ir_eval/ir_eval.py`,
  `ir_eval/ir_eval_debug.py`, `ir_eval/ir_eval_sqlite.py`,
  `ir_eval/scripts/display.py`, `ir_eval/scripts/golden_queries_module.py`,
  `ir_eval/scripts/query_runner.py`, `ir_eval/scripts/settings_compare.py`,
  `ir_eval/scripts/utils.py` (legacy JSON settings files).
- Tests: `tests/config/test_settings_parity.py`,
  `tests/test_api/test_narrative_jobs_pg.py:77,219`,
  `tests/test_memnon_embedding_cache.py:45`,
  `tests/test_orrery/test_retrograde_maturation.py:496,636` (façade);
  `tests/test_config/test_ir_eval_golden_overrides.py:80,94` (ir_eval JSON);
  `tests/test_lore/test_infrastructure.py:176-179` with
  `tests/test_lore/lore_test_settings.json` (JSON fixture loaded by
  `tests/test_lore/conftest.py:33`).

### (c) Documentation, Comments, and Evidence

None describes the payload of this endpoint as it is today, so none is edited.

- Section-header comments that name no payload key: `nexus.toml:204,246,872,
  1233,1312`; `nexus/config/settings_models.py:1122,3165,3575`.
- Historical design and module notes about the façade or the old JSON file:
  `docs/blueprint_nemesis.md`, `nexus/agents/memnon/memnon_hybrid_search.md`,
  `nexus/agents/memnon/README_MEMNON.md`,
  `tests/test_lore/test_assembled_prompt_fingerprint.py:4` (docstring).
- Evidence files: `docs/qa/809-typed-settings/verification.md`,
  `docs/qa/1033-membership-roles/verification.md`,
  `docs/qa/742-scene-order/parent-focused-initial.txt`.
- `docs/settings_scopes.md` and `docs/runtime.md` describe
  `GET /api/settings` without naming either alias; they stay accurate.

## Commands and Tails

All tails below ran on commit `b1c87960` (the product, client-type, and test
change), itself on `origin/main` at `172bd0e2`, on 2026-09-30, from the
worktree root with the shared interpreter (`$PY`), `PYTHONPATH=$PWD`, and
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT` unset. The import
check printed
`/Users/pythagor/nexus/.claude/worktrees/809-settings-aliases/nexus/__init__.py`.

### Named Test Files

```
$ $PY -m pytest -q -p no:cacheprovider tests/test_api/test_settings_endpoints.py \
    tests/test_api/test_route_capabilities.py tests/test_api/test_slot_settings.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 6 skipped, 7 warnings in 3.75s
```

The six skips are `tests/test_api/test_slot_settings.py` ("Set
NEXUS_RUN_POSTGRES=1 to run PostgreSQL integration tests."). The same files
with PostgreSQL on, so nothing skips:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit \
    tests/test_api/test_settings_endpoints.py tests/test_api/test_route_capabilities.py \
    tests/test_api/test_slot_settings.py
dbname audit: 7 targets: postgres, qa640_offline_gate_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
secret-store guard: active; nexus-api: denied; disposable keychain: denied
44 passed, 7 warnings in 12.58s
```

### Reachability

```
$ $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.25s
```

### Offline Suites

```
$ $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2608 passed, 391 skipped, 8 warnings in 399.47s (0:06:39)

$ $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1816 passed, 742 skipped, 7 warnings in 36.01s
```

No failures, so none of the issue #885 slot-5 exemptions applied.

### Black, Flake8, Mypy (Changed Python Files)

```
$ $PY -m black --check nexus/api/settings_endpoints.py tests/test_api/test_settings_endpoints.py
All done! ✨ 🍰 ✨
2 files would be left unchanged.
$ $PY -m flake8 nexus/api/settings_endpoints.py tests/test_api/test_settings_endpoints.py
(no output, exit 0)
$ PYTHONPATH=$PWD $PY -m mypy nexus/api/settings_endpoints.py tests/test_api/test_settings_endpoints.py
Success: no issues found in 2 source files
```

### UI

`node_modules` came from `npm --prefix ui ci` in this worktree (not
committed).

```
$ npm --prefix ui run check
> tsc && npm run check:design-sync
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
(exit 0)

$ npm --prefix ui test
 Test Files  35 passed (35)
      Tests  462 passed (462)
   Duration  6.87s (transform 2.26s, setup 2.47s, collect 13.64s, tests 15.87s, environment 16.99s, prepare 2.12s)
```

### After the Rebase

`origin/main` moved to `c8dd8c85` (#1048: migration 136, one PostgreSQL test
file, one evidence file; no overlap with this change) while the gates ran.
The branch was rebased onto it, and `b1c87960` became `13d0b3ec` with an
identical diff. The named test files and reachability were rerun at the
rebased head:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit \
    tests/test_api/test_settings_endpoints.py tests/test_api/test_route_capabilities.py \
    tests/test_api/test_slot_settings.py
dbname audit: owner targets: none
secret-store guard: active; nexus-api: denied; disposable keychain: denied
44 passed, 7 warnings in 12.45s

$ $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.05s
```

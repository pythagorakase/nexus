# Review Proof Commands

Executed from this worktree. Intermediate failures are diagnostic evidence; the invalid selector, TypeScript return-shape error, and legacy fixture settings were repaired before the final gates.

## MEMNON Scope

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_lore/test_runtime_config.py tests/test_memnon_runtime_config.py tests/test_memnon_embedding_cache.py > temp/gate/review-memnon.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
11 passed, 5 warnings in 23.33s
```

## Initial Reader Selector (Diagnostic)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_presence_roster_pg.py tests/test_api/test_reader_asset_endpoints.py::TestPlaceZoneFactionReads > temp/gate/review-places.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
5 warnings in 0.03s
```

## Reader and Recall

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_presence_roster_pg.py tests/test_api/test_reader_asset_endpoints.py::TestWorldReads > temp/gate/review-places-recheck.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
17 passed, 5 warnings in 11.20s
```

## Experience Metadata

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_presence_roster_pg.py tests/test_orrery/test_experiences.py tests/test_orrery/test_character_experiences_pg.py > temp/gate/review-experiences.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
69 passed, 7 warnings in 41.11s
```

## Offline Diagnostic

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/review-offline.log 2>&1
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_orrery/test_retrieval_boundaries.py::test_query_memory_vector_search_includes_retrograde_summary_collection
1 failed, 2654 passed, 817 skipped, 9 warnings in 92.26s (0:01:32)
```

## Offline Recheck Before Experience Repair

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/review-offline-recheck.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2655 passed, 817 skipped, 9 warnings in 91.57s (0:01:31)
```

## Initial TypeScript Check (Diagnostic)

```sh
npm --prefix ui run check > temp/gate/review-ui-check.log 2>&1
```

```text
> tsc

client/src/lib/narrative-api.ts(44,27): error TS2322: Type 'never[]' is not assignable to type 'ChunkWithMetadata'.
  Type 'never[]' is missing the following properties from type 'Omit<{ id: number; createdAt: Date | null; rawText: string; storytellerText: string | null; choiceObject: unknown; choiceText: string | null; }, "choiceObject">': id, createdAt, rawText, storytellerText, choiceText
```

## TypeScript Recheck

```sh
npm --prefix ui run check > temp/gate/review-ui-check-recheck.log 2>&1
```

```text

> nexus-ui@1.0.0 check
> tsc

```

## Initial UI Suite

```sh
npm --prefix ui test > temp/gate/review-ui-test.log 2>&1
```

```text

 Test Files  22 passed (22)
      Tests  238 passed (238)
   Start at  13:53:59
   Duration  1.83s (transform 1.55s, setup 1.19s, collect 5.22s, tests 2.54s, environment 7.69s, prepare 1.37s)

```

## Final PostgreSQL

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/review-full-pg.log 2>&1
```

```text
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways
95 failed, 3298 passed, 49 skipped, 11 warnings, 32 errors in 762.47s (0:12:42)
```

## Final Offline

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/review-offline-final.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2655 passed, 819 skipped, 9 warnings in 91.59s (0:01:31)
```

## Final UI Suite

```sh
npm --prefix ui run check && npm --prefix ui test
```

```text
 Test Files  22 passed (22)
      Tests  238 passed (238)
   Start at  13:59:35
   Duration  1.95s (transform 1.17s, setup 989ms, collect 4.78s, tests 2.61s, environment 7.93s, prepare 1.26s)


```

## Production Build

```sh
npm --prefix ui run build > temp/gate/review-ui-build.log 2>&1
```

```text
PWA v1.0.3
mode      generateSW
precache  22 entries (2273.84 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## Black

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only --diff-filter=ACM origin/main -- '*.py') > temp/gate/review-black-final.log 2>&1
```

```text
All done! ✨ 🍰 ✨
49 files would be left unchanged.
```

## Reachability

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -S scripts/check_reachability.py --report temp/gate/review-reachability-final.json > temp/gate/review-reachability-final.log 2>&1
```

```text
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```


# Work Order 880: PostgreSQL Connection Contract

The pooled, SQLAlchemy, direct psycopg2, asyncpg adapter, CLI, worker, and script paths share `nexus/database.py`. Explicit target arguments take precedence over `[api.database]`, then PGHOST/PGPORT/PGUSER/PGPASSWORD and OS/libpq defaults. Passwords use the platform secret resolver when `password_secret` is set. URLs escape credentials; status exposes only host, port, user, and database. Every generated connection carries the configured session timezone, default UTC.

MEMNON checks the requested server/user/database target before schema initialization. The database argument remains explicitly selectable per request; a caller can supply an expected database to `verify_database_url` to reject a mismatched URL. An existing pool rejects changed parameters until it is closed.

## Verification

Commands ran from this worktree using `PY=/Users/pythagor/nexus/.venv/bin/python`. The required import probe printed:

```text
/Users/pythagor/nexus/.claude/worktrees/880-connection-contract/nexus/__init__.py
```

TEST supplied only model responses. Every database operation, CLI command, HTTP request, turn-cycle step, retrieval, and background-job operation used production code and real PostgreSQL. The test fixture restores read-only schema/vocabulary exports from NEXUS_template into its own temporary clusters. No owner save or template was modified; no fleet migration or paid provider was called.

The lifecycle fixture creates save_04 and mock only inside its two disposable clusters. These are fixture-owned databases, not the owner's slots. It uses gateway port 8014 and a free port for its own TEST server. `nexus down`, provider termination, pool closure, `pg_ctl stop`, and cluster-directory removal run during teardown.

### Two-Cluster Evidence

`tests/test_connection_lifecycle.py` runs the wizard through setting, character, traits, wildcard, introduction, and bootstrap via `nexus continue`. A normal choice completes the actual LORE/MEMNON turn cycle. MEMNON retrieves the committed opening. A genuine sleep-pressure resolution is committed, promoted, leased, and completed by the production background worker.

A conflicting PG environment names the non-target cluster while TOML names the private cluster. The non-target monitor starts before runtime startup and finishes after shutdown. Its catalog, pg_stat_activity, connection log, and statement log establish:

```json
{"catalog_before_count": 415, "catalog_unchanged": true, "other_clients": 0, "new_connections": 0, "schema_statements": 0}
```

The background result has `promoted=1`, `narrated=1`, and all failure counts zero. Tests also inspect private pg_stat_activity, compare both preflight targets, reject a foreign MEMNON schema target before connecting, and verify `SHOW TimeZone = UTC` for pooled, URL-based, and asyncpg connections.

### Scope and Deferred Work

- #885 is the coordinator-approved exemption. The exact unfiltered PostgreSQL selection has that one failure; the same selection with only that test deselected passes.
- The full offline suite intentionally skips opt-in PostgreSQL and live-provider tests. Separate PostgreSQL gates actually ran.
- TEST preserves its existing Retrograde cold-start bypass. This proves connection routing and lifecycle protocol, not paid-model quality.
- The separate local-model Conversations routing issue remains deferred under the frozen work order.
- No schema migration, UI, intertitle, world-clock view, or clock rendering change is included.
- The connection audit found no executable PostgreSQL `localhost`, `5432`, or `user="pythagor"` defaults left in nexus/ or scripts/. Remaining localhost text is HTTP/CORS, documentation, or historical output.
- Legacy standalone scripts now require an active slot or explicit URL instead of silently choosing the deprecated NEXUS database. DB_* connection variables are retired in favor of the single contract.

## Commands and Verbatim Tails

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > temp/qa880_resume/offline-final.log 2>&1
```
```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2583 passed, 758 skipped, 11 warnings in 90.89s (0:01:30)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_lore tests/test_memnon_db_access.py tests/test_runtime -k 'connection or url or pool or override or status' > temp/qa880_resume/postgres.log 2>&1
```
```text
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures
1 failed, 45 passed, 614 deselected, 11 warnings in 26.50s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_lore tests/test_memnon_db_access.py tests/test_runtime -k 'connection or url or pool or override or status' --deselect=tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures > temp/qa880_resume/postgres-exempt.log 2>&1
```
```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
45 passed, 615 deselected, 11 warnings in 26.56s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_database_contract.py > temp/qa880_resume/contract-final.log 2>&1
```
```text
........                                                                 [100%]
8 passed in 1.71s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_database_contract.py tests/test_connection_lifecycle.py --basetemp=temp/qa880_resume/proof > temp/qa880_resume/proof-final.log 2>&1
```
```text
.........                                                                [100%]
9 passed in 21.44s
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/database.py tests/test_database_contract.py tests/test_connection_lifecycle.py
```
```text
All done! ✨ 🍰 ✨
3 files would be left unchanged.
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m compileall -q nexus scripts tests/test_connection_lifecycle.py
bash -n scripts/install_pgvector.sh scripts/apply_migration_to_slots.sh
git diff --check
```

Each exited 0 with no output. These were syntax/format checks, not execution of the installer or migration scripts. Pre-commit catalog and configuration/model-drift hooks passed.

## File Manifest

REVIEW marks nonmechanical behavior or validation work. Other entries are resolver redirects. Several legacy scripts also have whitespace-only cleanup inherited from the resumed commit; use `git diff -w` to concentrate on behavior.

### Resolver and Pool

- `nexus.toml` — REVIEW: add empty connection identity fields and UTC session policy; clear the legacy MEMNON URL.
- `nexus/api/db_pool.py` — REVIEW: key pools by validated database, pass explicit overrides, and reject changed connection parameters until pools are closed.
- `nexus/api/slot_utils.py` — REVIEW: replace literal defaults with optional overrides and add escaped password support through the resolver.
- `nexus/config/settings_models.py` — REVIEW: validate PostgreSQL host, port, user, secret-account, and IANA session timezone configuration.
- `nexus/database.py` — REVIEW: introduce precedence, escaped URL and driver adapters, credential-free targets, schema-target checks, and idempotent timezone normalization with typed timeouts.

### URL-Based Clients and Direct Runtime Clients

- `nexus/agents/lore/logon_utility.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/agents/lore/lore.py` — REVIEW: replace credential-bearing connection URL logging with a safe message.
- `nexus/agents/memnon/test_idf_dictionary.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/agents/memnon/utils/continuous_temporal_search.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/agents/memnon/utils/idf_dictionary.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/agents/memnon/utils/temporal_search.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/agents/orrery/retrograde_maturation.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/agents/orrery/tag_library.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/agents/orrery/worker.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/api/backstage_endpoints.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/api/mock_openai.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/api/narrative.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/api/new_story_flow.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/api/orrery_dev_endpoints.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/api/presence_reconciliation.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/api/save_slots.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/api/summary_triggers.py` — Redirect connection or URL construction through the shared resolver.
- `nexus/memory/correspondence.py` — Redirect connection or URL construction through the shared resolver.

### MEMNON Initialization Guard

- `nexus/agents/memnon/memnon.py` — REVIEW: verify schema target before engine creation and stop logging credential-bearing URLs.
- `nexus/agents/memnon/utils/db_access.py` — REVIEW: reject foreign targets before index setup; use shared URL decoding at all direct connection sites.
- `nexus/agents/memnon/utils/db_schema.py` — REVIEW: reject foreign targets before create_all and index initialization.

### Status Reporting

- `nexus/api/runtime_status.py` — REVIEW: expose separate redacted pooled and URL target identities in runtime status.
- `nexus/cli.py` — REVIEW: render both database targets in nexus status.

### Scripts

- `scripts/api_anthropic.py` — REVIEW: retire DB_* and implicit NEXUS defaults in favor of the active slot contract; remove URL logging.
- `scripts/api_openai.py` — REVIEW: retire DB_* and implicit NEXUS defaults in favor of the active slot contract; remove URL logging.
- `scripts/api_openrouter.py` — REVIEW: retire DB_* and implicit NEXUS defaults in favor of the active slot contract; remove URL logging.
- `scripts/apply_migration_to_slots.sh` — Delegate PostgreSQL CLI environment resolution to the shared module; not executed during verification.
- `scripts/apply_slot2_semantic_tags.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/assemble_context.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/backfill_routine_anchors.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/benchmark_experience_enqueue_fence.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/character_chunk_ranker.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/character_episode_ranker.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/checkpoint_state.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/create_vector_index.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/creative_character_expansion.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/estimate_time_delta.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/extract_scene_numbers.py` — REVIEW: replace ad hoc legacy settings parsing and empty-config fallback with validated resolution.
- `scripts/extract_season_episode.py` — REVIEW: retire duplicate DB_* resolution and implicit NEXUS default.
- `scripts/faction_former.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/faction_relationship_analyst.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/fix_chunks.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/fix_episode_ranges.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/freestyle_api_query.py` — REVIEW: retire its duplicate DB_* resolver and implicit NEXUS default.
- `scripts/generate_character_summaries_experimental.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/generate_psychology copy.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/generate_psychology.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/gis_backfill.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/gis_hygiene.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/import_narratives.py` — REVIEW: remove implicit NEXUS fallback and credential-bearing URL logging; normalize explicit URLs.
- `scripts/import_orrery_route_graph.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/import_setting.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/install_pgvector.sh` — REVIEW: resolve PostgreSQL CLI targets through the selected worktree even after changing cwd; installer not executed.
- `scripts/map_builder.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/map_builder.py.new` — Normalize the tracked legacy script variant through the URL adapter.
- `scripts/map_builder_fail.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/map_builder_legacy.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/map_illustrator.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/measure_presence_boost.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/memnon_config.json` — Remove the obsolete literal database URL from legacy script settings.
- `scripts/migrate.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/migrate_chunk_character_references.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/migrate_provider_names.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/new_story_setup.py` — REVIEW: propagate the resolved environment to every PostgreSQL child process as well as direct connections.
- `scripts/orrery_sample.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/process_characters.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/process_factions.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/propagate_schema.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/qa_shift/prose_metrics.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/query_narratives_simple.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/query_narratives_vector.py` — REVIEW: remove implicit NEXUS fallback and credential-bearing URL logging; normalize explicit URLs.
- `scripts/regenerate_embeddings.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/register_drift_study.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/relationship_analyst.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/replay_state.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/report_retrieval_coverage.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/retrieval_query_bakeoff.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/run_golden_queries.py` — Remove implicit NEXUS fallback so absent legacy URL settings use the active slot.
- `scripts/seed_slot2_routine_anchors.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/simple_update.py` — Use the contract for the default CLI URL and normalize explicit URLs.
- `scripts/stamp_lore_pass_baseline.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/summarize_narrative.py` — REVIEW: retire duplicate DB_* resolution and implicit NEXUS default; normalize worker URLs.
- `scripts/test_narrative_simple.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/test_narrative_turn.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/trim_oversized_contexts.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/update_raw_text.py` — REVIEW: remove implicit NEXUS fallback and credential-bearing URL logging; normalize explicit URLs.
- `scripts/update_scene_numbers.py` — Redirect connection or URL construction through the shared resolver.
- `scripts/validate_embeddings.py` — REVIEW: retire duplicate DB_* resolution and postgres/postgres credential defaults.
- `scripts/vector_migration.py` — Redirect connection or URL construction through the shared resolver.

### Tests

- `tests/test_api/test_runtime_status.py` — Update status expectations for resolver-derived target dictionaries.
- `tests/test_connection_lifecycle.py` — REVIEW: real CLI/gateway TEST lifecycle, retrieval, completed background work, startup-to-shutdown foreign-server monitoring and cleanup.
- `tests/test_database_contract.py` — REVIEW: real resolver precedence, secret-backend, URL escaping, timezone, foreign-target guards, and two-cluster driver coverage.
- `tests/test_memnon_db_access.py` — Use resolver-built URLs in existing index tests so target guards see the configured runtime.

### Documentation and Inventory

- `config/reachability_baseline.json` — Register the new production connection module in the reachability inventory.
- `docs/qa/880-connection-contract.md` — Record final verification, proof boundaries, and the grouped file manifest.

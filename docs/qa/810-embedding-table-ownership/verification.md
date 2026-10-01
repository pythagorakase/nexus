# STOP-REPORT: 810-S2 Amendment 3 (2026-10-01)

## New Untouched Recording-Cursor Failure

Resumed at accepted checkpoint `8dc4d37a`, preserving every commit. Read the
common rules (including Static Checks), frozen order, all three amendments,
previous reports, repository instructions, and live #810 comments. Proved
`nexus.__file__` resolves to this worktree. All commands ran from the assigned
worktree; all scratch files stayed under the assigned `scratchpad/810-S2/`.

Merged fetched `origin/main` `16993687d7381955e0cc5f7ea0bbb59bf4b22764` in
`6386630e`, without rebasing or rewriting history. Checkpoints `92d6fb70`,
`b619d8d3`, and `8dc4d37a` and fetched main are ancestors of HEAD. Validated
product/fixture head for this stop is `f18bca91f6ec6647c85a634ba786fa370d0f0af0`.

The ordered PostgreSQL proofs all pass on the merged branch: **66 + 116 +
182 = 364 passed**, with the secret-store guard active and **owner targets:
none** on every piece. This run exported all 52 ownership/source/384d starting
clone stamp records, closing the previously missing per-clone stamp evidence.
The remaining MEMNON/runtime/util/scripts offline split passes after the
amendment-authorized baseline update below: **290 passed, 25 skipped**.

The API/Orrery offline gate has one failure in an untouched file:

`tests/test_orrery/test_experiences.py::test_embedding_upsert_binds_each_correct_experience_id`

Its `_EmbeddingCursor` (`tests/test_orrery/test_experiences.py:612-642`) has no
DBAPI `description` and records writes without answering PostgreSQL catalog
queries. The test patches both the pool connection and embedding manager
(`:654-691`), then calls the real experience wrapper and ensure helper. The
new catalog validation reaches `_catalog_rows` at
`nexus/agents/memnon/utils/embedding_tables.py:140` and raises:

```text
E       AttributeError: '_EmbeddingCursor' object has no attribute 'description'
```

This is a recording-cursor test assumption, separate from product failures,
clone preparation, #1091, and fingerprint/allowlist/exemption liveness. The
frozen common rule says: "Any other failure in a file you did not change:
report the exact test id and the failure tail, do not fix it, do not skip it;
the coordinator triages." Amendment 3 retains that rule. STOP: no test or
production validator workaround was made, and this test was not skipped.
The gate reports **1 failed, 1828 passed, 749 skipped**; skips are offline
results, never counted as PostgreSQL proof.

## Completed Authorized Baseline Deltas

### ANN SQL Fingerprint

Commit `7c4dc699` updates only the `db_access.py` entry of
`tests/test_memnon/fixtures/ann_repaired_sql.json` from
`f24ac6cf9aa8e45d4cbb5f85194fa8ed68b875bfb460cb80b2b277d0eb370ac9` to
`35ecf4de78ec08ff80f23f5d96037125e428d6a6597e18619aea5082317d5497`.
The entire AST fingerprint test remains unchanged. Its offline rerun passes.

Exactly four AST expressions disappear, all from the ordered deletion of
`setup_database_indexes`; nothing is added. The raw delta follows:

```json
[
  "Constant(value=\"SELECT 1 FROM pg_extension WHERE extname = 'vector'\")",
  "JoinedStr(values=[Constant(value=\"\\n                        SELECT exists (\\n                            SELECT 1 FROM pg_indexes \\n                            WHERE indexname = '\"), FormattedValue(value=Name(id='dim_table', ctx=Load()), conversion=-1), Constant(value=\"_hnsw_idx'\\n                        )\\n                        \")])",
  "Constant(value=\"\\n                        SELECT exists (\\n                            SELECT 1 FROM pg_indexes \\n                            WHERE indexname = '\")",
  "Constant(value=\"_hnsw_idx'\\n                        )\\n                        \")"
]
```

A fresh read-only comparison against merged `origin/main` checked all 35 SQL
source segments matching the fingerprint keywords outside the deleted setup
function. **Retrieval SQL is byte-identical**, preserving literal whitespace
and interpolation. Output:

```text
Retrieval SQL source segments byte-identical to origin/main: 35; no additions.
All three accepted checkpoint commits and origin/main are ancestors of HEAD.
```

### Exception-Disposition Exemptions Introduced by the Main Merge

The first remaining-offline run failed only because the new main checker found
nine stale swallowing-handler exemptions caused by this order's deletions and
fail-loud conversions. Under Amendment 3's general rule, commit `f18bca91`
removes exactly those nine identities: six in deleted `setup_database_indexes`,
one in deleted `_setup_hybrid_search`, one for `check_vector_extension` now
re-raising, and one for `_generate_chunk_embeddings` now re-raising.
There are no additions or retained-reason changes; the checker is unchanged.
The exact removed identities are:

```text
nexus/agents/memnon/utils/content_processor.py|ContentProcessor._generate_chunk_embeddings|31f7919238de69c3543c28a5f4d3cd41891ee39576b41f1c7a3995ef3f15bd7c|1
nexus/agents/memnon/utils/db_access.py|check_vector_extension|f40e90a1a69e734e892bdb1e18105828c1ad1daab08ee68d12708d68ea1c690d|1
nexus/agents/memnon/utils/db_access.py|setup_database_indexes|189003dbed1940b3d1b2a58593ac3723f8b855f86e2b765e74cf551e5438aabd|1
nexus/agents/memnon/utils/db_access.py|setup_database_indexes|2bb427024de559e1ae86584eb5f578ae011aea3698e4dba7be021cd51681568e|1
nexus/agents/memnon/utils/db_access.py|setup_database_indexes|5335445c524ecdc3e2087e1cbfb22bfbd2ade6020fd38bcf7cfa082bf0863247|1
nexus/agents/memnon/utils/db_access.py|setup_database_indexes|6b53a987b88e0246e5a5eacc97fb056ca97ee8a11515646ad1739d8aff80b97e|1
nexus/agents/memnon/utils/db_access.py|setup_database_indexes|8eeb5b357c45b106dbc295a5b7f93670b0ca7b9a76dd750a09c920efd37721ee|1
nexus/agents/memnon/utils/db_access.py|setup_database_indexes|e332f0cb4568ce6249f95968cd12acac6068e9b6f1f82925832df010bdb6d61b|1
nexus/agents/memnon/utils/db_schema.py|DatabaseManager._setup_hybrid_search|315aba118220cefb097d0462c142438cae259783338e5cccfe6dee34203d9c77|1
```

The direct check against origin/main and the commit hook pass:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

Amendment 2's earlier removal of three stale owner-target exemption entries
remains preserved: two `database_url("save_04")` entries from deleted setup
probes, one `database.connect("save_05", dict_cursor=True)` from the converted
source tests. The guard passes within the 182-test PostgreSQL split.

## Exact Commands and Verbatim Tails

Every test command ran through the assigned scratch `run_gate.py` foreground
wrapper, with a 590-second command limit and 120-second silence limit. The
exact child argv is printed below. `TMPDIR` also pointed to that scratch
folder. No command timed out or remained running at STOP. Full logs and
`runs.jsonl` remain there. These are new results after the main merge; prior
dated results and accepted stops are retained verbatim below.

### final-ownership (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership:/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --capture=tee-sys --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-final-ownership -p tests.dbname_audit -p clone_manifest_810s2 tests/test_embedding_table_ownership_pg.py tests/test_memnon_db_access.py tests/test_memnon/test_source_embeddings.py tests/test_retrograde_summary_retrieval.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 53 targets: postgres, qa640_810s2_contract_* x46, qa640_810s2_source_* x5, qa640_810s2_summary384_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
66 passed in 91.72s (0:01:31)
```

### final-contract-migrations (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership:/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-final-contract-migrations -p tests.dbname_audit -p clone_manifest_810s2 tests/test_database_contract.py tests/test_unowned_index_adoption_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 23 targets: nexus_m10_fresh_test_82932, nexus_m10_template_test_82932, postgres, qa640_810_adopt_drift_*, qa640_810_adopt_noop_*, qa640_810_adopt_recreate_*, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_no_create_all_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_connection_contract, qa640_grieving_migration_*, qa640_raw_url_contract, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:53483 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[1] at local:53486 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[0] at local:53498 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard; two_clusters[1] at local:53503 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard
dbname audit: owner names admitted on registered clusters: none
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
116 passed in 35.71s
```

### final-schema-writers (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership:/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-final-schema-writers -p tests.dbname_audit -p clone_manifest_810s2 tests/test_schema_documentation_pg.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_orrery/test_retrograde_embedding_pg.py tests/test_memnon/test_ann_gate.py::test_ann_candidate_index_build_drop tests/test_memnon/test_ann_gate.py::test_ann_alias_candidates_and_database_errors tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: postgres, qa640_766_schema_*, qa640_docs_refresh_*, qa640_regen_truncate_* x2, qa640_schema_docs_* x3, qa665_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
182 passed in 26.11s
```

### final-offline-remaining (Exit 1)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-final-offline-remaining tests/test_memnon tests/test_runtime tests/test_util tests/test_scripts tests/test_turn_observation.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline
1 failed, 289 passed, 25 skipped, 7 warnings in 53.76s
```

### final-offline-remaining-rerun (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-final-offline-remaining-rerun tests/test_memnon tests/test_runtime tests/test_util tests/test_scripts tests/test_turn_observation.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
290 passed, 25 skipped, 7 warnings in 59.41s
```

### final-offline-api-orrery (Exit 1)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-final-offline-api-orrery tests/test_api tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_experiences.py::test_embedding_upsert_binds_each_correct_experience_id
1 failed, 1828 passed, 749 skipped, 7 warnings in 38.69s
```

New failure call-chain excerpt (terminal trailing spaces trimmed):

```text
tests/test_orrery/test_experiences.py:691:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
nexus/agents/orrery/experience_embedding.py:42: in embed_character_experiences
    return embed_source_rows(dbname, CHARACTER_EXPERIENCE_SOURCE, experience_ids)
nexus/agents/memnon/utils/source_embeddings.py:344: in embed_source_rows
    upsert_source_vectors(cursor, spec, generated)
nexus/agents/memnon/utils/source_embeddings.py:209: in upsert_source_vectors
    table_name = spec.ensure_table(cursor, dimensions)
nexus/agents/memnon/utils/embedding_tables.py:362: in ensure_character_experience_embedding_table
    return _ensure_corpus_table(
nexus/agents/memnon/utils/embedding_tables.py:165: in _ensure_corpus_table
    relations = _catalog_rows(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

connection = <test_orrery.test_experiences._EmbeddingCursor object at 0x16c11a650>
statement = "SELECT c.oid, c.relkind FROM pg_class c\n        JOIN pg_namespace n ON n.oid = c.relnamespace\n        WHERE n.nspname = 'public' AND c.relname = 'character_experience_embeddings_0002d'"

    def _catalog_rows(connection: Any, statement: str) -> List[dict[str, Any]]:
        """Read catalog rows through SQLAlchemy or tuple/dictionary DBAPI cursors."""
        driver = getattr(connection, "exec_driver_sql", None)
        if callable(driver):
            return [dict(row) for row in driver(statement).mappings()]
        connection.execute(statement)
>       names = [column[0] for column in connection.description]
E       AttributeError: '_EmbeddingCursor' object has no attribute 'description'

nexus/agents/memnon/utils/embedding_tables.py:140: AttributeError
```

Removal proof:

```sh
rg -n 'setup_database_indexes|_setup_hybrid_search' nexus scripts ir_eval
```

No output; exit 1. `git diff --check` has no output; exit 0.

## Fresh Disposable Clone Migration Manifest

The read-only scratch plugin `clone_manifest_810s2.py` queries
`SELECT version, name FROM schema_migrations ORDER BY version` before yielding
each clone. This resumption records 73 helper-created clones: all 52
ownership/source/384d clones, plus 21 adoption/schema/setup/ANN/transaction
clones. Fixture-owned private clusters and non-helper databases retain their
separate tests/audits; this manifest does not claim instrumentation of those
creation mechanisms. Every recorded clone has this exact starting stamp set:

```json
[["001", "baseline"], ["002", "add_choice_columns"], ["003", "add_layer_zone_drafts"], ["004", "fix_global_variables_fk"], ["005", "add_incubator_choice_object"], ["006", "add_save_slots_model"], ["007", "normalize_new_story_creator"], ["009", "remove_assets_save_slots"], ["010", "add_traits_table"], ["011", "add_traits_confirmed"], ["012", "add_wizard_choice_object"], ["014", "add_2560d_4096d_embeddings"], ["015", "add_ir_eval_v2_tables"], ["016", "add_ir_eval_v1_query_tables"], ["017", "add_judgment_justification"], ["018", "narrative_chunks_column_comments"], ["019", "add_incubator_choice_text"], ["020", "drop_chunk_embeddings_0384d"], ["021", "dedup_embedded_state"], ["022", "compound_embedding_pk_lazy_tables"], ["023", "orrery_schema"], ["024", "orrery_commit_pipeline"], ["025", "orrery_package_library_vocab"], ["026", "relationship_valence_magnitude"], ["027", "orrery_package_library_round2_vocab"], ["028", "orrery_sunhelm_needs"], ["029", "orrery_need_state_init_trigger"], ["030", "orrery_place_affordance_vocab"], ["031", "orrery_slot2_semantic_tag_vocab"], ["032", "orrery_interpersonal_needs"], ["033", "orrery_travel_work"], ["034", "orrery_concealment_surveillance_vocab"], ["035", "orrery_osm_route_graph"], ["036", "skald_inline_tag_runtime"], ["037", "orrery_tag_category_registry"], ["038", "orrery_tag_baseline_reconciliation"], ["039", "new_story_character_orrery_tags"], ["040", "storyteller_authorial_directives"], ["041", "orrery_authority_model"], ["042", "orrery_entity_pair_tags"], ["043", "orrery_category_refactor_phase1"], ["044", "disambiguate_status_reputation_traits"], ["045", "trait_compiler_substrate"], ["046", "canonical_grieving_state"], ["047", "kind_qualified_contact_pair_tags"], ["048", "orrery_hunting_pair_tag"], ["049", "orrery_entity_tag_expiry_substrate"], ["050", "orrery_state_clearance_event_types"], ["051", "orrery_time_tag_clearance_kind"], ["052", "orrery_faction_tag_vocab"], ["053", "retire_faction_legacy_write_defaults"], ["054", "orrery_completed_tag_vocab"], ["055", "orrery_character_tag_vocab"], ["056", "orrery_routine_anchors"], ["057", "orrery_need_bodyform_applicability"], ["058", "retire_faction_legacy_columns"], ["059", "orrery_social_travel_event"], ["060", "retrograde_persistence_sources"], ["061", "trait_compiler_sponsors_pair_tag"], ["062", "retrograde_maturation_jobs"], ["063", "orrery_adjudication_history"], ["064", "tag_provenance_forward_fix"], ["065", "reconstructability"], ["066", "signal_event_vocab"], ["067", "rename_orrery_templates"], ["068", "mundane_band_event_vocab"], ["069", "ecology_event_vocab"], ["070", "need_state_chunk_stamp"], ["071", "retrograde_world_layer"], ["072", "retrograde_layer_backfill"], ["073", "rename_dream_to_atemporal"], ["074", "plan_relocation_projects"], ["075", "retrieval_coverage_log"], ["076", "claims_awareness"], ["077", "recruit_ally_projects"], ["078", "retrograde_summary_storage"], ["079", "need_state_chunk_provenance_comment"], ["080", "epistemics_knowers"], ["081", "faction_project_contexts"], ["082", "generation_model_provenance"], ["083", "claim_propagation_ledger"], ["084", "build_venture_projects"], ["085", "pursue_romance_projects"], ["086", "court_patron_projects"], ["087", "seek_redemption_projects"], ["088", "valence_float_canonical"], ["089", "relationship_drift_milestone"], ["090", "claim_accounts"], ["091", "backstory_secrets"], ["092", "claim_distortion_depth"], ["093", "claim_awareness_knower_index"], ["094", "scene_weather_override"], ["095", "mood_vocabulary"], ["096", "polymorphic_patron"], ["097", "trait_cold_start_relationship_constraints"], ["098", "narrative_generation_lease"], ["099", "storyteller_correspondence"], ["100", "orrery_need_clock_anchor"], ["101", "delete_project_start_summary_orphans"], ["102", "narration_job_fencing"], ["103", "bleed_uptake"], ["104", "character_experiences"], ["105", "interaction_threads"], ["106", "recall_trace"], ["107", "lore_pass_baselines"], ["108", "strip_retired_observations_from_drafts"], ["109", "extend_expiry_default_durations"], ["110", "experience_formation_sweep"], ["111", "experience_job_enqueue_gin_fence"], ["112", "character_experience_recall_eligibility"], ["113", "acquisition_formation_indexes"], ["114", "slot_scoped_idf"], ["115", "relationship_write_provenance"], ["116", "acceptance_chunk_identity"], ["117", "story_settings"], ["118", "world_clock_identity"], ["120", "deferred_work_owner"], ["121", "generation_session_truth"], ["122", "orrery_card_identity"], ["123", "character_alias_provenance"], ["124", "attempt_manifests"], ["125", "embedding_summary_jobs"], ["126", "seat_policies"], ["127", "schema_documentation"], ["128", "character_identity_rulings"], ["129", "wizard_confirmation"], ["130", "retire_psychology_endpoint_comments"], ["131", "regeneration_lineage"], ["132", "genesis_weird_level"], ["133", "idf_rebuild_command"], ["134", "drop_chunk_lifecycle_columns"], ["135", "schema_docs_backfill"], ["136", "column_comment_corrections"], ["137", "view_comments"], ["138", "adopt_unowned_fleet_indexes"], ["139", "character_relationship_bigint_ids"], ["140", "world_clock_primary_layer"]]
```

| Clone | Test |
| --- | --- |
| `qa640_810s2_contract_670688353cdf` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[sqlalchemy-chunk_id]` |
| `qa640_810s2_contract_63ac7245c15e` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[sqlalchemy-summary_id]` |
| `qa640_810s2_contract_14587fbf37e0` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[sqlalchemy-experience_id]` |
| `qa640_810s2_contract_345abc521b4e` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[tuple-chunk_id]` |
| `qa640_810s2_contract_4df8a7919ea9` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[tuple-summary_id]` |
| `qa640_810s2_contract_a3e9480c9114` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[tuple-experience_id]` |
| `qa640_810s2_contract_f4bbb14b7f3e` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[dict-chunk_id]` |
| `qa640_810s2_contract_6bbf1bd85336` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[dict-summary_id]` |
| `qa640_810s2_contract_664ce8c98e33` | `tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[dict-experience_id]` |
| `qa640_810s2_contract_0bf694a280b2` | `tests/test_embedding_table_ownership_pg.py::test_ensure_is_idempotent_and_never_builds_ann[chunk_id]` |
| `qa640_810s2_contract_91e371926746` | `tests/test_embedding_table_ownership_pg.py::test_ensure_is_idempotent_and_never_builds_ann[summary_id]` |
| `qa640_810s2_contract_d2d681600c24` | `tests/test_embedding_table_ownership_pg.py::test_ensure_is_idempotent_and_never_builds_ann[experience_id]` |
| `qa640_810s2_contract_cd5b7a04f73d` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[dimension-chunk_id]` |
| `qa640_810s2_contract_b31a0d6780bf` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[dimension-summary_id]` |
| `qa640_810s2_contract_d8cd3fb63e52` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[dimension-experience_id]` |
| `qa640_810s2_contract_028c71e85e25` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[source_type-chunk_id]` |
| `qa640_810s2_contract_e3043ce669ea` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[source_type-summary_id]` |
| `qa640_810s2_contract_e6746105f0de` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[source_type-experience_id]` |
| `qa640_810s2_contract_ece312b87bc5` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[nullable_model-chunk_id]` |
| `qa640_810s2_contract_250b91874452` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[nullable_model-summary_id]` |
| `qa640_810s2_contract_f30e9d6d7abb` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[nullable_model-experience_id]` |
| `qa640_810s2_contract_3b88232c3f0c` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[primary-chunk_id]` |
| `qa640_810s2_contract_eef51453bff9` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[primary-summary_id]` |
| `qa640_810s2_contract_01d79b42c6bc` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[primary-experience_id]` |
| `qa640_810s2_contract_c5cfdb6708a7` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[fk_target-chunk_id]` |
| `qa640_810s2_contract_db5da08baeb7` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[fk_target-summary_id]` |
| `qa640_810s2_contract_6fda61ddaf06` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[fk_target-experience_id]` |
| `qa640_810s2_contract_54f6235bd5c4` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[fk_delete-chunk_id]` |
| `qa640_810s2_contract_1f4a87a388cc` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[fk_delete-summary_id]` |
| `qa640_810s2_contract_5217de41fd59` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[fk_delete-experience_id]` |
| `qa640_810s2_contract_c710f15e3531` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[timestamp-chunk_id]` |
| `qa640_810s2_contract_94c8f35a555f` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[timestamp-summary_id]` |
| `qa640_810s2_contract_6bf7e5a6a1fa` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[timestamp-experience_id]` |
| `qa640_810s2_contract_b8f22d38c5da` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[view-chunk_id]` |
| `qa640_810s2_contract_b6baa6e0d0e1` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[view-summary_id]` |
| `qa640_810s2_contract_c7fbdbc69257` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[view-experience_id]` |
| `qa640_810s2_contract_1f7d67b34365` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[index-chunk_id]` |
| `qa640_810s2_contract_131804463e4d` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[index-summary_id]` |
| `qa640_810s2_contract_3ca48b34c38c` | `tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[index-experience_id]` |
| `qa640_810s2_contract_beee3b54fbc5` | `tests/test_embedding_table_ownership_pg.py::test_ensure_and_upsert_roll_back_with_the_caller[chunk_id]` |
| `qa640_810s2_contract_9c79d27ece9d` | `tests/test_embedding_table_ownership_pg.py::test_ensure_and_upsert_roll_back_with_the_caller[summary_id]` |
| `qa640_810s2_contract_d65f46dcdb34` | `tests/test_embedding_table_ownership_pg.py::test_ensure_and_upsert_roll_back_with_the_caller[experience_id]` |
| `qa640_810s2_contract_281a0f7076ab` | `tests/test_embedding_table_ownership_pg.py::test_constructor_leaves_missing_indexes_and_catalog_unchanged` |
| `qa640_810s2_contract_c13a7608907d` | `tests/test_embedding_table_ownership_pg.py::test_constructor_refuses_missing_vector_extension` |
| `qa640_810s2_contract_8954575b7a17` | `tests/test_embedding_table_ownership_pg.py::test_embedding_job_source_path_propagates_ensure_failure` |
| `qa640_810s2_contract_cf1c9374e03e` | `tests/test_embedding_table_ownership_pg.py::test_content_processor_embedding_method_propagates_ensure_failure` |
| `qa640_810s2_source_50e935a936cc` | `tests/test_memnon/test_source_embeddings.py::test_summaries_generate_every_vector_before_one_write_transaction` |
| `qa640_810s2_source_9fc6cd281c15` | `tests/test_memnon/test_source_embeddings.py::test_experiences_load_and_stamp_only_valid_rendered_rows` |
| `qa640_810s2_source_e5bb2a0c8ca1` | `tests/test_memnon/test_source_embeddings.py::test_stamp_shortfall_rolls_back_the_upserted_vectors` |
| `qa640_810s2_source_358b07c293d1` | `tests/test_memnon/test_source_embeddings.py::test_wrappers_are_the_shared_orchestrator` |
| `qa640_810s2_source_aaf806da6733` | `tests/test_memnon/test_source_embeddings.py::test_shared_helpers_serve_a_caller_supplied_embedder` |
| `qa640_810s2_summary384_97429bd1de7e` | `tests/test_retrograde_summary_retrieval.py::test_retrograde_summary_embedding_table_helper_accepts_dbapi_cursor` |
| `qa640_810_adopt_recreate_be363a53bb6b` | `tests/test_unowned_index_adoption_pg.py::test_migration_138_recreates_the_indexes_and_column_it_owns` |
| `qa640_810_adopt_noop_a21df017d9a2` | `tests/test_unowned_index_adoption_pg.py::test_migration_138_changes_nothing_on_a_complete_database` |
| `qa640_810_adopt_drift_50dfd2367b3a` | `tests/test_unowned_index_adoption_pg.py::test_migration_138_refuses_a_same_named_index_with_another_definition` |
| `qa640_810_no_create_all_841a30f3ada5` | `tests/test_unowned_index_adoption_pg.py::test_database_manager_construction_creates_no_table` |
| `qa640_vocab_migration_27404eb10f4b` | `tests/test_orrery/test_migrate.py::test_character_tag_vocab_migration_executes_against_slot_db` |
| `qa640_vocab_migration_d9be97713173` | `tests/test_orrery/test_migrate.py::test_completed_tag_vocab_migration_executes_against_slot_db` |
| `qa640_vocab_migration_1a6a95192310` | `tests/test_orrery/test_migrate.py::test_entity_tag_expiry_substrate_migration_executes_against_slot_db` |
| `qa640_vocab_migration_0f959e5bedc6` | `tests/test_orrery/test_migrate.py::test_faction_tag_vocab_migration_executes_against_slot_db` |
| `qa640_vocab_migration_f4a851d87f7f` | `tests/test_orrery/test_migrate.py::test_state_clearance_event_type_migration_executes_against_slot_db` |
| `qa640_vocab_migration_4bd9360a82fb` | `tests/test_orrery/test_migrate.py::test_kind_qualified_contact_migration_executes_against_slot_db` |
| `qa640_grieving_migration_e402787de711` | `tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db` |
| `qa640_810_template_26af05737d76` | `tests/test_new_story_setup.py::test_template_clone_replays_no_migration` |
| `qa640_810_clone_5d66a5d811ee` | `tests/test_new_story_setup.py::test_template_clone_replays_no_migration` |
| `qa640_810_fail_0306709450d4` | `tests/test_new_story_setup.py::test_failing_migration_is_unapplied_and_initialization_raises` |
| `qa640_schema_docs_c7afb9dff257` | `tests/test_schema_documentation_pg.py::test_schema_documentation_coverage` |
| `qa640_docs_refresh_ab29f04466c6` | `tests/test_schema_documentation_pg.py::test_story_setup_and_runner_preserve_comments` |
| `qa640_regen_truncate_78611456c626` | `tests/test_regenerate_embeddings_truncate_pg.py::test_truncate_table_keeps_rows_when_the_model_artifact_is_missing` |
| `qa640_regen_truncate_976635837dc3` | `tests/test_regenerate_embeddings_truncate_pg.py::test_chunk_keeps_its_row_when_the_model_artifact_is_missing` |
| `qa665_072625389da8` | `tests/test_orrery/test_retrograde_embedding_pg.py::test_batch_embedding_writes_every_summary_model_pair` |
| `qa640_766_schema_54ac055dc074` | `tests/test_memnon/test_ann_gate.py::test_ann_candidate_index_build_drop` |
| `qa885_transaction_writer_d683d93e5de0` | `tests/test_pg_disposable_target.py::test_transaction_relationship_writer_writes_on_a_clone` |

The new 66-case log preserves each malformed-object expected/observed error.
On the caller's same still-open transaction the tests assert unchanged catalog,
comments, constraints, indexes and marker data before rollback, then again
after caller rollback (`tests/test_embedding_table_ownership_pg.py:298-365`).
The creation/upsert rollback proof is at `:370-393`; constructor invariance is
at `:396-416`; the real job-source failure and rollback proof is at `:428-468`.
The three corpora and all three real adapters verify catalog shape and exact
comments using independent SQL (`:150-222`). This run adds no catalog repair.

## Remaining Gates and Coordinator Question

At STOP, the standalone reachability command and final Black/flake8/mypy
branch-versus-main comparison checks remain unrun. Earlier root splits,
config, IR-eval and LORE results remain dated evidence; they are not claimed
as fresh post-merge runs. No final all-offline green gate, whole-tree
PostgreSQL gate, PR, push, merge-to-main, or landing is claimed.

Coordinator: authorize converting the untouched
`test_embedding_upsert_binds_each_correct_experience_id` regression to a real
disposable-clone proof that preserves its per-experience vector binding and
result assertions, then resume the remaining checks and publication?

The accepted legacy-importer defect remains deferred under
[issue #1091](https://github.com/pythagorakase/nexus/issues/1091).
No fresh corpus result or new #964 disposition is claimed. No paid provider
call, save/template write, owner-service action, main-checkout modification,
or other-worktree modification occurred. Fixtures retained TEST story pins
and the provider-only guard; configured embedding inference was local.

Landing notes remain: no migration or fleet migration application. Migration
022 documents lazy ownership; migration 138 owns fixed indexes. The
coordinator restarts `nexus restart gateway` by name after pulling product
changes. No UI bundle change or rebuild. The coordinator owns the final
whole-tree PostgreSQL gate.

Codex — GPT-6.

---

# STOP-REPORT: 810-S2 Amendment 2 (2026-10-01)

## New Frozen-Fingerprint Failure

Resumed from accepted checkpoint `b619d8d347d1e817ee82e5da1b6e1c902d7c1b56`
on `claude/810-embedding-table-ownership`. All commands ran from the assigned
worktree. `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c
'import nexus;print(nexus.__file__)'` printed this worktree's `nexus/__init__.py`.
The common rules, including Static Checks, both amendments, original order,
previous verification, and current issue #810 body/comments were read. The
binding 810-Q3 decision remains unchanged.

Amendment 2's guard update is complete and passes. The MEMNON offline split
then fails in an unchanged file:

`tests/test_memnon/test_ann_gate.py::test_ann_search_sql_matches_repaired_baseline[nexus/agents/memnon/utils/db_access.py]`

The test at `tests/test_memnon/test_ann_gate.py:258-277` fingerprints every AST
string matching `SELECT `, `WITH text_search`, or `<=>` in the entire module.
Its fixture expects `f24ac6cf9aa8e45d4cbb5f85194fa8ed68b875bfb460cb80b2b277d0eb370ac9`.
The branch computes `35ecf4de78ec08ff80f23f5d96037125e428d6a6597e18619aea5082317d5497`.
Both starting main `2e70e9cb` and fetched `origin/main` `67256d15` compute the
expected fingerprint. This is a new consequence of the ordered deletion,
not an exempt #885 owner-slot failure or existing main diagnostic.

A read-only AST multiset comparison shows **no added matching expression**.
Exactly four expressions disappeared, all from the deleted
`setup_database_indexes`: the vector-extension existence SELECT, the HNSW
index existence f-string, and its two constant fragments. None of the search
expressions changed. Raw comparison evidence is in the assigned scratch
`ann-fingerprint-diagnosis.json`. The unchanged retrieval fingerprint test
therefore also freezes schema-setup SQL that this order explicitly deletes.

Verbatim failure excerpt:

```text
E       AssertionError: assert '35ecf4de78ec...a5082317d5497' == 'f24ac6cf9aa8...277d0eb370ac9'
E
E         - f24ac6cf9aa8e45d4cbb5f85194fa8ed68b875bfb460cb80b2b277d0eb370ac9
E         + 35ecf4de78ec08ff80f23f5d96037125e428d6a6597e18619aea5082317d5497

tests/test_memnon/test_ann_gate.py:275: AssertionError
```

The common rule binds: "Any other failure in a file you did not change: report
the exact test id and the failure tail, do not fix it, do not skip it; the
coordinator triages." STOP. Neither the test nor
`tests/test_memnon/fixtures/ann_repaired_sql.json` was changed, and no setup SQL
was restored to satisfy the frozen hash.

## Authorized Changes and Remaining Gates

Removed exactly three stale `connection-owner-literal` exemptions:

- `test_memnon_db_access.py`, `database_url("save_04")`, two entries.
- `test_memnon/test_source_embeddings.py`,
  `database.connect("save_05", dict_cursor=True)`, one entry.

The synthetic exemption test now uses the existing
`test_scheduler_helpers_routing.py` slot-name exemptions. It proves a new
unlisted source remains refused and a second duplicate exceeds its one listed
use. No other guard behavior, allowlist, or exemption changed. Guard-only
coverage passes all 80 tests; the root split containing the guard also passes.

The broad offline-core run was deliberately interrupted to split its slow CLI
coverage into bounded commands; its 476-passed partial result is not a gate
pass. Root splits 1 through 6 and the config, test_config, test_ir_eval_v2 and
LORE directories passed. The MEMNON split failed as above. Every tail and exact
child command follows. A collection-only command built the complete 3259-node
split plan; collection is not claimed as a proof gate.

At STOP, runtime/util offline directories, API/Orrery offline suites, the
standalone reachability command, Black/flake8/mypy comparison gates, and the
amended PostgreSQL guard rerun remain unrun. Reachability did run as part of
root split 5, whose result is preserved below. The prior accepted PostgreSQL
proofs remain dated evidence, not fresh results from this resumption. No new
disposable clone was created, so there are no new migration stamps to report.
No paid call, owner database write, gateway action, main-checkout modification,
or other-worktree modification was made. `git diff --check` passes.

A fetch from this worktree observed `origin/main` at
`67256d15e2c5cf395c4336bb63f4a42472493db0`. Both accepted checkpoints are
preserved unchanged; no rebase, merge, push or PR was performed. A clarification
was requested because rebasing these commits onto advanced main necessarily
rewrites their IDs, while this resumption explicitly prohibits history rewrite.
No response was received before the separate test failure required STOP.

## Open Questions for the Coordinator

1. Authorize updating the db_access fingerprint for the exact ordered setup
   deletion, or narrow the frozen fingerprint to retrieval functions while
   proving their AST expressions unchanged?
2. Resolve newest-main synchronization: merge origin/main to keep both accepted
   checkpoint commit IDs, or explicitly permit their IDs to change in a rebase?
3. Resume this checkpoint after triage to finish the remaining gates and publish?

Legacy importer issue #1091 remains deferred. No fresh corpus result or new
#964 disposition is claimed. Landing remains no migration or fleet application;
the coordinator restarts `nexus restart gateway` by name and owns the final
whole-tree PostgreSQL gate. No UI rebuild is needed.

## Exact Commands and Verbatim Tails for This Resumption

The scratch foreground wrapper retains the 590-second command limit and
120-second silence limit. The commands below are its exact child argv rendered
as shell commands; full logs and `runs.jsonl` remain in the assigned scratch.
Offline skips are preserved, not counted as PostgreSQL proof.

### guard-amendment2 (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_owner_target_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
80 passed, 5 warnings in 2.95s
```

### offline-core-amendment2 (Exit 2)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-core-amendment2 tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/selectors.py:415: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
476 passed, 15 skipped, 7 warnings in 244.09s (0:04:04)
```

### offline-root-1 (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-root-1 tests/test_backfill_review_packet.py tests/test_bootstrap_episode_pg.py tests/test_character_identity.py tests/test_character_name_reveals.py tests/test_character_name_reveals_pg.py tests/test_character_relationship_id_types_pg.py tests/test_character_tag_manifest.py tests/test_chunk_lifecycle_columns_migration_pg.py tests/test_cli.py tests/test_cli_choice_http.py tests/test_cli_contract.py tests/test_cli_generation_http.py tests/test_cli_inspect_pg.py tests/test_cli_model_selection.py tests/test_cli_session_wait.py tests/test_cli_wizard_confirmation.py tests/test_clock_face.py tests/test_commit_choice_presence_pg.py tests/test_commit_chronology.py tests/test_commit_handler_sync.py tests/test_connection_lifecycle.py tests/test_correspondence.py tests/test_correspondence_live.py tests/test_database_contract.py tests/test_db_converters.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
490 passed, 28 skipped, 5 warnings in 261.37s (0:04:21)
```

### offline-root-2 (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-root-2 tests/test_dbname_audit.py tests/test_doc_front_matter.py tests/test_embedding_artifacts.py tests/test_embedding_table_ownership_pg.py tests/test_entity_reference_parity_pg.py tests/test_entity_tag_manifest_apply.py tests/test_enum_column_comment_labels_pg.py tests/test_faction_table_audit.py tests/test_gis_scripts_live.py tests/test_golden_path_live.py tests/test_idf_dictionary_pg.py tests/test_inherited_slot_isolation_pg.py tests/test_intention_revision_weight.py tests/test_interaction_boundary.py tests/test_interactions_pg.py tests/test_issue_601_wizard_live.py tests/test_jobs_cli_pg.py tests/test_live_gate_clones_pg.py tests/test_local_skald_live.py tests/test_logon_mock_integration.py tests/test_lore_adapter_metadata.py tests/test_measure_place_coordinate_costs.py tests/test_measure_place_coordinate_costs_pg.py tests/test_measure_place_scale_grammar.py tests/test_measure_place_scale_grammar_pg.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
120 passed, 139 skipped, 5 warnings in 15.43s
```

### offline-root-3 (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-root-3 tests/test_memnon_cross_encoder.py tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder_dependencies.py tests/test_memnon_db_access.py tests/test_memnon_embedding_cache.py tests/test_memnon_embedding_contract.py tests/test_memnon_model_failures_pg.py tests/test_memnon_runtime_config.py tests/test_memnon_script_model_loaders.py tests/test_migration_comment_lint.py tests/test_mock_openai.py tests/test_model_artifact_lock_committed.py tests/test_model_drift.py tests/test_model_registry_live.py tests/test_name_reveal_staged_bindings.py tests/test_name_reveal_staged_bindings_pg.py tests/test_name_reveal_tag_validation.py tests/test_name_reveal_tag_validation_pg.py tests/test_native_structured_output.py tests/test_new_story_cache.py tests/test_new_story_cli.py tests/test_new_story_integration.py tests/test_new_story_schemas.py tests/test_new_story_setup.py tests/test_new_story_setup_config.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
360 passed, 48 skipped, 8 warnings in 35.58s
```

### offline-root-4 (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-root-4 tests/test_openai_registry_capabilities.py tests/test_orrery_tag_validation.py tests/test_orrery_tag_validation_pg.py tests/test_owner_target_guard.py tests/test_pg_accepted_turn_factory.py tests/test_pg_adjudication_ledger_seed.py tests/test_pg_anchor_pair_tag_seeds.py tests/test_pg_character_pair_seed.py tests/test_pg_disposable_target.py tests/test_pg_legacy_faction_tag_seed.py tests/test_pg_target_contract.py tests/test_place_tag_manifest.py tests/test_player_identity_consumers_pg.py tests/test_postgres_tools.py tests/test_presence_audit.py tests/test_presence_boost.py tests/test_presence_boost_pg.py tests/test_presence_reconciliation.py tests/test_presence_roster.py tests/test_presence_roster_pg.py tests/test_prompt_lint.py tests/test_prompt_tag_vocabulary_pg.py tests/test_prose_metrics.py tests/test_prose_metrics_pg.py tests/test_qa_shift.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
457 passed, 130 skipped, 7 warnings in 36.49s
```

### offline-root-5 (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-root-5 tests/test_reachability.py tests/test_rebuild_memory_idf_pg.py tests/test_record_revelation_cli_pg.py tests/test_reentry_wire_ledger.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_register_drift_study.py tests/test_retrograde_summary_retrieval.py tests/test_routine_delta_grammar_probe_pg.py tests/test_runtime_home.py tests/test_scheduler_helpers_basetemp.py tests/test_scheduler_helpers_routing.py tests/test_schema_documentation_pg.py tests/test_secret_manager.py tests/test_secret_store_guard.py tests/test_secret_store_integration.py tests/test_skald_wire.py tests/test_slot_routed_entrypoints.py tests/test_slot_utils.py tests/test_summary_triggers.py tests/test_tags_audit_pg.py tests/test_trait_compiler.py tests/test_trait_compiler_integration.py tests/test_trait_input_derivation.py tests/test_trait_menu_docs.py tests/test_travel_reachability.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
442 passed, 76 skipped, 7 warnings in 44.54s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### offline-root-6 (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-root-6 tests/test_travel_reachability_pg.py tests/test_turn_observation.py tests/test_unowned_index_adoption_pg.py tests/test_usage_recorder.py tests/test_wizard_agent.py tests/test_wizard_live.py tests/test_wizard_opening_presence_pg.py tests/test_world_clock_contract_pg.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
60 passed, 34 skipped, 7 warnings in 6.07s
```

### offline-config (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-config tests/config
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
121 passed, 5 warnings in 6.04s
```

### offline-test_config (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-test_config tests/test_config
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
82 passed, 5 warnings in 4.26s
```

### offline-test_ir_eval_v2 (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-test_ir_eval_v2 tests/test_ir_eval_v2
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
12 passed, 5 warnings in 2.56s
```

### offline-test_lore (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-test_lore tests/test_lore
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
406 passed, 50 skipped, 5 warnings in 21.20s
```

### offline-test_memnon (Exit 1)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-offline-test_memnon tests/test_memnon
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_memnon/test_ann_gate.py::test_ann_search_sql_matches_repaired_baseline[nexus/agents/memnon/utils/db_access.py]
1 failed, 42 passed, 8 skipped, 5 warnings in 6.83s
```

Codex — GPT-6.

---

## Accepted Second Stop-Report (Checkpoint b619d8d3)

# STOP-REPORT: 810-S2 Amendment 1 (2026-10-01)

## Required Guard Exemptions Are Stale

Resumed from accepted checkpoint `92d6fb706dca3cf41a872bfc248908d933cc1281`.
`origin/main` was fetched and rebased before editing; that fetch observed
`2e70e9cb2c566f6f48e70ea84874670a719055f9`, and Git reported the branch
already up to date. During the gates the shared remote-tracking ref advanced
to `67256d15` through another session; this stopped branch has not yet been
rebased onto that commit. A fresh fetch/rebase remains required before any push. The checkpoint remains an ancestor; no history was rewritten.
All commands ran from the assigned worktree. Python import verification again
printed this worktree's `nexus/__init__.py`.

The amended writer proof and three fixture collisions are resolved. The required
remaining proof gate now fails at
`tests/test_owner_target_guard.py::test_every_allowlist_and_exemption_entry_is_live`.
The deleted setup tests used two `database_url("save_04")` probes; the converted
source test used one `database.connect("save_05", dict_cursor=True)` probe.
Their exemptions remain in the unchanged `tests/test_owner_target_guard.py`
(lines 159-173). The stale-exemption assertion is at line 521. This is a new
consequence of the ordered test removal/conversion, not an exempt #885 failure
and not an embedding product failure.

The working rules explicitly say: "Any other failure in a file you did not
change: report the exact test id and the failure tail, do not fix it, do not
skip it; the coordinator triages." The proof gate is not green. The guard and
its exemptions are untouched; no fake owner probes were restored. STOP pending
coordinator authorization for the guard's affected exemptions and synthetic
exemption-use test (lines 525-544). No push or PR was made.

## Amended Work and Current Evidence

- `tests/test_embedding_table_ownership_pg.py:72-86` reads the next available scene
  before each shared seed, eliminating the duplicate `S01E01_001` preparation
  failures in all three converted source cases. All five converted cases passed.
- `tests/test_embedding_table_ownership_pg.py:428-471` uses the embedding job's
  `_NARRATIVE_CHUNKS` specification and the actual configured local
  `EmbeddingManager` through `generate_source_vectors` and `upsert_source_vectors`.
  It does not run the durable queue itself. The helper's `RuntimeError` class and
  exact message propagate unchanged. The caller rolls back a prior 3d lazy table,
  vector insert and narrative edit; original text, NULL stamp, malformed marker
  row and catalog remain unchanged. The logged exception is:

  `chunk_embeddings_2560d.chunk_id type/nullability: expected ('bigint', True); observed None`

- `tests/test_embedding_table_ownership_pg.py:474-499` exercises the real legacy
  `_generate_chunk_embeddings` method with a real SQLAlchemy session and local
  embedder, avoiding the metadata INSERT. Its ensure error propagates and its
  catalog remains unchanged. `tests/test_memnon_db_access.py:32-79` independently
  checks the SQL alias, six constructors, narrative parameters and bare re-raise.
- Constructor catalog invariance and missing-extension refusal passed (lines
  398-425); all nine corpus/adapter contract cases, three idempotence/ANN cases,
  27 malformed-object cases and three caller rollback cases passed. Catalog
  definitions, exact comments and foreign-key cascade are asserted independently
  at lines 145-228; malformed-object state is checked before and after caller
  rollback at lines 304-370. The successful captured output contains the
  object-specific expected/observed errors for every malformed case.
- The 384d real DBAPI proof passed on rerun. Adoption, database-contract,
  migration/setup, schema-documentation, regenerator truncate, Retrograde,
  explicit ANN and disposable-target proofs passed. The separate owner guard
  liveness failure is the only remaining failure in those proof groups.
- The legacy importer defect remains deferred to
  [issue #1091](https://github.com/pythagorakase/nexus/issues/1091), per the supplied
  amendment. No `store_narrative_chunk` clone call was made on this resumed run,
  and no metadata schema or importer repair was made. No fresh corpus result or
  #964 disposition is claimed.

The first resumed proof run had an instrumentation-only failure: the scratch
clone recorder replaced its own saved fixture function, causing recursion in
the lazily imported 384d test. The recorder was corrected to exclude itself;
the failed test rerun passed. The other 65 tests passed in that first run.
This is distinct from the prior slug preparation failures and #1091.

## Exact Commands and Verbatim Tails

Every gate used the foreground scratch `run_gate.py` wrapper, with a 590-second
limit and a 120-second silence limit. None timed out. TMPDIR and pytest base temp
were under the assigned scratch directory. The commands below are the exact
child argv rendered as shell commands. The clone-recorder plugin performs real
read-only queries, not mock database responses. Every proof run reports the
secret-store guard and `owner targets: none`. All inference remained local;
TEST story pins and the provider-only guard were retained.

### amended-ownership (Exit 1)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership:/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --capture=tee-sys --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-ownership -p tests.dbname_audit -p clone_manifest_810s2 tests/test_embedding_table_ownership_pg.py tests/test_memnon_db_access.py tests/test_memnon/test_source_embeddings.py tests/test_retrograde_summary_retrieval.py
```

```text
../../../../.pyenv/versions/3.11.12/lib/python3.11/contextlib.py:137: in __enter__
    return next(self.gen)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/clone_manifest_810s2.py:14: in recorded
    with original(*args, **kwargs) as dbname:
../../../../.pyenv/versions/3.11.12/lib/python3.11/contextlib.py:137: in __enter__
    return next(self.gen)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/clone_manifest_810s2.py:14: in recorded
    with original(*args, **kwargs) as dbname:
E   RecursionError: maximum recursion depth exceeded
!!! Recursion detected (same locals & position)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 52 targets: postgres, qa640_810s2_contract_* x46, qa640_810s2_source_* x5
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_retrograde_summary_retrieval.py::test_retrograde_summary_embedding_table_helper_accepts_dbapi_cursor
1 failed, 65 passed in 78.02s (0:01:18)
```

### summary384-rerun (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership:/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-summary384 -p tests.dbname_audit -p clone_manifest_810s2 tests/test_retrograde_summary_retrieval.py::test_retrograde_summary_embedding_table_helper_accepts_dbapi_cursor
```

```text
.                                                                        [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_810s2_summary384_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed in 3.20s
```

### pg-contract-migrations (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership:/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-contract-migrations -p tests.dbname_audit -p clone_manifest_810s2 tests/test_database_contract.py tests/test_unowned_index_adoption_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py
```

```text
........................................................................ [ 62%]
............................................                             [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 23 targets: nexus_m10_fresh_test_96863, nexus_m10_template_test_96863, postgres, qa640_810_adopt_drift_*, qa640_810_adopt_noop_*, qa640_810_adopt_recreate_*, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_no_create_all_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_connection_contract, qa640_grieving_migration_*, qa640_raw_url_contract, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:55203 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[1] at local:55204 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[0] at local:55211 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard; two_clusters[1] at local:55212 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard
dbname audit: owner names admitted on registered clusters: none
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
116 passed in 33.63s
```

### pg-schema-writers (Exit 1)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership:/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/pytest-schema-writers -p tests.dbname_audit -p clone_manifest_810s2 tests/test_schema_documentation_pg.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_orrery/test_retrograde_embedding_pg.py tests/test_memnon/test_ann_gate.py::test_ann_candidate_index_build_drop tests/test_memnon/test_ann_gate.py::test_ann_alias_candidates_and_database_errors tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
......................................                                   [100%]
=================================== FAILURES ===================================
_______________ test_every_allowlist_and_exemption_entry_is_live _______________

    def test_every_allowlist_and_exemption_entry_is_live() -> None:
        """A stale allowlisted file or exemption is removed, not kept."""

        for relative, reason in ALLOWLISTED_FILES.items():
            assert (TESTS_ROOT / relative).is_file(), relative
            assert reason.strip(), relative
        found = Counter(
            (finding.path, finding.rule, finding.source) for finding in tree_findings()
        )
        listed = Counter(item.key for item in EXEMPTIONS)
        for item in EXEMPTIONS:
            assert item.reason.strip(), item
        stale = {key: count for key, count in listed.items() if found[key] < count}
>       assert stale == {}, f"stale exemptions (listed more than found): {stale}"
E       AssertionError: stale exemptions (listed more than found): {('test_memnon_db_access.py', 'connection-owner-literal', 'database_url("save_04")'): 2, ('test_memnon/test_source_embeddings.py', 'connection-owner-literal', 'database.connect("save_05", dict_cursor=True)'): 1}
E       assert {('test_memno...ave_04")'): 2} == {}
E
E         Left contains 2 more items:
E         {('test_memnon/test_source_embeddings.py', 'connection-owner-literal', 'database.connect("save_05", dict_cursor=True)'): 1,
E          ('test_memnon_db_access.py', 'connection-owner-literal', 'database_url("save_04")'): 2}
E         Use -v to get more diff

tests/test_owner_target_guard.py:521: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: postgres, qa640_766_schema_*, qa640_docs_refresh_*, qa640_regen_truncate_* x2, qa640_schema_docs_* x3, qa665_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_owner_target_guard.py::test_every_allowlist_and_exemption_entry_is_live
1 failed, 181 passed in 25.01s
```

Formatting:

```sh
/Users/pythagor/nexus/.venv/bin/python -m black tests/test_embedding_table_ownership_pg.py tests/test_memnon_db_access.py
```

```text
reformatted tests/test_memnon_db_access.py
reformatted tests/test_embedding_table_ownership_pg.py

All done! ✨ 🍰 ✨
2 files reformatted.
```

`rg -n 'setup_database_indexes|_setup_hybrid_search' nexus scripts ir_eval`
produced no output (exit 1). `git diff --check` produced no output (exit 0).

The offline suites, reachability and final Black/flake8/mypy comparison gates
remain unrun at this new STOP. No static success or baseline classification is
claimed. Their sanctioned invocation remains `mypy --explicit-package-bases`
with origin/main versions in the assigned scratch directory and no new
branch diagnostics. The coordinator's whole-tree PostgreSQL gate is unrun.

## Disposable Clone Migration Manifest

Read-only instrumentation is at the assigned scratch directory's
`clone_manifest_810s2.py`; full raw records are in `clone-manifest.jsonl`.
After the instrumentation fix it recorded 22 real helper clones, including
starting migration versions and names, immediately before yielding. The initial
65-success run did not produce recorder records; its ownership fixture directly
printed all 46 ownership clone version lists, preserved below. The five converted
source clones did not export their per-clone stamps; that evidence is incomplete
at STOP. Separate private-cluster/database fixtures retain their own gates and
audits; no complete manifest is claimed.

### Stamp Set 1

```text
[["001", "baseline"], ["002", "add_choice_columns"], ["003", "add_layer_zone_drafts"], ["004", "fix_global_variables_fk"], ["005", "add_incubator_choice_object"], ["006", "add_save_slots_model"], ["007", "normalize_new_story_creator"], ["009", "remove_assets_save_slots"], ["010", "add_traits_table"], ["011", "add_traits_confirmed"], ["012", "add_wizard_choice_object"], ["014", "add_2560d_4096d_embeddings"], ["015", "add_ir_eval_v2_tables"], ["016", "add_ir_eval_v1_query_tables"], ["017", "add_judgment_justification"], ["018", "narrative_chunks_column_comments"], ["019", "add_incubator_choice_text"], ["020", "drop_chunk_embeddings_0384d"], ["021", "dedup_embedded_state"], ["022", "compound_embedding_pk_lazy_tables"], ["023", "orrery_schema"], ["024", "orrery_commit_pipeline"], ["025", "orrery_package_library_vocab"], ["026", "relationship_valence_magnitude"], ["027", "orrery_package_library_round2_vocab"], ["028", "orrery_sunhelm_needs"], ["029", "orrery_need_state_init_trigger"], ["030", "orrery_place_affordance_vocab"], ["031", "orrery_slot2_semantic_tag_vocab"], ["032", "orrery_interpersonal_needs"], ["033", "orrery_travel_work"], ["034", "orrery_concealment_surveillance_vocab"], ["035", "orrery_osm_route_graph"], ["036", "skald_inline_tag_runtime"], ["037", "orrery_tag_category_registry"], ["038", "orrery_tag_baseline_reconciliation"], ["039", "new_story_character_orrery_tags"], ["040", "storyteller_authorial_directives"], ["041", "orrery_authority_model"], ["042", "orrery_entity_pair_tags"], ["043", "orrery_category_refactor_phase1"], ["044", "disambiguate_status_reputation_traits"], ["045", "trait_compiler_substrate"], ["046", "canonical_grieving_state"], ["047", "kind_qualified_contact_pair_tags"], ["048", "orrery_hunting_pair_tag"], ["049", "orrery_entity_tag_expiry_substrate"], ["050", "orrery_state_clearance_event_types"], ["051", "orrery_time_tag_clearance_kind"], ["052", "orrery_faction_tag_vocab"], ["053", "retire_faction_legacy_write_defaults"], ["054", "orrery_completed_tag_vocab"], ["055", "orrery_character_tag_vocab"], ["056", "orrery_routine_anchors"], ["057", "orrery_need_bodyform_applicability"], ["058", "retire_faction_legacy_columns"], ["059", "orrery_social_travel_event"], ["060", "retrograde_persistence_sources"], ["061", "trait_compiler_sponsors_pair_tag"], ["062", "retrograde_maturation_jobs"], ["063", "orrery_adjudication_history"], ["064", "tag_provenance_forward_fix"], ["065", "reconstructability"], ["066", "signal_event_vocab"], ["067", "rename_orrery_templates"], ["068", "mundane_band_event_vocab"], ["069", "ecology_event_vocab"], ["070", "need_state_chunk_stamp"], ["071", "retrograde_world_layer"], ["072", "retrograde_layer_backfill"], ["073", "rename_dream_to_atemporal"], ["074", "plan_relocation_projects"], ["075", "retrieval_coverage_log"], ["076", "claims_awareness"], ["077", "recruit_ally_projects"], ["078", "retrograde_summary_storage"], ["079", "need_state_chunk_provenance_comment"], ["080", "epistemics_knowers"], ["081", "faction_project_contexts"], ["082", "generation_model_provenance"], ["083", "claim_propagation_ledger"], ["084", "build_venture_projects"], ["085", "pursue_romance_projects"], ["086", "court_patron_projects"], ["087", "seek_redemption_projects"], ["088", "valence_float_canonical"], ["089", "relationship_drift_milestone"], ["090", "claim_accounts"], ["091", "backstory_secrets"], ["092", "claim_distortion_depth"], ["093", "claim_awareness_knower_index"], ["094", "scene_weather_override"], ["095", "mood_vocabulary"], ["096", "polymorphic_patron"], ["097", "trait_cold_start_relationship_constraints"], ["098", "narrative_generation_lease"], ["099", "storyteller_correspondence"], ["100", "orrery_need_clock_anchor"], ["101", "delete_project_start_summary_orphans"], ["102", "narration_job_fencing"], ["103", "bleed_uptake"], ["104", "character_experiences"], ["105", "interaction_threads"], ["106", "recall_trace"], ["107", "lore_pass_baselines"], ["108", "strip_retired_observations_from_drafts"], ["109", "extend_expiry_default_durations"], ["110", "experience_formation_sweep"], ["111", "experience_job_enqueue_gin_fence"], ["112", "character_experience_recall_eligibility"], ["113", "acquisition_formation_indexes"], ["114", "slot_scoped_idf"], ["115", "relationship_write_provenance"], ["116", "acceptance_chunk_identity"], ["117", "story_settings"], ["118", "world_clock_identity"], ["120", "deferred_work_owner"], ["121", "generation_session_truth"], ["122", "orrery_card_identity"], ["123", "character_alias_provenance"], ["124", "attempt_manifests"], ["125", "embedding_summary_jobs"], ["126", "seat_policies"], ["127", "schema_documentation"], ["128", "character_identity_rulings"], ["129", "wizard_confirmation"], ["130", "retire_psychology_endpoint_comments"], ["131", "regeneration_lineage"], ["132", "genesis_weird_level"], ["133", "idf_rebuild_command"], ["134", "drop_chunk_lifecycle_columns"], ["135", "schema_docs_backfill"], ["136", "column_comment_corrections"], ["137", "view_comments"], ["138", "adopt_unowned_fleet_indexes"], ["139", "character_relationship_bigint_ids"], ["140", "world_clock_primary_layer"]]
```

| Clone | Test |
| --- | --- |
| `qa640_810s2_summary384_f5a26eb12be5` | `tests/test_retrograde_summary_retrieval.py::test_retrograde_summary_embedding_table_helper_accepts_dbapi_cursor` |
| `qa640_810_adopt_recreate_fa73dbc431af` | `tests/test_unowned_index_adoption_pg.py::test_migration_138_recreates_the_indexes_and_column_it_owns` |
| `qa640_810_adopt_noop_4079eb16ca67` | `tests/test_unowned_index_adoption_pg.py::test_migration_138_changes_nothing_on_a_complete_database` |
| `qa640_810_adopt_drift_90732f622e86` | `tests/test_unowned_index_adoption_pg.py::test_migration_138_refuses_a_same_named_index_with_another_definition` |
| `qa640_810_no_create_all_bbe9db67e3fe` | `tests/test_unowned_index_adoption_pg.py::test_database_manager_construction_creates_no_table` |
| `qa640_vocab_migration_bf7364628482` | `tests/test_orrery/test_migrate.py::test_character_tag_vocab_migration_executes_against_slot_db` |
| `qa640_vocab_migration_35a8893fe4b8` | `tests/test_orrery/test_migrate.py::test_completed_tag_vocab_migration_executes_against_slot_db` |
| `qa640_vocab_migration_1c8be94ae09e` | `tests/test_orrery/test_migrate.py::test_entity_tag_expiry_substrate_migration_executes_against_slot_db` |
| `qa640_vocab_migration_dde2b4a5035f` | `tests/test_orrery/test_migrate.py::test_faction_tag_vocab_migration_executes_against_slot_db` |
| `qa640_vocab_migration_d1604941c2ed` | `tests/test_orrery/test_migrate.py::test_state_clearance_event_type_migration_executes_against_slot_db` |
| `qa640_vocab_migration_195fc9330222` | `tests/test_orrery/test_migrate.py::test_kind_qualified_contact_migration_executes_against_slot_db` |
| `qa640_grieving_migration_3c087a5f30c9` | `tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db` |
| `qa640_810_template_12ccddb1a892` | `tests/test_new_story_setup.py::test_template_clone_replays_no_migration` |
| `qa640_810_clone_0a55c487792d` | `tests/test_new_story_setup.py::test_template_clone_replays_no_migration` |
| `qa640_810_fail_78d830ad8566` | `tests/test_new_story_setup.py::test_failing_migration_is_unapplied_and_initialization_raises` |
| `qa640_schema_docs_686af1a3196d` | `tests/test_schema_documentation_pg.py::test_schema_documentation_coverage` |
| `qa640_docs_refresh_326d9abab1dc` | `tests/test_schema_documentation_pg.py::test_story_setup_and_runner_preserve_comments` |
| `qa640_regen_truncate_4dea11c54e6d` | `tests/test_regenerate_embeddings_truncate_pg.py::test_truncate_table_keeps_rows_when_the_model_artifact_is_missing` |
| `qa640_regen_truncate_97773295ff38` | `tests/test_regenerate_embeddings_truncate_pg.py::test_chunk_keeps_its_row_when_the_model_artifact_is_missing` |
| `qa665_6190bfa2a05f` | `tests/test_orrery/test_retrograde_embedding_pg.py::test_batch_embedding_writes_every_summary_model_pair` |
| `qa640_766_schema_95d83dbbf3e6` | `tests/test_memnon/test_ann_gate.py::test_ann_candidate_index_build_drop` |
| `qa885_transaction_writer_d5109e7be6c8` | `tests/test_pg_disposable_target.py::test_transaction_relationship_writer_writes_on_a_clone` |

### Initial Ownership Clone Version Evidence

All 46 clones printed this exact starting version list:

```text
[('001',), ('002',), ('003',), ('004',), ('005',), ('006',), ('007',), ('009',), ('010',), ('011',), ('012',), ('014',), ('015',), ('016',), ('017',), ('018',), ('019',), ('020',), ('021',), ('022',), ('023',), ('024',), ('025',), ('026',), ('027',), ('028',), ('029',), ('030',), ('031',), ('032',), ('033',), ('034',), ('035',), ('036',), ('037',), ('038',), ('039',), ('040',), ('041',), ('042',), ('043',), ('044',), ('045',), ('046',), ('047',), ('048',), ('049',), ('050',), ('051',), ('052',), ('053',), ('054',), ('055',), ('056',), ('057',), ('058',), ('059',), ('060',), ('061',), ('062',), ('063',), ('064',), ('065',), ('066',), ('067',), ('068',), ('069',), ('070',), ('071',), ('072',), ('073',), ('074',), ('075',), ('076',), ('077',), ('078',), ('079',), ('080',), ('081',), ('082',), ('083',), ('084',), ('085',), ('086',), ('087',), ('088',), ('089',), ('090',), ('091',), ('092',), ('093',), ('094',), ('095',), ('096',), ('097',), ('098',), ('099',), ('100',), ('101',), ('102',), ('103',), ('104',), ('105',), ('106',), ('107',), ('108',), ('109',), ('110',), ('111',), ('112',), ('113',), ('114',), ('115',), ('116',), ('117',), ('118',), ('120',), ('121',), ('122',), ('123',), ('124',), ('125',), ('126',), ('127',), ('128',), ('129',), ('130',), ('131',), ('132',), ('133',), ('134',), ('135',), ('136',), ('137',), ('138',), ('139',), ('140',)]
```

- `qa640_810s2_contract_6c73a1894d7e`
- `qa640_810s2_contract_6ef82dfecb06`
- `qa640_810s2_contract_505209811cca`
- `qa640_810s2_contract_4501df5d1bda`
- `qa640_810s2_contract_f6018af7475c`
- `qa640_810s2_contract_72af2a42f079`
- `qa640_810s2_contract_01c23d1a10fe`
- `qa640_810s2_contract_b399ba8944a4`
- `qa640_810s2_contract_7ad319919482`
- `qa640_810s2_contract_38c075ed5298`
- `qa640_810s2_contract_92f0d3f1d48f`
- `qa640_810s2_contract_36425408d520`
- `qa640_810s2_contract_9b57835cb5bf`
- `qa640_810s2_contract_da40798fb4d1`
- `qa640_810s2_contract_04c4b74e1d71`
- `qa640_810s2_contract_bc18bd9f8097`
- `qa640_810s2_contract_eebe83919d06`
- `qa640_810s2_contract_9b6b89b8a214`
- `qa640_810s2_contract_f806fcd28a00`
- `qa640_810s2_contract_7f9e8f430861`
- `qa640_810s2_contract_f261b3641338`
- `qa640_810s2_contract_2d23b4414068`
- `qa640_810s2_contract_e6a3bd898fef`
- `qa640_810s2_contract_dbce1f69f337`
- `qa640_810s2_contract_4b3a2160ef6e`
- `qa640_810s2_contract_87ba46f73216`
- `qa640_810s2_contract_7c4cc3d9e8a1`
- `qa640_810s2_contract_3ba0b8869e68`
- `qa640_810s2_contract_a9f862fffd17`
- `qa640_810s2_contract_3ac48b1c996c`
- `qa640_810s2_contract_ca2e8efc1c45`
- `qa640_810s2_contract_6d96b1752e4e`
- `qa640_810s2_contract_2c2668f84f04`
- `qa640_810s2_contract_f6b9a0a14630`
- `qa640_810s2_contract_d57a393dc520`
- `qa640_810s2_contract_f55e5322956b`
- `qa640_810s2_contract_66925c0f665f`
- `qa640_810s2_contract_39a74f1280cf`
- `qa640_810s2_contract_315347f56103`
- `qa640_810s2_contract_15eb9da015c0`
- `qa640_810s2_contract_8f3cdfc3c2d1`
- `qa640_810s2_contract_77194d76293a`
- `qa640_810s2_contract_257c5092a7d2`
- `qa640_810s2_contract_8fe3711510f9`
- `qa640_810s2_contract_dc05a138ef7a`
- `qa640_810s2_contract_45bf951e8972`

The manifest and captured fixture output record real database names rather than
collapsed audit prefixes.
The fixtures drop their clones in their `finally` blocks. No owner save or
template was written. No gateway was started, stopped or restarted. Audit gaps
remain the documented fixture subprocess template reads and the unaudited
ReplicationConnection class; no stronger coverage is claimed.

## Open Questions and Landing Notes

1. Authorize removing the three stale owner-literal exemption entries and
   updating the synthetic exemption-use test to exercise a remaining live
   exemption, or have the coordinator make that prerequisite change?
2. Resume this checkpoint after that scope decision to run the remaining offline,
   reachability and no-new-diagnostics gates, then rebase, push and open the PR?

No new migration number, fleet migration application, client bundle change or UI
rebuild. Migration 022's lazy ownership and migration 138's fixed ownership
remain. If this work later lands, the coordinator runs `nexus restart gateway`
by name and owns the whole-tree PostgreSQL gate. Do not merge this checkpoint.

Codex — GPT-6.

---

## Accepted Original Stop-Report (2026-10-01, Checkpoint 92d6fb70)

# STOP-REPORT: 810-S2

## False Premise and Required Disposition

Starting commit: `2e70e9cb2c566f6f48e70ea84874670a719055f9` on
`claude/810-embedding-table-ownership`. All commands ran from the assigned
worktree. Import verification printed
`/Users/pythagor/nexus/.claude/worktrees/810-embedding-table-ownership/nexus/__init__.py`.
The working rules, frozen order, issue snapshot, and live issue comments were read
in that order. No later live comment overrides 810-Q3.

STOP: the required `test_content_processor_propagates_ensure_failure` cannot
reach the embedding validator through the real writer on a current template
clone. After the required six `sql_text` aliases unblock SQL construction,
`store_narrative_chunk` inserts metadata naming five absent columns:
`perspective`, `location`, `time_code`, `keywords`, and `characters`.
It raises `sqlalchemy.exc.ProgrammingError` / `psycopg2.errors.UndefinedColumn`
for `perspective`, before calling `_generate_chunk_embeddings`.

This is an existing product/schema mismatch, not clone preparation failure.
The SQL appears unchanged at starting commit
`2e70e9cb:nexus/agents/memnon/utils/content_processor.py:337-340` and in the
checkpoint at `nexus/agents/memnon/utils/content_processor.py:337-340`.
The embedding call follows at line 362. The existing-row path also references
these columns at lines 296-302, before its embedding call at line 320.
The clone carries migration stamps through 140, including 022 and 138.

The order requires this writer proof to produce the validator's object-specific
`RuntimeError`, declares a different error a failure, and says to make no
unrelated edits to callers. Adding legacy columns to a test clone would conceal
the current production contract. Updating the metadata writer needs a revised
order; it has not been done.

## Partial Implementation, Not Ready to Land

- `nexus/agents/memnon/utils/db_access.py`: deleted constructor index builder and
  setup-only imports; extension-check database errors re-raise. #1059's search
  error propagation remains unchanged.
- `nexus/agents/memnon/utils/db_schema.py`: removed both setup paths; missing
  vector extension raises a migration-022-named connection error.
- `nexus/agents/memnon/utils/embedding_tables.py`: added catalog validation and
  full comments for all three lazy corpora, with caller-owned transactions.
- `nexus/agents/memnon/utils/content_processor.py`: changed six SQL constructors
  to `sql_text` and re-raised embedding-handler errors; legacy metadata SQL is
  preserved, and exposes the stop condition.
- `tests/test_memnon_db_access.py`: replaced deleted recording doubles with an
  offline AST removal proof.
- `tests/test_database_contract.py`: replaced only deleted setup-function probes
  with `verify_database_url`.
- `tests/test_memnon/test_source_embeddings.py`: converted five write-path cases
  to real clones; three currently fail due to fixture slug collisions.
- `tests/test_retrograde_summary_retrieval.py`: converted the 384d helper case to
  a real cursor and full catalog assertions.
- `tests/test_embedding_table_ownership_pg.py`: added adapter, catalog, comments,
  drift refusal, rollback, constructor and writer proofs; the writer proof fails.
- `docs/database.md`: updated the MEMNON ownership paragraph.
- `docs/qa/810-embedding-table-ownership/verification.md`: this stop-report.

The first proof run passed the nine corpus/adapter cases, three idempotence/ANN
cases, 27 malformed-object cases, three caller rollback cases, constructor
catalog invariance, and missing-extension refusal (44 ownership cases). The
malformed cases assert catalog and marker state on the same open transaction
before rollback and again after caller rollback. Their test assertions are at
`tests/test_embedding_table_ownership_pg.py:298-365`; full independent contract
assertions are at lines 150-222. These are partial proof results, not a completed
order or a claim that all implementation requirements are satisfied.

## Commands and Verbatim Tails

`PY` is `/Users/pythagor/nexus/.venv/bin/python`. `PYTHONPATH=$PWD` was set
explicitly on each test command. `NEXUS_RUN_LIVE_LLM` was not enabled.

Preflight, before edits:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_unowned_index_adoption_pg.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_810_adopt_drift_*, qa640_810_adopt_noop_*, qa640_810_adopt_recreate_*, qa640_810_no_create_all_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
5 passed in 6.76s
```

First partial proof run:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_embedding_table_ownership_pg.py tests/test_memnon_db_access.py tests/test_memnon/test_source_embeddings.py tests/test_retrograde_summary_retrieval.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 52 targets: postgres, qa640_810s2_contract_* x45, qa640_810s2_source_* x5, qa640_810s2_summary384_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_embedding_table_ownership_pg.py::test_content_processor_propagates_ensure_failure
FAILED tests/test_memnon/test_source_embeddings.py::test_experiences_load_and_stamp_only_valid_rendered_rows
FAILED tests/test_memnon/test_source_embeddings.py::test_stamp_shortfall_rolls_back_the_upserted_vectors
FAILED tests/test_memnon/test_source_embeddings.py::test_shared_helpers_serve_a_caller_supplied_embedder
4 failed, 60 passed in 81.91s (0:01:21)
```

Verbatim error excerpts:

```text
E       psycopg2.errors.UndefinedColumn: column "perspective" of relation "chunk_metadata" does not exist
E       LINE 3: ...                chunk_id, season, episode, scene, perspectiv...
E                                                                    ^
E       sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
E       LINE 3: ...                chunk_id, season, episode, scene, perspectiv...
E                                                                    ^
E
E       [SQL:
E                           INSERT INTO chunk_metadata (
E                               chunk_id, season, episode, scene, perspective, location, time_code, world_layer, keywords, characters
E                           ) VALUES (
E                               %(chunk_id)s, %(season)s, %(episode)s, %(scene)s, %(perspective)s, %(location)s, %(time_code)s, %(world_layer)s, %(keywords)s, %(characters)s
E                           )
E                           ]
E       [parameters: {'chunk_id': 1, 'season': 1, 'episode': 1, 'scene': 1, 'perspective': None, 'location': None, 'time_code': None, 'world_layer': 'primary', 'keywords': [], 'characters': []}]
E       (Background on this error at: https://sqlalche.me/e/20/f405)
E           psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "unique_slug"
E           DETAIL:  Key (slug)=(S01E01_001) already exists.
E           psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "unique_slug"
E           DETAIL:  Key (slug)=(S01E01_001) already exists.
E           psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "unique_slug"
E           DETAIL:  Key (slug)=(S01E01_001) already exists.
```

The three `UniqueViolation` failures are fixture preparation defects in the
newly converted tests: repeated `seed_committed_chunk`/`seed_story_clock` calls
use their default scene and collide on `S01E01_001`. They are separate from the
ContentProcessor product failure. They were not corrected after the false
premise triggered the stop rule. They are not treated as exempt baseline debt.

Formatting command:

```sh
/Users/pythagor/nexus/.venv/bin/python -m black nexus/agents/memnon/utils/db_access.py nexus/agents/memnon/utils/db_schema.py nexus/agents/memnon/utils/embedding_tables.py nexus/agents/memnon/utils/content_processor.py tests/test_memnon_db_access.py tests/test_database_contract.py tests/test_memnon/test_source_embeddings.py tests/test_retrograde_summary_retrieval.py tests/test_embedding_table_ownership_pg.py
```

```text
reformatted tests/test_memnon_db_access.py
reformatted nexus/agents/memnon/utils/embedding_tables.py
reformatted tests/test_embedding_table_ownership_pg.py
reformatted tests/test_memnon/test_source_embeddings.py

All done! ✨ 🍰 ✨
4 files reformatted, 5 files left unchanged.
```

Removal search:

```sh
rg -n 'setup_database_indexes|_setup_hybrid_search' nexus scripts ir_eval
```

No output; exit 1. `git diff --check` produced no output; exit 0.
The remaining ordered proof files, offline suites, reachability and static
comparison gates were not run after STOP; no success is claimed for them.
No static diagnostics were fixed or classified from an unrun gate.

## Disposable Schema Evidence

The diagnostic script in the assigned scratch directory creates only a
`qa640_810s2_stop_catalog_*` clone via `disposable_slot_database`, with its default
TEST story pin, reads the clone, and drops it in the fixture's `finally` block.
Its SQL includes:

```sql
SELECT version, name FROM schema_migrations ORDER BY version;
SELECT attname, format_type(atttypid, atttypmod), attnotnull
FROM pg_attribute
WHERE attrelid='public.chunk_metadata'::regclass
  AND attnum>0 AND NOT attisdropped ORDER BY attnum;
SELECT column_name FROM information_schema.columns
WHERE table_schema='public' AND table_name='chunk_metadata'
  AND column_name=ANY(ARRAY['perspective','location','time_code','keywords','characters']);
```

Exact command (final successful run, exit 0):

```sh
NEXUS_TEST_PROVIDER_ONLY=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/810-S2/catalog_probe.py
```

```text
DISPOSABLE CLONE: qa640_810s2_stop_catalog_937355a3e4dc
MIGRATION STAMPS: [('001', 'baseline'), ('002', 'add_choice_columns'), ('003', 'add_layer_zone_drafts'), ('004', 'fix_global_variables_fk'), ('005', 'add_incubator_choice_object'), ('006', 'add_save_slots_model'), ('007', 'normalize_new_story_creator'), ('009', 'remove_assets_save_slots'), ('010', 'add_traits_table'), ('011', 'add_traits_confirmed'), ('012', 'add_wizard_choice_object'), ('014', 'add_2560d_4096d_embeddings'), ('015', 'add_ir_eval_v2_tables'), ('016', 'add_ir_eval_v1_query_tables'), ('017', 'add_judgment_justification'), ('018', 'narrative_chunks_column_comments'), ('019', 'add_incubator_choice_text'), ('020', 'drop_chunk_embeddings_0384d'), ('021', 'dedup_embedded_state'), ('022', 'compound_embedding_pk_lazy_tables'), ('023', 'orrery_schema'), ('024', 'orrery_commit_pipeline'), ('025', 'orrery_package_library_vocab'), ('026', 'relationship_valence_magnitude'), ('027', 'orrery_package_library_round2_vocab'), ('028', 'orrery_sunhelm_needs'), ('029', 'orrery_need_state_init_trigger'), ('030', 'orrery_place_affordance_vocab'), ('031', 'orrery_slot2_semantic_tag_vocab'), ('032', 'orrery_interpersonal_needs'), ('033', 'orrery_travel_work'), ('034', 'orrery_concealment_surveillance_vocab'), ('035', 'orrery_osm_route_graph'), ('036', 'skald_inline_tag_runtime'), ('037', 'orrery_tag_category_registry'), ('038', 'orrery_tag_baseline_reconciliation'), ('039', 'new_story_character_orrery_tags'), ('040', 'storyteller_authorial_directives'), ('041', 'orrery_authority_model'), ('042', 'orrery_entity_pair_tags'), ('043', 'orrery_category_refactor_phase1'), ('044', 'disambiguate_status_reputation_traits'), ('045', 'trait_compiler_substrate'), ('046', 'canonical_grieving_state'), ('047', 'kind_qualified_contact_pair_tags'), ('048', 'orrery_hunting_pair_tag'), ('049', 'orrery_entity_tag_expiry_substrate'), ('050', 'orrery_state_clearance_event_types'), ('051', 'orrery_time_tag_clearance_kind'), ('052', 'orrery_faction_tag_vocab'), ('053', 'retire_faction_legacy_write_defaults'), ('054', 'orrery_completed_tag_vocab'), ('055', 'orrery_character_tag_vocab'), ('056', 'orrery_routine_anchors'), ('057', 'orrery_need_bodyform_applicability'), ('058', 'retire_faction_legacy_columns'), ('059', 'orrery_social_travel_event'), ('060', 'retrograde_persistence_sources'), ('061', 'trait_compiler_sponsors_pair_tag'), ('062', 'retrograde_maturation_jobs'), ('063', 'orrery_adjudication_history'), ('064', 'tag_provenance_forward_fix'), ('065', 'reconstructability'), ('066', 'signal_event_vocab'), ('067', 'rename_orrery_templates'), ('068', 'mundane_band_event_vocab'), ('069', 'ecology_event_vocab'), ('070', 'need_state_chunk_stamp'), ('071', 'retrograde_world_layer'), ('072', 'retrograde_layer_backfill'), ('073', 'rename_dream_to_atemporal'), ('074', 'plan_relocation_projects'), ('075', 'retrieval_coverage_log'), ('076', 'claims_awareness'), ('077', 'recruit_ally_projects'), ('078', 'retrograde_summary_storage'), ('079', 'need_state_chunk_provenance_comment'), ('080', 'epistemics_knowers'), ('081', 'faction_project_contexts'), ('082', 'generation_model_provenance'), ('083', 'claim_propagation_ledger'), ('084', 'build_venture_projects'), ('085', 'pursue_romance_projects'), ('086', 'court_patron_projects'), ('087', 'seek_redemption_projects'), ('088', 'valence_float_canonical'), ('089', 'relationship_drift_milestone'), ('090', 'claim_accounts'), ('091', 'backstory_secrets'), ('092', 'claim_distortion_depth'), ('093', 'claim_awareness_knower_index'), ('094', 'scene_weather_override'), ('095', 'mood_vocabulary'), ('096', 'polymorphic_patron'), ('097', 'trait_cold_start_relationship_constraints'), ('098', 'narrative_generation_lease'), ('099', 'storyteller_correspondence'), ('100', 'orrery_need_clock_anchor'), ('101', 'delete_project_start_summary_orphans'), ('102', 'narration_job_fencing'), ('103', 'bleed_uptake'), ('104', 'character_experiences'), ('105', 'interaction_threads'), ('106', 'recall_trace'), ('107', 'lore_pass_baselines'), ('108', 'strip_retired_observations_from_drafts'), ('109', 'extend_expiry_default_durations'), ('110', 'experience_formation_sweep'), ('111', 'experience_job_enqueue_gin_fence'), ('112', 'character_experience_recall_eligibility'), ('113', 'acquisition_formation_indexes'), ('114', 'slot_scoped_idf'), ('115', 'relationship_write_provenance'), ('116', 'acceptance_chunk_identity'), ('117', 'story_settings'), ('118', 'world_clock_identity'), ('120', 'deferred_work_owner'), ('121', 'generation_session_truth'), ('122', 'orrery_card_identity'), ('123', 'character_alias_provenance'), ('124', 'attempt_manifests'), ('125', 'embedding_summary_jobs'), ('126', 'seat_policies'), ('127', 'schema_documentation'), ('128', 'character_identity_rulings'), ('129', 'wizard_confirmation'), ('130', 'retire_psychology_endpoint_comments'), ('131', 'regeneration_lineage'), ('132', 'genesis_weird_level'), ('133', 'idf_rebuild_command'), ('134', 'drop_chunk_lifecycle_columns'), ('135', 'schema_docs_backfill'), ('136', 'column_comment_corrections'), ('137', 'view_comments'), ('138', 'adopt_unowned_fleet_indexes'), ('139', 'character_relationship_bigint_ids'), ('140', 'world_clock_primary_layer')]
CHUNK_METADATA COLUMNS: [('id', 'bigint', True), ('chunk_id', 'bigint', True), ('season', 'integer', False), ('episode', 'integer', False), ('scene', 'integer', False), ('world_layer', 'world_layer_type', False), ('time_delta', 'interval', False), ('generation_date', 'timestamp without time zone', False), ('slug', 'character varying(10)', False), ('world_time', 'timestamp with time zone', False), ('generation_model', 'text', False), ('scene_weather', 'text', False)]
LEGACY COLUMNS PRESENT: []
```

An initial diagnostic attempt also queried a nonexistent `story_settings`
table after successfully reading the above catalog evidence, raising
`UndefinedTable`. That diagnostic-query mistake was removed; the final probe
succeeded. It is not a product failure.

Per-clone full stamps were printed by the new ownership fixture, but pytest's
successful-case capture was not exported. The partial test log preserves
stamps for the failed ownership clone; it and the final independent probe
show the same migration list above. The audit records 45 ownership clones,
five source clones and one 384d summary clone. A complete per-clone evidence
manifest remains unfinished; no missing evidence is represented as collected.

Full logs remain under the assigned scratch directory: `preflight.log`,
`ownership-first.log`, `catalog-probe.log` (initial diagnostic failure), and
`catalog-probe-final.log`. No save or template was written, no gateway was
started or restarted, and no paid provider was called. Both pytest runs report
`owner targets: none`; fixture subprocess template reads are outside that audit,
as documented in `tests/pg_fixtures.py`.

No fresh corpus result or #964 disposition is claimed. The explicit ANN and
migration replay proof nodes still need their ordered runs.

## Open Questions for the Coordinator

1. Reissue 810-S2 to repair the ContentProcessor metadata writer against the
   current schema, or explicitly choose another real writer-failure proof?
2. After that scope decision, should the implementer resume this checkpoint,
   fix the three scene/slug seed defects, and complete all remaining gates?

No PR was opened, pushed or merged. The incomplete checkpoint is local only.
No new migration or fleet application was made. If the product work later
lands, the coordinator still restarts `nexus restart gateway` by name; no UI
bundle change is present.

Codex — GPT-6.

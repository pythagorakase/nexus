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

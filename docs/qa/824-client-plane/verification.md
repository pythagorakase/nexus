# 824-S1 and 824-S5 Verification: Client Plane Awareness and the Retired slot/select

Order: `temp/orders_2026_10_07/824-S1.md` (with the coordinator amendments of
2026-10-09 03:10 CDT and 2026-10-13 10:25 CDT). Issue: #824. Branch:
`claude/824-client-plane`, cut from `claude/wave-b-integration` at `7eb9a10c`
(merge base with `origin/main`: `f073b371`).

## Resumed on 2026-10-13

The first builder stopped at the usage limit on 2026-10-09 03:15 CDT after
three commits. `git log --stat claude/wave-b-integration..HEAD` at resume time
listed exactly these, with a clean tree and no evidence directory. Each commit
maps to the order's numbered items as follows; every item was re-read against
the diff (`git diff claude/wave-b-integration...HEAD`) before the proof ran.

| Commit | Subject | Order items |
|---|---|---|
| `6f3e5351` | Report the serving plane on /health and retire the no-op slot/select | 1 (`set_serving_plane`, `serving_plane`, `_build_projection`, docstring), 2 (`narrative.py` declaration and `health_check`), 4 (the `settings_endpoints.py` docstring line), 12 (route, schema, `activate_slot`, `all_slots` import, registry entry, baseline entry), Python tests (`test_health_reports_the_serving_plane`, `test_serving_plane_requires_a_declaration`, `test_retired_slot_select_is_not_served`, `OPERATOR_REQUESTS`, `test_slot_mutation_guard.py`) |
| `06075a47` | Drop LocationPhase's fetch of the retired slot/select route | 13 (`finalizeMutation`, `useMutation` and `Loader2` imports removed; button calls `onNext(locationData)`; props unchanged) |
| `b24d4b8a` | Shape the client by the plane that serves it | 3 (`usePlane.ts`), 4 (probe reads `/health`, caches the plane, `queryClient` dependency, Vite `/health` proxy), 5 (`usePreferencesQuery`, defaults gated on the operator plane, Theme and Font providers), 6 (TopBar meter, NexusLayout query, DeveloperMode gate, SettingsPane player console, CharactersPane upload, SlotSelector CLEAR), 7 (player plane starts only empty slots), 9 (design-sync and state-surface stubs, NOTES), 10 and 14 (`docs/runtime.md`), Vitest cases |

Items finished in this resume: 8 (no change needed, recorded below), 11 (no
new element was needed), 15 (freshness re-verification, below), the proof,
this evidence file and `pr-body.md`. No product code changed in the resume.

- Item 8: `useLocalModels.ts` and `narrative-api.ts` are unchanged. Their
  operator calls (`/api/local-models/*`, `/api/characters/{id}/images` upload
  and main) run only from components that the player plane no longer mounts
  (the memory meter, the settings pane's model and context-length sections,
  the portrait upload). The player browser transcript below records no
  operator request.
- Item 11: the order adds no UI element; it only withholds existing ones.
- Item 15: this branch changes `nexus/api/narrative.py` (a declared source of
  `AGENTS.md` and `docs/turn_flow_sequence.md`) and `useNarrativeEngine.ts` (a
  declared source of `docs/turn_flow_sequence.md`). Both documents were
  re-read. Neither names `/health`, the probe route, `slot/select` or
  `activate_slot`; `docs/turn_flow_sequence.md:62-63` ("The OFFLINE status
  reflects gateway reachability alone") stays true, because the probe still
  sets reachability from `res.ok` alone. Both already carry
  `verified_commit: "f073b3711a3bd0273943c9defad85913452fd00b"`, which is the
  merge base with `origin/main` (`git merge-base HEAD origin/main`), so the
  stamp does not move (the 2026-10-09 amendment says the same).
  Three canonical decision records also declare files this branch changes:
  `docs/decisions/0008-the-story-clock-in-chrome.md` (`TopBar.tsx`),
  `docs/decisions/0051-time-lens.md` and `docs/decisions/0054-responsive-shell.md`
  (`NexusLayout.tsx`). All three were re-read and stay true: the branch
  withholds the memory meter and gates two operator queries, and touches
  neither the top-bar story clock (0008), the time lens (0051) nor the narrow
  shell's bottom rail (0054). Each already carries `verified_commit`
  `f073b371` (the merge base), so no stamp moves.
  `tests/test_doc_front_matter.py` passes (below).

## Cited Lines, Verified on the Base (`claude/wave-b-integration` at `7eb9a10c`)

The order's line numbers came from an older `main`; these are the locations on
this branch's base, read with `git show claude/wave-b-integration:<path>`.

- `/health` answered `{"status": "healthy", "service": "narrative_api"}`:
  `nexus/api/narrative.py:823-826`. `require_classified(app)`: `:1752`.
  Imports of `activate_slot` `:55` and `SelectSlotRequest` `:336`.
- Probe `fetch("/api/settings", { method: "HEAD" })`:
  `ui/client/src/hooks/useNarrativeEngine.ts:404`; `CONNECTIVITY_POLL_MS`
  `:38`.
- Registry: `("HEAD", "/api/settings")` operator `route_capabilities.py:152`,
  `("GET", "/api/settings")` operator `:153`, `("GET", "/api/preferences")`
  player `:155`, `setup/reset` operator `:186`, `slot/select` operator `:190`,
  character image upload, main and delete operator `:220-224`; the module
  docstring paragraph ends at `:22`.
- `useSettingsQuery` read defaults ungated: `ui/client/src/hooks/useSettings.ts:10-11`.
  `ThemeProvider` read it at `ThemeContext.tsx:41-43`; `FontProvider` at
  `FontContext.tsx:61-65`.
- Operator requests on any plane: the memory meter's `/api/settings`
  (`TopBar.tsx:198-200`, rendered at `:300`); NexusLayout's `/api/settings`
  (`NexusLayout.tsx:69`); the backstage gate (`DeveloperModeContext.tsx:22-25`);
  the settings pane's story settings (`SettingsPane.tsx:774`) and secrets
  (`:465`).
- Operator-backed controls on any plane: `ModelSection`, `KeysSection`,
  `ContextLengthSection` (`SettingsPane.tsx:869-875`); portrait upload and
  set-main (`CharactersPane.tsx:68-80`, button at `:169`); CLEAR
  (`SlotSelector.tsx:87`, `:254`); the overwrite dialog (`handleSelect`
  `:118`, `overwrite-confirm` `:344`).
- `POST /api/story/new/slot/select`: `nexus/api/setup_endpoints.py:218-229`,
  imports `:24`, `:35`; `activate_slot` at `nexus/api/new_story_flow.py:1033`
  (the only use of `all_slots`, imported at `:36`); its two callees are no-ops
  (`nexus/api/save_slots.py:236-247` `clear_active`, `:287-310` `upsert_slot`
  ignores `is_active`); `SelectSlotRequest` at `narrative_schemas.py:277`; the
  only client was `LocationPhase.tsx:49-52`; design-sync exports it at
  `ui/.design-sync/nexus-ui.ts:15`; baseline entry
  `config/exception_disposition_baseline.json:121`.
- Vite proxied `/api` and `/ws` only (`ui/vite.config.ts:121-122`).
- `HEAD /api/settings` docstring: `nexus/api/settings_endpoints.py:107`.
- 503 page without a build: `nexus/api/static_ui.py:98`, `:112`.
- `docs/runtime.md:155` (Operator row), `:183` (the "Before the tunnel moves"
  sentence), `:737` (Development Workflows proxy list).
- State-surface fixture probe stub: `ui/scripts/state-surfaces/fixture.tsx:27`;
  `vite.config.ts` in the input closure: `ui/scripts/state-surfaces/inputs.mjs:37`.

No cited defect had disappeared on the integration base, so no item was
skipped.

## Red Runs (Product Hunks Reverted, No `git stash`)

Product files were checked out from the base with
`git checkout claude/wave-b-integration -- <files>`, the test ran, and the
files were restored with `git checkout HEAD -- <files>` (status clean
afterwards).

Python (`nexus/api/narrative.py`, `route_capabilities.py`, `new_story_flow.py`,
`setup_endpoints.py`, `narrative_schemas.py`, `settings_endpoints.py`
reverted):

```
$ PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider tests/test_api/test_route_capabilities.py::test_health_reports_the_serving_plane
E       AssertionError: assert {'service': '...s': 'healthy'} == {'plane': 'pl...s': 'healthy'}
E         Right contains 1 more item:
E         {'plane': 'player'}
FAILED tests/test_api/test_route_capabilities.py::test_health_reports_the_serving_plane[dist-missing]
FAILED tests/test_api/test_route_capabilities.py::test_health_reports_the_serving_plane[dist-built]
2 failed, 7 warnings in 0.75s
```

Vitest (`ThemeContext.tsx`, `FontContext.tsx`, `useSettings.ts` reverted):

The verbatim tail of `red-ui.log` (from the "Failed Tests" banner to the end;
ANSI colour codes stripped, nothing else removed): the assertion expected
`theme-gilded` on `<html>` and received only `dark`.

```
$ (cd ui && npx vitest run client/src/contexts/PreferenceProviders.test.tsx)
⎯⎯⎯⎯⎯⎯⎯ Failed Tests 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/contexts/PreferenceProviders.test.tsx > preference providers > applies saved theme and fonts from preferences alone
Error: expect(element).toHaveClass("theme-gilded")

Expected the element to have class:
  theme-gilded
Received:
  dark

Ignored nodes: comments, script, style
<html
  class="dark"
  style="--font-narrative: Spectral; --font-display: Megrim; --font-sans: Spectral; --font-serif: Spectral; --font-mono: Cinzel;"
>
  <head>
    <link
      href="/icons/veil/icon-32.png?v=20260612b"
      rel="icon"
      sizes="32x32"
      type="image/png"
    />
    <link
      href="/icons/veil/icon-16.png?v=20260612b"
      rel="icon"
      sizes="16x16"
      type="image/png"
    />
    <link
      href="/icons/veil/icon-180.png?v=20260612b"
      rel="apple-touch-icon"
      type="image/png"
    />
  </head>
  <body>
    <div>
      <span />
    </div>
  </body>
</html>
 ❯ src/contexts/PreferenceProviders.test.tsx:56:38
     54| 
     55|     const root = document.documentElement;
     56|     await waitFor(() => expect(root).toHaveClass("theme-gilded"));
       |                                      ^
     57|     await waitFor(() =>
     58|       expect(root.style.getPropertyValue("--font-narrative")).toBe("Sp…
 ❯ runWithExpensiveErrorDiagnosticsDisabled ../node_modules/@testing-library/dom/dist/config.js:47:12
 ❯ checkCallback ../node_modules/@testing-library/dom/dist/wait-for.js:124:77
 ❯ Timeout.checkRealTimersCallback ../node_modules/@testing-library/dom/dist/wait-for.js:118:16

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  1 failed (1)
   Start at  10:51:14
   Duration  1.91s (transform 41ms, setup 64ms, collect 101ms, tests 1.02s, environment 375ms, prepare 216ms)
```

Both pass on the branch (Python in the PostgreSQL proof set below; Vitest in
the full UI run).

## PostgreSQL Proof Set

`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. `uptime` before
the run: load averages `22.43 27.14 22.73` (one-minute below 24; the bounded
wait loop returned at once).

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_api/test_route_capabilities.py tests/test_api/test_slot_mutation_guard.py tests/test_api/test_cors.py tests/test_api/test_wizard_resume.py tests/test_api/test_slot_settings.py tests/test_new_story_setup.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 40 targets: nexus_m10_fresh_test_9444, nexus_m10_template_test_9444, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_816_lifecycle_test_provider, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_885_ren_replay_* x4, qa640_offline_gate_* x20, test_slot_guard_4739d591f2c04b529b5262a9fc9d8d9c
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:54563 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:54565 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:54563 (psycopg2), save_04@local:54565 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
156 passed, 2 skipped, 7 warnings in 129.21s (0:02:09)
```

The two skips are `tests/test_orrery/test_card_identity.py:122-125`
(`requires_corpus`, parametrized over `asynchronous`), which runs only under
`NEXUS_RUN_CORPUS=1`.

## Offline Suites

`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` and `NEXUS_RUN_POSTGRES`
unset. The order's first command (`tests --ignore=tests/test_api
--ignore=tests/test_orrery`) ran in three sequential pieces, because one
piece alone runs past the ten-minute command limit under this machine's load
(the one-minute load reached 39): the subdirectories, then the top-level
modules in two alphabetical halves. pytest's default `python_files`
(`test_*.py` and `*_test.py`; `pytest.ini` sets only `testpaths = tests`)
also collects the two top-level `*_test.py` modules
`tests/live_seed_schema_test.py` and `tests/live_set_designer_test.py`. The
first second-half run listed only `tests/test_*.py` and missed them; the
second half was re-run with both added (review round 3, below the first
run's tail), so the three pieces now cover the same files as the order's
command. Both modules skip at module level offline (`283 skipped` against
`281`).

The halves are the 144 files of `ls tests/test_*.py` split 78 + 66
(`ls tests/test_*.py | head -78` and `| tail -66` reproduce both lists
exactly at this head). First half:

```
tests/test_backfill_review_packet.py tests/test_bootstrap_episode_pg.py tests/test_character_identity.py tests/test_character_name_reveals_pg.py tests/test_character_name_reveals.py tests/test_character_relationship_id_types_pg.py tests/test_character_tag_manifest.py tests/test_chunk_entity_references_pg.py tests/test_chunk_lifecycle_columns_migration_pg.py tests/test_cli_choice_http.py tests/test_cli_contract.py tests/test_cli_generation_http.py tests/test_cli_inspect_pg.py tests/test_cli_model_selection.py tests/test_cli_reference_doc.py tests/test_cli_review_pg.py tests/test_cli_session_wait.py tests/test_cli_wizard_confirmation.py tests/test_cli.py tests/test_clock_face.py tests/test_commit_choice_presence_pg.py tests/test_commit_chronology.py tests/test_commit_handler_sync.py tests/test_connection_lifecycle.py tests/test_correspondence_live.py tests/test_correspondence.py tests/test_database_contract.py tests/test_db_converters.py tests/test_dbname_audit.py tests/test_doc_front_matter.py tests/test_embedding_artifacts.py tests/test_embedding_table_ownership_pg.py tests/test_entity_reference_parity_pg.py tests/test_entity_tag_manifest_apply.py tests/test_enum_column_comment_labels_pg.py tests/test_faction_table_audit.py tests/test_gis_scripts_live.py tests/test_golden_path_live.py tests/test_idf_dictionary_pg.py tests/test_inherited_slot_isolation_pg.py tests/test_intention_revision_weight.py tests/test_interaction_boundary.py tests/test_interactions_pg.py tests/test_issue_601_wizard_live.py tests/test_jobs_cli_pg.py tests/test_live_gate_clones_pg.py tests/test_local_skald_live.py tests/test_logon_mock_integration.py tests/test_lore_adapter_metadata.py tests/test_measure_place_scale_grammar_pg.py tests/test_measure_place_scale_grammar.py tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder_dependencies.py tests/test_memnon_cross_encoder.py tests/test_memnon_db_access.py tests/test_memnon_embedding_cache.py tests/test_memnon_embedding_contract.py tests/test_memnon_model_failures_pg.py tests/test_memnon_runtime_config.py tests/test_memnon_script_model_loaders.py tests/test_migration_comment_lint.py tests/test_mock_openai.py tests/test_model_artifact_lock_committed.py tests/test_model_drift.py tests/test_model_registry_live.py tests/test_name_reveal_staged_bindings_pg.py tests/test_name_reveal_staged_bindings.py tests/test_name_reveal_tag_validation_pg.py tests/test_name_reveal_tag_validation.py tests/test_native_structured_output.py tests/test_new_story_cache.py tests/test_new_story_cli.py tests/test_new_story_integration.py tests/test_new_story_schemas.py tests/test_new_story_setup_config.py tests/test_new_story_setup.py tests/test_openai_registry_capabilities.py tests/test_orrery_tag_validation_pg.py
```

Second half (plus the two `*_test.py` modules in the re-run):

```
tests/test_orrery_tag_validation.py tests/test_owner_target_guard.py tests/test_pg_accepted_turn_factory.py tests/test_pg_adjudication_ledger_seed.py tests/test_pg_anchor_pair_tag_seeds.py tests/test_pg_character_pair_seed.py tests/test_pg_disposable_target.py tests/test_pg_experience_seeds.py tests/test_pg_fixtures_corpus_clone.py tests/test_pg_legacy_faction_tag_seed.py tests/test_pg_target_contract.py tests/test_place_tag_manifest.py tests/test_player_identity_consumers_pg.py tests/test_postgres_tools.py tests/test_presence_audit.py tests/test_presence_boost_pg.py tests/test_presence_boost.py tests/test_presence_reconciliation.py tests/test_presence_roster_pg.py tests/test_presence_roster.py tests/test_prompt_lint.py tests/test_prompt_tag_vocabulary_pg.py tests/test_prose_metrics_pg.py tests/test_prose_metrics.py tests/test_qa_shift.py tests/test_reachability.py tests/test_rebuild_memory_idf_pg.py tests/test_record_revelation_cli_pg.py tests/test_reentry_wire_ledger.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_register_drift_study.py tests/test_relationship_entity_ids_pg.py tests/test_retrograde_summary_retrieval.py tests/test_routine_delta_grammar_probe_pg.py tests/test_runtime_home.py tests/test_scheduler_helpers_basetemp.py tests/test_scheduler_helpers_routing.py tests/test_schema_docs_baseline_routing.py tests/test_schema_documentation_pg.py tests/test_schema_ownership.py tests/test_script_wrappers.py tests/test_secret_manager.py tests/test_secret_store_guard.py tests/test_secret_store_integration.py tests/test_skald_wire.py tests/test_slot_operations_journal.py tests/test_slot_operations_pg.py tests/test_slot_routed_entrypoints.py tests/test_slot_utils.py tests/test_story_identity_pg.py tests/test_summary_triggers.py tests/test_tags_audit_pg.py tests/test_test_provider_seeder.py tests/test_trait_compiler_integration.py tests/test_trait_compiler.py tests/test_trait_input_derivation.py tests/test_trait_menu_docs.py tests/test_travel_reachability_pg.py tests/test_travel_reachability.py tests/test_turn_observation.py tests/test_unowned_index_adoption_pg.py tests/test_usage_recorder.py tests/test_wizard_agent.py tests/test_wizard_live.py tests/test_wizard_opening_presence_pg.py tests/test_world_clock_contract_pg.py
```

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/config tests/fixtures tests/proofs tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
2 failed, 1043 passed, 89 skipped, 7 warnings in 161.26s (0:02:41)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider $(ls tests/test_*.py | head -78)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1088 passed, 299 skipped, 8 warnings in 404.98s (0:06:44)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider $(ls tests/test_*.py | tail -66)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
3 failed, 1061 passed, 281 skipped, 7 warnings in 100.07s (0:01:40)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider $(ls tests/test_*.py | tail -66) tests/live_seed_schema_test.py tests/live_set_designer_test.py   # re-run on a239f55a
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
3 failed, 1061 passed, 283 skipped, 7 warnings in 97.87s (0:01:37)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
2 failed, 544 passed, 330 skipped, 7 warnings in 34.47s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts
FAILED tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
9 failed, 1349 passed, 1187 skipped, 7 warnings in 14.07s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 19.57s
```

### Failures in Files This Branch Does Not Change (Pre-Existing on the Base)

Every one of the 16 failures above is in a file this branch does not touch,
and each fails the same way on the base. The base check ran each failing test
id from a `git archive claude/wave-b-integration` export in the scratchpad
(`PYTHONPATH=<export>`, import path proven under the export):

- `test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged`:
  the Gaia request digest is `e0f4920a…` against the recorded `cac3d730…`.
  Base: `1 failed, 2 passed` (same test).
- `test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained`:
  `assert 732 < 700` (Gaia prompt word count). Base: `1 failed`.
- `test_skald_wire.py::test_wire_schema_size_and_description_budget`: the
  undeclared description `NewEntityDeclaration.coordinates` (840-S2's authored
  coordinates). Base: same assertion.
- `test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp`
  and `test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[*]`:
  "Unit test attempted psycopg2.connect; mark it requires_postgres". Base:
  same message, same three ids.
- `tests/test_orrery/test_worker.py` (8 ids): `Settings` validation error
  "orrery.projects.milestone_magnitude must be >= orrery.promote.magnitude_threshold";
  `tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy`:
  the error message no longer matches the test's regex. Base: `9 failed`.
- `test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module`:
  flags `tests/test_orrery/test_place_point_required_pg.py:11` and one
  `…lan_pg.py:23` binding. The test scans tracked files under `scripts/` and
  `tests/` with `git ls-files`, so it cannot run in an archive export; this
  branch changes only `tests/test_api/test_route_capabilities.py` and
  `tests/test_api/test_slot_mutation_guard.py` under those roots, so the
  flagged files are the base's.

Not fixed, not skipped: the coordinator triages them.

## UI

```
$ nice -n 15 npm --prefix ui run check
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
(exit 0)

$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
 ❯ src/state-shades.test.ts:183:9
    183|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
 Test Files  1 failed | 41 passed (42)
      Tests  639 passed (639)

$ nice -n 15 npm --prefix ui run build
PWA v1.0.3
mode      generateSW
precache  22 entries (2322.81 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
(exit 0)

$ (cd ui && nice -n 15 node .design-sync/build.mjs)
✓ 4423 modules transformed.
.design-sync/.cache/lib-dist/style.css  1,632.18 kB │ gzip: 983.79 kB
.design-sync/.cache/lib-dist/index.js   3,445.65 kB │ gzip: 853.50 kB
✓ built in 3.97s
[build] dist/index.js + style.css + declarations ready (brand font urls rewritten)
(exit 0)

$ git status --porcelain ui/.design-sync
(empty: nothing uncommitted)
$ git diff --name-only claude/wave-b-integration...HEAD -- ui/.design-sync
ui/.design-sync/NOTES.md
ui/.design-sync/ds-provider.tsx
```

The design-sync build needs the converter dependencies in the gitignored
`ui/.ds-sync/`; they were installed there with `npm ci` from a copy of the
main checkout's `ui/.ds-sync/package.json` and `package-lock.json` (read
only; nothing in the main checkout changed, nothing symlinked).

The one Vitest failure is `src/state-shades.test.ts`, "Stale browser-resolved
state surfaces", the expected stale receipt on this base (coordinator
amendment, point 4). Every one of the 639 tests passes, including the seven
named in the order: `PreferenceProviders.test.tsx` (applies saved theme and
fonts from preferences alone), `SettingsPane.test.tsx` (player plane shows
only theme, typography and app icon), `TopBar.test.tsx` (player plane renders
no memory meter), `CharactersPane.test.tsx` (player plane offers no portrait
upload), `SlotSelector.test.tsx` (player plane offers no clear and no
overwrite), `NexusLayout.test.tsx` (player plane sends no operator request),
`useNarrativeEngine.recovery.test.tsx` (probe reads /health and caches the
plane).

## State Surfaces

Not regenerated, by the coordinator amendment (point 4): the coordinator
regenerates once on the final UI union. This branch's edits sit in the input
closure (the IRIS shell modules, `ui/vite.config.ts` via `inputs.mjs:37`, and
`fixture.tsx`). Which measured surfaces could move: none is intended. The
player plane is not measured (the fixture answers `/health` with the operator
plane and seeds it), every operator control still renders under the fixture's
seeds, and `ui/scripts/state-surfaces/fixture.tsx` now also seeds
`['/api/preferences']` with `{ theme, fonts: KEEPERS, wizard_model }`, which
equals the fonts the old `/api/settings` seed already gave the providers. The
regeneration owed at land time should therefore reproduce identical
measurements; any moved sample is a finding.

## Static Checks

Changed Python files: `nexus/api/narrative.py`, `narrative_schemas.py`,
`new_story_flow.py`, `route_capabilities.py`, `settings_endpoints.py`,
`setup_endpoints.py`, `tests/test_api/test_route_capabilities.py`,
`tests/test_api/test_slot_mutation_guard.py`.

- Black: `All done! 8 files would be left unchanged.`
- flake8 (`--config .flake8`): head 54 diagnostics, base 57 (base versions
  from `git show claude/wave-b-integration:<path>`). Line-number-stripped
  diff: head removes `F401 SelectSlotRequest`, `F401 activate_slot` and the
  `new_story_flow.py` `E501 (94 > 88)` inside the deleted `activate_slot`; the
  `F811 slot_dbname` entry moves from line 58 to 57. No new diagnostic.
- mypy (`--explicit-package-bases`, base run in a `git archive` export of the
  base so imports resolve to the base tree): diagnostics in the changed files,
  head 9, base 10. Head drops `new_story_flow.py: Incompatible return value
  type (got "dict[int, str]", expected "dict[str, str]")` (the deleted
  `activate_slot`). No new diagnostic.
- Pre-existing diagnostics on untouched lines (both trees):
  `narrative_schemas.py` union-attr on `narrative_generation`;
  `narrative.py` implicit Optional default and untyped `frontmatter`;
  four `setup_endpoints.py` `ResumeSetupResponse` arg-types and untyped
  `frontmatter`; `test_slot_mutation_guard.py:147` assignment type.

```
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref claude/wave-b-integration
OK: exception disposition coverage and shrink-only baseline verified.
```

The baseline shrinks by exactly the `nexus/api/new_story_flow.py|activate_slot|2414808e…|1`
entry (the handler was deleted with its function).

## Browser Proof

Scratch directory: `<scratchpad>/824-S1-resume/824-S1/` (session scratchpad
`ac1789b0-…`). Files: `serve.py <player|operator> <port>` (imports
`nexus.api.narrative`, builds one projection, `uvicorn.run` on 127.0.0.1),
`nexus.toml` (the worktree's copy with `[runtime].state_dir` set to the
absolute `<scratch>/824-S1/state`), `dump_operator_templates.py` (operator
keys of `ROUTE_CAPABILITIES`; 43 at the cut point, 42 at the final tree, the
difference being `slot/select`), and `browser_proof.mjs` (Playwright 1.63 from
the worktree's `ui/node_modules`, Chromium 1243, one fresh context per run,
records every same-origin request and response; operator templates match by
method plus path with `{param}` as `[^/]+`).

Server environment, identical for every run: `PYTHONPATH=<worktree>`,
`NEXUS_RUNTIME_CONFIG=<scratch>/824-S1/nexus.toml`, `NEXUS_KEYRING_DISABLE=1`;
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` and `NEXUS_HOME` unset.
Two additions for safety, beyond the order's list: `NEXUS_TEST_PROVIDER_ONLY=1`
(no paid provider can be reached; the lifespan then skips the model-artifact
boot check) and `PGOPTIONS='-c default_transaction_read_only=on'` (every
libpq session is read-only, so the player pages' slot reads could not write
to any `save_NN`; a write would have surfaced as a 500). `lsof` showed no
listener on 8023 or 8024 before each start; only the processes started here
were stopped, by PID; both ports were free afterwards. The preferences file
written by the theme click is `<scratch>/824-S1/state/preferences.toml`
(removed before each player run); the owner's `preferences.toml` was never
touched.

### Red Run at the Cut Point (`7eb9a10c`), Player on 8023

The worktree was checked out detached at `7eb9a10c` (clean tree), then
`npm --prefix ui ci && npm --prefix ui run build` (both exit 0), and the
cut-point `serve.py player 8023` answered `{"status":"healthy","service":"narrative_api"}`.
After the run the server was stopped by PID (18894) and the branch checked
out again. Transcript:

```
[step] visit /
[step] visit /nexus?tab=settings
[step] visit /new-story
[step] visit /nexus?tab=settings and click theme-gilded
[step] theme-gilded not rendered
[step] PATCH /api/preferences status: null
[step] removed nexus-theme from localStorage; reload /nexus?tab=settings

== requests (method path?query) ==
GET /
GET /assets/index-C5o0njTX.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /fonts/Megrim-Regular.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /api/settings
GET /api/preferences
GET /api/dev/backstage/health
GET /nexus?tab=settings
GET /assets/index-C5o0njTX.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /api/settings
GET /api/local-models/status
GET /api/config/ui
GET /api/preferences
HEAD /api/settings
GET /api/dev/backstage/health
GET /fonts/Megrim-Regular.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /fonts/Spectral-Italic.ttf
GET /new-story
GET /assets/index-C5o0njTX.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /assets/index-C5o0njTX.js
GET /fonts/Megrim-Regular.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /fonts/Spectral-Italic.ttf
GET /api/story/new/slots
GET /api/settings
GET /api/preferences
GET /api/dev/backstage/health
GET /nexus?tab=settings
GET /assets/index-C5o0njTX.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /fonts/Megrim-Regular.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /fonts/Spectral-Italic.ttf
GET /api/settings
GET /api/local-models/status
GET /api/config/ui
GET /api/preferences
HEAD /api/settings
GET /api/dev/backstage/health
GET /nexus?tab=settings
GET /assets/index-C5o0njTX.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /assets/index-C5o0njTX.js
GET /fonts/Megrim-Regular.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /fonts/Spectral-Italic.ttf
GET /api/settings
GET /api/local-models/status
GET /api/config/ui
GET /api/preferences
HEAD /api/settings
GET /api/dev/backstage/health

== /api and /health responses ==
404 GET /api/settings
404 GET /api/dev/backstage/health
200 GET /api/preferences
404 GET /api/settings
404 GET /api/local-models/status
404 GET /api/dev/backstage/health
200 GET /api/config/ui
404 HEAD /api/settings
200 GET /api/preferences
200 GET /api/story/new/slots
404 GET /api/settings
404 GET /api/dev/backstage/health
200 GET /api/preferences
404 GET /api/settings
404 GET /api/dev/backstage/health
404 GET /api/local-models/status
200 GET /api/config/ui
404 HEAD /api/settings
200 GET /api/preferences
404 GET /api/local-models/status
404 GET /api/dev/backstage/health
404 GET /api/settings
200 GET /api/config/ui
404 HEAD /api/settings
200 GET /api/preferences

== assertions ==
patch_preferences_200: false
html_has_theme_gilded: false
preferences_toml_theme_gilded: false
no_operator_request: false
api_and_health_below_400: false
_html_class: "dark"
_preferences_toml: null
_operator_hits: [{"method":"GET","path":"/api/settings","search":""},{"method":"GET","path":"/api/dev/backstage/health","search":""},{"method":"GET","path":"/api/settings","search":""},{"method":"GET","path":"/api/local-models/status","search":""},{"method":"HEAD","path":"/api/settings","search":""},{"method":"GET","path":"/api/dev/backstage/health","search":""},{"method":"GET","path":"/api/settings","search":""},{"method":"GET","path":"/api/dev/backstage/health","search":""},{"method":"GET","path":"/api/settings","search":""},{"method":"GET","path":"/api/local-models/status","search":""},{"method":"HEAD","path":"/api/settings","search":""},{"method":"GET","path":"/api/dev/backstage/health","search":""},{"method":"GET","path":"/api/settings","search":""},{"method":"GET","path":"/api/local-models/status","search":""},{"method":"HEAD","path":"/api/settings","search":""},{"method":"GET","path":"/api/dev/backstage/health","search":""}]
_bad_responses: [{"method":"GET","path":"/api/settings","status":404},{"method":"GET","path":"/api/dev/backstage/health","status":404},{"method":"GET","path":"/api/settings","status":404},{"method":"GET","path":"/api/local-models/status","status":404},{"method":"GET","path":"/api/dev/backstage/health","status":404},{"method":"HEAD","path":"/api/settings","status":404},{"method":"GET","path":"/api/settings","status":404},{"method":"GET","path":"/api/dev/backstage/health","status":404},{"method":"GET","path":"/api/settings","status":404},{"method":"GET","path":"/api/dev/backstage/health","status":404},{"method":"GET","path":"/api/local-models/status","status":404},{"method":"HEAD","path":"/api/settings","status":404},{"method":"GET","path":"/api/local-models/status","status":404},{"method":"GET","path":"/api/dev/backstage/health","status":404},{"method":"GET","path":"/api/settings","status":404},{"method":"HEAD","path":"/api/settings","status":404}]

RESULT: FAIL
```

The settings pane never left its loading state (its `/api/settings` read
answered 404), so `theme-gilded` never rendered, and every page sent operator
requests that the player projection refused.

### Green Run at the Final Tree, Player on 8023

`npm --prefix ui ci && npm --prefix ui run build` at the branch head (exit 0),
then both projections started from the final tree: `GET /health` answered
`{"status":"healthy","service":"narrative_api","plane":"player"}` on 8023 and
`{…,"plane":"operator"}` on 8024 (PIDs 19361 and 19362).

```
[step] visit /
[step] visit /nexus?tab=settings
[step] visit /new-story
[step] visit /nexus?tab=settings and click theme-gilded
[step] PATCH /api/preferences status: 200
[step] removed nexus-theme from localStorage; reload /nexus?tab=settings

== requests (method path?query) ==
GET /
GET /assets/index-BMsxOmuy.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /fonts/Megrim-Regular.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /api/preferences
GET /health
GET /nexus?tab=settings
GET /assets/index-BMsxOmuy.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /api/config/ui
GET /health
GET /api/preferences
GET /health
GET /icons/veil/icon-192.png?v=20260612b
GET /icons/gilded/icon-192.png?v=20260612b
GET /icons/vector/icon-192.png?v=20260612b
GET /fonts/Megrim-Regular.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /fonts/Monoton-Regular.ttf
GET /fonts/SpaceMono-Regular.ttf
GET /fonts/CormorantGaramond-VariableFont_wght.ttf
GET /fonts/Sixtyfour-Variable.ttf
GET /fonts/SourceCodePro-VariableFont_wght.ttf
GET /fonts/Rajdhani-Regular.ttf
GET /new-story
GET /assets/index-BMsxOmuy.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /assets/index-BMsxOmuy.js
GET /fonts/Megrim-Regular.ttf
GET /fonts/Monoton-Regular.ttf
GET /fonts/Sixtyfour-Variable.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/SpaceMono-Regular.ttf
GET /fonts/SourceCodePro-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /fonts/CormorantGaramond-VariableFont_wght.ttf
GET /fonts/Rajdhani-Regular.ttf
GET /health
GET /api/story/new/slots
GET /api/preferences
GET /nexus?tab=settings
GET /assets/index-BMsxOmuy.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /fonts/Megrim-Regular.ttf
GET /fonts/Monoton-Regular.ttf
GET /fonts/Sixtyfour-Variable.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/SpaceMono-Regular.ttf
GET /fonts/SourceCodePro-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /fonts/CormorantGaramond-VariableFont_wght.ttf
GET /fonts/Rajdhani-Regular.ttf
GET /api/config/ui
GET /health
GET /api/preferences
GET /health
GET /icons/veil/icon-192.png?v=20260612b
GET /icons/gilded/icon-192.png?v=20260612b
GET /icons/vector/icon-192.png?v=20260612b
PATCH /api/preferences
GET /fonts/SpaceMono-Bold.ttf
GET /nexus?tab=settings
GET /assets/index-BMsxOmuy.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /assets/index-BMsxOmuy.js
GET /fonts/Megrim-Regular.ttf
GET /fonts/Monoton-Regular.ttf
GET /fonts/Sixtyfour-Variable.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/SpaceMono-Regular.ttf
GET /fonts/SpaceMono-Bold.ttf
GET /fonts/SourceCodePro-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /fonts/CormorantGaramond-VariableFont_wght.ttf
GET /fonts/Rajdhani-Regular.ttf
GET /api/config/ui
GET /health
GET /api/preferences
GET /health
GET /icons/veil/icon-192.png?v=20260612b
GET /icons/gilded/icon-192.png?v=20260612b
GET /icons/vector/icon-192.png?v=20260612b

== /api and /health responses ==
200 GET /health
200 GET /api/preferences
200 GET /health
200 GET /health
200 GET /api/config/ui
200 GET /api/preferences
200 GET /api/story/new/slots
200 GET /health
200 GET /api/preferences
200 GET /health
200 GET /health
200 GET /api/config/ui
200 GET /api/preferences
200 PATCH /api/preferences
200 GET /health
200 GET /health
200 GET /api/config/ui
200 GET /api/preferences

== assertions ==
patch_preferences_200: true
html_has_theme_gilded: true
preferences_toml_theme_gilded: true
no_operator_request: true
api_and_health_below_400: true
_html_class: "dark theme-gilded"
_preferences_toml: "theme = \"gilded\"\nwizard_model = \"gpt-6-astra\"\n\n[fonts.veil]\nbody = \"Spectral\"\nmenu = \"Cinzel\"\ndisplay = \"Megrim\"\n\n[fonts.gilded]\nbody = \"Cormorant Garamond\"\nmenu = \"Space Mono\"\ndisplay = \"Monoton\"\n\n[fonts.vector]\nbody = \"Rajdhani\"\nmenu = \"Source Code Pro\"\ndisplay = \"Sixtyfour\"\n"
_operator_hits: []
_bad_responses: []

RESULT: PASS
```

### Green Run at the Final Tree, Operator on 8024

```
[step] visit /nexus?tab=settings

== requests (method path?query) ==
GET /nexus?tab=settings
GET /assets/index-BMsxOmuy.js
GET /assets/index-B-UNXzR1.css
GET /registerSW.js
GET /api/config/ui
GET /health
GET /api/preferences
GET /health
GET /fonts/Megrim-Regular.ttf
GET /fonts/Cinzel-VariableFont_wght.ttf
GET /fonts/Spectral-Regular.ttf
GET /api/settings
GET /api/local-models/status
GET /api/dev/backstage/health
GET /api/secrets/status
GET /icons/veil/icon-192.png?v=20260612b
GET /icons/gilded/icon-192.png?v=20260612b
GET /icons/vector/icon-192.png?v=20260612b
GET /fonts/Monoton-Regular.ttf
GET /fonts/SpaceMono-Regular.ttf
GET /fonts/CormorantGaramond-VariableFont_wght.ttf
GET /fonts/Sixtyfour-Variable.ttf
GET /fonts/SourceCodePro-VariableFont_wght.ttf
GET /fonts/Rajdhani-Regular.ttf
GET /fonts/SpaceMono-Bold.ttf

== /api and /health responses ==
200 GET /health
200 GET /health
200 GET /api/settings
200 GET /api/config/ui
200 GET /api/preferences
404 GET /api/dev/backstage/health
200 GET /api/secrets/status
200 GET /api/local-models/status

== assertions ==
set_keys_renders: true
get_api_settings_requested: true
get_local_models_status_requested: true
_bad_responses: [{"method":"GET","path":"/api/dev/backstage/health","status":404}]

RESULT: PASS
```

`GET /api/dev/backstage/health` answers 404 on the operator projection because
the dev dashboard is committed disabled (`[orrery.dashboard] enabled = false`),
so the Backstage router is not registered; the client reads 404 as a closed
gate (`DeveloperModeContext.tsx`), as before this branch.

## Review Fixes (2026-10-13)

Applied in `2a97d5fa` (test stubs) and the evidence commit that adds this
section. No product code changed.

- `NexusLayout.announcer.test.tsx` and `NarrativePane.regenerate.test.tsx`
  mount the real engine but still answered the retired `HEAD /api/settings`
  probe, so the `/health` probe failed and only a later slot read restored
  reachability. Both stubs now answer `GET /health` with
  `{ status: "healthy", service: "narrative_api", plane: "operator" }`
  (the order's rule: stubs that answered `HEAD /api/settings` answer
  `GET /health` with a JSON body). The optional "never OFFLINE" assertion was
  not added.
- `useNarrativeEngine.recovery.test.tsx` `mount()` seeded the retired
  `["/api/settings"]` theme source; it now seeds `["/api/preferences"]` with
  `{ theme: "veil", fonts: KEEPERS, wizard_model: "TEST" }`, the key
  `ThemeProvider` reads (the first alternative the finding offered).
- Evidence: "the eight named in the order" is now "the seven"; Item 15 and
  the PR body name the three decision records (0008, 0051, 0054) re-read for
  freshness.

Tails, run on `2a97d5fa`:

```
$ nice -n 15 npx --prefix ui vitest run --root ui client/src/hooks/useNarrativeEngine.recovery.test.tsx client/src/components/nexus/NexusLayout.announcer.test.tsx client/src/components/nexus/NarrativePane.regenerate.test.tsx
 ✓ client/src/hooks/useNarrativeEngine.recovery.test.tsx (14 tests) 266ms
 ✓ client/src/components/nexus/NarrativePane.regenerate.test.tsx (10 tests) 314ms
 ✓ client/src/components/nexus/NexusLayout.announcer.test.tsx (3 tests) 271ms

 Test Files  3 passed (3)
      Tests  27 passed (27)

$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 41 passed (42)
      Tests  639 passed (639)

$ nice -n 15 npm --prefix ui run check
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
(exit 0)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 7.33s

$ $PY -m black --check <the 8 changed Python files>
All done! ✨ 🍰 ✨
8 files would be left unchanged.
```

The only Vitest failure is still the expected stale state-surface receipt.

## Review Fixes, Round 3 (2026-10-13)

Applied in `67ab65f7` (UI suites and `SlotSelector.tsx`), `a239f55a` (the
`/health` plane test) and the evidence commit that adds this section. Every
tail below ran on the tree committed as `a239f55a`.

- Retired theme seeds. `ThemeProvider` reads its theme only from
  `usePreferencesQuery()` (`ThemeContext.tsx:42`). Eight suites still seeded
  `["/api/settings"]` with `{ ui: { theme: "veil" } }`:
  `NarrativePane.test.tsx`, `NarrativePane.drafts.test.tsx`,
  `NarrativePane.regenerate.test.tsx`, `ReturnRecapCard.test.tsx`,
  `Intertitle.test.tsx`, `NexusLayout.announcer.test.tsx`,
  `InteractiveWizard.transition.test.tsx` and `WaitScreen.test.tsx`. Each now
  seeds `["/api/preferences"]` with
  `{ theme: "veil", fonts: KEEPERS, wizard_model: "TEST" }` (`KEEPERS` from
  `@/contexts/FontContext`), as `2a97d5fa` did for the recovery suite; the
  wizard and wait-screen suites' second, settings-shaped `/api/preferences`
  seed folded into that one line. `StateGlyphs.test.tsx:35` takes the same
  `Preferences` shape and keeps its `["/api/settings"]` seed (`:34`), which
  carries the MemoryMeter's `ui.local_models` knobs on the operator plane.
  `NexusLayout.announcer.test.tsx` keeps an `["/api/settings"]` seed, now
  `{}`: its probe stub reports the operator plane, so NexusLayout's
  operator read of the backstage knobs (`NexusLayout.tsx:68-71`) is enabled
  and this client has no query function. No other suite of the eight mounts
  an `/api/settings` reader (only `TopBar.tsx`, `SettingsPane.tsx`,
  `NexusLayout.tsx` and `useSettings.ts` read it).
- Player-plane occupied slot card. On the player plane an occupied unlocked
  card now adds `cursor-default hover:border-primary/30` through `cn`
  (`tailwind-merge` drops the base `cursor-pointer` and the lit
  `hover:border-primary/60`), so it no longer looks clickable; RESUME stays
  its only action. The operator plane and the design-sync card (stubbed to
  the operator plane) are unchanged. The `player plane offers no clear and no
  overwrite` case asserts the occupied card has `cursor-default` and not
  `cursor-pointer`, and the empty card keeps `cursor-pointer`. This is the
  finding's example taken as written; `tabIndex` and the Enter/Space handler
  stay, so keyboard focus order does not change.
- `/health` plane test. `test_health_reports_the_serving_plane` now builds
  the player and operator projections before it sends any request, then
  requests `/health` from the player, operator and unprojected apps in that
  order. A shared-plane implementation therefore answers every request with
  the last declaration. Proof with a pytest plugin that replaces
  `set_serving_plane` and `serving_plane` with one module global
  (`<scratchpad>/824-S1-resume/fix3/shared_plane.py`, loaded with
  `-p shared_plane`): the restructured test fails on the player case, and
  the previous structure (`git show HEAD~1:tests/test_api/test_route_capabilities.py`
  copied in for one run, then restored) passed under the same plugin.
- Evidence: the offline split now names the two `*_test.py` modules, the
  half commands are the real shell forms with both file lists pasted, and
  the Vitest red run above is the verbatim tail of `red-ui.log`.

```
$ PYTHONPATH=$PWD:<scratch>/fix3 nice -n 15 $PY -m pytest -q -p no:cacheprovider -p shared_plane tests/test_api/test_route_capabilities.py::test_health_reports_the_serving_plane
E       AssertionError: assert {'plane': 'op...s': 'healthy'} == {'plane': 'pl...s': 'healthy'}
E         
E         Omitting 2 identical items, use -vv to show
E         Differing items:
E         {'plane': 'operator'} != {'plane': 'player'}
E         Use -v to get more diff

tests/test_api/test_route_capabilities.py:234: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_api/test_route_capabilities.py::test_health_reports_the_serving_plane[dist-missing]
FAILED tests/test_api/test_route_capabilities.py::test_health_reports_the_serving_plane[dist-built]
2 failed in 0.14s

$ # same command, previous test structure (HEAD before a239f55a) copied in for one run
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
2 passed in 0.05s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api/test_route_capabilities.py::test_health_reports_the_serving_plane tests/test_api/test_route_capabilities.py::test_serving_plane_requires_a_declaration
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3 passed, 7 warnings in 0.67s

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_api/test_route_capabilities.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_offline_gate_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
37 passed, 7 warnings in 5.86s

$ $PY -m black --check tests/test_api/test_route_capabilities.py
All done! ✨ 🍰 ✨
1 file would be left unchanged.

$ nice -n 15 npx --prefix ui vitest run --root ui <the nine suites above> client/src/components/NewStoryWizard/SlotSelector.test.tsx
 ✓ client/src/components/nexus/Intertitle.test.tsx (4 tests) 23ms
 ✓ client/src/components/NewStoryWizard/WaitScreen.test.tsx (12 tests) 86ms
 ✓ client/src/components/nexus/NarrativePane.test.tsx (3 tests) 63ms
 ✓ client/src/components/NewStoryWizard/SlotSelector.test.tsx (15 tests) 300ms
 ✓ client/src/components/nexus/ReturnRecapCard.test.tsx (16 tests) 293ms
 ✓ client/src/components/nexus/NarrativePane.regenerate.test.tsx (10 tests) 378ms
 ✓ client/src/components/nexus/NarrativePane.drafts.test.tsx (36 tests) 408ms
 ✓ client/src/components/nexus/NexusLayout.announcer.test.tsx (3 tests) 271ms
 ✓ client/src/components/nexus/StateGlyphs.test.tsx (6 tests) 432ms
 ✓ client/src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx (50 tests) 4952ms

 Test Files  10 passed (10)
      Tests  155 passed (155)

$ nice -n 15 npm --prefix ui run check
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
(exit 0)

$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 41 passed (42)
      Tests  639 passed (639)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 6.91s
```

The only Vitest failure is still the expected stale state-surface receipt.

## Landing Notes for the Coordinator

- No migration; no fleet application.
- A gateway restart is owed when the services run again (`narrative.py`,
  `route_capabilities.py`, `settings_endpoints.py`, `setup_endpoints.py`,
  `new_story_flow.py`, `narrative_schemas.py` change).
- A UI rebuild (`npm --prefix ui run build`) is owed, together with the
  gateway restart or after it, never while an older gateway runs: an old
  gateway's `/health` has no `plane`, so the new bundle would hide every
  operator control and keep the settings pane on RECEIVING.
- State surfaces: regenerate once on the final UI union (not done here).
- Design-sync: no card should change; `LocationPhase` stays exported and
  `config.json`, `nexus-ui.ts` and `previews/` are byte-identical.

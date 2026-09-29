# Orrery Tests Own Their Data: Verification

Work order 885/816-A. Issues #885 (the `seed_disposable_clone` route) and #816 (shared factories, Sketch 1). Base: `origin/main` at 626b2293. No migration, no gateway lane, no paid calls. Every database written here was a disposable `qa640_*` template clone created and dropped by `tests.pg_fixtures.disposable_slot_database`; no `save_NN` or `NEXUS_template` was written.

## What Changed

- `tests/pg_fixtures.py`: new shared seeds `seed_story_clock`, `seed_character`, `seed_place`, `seed_faction`, `seed_relationship`, `seed_entity_tag`. `seed_committed_chunk` takes `time_delta`; `seed_protagonist` takes `current_location` and closes its connection. Each seed takes the production insert shape, asserts its own row count, and returns IDs.
- `tests/test_orrery/checkpointed_story_support.py`: `seed_checkpointed_story` composes those seeds into a three-character, two-place story with two relationships, one active tag, a clocked head chunk, and a genesis checkpoint.
- Need-clock files (`test_communication_graph_live`, `test_claim_accounts_live`, `test_claim_consumption_live`, `test_orbit_distance_live`, `test_migrate::test_canonical_grieving_migration_executes_against_slot_db`): module-scoped clones with `seed_story_clock`; every slot-5 URL, engine, and asyncpg target points at the clone.
- Unpack files (`test_replay`, `test_reconstruction`, `test_status_bestow_delta_live`): module-scoped clones; every probe asserts its row and names the seed that owns it; `_fabricate_chunk` takes its ID from the sequence.

## Before: The Eight Files on Main

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q --tb=line \
    tests/test_orrery/test_communication_graph_live.py tests/test_orrery/test_claim_accounts_live.py \
    tests/test_orrery/test_claim_consumption_live.py tests/test_orrery/test_orbit_distance_live.py \
    tests/test_orrery/test_migrate.py tests/test_orrery/test_replay.py \
    tests/test_orrery/test_reconstruction.py tests/test_orrery/test_status_bestow_delta_live.py
43 failed, 80 passed, 11 errors in 2.76s
```

## After: Each Changed File in Isolation

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_communication_graph_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
9 passed in 2.00s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_claim_accounts_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
6 passed in 1.70s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_claim_consumption_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
8 passed in 1.96s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_orbit_distance_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed in 1.52s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_migrate.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
77 passed in 1.71s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_replay.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
25 passed in 3.19s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_reconstruction.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
5 passed in 2.73s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_status_bestow_delta_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
3 passed in 1.98s
```

## After: Full Orrery PostgreSQL Tier

Run in two batches (68 files `test_[a-o]*`, 65 files `test_[p-z]*`), gateway variables unset.

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q --tb=line tests/test_orrery/test_[a-o]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
FAILED tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True]
FAILED tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[False]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings
4 failed, 792 passed, 29 skipped, 8 errors in 160.36s (0:02:40)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q --tb=line tests/test_orrery/test_[p-z]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_reveal_live.py::test_authoring_rejects_non_private_and_unregistered_gate
FAILED tests/test_orrery/test_reveal_live.py::test_authoring_grants_unpossessed_holder_and_reveal_completes
FAILED tests/test_orrery/test_reveal_live.py::test_async_authoring_grants_unpossessed_holder
FAILED tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop
FAILED tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate
FAILED tests/test_orrery/test_reveal_live.py::test_unregistered_gate_in_latent_row_raises_loudly
FAILED tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[retrograde-settings0]
FAILED tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[primary-settings1]
FAILED tests/test_orrery/test_reveal_live.py::test_authored_and_revealed_secrets_replay_between_checkpoints
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_packet_and_transition_keep_event_without_adversarial_rows
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_compiler_gate_suppresses_all_named_target_materialization
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_persistence_identity_binds_database_alias_without_packet_alias
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction
10 failed, 807 passed, 10 skipped, 5 errors in 111.87s (0:01:51)
```

The need-clock class (`need-clock anchor unavailable`) and the unpack class (`cannot unpack non-iterable NoneType object`) are gone: neither signature appears in either batch. The #1013 IDF class (`IDF analyzer mismatch`) appears zero times. Every remaining failure is in a file this PR does not change:

| Nodes | Signature | Class |
| --- | --- | --- |
| `test_reveal_live.py` (9) | `TypeError: 'NoneType' object is not subscriptable` at line 184 (`SELECT id FROM places` on save_05) | #885 empty slot 5, already named in #885 |
| `test_faction_project_contexts_live.py` (8 errors) | `NoResultFound` in the slot-5 fixture | #885, already named |
| `test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end` | `save_05 is expected to bind off-screen actors` | #885, already named |
| `test_tag_library.py::test_contextual_library_save_05_completeness_and_size` | `save_05 must contain current entity tags` | #885, already named |
| `test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle` (error) | `NoResultFound` in `patron_circle_db` on slot 5 | #885, already named |
| `test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots` | no audited slot has adjudication-log rows | #885; #964 routes it as an intentional corpus-bound probe |
| `test_retrograde_constraints_pg.py` (4 errors) | `DuplicateColumn: column "provenance" of relation "character_aliases"` in `disposable_dbname` | fixture repair left for the next #816 slice |
| `test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True/False]` | `ValidationError: 4 validation errors for RenderLimits` (`nexus/agents/lore/utils/turn_cycle.py:1152`; the test's settings dict has no `render_limits`) | new to the gate (the IDF class hid it), not slot-5; fails identically on a `git archive` of `origin/main` |

## Offline Gate, Reachability, and Linters

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES $PY -m pytest -q --tb=line
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
1 failed, 4078 passed, 1054 skipped in 283.93s (0:04:43)
$ $PY -m pytest -q tests/test_pg_target_contract.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
145 passed, 1 skipped in 13.22s
```

The one offline failure (`assert 711 < 700`, the Gaia prompt word budget) fails identically on a `git archive` of `origin/main`; it follows #1011's prompt change, not this PR.

Black: all ten changed files unchanged. Flake8: one E501 at `tests/test_orrery/test_replay.py:1039`, a JSON literal inside SQL that is unchanged from main. Mypy on the ten changed modules: 25 errors, all on lines unchanged from main (20 `dict | None` indexes in `test_replay.py`, the `driver_connection` and `OrrerySettings | None` unions in the three claim and communication files); main has 28 in the same files, and the three in `test_migrate.py` and `test_status_bestow_delta_live.py` are gone.

## Retired #885 IDs (54)

All 54 failed or errored on main before this PR, pass after it, and are named in #885's canonical list.

- `tests/test_orrery/test_claim_accounts_live.py::test_latent_sibling_secret_stays_private_until_its_own_gate_fires`
- `tests/test_orrery/test_claim_accounts_live.py::test_old_divergent_sibling_scopes_raise_during_hydration`
- `tests/test_orrery/test_claim_accounts_live.py::test_scope_promotion_updates_every_sibling_and_hydrates_cleanly`
- `tests/test_orrery/test_claim_accounts_live.py::test_sibling_accounts_hydrate_predicates_and_propagate_independently`
- `tests/test_orrery/test_claim_accounts_live.py::test_sync_variant_rejects_cross_incident_lineage_parent`
- `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_common_claims_are_bounded_to_their_about_entities`
- `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_joins_distorted_delivery_to_real_depth`
- `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_renders_two_hop_provenance_and_ledger_depth`
- `tests/test_orrery/test_claim_consumption_live.py::test_historical_anchor_excludes_future_claim_and_awareness`
- `tests/test_orrery/test_claim_consumption_live.py::test_hydration_excludes_irrelevant_history_and_empty_universe_issues_no_sql`
- `tests/test_orrery/test_claim_consumption_live.py::test_live_predicates_cover_participant_told_common_false_and_faction`
- `tests/test_orrery/test_claim_consumption_live.py::test_recent_claim_scope_survives_inactive_endpoints`
- `tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity`
- `tests/test_orrery/test_communication_graph_live.py::test_assembly_is_deterministic_and_unknown_configured_channel_is_loud`
- `tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum`
- `tests/test_orrery/test_communication_graph_live.py::test_conflicted_live_pair_licenses_only_each_tellers_own_direction`
- `tests/test_orrery/test_communication_graph_live.py::test_culture_profiles_multiply_and_record_provenance`
- `tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge`
- `tests/test_orrery/test_communication_graph_live.py::test_lone_row_is_sparse_and_handler_override_beats_neutral`
- `tests/test_orrery/test_communication_graph_live.py::test_production_explain_and_entity_audit_share_one_edge_list`
- `tests/test_orrery/test_communication_graph_live.py::test_unknown_dyad_override_key_is_loud`
- `tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db`
- `tests/test_orrery/test_orbit_distance_live.py::test_hydrate_orbit_distance_from_active_relationship_graph`
- `tests/test_orrery/test_reconstruction.py::test_checkpoint_captures_every_section_and_is_idempotent`
- `tests/test_orrery/test_reconstruction.py::test_relationship_triggers_version_updates_and_deletes`
- `tests/test_orrery/test_reconstruction.py::test_skald_state_updates_are_ledgered`
- `tests/test_orrery/test_reconstruction.py::test_unattributed_relationship_write_versions_with_null_chunk`
- `tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape`
- `tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored`
- `tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier`
- `tests/test_orrery/test_replay.py::test_pair_tag_bestowal_and_clearance_replay`
- `tests/test_orrery/test_replay.py::test_post_fix_null_world_time_uses_primary_clock_exactly`
- `tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder`
- `tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning`
- `tests/test_orrery/test_replay.py::test_project_complete_hands_off_and_real_travel_applier_relocates`
- `tests/test_orrery/test_replay.py::test_project_replay_rejects_ledger_without_applied_projection`
- `tests/test_orrery/test_replay.py::test_project_transition_window_replays_with_zero_checkpoint_drift`
- `tests/test_orrery/test_replay.py::test_reconstruction_refuses_pre_instrumentation_chunks`
- `tests/test_orrery/test_replay.py::test_relationship_multi_version_unwind_order`
- `tests/test_orrery/test_replay.py::test_relationship_unwind_restores_updates_deletes_and_drops_inserts`
- `tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift`
- `tests/test_orrery/test_replay.py::test_scalar_replay_round_trip_and_within_chunk_ordering`
- `tests/test_orrery/test_replay.py::test_tag_applicability_before_fulfillment_preserves_marker`
- `tests/test_orrery/test_replay.py::test_tag_bestowal_and_clearance_replay_at_exact_chunks`
- `tests/test_orrery/test_replay.py::test_travel_replay_start_advance_arrive`
- `tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible`
- `tests/test_orrery/test_replay.py::test_verify_catches_unledgered_entity_deactivation`
- `tests/test_orrery/test_replay.py::test_verify_catches_unledgered_scalar_drift`
- `tests/test_orrery/test_replay.py::test_verify_catches_unlogged_tag_clear`
- `tests/test_orrery/test_replay.py::test_verify_skips_legacy_checkpoint_without_entity_activity`
- `tests/test_orrery/test_replay.py::test_window_born_character_fulfillment_preserves_applicability_marker`
- `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly`
- `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways`
- `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance`

## Slot-5 Reference Audit

`grep -rn "slot=5\|save_05\|LIVE_SLOT\|WRITE_SLOT" tests/test_orrery/`: 259 lines before, 236 after.

### Changed Files, Before

```
tests/test_orrery/test_claim_accounts_live.py:38:    LIVE_SLOT,
tests/test_orrery/test_claim_accounts_live.py:103:    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
tests/test_orrery/test_claim_accounts_live.py:571:    conn = await asyncpg.connect(**asyncpg_kwargs(f"save_{LIVE_SLOT:02d}"))
tests/test_orrery/test_replay.py:3:Real writers, real triggers, real ledgers against save_05 inside
tests/test_orrery/test_replay.py:61:WRITE_SLOT = 5
tests/test_orrery/test_replay.py:65:    database = os.environ.get("NEXUS_REPLAY_TEST_DB", f"save_{WRITE_SLOT:02d}")
tests/test_orrery/test_replay.py:66:    assert database == f"save_{WRITE_SLOT:02d}" or database.startswith("qa640_")
tests/test_orrery/test_replay.py:195:    """Create the pilot table only inside this rolled-back save_05 transaction."""
tests/test_orrery/test_replay.py:1143:            assert earliest is not None, "save_05 must carry a genesis checkpoint"
tests/test_orrery/test_orbit_distance_live.py:23:LIVE_SLOT = 5
tests/test_orrery/test_orbit_distance_live.py:104:    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT), future=True)
tests/test_orrery/test_migrate.py:92:        migrate.migrate_database("save_05")
tests/test_orrery/test_migrate.py:116:        "NEXUS_template, save_01, save_02. Not attempted: save_04, save_05."
tests/test_orrery/test_migrate.py:1638:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1640:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1715:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1717:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1804:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1806:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1854:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1856:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1929:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1931:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1972:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1974:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:2089:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:2091:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_claim_consumption_live.py:39:    LIVE_SLOT,
tests/test_orrery/test_claim_consumption_live.py:58:    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
tests/test_orrery/test_communication_graph_live.py:29:LIVE_SLOT = 5
tests/test_orrery/test_communication_graph_live.py:164:    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT), future=True)
tests/test_orrery/test_communication_graph_live.py:379:        pytest.skip("save_05 does not contain the frozen Tomi/Kosi pair")
tests/test_orrery/test_reconstruction.py:3:Real writers and real triggers against save_05 inside always-rolled-back
tests/test_orrery/test_reconstruction.py:38:WRITE_SLOT = 5
tests/test_orrery/test_reconstruction.py:42:    conn = connect(f"save_{WRITE_SLOT:02d}")
tests/test_orrery/test_reconstruction.py:75:            assert active_tags > 0, "save_05 must carry active tags"
tests/test_orrery/test_status_bestow_delta_live.py:29:    conn = psycopg2.connect(get_slot_db_url(slot=5))
```

### Changed Files, After

```
tests/test_orrery/test_migrate.py:95:        migrate.migrate_database("save_05")
tests/test_orrery/test_migrate.py:119:        "NEXUS_template, save_01, save_02. Not attempted: save_04, save_05."
tests/test_orrery/test_migrate.py:1641:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1643:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1718:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1720:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1807:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1809:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1857:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1859:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1932:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1934:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
tests/test_orrery/test_migrate.py:1975:        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
tests/test_orrery/test_migrate.py:1977:        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")
```

Why these stay:

- `test_migrate.py:95` and `:119` name `save_05` as a string only: the first proves `migrate_database` refuses an invalid migration tree before touching any database (every database call is monkeypatched to fail), the second is the expected `--all` log line. Neither connects.
- `test_migrate.py:1641-1977`: six sibling migration re-run tests (`test_character_tag_vocab_…`, `test_completed_tag_vocab_…`, `test_entity_tag_expiry_substrate_…`, `test_faction_tag_vocab_…`, `test_state_clearance_event_type_…`, `test_kind_qualified_contact_…`). They pass on the empty save_05, are not in either failure class, and are outside this order; they still roll back and restore vocabulary rows on the owner slot, so they are candidates for the next #816 slice.

### Unchanged Files (Counts Before and After)

| File | Before | After |
| --- | ---: | ---: |
| `tests/test_orrery/test_adjudication_history.py` | 7 | 7 |
| `tests/test_orrery/test_claim_accounts_live.py` | 3 | 0 |
| `tests/test_orrery/test_claim_consumption_live.py` | 2 | 0 |
| `tests/test_orrery/test_claim_propagation_live.py` | 4 | 4 |
| `tests/test_orrery/test_communication_graph_live.py` | 3 | 0 |
| `tests/test_orrery/test_composition_sources_live.py` | 4 | 4 |
| `tests/test_orrery/test_distortion_live.py` | 2 | 2 |
| `tests/test_orrery/test_ecology_live.py` | 4 | 4 |
| `tests/test_orrery/test_embedding_audit.py` | 4 | 4 |
| `tests/test_orrery/test_events.py` | 40 | 40 |
| `tests/test_orrery/test_evidence.py` | 3 | 3 |
| `tests/test_orrery/test_faction_project_contexts_live.py` | 3 | 3 |
| `tests/test_orrery/test_generation_model_provenance_live.py` | 3 | 3 |
| `tests/test_orrery/test_geo_resolver_live.py` | 1 | 1 |
| `tests/test_orrery/test_knowledge_surfacing_live.py` | 2 | 2 |
| `tests/test_orrery/test_live_cycle.py` | 6 | 6 |
| `tests/test_orrery/test_migrate.py` | 16 | 14 |
| `tests/test_orrery/test_mood_migration_pg.py` | 1 | 1 |
| `tests/test_orrery/test_orbit_distance_live.py` | 2 | 0 |
| `tests/test_orrery/test_pair_tag_predicates.py` | 4 | 4 |
| `tests/test_orrery/test_pair_tag_substrate.py` | 2 | 2 |
| `tests/test_orrery/test_polymorphic_patron_live.py` | 1 | 1 |
| `tests/test_orrery/test_polymorphic_patron_migration_pg.py` | 1 | 1 |
| `tests/test_orrery/test_reconstruction.py` | 4 | 0 |
| `tests/test_orrery/test_replay.py` | 6 | 0 |
| `tests/test_orrery/test_retrograde_graph.py` | 1 | 1 |
| `tests/test_orrery/test_retrograde_orchestrator.py` | 8 | 8 |
| `tests/test_orrery/test_retrograde_packet.py` | 18 | 18 |
| `tests/test_orrery/test_retrograde_persistence.py` | 38 | 38 |
| `tests/test_orrery/test_retrograde_vocabulary.py` | 1 | 1 |
| `tests/test_orrery/test_reveal_live.py` | 1 | 1 |
| `tests/test_orrery/test_signal_events.py` | 5 | 5 |
| `tests/test_orrery/test_stage2a_status_live.py` | 15 | 15 |
| `tests/test_orrery/test_status_bestow_delta_live.py` | 1 | 0 |
| `tests/test_orrery/test_tag_library.py` | 27 | 27 |
| `tests/test_orrery/test_tag_provenance.py` | 4 | 4 |
| `tests/test_orrery/test_weather_migration_pg.py` | 1 | 1 |
| `tests/test_orrery/test_worker.py` | 11 | 11 |

The unchanged files are outside this order. The ones hardwired to an empty save_05 (`test_reveal_live`, `test_faction_project_contexts_live`, `test_evidence`, `test_tag_library`, `test_polymorphic_patron_live`, and, live-LLM gated so they skip in this gate, `test_composition_sources_live`, `test_stage2a_status_live`, `test_claim_propagation_live`) remain #885 work for a later slice. `test_adjudication_history`, `test_ecology_live`, `test_live_cycle`, `test_signal_events`, and `test_tag_provenance` read save_02 through `WRITE_SLOT`/`LIVE_SLOT` names. `test_events`, `test_retrograde_*`, `test_worker`, and `test_embedding_audit` pass `slot=5` or `dbname="save_05"` as labels into offline or rolled-back calls.

## Deferred

- The accepted-turn factory through `commit_incubator_to_database_sync` (no ported test needed it).
- The owner-`save_04` `include_data` trio: `test_attempt_manifest_pg`, `test_scheduler_corpus_pg`, `test_seat_policy_jobs_pg`.
- The `test_retrograde_constraints_pg` fixture repair.

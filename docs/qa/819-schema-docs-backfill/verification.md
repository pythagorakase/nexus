# Schema Documentation Backfill Verification

## Scope

Work order 819-C, branch `claude/819-schema-docs-backfill`, migration **135**
(comment-only). No application server or paid provider was started. No
migration was applied to `NEXUS_template` or any `save_NN`; the coordinator
applies 135 fleet-wide at landing. Catalog reads against `NEXUS_template` and
`save_01..save_05` were read-only and showed every commented object present,
with the same function identity arguments, at schema version 134.

## Method

`tests.pg_fixtures.disposable_slot_database("qa640_819_verify")` cloned
`NEXUS_template` into a disposable database and migrated it with
`scripts.migrate` (log: `Applied: 135_schema_docs_backfill`, `Applied 1
migrations to qa640_819_verify_bf63e72dd8c5`). A read-only session then read
`obj_description(oid, 'pg_type')` for each enum and
`obj_description(oid, 'pg_proc')` for each function named by a `COMMENT ON` in
the migration, asserting exactly one catalog object per name and matching
identity arguments. The fixture dropped the clone afterward.

The PostgreSQL ratchet (`tests/test_schema_documentation_pg.py`) migrates its
own clone the same way. A negative probe that restored one retired entry
(`enum:public.tone`) failed with `Retire documented or removed baseline
entries: ['enum:public.tone']`, which shows the ratchet sees migration 135.

## Catalog Listing on the Migrated Clone

Clone `qa640_819_verify_bf63e72dd8c5`; `schema_migrations` maximum version after migrating: **135**.

| enum | obj_description(oid, 'pg_type') |
|---|---|
| `character_experience_basis` | How a character holds an experience: participant or witness from the event-role receipts that seed_character_experiences_sync turns into seeds, acquisition from a claim the character was told or granted. Rendering reads it to choose the permitted names: claim sources for acquisition, the scene setting places otherwise. |
| `character_experience_invalidation_status` | Replay validity of a character experience. supersede_world_event_sync sets invalidated only on seeds that are not yet rendered; seed_character_experiences_sync treats only valid rows as already representing an event. |
| `character_need_type` | Need clocks that Orrery accrues against world time (needs.effective_debt_score, tuned in [orrery.sunhelm]). orrery_need_applies_to_tags and needs.need_applies_to_tags drop a need for bodyform or mind tags that exempt it. |
| `entity_kind` | Subtype of a row in entities. orrery_ensure_subtype_entity_kind creates or checks the entities row for each characters, factions, or places insert, and the tag writer reads tag_category_registry by this kind to allow tag categories. |
| `entity_tag_clearance_kind` | How an ephemeral tag clears: event when a matching event type fires (events._clear_event_tags_sync), time when expires_at_world_time passes (events._sweep_expired_entity_tags_sync), semantic only by an explicit clear. authored appears only in tag_clearance_log.mechanism, for clears by template state deltas and clear_entity_tag. |
| `entity_tag_reapplication_policy` | What the tag writer does when a tag is applied while it is still active: new_row (the default) keeps the active row, replace overwrites its timing and provenance, extend_expiry pushes its expiry out by the duration (semantic and event tags land without expiry). |
| `entity_tag_source_kind` | Provenance of a tag row: skald_inline for runtime bestowals (storyteller, wizard, trait compiler), template for Orrery template effects, retrograde for Retrograde history, system for the entity tag manifest apply, authored and llm_generated for offline or CLI backfills. The Orrery tag writer rejects auto_registered. |
| `event_role_kind` | Role of an entity in a world event. The event writers record actor and target; epistemics.PARTICIPANT_ROLES (actor, target, beneficiary) make a character a participant and WITNESS_ROLES (observer, witness) a witness when experiences and claims are seeded. |
| `event_severity_kind` | Registered weight of an event type, seeded with the event vocabulary. Knowledge surfacing maps it through the configured severity_scores into candidate scoring, and the cognition audit reports it. |
| `event_source_kind` | Writer family of a world event: resolver for Orrery resolver-side writers (resolutions, propagation, relationship provenance, reveals), authored for authored backstory secrets, retrograde for Retrograde history, which Retrograde persistence and replay select by this value. No current writer uses apex, narrator, or bleed. |
| `faction_member_role` | Position of a character in a faction, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py) and exposed as entity_relationships_v.relationship_type with scope faction_character. The Orrery membership loader counts every row as membership whatever its role. |
| `faction_relationship_type` | Relationship between two factions, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py) and exposed as entity_relationships_v.relationship_type with scope faction. Current Orrery readers of that view select only character scope. |
| `genre` | Genre vocabulary of the new-story wizard. write_cache casts the setting draft into assets.new_story_creator.setting_genre and setting_secondary_genres, and _row_to_cache reads them back; a non-null setting_genre marks the setting phase complete. |
| `geographic_scope` | Geographic reach vocabulary of the new-story wizard setting draft; write_cache stores it in assets.new_story_creator.setting_geographic_scope and _row_to_cache reads it back. |
| `tech_level` | Technology level vocabulary of the new-story wizard setting draft; write_cache stores it in assets.new_story_creator.setting_tech_level and _row_to_cache reads it back. |
| `tone` | Tone vocabulary of the new-story wizard setting draft; write_cache stores it in assets.new_story_creator.setting_tone and _row_to_cache reads it back. |
| `seed_type` | Opening-situation vocabulary of the new-story wizard seed draft; write_cache stores the selected seed in assets.new_story_creator.seed_type, and its presence is part of the seed phase completion check. |
| `layer_type` | Kind of world layer in the new-story wizard: a planet or a separate dimension. Stored in assets.new_story_creator.layer_type while drafting and in layers.type when new_story_db_mapper inserts the accepted layer. |
| `offscreen_embedding_status` | Embedding state of an offscreen narration. The narration worker inserts rows at the pending default and no current writer moves them to embedded or failed; load_orrery_status_sync counts pending and failed rows. |
| `orrery_job_state` | Shared lease lifecycle of the durable job tables: queued, leased while a worker holds the lease, then succeeded, failed (requeued as queued below the attempt cap), or stale_rejected when the source the job was frozen against changed before completion. |
| `orrery_narration_status` | Offscreen narration progress of a resolution, set by the narration worker: none when promotion skipped it, queued when promoted or retried, succeeded with narration_chunk_id, failed on a final or stale-anchor failure. Bleed offers only succeeded rows; no current writer sets leased. |
| `orrery_promotion_status` | Promotion verdict of a resolution: pending for promotable drafts until promote_pending_resolutions_sync decides, promoted (which queues narration) or skipped. Non-promotable drafts are inserted as skipped; bleed reads promoted rows. |
| `orrery_routine_anchor_type` | Routine anchor a character travels to: home or work. Routine travel resolves the destination by this type, and works_from_home work anchors resolve through the home anchor. |
| `orrery_routine_mobility_policy` | How routine travel resolves a routine anchor (events._routine_anchor_destination_sync): fixed_place uses place_id, zone_resolved picks a place in zone_id, works_from_home uses the home anchor; nomadic and none yield no destination, and the resolver and substrate treat such anchors as absent. |
| `orrery_travel_mode` | Coarse travel mode used for route selection and duration estimates. Route graph node lookup accepts mixed as the fallback for any concrete mode. |
| `orrery_travel_risk` | Coarse travel risk. Estimated routes take the caller risk and authored edges keep their stored risk; package conditions read it through substrate.travel_risk_is. |
| `orrery_travel_route_method` | Which route source events._select_route_sync used, in order of preference: osm_graph (imported route graph), authored_edge (orrery_travel_edges), estimated (coordinate distance fallback). |
| `orrery_travel_status` | Travel lifecycle of a character: travel start writes in_transit, arrival writes at_place, and only an explicit planned row supplies a destination to start travel. |
| `place_reference_type` | Place role in an accepted chunk, written by the presence roster (roster.write_roster). Readers rank setting over transit over mentioned when choosing featured places, and setting rows give the scene location for return recaps and experiences. |
| `place_type` | Physical category of a place. The wizard writes the starting location type, trait compiler and Retrograde persistence stubs use other, Retrograde maturation places use fixed_location, and place_tag_manifest derives type rules from it. |
| `reference_type` | Character role in an accepted chunk, written by the presence roster: present for characters in the scene, mentioned for characters only named. Return recaps read present rows as the scene cast. |
| `world_layer_type` | Timeline layer of a chunk and of what derives from it: primary by default, flashback, atemporal, or extradiegetic when the storyteller wire declares one, retrograde for the Retrograde prologue chunk. Experience and narration jobs copy the anchor chunk layer and reject completion if it changed. |

| function (identity arguments) | obj_description(oid, 'pg_proc') |
|---|---|
| `nexus_reject_legacy_retrograde_summary_chunk()` | BEFORE INSERT OR UPDATE OF authorial_directives trigger on narrative_chunks (migration 078): rejects the orrery:retrograde_event_summary marker, because Retrograde event summaries live in retrograde_summaries. |
| `nexus_reject_legacy_retrograde_summary_link()` | BEFORE INSERT OR UPDATE OF payload trigger on world_events (migration 078): rejects the retired retrograde_summary_chunk_id payload key. |
| `nexus_require_retrograde_maturation_manifest_v1()` | BEFORE INSERT OR UPDATE OF result_manifest trigger on orrery_maturation_jobs (migration 078): a nonempty manifest must carry schema_version orrery_retrograde_maturation_manifest.v1, must not carry embedding_pending_chunk_ids, and must key embedding results by summary_id, not chunk_id. |
| `orrery_active_character_tag_names(p_character_entity_id bigint)` | Distinct names of the uncleared entity_tags on an entity; orrery_sync_character_need_states passes them to orrery_need_applies_to_tags. |
| `orrery_need_applies_to_tags(p_need_type character_need_type, p_active_tags text[])` | False when an active tag exempts the need (bodyform or mind tags for sleep, hunger, and thirst; also libido_absent for intimacy), else true. orrery_sync_character_need_states uses it to create and delete need rows; needs.need_applies_to_tags is the Python mirror. |
| `orrery_ensure_subtype_entity_kind()` | BEFORE INSERT OR UPDATE OF entity_id trigger on characters, factions, and places, with the expected entity_kind as its argument: creates the entities row when entity_id is NULL and raises when the linked entity is missing or of another kind. |
| `orrery_initialize_character_need_states()` | AFTER INSERT OR UPDATE OF entity_id trigger on characters: runs orrery_sync_character_need_states for the new entity_id so every applicable need row exists. |
| `orrery_sync_need_states_after_entity_tag_change()` | AFTER INSERT, UPDATE, or DELETE trigger on entity_tags: resynchronizes need rows for the affected entity through orrery_sync_character_need_states, skipped when fired from inside another trigger. |
| `refresh_world_time_from_chunk()` | Recomputes chunk_metadata.world_time for every chunk as global_variables.base_timestamp (now() if absent) plus the running sum of time_delta in chunk_id order; a world_time written by the inserter is overwritten. |
| `refresh_world_time_from_chunk_trigger()` | AFTER INSERT OR UPDATE OF time_delta statement trigger on chunk_metadata that calls refresh_world_time_from_chunk(); commit_handler_sync reads the resulting trigger-authored world_time after insertion. |
| `reject_storyteller_digest_update()` | BEFORE UPDATE trigger on storyteller_correspondence_digest_versions: raises on every update, because compaction appends a new digest version instead. |
| `reject_storyteller_letter_update()` | BEFORE UPDATE trigger on storyteller_correspondence_letters: raises on every update, because letters are append-only per accepted chunk. |
| `set_chunk_slug()` | BEFORE INSERT OR UPDATE trigger on chunk_metadata (trg_chunk_metadata_slug): sets slug to S&lt;season&gt;E&lt;episode&gt;_&lt;scene&gt; with two, two, and three zero-padded digits, overwriting any slug the inserter supplies. |
| `set_updated_at()` | BEFORE UPDATE trigger on characters, items, and places (trg_characters_set_updated, trg_items_set_updated, trg_places_set_updated): stamps updated_at with now(), the transaction start time. |
| `update_updated_at_column()` | BEFORE UPDATE trigger on incubator (update_incubator_updated_at, scripts/create_incubator_table.sql): stamps updated_at with CURRENT_TIMESTAMP on every update. |

## Counts

- Enums listed: **32**; functions listed: **15**; null or blank comments: **0**.
- Baseline before (`origin/main`, 8274b772): **81** entries (14 columns, 41 enums, 21 functions, 5 views).
- Baseline after (this branch): **34** entries (14 columns, 9 enums, 6 functions, 5 views).
- Removed: **47** entries (81 - 47 = 34), exactly the 32 enums and 15 functions listed above.
- Left for #813's drop list: enums `agent_type`, `log_level_type`, `emotional_valence`, `entity_type`, `item_type`, `relationship_type`, `threat_domain_type`, `threat_lifecycle_type`, `trait`; functions `hybrid_search` (three overloads), `migrate_embeddings()`, `pad_vector_384_to_1024(v vector)`, `pad_vector_to_1024(v vector)`.

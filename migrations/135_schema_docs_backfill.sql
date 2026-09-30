-- Migration 135: Backfill Evidence-Backed Enum and Function Comments (issue #819)
--
-- Slice C of #819. config/schema_docs_baseline.json listed 81 undocumented
-- objects (14 columns, 41 enums, 21 functions, 5 views). This migration
-- comments the 32 enums and 15 functions that a current reader, writer, or
-- trigger binding explains, and the same change removes their 47 baseline
-- entries (81 - 47 = 34 remain). The inventory is the independent review of
-- PR #1020 (issue #819 comment "Slice B (PR #1020) and the Seed of Slice C")
-- plus four objects resolved from the live NEXUS_template catalog:
-- faction_relationship_type, faction_member_role, set_chunk_slug(), and
-- set_updated_at(). No source file defines the last two; pg_proc and
-- pg_trigger on NEXUS_template and save_01..save_05 show the bodies and the
-- trigger bindings described below.
--
-- Left in the baseline on purpose: the #813 drop candidates (enums
-- agent_type, log_level_type, emotional_valence, entity_type, item_type,
-- relationship_type, threat_domain_type, threat_lifecycle_type, trait;
-- functions hybrid_search (three overloads), migrate_embeddings,
-- pad_vector_384_to_1024, pad_vector_to_1024), because a comment would
-- present a drop candidate as a documented object; and every baselined view
-- and column, which belong to a later slice.
--
-- Comment-only and idempotent: COMMENT ON replaces the previous text, so
-- rerunning this file leaves the same documentation. No objects are created
-- or changed. On 2026-09-29 every object below existed, with the identity
-- arguments used here, on NEXUS_template and save_01..save_05.
--
-- Evidence sites (reader/writer code at 8274b772) for every object below.
-- character_experience_basis: nexus/agents/orrery/experiences.py:569-573,621,967,1138,1444; nexus/agents/orrery/epistemics.py:17-18
-- character_experience_invalidation_status: nexus/agents/orrery/events.py:475-479; nexus/agents/orrery/experiences.py:832
-- character_need_type: nexus/agents/orrery/events.py:5605,5637; nexus/agents/orrery/needs.py:268,277,285
-- entity_kind: migrations/023_orrery_schema.py:260,302; nexus/agents/orrery/tag_writer.py:389-398
-- entity_tag_clearance_kind: nexus/agents/orrery/events.py:6015,7916,7932,7955,7973; nexus/agents/orrery/tag_writer.py:521-531,767,1119; nexus/agents/orrery/worker.py:498
-- entity_tag_reapplication_policy: nexus/agents/orrery/tag_writer.py:505-506,739,783,811
-- entity_tag_source_kind: nexus/agents/orrery/tag_writer.py:5-12,38,747,790; nexus/api/entity_tag_manifest_apply.py:11,491; nexus/agents/orrery/events.py:2379; nexus/agents/orrery/retrograde_persistence.py:2458; nexus/cli.py:107; nexus/api/faction_table_audit.py:17,475
-- event_role_kind: nexus/agents/orrery/events.py:6630,6639; nexus/agents/orrery/retrograde_persistence.py:1662,2429-2436; nexus/agents/orrery/epistemics.py:17-18; nexus/agents/orrery/experiences.py:569-571
-- event_severity_kind: migrations/033_orrery_travel_work.py:397-404; nexus/agents/orrery/knowledge_surfacing.py:168,505,523; nexus/agents/orrery/audit.py:1949
-- event_source_kind: nexus/agents/orrery/events.py:6610,6755; nexus/agents/orrery/propagation.py:809; nexus/agents/orrery/relationship_provenance.py:309; nexus/agents/orrery/reveal.py:508; nexus/agents/orrery/epistemics.py:535-536; nexus/agents/orrery/retrograde_persistence.py:1641,2183,2612; nexus/agents/orrery/replay.py:1525
-- faction_member_role: scripts/faction_relationship_analyst.py:651; migrations/088_valence_float_canonical.sql:188; nexus/agents/orrery/resolver.py:668
-- faction_relationship_type: scripts/faction_relationship_analyst.py:559; migrations/088_valence_float_canonical.sql:172; nexus/agents/orrery/resolver.py:625; nexus/agents/orrery/audit.py:2170
-- genre, geographic_scope, tech_level, tone: nexus/api/new_story_cache.py:721-730,1558-1571
-- layer_type: nexus/api/new_story_cache.py:765,1720; nexus/api/new_story_db_mapper.py:155,385
-- offscreen_embedding_status: nexus/agents/orrery/worker.py:478,486,624
-- orrery_job_state: nexus/jobs/narrative_jobs.py:106-119; nexus/agents/orrery/experiences.py:1737; nexus/agents/orrery/job_queues.py:25
-- orrery_narration_status: nexus/agents/orrery/worker.py:615,642,714,751,811,842; nexus/agents/orrery/bleed.py:252; nexus/agents/orrery/history.py:222
-- orrery_promotion_status: nexus/agents/orrery/events.py:2005,2017; nexus/agents/orrery/worker.py:206,809,842; nexus/agents/orrery/bleed.py:251
-- orrery_routine_anchor_type, orrery_routine_mobility_policy: nexus/agents/orrery/events.py:6919-6948; nexus/agents/orrery/resolver.py:1407; nexus/agents/orrery/substrate.py:1690,1760; scripts/backfill_routine_anchors.py:235
-- orrery_travel_mode, orrery_travel_risk, orrery_travel_route_method, orrery_travel_status: nexus/agents/orrery/events.py:5109-5120,5421,6902,7459,7607,7751,7855 (_select_route_sync); nexus/agents/orrery/substrate.py:1892; scripts/import_orrery_route_graph.py:110
-- place_reference_type: nexus/presence/roster.py:438-456; nexus/agents/lore/utils/entity_queries.py:259-274; nexus/api/return_recap.py:329
-- place_type: nexus/api/new_story_db_mapper.py:120,416; nexus/api/trait_compiler.py:1853; nexus/agents/orrery/retrograde_persistence.py:3222; nexus/agents/orrery/retrograde_maturation.py:455; nexus/api/place_tag_manifest.py:666
-- reference_type: nexus/presence/roster.py:438-453; nexus/api/return_recap.py:340
-- seed_type: nexus/api/new_story_cache.py:8,751,1685
-- world_layer_type: nexus/agents/logon/skald_wire.py:60,534; nexus/agents/orrery/retrograde_persistence.py:2580; nexus/agents/orrery/experiences.py:1055; nexus/agents/orrery/worker.py:822
-- nexus_reject_legacy_retrograde_summary_chunk(), nexus_reject_legacy_retrograde_summary_link(), nexus_require_retrograde_maturation_manifest_v1(): migrations/078_retrograde_summary_storage.py:1470,1492,1512; nexus/agents/orrery/retrograde_maturation.py:87,937
-- orrery_active_character_tag_names(bigint), orrery_need_applies_to_tags(character_need_type, text[]): migrations/057_orrery_need_bodyform_applicability.py:47,69; migrations/100_orrery_need_clock_anchor.sql:93,125,135,154; nexus/agents/orrery/needs.py:277
-- orrery_ensure_subtype_entity_kind(): migrations/023_orrery_schema.py:260,302
-- orrery_initialize_character_need_states(), orrery_sync_need_states_after_entity_tag_change(): migrations/057_orrery_need_bodyform_applicability.py:177,202
-- refresh_world_time_from_chunk(), refresh_world_time_from_chunk_trigger(): migrations/023_orrery_schema.py:721,748,761; nexus/api/commit_handler_sync.py:144-155
-- reject_storyteller_letter_update(), reject_storyteller_digest_update(): migrations/099_storyteller_correspondence.sql:41,81; nexus/memory/correspondence.py:321,381
-- set_chunk_slug(): trigger trg_chunk_metadata_slug (catalog only); nexus/api/commit_handler_sync.py:118-126; nexus/agents/orrery/backstage.py:203
-- set_updated_at(): triggers trg_characters_set_updated, trg_items_set_updated, trg_places_set_updated (catalog only)
-- update_updated_at_column(): scripts/create_incubator_table.sql:95,106

-- Enums.

COMMENT ON TYPE public.character_experience_basis IS
    'How a character holds an experience: participant or witness from the event-role receipts that seed_character_experiences_sync turns into seeds, acquisition from a claim the character was told or granted. Rendering reads it to choose the permitted names: claim sources for acquisition, the scene setting places otherwise.';

COMMENT ON TYPE public.character_experience_invalidation_status IS
    'Replay validity of a character experience. supersede_world_event_sync sets invalidated only on seeds that are not yet rendered; seed_character_experiences_sync treats only valid rows as already representing an event.';

COMMENT ON TYPE public.character_need_type IS
    'Need clocks that Orrery accrues against world time (needs.effective_debt_score, tuned in [orrery.sunhelm]). orrery_need_applies_to_tags and needs.need_applies_to_tags drop a need for bodyform or mind tags that exempt it.';

COMMENT ON TYPE public.entity_kind IS
    'Subtype of a row in entities. orrery_ensure_subtype_entity_kind creates or checks the entities row for each characters, factions, or places insert, and the tag writer reads tag_category_registry by this kind to allow tag categories.';

COMMENT ON TYPE public.entity_tag_clearance_kind IS
    'How an ephemeral tag clears: event when a matching event type fires (events._clear_event_tags_sync), time when expires_at_world_time passes (events._sweep_expired_entity_tags_sync), semantic only by an explicit clear. authored appears only in tag_clearance_log.mechanism, for any explicit clear by a writer (bestowal tags_to_clear, exclusive and status ladder replacement, template state deltas, clear_entity_tag).';

COMMENT ON TYPE public.entity_tag_reapplication_policy IS
    'What the tag writer does when a tag is applied while it is still active: new_row (the default) keeps the active row, replace overwrites its timing and provenance, extend_expiry pushes its expiry out by the duration (semantic and event tags land without expiry).';

COMMENT ON TYPE public.entity_tag_source_kind IS
    'Provenance of a tag row: skald_inline for runtime bestowals (storyteller, wizard, trait compiler), template for Orrery template effects, retrograde for Retrograde history, system for the entity tag and faction migration manifest applies, authored and llm_generated for offline or CLI backfills. The Orrery tag writer rejects auto_registered.';

COMMENT ON TYPE public.event_role_kind IS
    'Role of an entity in a world event: the resolver event writers and relationship provenance record actor and target, and Retrograde persistence records any role its expansion assigns (observer by default). epistemics.PARTICIPANT_ROLES (actor, target, beneficiary) make a character a participant and WITNESS_ROLES (observer, witness) a witness when experiences and claims are seeded.';

COMMENT ON TYPE public.event_severity_kind IS
    'Registered weight of an event type, seeded with the event vocabulary. Knowledge surfacing maps it through the configured severity_scores into candidate scoring, and the cognition audit reports it.';

COMMENT ON TYPE public.event_source_kind IS
    'Writer family of a world event: resolver for Orrery resolver-side writers (resolutions, propagation, relationship provenance, reveals), authored for authored backstory secrets, retrograde for Retrograde history, which Retrograde persistence and replay select by this value. No current writer uses apex, narrator, or bleed.';

COMMENT ON TYPE public.faction_member_role IS
    'Position of a character in a faction, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py) and exposed as entity_relationships_v.relationship_type with scope faction_character. The Orrery membership loader counts every row as membership whatever its role.';

COMMENT ON TYPE public.faction_relationship_type IS
    'Relationship between two factions, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py) and exposed as entity_relationships_v.relationship_type with scope faction. Current Orrery readers of that view select only character scope.';

COMMENT ON TYPE public.genre IS
    'Genre vocabulary of the new-story wizard. write_cache casts the setting draft into assets.new_story_creator.setting_genre and setting_secondary_genres, and _row_to_cache reads them back; a non-null setting_genre marks the setting phase complete.';

COMMENT ON TYPE public.geographic_scope IS
    'Geographic reach vocabulary of the new-story wizard setting draft; write_cache stores it in assets.new_story_creator.setting_geographic_scope and _row_to_cache reads it back.';

COMMENT ON TYPE public.tech_level IS
    'Technology level vocabulary of the new-story wizard setting draft; write_cache stores it in assets.new_story_creator.setting_tech_level and _row_to_cache reads it back.';

COMMENT ON TYPE public.tone IS
    'Tone vocabulary of the new-story wizard setting draft; write_cache stores it in assets.new_story_creator.setting_tone and _row_to_cache reads it back.';

COMMENT ON TYPE public.seed_type IS
    'Opening-situation vocabulary of the new-story wizard seed draft; write_cache stores the selected seed in assets.new_story_creator.seed_type, and its presence is part of the seed phase completion check.';

COMMENT ON TYPE public.layer_type IS
    'World layer kind of the new-story wizard, stored in assets.new_story_creator.layer_type while drafting and in layers.type when new_story_db_mapper inserts the accepted layer.';

COMMENT ON TYPE public.offscreen_embedding_status IS
    'Embedding state of an offscreen narration. The narration worker inserts rows at the pending default and no current writer moves them to embedded or failed; load_orrery_status_sync counts pending and failed rows.';

COMMENT ON TYPE public.orrery_job_state IS
    'Shared lease lifecycle of the durable job tables: queued, leased while a worker holds the lease, then succeeded, failed once the attempt cap is reached or on an error that cannot be retried (earlier retryable failures return to queued), or stale_rejected when the source the job was frozen against changed before completion.';

COMMENT ON TYPE public.orrery_narration_status IS
    'Offscreen narration progress of a resolution, set by the narration worker: none (the default) until promotion queues it, and it stays none when promotion skips it; queued when promoted or retried; succeeded with narration_chunk_id; failed on a final or stale-anchor failure. Bleed offers only succeeded rows; no current writer sets leased.';

COMMENT ON TYPE public.orrery_promotion_status IS
    'Promotion verdict of a resolution: pending for promotable drafts until promote_pending_resolutions_sync decides, promoted (which queues narration) or skipped. Non-promotable drafts are inserted as skipped; bleed reads promoted rows.';

COMMENT ON TYPE public.orrery_routine_anchor_type IS
    'Which routine anchor routine travel resolves (events._routine_anchor_destination_sync); a works_from_home work anchor resolves through the home anchor.';

COMMENT ON TYPE public.orrery_routine_mobility_policy IS
    'How routine travel resolves a routine anchor (events._routine_anchor_destination_sync): fixed_place uses place_id, zone_resolved picks a place in zone_id, works_from_home uses the home anchor; nomadic and none yield no destination, and the resolver and substrate treat such anchors as absent.';

COMMENT ON TYPE public.orrery_travel_mode IS
    'Coarse travel mode used for route selection and duration estimates. Route graph node lookup accepts mixed as the fallback for any concrete mode.';

COMMENT ON TYPE public.orrery_travel_risk IS
    'Coarse travel risk. Estimated routes take the caller risk and authored edges keep their stored risk; package conditions read it through substrate.travel_risk_is.';

COMMENT ON TYPE public.orrery_travel_route_method IS
    'Which route source events._select_route_sync used, in order of preference: osm_graph (imported route graph), authored_edge (orrery_travel_edges), estimated (coordinate distance fallback).';

COMMENT ON TYPE public.orrery_travel_status IS
    'Travel lifecycle of a character: travel start writes in_transit, arrival writes at_place, and only an explicit planned row supplies a destination to start travel.';

COMMENT ON TYPE public.place_reference_type IS
    'Place role in an accepted chunk, written by the presence roster (roster.write_roster). Readers rank setting over transit over mentioned when choosing featured places, and setting rows give the scene location for return recaps and experiences.';

COMMENT ON TYPE public.place_type IS
    'Physical category of a place. The wizard writes the starting location type, trait compiler and Retrograde persistence stubs use other, Retrograde maturation places use fixed_location, and place_tag_manifest derives type rules from it.';

COMMENT ON TYPE public.reference_type IS
    'Character role in an accepted chunk, written by the presence roster: present for characters in the scene, mentioned for characters only named. Return recaps read present rows as the scene cast.';

COMMENT ON TYPE public.world_layer_type IS
    'Timeline layer of a chunk and of what derives from it: primary by default, flashback, atemporal, or extradiegetic when the storyteller wire declares one, retrograde for the Retrograde prologue chunk. Experience and narration jobs copy the anchor chunk layer and reject completion if it changed.';

-- Functions.

COMMENT ON FUNCTION public.nexus_reject_legacy_retrograde_summary_chunk() IS
    'BEFORE INSERT OR UPDATE OF authorial_directives trigger on narrative_chunks (migration 078): rejects the orrery:retrograde_event_summary marker, because Retrograde event summaries live in retrograde_summaries.';

COMMENT ON FUNCTION public.nexus_reject_legacy_retrograde_summary_link() IS
    'BEFORE INSERT OR UPDATE OF payload trigger on world_events (migration 078): rejects the retired retrograde_summary_chunk_id payload key.';

COMMENT ON FUNCTION public.nexus_require_retrograde_maturation_manifest_v1() IS
    'BEFORE INSERT OR UPDATE OF result_manifest trigger on orrery_maturation_jobs (migration 078): a nonempty manifest must carry schema_version orrery_retrograde_maturation_manifest.v1, must not carry embedding_pending_chunk_ids, and its embedding results must not carry chunk_id (results are keyed by summary_id).';

COMMENT ON FUNCTION public.orrery_active_character_tag_names(p_character_entity_id bigint) IS
    'Distinct names of the uncleared entity_tags on an entity; orrery_sync_character_need_states passes them to orrery_need_applies_to_tags.';

COMMENT ON FUNCTION public.orrery_need_applies_to_tags(p_need_type character_need_type, p_active_tags text[]) IS
    'False when an active tag exempts the need (bodyform:android, bodyform:construct, bodyform:non_corporeal, digital_mind, inorganic, or virtual for sleep, hunger, and thirst; bodyform:non_corporeal, digital_mind, virtual, or libido_absent for intimacy), else true. orrery_sync_character_need_states uses it to create and delete need rows; needs.need_applies_to_tags is the Python mirror.';

COMMENT ON FUNCTION public.orrery_ensure_subtype_entity_kind() IS
    'BEFORE INSERT OR UPDATE OF entity_id trigger on characters, factions, and places, with the expected entity_kind as its argument: creates the entities row when entity_id is NULL and raises when the linked entity is missing or of another kind.';

COMMENT ON FUNCTION public.orrery_initialize_character_need_states() IS
    'AFTER INSERT OR UPDATE OF entity_id trigger on characters: runs orrery_sync_character_need_states for the new entity_id so every applicable need row exists.';

COMMENT ON FUNCTION public.orrery_sync_need_states_after_entity_tag_change() IS
    'AFTER INSERT, UPDATE, or DELETE trigger on entity_tags: resynchronizes need rows for the affected entity through orrery_sync_character_need_states, skipped when fired from inside another trigger.';

COMMENT ON FUNCTION public.refresh_world_time_from_chunk() IS
    'Recomputes chunk_metadata.world_time for every chunk as global_variables.base_timestamp (now() if absent) plus the running sum of time_delta in chunk_id order; a world_time written by the inserter is overwritten.';

COMMENT ON FUNCTION public.refresh_world_time_from_chunk_trigger() IS
    'AFTER INSERT OR UPDATE OF time_delta statement trigger on chunk_metadata that calls refresh_world_time_from_chunk(); commit_handler_sync reads the resulting trigger-authored world_time after insertion.';

COMMENT ON FUNCTION public.reject_storyteller_digest_update() IS
    'BEFORE UPDATE trigger on storyteller_correspondence_digest_versions: raises on every update, because compaction appends a new digest version instead.';

COMMENT ON FUNCTION public.reject_storyteller_letter_update() IS
    'BEFORE UPDATE trigger on storyteller_correspondence_letters: raises on every update, because letters are append-only per accepted chunk.';

COMMENT ON FUNCTION public.set_chunk_slug() IS
    'BEFORE INSERT OR UPDATE trigger on chunk_metadata (trg_chunk_metadata_slug): sets slug to S<season>E<episode>_<scene> with two, two, and three zero-padded digits, overwriting any slug the inserter supplies.';

COMMENT ON FUNCTION public.set_updated_at() IS
    'BEFORE UPDATE trigger on characters, items, and places (trg_characters_set_updated, trg_items_set_updated, trg_places_set_updated): stamps updated_at with now(), the transaction start time.';

COMMENT ON FUNCTION public.update_updated_at_column() IS
    'BEFORE UPDATE trigger on incubator (update_incubator_updated_at, scripts/create_incubator_table.sql): stamps updated_at with CURRENT_TIMESTAMP on every update.';

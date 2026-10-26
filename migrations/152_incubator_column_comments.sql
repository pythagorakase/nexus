-- Migration 152: Correct the Incubator Column Comments (issue #1106)
--
-- Routed from #819 at its close-out. Ten COMMENT ON COLUMN texts on
-- public.incubator and the COMMENT ON FUNCTION text of public.clear_incubator()
-- describe writers, keys, or states that the code at c7ae2988 does not have
-- (decision 1106-D1 on #1106 and its amendment at order freeze). A wrong
-- comment weighs as much as wrong behavior, because psql \d+ and the schema
-- summary present it as the documentation. Each replacement says what the
-- value holds and which code writes and reads it. The three JSON-column
-- comments name their top-level keys once as keys: {...} and the keys of a
-- nested object as <field>.keys: {...}, and
-- tests/test_incubator_column_comments_pg.py requires those sets to equal the
-- fields of the Pydantic models the writers and readers validate against.
-- Comments on the other incubator columns are accurate and stay as they are.
--
-- Comment-only and idempotent: COMMENT ON replaces the previous text, so
-- rerunning this file leaves the same documentation. No object is created or
-- changed and there is no schema change.
--
-- Locks: COMMENT ON takes SHARE UPDATE EXCLUSIVE on public.incubator, which
-- turn writes and FOR UPDATE reads do not block. lock_timeout bounds a wait
-- behind autovacuum or DDL.
--
-- Fleet: NEXUS_template and save_01 to save_05 were all at migration 151 with
-- byte-identical incubator column comments (md5
-- 6c46fa96543ffe20d5a9f2dbae7cb923, read-only, 2026-10-26).
--
-- Evidence sites (code at c7ae2988).
-- metadata_updates: nexus/api/lore_adapter.py:184,271-334,417-420; nexus/api/narrative_generation.py:852-862; nexus/agents/logon/apex_schema.py:322-379,382-407; nexus/api/draft_validation.py:59-63; nexus/api/commit_handler_sync.py:408,442-463,590,820-828; nexus/api/db_converters.py:88-119
-- entity_updates: nexus/api/lore_adapter.py:185,337-341,421; nexus/agents/logon/apex_schema.py:535-553; nexus/api/narrative_generation.py:863; nexus/api/draft_validation.py:105; nexus/api/commit_handler_sync.py:685-689,716-723,741
-- reference_updates: nexus/agents/logon/apex_schema.py:292-314; nexus/api/lore_adapter.py:186,344-379,422; nexus/api/narrative_generation.py:864-886; nexus/api/draft_validation.py:84; nexus/api/commit_handler_sync.py:634-684,707-714
-- status: nexus/api/lore_adapter.py:202; nexus/api/narrative_generation.py:521,590-614,891; nexus/api/commit_handler_sync.py:529,880-889; nexus/api/narrative.py:385-394,1659-1677; scripts/stamp_lore_pass_baseline.py:108; nexus/api/slot_endpoints.py:169-170,252-267
-- llm_response_id: nexus/api/lore_adapter.py:201; nexus/agents/logon/apex_schema.py:870-875; nexus/api/narrative_generation.py:890; nexus/api/commit_handler_sync.py:366
-- authorial_directives: migrations/040_storyteller_authorial_directives.sql:15-16; nexus/api/narrative_generation.py:562-575,590-614; nexus/api/commit_handler_sync.py:357-367
-- orrery_proposal: migrations/024_orrery_commit_pipeline.sql:9-10; nexus/api/lore_adapter.py:30,187-190,220-268; nexus/api/narrative_generation.py:510-513,844-892; nexus/api/commit_handler_sync.py:731-760; nexus/agents/orrery/bleed.py:372-394
-- parent_chunk_id: nexus/api/narrative_generation.py:846; nexus/api/commit_handler_sync.py:400-412,695-699; nexus/api/draft_validation.py:46-58
-- choice_object: nexus/api/choice_handling.py:131-186,227-298; nexus/api/lore_adapter.py:48-59,169-173; nexus/api/narrative_generation.py:894-900; nexus/api/narrative.py:362-394,1530-1572,1583-1595; nexus/api/commit_handler_sync.py:501-524
-- generation_model: nexus/api/narrative_generation.py:383,480-482,849; nexus/api/lore_adapter.py:165; nexus/api/commit_handler_sync.py:589
-- clear_incubator() (function): catalog body DELETE FROM incubator WHERE id = TRUE; no SQL caller in nexus/ or scripts/; nexus/api/narrative.py:1668-1672; nexus/api/slot_endpoints.py:262-265; nexus/api/commit_handler_sync.py:880-889

SET LOCAL lock_timeout = '5s';

-- Columns.

COMMENT ON COLUMN public.incubator.metadata_updates IS
    'Chunk metadata the storyteller declared for the pending draft, an apex_schema.ChunkMetadataUpdate object with keys: {chronology, world_layer, scene_weather, scene_boundary} and chronology.keys: {episode_transition, time_delta_minutes, time_delta_hours, time_delta_days, time_delta_description}. On a storyteller turn lore_adapter.extract_metadata_updates writes chronology when the response carries one, world_layer whenever it carries metadata, scene_weather only when the Skald sets one, and scene_boundary only when it is true; a response without metadata stores an empty object. The bootstrap opening writes chronology (new_episode, 0 minutes, Story begins) and world_layer primary. Staging and acceptance validate it against ChunkMetadataUpdate and ChronologyUpdate. Acceptance derives the new chunk season, episode and time delta from chronology (the scene is the parent scene plus one), writes world_layer (primary when absent) and scene_weather to chunk_metadata, and after the opening enqueues a scene experience job when scene_boundary is true. incubator_view lifts episode_transition, time_delta_description and world_layer.';

COMMENT ON COLUMN public.incubator.entity_updates IS
    'State changes the storyteller declared for the pending draft, an apex_schema.StateUpdates object with keys: {characters, relationships, locations, factions}, each an array. On a storyteller turn lore_adapter.extract_entity_updates stores the whole object with None fields left out, so all four arrays are present; the bootstrap opening stores an empty object. Both writers set the column, so its empty-array default is never kept. Staging and acceptance validate it against StateUpdates. When it is not empty, acceptance resolves its entity ids and applies it to the entity tables (apply_state_updates_sync); the stored value also goes to the Orrery tick as the storyteller state updates. incubator_view exposes it as entity_changes and counts its characters, locations and factions entries.';

COMMENT ON COLUMN public.incubator.reference_updates IS
    'Existing entities the pending draft names, an apex_schema.ReferencedEntities object with keys: {characters, places, factions, departures}. On a storyteller turn lore_adapter.extract_reference_updates always writes the characters, places and factions arrays, and adds departures (authored exits retained internally for reconciliation) only when there are any. The bootstrap opening writes the player character as present when known, other characters the prose names as mentioned, the starting place as setting, and an empty factions array. Staging and acceptance validate it against ReferencedEntities. Acceptance resolves characters, places and factions to ids, treats departures as explicit exits while it reconciles the scene with the parent roster, and writes the new chunk roster (roster.write_roster). incubator_view exposes it as references.';

COMMENT ON COLUMN public.incubator.status IS
    'Draft state, always provisional. Both writers set provisional (lore_adapter.response_to_incubator and narrative_generation.generate_bootstrap_narrative), a replaced draft is written as provisional again, and no code writes another value. Acceptance deletes the row in the transaction that creates the new chunk, and DELETE /api/narrative/incubator and slot undo delete a discarded draft, so no other value occurs. Acceptance selects it without acting on it; incubator_view and GET /api/narrative/incubator pass it through.';

COMMENT ON COLUMN public.incubator.llm_response_id IS
    'Debugging id of the generation behind the pending draft. The bootstrap opening stores bootstrap_ followed by eight hex digits. Storyteller turns store NULL: lore_adapter.response_to_incubator reads a response_id attribute that no StoryTurnResponse model defines. Acceptance selects it and copies it nowhere; incubator_view leaves it out.';

COMMENT ON COLUMN public.incubator.authorial_directives IS
    'Unused; every row keeps the default empty array. Migration 040 added it for storyteller retrieval directives, but no current code writes it: neither incubator writer names it, and acceptance does not copy it to narrative_chunks.authorial_directives. incubator_view and GET /api/narrative/incubator pass it through.';

COMMENT ON COLUMN public.incubator.orrery_proposal IS
    'Staged Orrery state for the pending draft; NULL for the bootstrap opening. On a storyteller turn lore_adapter stores the no-write OrreryTickProposal (OrreryTickProposal.to_dict) when one was resolved, plus the key _bleed_offer_resolution_ids: the orrery_resolutions ids whose Bleed offers this exact draft carried, possibly none. Without a proposal the object holds that key alone. Acceptance separates the two (lore_adapter.split_staged_orrery_payload), passes the proposal to the Orrery tick, which stamps it into the canonical Orrery tables, and counts each listed offer against the parent chunk (bleed.record_bleed_offers).';

COMMENT ON COLUMN public.incubator.parent_chunk_id IS
    'Id of the accepted chunk the pending draft continues, or 0 for the bootstrap opening, which has no parent; the column has no foreign key. Draft validation and acceptance treat 0 as the opening and read no parent metadata or roster.';

COMMENT ON COLUMN public.incubator.choice_object IS
    'Choices the pending draft offers and the player selection among them, an object with presented (the choice texts) and selected, plus edited true when the player sent an edited version of the selected choice. A storyteller turn (lore_adapter.extract_choice_object) stores the presented choices with selected null when the response carries at least two, and the bootstrap opening does so when its response carries any; otherwise the column is NULL. When the player responds, the continue path and POST /api/narrative/select-choice rewrite it in the shape choice_handling.normalize_choice_object returns: selected is the 1-indexed number of the chosen presented choice, or null for freeform input (the continue path gives freeform text identical to a presented choice that number), and edited sits at the top level beside selected while the edited text itself lives in choice_text. Acceptance copies the normalized object to narrative_chunks.choice_object, filling a blank choice_text from the selected choice; incubator_view and GET /api/narrative/incubator pass it through.';

COMMENT ON COLUMN public.incubator.generation_model IS
    'Registry model id that produced the pending storyteller text. write_to_incubator refuses a draft whose model id is missing or blank, and both the storyteller turn and the bootstrap opening are staged through it, so no current row holds NULL, although the column allows it. Acceptance copies it to chunk_metadata.generation_model; incubator_view leaves it out.';

-- Function.

COMMENT ON FUNCTION public.clear_incubator() IS
    'Deletes the singleton incubator row, discarding any pending draft. No code in nexus/ or scripts/ calls it: DELETE /api/narrative/incubator, slot undo and acceptance each delete the row with their own statement.';

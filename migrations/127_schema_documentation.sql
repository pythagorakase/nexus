-- Migration 127: Document Evident Table and Column Contracts
--
-- Evidence sites (reader/writer code) for every table touched below.
-- Timestamp comments describe stored database fields, not automatic-update guarantees.
-- Unresolved semantics remain in config/schema_docs_baseline.json.
-- assets.character_images: nexus/api/asset_endpoints.py:61,119,142,168,231,287,349
-- assets.new_story_creator: nexus/api/new_story_cache.py:301,325,371,410,1006,1249,1379,1430,1462
-- assets.place_images: nexus/api/asset_endpoints.py:61,119,142,168,231,287,349
-- public.character_need_states: nexus/agents/orrery/events.py:5600,5634; migrations/028_orrery_sunhelm_needs.py:105,207
-- public.character_psychology: nexus/api/reader_endpoints.py:477
-- public.character_relationships: nexus/api/reader_endpoints.py:444; migrations/065_reconstructability.sql:92
-- public.character_routine_anchors: scripts/backfill_routine_anchors.py:235; nexus/agents/orrery/resolver.py:839; migrations/056_orrery_routine_anchors.py:58
-- public.characters: nexus/api/reader_endpoints.py:398; migrations/023_orrery_schema.py:231,257
-- public.chunk_metadata: nexus/api/commit_handler.py:265,279; nexus/api/reader_endpoints.py:84
-- public.entities: migrations/023_orrery_schema.py:184,231,257; nexus/agents/orrery/resolver.py:395,518
-- public.entity_pair_tags: nexus/agents/orrery/tag_writer.py:1527,1696
-- public.entity_tags: nexus/agents/orrery/events.py:5890,5990; nexus/agents/orrery/tag_writer.py:889
-- public.event_types: nexus/agents/orrery/tag_library.py:188,216; nexus/agents/orrery/events.py:6854; migrations/025_orrery_package_library_vocab.py:264; migrations/023_orrery_schema.py:545
-- public.factions: migrations/023_orrery_schema.py:231,257
-- public.global_variables: nexus/config/story_model.py:38,64
-- public.incubator: nexus/api/narrative_generation.py:557
-- public.layers: nexus/api/new_story_db_mapper.py:380
-- public.narrative_generation_lease: nexus/api/narrative_lease.py:50,101,125
-- public.narrative_generation_sessions: nexus/api/narrative_lease.py:71,84,137,213
-- public.narrative_parent_embedding_claims: nexus/api/narrative_lease.py:157,180
-- public.offscreen_narrations: nexus/agents/orrery/worker.py:477,624; nexus/agents/orrery/bleed.py:241
-- public.orrery_adjudication_log: nexus/agents/orrery/events.py:1625
-- public.orrery_maturation_jobs: nexus/agents/orrery/retrograde_maturation.py:1540; migrations/062_retrograde_maturation_jobs.py:34
-- public.orrery_narration_jobs: nexus/agents/orrery/worker.py:242,283,320,650,683,818
-- public.orrery_place_route_graph_nodes: scripts/import_orrery_route_graph.py:45,69,105,139; nexus/agents/orrery/events.py:7455,7519
-- public.orrery_prompt_exposures: nexus/agents/orrery/events.py:1850,1927
-- public.orrery_resolutions: nexus/agents/orrery/events.py:2001,6533,7886; nexus/agents/orrery/worker.py:624,799; nexus/agents/orrery/bleed.py:388
-- public.orrery_route_graph_edges: scripts/import_orrery_route_graph.py:45,69,105,139; nexus/agents/orrery/events.py:7455,7519
-- public.orrery_route_graph_nodes: scripts/import_orrery_route_graph.py:45,69,105,139; nexus/agents/orrery/events.py:7455,7519
-- public.orrery_scene_pressures: nexus/agents/orrery/events.py:1790
-- public.pair_tags: nexus/agents/orrery/tag_writer.py:1451,1527
-- public.place_chunk_references: nexus/presence/roster.py:434
-- public.places: nexus/api/reader_endpoints.py:522; nexus/api/new_story_db_mapper.py:415; migrations/023_orrery_schema.py:257
-- public.relationship_versions: migrations/065_reconstructability.sql:92
-- public.retrograde_summaries: nexus/agents/orrery/retrograde_persistence.py:2283; nexus/agents/orrery/retrograde_embedding.py:158
-- public.schema_migrations: scripts/migrate.py:114,173,203,267
-- public.state_checkpoints: nexus/agents/orrery/reconstruction.py:225
-- public.state_delta_log: nexus/agents/orrery/reconstruction.py:287
-- public.tag_category_registry: nexus/agents/orrery/tag_library.py:113,168; nexus/agents/orrery/tag_writer.py:493
-- public.tag_clearance_log: nexus/agents/orrery/events.py:6013,7900; nexus/agents/orrery/tag_writer.py:688
-- public.tags: nexus/agents/orrery/tag_writer.py:515,608,837; nexus/agents/orrery/tag_library.py:113; nexus/agents/orrery/events.py:7917
-- public.world_event_entities: nexus/agents/orrery/events.py:6630; nexus/agents/orrery/retrograde_persistence.py:2406
-- public.world_events: nexus/agents/orrery/events.py:445,6580,6606; nexus/agents/orrery/retrograde_persistence.py:2375
-- public.zones: nexus/api/new_story_db_mapper.py:394

-- assets.character_images
COMMENT ON TABLE assets.character_images IS 'Uploaded character image records served by the asset endpoints.';
COMMENT ON COLUMN assets.character_images.id IS 'Image row identifier used by image selection and deletion.';
COMMENT ON COLUMN assets.character_images.character_id IS 'Owner ID from the characters table.';
COMMENT ON COLUMN assets.character_images.file_path IS 'Image path relative to ui/client/public, returned to the client.';
COMMENT ON COLUMN assets.character_images.is_main IS 'Main image flag: 1 for the selected image, 0 for other images of the same owner.';
COMMENT ON COLUMN assets.character_images.display_order IS 'Ascending image display order within an owner.';
COMMENT ON COLUMN assets.character_images.uploaded_at IS 'Upload row timestamp returned as uploadedAt; defaults to database transaction time.';

-- assets.new_story_creator
COMMENT ON COLUMN assets.new_story_creator.id IS 'Singleton wizard cache key; readers and writers use TRUE.';
COMMENT ON COLUMN assets.new_story_creator.thread_id IS 'Wizard conversation thread identifier stored when the cache is initialized.';
COMMENT ON COLUMN assets.new_story_creator.target_slot IS 'Save slot selected when the wizard cache is initialized.';
COMMENT ON COLUMN assets.new_story_creator.setting_secondary_genres IS 'Cached setting secondary genres from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_world_name IS 'Cached setting world name from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_time_period IS 'Cached setting time period from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_tech_level IS 'Cached setting tech level from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_magic_exists IS 'Cached setting magic exists from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_magic_description IS 'Cached setting magic description from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_political_structure IS 'Cached setting political structure from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_major_conflict IS 'Cached setting major conflict from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_tone IS 'Cached setting tone from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_themes IS 'Cached setting themes from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_cultural_notes IS 'Cached setting cultural notes from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_language_notes IS 'Cached setting language notes from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.setting_geographic_scope IS 'Cached setting geographic scope from the wizard setting draft.';
COMMENT ON COLUMN assets.new_story_creator.character_archetype IS 'Cached character archetype from the wizard character draft.';
COMMENT ON COLUMN assets.new_story_creator.character_background IS 'Cached character background from the wizard character draft.';
COMMENT ON COLUMN assets.new_story_creator.character_appearance IS 'Cached character appearance from the wizard character draft.';
COMMENT ON COLUMN assets.new_story_creator.seed_title IS 'Cached seed title from the wizard seed draft.';
COMMENT ON COLUMN assets.new_story_creator.seed_situation IS 'Cached seed situation from the wizard seed draft.';
COMMENT ON COLUMN assets.new_story_creator.seed_hook IS 'Cached seed hook from the wizard seed draft.';
COMMENT ON COLUMN assets.new_story_creator.seed_immediate_goal IS 'Cached seed immediate goal from the wizard seed draft.';
COMMENT ON COLUMN assets.new_story_creator.seed_stakes IS 'Cached seed stakes from the wizard seed draft.';
COMMENT ON COLUMN assets.new_story_creator.seed_tension_source IS 'Cached seed tension source from the wizard seed draft.';
COMMENT ON COLUMN assets.new_story_creator.seed_weather IS 'Cached seed weather from the wizard seed draft.';
COMMENT ON COLUMN assets.new_story_creator.seed_key_npcs IS 'Cached seed key npcs from the wizard seed draft.';
COMMENT ON COLUMN assets.new_story_creator.layer_name IS 'Cached layer name from the wizard layer draft.';
COMMENT ON COLUMN assets.new_story_creator.layer_type IS 'Cached layer type from the wizard layer draft.';
COMMENT ON COLUMN assets.new_story_creator.layer_description IS 'Cached layer description from the wizard layer draft.';
COMMENT ON COLUMN assets.new_story_creator.zone_name IS 'Cached zone name from the wizard zone draft.';
COMMENT ON COLUMN assets.new_story_creator.zone_summary IS 'Cached zone summary from the wizard zone draft.';
COMMENT ON COLUMN assets.new_story_creator.base_timestamp IS 'Diegetic base instant used to reconstruct the selected seed timestamp in UTC.';
COMMENT ON COLUMN assets.new_story_creator.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- assets.place_images
COMMENT ON TABLE assets.place_images IS 'Uploaded place image records served by the asset endpoints.';
COMMENT ON COLUMN assets.place_images.id IS 'Image row identifier used by image selection and deletion.';
COMMENT ON COLUMN assets.place_images.place_id IS 'Owner ID from the places table.';
COMMENT ON COLUMN assets.place_images.file_path IS 'Image path relative to ui/client/public, returned to the client.';
COMMENT ON COLUMN assets.place_images.is_main IS 'Main image flag: 1 for the selected image, 0 for other images of the same owner.';
COMMENT ON COLUMN assets.place_images.display_order IS 'Ascending image display order within an owner.';
COMMENT ON COLUMN assets.place_images.uploaded_at IS 'Upload row timestamp returned as uploadedAt; defaults to database transaction time.';

-- public.character_need_states
COMMENT ON COLUMN public.character_need_states.character_entity_id IS 'Character entity whose need debt is tracked; joins the entity identity spine.';
COMMENT ON COLUMN public.character_need_states.need_type IS 'Need being tracked, paired with character_entity_id to identify the debt row.';
COMMENT ON COLUMN public.character_need_states.metadata IS 'JSON metadata written by the need-state backfill, including its backfilled flag.';
COMMENT ON COLUMN public.character_need_states.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.character_need_states.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.character_psychology
COMMENT ON COLUMN public.character_psychology.character_id IS 'Character ID used to retrieve this psychology profile.';
COMMENT ON COLUMN public.character_psychology.self_concept IS 'Psychology profile self concept JSON returned by the character psychology endpoint.';
COMMENT ON COLUMN public.character_psychology.behavior IS 'Psychology profile behavior JSON returned by the character psychology endpoint.';
COMMENT ON COLUMN public.character_psychology.cognitive_framework IS 'Psychology profile cognitive framework JSON returned by the character psychology endpoint.';
COMMENT ON COLUMN public.character_psychology.temperament IS 'Psychology profile temperament JSON returned by the character psychology endpoint.';
COMMENT ON COLUMN public.character_psychology.relational_style IS 'Psychology profile relational style JSON returned by the character psychology endpoint.';
COMMENT ON COLUMN public.character_psychology.defense_mechanisms IS 'Psychology profile defense mechanisms JSON returned by the character psychology endpoint.';
COMMENT ON COLUMN public.character_psychology.character_arc IS 'Psychology profile character arc JSON returned by the character psychology endpoint.';
COMMENT ON COLUMN public.character_psychology.secrets IS 'Psychology profile secrets JSON returned by the character psychology endpoint.';

-- public.character_relationships
COMMENT ON COLUMN public.character_relationships.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.character_relationships.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.character_routine_anchors
COMMENT ON COLUMN public.character_routine_anchors.id IS 'Routine anchor row identifier.';
COMMENT ON COLUMN public.character_routine_anchors.character_entity_id IS 'Character entity assigned to this routine anchor.';
COMMENT ON COLUMN public.character_routine_anchors.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.character_routine_anchors.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.characters
COMMENT ON COLUMN public.characters.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.characters.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';
COMMENT ON COLUMN public.characters.entity_id IS 'Shared entity identity for this character, allocated by the entity-kind trigger.';

-- public.chunk_metadata
COMMENT ON COLUMN public.chunk_metadata.id IS 'Surrogate identifier of the chunk metadata row.';
COMMENT ON COLUMN public.chunk_metadata.generation_date IS 'Generation timestamp supplied to the chunk commit; defaults in the writer to UTC now.';

-- public.entities
COMMENT ON TABLE public.entities IS 'Shared identity spine for characters, places, and factions used by Orrery.';
COMMENT ON COLUMN public.entities.id IS 'Shared entity identifier used by character, place, and faction subtype rows.';
COMMENT ON COLUMN public.entities.kind IS 'Entity subtype: character, place, or faction; validated by subtype triggers.';
COMMENT ON COLUMN public.entities.is_active IS 'Whether the entity participates in active-entity resolver queries.';
COMMENT ON COLUMN public.entities.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.entities.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.entity_pair_tags
COMMENT ON COLUMN public.entity_pair_tags.id IS 'Identifier of one applied directed pair-tag row.';

-- public.entity_tags
COMMENT ON TABLE public.entity_tags IS 'Applications of registered tags to entities, retaining cleared applications.';
COMMENT ON COLUMN public.entity_tags.id IS 'Identifier of one tag application, referenced by tag_clearance_log.';
COMMENT ON COLUMN public.entity_tags.entity_id IS 'Entity receiving the tag application.';
COMMENT ON COLUMN public.entity_tags.tag_id IS 'Applied vocabulary entry in tags.';
COMMENT ON COLUMN public.entity_tags.applied_at IS 'Database timestamp when the tag application row was inserted.';
COMMENT ON COLUMN public.entity_tags.applied_at_world_time IS 'Diegetic timestamp of tag application, supplied by the writer.';
COMMENT ON COLUMN public.entity_tags.cleared_at IS 'Database timestamp of clearance; NULL identifies a current application.';
COMMENT ON COLUMN public.entity_tags.template_id IS 'Orrery template identifier supplied by template-driven tag writers.';
COMMENT ON COLUMN public.entity_tags.source_kind IS 'Provenance category supplied by the tag writer, such as template or authored.';

-- public.event_types
COMMENT ON TABLE public.event_types IS 'Registered world-event vocabulary read by event validation and prompt libraries.';
COMMENT ON COLUMN public.event_types.category IS 'Event category exposed by the event vocabulary library.';
COMMENT ON COLUMN public.event_types.severity IS 'Registered severity label assigned by event vocabulary seed writers.';
COMMENT ON COLUMN public.event_types.description IS 'Human-readable event vocabulary description.';
COMMENT ON COLUMN public.event_types.deprecated IS 'Whether this event type is excluded from current event validation.';
COMMENT ON COLUMN public.event_types.synonym_for IS 'Canonical event-type name referenced by an alias vocabulary row.';

-- public.factions
COMMENT ON COLUMN public.factions.entity_id IS 'Shared entity identity for this faction, allocated by the entity-kind trigger.';

-- public.global_variables
COMMENT ON COLUMN public.global_variables.model IS 'Per-story Skald model pin read through StorySettings; NULL leaves model resolution to defaults.';

-- public.incubator
COMMENT ON COLUMN public.incubator.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.incubator.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.layers
COMMENT ON TABLE public.layers IS 'World layers created by the new-story mapper and referenced by zones.';
COMMENT ON COLUMN public.layers.id IS 'Layer identifier returned when creating the layer and assigned to its zones.';
COMMENT ON COLUMN public.layers.name IS 'Layer name from the accepted layer draft.';
COMMENT ON COLUMN public.layers.type IS 'Layer type from the accepted layer draft.';
COMMENT ON COLUMN public.layers.description IS 'Layer description from the accepted layer draft.';

-- public.narrative_generation_lease
COMMENT ON COLUMN public.narrative_generation_lease.id IS 'Singleton lease key; acquisition and ownership checks use TRUE.';
COMMENT ON COLUMN public.narrative_generation_lease.session_id IS 'Generation session that owns the slot lease.';
COMMENT ON COLUMN public.narrative_generation_lease.parent_chunk_id IS 'Parent chunk bound after lease acquisition; NULL until binding.';
COMMENT ON COLUMN public.narrative_generation_lease.operation IS 'Generation operation supplied at lease acquisition.';
COMMENT ON COLUMN public.narrative_generation_lease.acquired_at IS 'Database timestamp when the lease row was inserted.';
COMMENT ON COLUMN public.narrative_generation_lease.expires_at IS 'Lease expiry instant used to reject stale ownership and allow reacquisition.';

-- public.narrative_generation_sessions
COMMENT ON COLUMN public.narrative_generation_sessions.session_id IS 'Durable generation-session identifier used to correlate lease ownership and outcome.';
COMMENT ON COLUMN public.narrative_generation_sessions.operation IS 'Generation operation recorded when the session is initiated.';
COMMENT ON COLUMN public.narrative_generation_sessions.parent_chunk_id IS 'Resolved parent chunk bound to this generation session.';
COMMENT ON COLUMN public.narrative_generation_sessions.status IS 'Generation lifecycle status updated by the lease/session writers.';
COMMENT ON COLUMN public.narrative_generation_sessions.error IS 'Error text persisted when a generation session fails or expires.';
COMMENT ON COLUMN public.narrative_generation_sessions.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.narrative_generation_sessions.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.narrative_parent_embedding_claims
COMMENT ON COLUMN public.narrative_parent_embedding_claims.parent_chunk_id IS 'Parent chunk whose embedding enqueue is claimed.';
COMMENT ON COLUMN public.narrative_parent_embedding_claims.session_id IS 'Generation session owning the parent embedding claim.';
COMMENT ON COLUMN public.narrative_parent_embedding_claims.claimed_at IS 'Database timestamp of initial claim or replacement of an errored session claim.';

-- public.offscreen_narrations
COMMENT ON TABLE public.offscreen_narrations IS 'Stored perceptual descriptors for promoted Orrery resolutions, consumed by bleed retrieval.';
COMMENT ON COLUMN public.offscreen_narrations.id IS 'Descriptor row identifier referenced by orrery_resolutions.narration_chunk_id.';
COMMENT ON COLUMN public.offscreen_narrations.resolution_id IS 'Orrery resolution for which the descriptor was produced.';
COMMENT ON COLUMN public.offscreen_narrations.tick_chunk_id IS 'Accepted tick chunk anchoring the descriptor.';
COMMENT ON COLUMN public.offscreen_narrations.world_layer IS 'World layer captured from the narration job anchor.';
COMMENT ON COLUMN public.offscreen_narrations.text IS 'Text column currently written as the deterministic perceptual descriptor serialized to JSON.';
COMMENT ON COLUMN public.offscreen_narrations.perceptual_descriptor IS 'Structured perceptual descriptor JSON persisted by the narration worker.';
COMMENT ON COLUMN public.offscreen_narrations.embedding_status IS 'Stored embedding state counted by the worker status report.';
COMMENT ON COLUMN public.offscreen_narrations.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.orrery_adjudication_log
COMMENT ON TABLE public.orrery_adjudication_log IS 'Recorded adjudication decisions and optional replacements for Orrery proposals.';
COMMENT ON COLUMN public.orrery_adjudication_log.id IS 'Adjudication log row identifier.';
COMMENT ON COLUMN public.orrery_adjudication_log.tick_chunk_id IS 'Tick chunk to which the adjudication belongs.';
COMMENT ON COLUMN public.orrery_adjudication_log.proposal_id IS 'Proposal identifier supplied by the adjudication decision.';
COMMENT ON COLUMN public.orrery_adjudication_log.template_id IS 'Template identifier of the adjudicated resolution draft.';
COMMENT ON COLUMN public.orrery_adjudication_log.binding_hash IS 'Binding fingerprint of the adjudicated resolution draft.';
COMMENT ON COLUMN public.orrery_adjudication_log.action IS 'Adjudication action supplied by the decision.';
COMMENT ON COLUMN public.orrery_adjudication_log.adjudication_source IS 'Validated source label supplied to the adjudication writer.';
COMMENT ON COLUMN public.orrery_adjudication_log.skald_note IS 'Note text supplied by the adjudication decision.';
COMMENT ON COLUMN public.orrery_adjudication_log.original_state_delta IS 'State-delta JSON from the original resolution draft.';
COMMENT ON COLUMN public.orrery_adjudication_log.replacement_state_delta IS 'Replacement state-delta JSON, when supplied by the decision.';
COMMENT ON COLUMN public.orrery_adjudication_log.replacement_event_type IS 'Replacement event type supplied by the adjudication decision.';
COMMENT ON COLUMN public.orrery_adjudication_log.applied_resolution_id IS 'Applied resolution identifier supplied to the log writer, if any.';
COMMENT ON COLUMN public.orrery_adjudication_log.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.orrery_maturation_jobs
COMMENT ON COLUMN public.orrery_maturation_jobs.id IS 'Maturation job row identifier.';
COMMENT ON COLUMN public.orrery_maturation_jobs.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.orrery_maturation_jobs.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.orrery_narration_jobs
COMMENT ON TABLE public.orrery_narration_jobs IS 'Leased and retried jobs that persist descriptors for promoted Orrery resolutions.';
COMMENT ON COLUMN public.orrery_narration_jobs.id IS 'Narration job identifier used for lease fencing and completion.';
COMMENT ON COLUMN public.orrery_narration_jobs.resolution_id IS 'Orrery resolution whose descriptor is to be persisted.';
COMMENT ON COLUMN public.orrery_narration_jobs.slot IS 'Save-slot label supplied when the resolution is promoted.';
COMMENT ON COLUMN public.orrery_narration_jobs.state IS 'Job lifecycle state used by lease, completion, and retry queries.';
COMMENT ON COLUMN public.orrery_narration_jobs.attempts IS 'Number of leases acquired; incremented when a worker leases the job.';
COMMENT ON COLUMN public.orrery_narration_jobs.available_at IS 'Earliest database time at which a queued retry may be leased.';
COMMENT ON COLUMN public.orrery_narration_jobs.lease_until IS 'Lease expiry checked by fenced job updates.';
COMMENT ON COLUMN public.orrery_narration_jobs.last_error IS 'Most recently persisted retry or terminal failure text.';
COMMENT ON COLUMN public.orrery_narration_jobs.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.orrery_narration_jobs.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.orrery_place_route_graph_nodes
COMMENT ON COLUMN public.orrery_place_route_graph_nodes.place_id IS 'Place ID attached to the route graph.';
COMMENT ON COLUMN public.orrery_place_route_graph_nodes.graph_key IS 'Graph key grouping the place anchor with its route node.';
COMMENT ON COLUMN public.orrery_place_route_graph_nodes.node_id IS 'Route-node ID resolved from the imported anchor node key.';
COMMENT ON COLUMN public.orrery_place_route_graph_nodes.distance_m IS 'Optional place-to-node distance in meters from the import payload.';
COMMENT ON COLUMN public.orrery_place_route_graph_nodes.source IS 'Source label supplied per imported item, falling back to the graph source label.';
COMMENT ON COLUMN public.orrery_place_route_graph_nodes.metadata IS 'JSON metadata copied from the imported graph item, defaulting to an empty object.';
COMMENT ON COLUMN public.orrery_place_route_graph_nodes.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.orrery_place_route_graph_nodes.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.orrery_prompt_exposures
COMMENT ON COLUMN public.orrery_prompt_exposures.id IS 'Prompt exposure row identifier.';
COMMENT ON COLUMN public.orrery_prompt_exposures.tick_chunk_id IS 'Tick chunk whose rendered cards are recorded.';
COMMENT ON COLUMN public.orrery_prompt_exposures.kind IS 'Rendered card kind, including resolution, scene_pressure, and joint_beat.';
COMMENT ON COLUMN public.orrery_prompt_exposures.proposal_id IS 'Rendered proposal identity formed from template_id and binding_hash.';
COMMENT ON COLUMN public.orrery_prompt_exposures.template_id IS 'Template identity of the exposed card.';
COMMENT ON COLUMN public.orrery_prompt_exposures.binding_hash IS 'Binding fingerprint or ambient seed deduplication key of the exposed card.';
COMMENT ON COLUMN public.orrery_prompt_exposures.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.orrery_resolutions
COMMENT ON TABLE public.orrery_resolutions IS 'Persisted Orrery resolution drafts and their event, promotion, narration, and surfacing state.';
COMMENT ON COLUMN public.orrery_resolutions.id IS 'Resolution identifier returned by the resolution writer.';
COMMENT ON COLUMN public.orrery_resolutions.tick_chunk_id IS 'Tick chunk under which the resolution was applied.';
COMMENT ON COLUMN public.orrery_resolutions.template_id IS 'Template identifier copied from the resolution draft.';
COMMENT ON COLUMN public.orrery_resolutions.binding_hash IS 'Binding fingerprint used with tick and template to deduplicate a resolution.';
COMMENT ON COLUMN public.orrery_resolutions.actor_entity_id IS 'Actor entity supplied by the resolution writer.';
COMMENT ON COLUMN public.orrery_resolutions.priority IS 'Priority copied from the resolution draft.';
COMMENT ON COLUMN public.orrery_resolutions.magnitude IS 'Magnitude copied from the resolution draft.';
COMMENT ON COLUMN public.orrery_resolutions.state_delta IS 'Resolution state-delta JSON, also extended with applied-result bookkeeping.';
COMMENT ON COLUMN public.orrery_resolutions.brief IS 'Rendered brief supplied by the resolution writer.';
COMMENT ON COLUMN public.orrery_resolutions.event_ids IS 'World-event identifiers attached to this resolution by the event writer.';
COMMENT ON COLUMN public.orrery_resolutions.promotion_status IS 'Promotion state: initially pending for promotable drafts, otherwise skipped.';
COMMENT ON COLUMN public.orrery_resolutions.promotion_verdict IS 'Serialized promotion verdict persisted by the worker.';
COMMENT ON COLUMN public.orrery_resolutions.narration_status IS 'Descriptor-job status tracked on the resolution.';
COMMENT ON COLUMN public.orrery_resolutions.narration_chunk_id IS 'Identifier of the offscreen_narrations row persisted for this resolution.';
COMMENT ON COLUMN public.orrery_resolutions.last_offered_chunk_id IS 'Most recent chunk at which the bleed candidate was recorded as offered.';
COMMENT ON COLUMN public.orrery_resolutions.offer_count IS 'Count incremented each time the bleed offer is recorded.';
COMMENT ON COLUMN public.orrery_resolutions.first_surfaced_chunk_id IS 'First chunk recorded by the bleed-offer writer; preserved on later offers.';
COMMENT ON COLUMN public.orrery_resolutions.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.orrery_route_graph_edges
COMMENT ON COLUMN public.orrery_route_graph_edges.id IS 'Route-edge row identifier.';
COMMENT ON COLUMN public.orrery_route_graph_edges.graph_key IS 'Graph key from the import payload, grouping edges with their nodes.';
COMMENT ON COLUMN public.orrery_route_graph_edges.from_node_id IS 'Starting route-node identifier resolved from the imported from key.';
COMMENT ON COLUMN public.orrery_route_graph_edges.to_node_id IS 'Ending route-node identifier resolved from the imported to key.';
COMMENT ON COLUMN public.orrery_route_graph_edges.travel_mode IS 'Travel mode assigned to the imported route edge.';
COMMENT ON COLUMN public.orrery_route_graph_edges.risk IS 'Risk label assigned to the imported route edge.';
COMMENT ON COLUMN public.orrery_route_graph_edges.bidirectional IS 'Whether the route edge permits traversal in both directions.';
COMMENT ON COLUMN public.orrery_route_graph_edges.distance_m IS 'Imported edge travel distance in meters.';
COMMENT ON COLUMN public.orrery_route_graph_edges.source IS 'Source label supplied per imported item, falling back to the graph source label.';
COMMENT ON COLUMN public.orrery_route_graph_edges.metadata IS 'JSON metadata copied from the imported graph item, defaulting to an empty object.';
COMMENT ON COLUMN public.orrery_route_graph_edges.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.orrery_route_graph_edges.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.orrery_route_graph_nodes
COMMENT ON COLUMN public.orrery_route_graph_nodes.id IS 'Route-node identifier returned by the importer and used by edges and place anchors.';
COMMENT ON COLUMN public.orrery_route_graph_nodes.source IS 'Source label supplied per imported item, falling back to the graph source label.';
COMMENT ON COLUMN public.orrery_route_graph_nodes.metadata IS 'JSON metadata copied from the imported graph item, defaulting to an empty object.';
COMMENT ON COLUMN public.orrery_route_graph_nodes.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.orrery_route_graph_nodes.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';

-- public.orrery_scene_pressures
COMMENT ON COLUMN public.orrery_scene_pressures.id IS 'Scene-pressure row identifier.';
COMMENT ON COLUMN public.orrery_scene_pressures.tick_chunk_id IS 'Tick chunk whose scene pressure is recorded.';
COMMENT ON COLUMN public.orrery_scene_pressures.priority IS 'Priority copied from the scene-pressure proposal.';
COMMENT ON COLUMN public.orrery_scene_pressures.magnitude IS 'Magnitude copied from the scene-pressure proposal.';
COMMENT ON COLUMN public.orrery_scene_pressures.branch_label IS 'Branch label copied from the scene-pressure proposal.';
COMMENT ON COLUMN public.orrery_scene_pressures.pressure_stub IS 'Pressure stub text copied from the proposal.';
COMMENT ON COLUMN public.orrery_scene_pressures.bindings IS 'Entity-binding JSON copied from the scene-pressure proposal.';
COMMENT ON COLUMN public.orrery_scene_pressures.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.pair_tags
COMMENT ON COLUMN public.pair_tags.id IS 'Pair-tag vocabulary identifier referenced by entity_pair_tags.pair_tag_id.';

-- public.place_chunk_references
COMMENT ON COLUMN public.place_chunk_references.reference_type IS 'Place presence/reference role written from the chunk roster: mentioned, transit, setting, or present.';
COMMENT ON COLUMN public.place_chunk_references.evidence IS 'Evidence text carried by the place entry in the chunk presence roster.';

-- public.places
COMMENT ON COLUMN public.places.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';
COMMENT ON COLUMN public.places.updated_at IS 'Stored row update timestamp; initialized to database transaction time.';
COMMENT ON COLUMN public.places.entity_id IS 'Shared entity identity for this place, allocated by the entity-kind trigger.';

-- public.relationship_versions
COMMENT ON COLUMN public.relationship_versions.id IS 'Relationship-version row identifier.';
COMMENT ON COLUMN public.relationship_versions.relationship_table IS 'Name of the relationship table whose row was changed, taken from TG_TABLE_NAME.';
COMMENT ON COLUMN public.relationship_versions.operation IS 'Lowercase trigger operation: update or delete.';
COMMENT ON COLUMN public.relationship_versions.source_chunk_id IS 'Chunk attribution from transaction-local nexus.source_chunk_id; NULL for unattributed writes.';
COMMENT ON COLUMN public.relationship_versions.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.retrograde_summaries
COMMENT ON COLUMN public.retrograde_summaries.id IS 'Retrograde summary identifier returned by the summary writer.';
COMMENT ON COLUMN public.retrograde_summaries.world_event_id IS 'World event summarized by this retrograde summary.';
COMMENT ON COLUMN public.retrograde_summaries.chronology IS 'Chronology text supplied with the retrograde summary.';
COMMENT ON COLUMN public.retrograde_summaries.summary_text IS 'Persisted retrograde summary text used for embedding and retrieval.';
COMMENT ON COLUMN public.retrograde_summaries.embedding_generated_at IS 'Timestamp stamped after the summary embedding write succeeds; NULL permits retry.';
COMMENT ON COLUMN public.retrograde_summaries.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.schema_migrations
COMMENT ON TABLE public.schema_migrations IS 'Applied migration versions tracked by the migration runner.';
COMMENT ON COLUMN public.schema_migrations.version IS 'Three-digit migration version from the migration filename or bootstrap list.';
COMMENT ON COLUMN public.schema_migrations.name IS 'Migration name from the migration filename or bootstrap list.';
COMMENT ON COLUMN public.schema_migrations.applied_at IS 'Database transaction timestamp when the migration stamp was inserted.';

-- public.state_checkpoints
COMMENT ON COLUMN public.state_checkpoints.id IS 'Checkpoint identifier returned by the checkpoint writer.';
COMMENT ON COLUMN public.state_checkpoints.label IS 'Validated checkpoint label used with chunk_id for idempotency.';
COMMENT ON COLUMN public.state_checkpoints.state IS 'JSON snapshot of the mutable state sections assembled by the checkpoint writer.';
COMMENT ON COLUMN public.state_checkpoints.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.state_delta_log
COMMENT ON COLUMN public.state_delta_log.id IS 'State-delta ledger row identifier.';
COMMENT ON COLUMN public.state_delta_log.source_chunk_id IS 'Chunk attributed to this scalar state write.';
COMMENT ON COLUMN public.state_delta_log.writer IS 'Writer label supplied by the scalar-state writer.';
COMMENT ON COLUMN public.state_delta_log.entity_id IS 'Entity associated with the scalar write, when supplied.';
COMMENT ON COLUMN public.state_delta_log.new_value IS 'New scalar field value serialized to JSON by the delta writer.';
COMMENT ON COLUMN public.state_delta_log.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.tag_category_registry
COMMENT ON COLUMN public.tag_category_registry.category IS 'Category key joined to tags.category.';
COMMENT ON COLUMN public.tag_category_registry.entity_kind IS 'Entity kind permitted to receive tags in this category.';
COMMENT ON COLUMN public.tag_category_registry.prompt_order IS 'Numeric category ordering used by the prompt vocabulary reader.';
COMMENT ON COLUMN public.tag_category_registry.description IS 'Category description exposed by the tag library.';
COMMENT ON COLUMN public.tag_category_registry.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.tag_clearance_log
COMMENT ON TABLE public.tag_clearance_log IS 'Audit records for cleared entity-tag applications and their triggering evidence.';
COMMENT ON COLUMN public.tag_clearance_log.id IS 'Tag-clearance audit row identifier.';
COMMENT ON COLUMN public.tag_clearance_log.entity_tag_id IS 'Tag application being cleared.';
COMMENT ON COLUMN public.tag_clearance_log.cleared_at IS 'Database timestamp when the clearance log row was inserted.';
COMMENT ON COLUMN public.tag_clearance_log.cleared_at_world_time IS 'Diegetic clearance time supplied by the tag-clearance writer.';
COMMENT ON COLUMN public.tag_clearance_log.mechanism IS 'Clearance mechanism supplied by the writer, such as event or authored.';
COMMENT ON COLUMN public.tag_clearance_log.triggering_event_id IS 'World event responsible for an event-triggered clearance, when supplied.';
COMMENT ON COLUMN public.tag_clearance_log.justification IS 'Writer-supplied JSON explaining the tag clearance.';
COMMENT ON COLUMN public.tag_clearance_log.source_chunk_id IS 'Chunk attributed to the clearance by the writer.';

-- public.tags
COMMENT ON TABLE public.tags IS 'Registered single-entity tag vocabulary and application/clearance policies.';
COMMENT ON COLUMN public.tags.id IS 'Tag vocabulary identifier referenced by entity_tags.tag_id.';
COMMENT ON COLUMN public.tags.tag IS 'Tag name accepted by the registered-tag writer.';
COMMENT ON COLUMN public.tags.category IS 'Category key used to validate compatible entity kinds and group prompt vocabulary.';
COMMENT ON COLUMN public.tags.is_ephemeral IS 'Whether the registered tag uses ephemeral lifecycle handling.';
COMMENT ON COLUMN public.tags.clearance_kind IS 'Registered clearance mechanism used by the tag application writer.';
COMMENT ON COLUMN public.tags.reapplication_policy IS 'Registered policy used when applying the tag again: new_row, extend_expiry, or replace.';
COMMENT ON COLUMN public.tags.clear_on IS 'JSON clearance configuration whose event_types list is matched by event-driven clearance.';
COMMENT ON COLUMN public.tags.synonym_for IS 'Canonical tag ID referenced by an alias; alias rows are excluded from direct application.';
COMMENT ON COLUMN public.tags.deprecated IS 'Whether the tag is excluded from current application and prompt vocabulary.';
COMMENT ON COLUMN public.tags.description IS 'Human-readable description exposed in the tag library.';
COMMENT ON COLUMN public.tags.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.world_event_entities
COMMENT ON TABLE public.world_event_entities IS 'Entity participants associated with world events and their event roles.';
COMMENT ON COLUMN public.world_event_entities.event_id IS 'World event in which the entity participates.';
COMMENT ON COLUMN public.world_event_entities.role IS 'Participant role in the event, such as actor or target.';
COMMENT ON COLUMN public.world_event_entities.entity_id IS 'Shared identity of the participating entity.';

-- public.world_events
COMMENT ON TABLE public.world_events IS 'World-event records emitted by narrative and Orrery writers, with participants and provenance.';
COMMENT ON COLUMN public.world_events.id IS 'World-event identifier returned by event writers.';
COMMENT ON COLUMN public.world_events.event_type IS 'Registered event-type name validated against event_types.';
COMMENT ON COLUMN public.world_events.tick_chunk_id IS 'Tick chunk attributed to the event by its writer.';
COMMENT ON COLUMN public.world_events.actor_entity_id IS 'Actor entity supplied by the event writer.';
COMMENT ON COLUMN public.world_events.target_entity_id IS 'Target entity supplied by the event writer.';
COMMENT ON COLUMN public.world_events.location_id IS 'Place ID supplied as the event location.';
COMMENT ON COLUMN public.world_events.world_layer IS 'World layer supplied by the event writer.';
COMMENT ON COLUMN public.world_events.source IS 'Event provenance category supplied by the writer.';
COMMENT ON COLUMN public.world_events.changed_fields IS 'State-field names supplied by the event writer to describe changes.';
COMMENT ON COLUMN public.world_events.magnitude IS 'Event magnitude supplied by the writer.';
COMMENT ON COLUMN public.world_events.resolution_id IS 'Originating Orrery resolution when the event is emitted by a resolution.';
COMMENT ON COLUMN public.world_events.payload IS 'Writer-supplied event JSON, including resolution bindings and signal detection for resolver events.';
COMMENT ON COLUMN public.world_events.superseded_by_event_id IS 'Replacement event identifier set when an event is superseded.';
COMMENT ON COLUMN public.world_events.created_at IS 'Database timestamp when this row was created; defaults to transaction time.';

-- public.zones
COMMENT ON COLUMN public.zones.layer IS 'Layer ID returned during world-hierarchy creation and assigned to the zone.';

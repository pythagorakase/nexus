Every event_anchored single_entity_tag must include supporting_event_ref that matches a mechanical_hints.events event_ref inside the same candidate.
single_entity_tags use tag_ref values from allowed_vocabulary.single_entity_tag_refs; this encodes the legal entity_kind|tag pair.
Prompt-visible-only tags may influence prose but must not appear in mechanical_hints.single_entity_tags.
Pair tags use tag_ref values from allowed_vocabulary.pair_tag_refs; relationships use relationship_ref values from allowed_vocabulary.relationship_refs.
Single-entity tags must be registered for the tagged entity_kind in registered_tags_by_entity_kind; a tag listed only under another kind is illegal.
selected_seed_ids and rejected_seed_ids must reference returned candidate seed_id values, and a seed cannot be both selected and rejected.
Every candidate_graph.junctions entry has exactly two edge legs. Those legs must be claimed exactly once by two different candidates using the same endpoint kind and normalized name.
Entity refs (entity_ref, subject_ref, object_ref, participating_entities, open_endpoint_name, project_intent.target_ref) are bare proper names of at most {{ENTITY_REF_MAX_LENGTH}} characters -- never sentences, descriptive phrases, or kind-prefixed forms such as character:Name. candidate_graph ref and anchor_ref values (kind:name) are graph identifiers; write only the matching node's name field in a ref, never the identifier. Implied new entities get a short invented name, not a description.
If a hint is marginal or cannot satisfy these rules, omit the hint.
Every event_plan item must reference one or more selected seed ids.
Every selected seed must appear once in thread_plan.
Woven threads must reference planned event_ref values whose event seed_ids include that thread's seed_id.
Each selected junction must have both member seeds woven through its promised shared entity in structured event participants/location, or both rejected with no events; junction members cannot be deferred.
mechanical_plan rows use plan='entity_tag', 'pair_tag', 'relationship', or 'death'. Leave fields irrelevant to that plan as empty strings.
death mechanics require source_event_ref naming the causing event, and that event must list the dying entity as a participant.
death mechanics may only target new backstory figures this plan itself introduces — never first-class starting entities or entities already live in the story.
Event-anchored entity_tag mechanics require source_event_ref that matches event_plan.event_ref.
Prompt-visible-only tags must not appear in mechanical_plan.
Pair tags must obey registered subject/object kind constraints.
Plan at most one status:* pair tag per subject/object edge; it records final standing, while the arc belongs in event_plan.
Single-entity tags must be registered for the tagged entity_kind in registered_tags_by_entity_kind; a tag listed only under another kind is illegal.
relationship mechanics currently support only character->character rows; express faction/place pressure through events or pair tags.
A trait with cold_start_relationships='forbidden' prohibits its blocked relationship and pair-tag mechanics when either endpoint is the protagonist or a listed alias. Keep permissible backstory events; omit only the forbidden mechanical row.
project_plan may carry only a woven selected seed's exact project_intent; explain any dropped woven intent in thread_plan.note.
Every seek_redemption project requires a TARGET->ACTOR relationship at wary-or-worse valence in project_start_relationships or this response's relationship mechanics.
Entity refs (subject_ref, object_ref, location_ref) are proper names of at most {{ENTITY_REF_MAX_LENGTH}} characters -- never sentences or descriptive phrases. New implied entities get a short invented name, not a description.
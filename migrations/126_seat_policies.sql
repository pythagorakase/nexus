ALTER TABLE character_experience_jobs ADD COLUMN resolved_model text;
COMMENT ON COLUMN character_experience_jobs.resolved_model IS 'Literal registry model ID resolved in the accepting transaction; immutable across story repins. NULL legacy jobs must fail before dispatch.';
ALTER TABLE character_experience_jobs ADD COLUMN resolved_source text;
COMMENT ON COLUMN character_experience_jobs.resolved_source IS 'Model selection source captured at enqueue (request, story_pin, story_follow, player_preference, seat_default, repository_default). NULL identifies unresolved legacy work.';

ALTER TABLE orrery_maturation_jobs ADD COLUMN resolved_model text;
COMMENT ON COLUMN orrery_maturation_jobs.resolved_model IS 'Literal registry model ID resolved in the accepting transaction; immutable across story repins. NULL legacy jobs must fail before dispatch.';
ALTER TABLE orrery_maturation_jobs ADD COLUMN resolved_source text;
COMMENT ON COLUMN orrery_maturation_jobs.resolved_source IS 'Model selection source captured at enqueue (request, story_pin, story_follow, player_preference, seat_default, repository_default). NULL identifies unresolved legacy work.';

ALTER TABLE correspondence_compaction_jobs ADD COLUMN resolved_model text;
COMMENT ON COLUMN correspondence_compaction_jobs.resolved_model IS 'Literal registry model ID resolved in the accepting transaction; immutable across story repins. NULL legacy jobs must fail before dispatch.';
ALTER TABLE correspondence_compaction_jobs ADD COLUMN resolved_source text;
COMMENT ON COLUMN correspondence_compaction_jobs.resolved_source IS 'Model selection source captured at enqueue (request, story_pin, story_follow, player_preference, seat_default, repository_default). NULL identifies unresolved legacy work.';

ALTER TABLE narrative_summary_jobs ADD COLUMN resolved_model text;
COMMENT ON COLUMN narrative_summary_jobs.resolved_model IS 'Literal registry model ID resolved in the accepting transaction; immutable across story repins. NULL legacy jobs must fail before dispatch.';
ALTER TABLE narrative_summary_jobs ADD COLUMN resolved_source text;
COMMENT ON COLUMN narrative_summary_jobs.resolved_source IS 'Model selection source captured at enqueue (request, story_pin, story_follow, player_preference, seat_default, repository_default). NULL identifies unresolved legacy work.';

COMMENT ON COLUMN generation_attempt_manifests.story_pin IS 'Story model, Gaia model and context-window pins at dispatch, plus resolved_source from the captured seat resolution (NULL on historical attempts).';

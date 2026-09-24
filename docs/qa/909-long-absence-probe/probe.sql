-- All distinct probe-authored SQL, in execution order.
-- SELECT current_database() was repeated before source queries and clone steps.
-- Source transactions were read-only; CREATE used the postgres maintenance database.

SELECT current_database();

SELECT current_database(), count(*), max(id) FROM narrative_chunks;

SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('characters','character_relationships','chunk_metadata','global_variables','narrative_chunks','turn_llm_calls') ORDER BY table_name,ordinal_position;

SELECT c.id,c.name,c.summary,max(r.chunk_id) AS last_present,49-max(r.chunk_id) AS id_gap,(SELECT world_time FROM chunk_metadata WHERE chunk_id=49)-m.world_time AS world_gap,EXISTS(SELECT 1 FROM character_relationships cr WHERE c.id IN (cr.character1_id,cr.character2_id)) AS has_relationship FROM characters c JOIN chunk_character_references r ON r.character_id=c.id AND r.reference='present' JOIN chunk_metadata m ON m.chunk_id=(SELECT max(r2.chunk_id) FROM chunk_character_references r2 WHERE r2.character_id=c.id AND r2.reference='present') GROUP BY c.id,m.world_time ORDER BY last_present,c.id;

SELECT * FROM global_variables;

SELECT * FROM character_relationships ORDER BY character1_id,character2_id;

SELECT id,storyteller_text,choice_text FROM narrative_chunks WHERE id=49;

SELECT id,storyteller_text,choice_text FROM narrative_chunks WHERE id IN (21,25);

SELECT c.*, p.name AS location_name FROM characters c LEFT JOIN places p ON p.id=c.current_location WHERE c.id IN (4,11,14);

SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name LIKE '%job%' OR table_name LIKE '%prompt%' OR table_name LIKE '%exposure%' OR table_name='incubator');

CREATE DATABASE qa640_909_long_absence TEMPLATE template0;

-- Cleanup: clone and source counts checked before dropping the clone.
SELECT current_database(), count(*), max(id) FROM narrative_chunks;

SELECT current_database(), count(*), max(id) FROM narrative_chunks;

SELECT current_database();

DROP DATABASE qa640_909_long_absence;

SELECT current_database(), datname FROM pg_database WHERE datname='qa640_909_long_absence';

-- Resumed live probe, 2026-09-24. Source reads use default_transaction_read_only=on.
-- Each evidence query and psycopg2 connection is preceded by SELECT current_database().
-- These exploratory statements preceded the JSONL recorder.
SELECT current_database(), count(*), max(id) FROM narrative_chunks;
-- Failed introspection; transaction rolled back: UndefinedColumn world_state_model.
SELECT model,world_state_model FROM global_variables;
SELECT current_database(),model,gaia_model FROM global_variables;
SELECT id,storyteller_text FROM narrative_chunks WHERE id IN (25,48,49) ORDER BY id;
-- Maintenance connection identity checked first; clone only.
CREATE DATABASE qa640_909_long_absence TEMPLATE template0;
-- pg_dump/pg_restore use their standard internal catalog/export/restore SQL.
-- Gateway DELETE /api/narrative/incubator?slot=4, admitted clone only:
DELETE FROM incubator WHERE id=TRUE;
-- Reset the clone's inherited frontier choice before first probe continuation.
UPDATE narrative_chunks SET choice_text=NULL,
  choice_object=choice_object - 'selected' - 'selection_type',
  raw_text=storyteller_text WHERE id=49;
-- All subsequent distinct evidence SQL is appended from live/sql.jsonl below.
-- Second Ivo attempt failed validation. Reset only the clone's frontier choice
-- to permit a same-setting return input on the final spare.
UPDATE narrative_chunks SET choice_text=NULL,
  choice_object=choice_object - 'selected' - 'selection_type',
  raw_text=storyteller_text WHERE id=53;

-- Target: save_04 (read-only evidence).
SELECT current_database(), count(*), max(id) FROM narrative_chunks;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT current_database(), count(*), max(id) FROM narrative_chunks;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT c.id,c.name,c.summary,max(r.chunk_id) AS last_present,49-max(r.chunk_id) AS id_gap,(SELECT world_time FROM chunk_metadata WHERE chunk_id=49)-m.world_time AS world_gap,EXISTS(SELECT 1 FROM character_relationships cr WHERE c.id IN (cr.character1_id,cr.character2_id)) AS has_relationship FROM characters c JOIN chunk_character_references r ON r.character_id=c.id AND r.reference='present' JOIN chunk_metadata m ON m.chunk_id=(SELECT max(r2.chunk_id) FROM chunk_character_references r2 WHERE r2.character_id=c.id AND r2.reference='present') GROUP BY c.id,m.world_time ORDER BY last_present,c.id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT id,storyteller_text,choice_text FROM narrative_chunks WHERE id IN (21,25,48,49) ORDER BY id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM character_relationships ORDER BY character1_id,character2_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM global_variables;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM characters WHERE id IN (2,4,11,14);

-- Target: qa640_909_long_absence (read-only evidence).
SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('retrieval_coverage_log','turn_llm_calls','prompt_exposure_log','narrative_chunks','incubator') ORDER BY table_name,ordinal_position;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM incubator;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT current_database();

-- Target: qa640_909_long_absence (read-only evidence).
SELECT id,choice_object,choice_text,raw_text FROM narrative_chunks WHERE id=49;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT id,choice_object,choice_text FROM narrative_chunks WHERE id=49;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM narrative_chunks WHERE id=(SELECT max(id) FROM narrative_chunks);

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM retrieval_coverage_log WHERE turn_id='79b4e65e-39ab-4e90-a28d-86756688ac02';

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM chunk_metadata WHERE chunk_id=50;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM chunk_character_references WHERE chunk_id=50;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM world_events WHERE tick_chunk_id=50;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM orrery_adjudication_log WHERE tick_chunk_id=50;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM orrery_prompt_exposures WHERE tick_chunk_id=50;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM retrieval_coverage_log WHERE turn_id='86c3f720-9cfb-4855-ac3f-4ff32c829851';

-- Target: qa640_909_long_absence (read-only evidence).
SELECT table_schema,table_name,column_name FROM information_schema.columns WHERE column_name IN ('source_chunk_id','episode_id','season_id','summary') AND table_schema='public' ORDER BY column_name,table_name;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'backstory_secrets' AS source_table,source_chunk_id,count(*) FROM backstory_secrets WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'character_project_states' AS source_table,source_chunk_id,count(*) FROM character_project_states WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'claim_awareness' AS source_table,source_chunk_id,count(*) FROM claim_awareness WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'claims' AS source_table,source_chunk_id,count(*) FROM claims WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'entity_pair_tags' AS source_table,source_chunk_id,count(*) FROM entity_pair_tags WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'entity_tags' AS source_table,source_chunk_id,count(*) FROM entity_tags WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'relationship_versions' AS source_table,source_chunk_id,count(*) FROM relationship_versions WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'state_delta_log' AS source_table,source_chunk_id,count(*) FROM state_delta_log WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT 'tag_clearance_log' AS source_table,source_chunk_id,count(*) FROM tag_clearance_log WHERE source_chunk_id IN (25,48) GROUP BY source_chunk_id;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM episodes;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM seasons;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM relationship_versions WHERE source_chunk_id IN (25,48);

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM state_delta_log WHERE source_chunk_id IN (25,48);

-- Target: qa640_909_long_absence (read-only evidence).
SELECT current_database(), (SELECT count(*) FROM episodes) AS episode_rows,(SELECT count(*) FROM seasons) AS season_rows;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM retrieval_coverage_log WHERE turn_id='0eaa2cbf-a5b5-4b1b-a728-4ae381d71e9f';

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM chunk_metadata WHERE chunk_id=52;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM chunk_character_references WHERE chunk_id=52;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM world_events WHERE tick_chunk_id=52;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM orrery_adjudication_log WHERE tick_chunk_id=52;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM orrery_prompt_exposures WHERE tick_chunk_id=52;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM retrieval_coverage_log WHERE turn_id='f246f3ca-052c-4719-a64c-2bbe24410ed3';

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM chunk_metadata WHERE chunk_id=53;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM chunk_character_references WHERE chunk_id=53;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM world_events WHERE tick_chunk_id=53;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM orrery_adjudication_log WHERE tick_chunk_id=53;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM orrery_prompt_exposures WHERE tick_chunk_id=53;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM chunk_metadata WHERE chunk_id=51;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM chunk_character_references WHERE chunk_id=51;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM world_events WHERE tick_chunk_id=51;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM orrery_adjudication_log WHERE tick_chunk_id=51;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM orrery_prompt_exposures WHERE tick_chunk_id=51;

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM narrative_generation_sessions WHERE session_id='71c52416-673f-4400-93de-4411368c9c5d';

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM narrative_generation_sessions WHERE session_id='1f6e283e-ca89-41ed-af93-1d7a43d668c4';

-- Target: qa640_909_long_absence (read-only evidence).
SELECT * FROM narrative_generation_sessions WHERE session_id='d62347f1-cf28-468e-a44b-cd853c8d44f7';

-- Final cleanup after report writing, maintenance database postgres.
SELECT current_database();
DROP DATABASE qa640_909_long_absence;
SELECT current_database(), datname FROM pg_database WHERE datname='qa640_909_long_absence';

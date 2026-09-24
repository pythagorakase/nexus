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

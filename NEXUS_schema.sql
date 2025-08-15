-- -------------------------------------------------------------
-- TablePlus 6.6.8(632)
--
-- https://tableplus.com/
--
-- Database: NEXUS
-- Generation Time: 2025-08-15 14:17:52.7930
-- -------------------------------------------------------------


-- Table Definition
CREATE TABLE "public"."seasons" (
    "id" int8 NOT NULL,
    "summary" jsonb,
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."seasons"."id" IS 'Season number - primary key for sequential ordering';
COMMENT ON COLUMN "public"."seasons"."summary" IS 'JSONB containing season overview, themes, major plot arcs, and key events';

-- Table Definition
CREATE TABLE "public"."global_variables" (
    "id" bool NOT NULL DEFAULT true,
    "base_timestamp" timestamptz NOT NULL,
    "user_character" int8,
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."global_variables"."id" IS 'Boolean primary key - ensures only one row exists (always TRUE)';
COMMENT ON COLUMN "public"."global_variables"."base_timestamp" IS 'Reference timestamp for calculating narrative time progression';
COMMENT ON COLUMN "public"."global_variables"."user_character" IS 'Foreign key to characters.id - the currently active player character';

-- Table Definition
CREATE TABLE "public"."character_relationships" (
    "character1_id" int4 NOT NULL,
    "character2_id" int4 NOT NULL,
    "relationship_type" varchar(50) NOT NULL,
    "emotional_valence" varchar(50) NOT NULL,
    "dynamic" text NOT NULL,
    "recent_events" text NOT NULL,
    "history" text NOT NULL,
    "extra_data" jsonb,
    "created_at" timestamptz DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamptz DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY ("character1_id","character2_id")
);

-- Column Comment
COMMENT ON COLUMN "public"."character_relationships"."character1_id" IS 'First character in the relationship';
COMMENT ON COLUMN "public"."character_relationships"."character2_id" IS 'Second character in the relationship';
COMMENT ON COLUMN "public"."character_relationships"."relationship_type" IS 'Type of relationship (romantic, friend, rival, etc.)';
COMMENT ON COLUMN "public"."character_relationships"."emotional_valence" IS 'Emotional quality and intensity (e.g. +5|devoted)';
COMMENT ON COLUMN "public"."character_relationships"."dynamic" IS 'Description of relationship dynamics';
COMMENT ON COLUMN "public"."character_relationships"."recent_events" IS 'Recent developments affecting the relationship';
COMMENT ON COLUMN "public"."character_relationships"."history" IS 'Historical context of the relationship';
COMMENT ON COLUMN "public"."character_relationships"."extra_data" IS 'Additional relationship data (shared experiences, tension points, etc.)';

-- Table Definition
CREATE TABLE "public"."character_psychology" (
    "character_id" int8 NOT NULL,
    "self_concept" jsonb,
    "behavior" jsonb,
    "cognitive_framework" jsonb,
    "temperament" jsonb,
    "relational_style" jsonb,
    "defense_mechanisms" jsonb,
    "character_arc" jsonb,
    "secrets" jsonb,
    "validation_evidence" jsonb,
    "created_at" timestamptz DEFAULT now(),
    "updated_at" timestamptz DEFAULT now(),
    PRIMARY KEY ("character_id")
);

-- Column Comment
COMMENT ON COLUMN "public"."character_psychology"."validation_evidence" IS 'JSONB array of narrative excerpts and chunk references that support the psychological analysis';
COMMENT ON COLUMN "public"."character_psychology"."created_at" IS 'Timestamp when psychological profile was first created';
COMMENT ON COLUMN "public"."character_psychology"."updated_at" IS 'Timestamp of last psychological profile update';

-- Table Definition
CREATE TABLE "public"."episodes" (
    "season" int8 NOT NULL,
    "episode" int8 NOT NULL,
    "chunk_span" int8range,
    "summary" jsonb,
    "temp_span" int8range,
    PRIMARY KEY ("season","episode")
);

-- Column Comment
COMMENT ON COLUMN "public"."episodes"."season" IS 'Season number';
COMMENT ON COLUMN "public"."episodes"."episode" IS 'Episode number within the season';
COMMENT ON COLUMN "public"."episodes"."chunk_span" IS 'Range of chunk IDs included in this episode';
COMMENT ON COLUMN "public"."episodes"."summary" IS 'Comprehensive episode summary (OVERVIEW, TIMELINE, CHARACTERS, PLOT_THREADS, CONTINUITY_ELEMENTS)';

DROP TYPE IF EXISTS "public"."world_layer_type";
CREATE TYPE "public"."world_layer_type" AS ENUM ('primary', 'flashback', 'dream', 'extradiegetic');

-- Table Definition
CREATE TABLE "public"."chunk_metadata" (
    "id" int8 NOT NULL,
    "chunk_id" int8 NOT NULL,
    "season" int4,
    "episode" int4,
    "scene" int4,
    "world_layer" "public"."world_layer_type",
    "time_delta" interval,
    "place" int8,
    "atmosphere" varchar(255),
    "arc_position" varchar(50),
    "direction" jsonb,
    "magnitude" varchar(50),
    "character_elements" jsonb,
    "perspective" jsonb,
    "interactions" jsonb,
    "dialogue_analysis" jsonb,
    "emotional_tone" jsonb,
    "narrative_function" jsonb,
    "narrative_techniques" jsonb,
    "thematic_elements" jsonb,
    "causality" jsonb,
    "continuity_markers" jsonb,
    "metadata_version" varchar(20),
    "generation_date" timestamp,
    "slug" varchar(10),
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."chunk_metadata"."chunk_id" IS 'Foreign key reference to narrative_chunks.id';
COMMENT ON COLUMN "public"."chunk_metadata"."season" IS 'Season number of the episode';
COMMENT ON COLUMN "public"."chunk_metadata"."episode" IS 'Episode number within the season';
COMMENT ON COLUMN "public"."chunk_metadata"."scene" IS 'Scene number within the episode';
COMMENT ON COLUMN "public"."chunk_metadata"."world_layer" IS 'Narrative layer (e.g. primary, secondary)';
COMMENT ON COLUMN "public"."chunk_metadata"."time_delta" IS 'Time elapsed since previous scene';
COMMENT ON COLUMN "public"."chunk_metadata"."place" IS 'Location identifier where scene occurs';
COMMENT ON COLUMN "public"."chunk_metadata"."slug" IS 'Human-readable identifier (e.g. S03E14_014)';

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS narrative_chunks_id_seq;

-- Table Definition
CREATE TABLE "public"."narrative_chunks" (
    "id" int8 NOT NULL DEFAULT nextval('narrative_chunks_id_seq'::regclass),
    "raw_text" text NOT NULL,
    "created_at" timestamptz DEFAULT now(),
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."narrative_chunks"."id" IS 'Unique identifier for each narrative chunk';
COMMENT ON COLUMN "public"."narrative_chunks"."raw_text" IS 'The actual narrative content with scene breaks and markdown formatting';
COMMENT ON COLUMN "public"."narrative_chunks"."created_at" IS 'Timestamp when the chunk was added to the database';

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS characters_id_seq;

-- Table Definition
CREATE TABLE "public"."characters" (
    "id" int8 NOT NULL DEFAULT nextval('characters_id_seq'::regclass),
    "name" varchar(50) NOT NULL,
    "summary" text,
    "appearance" text,
    "background" text DEFAULT 'unknown'::text,
    "personality" text,
    "emotional_state" text,
    "current_activity" text,
    "current_location" text,
    "extra_data" jsonb,
    "created_at" timestamptz NOT NULL DEFAULT now(),
    "updated_at" timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."characters"."id" IS 'Unique character identifier';
COMMENT ON COLUMN "public"."characters"."name" IS 'Character name';
COMMENT ON COLUMN "public"."characters"."summary" IS 'Brief character overview';
COMMENT ON COLUMN "public"."characters"."appearance" IS 'Physical description of the character';
COMMENT ON COLUMN "public"."characters"."background" IS 'Character history and backstory';
COMMENT ON COLUMN "public"."characters"."personality" IS 'Personality traits and behavioral patterns';
COMMENT ON COLUMN "public"."characters"."emotional_state" IS 'Current emotional condition';
COMMENT ON COLUMN "public"."characters"."current_activity" IS 'What the character is doing now';
COMMENT ON COLUMN "public"."characters"."current_location" IS 'Where the character is currently located';
COMMENT ON COLUMN "public"."characters"."extra_data" IS 'Additional flexible data (allies, skills, enemies, signature tech, etc.)';

DROP TYPE IF EXISTS "public"."place_reference_type";
CREATE TYPE "public"."place_reference_type" AS ENUM ('setting', 'mentioned', 'transit');

-- Table Definition
CREATE TABLE "public"."place_chunk_references" (
    "place_id" int8 NOT NULL,
    "chunk_id" int8 NOT NULL,
    "reference_type" "public"."place_reference_type" NOT NULL,
    "evidence" text,
    PRIMARY KEY ("place_id","chunk_id","reference_type")
);

-- Column Comment
COMMENT ON COLUMN "public"."place_chunk_references"."place_id" IS 'Foreign key to places.id - the location where the scene takes place or that is referenced';
COMMENT ON COLUMN "public"."place_chunk_references"."chunk_id" IS 'Foreign key to narrative_chunks.id - the chunk occurring at or referencing this place';

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS zones_id_seq;

-- Table Definition
CREATE TABLE "public"."zones" (
    "id" int8 NOT NULL DEFAULT nextval('zones_id_seq'::regclass),
    "name" varchar(50) NOT NULL,
    "summary" varchar(500),
    "boundary" geometry(MultiPolygon,4326),
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."zones"."id" IS 'Unique zone identifier';
COMMENT ON COLUMN "public"."zones"."name" IS 'Zone name (max 50 chars) - e.g. Downtown, Industrial District, The Wastes';
COMMENT ON COLUMN "public"."zones"."summary" IS 'Brief zone description (max 500 chars) - atmosphere, characteristics, notable features';
COMMENT ON COLUMN "public"."zones"."boundary" IS 'Geographic boundary polygon using PostGIS MultiPolygon geometry (SRID 4326/WGS84)';

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS chunk_embeddings_1536d_id_seq;

-- Table Definition
CREATE TABLE "public"."chunk_embeddings_1536d" (
    "id" int4 NOT NULL DEFAULT nextval('chunk_embeddings_1536d_id_seq'::regclass),
    "chunk_id" int8 NOT NULL,
    "model" varchar(255) NOT NULL,
    "embedding" vector NOT NULL,
    "created_at" timestamptz DEFAULT now(),
    PRIMARY KEY ("id")
);

-- Table Definition
CREATE TABLE "public"."factions" (
    "id" int8 NOT NULL,
    "name" varchar(255) NOT NULL,
    "summary" text,
    "ideology" text,
    "history" text,
    "current_activity" text,
    "hidden_agenda" text,
    "territory" text,
    "primary_location" int8,
    "power_level" numeric(3,2) DEFAULT 0.5,
    "resources" text,
    "extra_data" jsonb,
    "created_at" timestamptz NOT NULL DEFAULT now(),
    "updated_at" timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."factions"."id" IS 'Unique faction identifier';
COMMENT ON COLUMN "public"."factions"."name" IS 'Faction name';
COMMENT ON COLUMN "public"."factions"."summary" IS 'Brief description of the faction';
COMMENT ON COLUMN "public"."factions"."ideology" IS 'Core beliefs and values';
COMMENT ON COLUMN "public"."factions"."primary_location" IS 'Foreign key to places.id - main headquarters or base of operations';
COMMENT ON COLUMN "public"."factions"."extra_data" IS 'JSONB storage for faction-specific data: leadership structure, notable members, assets, weaknesses, recruitment methods, symbols, motto, etc.';
COMMENT ON COLUMN "public"."factions"."created_at" IS 'Timestamp when faction record was created';
COMMENT ON COLUMN "public"."factions"."updated_at" IS 'Timestamp of last faction information update';

-- Table Definition
CREATE TABLE "public"."character_aliases" (
    "character_id" int8 NOT NULL,
    "alias" text NOT NULL,
    PRIMARY KEY ("character_id","alias")
);

-- Column Comment
COMMENT ON COLUMN "public"."character_aliases"."character_id" IS 'Foreign key to characters.id - the canonical character this alias refers to';
COMMENT ON COLUMN "public"."character_aliases"."alias" IS 'Alternative name, nickname, codename, or other reference used for the character';

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS items_id_seq;

-- Table Definition
CREATE TABLE "public"."items" (
    "id" int8 NOT NULL DEFAULT nextval('items_id_seq'::regclass),
    "type" varchar(100) NOT NULL,
    "quantity" int4 NOT NULL DEFAULT 1,
    "summary" varchar(500) NOT NULL,
    "name" varchar(50) NOT NULL,
    "owner_id" int8,
    "history" text,
    "status" varchar(50) NOT NULL DEFAULT 'functional'::character varying,
    "extra_data" jsonb,
    "created_at" timestamptz NOT NULL DEFAULT now(),
    "updated_at" timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."items"."id" IS 'Unique item identifier';
COMMENT ON COLUMN "public"."items"."type" IS 'Category or classification of item (weapon, data, artifact, etc.)';
COMMENT ON COLUMN "public"."items"."quantity" IS 'Number of units if stackable/countable';
COMMENT ON COLUMN "public"."items"."summary" IS 'Brief description of the item';
COMMENT ON COLUMN "public"."items"."name" IS 'Item name or designation';
COMMENT ON COLUMN "public"."items"."owner_id" IS 'Foreign key to characters.id - current owner/possessor';
COMMENT ON COLUMN "public"."items"."history" IS 'Provenance and past ownership/usage of the item';
COMMENT ON COLUMN "public"."items"."status" IS 'Current condition (intact, damaged, active, depleted, etc.)';
COMMENT ON COLUMN "public"."items"."extra_data" IS 'JSONB for item-specific properties, abilities, or metadata';
COMMENT ON COLUMN "public"."items"."created_at" IS 'When item record was created';
COMMENT ON COLUMN "public"."items"."updated_at" IS 'Last modification to item record';

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS places_id_seq;
DROP TYPE IF EXISTS "public"."place_type";
CREATE TYPE "public"."place_type" AS ENUM ('fixed_location', 'vehicle', 'other');

-- Table Definition
CREATE TABLE "public"."places" (
    "id" int8 NOT NULL DEFAULT nextval('places_id_seq'::regclass),
    "name" varchar(50) NOT NULL,
    "type" "public"."place_type" NOT NULL,
    "zone" int8 NOT NULL,
    "summary" text,
    "inhabitants" _text,
    "history" text,
    "current_status" text,
    "secrets" text,
    "extra_data" jsonb,
    "created_at" timestamptz NOT NULL DEFAULT now(),
    "updated_at" timestamptz NOT NULL DEFAULT now(),
    "coordinates" geography(PointZM,4326),
    PRIMARY KEY ("id")
);

-- Column Comment
COMMENT ON COLUMN "public"."places"."id" IS 'Unique place identifier';
COMMENT ON COLUMN "public"."places"."name" IS 'Location name';
COMMENT ON COLUMN "public"."places"."type" IS 'Type of location (facility, vehicle, district, etc.)';
COMMENT ON COLUMN "public"."places"."zone" IS 'Zone identifier for geographical grouping';
COMMENT ON COLUMN "public"."places"."summary" IS 'Detailed location description';
COMMENT ON COLUMN "public"."places"."inhabitants" IS 'Who lives or works at this location';
COMMENT ON COLUMN "public"."places"."history" IS 'Historical significance of the location';
COMMENT ON COLUMN "public"."places"."current_status" IS 'Present condition and activity';
COMMENT ON COLUMN "public"."places"."secrets" IS 'Hidden information about the location';
COMMENT ON COLUMN "public"."places"."extra_data" IS 'Flexible JSONB storage for additional location attributes like notable features, resources, dangers, connections to other places, environmental conditions, or narrative significance';
COMMENT ON COLUMN "public"."places"."coordinates" IS 'Spatial coordinates for mapping';

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS chunk_embeddings_1024d_id_seq;

-- Table Definition
CREATE TABLE "public"."chunk_embeddings_1024d" (
    "id" int4 NOT NULL DEFAULT nextval('chunk_embeddings_1024d_id_seq'::regclass),
    "chunk_id" int8 NOT NULL,
    "model" varchar(255) NOT NULL,
    "embedding" vector NOT NULL,
    "created_at" timestamptz DEFAULT now(),
    PRIMARY KEY ("id")
);

DROP TYPE IF EXISTS "public"."reference_type";
CREATE TYPE "public"."reference_type" AS ENUM ('present', 'mentioned');

-- Table Definition
CREATE TABLE "public"."chunk_character_references" (
    "chunk_id" int8 NOT NULL,
    "character_id" int8 NOT NULL,
    "reference" "public"."reference_type",
    PRIMARY KEY ("chunk_id","character_id")
);

-- Column Comment
COMMENT ON COLUMN "public"."chunk_character_references"."chunk_id" IS 'Foreign key to narrative_chunks.id - the chunk containing the reference';
COMMENT ON COLUMN "public"."chunk_character_references"."character_id" IS 'Foreign key to characters.id - the character being referenced';
COMMENT ON COLUMN "public"."chunk_character_references"."reference" IS 'Type of reference: present (character is in scene), mentioned (character discussed but not present), implied (indirect reference)';

-- Table Definition
CREATE TABLE "public"."chunk_faction_references" (
    "chunk_id" int8 NOT NULL,
    "faction_id" int8 NOT NULL,
    PRIMARY KEY ("chunk_id","faction_id")
);

-- Column Comment
COMMENT ON COLUMN "public"."chunk_faction_references"."chunk_id" IS 'Foreign key to narrative_chunks.id - the chunk referencing the faction';
COMMENT ON COLUMN "public"."chunk_faction_references"."faction_id" IS 'Foreign key to factions.id - the faction being referenced';

DROP TYPE IF EXISTS "public"."faction_relationship_type";
CREATE TYPE "public"."faction_relationship_type" AS ENUM ('alliance', 'trade_partners', 'truce', 'vassalage', 'coalition', 'war', 'rivalry', 'ideological_enemy', 'competitor', 'splinter', 'unknown', 'shadow_partner');

-- Table Definition
CREATE TABLE "public"."faction_relationships" (
    "faction1_id" int8 NOT NULL,
    "faction2_id" int8 NOT NULL,
    "relationship_type" "public"."faction_relationship_type" NOT NULL,
    "current_status" text,
    "history" text,
    "extra_data" jsonb,
    "created_at" timestamptz DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamptz DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY ("faction1_id","faction2_id")
);

-- Column Comment
COMMENT ON COLUMN "public"."faction_relationships"."faction1_id" IS 'Foreign key to factions.id - first faction in relationship';
COMMENT ON COLUMN "public"."faction_relationships"."faction2_id" IS 'Foreign key to factions.id - second faction in relationship';
COMMENT ON COLUMN "public"."faction_relationships"."relationship_type" IS 'Nature of relationship (allied, hostile, neutral, trade_partner, etc.)';
COMMENT ON COLUMN "public"."faction_relationships"."current_status" IS 'Present state of the relationship and recent developments';
COMMENT ON COLUMN "public"."faction_relationships"."history" IS 'Historical context and evolution of the faction relationship';
COMMENT ON COLUMN "public"."faction_relationships"."extra_data" IS '{
  "relationship_dynamics": {
    "power_balance": "Which faction holds more leverage and why",
    "interaction": "Where and how they typically encounter each other",
    "trust_level": "Scale of suspicion to confidence (0.0-1.0)",
    "volatility": "How stable or explosive this relationship is",
    "public_perception": "How their relationship is viewed by outsiders"
  },
  "conflict": {
    "disputes": "Active disagreements or competitions",
    "grievances": "Historical wounds (if any)",
    "flashpoints": "What could escalate tensions",
    "economic_friction": "Trade disputes, resource competition, etc",
    "espionage": "Intelligence operations undertaken against each other (if any)"
  },
  "cooperation": {
    "shared_interests": "If/where goals align",
    "joint_activities": "If/how they work together",
    "mutual_threats": "Common enemies they face",
    "economic_exchange": "Trade, resources, or services shared"
  },
  "future_scenarios": {
    "likely_evolution": "Where this relationship is heading",
    "breaking_points": "Events that could fundamentally change things",
    "narrative_potential": "Story opportunities in this relationship"
  },
  "hidden_layers": {
    "secrets": "Unknown aspects of their relationship (if any)",
    "contingencies": "Backup plans either might have"
  }
}';
COMMENT ON COLUMN "public"."faction_relationships"."created_at" IS 'When relationship record was created';
COMMENT ON COLUMN "public"."faction_relationships"."updated_at" IS 'Last modification to relationship record';



-- Comments
COMMENT ON TABLE "public"."seasons" IS 'Major narrative arcs or chapters that group episodes into thematic segments';
ALTER TABLE "public"."global_variables" ADD FOREIGN KEY ("user_character") REFERENCES "public"."characters"("id");


-- Comments
COMMENT ON TABLE "public"."global_variables" IS 'System-wide singleton configuration storing base timestamp and active user character for the narrative system';
ALTER TABLE "public"."character_relationships" ADD FOREIGN KEY ("character2_id") REFERENCES "public"."characters"("id");
ALTER TABLE "public"."character_relationships" ADD FOREIGN KEY ("character1_id") REFERENCES "public"."characters"("id");


-- Comments
COMMENT ON TABLE "public"."character_relationships" IS 'Tracks bidirectional relationships between characters with emotional depth';


-- Indices
CREATE INDEX idx_character_relationships_character1 ON public.character_relationships USING btree (character1_id);
CREATE INDEX idx_character_relationships_character2 ON public.character_relationships USING btree (character2_id);
CREATE INDEX idx_character_relationships_type ON public.character_relationships USING btree (relationship_type);
ALTER TABLE "public"."character_psychology" ADD FOREIGN KEY ("character_id") REFERENCES "public"."characters"("id");


-- Comments
COMMENT ON TABLE "public"."character_psychology" IS 'Deep psychological profiles analyzing character motivations, trauma, coping mechanisms, and developmental arcs';
ALTER TABLE "public"."episodes" ADD FOREIGN KEY ("season") REFERENCES "public"."seasons"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Comments
COMMENT ON TABLE "public"."episodes" IS 'Episode-level summaries and metadata for story organization';
ALTER TABLE "public"."chunk_metadata" ADD FOREIGN KEY ("place") REFERENCES "public"."places"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "public"."chunk_metadata" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Comments
COMMENT ON TABLE "public"."chunk_metadata" IS 'Structured metadata about each narrative chunk including temporal and spatial information';


-- Indices
CREATE UNIQUE INDEX chunk_metadata_new_pkey ON public.chunk_metadata USING btree (id);
CREATE UNIQUE INDEX chunk_metadata_chunk_id_key ON public.chunk_metadata USING btree (chunk_id);
CREATE INDEX idx_chunk_metadata_scene ON public.chunk_metadata USING btree (scene);
CREATE INDEX idx_chunk_metadata_season_episode_scene ON public.chunk_metadata USING btree (season, episode, scene);
CREATE UNIQUE INDEX unique_slug ON public.chunk_metadata USING btree (slug);


-- Comments
COMMENT ON TABLE "public"."narrative_chunks" IS 'Stores raw narrative text content forming the foundation of the story';


-- Indices
CREATE UNIQUE INDEX narrative_chunks_new_pkey ON public.narrative_chunks USING btree (id);
CREATE UNIQUE INDEX narrative_chunks_id_key ON public.narrative_chunks USING btree (id);
CREATE INDEX narrative_chunks_text_idx ON public.narrative_chunks USING gin (to_tsvector('english'::regconfig, raw_text));
CREATE INDEX narrative_chunks_text_search_idx ON public.narrative_chunks USING gin (to_tsvector('english'::regconfig, raw_text));


-- Comments
COMMENT ON TABLE "public"."characters" IS 'Comprehensive character profiles including appearance, personality, and current status';


-- Indices
CREATE UNIQUE INDEX characters_name_key ON public.characters USING btree (name);
ALTER TABLE "public"."place_chunk_references" ADD FOREIGN KEY ("place_id") REFERENCES "public"."places"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."place_chunk_references" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Comments
COMMENT ON TABLE "public"."place_chunk_references" IS 'Junction table associating narrative chunks with locations where scenes occur or are referenced';


-- Comments
COMMENT ON TABLE "public"."zones" IS 'Geographical regions with spatial boundaries that organize locations in the game world';


-- Indices
CREATE INDEX idx_zones_boundary ON public.zones USING gist (boundary);
ALTER TABLE "public"."chunk_embeddings_1536d" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE;


-- Comments
COMMENT ON TABLE "public"."chunk_embeddings_1536d" IS 'Vector embeddings (1536 dimensions) for semantic search - highest accuracy';


-- Indices
CREATE UNIQUE INDEX unique_chunk_embeddings_1536d_chunk_model ON public.chunk_embeddings_1536d USING btree (chunk_id, model);
CREATE INDEX chunk_embeddings_1536d_chunk_id_idx ON public.chunk_embeddings_1536d USING btree (chunk_id);
CREATE INDEX chunk_embeddings_1536d_model_idx ON public.chunk_embeddings_1536d USING btree (model);
CREATE INDEX chunk_embeddings_1536d_hnsw_idx ON public.chunk_embeddings_1536d USING hnsw (embedding vector_cosine_ops) WITH (ef_construction='64', m='16');
ALTER TABLE "public"."factions" ADD FOREIGN KEY ("primary_location") REFERENCES "public"."places"("id");


-- Comments
COMMENT ON TABLE "public"."factions" IS 'Organizations, groups, and collective entities in the narrative';


-- Indices
CREATE UNIQUE INDEX factions_name_key ON public.factions USING btree (name);
ALTER TABLE "public"."character_aliases" ADD FOREIGN KEY ("character_id") REFERENCES "public"."characters"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Comments
COMMENT ON TABLE "public"."character_aliases" IS 'Alternative names, nicknames, and aliases used to refer to characters throughout the narrative';


-- Indices
CREATE INDEX idx_character_alias_lookup ON public.character_aliases USING btree (alias);
ALTER TABLE "public"."items" ADD FOREIGN KEY ("owner_id") REFERENCES "public"."characters"("id") ON DELETE SET NULL;


-- Comments
COMMENT ON TABLE "public"."items" IS 'Physical and digital objects, artifacts, weapons, and significant items tracked in the narrative';


-- Indices
CREATE UNIQUE INDEX items_name_key ON public.items USING btree (name);
ALTER TABLE "public"."places" ADD FOREIGN KEY ("zone") REFERENCES "public"."zones"("id") ON DELETE SET NULL ON UPDATE CASCADE;


-- Comments
COMMENT ON TABLE "public"."places" IS 'Location database with detailed descriptions and current status';


-- Indices
CREATE UNIQUE INDEX places_name_key ON public.places USING btree (name);
CREATE INDEX idx_places_inhabitants ON public.places USING gin (inhabitants);
CREATE INDEX idx_places_coordinates ON public.places USING gist (coordinates);
ALTER TABLE "public"."chunk_embeddings_1024d" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE;


-- Comments
COMMENT ON TABLE "public"."chunk_embeddings_1024d" IS 'Vector embeddings (1024 dimensions) for semantic search - balanced size/performance';


-- Indices
CREATE UNIQUE INDEX unique_chunk_embeddings_1024d_chunk_model ON public.chunk_embeddings_1024d USING btree (chunk_id, model);
CREATE INDEX chunk_embeddings_1024d_chunk_id_idx ON public.chunk_embeddings_1024d USING btree (chunk_id);
CREATE INDEX chunk_embeddings_1024d_model_idx ON public.chunk_embeddings_1024d USING btree (model);
CREATE INDEX chunk_embeddings_1024d_hnsw_idx ON public.chunk_embeddings_1024d USING hnsw (embedding vector_cosine_ops) WITH (ef_construction='64', m='16');
ALTER TABLE "public"."chunk_character_references" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."chunk_character_references" ADD FOREIGN KEY ("character_id") REFERENCES "public"."characters"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Comments
COMMENT ON TABLE "public"."chunk_character_references" IS 'Junction table linking narrative chunks to characters, tracking how characters appear in or are referenced by the narrative';
ALTER TABLE "public"."chunk_faction_references" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."chunk_faction_references" ADD FOREIGN KEY ("faction_id") REFERENCES "public"."factions"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Comments
COMMENT ON TABLE "public"."chunk_faction_references" IS 'Simple junction table linking narrative chunks to factions mentioned or involved';
ALTER TABLE "public"."faction_relationships" ADD FOREIGN KEY ("faction2_id") REFERENCES "public"."factions"("id");
ALTER TABLE "public"."faction_relationships" ADD FOREIGN KEY ("faction1_id") REFERENCES "public"."factions"("id");


-- Comments
COMMENT ON TABLE "public"."faction_relationships" IS 'Tracks diplomatic, hostile, or neutral relationships between factions';

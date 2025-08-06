-- -------------------------------------------------------------
-- TablePlus 6.6.8(632)
--
-- https://tableplus.com/
--
-- Database: NEXUS
-- Generation Time: 2025-08-06 10:48:10.4370
-- -------------------------------------------------------------




































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































-- Table Definition
CREATE TABLE "public"."seasons" (
    "id" int8 NOT NULL,
    "summary" jsonb,
    PRIMARY KEY ("id")
);

-- Table Definition
CREATE TABLE "public"."global_variables" (
    "id" bool NOT NULL DEFAULT true,
    "base_timestamp" timestamptz NOT NULL,
    "user_character" int8,
    PRIMARY KEY ("id")
);

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

-- Table Definition
CREATE TABLE "public"."episodes" (
    "season" int8 NOT NULL,
    "episode" int8 NOT NULL,
    "chunk_span" int8range,
    "summary" jsonb,
    "temp_span" int8range,
    PRIMARY KEY ("season","episode")
);

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
    "characters" _text,
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

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS narrative_chunks_id_seq;

-- Table Definition
CREATE TABLE "public"."narrative_chunks" (
    "id" int8 NOT NULL DEFAULT nextval('narrative_chunks_id_seq'::regclass),
    "raw_text" text NOT NULL,
    "created_at" timestamptz DEFAULT now(),
    PRIMARY KEY ("id")
);

-- Table Definition
CREATE TABLE "public"."events" (
    "id" int8 NOT NULL,
    "chunk_id" int8,
    "title" varchar(100) NOT NULL,
    "description" text,
    "cause" text,
    "consequences" text,
    "characters_involved" _text,
    "status" varchar(50) NOT NULL DEFAULT 'ongoing'::character varying,
    "created_at" timestamptz NOT NULL DEFAULT now(),
    "updated_at" timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY ("id")
);

DROP TYPE IF EXISTS "public"."threat_lifecycle_type";
CREATE TYPE "public"."threat_lifecycle_type" AS ENUM ('inception', 'gestation', 'manifestation', 'escalation', 'culmination', 'resolution', 'aftermath');
DROP TYPE IF EXISTS "public"."threat_lifecycle_type";
CREATE TYPE "public"."threat_lifecycle_type" AS ENUM ('inception', 'gestation', 'manifestation', 'escalation', 'culmination', 'resolution', 'aftermath');

-- Table Definition
CREATE TABLE "public"."threat_transitions" (
    "id" int8 NOT NULL,
    "threat_id" int8 NOT NULL,
    "from_stage" "public"."threat_lifecycle_type" NOT NULL,
    "to_stage" "public"."threat_lifecycle_type" NOT NULL,
    "transition_reason" text,
    "chunk_id" int8,
    "transition_date" timestamptz NOT NULL DEFAULT now(),
    "notes" text,
    PRIMARY KEY ("id")
);

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS chunk_embeddings_0384d_id_seq;

-- Table Definition
CREATE TABLE "public"."chunk_embeddings_0384d" (
    "id" int4 NOT NULL DEFAULT nextval('chunk_embeddings_0384d_id_seq'::regclass),
    "chunk_id" int8 NOT NULL,
    "model" varchar(255) NOT NULL,
    "embedding" vector NOT NULL,
    "created_at" timestamptz DEFAULT now(),
    PRIMARY KEY ("id")
);

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
COMMENT ON COLUMN "public"."characters"."current_activity" IS 'establishes and tracks persistent independent behavior when a character is off-screen';

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

-- Table Definition
CREATE TABLE "public"."spatial_ref_sys" (
    "srid" int4 NOT NULL CHECK ((srid > 0) AND (srid <= 998999)),
    "auth_name" varchar(256),
    "auth_srid" int4,
    "srtext" varchar(2048),
    "proj4text" varchar(2048),
    PRIMARY KEY ("srid")
);

-- Table Definition
CREATE TABLE "public"."character_aliases" (
    "character_id" int8 NOT NULL,
    "alias" text NOT NULL,
    PRIMARY KEY ("character_id","alias")
);

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS ai_notebook_id_seq;
DROP TYPE IF EXISTS "public"."agent_type";
CREATE TYPE "public"."agent_type" AS ENUM ('LOGON', 'LORE', 'GAIA', 'PSYCHE', 'MEMNON', 'MAESTRO', 'NEMESIS');
DROP TYPE IF EXISTS "public"."log_level_type";
CREATE TYPE "public"."log_level_type" AS ENUM ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL');

-- Table Definition
CREATE TABLE "public"."ai_notebook" (
    "id" int8 NOT NULL DEFAULT nextval('ai_notebook_id_seq'::regclass),
    "timestamp" timestamptz NOT NULL DEFAULT now(),
    "log_entry" text NOT NULL,
    "agent" "public"."agent_type" NOT NULL,
    "level" "public"."log_level_type" NOT NULL DEFAULT 'INFO'::log_level_type,
    PRIMARY KEY ("id")
);

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

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS threats_id_seq;
DROP TYPE IF EXISTS "public"."threat_domain_type";
CREATE TYPE "public"."threat_domain_type" AS ENUM ('physical', 'psychological', 'social', 'environmental');
DROP TYPE IF EXISTS "public"."threat_lifecycle_type";
CREATE TYPE "public"."threat_lifecycle_type" AS ENUM ('inception', 'gestation', 'manifestation', 'escalation', 'culmination', 'resolution', 'aftermath');
DROP TYPE IF EXISTS "public"."entity_type";
CREATE TYPE "public"."entity_type" AS ENUM ('character', 'faction', 'place', 'item');

-- Table Definition
CREATE TABLE "public"."threats" (
    "id" int8 NOT NULL DEFAULT nextval('threats_id_seq'::regclass),
    "name" varchar(255) NOT NULL,
    "description" text,
    "domain" "public"."threat_domain_type" NOT NULL,
    "lifecycle_stage" "public"."threat_lifecycle_type" NOT NULL DEFAULT 'inception'::threat_lifecycle_type,
    "target_entity_type" "public"."entity_type" NOT NULL,
    "target_entity_id" varchar(50) NOT NULL,
    "severity" numeric(3,2) NOT NULL DEFAULT 0.5,
    "is_active" bool NOT NULL DEFAULT true,
    "extra_data" jsonb,
    "created_at" timestamptz NOT NULL DEFAULT now(),
    "updated_at" timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY ("id")
);

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
COMMENT ON COLUMN "public"."places"."inhabitants" IS 'array of named characters';
COMMENT ON COLUMN "public"."places"."history" IS 'rich backstory with specific events';
COMMENT ON COLUMN "public"."places"."current_status" IS 'dynamic state elements that change over time';
COMMENT ON COLUMN "public"."places"."secrets" IS 'hidden elements, secrets, or narrative hooks';

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

-- Table Definition
CREATE TABLE "public"."chunk_faction_references" (
    "chunk_id" int8 NOT NULL,
    "faction_id" int8 NOT NULL,
    PRIMARY KEY ("chunk_id","faction_id")
);

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

DROP TYPE IF EXISTS "public"."faction_member_role";
CREATE TYPE "public"."faction_member_role" AS ENUM ('leader', 'employee', 'member', 'target', 'informant', 'sympathizer', 'defector', 'exile', 'insider_threat');

-- Table Definition
CREATE TABLE "public"."faction_character_relationships" (
    "faction_id" int8 NOT NULL,
    "character_id" int8 NOT NULL,
    "role" "public"."faction_member_role" NOT NULL,
    "current_status" text,
    "history" text,
    "public_knowledge" bool DEFAULT true,
    "extra_data" jsonb,
    "created_at" timestamptz DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamptz DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY ("faction_id","character_id")
);

-- Column Comment
COMMENT ON COLUMN "public"."faction_character_relationships"."extra_data" IS '{
  "connection_nature": {
    "origin_story": "How this relationship began",
    "current_dynamics": "The present state of their interaction",
    "key_events": "Significant moments that shaped this relationship",
    "interaction_frequency": "How often they engage, if at all"
  },
  "faction_perspective": {
    "value_assessment": "What the faction thinks this person is worth",
    "strategic_importance": "Their role in faction plans",
    "handling_approach": "How the faction deals with them",
    "known_intelligence": "What the faction knows about them",
    "desired_outcome": "What the faction wants from this relationship"
  },
  "character_perspective": {
    "attitude": "How they view the faction",
    "personal_stakes": "What they stand to gain or lose",
    "constraints": "What limits their choices",
    "options": "Potential moves they could make"
  },
  "operational_details": {
    "resources_involved": "Assets, money, or efforts directed at/from them",
    "active_operations": "Ongoing activities if any",
    "contingency_plans": "Backup strategies",
    "success_metrics": "How the faction measures this relationship"
  },
  "narrative_threads": {
    "unresolved_tensions": "What remains unsettled",
    "potential_developments": "Where this could go",
    "connected_relationships": "Others affected by this dynamic",
    "secrets": "Hidden aspects from either side"
  }
}';

CREATE VIEW "public"."chunk_faction_references_view" AS ;
CREATE VIEW "public"."chunk_character_references_view" AS ;
CREATE VIEW "public"."character_present_view" AS ;
CREATE VIEW "public"."place_chunk_references_view" AS ;
CREATE VIEW "public"."character_reference_view" AS ;
CREATE VIEW "public"."enum_types_view" AS ;
CREATE VIEW "public"."character_relationship_pairs" AS ;
CREATE VIEW "public"."character_relationship_summary" AS ;
CREATE VIEW "public"."geometry_columns" AS ;
CREATE VIEW "public"."geography_columns" AS ;
CREATE VIEW "public"."character_aliases_view" AS ;
CREATE VIEW "public"."chunk_places_view" AS ;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
;
ALTER TABLE "public"."global_variables" ADD FOREIGN KEY ("user_character") REFERENCES "public"."characters"("id");
ALTER TABLE "public"."character_relationships" ADD FOREIGN KEY ("character2_id") REFERENCES "public"."characters"("id");
ALTER TABLE "public"."character_relationships" ADD FOREIGN KEY ("character1_id") REFERENCES "public"."characters"("id");


-- Indices
CREATE INDEX idx_character_relationships_character1 ON public.character_relationships USING btree (character1_id);
CREATE INDEX idx_character_relationships_character2 ON public.character_relationships USING btree (character2_id);
CREATE INDEX idx_character_relationships_type ON public.character_relationships USING btree (relationship_type);
ALTER TABLE "public"."character_psychology" ADD FOREIGN KEY ("character_id") REFERENCES "public"."characters"("id");
ALTER TABLE "public"."episodes" ADD FOREIGN KEY ("season") REFERENCES "public"."seasons"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."chunk_metadata" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."chunk_metadata" ADD FOREIGN KEY ("place") REFERENCES "public"."places"("id") ON DELETE SET NULL ON UPDATE CASCADE;


-- Indices
CREATE UNIQUE INDEX chunk_metadata_new_pkey ON public.chunk_metadata USING btree (id);
CREATE UNIQUE INDEX chunk_metadata_chunk_id_key ON public.chunk_metadata USING btree (chunk_id);
CREATE INDEX idx_chunk_metadata_scene ON public.chunk_metadata USING btree (scene);
CREATE INDEX idx_chunk_metadata_season_episode_scene ON public.chunk_metadata USING btree (season, episode, scene);
CREATE UNIQUE INDEX unique_slug ON public.chunk_metadata USING btree (slug);


-- Indices
CREATE UNIQUE INDEX narrative_chunks_new_pkey ON public.narrative_chunks USING btree (id);
CREATE UNIQUE INDEX narrative_chunks_id_key ON public.narrative_chunks USING btree (id);
CREATE INDEX narrative_chunks_text_idx ON public.narrative_chunks USING gin (to_tsvector('english'::regconfig, raw_text));
CREATE INDEX narrative_chunks_text_search_idx ON public.narrative_chunks USING gin (to_tsvector('english'::regconfig, raw_text));
ALTER TABLE "public"."events" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE SET NULL ON UPDATE CASCADE;


-- Indices
CREATE UNIQUE INDEX events_new_pkey ON public.events USING btree (id);
CREATE INDEX idx_events_chars_involved ON public.events USING gin (characters_involved);
ALTER TABLE "public"."threat_transitions" ADD FOREIGN KEY ("threat_id") REFERENCES "public"."threats"("id") ON DELETE CASCADE;
ALTER TABLE "public"."threat_transitions" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE SET NULL ON UPDATE CASCADE;


-- Indices
CREATE UNIQUE INDEX threat_transitions_new_pkey ON public.threat_transitions USING btree (id);
ALTER TABLE "public"."chunk_embeddings_0384d" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE;


-- Indices
CREATE UNIQUE INDEX unique_chunk_embeddings_0384d_chunk_model ON public.chunk_embeddings_0384d USING btree (chunk_id, model);
CREATE INDEX chunk_embeddings_0384d_chunk_id_idx ON public.chunk_embeddings_0384d USING btree (chunk_id);
CREATE INDEX chunk_embeddings_0384d_model_idx ON public.chunk_embeddings_0384d USING btree (model);
CREATE INDEX chunk_embeddings_0384d_hnsw_idx ON public.chunk_embeddings_0384d USING hnsw (embedding vector_cosine_ops) WITH (ef_construction='64', m='16');


-- Comments
COMMENT ON TABLE "public"."characters" IS 'An enriched ''characters'' table that stores specialized columns for depth and personality. Non-character entities rely on entity_details/states.';


-- Indices
CREATE UNIQUE INDEX characters_name_key ON public.characters USING btree (name);
ALTER TABLE "public"."place_chunk_references" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."place_chunk_references" ADD FOREIGN KEY ("place_id") REFERENCES "public"."places"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Indices
CREATE INDEX idx_zones_boundary ON public.zones USING gist (boundary);
ALTER TABLE "public"."chunk_embeddings_1536d" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE;


-- Indices
CREATE UNIQUE INDEX unique_chunk_embeddings_1536d_chunk_model ON public.chunk_embeddings_1536d USING btree (chunk_id, model);
CREATE INDEX chunk_embeddings_1536d_chunk_id_idx ON public.chunk_embeddings_1536d USING btree (chunk_id);
CREATE INDEX chunk_embeddings_1536d_model_idx ON public.chunk_embeddings_1536d USING btree (model);
CREATE INDEX chunk_embeddings_1536d_hnsw_idx ON public.chunk_embeddings_1536d USING hnsw (embedding vector_cosine_ops) WITH (ef_construction='64', m='16');
ALTER TABLE "public"."factions" ADD FOREIGN KEY ("primary_location") REFERENCES "public"."places"("id");


-- Indices
CREATE UNIQUE INDEX factions_name_key ON public.factions USING btree (name);
ALTER TABLE "public"."character_aliases" ADD FOREIGN KEY ("character_id") REFERENCES "public"."characters"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Indices
CREATE INDEX idx_character_alias_lookup ON public.character_aliases USING btree (alias);


-- Comments
COMMENT ON TABLE "public"."ai_notebook" IS 'Stores log entries from any internal agent (LORE, GAIA, etc.) for debugging or historical review.';
ALTER TABLE "public"."items" ADD FOREIGN KEY ("owner_id") REFERENCES "public"."characters"("id") ON DELETE SET NULL;


-- Indices
CREATE UNIQUE INDEX items_name_key ON public.items USING btree (name);


-- Comments
COMMENT ON TABLE "public"."threats" IS 'Core record for an active threat in NEMESIS. Lifecycle stage tracks progression.';
ALTER TABLE "public"."places" ADD FOREIGN KEY ("zone") REFERENCES "public"."zones"("id") ON DELETE SET NULL ON UPDATE CASCADE;


-- Indices
CREATE UNIQUE INDEX places_name_key ON public.places USING btree (name);
CREATE INDEX idx_places_inhabitants ON public.places USING gin (inhabitants);
CREATE INDEX idx_places_coordinates ON public.places USING gist (coordinates);
ALTER TABLE "public"."chunk_embeddings_1024d" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE;


-- Indices
CREATE UNIQUE INDEX unique_chunk_embeddings_1024d_chunk_model ON public.chunk_embeddings_1024d USING btree (chunk_id, model);
CREATE INDEX chunk_embeddings_1024d_chunk_id_idx ON public.chunk_embeddings_1024d USING btree (chunk_id);
CREATE INDEX chunk_embeddings_1024d_model_idx ON public.chunk_embeddings_1024d USING btree (model);
CREATE INDEX chunk_embeddings_1024d_hnsw_idx ON public.chunk_embeddings_1024d USING hnsw (embedding vector_cosine_ops) WITH (ef_construction='64', m='16');
ALTER TABLE "public"."chunk_character_references" ADD FOREIGN KEY ("character_id") REFERENCES "public"."characters"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."chunk_character_references" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."chunk_faction_references" ADD FOREIGN KEY ("faction_id") REFERENCES "public"."factions"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."chunk_faction_references" ADD FOREIGN KEY ("chunk_id") REFERENCES "public"."narrative_chunks"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "public"."faction_relationships" ADD FOREIGN KEY ("faction2_id") REFERENCES "public"."factions"("id");
ALTER TABLE "public"."faction_relationships" ADD FOREIGN KEY ("faction1_id") REFERENCES "public"."factions"("id");
ALTER TABLE "public"."faction_character_relationships" ADD FOREIGN KEY ("faction_id") REFERENCES "public"."factions"("id");
ALTER TABLE "public"."faction_character_relationships" ADD FOREIGN KEY ("character_id") REFERENCES "public"."characters"("id");

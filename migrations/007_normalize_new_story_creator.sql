-- migrations/007_normalize_new_story_creator.sql
-- Description: Normalize new_story_creator table from JSONB blobs to typed columns
-- Date: 2026-01-13
-- Issue: Phase detection requires JSON introspection; normalized schema enables column nullability checks

-- ═══════════════════════════════════════════════════════════════════════════════
-- ENUMS
-- ═══════════════════════════════════════════════════════════════════════════════

-- Setting phase enums (all idempotent for re-runnable migrations)
DO $$ BEGIN
    CREATE TYPE genre AS ENUM (
        'fantasy', 'scifi', 'horror', 'mystery', 'historical',
        'contemporary', 'postapocalyptic', 'cyberpunk', 'steampunk',
        'urban_fantasy', 'space_opera', 'noir', 'thriller'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE tech_level AS ENUM (
        'stone_age', 'bronze_age', 'iron_age', 'medieval', 'renaissance',
        'industrial', 'modern', 'near_future', 'far_future', 'post_singularity'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE tone AS ENUM ('light', 'balanced', 'dark', 'grimdark');
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE geographic_scope AS ENUM (
        'local', 'regional', 'continental', 'global', 'interplanetary'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- Seed phase enums
DO $$ BEGIN
    CREATE TYPE seed_type AS ENUM (
        'in_medias_res', 'discovery', 'arrival', 'meeting',
        'crisis', 'mystery', 'opportunity', 'loss', 'threat'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE layer_type AS ENUM ('planet', 'dimension');
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- Character trait enum
DO $$ BEGIN
    CREATE TYPE trait AS ENUM (
        'allies', 'contacts', 'patron', 'dependents', 'status',
        'reputation', 'resources', 'domain', 'enemies', 'obligations'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- TABLE RECREATION
-- ═══════════════════════════════════════════════════════════════════════════════

-- Drop the old table (transient wizard cache - safe to drop)
DROP TABLE IF EXISTS assets.new_story_creator;

CREATE TABLE assets.new_story_creator (
    id bool NOT NULL DEFAULT true CHECK (id),
    thread_id text,
    target_slot int,

    -- ═══════════════════════════════════════════════════════════════
    -- SETTING PHASE
    -- ═══════════════════════════════════════════════════════════════
    setting_genre genre,
    setting_secondary_genres genre[],
    setting_world_name varchar(100),
    setting_time_period text,
    setting_tech_level tech_level,
    setting_magic_exists bool,
    setting_magic_description text,
    setting_political_structure text,
    setting_major_conflict text,
    setting_tone tone,
    setting_themes text[],
    setting_cultural_notes text,
    setting_language_notes text,
    setting_geographic_scope geographic_scope,
    setting_diegetic_artifact text,

    -- ═══════════════════════════════════════════════════════════════
    -- CHARACTER PHASE
    -- ═══════════════════════════════════════════════════════════════
    character_name varchar(50),
    character_archetype text,
    character_background text,
    character_appearance text,
    character_trait1 trait,
    character_trait2 trait,
    character_trait3 trait,
    wildcard_name varchar(50),
    wildcard_description text,

    -- ═══════════════════════════════════════════════════════════════
    -- SEED PHASE
    -- ═══════════════════════════════════════════════════════════════
    -- StorySeed core fields
    seed_type seed_type,
    seed_title varchar(100),
    seed_situation text,
    seed_hook text,
    seed_immediate_goal text,
    seed_stakes text,
    seed_tension_source text,
    seed_starting_location text,
    seed_weather text,
    seed_key_npcs text[],
    seed_initial_mystery text,
    seed_potential_allies text[],
    seed_potential_obstacles text[],
    seed_secrets text,

    -- LayerDefinition
    layer_name varchar(50),
    layer_type layer_type,
    layer_description text,

    -- ZoneDefinition
    zone_name varchar(50),
    zone_summary varchar(500),
    zone_boundary_description text,
    zone_approximate_area text,

    -- PlaceProfile (complex structure - keep as JSONB)
    initial_location jsonb,

    -- Temporal
    base_timestamp timestamptz,
    updated_at timestamptz DEFAULT now(),

    PRIMARY KEY (id),

    -- Ensure trait uniqueness within a row (when not null)
    CONSTRAINT unique_trait1_trait2 CHECK (
        character_trait1 IS NULL OR character_trait2 IS NULL OR character_trait1 <> character_trait2
    ),
    CONSTRAINT unique_trait2_trait3 CHECK (
        character_trait2 IS NULL OR character_trait3 IS NULL OR character_trait2 <> character_trait3
    ),
    CONSTRAINT unique_trait1_trait3 CHECK (
        character_trait1 IS NULL OR character_trait3 IS NULL OR character_trait1 <> character_trait3
    )
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- COMMENTS
-- ═══════════════════════════════════════════════════════════════════════════════

COMMENT ON TABLE assets.new_story_creator IS 'Wizard cache for new story creation. Singleton row (id=true). Cleared on wizard start.';

-- Setting phase
COMMENT ON COLUMN assets.new_story_creator.setting_genre IS 'Primary genre of the story';
COMMENT ON COLUMN assets.new_story_creator.setting_diegetic_artifact IS 'Full in-world document describing the setting';

-- Character phase
COMMENT ON COLUMN assets.new_story_creator.character_name IS 'Protagonist name (signals concept subphase complete)';
COMMENT ON COLUMN assets.new_story_creator.character_trait1 IS 'First selected trait from the 10 optional traits';
COMMENT ON COLUMN assets.new_story_creator.wildcard_name IS 'Custom wildcard trait name (signals character phase complete)';

-- Seed phase
COMMENT ON COLUMN assets.new_story_creator.seed_type IS 'Type of story opening (signals seed phase complete)';
COMMENT ON COLUMN assets.new_story_creator.seed_secrets IS 'LLM-to-LLM channel: hidden plot info user never sees';
COMMENT ON COLUMN assets.new_story_creator.initial_location IS 'PlaceProfile JSONB - complex nested structure';

-- ═══════════════════════════════════════════════════════════════════════════════
-- EPHEMERAL SUGGESTION TABLE
-- ═══════════════════════════════════════════════════════════════════════════════

DROP TABLE IF EXISTS assets.suggested_traits;

CREATE TABLE assets.suggested_traits (
    ordinal int CHECK (ordinal BETWEEN 1 AND 3),
    suggested_trait trait NOT NULL,
    rationale text NOT NULL,
    PRIMARY KEY (ordinal)
);

COMMENT ON TABLE assets.suggested_traits IS
    'Ephemeral LLM suggestions for trait selection. Max 3 rows via PK + CHECK. Cleared after character phase.';

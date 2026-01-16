-- Migration 010: Replace suggested_traits with full traits table
--
-- This migration:
-- 1. Creates assets.traits with canonical definitions and selection state
-- 2. Row 11 is the wildcard (always selected, rationale stores the custom definition)
-- 3. Drops the half-baked assets.suggested_traits table
-- 4. Removes character_trait1/2/3 and wildcard columns from new_story_creator
--    (all trait data now lives in assets.traits)

-- ============================================================================
-- Step 1: Create the new traits table
-- ============================================================================

CREATE TABLE IF NOT EXISTS assets.traits (
    id INTEGER PRIMARY KEY CHECK (id >= 1 AND id <= 11),
    name VARCHAR(50) NOT NULL,  -- Longer for custom wildcard names
    description TEXT[] NOT NULL,  -- Bullet points from trait_menu.md
    is_selected BOOLEAN NOT NULL DEFAULT FALSE,
    rationale TEXT  -- Skald's rationale; for wildcard, this IS the trait definition
);

COMMENT ON TABLE assets.traits IS 'Canonical trait definitions with per-slot selection state';
COMMENT ON COLUMN assets.traits.id IS 'Trait ordinal (1-10 optional, 11 wildcard)';
COMMENT ON COLUMN assets.traits.name IS 'Trait name; for wildcard (id=11) this is the custom name';
COMMENT ON COLUMN assets.traits.description IS 'Bullet-point descriptions from docs/trait_menu.md';
COMMENT ON COLUMN assets.traits.is_selected IS 'Selection state (exactly 3 of 1-10, plus wildcard always true = 4 total)';
COMMENT ON COLUMN assets.traits.rationale IS 'Why this trait fits; for wildcard, the full custom definition';

-- ============================================================================
-- Step 2: Populate with canonical trait definitions
-- ============================================================================

INSERT INTO assets.traits (id, name, description, is_selected, rationale) VALUES
-- Social Network
(1, 'allies', ARRAY[
    'will actively help you when it matters',
    'will take risks for you'
], FALSE, NULL),

(2, 'contacts', ARRAY[
    'can be tapped for information, favors, or access',
    'limited willingness to take risks for you; may be transactional or arms-length',
    'examples: bartender, smuggler, journalist, information broker'
], FALSE, NULL),

(3, 'patron', ARRAY[
    'powerful figure who mentors, sponsors, protects, or guides you',
    'has own position to protect; may have own agenda'
], FALSE, NULL),

(4, 'dependents', ARRAY[
    'lower status/power relative to you, but almost always willing to do what you want',
    'rely on you for some degree of support, protection, or guidance',
    'may be vulnerable, yet devoted',
    'may be capable, but with limited ability to act effectively without your guidance',
    'examples: child, employee, subordinate'
], FALSE, NULL),

-- Power & Position
(5, 'status', ARRAY[
    'formal standing recognized by a specific institution or social structure',
    'examples: military commission, guild journeyman, corporate board seat'
], FALSE, NULL),

(6, 'reputation', ARRAY[
    'how widely you''re known',
    'what for',
    'for better or worse',
    'may or may not confer influence'
], FALSE, NULL),

-- Assets & Territory
(7, 'resources', ARRAY[
    'material wealth, equipment, supplies',
    'can represent ready access rather than literal possession',
    'examples: stock portfolio, buried gold, high loan availability, mineral rights, harvest tithes, access to communal resources'
], FALSE, NULL),

(8, 'domain', ARRAY[
    'place or area controlled or claimed by character',
    'examples: condominium, uncontested turf, wizard''s tower'
], FALSE, NULL),

-- Liabilities
(9, 'enemies', ARRAY[
    'actively opposed to you; will expend energy and take risks to thwart you',
    'goals may be limited (jealous colleague who wants to humiliate you) or unlimited (mortal vengeance)'
], FALSE, NULL),

(10, 'obligations', ARRAY[
    'can be to individuals, groups, or concepts',
    'examples: oath, debt collector, filial piety'
], FALSE, NULL),

-- Wildcard (always selected, name and rationale are custom per-character)
(11, 'wildcard', ARRAY[
    'the only required trait',
    'defined by user and storyteller',
    'bespoke to setting, character archetype, and play-style preferences',
    'should be something that can matter regularly, not a trinket or quirk',
    'may be a capability or power exclusive to you, with an inherent drawback, e.g., some limited magical ability in an otherwise mundane world—but possibly inciting persecution',
    'may be a possession or item unique to the setting or not of that world, e.g., binoculars or a modern compound bow in a medieval or earlier setting; or a textbook from the future with world-changing, undiscovered knowledge—but others may try to steal or destroy it',
    'may be entirely detrimental, e.g., a curse or incurable disease',
    'examples: a vampire''s herd, symbiote (AI, xeno-implant), artifact (sentient sword, unique cyberware), a wizard''s familiar, pact with a deity, a powerful secret'
], TRUE, NULL)

ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_selected = EXCLUDED.is_selected;

-- ============================================================================
-- Step 3: Drop the old suggested_traits table
-- ============================================================================

DROP TABLE IF EXISTS assets.suggested_traits;

-- ============================================================================
-- Step 4: Remove trait columns from new_story_creator
-- ============================================================================

ALTER TABLE assets.new_story_creator
    DROP COLUMN IF EXISTS character_trait1,
    DROP COLUMN IF EXISTS character_trait2,
    DROP COLUMN IF EXISTS character_trait3,
    DROP COLUMN IF EXISTS wildcard_name,
    DROP COLUMN IF EXISTS wildcard_description;

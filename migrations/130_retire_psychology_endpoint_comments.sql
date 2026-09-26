-- Migration 130: Retire the Psychology Endpoint from Column Documentation
--
-- Issue #769 removed GET /api/characters/{character_id}/psychology from the
-- ordinary reader because it served hidden psychology and secrets to the
-- player client. Migration 127 documented these columns as "returned by the
-- character psychology endpoint", which is no longer true. The rows stay in
-- the database as authored canonical truth; no runtime code reads them (the
-- new-story reset only deletes them, and MEMNON's read-only SQL allowlist
-- excludes the table).
--
-- Comment-only and idempotent: COMMENT ON replaces the previous text, so
-- rerunning this file leaves the same documentation. No objects are created.

COMMENT ON COLUMN public.character_psychology.self_concept IS
    'Hidden psychology profile self concept JSON; canonical truth, not served to the player client since #769.';
COMMENT ON COLUMN public.character_psychology.behavior IS
    'Hidden psychology profile behavior JSON; canonical truth, not served to the player client since #769.';
COMMENT ON COLUMN public.character_psychology.cognitive_framework IS
    'Hidden psychology profile cognitive framework JSON; canonical truth, not served to the player client since #769.';
COMMENT ON COLUMN public.character_psychology.temperament IS
    'Hidden psychology profile temperament JSON; canonical truth, not served to the player client since #769.';
COMMENT ON COLUMN public.character_psychology.relational_style IS
    'Hidden psychology profile relational style JSON; canonical truth, not served to the player client since #769.';
COMMENT ON COLUMN public.character_psychology.defense_mechanisms IS
    'Hidden psychology profile defense mechanisms JSON; canonical truth, not served to the player client since #769.';
COMMENT ON COLUMN public.character_psychology.character_arc IS
    'Hidden psychology profile character arc JSON; canonical truth, not served to the player client since #769.';
COMMENT ON COLUMN public.character_psychology.secrets IS
    'Hidden psychology profile secrets JSON; canonical truth, not served to the player client since #769.';

-- 081_faction_project_contexts.sql
--
-- Persist the institutional counterparty selected by faction-bound Orrery
-- project templates. The binding is chosen on INSERT and may never change.

ALTER TABLE character_project_states
    ADD COLUMN IF NOT EXISTS target_faction_entity_id bigint NULL
        REFERENCES entities(id);

CREATE OR REPLACE FUNCTION prevent_project_faction_rebinding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.target_faction_entity_id IS DISTINCT FROM OLD.target_faction_entity_id THEN
        RAISE EXCEPTION
            'character_project_states.target_faction_entity_id is immutable '
            'after project entry (project id %, old %, new %)',
            OLD.id,
            OLD.target_faction_entity_id,
            NEW.target_faction_entity_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_character_project_states_faction_immutable
    ON character_project_states;
CREATE TRIGGER trg_character_project_states_faction_immutable
    BEFORE UPDATE OF target_faction_entity_id ON character_project_states
    FOR EACH ROW
    EXECUTE FUNCTION prevent_project_faction_rebinding();

COMMENT ON COLUMN character_project_states.target_faction_entity_id IS
    'The institutional counterparty bound at project entry; NULL for projects whose template declares no faction slot; immutable once set.';
COMMENT ON FUNCTION prevent_project_faction_rebinding() IS
    'Rejects every attempt to change a project faction binding after entry, including assigning a faction to an existing NULL binding.';
COMMENT ON TRIGGER trg_character_project_states_faction_immutable
    ON character_project_states IS
    'Makes the faction counterparty an entry-time, lifetime project binding.';

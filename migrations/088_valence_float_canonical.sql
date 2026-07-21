-- 088_valence_float_canonical.sql
--
-- Make the continuous signed float the canonical character-relationship
-- valence while preserving the eleven authored EmotionalValence literals as
-- a derived compatibility ladder.  The +/-5 rungs are outer bands of the
-- open interval (absolute float >= 4.5 / 5.5), centered at +/-5 / 5.5.  The
-- unattainable +/-1 endpoints remain available to later drift work as
-- asymptotes rather than authored states.

ALTER TABLE character_relationships
    ADD COLUMN valence_current numeric;

ALTER TABLE character_relationships
    ADD CONSTRAINT character_relationships_valence_current_open_check
    CHECK (valence_current > -1 AND valence_current < 1);

COMMENT ON COLUMN character_relationships.valence_current IS
    'Canonical continuous signed relationship valence in the open interval '
    '(-1, +1). emotional_valence is the derived eleven-rung compatibility '
    'projection; authored rung k enters at k / 5.5.';

COMMENT ON CONSTRAINT character_relationships_valence_current_open_check
    ON character_relationships IS
    'Keeps canonical relationship valence strictly inside (-1, +1); the '
    'endpoints are asymptotes, never stored states.';

CREATE OR REPLACE FUNCTION fn_character_valence_from_literal(valence_literal text)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    prefix_match text[];
BEGIN
    prefix_match := regexp_match(valence_literal, '^([+-]?[0-9]+)\|');
    IF prefix_match IS NULL THEN
        RAISE EXCEPTION
            'Unparseable emotional_valence %; expected signed integer prefix and |label',
            valence_literal
            USING ERRCODE = '22023';
    END IF;
    RETURN prefix_match[1]::numeric / 5.5;
END;
$$;

COMMENT ON FUNCTION fn_character_valence_from_literal(text) IS
    'Parses an authored emotional-valence numeric prefix and maps rung k to '
    'canonical float k / 5.5. Raises on literals without a parseable prefix.';

CREATE OR REPLACE FUNCTION fn_character_valence_literal(valence numeric)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    rung integer := greatest(-5, least(5, round(valence * 5.5)::integer));
BEGIN
    RETURN CASE rung
        WHEN 5 THEN '+5|devoted'
        WHEN 4 THEN '+4|admiring'
        WHEN 3 THEN '+3|trusting'
        WHEN 2 THEN '+2|friendly'
        WHEN 1 THEN '+1|favorable'
        WHEN 0 THEN '0|neutral'
        WHEN -1 THEN '-1|wary'
        WHEN -2 THEN '-2|disapproving'
        WHEN -3 THEN '-3|resentful'
        WHEN -4 THEN '-4|hostile'
        WHEN -5 THEN '-5|hateful'
    END;
END;
$$;

COMMENT ON FUNCTION fn_character_valence_literal(numeric) IS
    'Projects canonical float valence onto the nearest eleven-rung '
    'EmotionalValence literal via round(valence * 5.5), clamped to -5..+5.';

CREATE OR REPLACE FUNCTION fn_derive_character_relationship_valence()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.valence_current IS NULL THEN
            NEW.valence_current :=
                fn_character_valence_from_literal(NEW.emotional_valence::text);
        END IF;
        NEW.emotional_valence :=
            fn_character_valence_literal(NEW.valence_current);
        RETURN NEW;
    END IF;

    IF NEW.valence_current IS DISTINCT FROM OLD.valence_current THEN
        -- Float-first writes win when both representations change.
        NEW.emotional_valence :=
            fn_character_valence_literal(NEW.valence_current);
    ELSIF NEW.emotional_valence IS DISTINCT FROM OLD.emotional_valence THEN
        -- A changed authored literal re-enters through its new rung center.
        -- Reasserting the current projection is intentionally a no-op so an
        -- off-center canonical float retains its intra-rung drift position.
        NEW.valence_current :=
            fn_character_valence_from_literal(NEW.emotional_valence::text);
        NEW.emotional_valence :=
            fn_character_valence_literal(NEW.valence_current);
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_derive_character_relationship_valence() IS
    'Single write-boundary authority for character relationship valence. '
    'A changed authored literal re-enters at the new rung center; reasserting '
    'the currently projected literal is a no-op that preserves off-center '
    'intra-rung float drift. Float-first writes derive the compatibility '
    'literal, and the float wins if both representations change.';

DROP TRIGGER IF EXISTS trg_character_relationships_valence_boundary
    ON character_relationships;

CREATE TRIGGER trg_character_relationships_valence_boundary
    BEFORE INSERT OR UPDATE ON character_relationships
    FOR EACH ROW EXECUTE FUNCTION fn_derive_character_relationship_valence();

COMMENT ON TRIGGER trg_character_relationships_valence_boundary
    ON character_relationships IS
    'Canonical valence write boundary: changed literal writes re-center; '
    'same-projection literal reassertions preserve intra-rung float drift; '
    'float writes project the literal and win when both representations '
    'change. PostgreSQL fires same-kind triggers alphabetically, so this '
    'trigger runs before '
    'trg_version_character_relationships. The versioning trigger still '
    'captures to_jsonb(OLD), so its pre-image contract is unchanged.';

-- The boundary trigger performs the one-time backfill too.  Every UPDATE is
-- therefore versioned by migration 065 with an OLD pre-image whose newly
-- added valence_current key is NULL.  Replay comparison already treats that
-- explicit NULL as equal to the key absent from pre-088 checkpoints, while a
-- non-NULL mismatch remains loud for post-088 checkpoints.
UPDATE character_relationships
SET valence_current =
        fn_character_valence_from_literal(emotional_valence::text),
    emotional_valence = fn_character_valence_literal(
        fn_character_valence_from_literal(emotional_valence::text)
    );

ALTER TABLE character_relationships
    ALTER COLUMN valence_current SET NOT NULL;

CREATE OR REPLACE VIEW entity_relationships_v AS
    SELECT
        c1.entity_id AS source_entity_id,
        c2.entity_id AS target_entity_id,
        'character'::text AS relationship_scope,
        cr.relationship_type::text AS relationship_type,
        cr.emotional_valence::text AS valence,
        cr.dynamic,
        cr.recent_events,
        cr.history,
        cr.extra_data,
        round(cr.valence_current * 5.5)::integer AS valence_magnitude,
        cr.valence_current
    FROM character_relationships cr
    JOIN characters c1 ON c1.id = cr.character1_id
    JOIN characters c2 ON c2.id = cr.character2_id
UNION ALL
    SELECT
        f1.entity_id AS source_entity_id,
        f2.entity_id AS target_entity_id,
        'faction'::text AS relationship_scope,
        fr.relationship_type::text AS relationship_type,
        NULL::text AS valence,
        fr.current_status AS dynamic,
        NULL::text AS recent_events,
        fr.history,
        fr.extra_data,
        NULL::integer AS valence_magnitude,
        NULL::numeric AS valence_current
    FROM faction_relationships fr
    JOIN factions f1 ON f1.id = fr.faction1_id
    JOIN factions f2 ON f2.id = fr.faction2_id
UNION ALL
    SELECT
        f.entity_id AS source_entity_id,
        c.entity_id AS target_entity_id,
        'faction_character'::text AS relationship_scope,
        fcr.role::text AS relationship_type,
        NULL::text AS valence,
        fcr.current_status AS dynamic,
        NULL::text AS recent_events,
        fcr.history,
        fcr.extra_data,
        NULL::integer AS valence_magnitude,
        NULL::numeric AS valence_current
    FROM faction_character_relationships fcr
    JOIN factions f ON f.id = fcr.faction_id
    JOIN characters c ON c.id = fcr.character_id;

COMMENT ON COLUMN entity_relationships_v.valence_magnitude IS
    'Signed integer in -5..+5 derived from canonical valence_current via '
    'round(valence_current * 5.5); NULL outside character scope.';

COMMENT ON COLUMN entity_relationships_v.valence_current IS
    'Canonical continuous signed valence for character relationships; NULL '
    'for faction and faction_character scopes.';

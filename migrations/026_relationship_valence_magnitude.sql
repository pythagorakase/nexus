-- Add SQL-side relationship valence magnitude for Orrery trust hydration.
--
-- `character_relationships.emotional_valence` remains the canonical hybrid
-- enum/label. The compatibility view exposes the parseable signed magnitude
-- as an integer so runtime readers do not embed enum-string parsing rules.

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
        CASE cr.emotional_valence::text
            WHEN '+5|devoted' THEN 5
            WHEN '+4|admiring' THEN 4
            WHEN '+3|trusting' THEN 3
            WHEN '+2|friendly' THEN 2
            WHEN '+1|favorable' THEN 1
            WHEN '0|neutral' THEN 0
            WHEN '-1|wary' THEN -1
            WHEN '-2|disapproving' THEN -2
            WHEN '-3|resentful' THEN -3
            WHEN '-4|hostile' THEN -4
            WHEN '-5|hateful' THEN -5
            ELSE NULL
        END::integer AS valence_magnitude
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
        NULL::integer AS valence_magnitude
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
        NULL::integer AS valence_magnitude
    FROM faction_character_relationships fcr
    JOIN factions f ON f.id = fcr.faction_id
    JOIN characters c ON c.id = fcr.character_id;

COMMENT ON COLUMN entity_relationships_v.valence_magnitude IS
    'Signed integer in -5..+5 derived from character_relationships.emotional_valence; NULL for faction and faction_character scopes.';

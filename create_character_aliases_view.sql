-- Create a view that shows each character's name with an array of their aliases
-- This view joins the characters table with the normalized character_aliases table
-- and aggregates all aliases for each character into an array

CREATE OR REPLACE VIEW character_aliases_view AS
SELECT 
    c.name,
    COALESCE(
        ARRAY_AGG(ca.alias ORDER BY ca.alias) FILTER (WHERE ca.alias IS NOT NULL),
        ARRAY[]::text[]
    ) AS aliases
FROM characters c
LEFT JOIN character_aliases ca ON c.id = ca.character_id
GROUP BY c.id, c.name
ORDER BY c.name;

-- The view provides:
-- - One row per character name
-- - An array of all associated aliases (empty array if no aliases)
-- - Aliases are sorted alphabetically within each array
-- - LEFT JOIN ensures all characters appear, even those without aliases

-- Example usage:
-- SELECT * FROM character_aliases_view WHERE name = 'Alex';
-- SELECT name, array_length(aliases, 1) as alias_count FROM character_aliases_view;
-- SELECT name, aliases[1] as first_alias FROM character_aliases_view WHERE array_length(aliases, 1) > 0;
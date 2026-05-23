-- Migration 044: Disambiguate Status from broad Reputation/Fame in the wizard.
--
-- The trait enum/storage value remains `reputation` until the broader Fame
-- rename lands. This copy update makes the wizard distinction explicit now:
-- Status is scoped standing inside a group; Reputation is ambient recognition.

UPDATE assets.traits
SET description = ARRAY[
    'standing within a specific institution, faction, community, or social scene',
    'can be formal rank or informal local esteem/clout',
    'use this when you are known within that group, even if obscure elsewhere',
    'examples: military commission, guild journeyman, corporate board seat, respected neighborhood fixer'
]
WHERE id = 5
  AND name = 'status';

UPDATE assets.traits
SET description = ARRAY[
    'Fame: how broadly you''re recognized beyond any one specific group',
    'what the wider world recognizes you for, for better or worse',
    'use Status instead when recognition is limited to one faction, institution, community, or subculture',
    'may or may not confer influence'
]
WHERE id = 6
  AND name IN ('reputation', 'fame');

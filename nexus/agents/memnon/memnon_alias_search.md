# MEMNON Alias-Aware Search

`utils/alias_search.py` loads canonical names from `characters` and populated
aliases from `character_aliases`. The canonical player is resolved through
`global_variables.user_character`; only that character receives the second-person
aliases “You,” “Your,” “Yours,” and “Yourself.” Database and identity errors
propagate to the caller. There is no default cast or alias mapping.

`alias_terms(query, alias_lookup)` requires the database-derived mapping and
expands matched names or aliases using word boundaries. Possessive pronouns use
the same matching path as other aliases. `hybrid_alias_search` loads the mapping
from its connection when the caller does not supply one.

MEMNON's `_load_aliases()` uses its selected database session and propagates
loading failures. See `tests/test_lore/test_query_patterns_pg.py` for disposable
PostgreSQL coverage of cast changes, pronoun ownership, and missing tables.

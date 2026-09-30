-- Migration 136: Correct Six Column Comments and One Type Comment (issue #819)
--
-- Slice D of #819. Six COMMENT ON COLUMN texts named labels their enum types
-- do not have (issue #819 comment "Slice D Seed: Six Column Comments That
-- Name Labels Their Enums Do Not Have", confirmed read-only on
-- NEXUS_template on 2026-09-29). A wrong comment is worse than none, because
-- psql \d+ and the schema summary present it as the documentation. Each
-- replacement says what the value means and which code writes and reads it,
-- and leaves the label list to the enum catalog.
--
-- The seventh statement replaces the faction_member_role type comment from
-- migration 135 (line 96), whose last sentence ("counts every row as
-- membership whatever its role") #1033 (PR #1047) makes false. The text is
-- the statement recorded in that branch's
-- docs/qa/1033-membership-roles/verification.md, copied verbatim. PR #1047
-- merges before this migration lands; the faction_character_relationships.role
-- comment below describes the membership rule as that branch implements it.
--
-- Comment-only and idempotent: COMMENT ON replaces the previous text, so
-- rerunning this file leaves the same documentation. No objects are created
-- or changed. None of the seven objects is in config/schema_docs_baseline.json.
--
-- Evidence sites (reader/writer code at 384634f9 unless noted).
-- chunk_character_references.reference: nexus/presence/roster.py:160-166,219-234,417-435,448; nexus/api/commit_handler_sync.py:713; nexus/api/return_recap.py:332-337,423
-- chunk_metadata.world_layer: nexus/agents/logon/skald_wire.py:60,532-538; nexus/api/lore_adapter.py:316-321; nexus/api/commit_handler_sync.py:124-137,462,584; nexus/agents/orrery/retrograde_persistence.py:2575-2580; nexus/agents/orrery/drift.py:235-237; nexus/agents/orrery/propagation.py:131-133; nexus/agents/orrery/reveal.py:87-89; nexus/agents/orrery/worker.py:281,556,589-590,824; nexus/agents/orrery/resolver.py:1336,1342,2826-2831; nexus/agents/orrery/experiences.py:1055-1056,1581-1582
-- place_chunk_references.reference_type: nexus/presence/roster.py:170-175,219-244,417-440; nexus/api/commit_handler_sync.py:713; nexus/agents/lore/logon_utility.py:245-257,2212; nexus/agents/lore/utils/entity_queries.py:257-275; nexus/api/reader_endpoints.py:617-640; nexus/api/return_recap.py:302-322; nexus/agents/orrery/experiences.py:738,1443; nexus/agents/orrery/knowledge_surfacing.py:138
-- places.type: nexus/api/new_story_db_mapper.py:120,340,416; nexus/api/new_story_schemas.py:1152; nexus/api/trait_compiler.py:1850-1853; nexus/agents/orrery/retrograde_persistence.py:3219-3222; nexus/agents/orrery/retrograde_maturation.py:455-457; nexus/agents/orrery/resolver.py:558-597; nexus/agents/orrery/substrate.py:1140-1161; nexus/api/place_tag_manifest.py:375-390,441,665-667
-- faction_character_relationships.role: scripts/faction_relationship_analyst.py:589,612-665; migrations/088_valence_float_canonical.sql:184-198; nexus/agents/orrery/resolver.py:697-708 and nexus/config/settings_models.py:1340-1363 and nexus.toml:345-350 at e9376065 (PR #1047); nexus/agents/orrery/substrate.py:2106-2117
-- faction_relationships.relationship_type: scripts/faction_relationship_analyst.py:497,505-506,521-570; migrations/088_valence_float_canonical.sql:168-182; nexus/agents/orrery/resolver.py:403-408,624-625,990-994; nexus/agents/orrery/audit.py:2169-2170; nexus/agents/orrery/reveal.py:425-426; nexus/agents/orrery/knowledge_surfacing.py:675-676; nexus/agents/orrery/reconstruction.py:89-93,123-126
-- faction_member_role (type): docs/qa/1033-membership-roles/verification.md at e9376065 (PR #1047); migrations/135_schema_docs_backfill.sql:96-97

-- Columns.

COMMENT ON COLUMN public.chunk_character_references.reference IS
    'Role of the character in this accepted chunk. The commit path writes it through the presence roster (roster.write_roster), one row per character and chunk, and a rewrite of the same pair replaces the value. roster.read_rosters puts present rows in the scene cast and the remaining rows among the characters only named; return recaps read the present rows of the frontier chunk as its cast.';

COMMENT ON COLUMN public.chunk_metadata.world_layer IS
    'Timeline layer of this chunk. The commit path writes the layer the storyteller wire declares, or primary when the wire declares none; the Retrograde prologue insert writes retrograde. The column has no default; narration jobs and the Orrery resolver read NULL as primary, while the relationship drift, claim propagation, and secret reveal drains act only on a primary chunk and so skip a NULL layer. Experience and narration jobs copy the anchor chunk layer and refuse completion when it has changed.';

COMMENT ON COLUMN public.place_chunk_references.reference_type IS
    'Role of the place in this accepted chunk, written at commit through the presence roster (roster.write_roster). The storyteller presence baseline requires exactly one setting row on the parent chunk (roster.continuation_setting); featured-place selection takes places from the most recent referencing chunks and reports the strongest role each place holds there; setting rows also give /api/current-place, the return-recap location, and the scene location that experiences and knowledge surfacing read.';

COMMENT ON COLUMN public.places.type IS
    'Structural category of the place. The new-story wizard writes the starting location from its place profile, trait compiler and Retrograde persistence stubs write other, and Retrograde maturation writes fixed_location. The Orrery resolver loads it as a location class beside the place location-class tags (orrery:location_classes), so in_location_class conditions match it, and place_tag_manifest turns some values into review-required place tag proposals.';

COMMENT ON COLUMN public.faction_character_relationships.role IS
    'Position of the character in the faction, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py), which replaces it when rerun for the same pair, and exposed as entity_relationships_v.relationship_type with scope faction_character. The Orrery resolver counts the row as faction membership (orrery:faction_memberships, read by the faction_member condition) only when this role is listed in nexus.toml [orrery.resolver] membership_roles.';

COMMENT ON COLUMN public.faction_relationships.relationship_type IS
    'Relationship between the two factions, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py), which stores each pair once with the lower faction id first and replaces the value when rerun, and exposed as entity_relationships_v.relationship_type with scope faction. Current Orrery readers of that view select only character scope; reconstruction checkpoints copy the row whole.';

-- Type.

COMMENT ON TYPE public.faction_member_role IS
    'Position of a character in a faction, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py) and exposed as entity_relationships_v.relationship_type with scope faction_character. The Orrery membership loader counts a row as membership only when its role is listed in nexus.toml [orrery.resolver] membership_roles (default leader, employee, member, sympathizer).';

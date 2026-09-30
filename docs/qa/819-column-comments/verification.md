# Issue 819 Slice D: Enum Column Comments Name Only Their Own Labels

Branch `claude/819-column-comments`, cut from `origin/main` at `384634f9`.
One comment-only migration, `migrations/136_column_comment_corrections.sql`.
No paid provider call, no gateway lane. No `save_NN` or `NEXUS_template` was
written: the template was read (`psql -d NEXUS_template`, SELECT only), and
every PostgreSQL test and the listing below ran on disposable `qa640_` clones
(`-p tests.dbname_audit` reports `owner targets: none`).

Merge order: PR #1047 (#1033, branch `claude/1033-membership-roles`) first.
The `faction_character_relationships.role` comment and the
`faction_member_role` type comment describe the membership rule as that branch
implements it (`nexus/agents/orrery/resolver.py:697-708`,
`nexus/config/settings_models.py:1340-1363`, `nexus.toml:345-350` at
`e9376065`). The type statement is copied verbatim from that branch's
`docs/qa/1033-membership-roles/verification.md` ("Replacement Comment for
Migration 135"); `diff` against the migration's lines 54-55 is empty at
`1527e30d`, at `e9376065`, and at `69701371` (the branch head on 2026-09-30).

## Migration Number

136 is free: `migrations/` on `origin/main` ends at
`135_schema_docs_backfill.sql`; the open PR branches
(`claude/1033-membership-roles`, `claude/1037-import-time-logging`) and every
local worktree also end at 135.

## Ratchet Baseline

Unchanged. None of the six columns and not `faction_member_role` appears in
`config/schema_docs_baseline.json` (all seven carried a comment before this
migration), so the migration retires no baseline entry.
`scripts/check_migration_comments.py`: `OK: every object created after
migration 129 has a comment.`

## Before and After

Before: read on `NEXUS_template` (schema version 135). Only the
`place_chunk_references.reference_type` text and the type text come from a
file in the tree (`migrations/127_schema_documentation.sql:333`,
`migrations/135_schema_docs_backfill.sql:96-97`); the other five are legacy
schema comments no migration or script in the tree writes.

| Object | Enum labels (catalog) | Before | Wrong label |
| --- | --- | --- | --- |
| `chunk_character_references.reference` | present, mentioned | Type of reference: present (character is in scene), mentioned (character discussed but not present), implied (indirect reference) | implied |
| `chunk_metadata.world_layer` | primary, flashback, atemporal, extradiegetic, retrograde | Narrative layer (e.g. primary, secondary) | secondary |
| `place_chunk_references.reference_type` | setting, mentioned, transit | Place presence/reference role written from the chunk roster: mentioned, transit, setting, or present. | present |
| `places.type` | fixed_location, vehicle, virtual, other | Type of location (facility, vehicle, district, etc.) | facility, district |
| `faction_character_relationships.role` | leader, employee, member, target, informant, sympathizer, defector, exile, insider_threat | Character position/function within faction (leader, member, contractor, etc.) | contractor |
| `faction_relationships.relationship_type` | alliance, trade_partners, truce, vassalage, coalition, war, rivalry, ideological_enemy, competitor, splinter, unknown, shadow_partner | Nature of relationship (allied, hostile, neutral, trade_partner, etc.) | allied, hostile, neutral, trade_partner |
| `faction_member_role` (type) | as above | Position of a character in a faction, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py) and exposed as entity_relationships_v.relationship_type with scope faction_character. The Orrery membership loader counts every row as membership whatever its role. | last sentence false after #1033 |

After, with the evidence each claim rests on (code at `384634f9` unless
noted; the full site list is in the migration header):

- **`chunk_character_references.reference`**: writer `nexus/presence/roster.py:417-435` (`_write_statements`, `ON CONFLICT (chunk_id, character_id) DO UPDATE`), called from `nexus/api/commit_handler_sync.py:713`; reader `roster.py:160-166,219-234` (`present` goes to the scene cast, every other value to `referenced`); return recap `nexus/api/return_recap.py:423`.
- **`chunk_metadata.world_layer`**: wire default `nexus/agents/logon/skald_wire.py:60,532-538`, `nexus/api/lore_adapter.py:316-321`, `nexus/api/commit_handler_sync.py:462,584`; prologue `nexus/agents/orrery/retrograde_persistence.py:2575-2580`; no default (catalog: nullable, no `pg_attrdef`); NULL read as primary by narration jobs `nexus/agents/orrery/worker.py:281,556,824`; the drains compare the raw value with `primary` and so skip NULL: `drift.py:235-237`, `propagation.py:131-133`, `reveal.py:87-89`; job layer checks `worker.py:585-590`, `experiences.py:1055-1056,1581-1582`.
- **`place_chunk_references.reference_type`**: writer `roster.py:438-440`; exactly one setting `roster.py:238-247` via `nexus/agents/lore/logon_utility.py:245-257` (`read_presence_baseline`); featured-place selection `nexus/agents/lore/utils/entity_queries.py:220-320` (`fetch_all_places_with_references`: `WHERE chunk_id = ANY(:chunk_ids)` reads only the chunk ids its caller supplies; `DISTINCT ON (place_id)` ordered by `chunk_id DESC` then setting, transit, mentioned, so each place reports its strongest role in its latest referencing chunk among them; the outer `ORDER BY chunk_id DESC, place_id LIMIT :max_featured_places` keeps the most recently referenced places; then `featured_ids.setdefault(pid, "character_location")` adds each featured character's current location whether or not a row references it), whose one caller `nexus/agents/lore/utils/turn_cycle.py:561-566` passes `warm_chunk_ids` (the warm-slice chunk ids, `turn_cycle.py:486-488`), the featured characters' location ids, and `entity_settings.max_locations_from_warm_slice`; setting readers `nexus/api/reader_endpoints.py:617-640`, `nexus/api/return_recap.py:302-322`, `nexus/agents/orrery/experiences.py:738,1443`, `nexus/agents/orrery/knowledge_surfacing.py:138`.
- **`places.type`**: wizard `nexus/api/new_story_db_mapper.py:120,340,416`; stubs `nexus/api/trait_compiler.py:1850-1853`, `nexus/agents/orrery/retrograde_persistence.py:3219-3222`; maturation `nexus/agents/orrery/retrograde_maturation.py:455-457`; resolver `nexus/agents/orrery/resolver.py:558-597` (`p.type::text AS location_class`), matched by `nexus/agents/orrery/substrate.py:1140-1161`; `nexus/api/place_tag_manifest.py:375-390,441,665-667`.
- **`faction_character_relationships.role`**: writer `scripts/faction_relationship_analyst.py:589,612-665`; view `migrations/088_valence_float_canonical.sql:184-198`; filter at `e9376065`: `resolver.py:705` (`AND fcr.role::text = ANY(:membership_roles)`), read by `substrate.py:2106-2117` (`faction_member`).
- **`faction_relationships.relationship_type`**: writer `scripts/faction_relationship_analyst.py:497,505-506,521-570` (ids swapped so `faction1_id < faction2_id`, then update or insert); view `migrations/088_valence_float_canonical.sql:168-182`; every Orrery reader of the view filters `relationship_scope = 'character'` (`resolver.py:403-408,624-625,990-994`, `audit.py:2169-2170`, `reveal.py:425-426`, `knowledge_surfacing.py:675-676`); checkpoints `nexus/agents/orrery/reconstruction.py:89-93,123-126`.

## Test

`tests/test_enum_column_comment_labels_pg.py` builds one disposable clone with
`disposable_slot_database("qa640_819_labels")` (template stamps at 135, so the
clone applies 136) and reads only `pg_enum`, `col_description`, and
`obj_description`:

- for each of the six columns, the column's enum type comes from `atttypid`;
  the label vocabulary is every label of the six enums plus the nine labels
  only the old comments named (`implied`, `secondary`, `facility`, `district`,
  `contractor`, `allied`, `hostile`, `neutral`, `trade_partner`); the comment's
  words, folded to lower case, may not contain a vocabulary label outside the
  column's own enum; the subsystem name "Retrograde" is exempt only inside
  the exact phrases the migration uses ("Retrograde prologue", "Retrograde
  persistence", "Retrograde maturation"), and every other occurrence, in any
  letter case, counts as the label `retrograde`;
- the same check rejects each pre-136 comment (kept verbatim in the test);
- a capitalized stale label is caught: "Narrative layer (e.g. Primary,
  Secondary)" checked against `world_layer_type` yields exactly
  `{'secondary'}`;
- a bare subsystem word is caught: "Type of place: Retrograde." checked
  against `place_type` yields exactly `{'retrograde'}`;
- the `faction_member_role` type comment no longer contains "counts every row
  as membership whatever its role" and names only its own labels.

No test imports `OrreryResolverSettings` or reads `[orrery.resolver]`.

Bite check: with `migrations/136_column_comment_corrections.sql` moved out of
the tree, the module failed 13 of 13 (before the capitalized-label test
existed); the six label assertions report exactly the wrong labels in the
table above (`['implied']`, `['secondary']`, `['present']`,
`['district', 'facility']`, `['contractor']`,
`['allied', 'hostile', 'neutral', 'trade_partner']`), and the type test
reports the stale sentence. The file was restored and the module passes.

Case-folding bite check (at `effc36c1`): with `_tokens` changed back to keep
each word's case, `test_capitalized_stale_label_is_rejected` fails with
`AssertionError: assert set() == {'secondary'}` (1 failed, 13 passed); the
change was reverted and the module passes.

Phrase-exemption bite check (at `cfc6253e`): with `_tokens` changed back to
the word-level exemption (every "Retrograde" kept its case), the new case
fails with `AssertionError: assert set() == {'retrograde'}`
(`FAILED tests/test_enum_column_comment_labels_pg.py::test_bare_subsystem_word_counts_as_a_label`,
1 failed, 14 passed); the plant was reverted and the module passes.

## Proof

`$PY` is `/Users/pythagor/nexus/.venv/bin/python`; every command ran from the
worktree root with `PYTHONPATH=$PWD`, `NEXUS_GATEWAY_PORT` and
`NEXUS_API_URL` unset; `nexus.__file__` resolved under the worktree.

PostgreSQL tails at `3a73be58` (the round-4 review-fix head; `cfc6253e`
changed the migration and the test, `3a73be58` only removed a trailing blank
line from the test). `tests/test_new_story_setup.py` runs in the same
command because it rolls migration 135 back as its lagging-template probe and
136 now follows it:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_enum_column_comment_labels_pg.py tests/test_new_story_setup.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 22 targets: nexus_m10_fresh_test_23647, nexus_m10_template_test_23647, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_819_labels_*, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
133 passed in 24.13s
```

Offline (recorded for the first push, before `effc36c1`; not rerun, since
`effc36c1`, `3a4828f9`, `cfc6253e` and `3a73be58` change only comment text
in the migration, the PostgreSQL-only test module, and this file):

```
$ $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 737 skipped, 7 warnings in 35.23s

$ $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2607 passed, 404 skipped, 8 warnings in 394.94s (0:06:34)

$ $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 9.90s
```

Black, flake8, and mypy on the one changed Python file
(`tests/test_enum_column_comment_labels_pg.py`), and the migration-comment
check, at `3a73be58` (flake8 prints nothing):

```
$ $PY -m black --check tests/test_enum_column_comment_labels_pg.py
All done! ✨ 🍰 ✨
1 file would be left unchanged.
$ $PY -m flake8 tests/test_enum_column_comment_labels_pg.py
$ $PY -m mypy tests/test_enum_column_comment_labels_pg.py
Success: no issues found in 1 source file
$ $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
```

## Migrated-Clone Listing

Read-only `col_description` / `obj_description` on a disposable clone built
by `disposable_slot_database("qa640_819_listing")` from the migration text
committed at `cfc6253e` (unchanged at `3a73be58`). The runner logged
`Applied: 136_column_comment_corrections`, the clone was dropped afterward,
and each of the seven texts equals its string in the migration byte for byte
(the listing script compared them: 0 mismatches):

```
clone: qa640_819_listing_*; max(schema_migrations.version) = 136
chunk_character_references.reference (reference_type):
  Role of the character in this accepted chunk. The commit path writes it through the presence roster (roster.write_roster), one row per character and chunk, and a rewrite of the same pair replaces the value. roster.read_rosters puts present rows in the scene cast and the remaining rows among the characters only named; return recaps read the present rows of the frontier chunk as its cast.
chunk_metadata.world_layer (world_layer_type):
  Timeline layer of this chunk. The commit path writes the layer the storyteller wire declares, or primary when the wire declares none; the Retrograde prologue insert writes retrograde. The column has no default; narration jobs read NULL as primary, while the relationship drift, claim propagation, and secret reveal drains act only on a primary chunk and so skip a NULL layer. Experience and narration jobs copy the anchor chunk layer and refuse completion when it has changed.
faction_character_relationships.role (faction_member_role):
  Position of the character in the faction, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py), which replaces it when rerun for the same pair, and exposed as entity_relationships_v.relationship_type with scope faction_character. The Orrery resolver counts the row as faction membership (orrery:faction_memberships, read by the faction_member condition) only when this role is listed in nexus.toml [orrery.resolver] membership_roles.
faction_relationships.relationship_type (faction_relationship_type):
  Relationship between the two factions, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py), which stores each pair once with the lower faction id first and replaces the value when rerun, and exposed as entity_relationships_v.relationship_type with scope faction. Current Orrery readers of that view select only character scope; reconstruction checkpoints copy the row whole.
place_chunk_references.reference_type (place_reference_type):
  Role of the place in this accepted chunk, written at commit through the presence roster (roster.write_roster). The storyteller presence baseline requires exactly one setting row on the parent chunk (roster.continuation_setting). Featured-place selection reads the rows of the warm-slice chunks: for each place it reports the strongest role the place holds in its latest referencing chunk among them, and it keeps the most recently referenced places up to its limit; the current location of a featured character is also featured, whether or not a row here references it. Setting rows also give /api/current-place, the return-recap location, and the scene location that experiences and knowledge surfacing read.
places.type (place_type):
  Structural category of the place. The new-story wizard writes the starting location from its place profile, trait compiler and Retrograde persistence stubs write other, and Retrograde maturation writes fixed_location. The Orrery resolver loads it as a location class beside the place location-class tags (orrery:location_classes), so in_location_class conditions match it, and place_tag_manifest turns some values into review-required place tag proposals.
TYPE faction_member_role:
  Position of a character in a faction, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py) and exposed as entity_relationships_v.relationship_type with scope faction_character. The Orrery membership loader counts a row as membership only when its role is listed in nexus.toml [orrery.resolver] membership_roles (default leader, employee, member, sympathizer).
```

## Round 4: Independent Review Fixes (2026-09-30)

The independent review of `e09476d9` found two defects, both fixed at
`cfc6253e`:

- P1: the `place_chunk_references.reference_type` comment described
  featured-place selection too broadly. The new text says the selection reads
  only the warm-slice chunks and that a featured character's current location
  is featured whether or not a row references it; each clause was checked
  against `entity_queries.py:220-320` and `turn_cycle.py:486-488,561-566`.
- P2: the test exempted every "Retrograde", so `Type of place: Retrograde.`
  passed for `places.type`. The exemption now covers only the three exact
  phrases the migration uses, and a new case proves a bare "Retrograde" counts
  as the label `retrograde`.

The reviewer's sandbox reached neither PostgreSQL nor GitHub. The coordinator
ran these read-only checks on `NEXUS_template` on 2026-09-30:

```
$ psql -d NEXUS_template -Atc "SELECT column_default IS NULL, is_nullable, udt_name FROM information_schema.columns WHERE table_name='chunk_metadata' AND column_name='world_layer'"
t|YES|world_layer_type

$ psql -d NEXUS_template -Atc "SELECT t.typname, string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder) FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid WHERE t.typname IN ('place_reference_type','world_layer_type','place_type','faction_member_role','faction_relationship_type','reference_type') GROUP BY 1"
faction_member_role|leader,employee,member,target,informant,sympathizer,defector,exile,insider_threat
faction_relationship_type|alliance,trade_partners,truce,vassalage,coalition,war,rivalry,ideological_enemy,competitor,splinter,unknown,shadow_partner
place_reference_type|setting,mentioned,transit
place_type|fixed_location,vehicle,virtual,other
reference_type|present,mentioned
world_layer_type|primary,flashback,atemporal,extradiegetic,retrograde
```

Migration number: on 2026-09-30 the open pull requests are #1046, #1047 and
#1048 (`gh pr list --state open`). Rerun after `git fetch origin`:

```
$ git ls-tree --name-only origin/claude/1037-import-time-logging migrations/ | tail -1
migrations/135_schema_docs_backfill.sql
$ git ls-tree --name-only origin/claude/1033-membership-roles migrations/ | tail -1
migrations/135_schema_docs_backfill.sql
```

## Coordinator Note

The coordinator applies migration 136 fleet-wide after PR #1047 merges:
`NEXUS_template`, `save_02`-`save_05`, and `save_01` through
`--write-locked-slot`. The migration is comment-only and idempotent.

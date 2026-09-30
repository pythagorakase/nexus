# Issue 819 Slice E: Comments on the Five Uncommented Views

Branch `claude/819-view-comments`, cut from `origin/main` at `c8dd8c85`.
One comment-only migration, `migrations/137_view_comments.sql`: five
`COMMENT ON VIEW` statements and no other SQL. No paid provider call, no
gateway lane. No `save_NN` or `NEXUS_template` was written: the template and
the saves were read in `default_transaction_read_only` sessions, and every
PostgreSQL test and the listing below ran on disposable `qa640_` clones
(`-p tests.dbname_audit` reports `owner targets: none`).

## Migration Number

137 is free: `migrations/` on `origin/main` ends at
`136_column_comment_corrections.sql`; the open PR branches end at 135
(`claude/836-reference-parity`, `claude/812-legacy-inventory`,
`claude/842-mock-openai-logging`) or 136 (`claude/809-settings-aliases`,
`claude/1037-import-time-logging`). A parallel order holds 138.

## Ratchet Coverage and Baseline

`tests/test_schema_documentation_pg.py` inventories views: `INVENTORY_SQL`
selects `pg_class` rows with `relkind IN ('r', 'p', 'f', 'v', 'm')` in
`public` and `assets` that no extension owns, and keys `v` and `m` as
`view:<schema>.<name>` with `obj_description` (lines 41-58). `_assert_coverage`
fails on any undocumented object missing from the baseline and on any baseline
entry that is documented or gone (lines 151-158), and
`test_views_are_documented_at_view_level` (lines 413-444) proves an
uncommented view fails the gate. So the premise holds: once migration 137
comments the five views, their baseline entries must go, and the file passes
only with them removed.

Bite check: with `migrations/137_view_comments.sql` moved out of the tree and
the reduced baseline in place,
`tests/test_schema_documentation_pg.py::test_schema_documentation_coverage`
errors in its fixture with `AssertionError: Undocumented objects absent from
baseline: ['view:public.chunk_entity_references_v', 'view:public.entity_names_v',
'view:public.entity_relationships_v', 'view:public.entity_tags_current',
'view:public.incubator_view']`; with the migration restored it passes.

`config/schema_docs_baseline.json`: the five `view:public.*` keys removed;
the other 29 entries (14 columns, 9 enums, 6 functions) are unchanged
(`json.dumps(indent=2)` reproduces the original file byte for byte, so only
the six affected lines differ in the diff).

## Before

`obj_description(..., 'pg_class')` is NULL for all five views on
`NEXUS_template` and `save_01`..`save_05` (all at schema version 136, read
2026-09-30). The `md5(pg_get_viewdef(view, true))` of each view is the same on
all six databases:

| View | md5 of live definition |
| --- | --- |
| `chunk_entity_references_v` | `9ed169300fa3cec5db0a455636bc7c2c` |
| `entity_names_v` | `c0409d75c5a06995d5cf8e7e5a5f1b07` |
| `entity_relationships_v` | `c09dd8617c1e293b96ce711c1321a609` |
| `entity_tags_current` | `8ac4b88876c05ce2c1f81d83419c911b` |
| `incubator_view` | `d8910ed1448918f1809c32f71f31e4dc` |

Reader lists come from `git grep -n "<view>" -- nexus scripts tests` at
`c8dd8c85`. `nexus/agents/memnon/memnon.py:62-86` lists `entity_names_v` and
`entity_tags_current` in `READONLY_SQL_ALLOWED_TABLES`, but its only user,
`MEMNON.execute_readonly_sql` (`memnon.py:429`), has no caller under `nexus/`
or `scripts/`, so no comment cites it.

## chunk_entity_references_v

**Live definition** (`NEXUS_template`):

```sql
 SELECT ccr.chunk_id, c.entity_id, ccr.reference::text AS reference_type
   FROM chunk_character_references ccr JOIN characters c ON c.id = ccr.character_id
UNION ALL
 SELECT cfr.chunk_id, f.entity_id, NULL::text AS reference_type
   FROM chunk_faction_references cfr JOIN factions f ON f.id = cfr.faction_id
UNION ALL
 SELECT pcr.chunk_id, p.entity_id, pcr.reference_type::text AS reference_type
   FROM place_chunk_references pcr JOIN places p ON p.id = pcr.place_id;
```

**Defining migration:** `migrations/023_orrery_schema.py:423-434`; no later
migration redefines it. The live definition matches it clause for clause.

**Readers:** `scripts/orrery_sample.py:233-263` (`fetch_first_reference_chunk`:
`SELECT entity_id, MIN(chunk_id) ... GROUP BY entity_id`, used by the dry-run
harness to drop actors whose first reference postdates the anchor,
`orrery_sample.py:425-440`). Tests only: `tests/test_orrery/test_need_absence_pg.py:84`,
`tests/test_orrery/test_mood_live.py:379` (a stand-in table). No file under
`nexus/`.

| Clause | Evidence |
| --- | --- |
| One row per row of the three reference tables, with chunk_id and the referenced entity id | definition: three `UNION ALL` branches, inner join on the subtype id; `characters`, `factions`, `places` `entity_id` is NOT NULL (catalog) |
| reference_type is `reference` or `reference_type` cast to text, NULL on faction rows | definition (`ccr.reference::text`, `NULL::text`, `pcr.reference_type::text`) |
| chunk_faction_references has no role column | catalog: its columns are `chunk_id`, `faction_id` only |
| place_chunk_references keyed by place, chunk, reference type, so several rows per place and chunk | catalog: `place_chunk_references_pkey PRIMARY KEY (place_id, chunk_id, reference_type)` |
| No entity kind; leaves out `place_chunk_references.evidence` | definition projects three columns; catalog: `evidence text` on `place_chunk_references` |
| No code under nexus/ reads it; the dry-run sampler takes the first chunk per entity | `git grep` (above); `scripts/orrery_sample.py:233-263` |

**Comment:** see the listing at the end.

## entity_names_v

**Live definition** (`NEXUS_template`):

```sql
 SELECT e.id, e.kind, c.name FROM entities e JOIN characters c ON c.entity_id = e.id
  WHERE e.kind = 'character'::entity_kind
UNION ALL
 SELECT e.id, e.kind, f.name FROM entities e JOIN factions f ON f.entity_id = e.id
  WHERE e.kind = 'faction'::entity_kind
UNION ALL
 SELECT e.id, e.kind, p.name FROM entities e JOIN places p ON p.entity_id = e.id
  WHERE e.kind = 'place'::entity_kind;
```

**Defining migration:** `migrations/023_orrery_schema.py:407-421`; no later
migration redefines it.

**Readers:**

- `nexus/agents/orrery/events.py:1553-1570` (`_entity_names_sync`/`_async`: `SELECT id, name ... WHERE id = ANY`), called from `commit_orrery_tick_sync` at `events.py:803` and its async twin at `events.py:1092` with the proposal entity ids (`_entity_ids_from_proposal`, `events.py:801`).
- `nexus/agents/orrery/resolver.py:3443-3458` (`_load_entity_names`), used at `resolver.py:2677-2684` for `binding_names` and the bound narrative stub of each draft.
- `nexus/agents/orrery/worker.py:176-205` (`promote_pending_resolutions_sync`, actor name) and `worker.py:235-286` (`drain_narration_outbox_sync`, actor name).
- `nexus/agents/orrery/bleed.py:196-250` (`load_bleed_candidates`, actor and first world event target) and `bleed.py:415-436` (`record_bleed_uptake_sync`, actor).
- `nexus/agents/orrery/experiences.py:647,720-752` (`seed_character_experiences_sync`, world event actor and target names, used at `experiences.py:438-439`).
- `nexus/agents/orrery/experiences.py:1133-1226` (`_known_and_allowed_names`: every non-NULL name as `known`; owner and sources, or event participants, as `allowed`), called at `experiences.py:2080`; `experiences.py:1350-1355,1381-1382,1403-1405` reject a rendered experience that names a name in `known - allowed`.
- `nexus/agents/orrery/relationship_provenance.py:427-452` (`_claim_participants_sync`/`_async`).
- `nexus/agents/orrery/retrograde_persistence.py:2725-2742` (`_load_entity_index`), called at `retrograde_persistence.py:192,276`.
- `scripts/apply_slot2_semantic_tags.py:232-241` (all entities with kind and name).
- Tests: `tests/test_golden_path_live.py:368,385`, `tests/test_orrery/test_epistemics.py:157,395`, `tests/test_orrery/test_events.py:136` (a stub matcher), `tests/test_orrery/test_memnon_whitelist.py:11`.

| Clause | Evidence |
| --- | --- |
| One row per entity of kind character, faction, or place that has a subtype row of the same kind; id, kind, name from that row | definition; catalog: `entity_kind` is `{character,faction,place}`, `UNIQUE (entity_id)` on each subtype table, `name` NOT NULL |
| Commit tick names proposal entities | `events.py:801-803,1553-1570` |
| Resolver names draft bindings | `resolver.py:2677-2684,3443-3458` |
| Promotion and narration drains name resolution actors | `worker.py:176-205,235-286` |
| Bleed names resolution actors and event targets | `bleed.py:196-250,415-436` |
| Experience seeding names world event actors and targets | `experiences.py:647,720-752,438-439` |
| Relationship provenance names claim participants | `relationship_provenance.py:427-452` |
| Experience rendering reads every name and rejects a render naming a known entity its seed does not allow | `experiences.py:1136,1350-1355,1381-1382,1403-1405` |
| Retrograde persistence builds its entity catalog from it | `retrograde_persistence.py:192,276,2725-2742` |

## entity_relationships_v

**Live definition** (`NEXUS_template`): three `UNION ALL` branches with
columns `source_entity_id, target_entity_id, relationship_scope,
relationship_type, valence, dynamic, recent_events, history, extra_data,
valence_magnitude, valence_current`:

- `character_relationships cr` joined to `characters c1` on `character1_id` and `c2` on `character2_id`: `'character'`, `cr.relationship_type::text`, `cr.emotional_valence::text`, `cr.dynamic`, `cr.recent_events`, `cr.history`, `cr.extra_data`, `round(cr.valence_current * 5.5)::integer`, `cr.valence_current`.
- `faction_relationships fr` joined to `factions f1` on `faction1_id` and `f2` on `faction2_id`: `'faction'`, `fr.relationship_type::text`, `NULL`, `fr.current_status`, `NULL`, `fr.history`, `fr.extra_data`, `NULL`, `NULL`.
- `faction_character_relationships fcr` joined to `factions f` and `characters c`: source `f.entity_id`, target `c.entity_id`, `'faction_character'`, `fcr.role::text`, `NULL`, `fcr.current_status`, `NULL`, `fcr.history`, `fcr.extra_data`, `NULL`, `NULL`.

**Defining migration:** `migrations/088_valence_float_canonical.sql:151-198`
(earlier forms `023_orrery_schema.py:436`, `026_relationship_valence_magnitude.sql:7`).
Its view column comments (`088:200-206`) stay as they are.

**Readers** (all `WHERE relationship_scope = 'character'`):

- `nexus/agents/orrery/resolver.py:383-413` (`_load_orbit_distances`, `orrery:orbit_distance_graph`).
- `nexus/agents/orrery/resolver.py:646-668` (`hydrate_world_state`, `orrery:relationship_types`: relationship types and trust from `valence_magnitude`).
- `nexus/agents/orrery/resolver.py:1011-1034` (`_load_character_relationship_pairs`, `orrery:actor_target_bindings_character_relationships`).
- `nexus/agents/orrery/reveal.py:423-432` (`_TRUST_SQL`, `valence_magnitude`), run at `reveal.py:387,410`.
- `nexus/agents/orrery/knowledge_surfacing.py:659-689` (`_disclosure_context`, `valence_current` between the given characters).
- `nexus/agents/orrery/audit.py:2162-2178` (`entity_context`, the hover-audit payload, `audit.py:2022-2031`).
- `nexus/agents/orrery/templates.py:704` is a comment only. Tests: `tests/test_orrery/test_recruit_ally_projects.py:889` (character scope), `tests/test_orrery/test_valence_float_migration_pg.py:124,513,525`.
- The faction membership loader reads the table, not the view: `resolver.py:694-708` (`orrery:faction_memberships`, `fcr.role::text = ANY(:membership_roles)`).

**Agreement with migration 136:** `136_column_comment_corrections.sql:46-47`
says `faction_character_relationships.role` is exposed as
`entity_relationships_v.relationship_type` with scope `faction_character` and
that the resolver counts membership from the role filter; `136:49-50` says
`faction_relationships.relationship_type` is exposed with scope `faction` and
that current Orrery readers of the view select only character scope. The view
comment says the same three things.

| Clause | Evidence |
| --- | --- |
| One row per row of the three tables, scopes and source/target as listed, ends mapped to entity ids | definition (above) |
| relationship_type carries type, faction type, or member role as text | definition |
| dynamic is `dynamic` in character scope, `current_status` otherwise | definition |
| valence, recent_events, valence_magnitude, valence_current NULL outside character scope | definition |
| Every reader under nexus/ selects character scope only (resolver, reveal, knowledge surfacing, audit hover) | readers above |
| Membership loader reads faction_character_relationships directly | `resolver.py:694-708` |

## entity_tags_current

**Live definition** (`NEXUS_template`):

```sql
 SELECT et.id AS entity_tag_id, et.entity_id, e.kind AS entity_kind, t.tag,
    t.category, t.is_ephemeral, t.clearance_kind, et.applied_at,
    et.applied_at_world_time, et.source_kind, et.template_id, et.source_chunk_id
   FROM entity_tags et
     JOIN entities e ON e.id = et.entity_id
     JOIN tags t ON t.id = et.tag_id
  WHERE t.deprecated = false AND et.cleared_at IS NULL AND t.synonym_for IS NULL;
```

**Defining migration:** `migrations/064_tag_provenance_forward_fix.sql:52-70`
(first form `023_orrery_schema.py:519`, without `source_chunk_id`).

**Readers** (every one joins `entity_tags et ON et.id = etc.entity_tag_id` and
tests `et.expires_at_world_time` against a world time):

- `nexus/agents/orrery/resolver.py:446-475` (`load_current_entity_tags`, `orrery:current_tags`, predicate from `tag_activity.py:6-24`), `resolver.py:595-612` (place location classes), `resolver.py:1320,1389-1403` (`compose_actor_bindings`, `orrery:actor_bindings_ephemeral`).
- `nexus/agents/orrery/events.py:5708-5760` (`_need_applies_to_entity_sync`/`_async`, from `_load_need_debt_sync` at `events.py:5582-5594`); `events.py:6953-6990,7005-7030,7111-7146,7158-7182` (routine-zone and location-class destination choice, sync and async).
- `nexus/agents/orrery/communication.py:64-78` (`_CULTURE_TAGS_SQL`).
- `nexus/agents/orrery/audit.py:2067-2083` (`orrery_audit:entity_tags`), `audit.py:2388-2403` (`orrery_audit:place_classes`), both in `entity_context`.
- `nexus/api/faction_table_audit.py:794-815` (`_fetch_legacy_tag_rows`).
- `nexus/agents/lore/utils/entity_queries.py:29-70` (`_attributed_tag_summary_join`, whose docstring says "The view owns soft clears, deprecated tags, and synonyms; world-time starts and expiry stay separate"), used by `fetch_all_characters_with_references` (`:82,102`) and `fetch_all_factions_with_references` (`:323,339`).
- `scripts/orrery_sample.py:195-210`.
- Tests: `tests/pg_fixtures.py:1516`, `tests/test_orrery/test_tag_library.py:846,989`, `tests/test_pg_legacy_faction_tag_seed.py:80,127`, and others that match SQL text.

| Clause | Evidence |
| --- | --- |
| One row per entity_tags row with cleared_at NULL, tag not deprecated, not a synonym | definition `WHERE` |
| Tag name, category, ephemeral flag, clearance kind from tags; entity kind; provenance columns | definition select list |
| At most one row per entity and tag | catalog: `CREATE UNIQUE INDEX ix_entity_tags_current ON public.entity_tags USING btree (entity_id, tag_id) WHERE (cleared_at IS NULL)` |
| No expiry test; an expired tag stays until a clear such as the expiry sweep sets cleared_at | definition has no `expires_at_world_time`; `events.py:7944-7967` (`_sweep_expired_entity_tags_sync` sets `cleared_at = now()`) |
| Every reader under nexus/ and scripts/ joins entity_tags and applies its own expiry test | readers above |
| Named reader groups | readers above |

## incubator_view

**Live definition** (`NEXUS_template`): from `incubator i LEFT JOIN
narrative_chunks nc ON nc.id = i.parent_chunk_id WHERE i.id = true`, the
columns `i.chunk_id, i.parent_chunk_id, nc.raw_text AS parent_chunk_text,
i.user_text, i.storyteller_text, i.choice_object, i.choice_text,
i.authorial_directives, i.orrery_proposal, i.orrery_adjudications,
metadata_updates->'chronology'->>'episode_transition' AS episode_transition,
metadata_updates->'chronology'->>'time_delta_description' AS time_delta,
metadata_updates->>'world_layer' AS world_layer, metadata_updates->>'pacing'
AS pacing, COALESCE(jsonb_array_length(entity_updates->'characters'),0) +
COALESCE(jsonb_array_length(entity_updates->'locations'),0) +
COALESCE(jsonb_array_length(entity_updates->'factions'),0) AS
entity_update_count, i.entity_updates AS entity_changes, i.reference_updates
AS "references", i.status, i.session_id, i.created_at`.

**Defining migration:** `migrations/041_orrery_authority_model.sql:40-68`
(earlier forms 005, 019, 024, 040, each `DROP VIEW` then `CREATE VIEW`).

**The older comment as a lead:** `scripts/create_incubator_table.sql:70`
says "Human-readable view of incubator contents with parent chunk context".
No database carries it. "With parent chunk context" holds (the left join to
`narrative_chunks` supplies `parent_chunk_text`) and is kept; "human-readable"
is not a checkable claim and is dropped; "incubator contents" is too broad,
because the view leaves out nine of the 23 columns of today's `incubator` table (`id` among them).

**Writers of the source columns the comment describes:**

- `metadata_updates`: `nexus/api/lore_adapter.py:184,290-335` (`extract_metadata_updates`: `chronology`, `world_layer`, `scene_weather`, `scene_boundary`) and `nexus/api/narrative_generation.py:641,852-861` (`generate_bootstrap_narrative`: `chronology`, `world_layer`). Neither sets `pacing`; `git grep` finds no other `metadata_updates` constructor or `pacing` key under `nexus/` or `scripts/` (only `scripts/create_incubator_table.sql`).
- `entity_updates`: `nexus/api/lore_adapter.py:337-341` dumps `StateUpdates` (`nexus/agents/logon/apex_schema.py:531-547`: `characters`, `relationships`, `locations`, `factions`); the bootstrap writes `{}` (`narrative_generation.py:863`).

**Readers:** `nexus/api/narrative.py:1619-1638` (`GET /api/narrative/incubator`:
`SELECT * FROM incubator_view WHERE (%s IS NULL OR session_id = %s)`,
`fetchone`, or `{"message": "Incubator is empty"}`); `nexus/cli.py:1459-1472,5036`
(`nexus inspect incubator` reads that endpoint). `scripts/test_narrative_api.py:81-84`
calls the endpoint. The client function `getIncubator`
(`ui/client/src/lib/narrative-api.ts:179-180`) has no caller in `ui/client/src`.
Tests: `tests/test_api/test_backstage_endpoints_pg.py:712-730` asserts the
endpoint payload has no correspondence letter; `tests/test_api/test_slot_mutation_guard.py:117`
creates a stand-in.

| Clause | Evidence |
| --- | --- |
| At most one row, from the singleton row (id true) | definition `WHERE i.id = true`; catalog `incubator_id_check CHECK (id = true)`, primary key `id` |
| parent_chunk_text is narrative_chunks.raw_text of parent_chunk_id through a left join | definition |
| Twelve columns passed through unchanged | definition |
| episode_transition and time_delta (from time_delta_description) from metadata_updates.chronology; world_layer and pacing from metadata_updates | definition |
| No current writer sets pacing | writers above |
| entity_updates renamed entity_changes, reference_updates renamed references | definition |
| entity_update_count counts characters, locations, factions; leaves out relationships | definition; `apex_schema.py:531-547` |
| Leaves out metadata_updates, new_entities, generation_model, llm_response_id, updated_at, lore_pass_baseline, both correspondence letters | catalog `\d+ incubator` (23 columns) against the definition; `test_backstage_endpoints_pg.py:712-730` |
| GET /api/narrative/incubator returns its row, filtered by session_id when given; nexus inspect incubator reads the endpoint | `narrative.py:1619-1638`; `cli.py:1459-1472,5036` |

## After: Listing From a Migrated Disposable Clone

Command (from the worktree root, gateway variables unset; the script
creates a `qa640_819s1_listing_*` clone with `tests.pg_fixtures.disposable_slot_database`,
which copies `NEXUS_template` schema and seed rows and runs `scripts/migrate.py`
on the clone only, reads `obj_description` for each view, compares it with the
string literal in `migrations/137_view_comments.sql` (with `''` unescaped), and
drops the clone):

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY docs/qa/819-view-comments/listing.py
```

The migration log showed `Applied: 137_view_comments`; the script exited 0, and
no `qa640_819s1*` database remained afterward.

```
clone qa640_819s1_listing_* at schema version 137

chunk_entity_references_v (byte-identical to migration text: True, 804 bytes)
Chunk references of characters, factions, and places in one shape: one row for each row of chunk_character_references, chunk_faction_references, and place_chunk_references, carrying its chunk_id and the entity_id of the referenced character, faction, or place. reference_type is chunk_character_references.reference or place_chunk_references.reference_type cast to text, and is NULL on every faction row, because chunk_faction_references has no role column. place_chunk_references keys its rows by place, chunk, and reference type, so one place can have several rows for one chunk. The view carries no entity kind and leaves out place_chunk_references.evidence. No code under nexus/ reads it; the Orrery dry-run sampler (scripts/orrery_sample.py) takes the first referencing chunk of each entity from it.

entity_names_v (byte-identical to migration text: True, 779 bytes)
Name of each character, faction, and place entity: one row for each entities row of kind character, faction, or place that has a characters, factions, or places row of the same kind, carrying the entity id, the kind, and the name from that row. Orrery code joins it to put names on entity ids: the commit tick for proposal entities, the resolver for draft bindings, the resolution promotion and narration drains for resolution actors, bleed for resolution actors and event targets, experience seeding for world event actors and targets, and relationship provenance for claim participants. Experience rendering reads every name and rejects a rendered experience that names a known entity its seed does not allow, and Retrograde persistence builds its entity catalog from the view.

entity_relationships_v (byte-identical to migration text: True, 1028 bytes)
Relationship edges between entities in one shape: one row for each row of character_relationships (relationship_scope character, source character1, target character2), faction_relationships (scope faction, source faction1, target faction2), and faction_character_relationships (scope faction_character, source the faction, target the character), with both ends mapped to entity ids. relationship_type carries the character relationship type, the faction relationship type, or the member role as text; dynamic carries dynamic in character scope and current_status in the other two; valence, recent_events, valence_magnitude, and valence_current are NULL outside character scope. Every reader under nexus/ selects character scope only: the Orrery resolver (orbit distances, relationship types and trust, actor-target bindings), secret reveal (trust), knowledge surfacing (valence between characters), and the audit entity hover. The resolver faction membership loader reads faction_character_relationships directly, not this view.

entity_tags_current (byte-identical to migration text: True, 1026 bytes)
Uncleared tag applications: one row for each entity_tags row whose cleared_at is NULL and whose tag is neither deprecated nor a synonym (tags.synonym_for NULL), carrying the tag name, category, ephemeral flag, and clearance kind from tags, the entity kind, and the application provenance (applied_at, applied_at_world_time, source_kind, template_id, source_chunk_id). A partial unique index on entity_tags allows at most one such row per entity and tag. The view applies no expiry test: a tag whose expires_at_world_time has passed stays here until a clear, such as the expiry sweep, sets cleared_at. Every reader under nexus/ and scripts/ joins entity_tags on entity_tag_id and applies its own expires_at_world_time test: the Orrery resolver (current tags, place location classes, actors with ephemeral tags), need applicability and routine destination choice in the Orrery events module, communication culture tags, the audit entity hover, the faction table audit, and the character and faction dossiers of the turn context.

incubator_view (byte-identical to migration text: True, 1116 bytes)
The pending draft with its parent chunk text: at most one row, from the singleton incubator row (id true), with narrative_chunks.raw_text of parent_chunk_id as parent_chunk_text through a left join. It passes through chunk_id, parent_chunk_id, user_text, storyteller_text, choice_object, choice_text, authorial_directives, orrery_proposal, orrery_adjudications, status, session_id, and created_at; lifts episode_transition and time_delta_description (as time_delta) from metadata_updates.chronology, and world_layer and pacing from metadata_updates, although no current writer sets pacing; renames entity_updates to entity_changes and reference_updates to references; and counts entity_update_count as the lengths of the characters, locations, and factions arrays of entity_updates, leaving out its relationships array. It leaves out metadata_updates itself, new_entities, generation_model, llm_response_id, updated_at, lore_pass_baseline, and both staged correspondence letters. GET /api/narrative/incubator returns its row, filtered by session_id when one is given, and nexus inspect incubator reads that endpoint.
```

## Gates

All from the worktree root with `PY=/Users/pythagor/nexus/.venv/bin/python`,
`PYTHONPATH=$PWD`, and `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT`
unset, after the rebase onto `origin/main` at `88fddbde` (the two new commits
touch none of the files cited here; the citations hold at both `c8dd8c85` and
`88fddbde`).

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_enum_column_comment_labels_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
133 passed in 33.89s

$ $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.

$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2614 passed, 406 skipped, 8 warnings in 424.78s (0:07:04)

$ $PY -m pytest -q tests/test_api tests/test_orrery tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1849 passed, 742 skipped, 7 warnings in 57.36s
```

`tests/test_reachability.py` alone before the rebase: `38 passed`.

The offline skips are the PostgreSQL-marked tests (`NEXUS_RUN_POSTGRES`
unset). Landing: the coordinator applies migration 137 fleet-wide
(`NEXUS_template`, `save_02`..`save_05`, and `save_01` through
`--write-locked-slot`). Comments only, so no restart is owed.

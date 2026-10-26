# Verification: Correct the Incubator Column Comments (Issue #1106, Order 1106-S1)

Branch `claude/1106-incubator-comments`, cut from `origin/main` at `c7ae2988`.
Migration `migrations/152_incubator_column_comments.sql` replaces ten
`public.incubator` column comments and the `public.clear_incubator()` function
comment (decision 1106-D1 and its amendment at order freeze, which adds
`choice_object` and `generation_model`). Every database read below ran with
`PGOPTIONS='-c default_transaction_read_only=on'`; no `save_NN`,
`NEXUS_template` or `ref_codex_bakeoff_2026_07` was written. Test and listing
runs used disposable `qa640_` clones.

The reads and tails below were re-run on commit `4931cf24` (the migration and
guard test as reviewed) after review asked for every command and every tail;
the commit that records them changes only this file. Each PostgreSQL run is
preceded by the `uptime` read taken just before it. `$PY` is
`/Users/pythagor/nexus/.venv/bin/python`, and every PostgreSQL run had
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.

## Migration Number Check (Decision 1106-D3)

```
$ gh pr list --repo pythagorakase/nexus --state open --json number,headRefName
[]
$ for r in $(git for-each-ref --format='%(refname)' refs/heads refs/remotes/origin); do
    git ls-tree --name-only $r migrations/ | grep -E 'migrations/15[2-9]'; done
(no output: no local or origin ref carries a migration numbered 152 to 159)
```

The newest migration on `origin/main` is `151_relationship_entity_ids.sql`.

## Before Texts (Read Only, 2026-10-26)

md5 over every incubator column comment, in attnum order (the loop as run):

```
$ for db in NEXUS_template save_01 save_02 save_03 save_04 save_05; do
    echo "== $db"
    PGOPTIONS='-c default_transaction_read_only=on' psql -d "$db" -Atc "SELECT md5(string_agg(coalesce(col_description('public.incubator'::regclass, attnum),''), '|' ORDER BY attnum)) FROM pg_attribute WHERE attrelid = 'public.incubator'::regclass AND attnum > 0 AND NOT attisdropped"
  done
== NEXUS_template
6c46fa96543ffe20d5a9f2dbae7cb923
== save_01
6c46fa96543ffe20d5a9f2dbae7cb923
== save_02
6c46fa96543ffe20d5a9f2dbae7cb923
== save_03
6c46fa96543ffe20d5a9f2dbae7cb923
== save_04
6c46fa96543ffe20d5a9f2dbae7cb923
== save_05
6c46fa96543ffe20d5a9f2dbae7cb923
```

`NEXUS_template` before texts:

```
$ PGOPTIONS='-c default_transaction_read_only=on' psql -d NEXUS_template -Atc "SELECT attname, col_description('public.incubator'::regclass, attnum) FROM pg_attribute WHERE attrelid = 'public.incubator'::regclass AND attnum > 0 AND NOT attisdropped ORDER BY attnum"
id|Singleton constraint - only one incubation at a time
chunk_id|NULL while provisional; assigned from narrative_chunks INSERT RETURNING id inside acceptance before the incubator row is deleted.
parent_chunk_id|ID of existing chunk being continued from
user_text|User completion text for the parent chunk
storyteller_text|AI-generated storyteller text for the new chunk
metadata_updates|JSON: {episode_transition, time_delta_seconds, time_delta_description, world_layer, pacing}
entity_updates|JSON array of entity state changes: [{type, id, field, old_value, new_value}]
reference_updates|JSON: {character_present: [], character_referenced: [], place_referenced: []}
session_id|UUID for tracking regeneration attempts
llm_response_id|OpenAI or LM Studio response ID for debugging
status|Status: provisional (pending approval), approved (ready to commit), committed (written to main tables)
created_at|Database timestamp of the incubator insert or most recent conditional replacement; replacement rewrites it to NOW().
updated_at|Stored row update timestamp; initialized to database transaction time.
choice_object|Structured choice data: {presented: string[], selected: {label, text, edited}}
choice_text|Resolved user response text for the pending chunk. Copied into narrative_chunks.choice_text at promotion.
orrery_proposal|No-write OrreryTickProposal generated during preview; stamped into canonical Orrery tables only when the incubator chunk is accepted.
authorial_directives|Provisional Storyteller-authored retrieval directives to persist when accepted.
orrery_adjudications|Skald-authored defer/replace/void rulings for Orrery proposals in the provisional chunk.
new_entities|Skald new-entity declarations (apex_schema.NewEntityDeclaration list): kind, name, one-line summary, optional registered tag/pair-tag hints. Processed at commit time: hints validated against the live registries, stub rows created when absent, and maturation jobs enqueued when the declared name appears in the committed chunk (spec decisions 9/12).
generation_model|The registry model id that produced the accepted storyteller text; NULL for pre-082 history and rows not produced by the storyteller pipeline.
correspondence_writer_letter|Player-invisible provisional writer or single-pass letter; copied to the immutable journal only when this incubator row is accepted.
correspondence_gaia_letter|Player-invisible provisional Gaia reply; copied to the immutable journal only when this incubator row is accepted.
lore_pass_baseline|Unbound versioned Pass-2 baseline staged atomically with provisional storyteller prose and discarded on rejection.
```

The same query on `save_01` to `save_05`, each saved to a file and compared with
the template output (the loop as run, in the `1106-S1` scratch directory):

```
$ for db in NEXUS_template save_01 save_02 save_03 save_04 save_05; do
    PGOPTIONS='-c default_transaction_read_only=on' psql -d "$db" -Atc "SELECT attname, col_description('public.incubator'::regclass, attnum) FROM pg_attribute WHERE attrelid = 'public.incubator'::regclass AND attnum > 0 AND NOT attisdropped ORDER BY attnum" > "before_$db.txt"
  done
$ wc -l before_*.txt
      23 before_NEXUS_template.txt
      23 before_save_01.txt
      23 before_save_02.txt
      23 before_save_03.txt
      23 before_save_04.txt
      23 before_save_05.txt
     138 total
$ for db in save_01 save_02 save_03 save_04 save_05; do
    diff -q before_NEXUS_template.txt "before_$db.txt" && echo "before_$db.txt: identical to before_NEXUS_template.txt"
  done
before_save_01.txt: identical to before_NEXUS_template.txt
before_save_02.txt: identical to before_NEXUS_template.txt
before_save_03.txt: identical to before_NEXUS_template.txt
before_save_04.txt: identical to before_NEXUS_template.txt
before_save_05.txt: identical to before_NEXUS_template.txt
```

Function comment before (`NEXUS_template`):

```
$ PGOPTIONS='-c default_transaction_read_only=on' psql -d NEXUS_template -Atc "select obj_description('public.clear_incubator()'::regprocedure,'pg_proc'), pg_get_functiondef('public.clear_incubator()'::regprocedure)"
Clear the incubator after content is approved and committed|CREATE OR REPLACE FUNCTION public.clear_incubator()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    DELETE FROM incubator WHERE id = TRUE;
END;
$function$

```

## Code Searches

```
$ git grep -nw response_id -- nexus
nexus/api/lore_adapter.py:201:        "llm_response_id": getattr(response, "response_id", None),

$ git grep -n authorial_directives -- nexus
nexus/agents/memnon/memnon.py:81:    authorial_directives = Column(
nexus/agents/memnon/utils/db_schema.py:30:    authorial_directives = Column(
nexus/agents/orrery/job_queues.py:111:              AND NOT (coalesce(n.authorial_directives, '[]'::jsonb) @> %s::jsonb)
nexus/agents/orrery/reconstruction.py:46:        f"COALESCE({table_alias}.authorial_directives, '[]'::jsonb) "
nexus/agents/orrery/retrograde_orchestrator.py:666:          AND nc.authorial_directives @> %s::jsonb
nexus/agents/orrery/retrograde_persistence.py:2548:            authorial_directives
nexus/agents/orrery/retrograde_persistence.py:2595:        WHERE authorial_directives @> %s::jsonb

$ git grep -n clear_incubator
docs/qa/807-one-commit-path/verification.md:28:helper (`fetch_incubator_data`, `insert_narrative_chunk`, `clear_incubator`)
docs/qa/819-ratchet-extension/verification.md:112:  (`public.clear_incubator()`), `removed-view-comment` (`public.narrative_view`).
nexus/api/narrative.py:1660:async def clear_incubator(
scripts/create_incubator_table.sql:73:CREATE OR REPLACE FUNCTION clear_incubator() RETURNS VOID AS $$
scripts/create_incubator_table.sql:79:COMMENT ON FUNCTION clear_incubator IS 'Clear the incubator after content is approved and committed';
scripts/test_narrative_api.py:109:def test_clear_incubator(slot: int):
scripts/test_narrative_api.py:176:            test_clear_incubator(args.slot)
tests/test_schema_documentation_pg.py:288:            "COMMENT ON FUNCTION public.clear_incubator() IS NULL",
tests/test_schema_documentation_pg.py:289:            "function:public.clear_incubator()",
```

`scripts/test_narrative_api.py:109` calls the HTTP route `DELETE
/api/narrative/incubator`, not the SQL function; `tests/test_schema_documentation_pg.py:288`
clears the comment to probe the schema-documentation ratchet. No SQL caller of
`clear_incubator()` exists in `nexus/` or `scripts/`.

These searches were recorded on the base commit `c7ae2988`. Re-run on
`4931cf24` (the same searches pinned to that tree), the first two return the
same lines, and `git grep -n clear_incubator` adds only this branch's own files
(migration 152, the guard test, `listing.py` and this file):

```
$ git grep -nw response_id 4931cf24 -- nexus
4931cf24:nexus/api/lore_adapter.py:201:        "llm_response_id": getattr(response, "response_id", None),

$ git grep -n authorial_directives 4931cf24 -- nexus
4931cf24:nexus/agents/memnon/memnon.py:81:    authorial_directives = Column(
4931cf24:nexus/agents/memnon/utils/db_schema.py:30:    authorial_directives = Column(
4931cf24:nexus/agents/orrery/job_queues.py:111:              AND NOT (coalesce(n.authorial_directives, '[]'::jsonb) @> %s::jsonb)
4931cf24:nexus/agents/orrery/reconstruction.py:46:        f"COALESCE({table_alias}.authorial_directives, '[]'::jsonb) "
4931cf24:nexus/agents/orrery/retrograde_orchestrator.py:666:          AND nc.authorial_directives @> %s::jsonb
4931cf24:nexus/agents/orrery/retrograde_persistence.py:2548:            authorial_directives
4931cf24:nexus/agents/orrery/retrograde_persistence.py:2595:        WHERE authorial_directives @> %s::jsonb

$ git grep -n clear_incubator 4931cf24
4931cf24:docs/qa/1106-incubator-comments/listing.py:4:public.clear_incubator()) with the literal in migration 152, prints the live
4931cf24:docs/qa/1106-incubator-comments/listing.py:28:FUNCTION = "clear_incubator()"
4931cf24:docs/qa/1106-incubator-comments/listing.py:31:    r"|FUNCTION public\.(clear_incubator\(\))) IS\n    '((?:[^']|'')*)';"
4931cf24:docs/qa/1106-incubator-comments/listing.py:63:                    "'public.clear_incubator()'::regprocedure, 'pg_proc')"
4931cf24:docs/qa/1106-incubator-comments/verification.md:5:`public.incubator` column comments and the `public.clear_incubator()` function
4931cf24:docs/qa/1106-incubator-comments/verification.md:79:$ psql -d NEXUS_template -Atc "select obj_description('public.clear_incubator()'::regprocedure,'pg_proc'), pg_get_functiondef('public.clear_incubator()'::regprocedure)"
4931cf24:docs/qa/1106-incubator-comments/verification.md:80:Clear the incubator after content is approved and committed|CREATE OR REPLACE FUNCTION public.clear_incubator()
4931cf24:docs/qa/1106-incubator-comments/verification.md:105:$ git grep -n clear_incubator
4931cf24:docs/qa/1106-incubator-comments/verification.md:106:docs/qa/807-one-commit-path/verification.md:28:helper (`fetch_incubator_data`, `insert_narrative_chunk`, `clear_incubator`)
4931cf24:docs/qa/1106-incubator-comments/verification.md:107:docs/qa/819-ratchet-extension/verification.md:112:  (`public.clear_incubator()`), `removed-view-comment` (`public.narrative_view`).
4931cf24:docs/qa/1106-incubator-comments/verification.md:108:nexus/api/narrative.py:1660:async def clear_incubator(
4931cf24:docs/qa/1106-incubator-comments/verification.md:109:scripts/create_incubator_table.sql:73:CREATE OR REPLACE FUNCTION clear_incubator() RETURNS VOID AS $$
4931cf24:docs/qa/1106-incubator-comments/verification.md:110:scripts/create_incubator_table.sql:79:COMMENT ON FUNCTION clear_incubator IS 'Clear the incubator after content is approved and committed';
4931cf24:docs/qa/1106-incubator-comments/verification.md:111:scripts/test_narrative_api.py:109:def test_clear_incubator(slot: int):
4931cf24:docs/qa/1106-incubator-comments/verification.md:112:scripts/test_narrative_api.py:176:            test_clear_incubator(args.slot)
4931cf24:docs/qa/1106-incubator-comments/verification.md:113:tests/test_schema_documentation_pg.py:288:            "COMMENT ON FUNCTION public.clear_incubator() IS NULL",
4931cf24:docs/qa/1106-incubator-comments/verification.md:114:tests/test_schema_documentation_pg.py:289:            "function:public.clear_incubator()",
4931cf24:docs/qa/1106-incubator-comments/verification.md:120:`clear_incubator()` exists in `nexus/` or `scripts/`.
4931cf24:docs/qa/1106-incubator-comments/verification.md:159:FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[clear_incubator()]
4931cf24:docs/qa/1106-incubator-comments/verification.md:210:clear_incubator() (byte-identical to migration text: True, 210 bytes)
4931cf24:docs/qa/807-one-commit-path/verification.md:28:helper (`fetch_incubator_data`, `insert_narrative_chunk`, `clear_incubator`)
4931cf24:docs/qa/819-ratchet-extension/verification.md:112:  (`public.clear_incubator()`), `removed-view-comment` (`public.narrative_view`).
4931cf24:migrations/152_incubator_column_comments.sql:4:-- public.incubator and the COMMENT ON FUNCTION text of public.clear_incubator()
4931cf24:migrations/152_incubator_column_comments.sql:39:-- clear_incubator() (function): catalog body DELETE FROM incubator WHERE id = TRUE; no SQL caller in nexus/ or scripts/; nexus/api/narrative.py:1668-1672; nexus/api/slot_endpoints.py:262-265; nexus/api/commit_handler_sync.py:880-889
4931cf24:migrations/152_incubator_column_comments.sql:77:COMMENT ON FUNCTION public.clear_incubator() IS
4931cf24:nexus/api/narrative.py:1660:async def clear_incubator(
4931cf24:scripts/create_incubator_table.sql:73:CREATE OR REPLACE FUNCTION clear_incubator() RETURNS VOID AS $$
4931cf24:scripts/create_incubator_table.sql:79:COMMENT ON FUNCTION clear_incubator IS 'Clear the incubator after content is approved and committed';
4931cf24:scripts/test_narrative_api.py:109:def test_clear_incubator(slot: int):
4931cf24:scripts/test_narrative_api.py:176:            test_clear_incubator(args.slot)
4931cf24:tests/test_incubator_column_comments_pg.py:4:and the comment on ``public.clear_incubator()``. These tests read
4931cf24:tests/test_incubator_column_comments_pg.py:39:FUNCTION = "clear_incubator()"
4931cf24:tests/test_incubator_column_comments_pg.py:131:SELECT obj_description('public.clear_incubator()'::regprocedure, 'pg_proc')
4931cf24:tests/test_schema_documentation_pg.py:288:            "COMMENT ON FUNCTION public.clear_incubator() IS NULL",
4931cf24:tests/test_schema_documentation_pg.py:289:            "function:public.clear_incubator()",
```

## Fleet Facts Behind the Comments (Read Only)

`parent_chunk_id = 0` names no chunk, and the pending drafts on `save_03` and
`save_04` hold the values the new comments state:

```
$ for db in save_01 save_02 save_03 save_04 save_05; do
    echo "== $db"
    PGOPTIONS='-c default_transaction_read_only=on' psql -d "$db" -Atc "SELECT 'min_id=' || coalesce(min(id)::text, 'none') || ' has_id0=' || coalesce(bool_or(id = 0), false)::text FROM narrative_chunks"
    PGOPTIONS='-c default_transaction_read_only=on' psql -d "$db" -Atc "SELECT 'incubator: status=' || status || ' parent=' || parent_chunk_id || ' authorial_directives=' || authorial_directives::text || ' llm_response_id=' || coalesce(llm_response_id, 'NULL') || ' generation_model_null=' || (generation_model IS NULL)::text FROM incubator"
  done
== save_01
min_id=1 has_id0=false
== save_02
min_id=1 has_id0=false
== save_03
min_id=1 has_id0=false
incubator: status=provisional parent=100 authorial_directives=[] llm_response_id=NULL generation_model_null=false
== save_04
min_id=1 has_id0=false
incubator: status=provisional parent=49 authorial_directives=[] llm_response_id=NULL generation_model_null=false
== save_05
min_id=none has_id0=false
```

## Red Run (Test File Present, Migration 152 Absent)

First recorded at `a6595dbe` (test file committed, migration not yet written):
15 failed, 6 passed. Re-run on `4931cf24` by moving the migration file out of
the worktree for the run and back afterwards (`git status --short` shows the
deletion during the run and a clean tree after):

```
$ mv migrations/152_incubator_column_comments.sql <scratch>/1106-S1/152_aside.sql && git status --short
 D migrations/152_incubator_column_comments.sql
$ uptime
14:01  up  2:39, 5 users, load averages: 5.57 6.91 6.01
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_incubator_column_comments_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_1106_comments_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_incubator_column_comments_pg.py::test_json_column_comment_lists_its_model_keys[entity_updates]
FAILED tests/test_incubator_column_comments_pg.py::test_json_column_comment_lists_its_model_keys[metadata_updates]
FAILED tests/test_incubator_column_comments_pg.py::test_json_column_comment_lists_its_model_keys[reference_updates]
FAILED tests/test_incubator_column_comments_pg.py::test_corrected_comments_drop_retired_tokens
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[authorial_directives]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[choice_object]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[clear_incubator()]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[entity_updates]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[generation_model]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[llm_response_id]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[metadata_updates]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[orrery_proposal]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[parent_chunk_id]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[reference_updates]
FAILED tests/test_incubator_column_comments_pg.py::test_every_corrected_comment_replaced_its_pre_152_text[status]
15 failed, 6 passed in 2.03s
(exit 1)
$ mv <scratch>/1106-S1/152_aside.sql migrations/152_incubator_column_comments.sql && git status --short
(no output: clean tree)
```

The first test (three cases), the fourth test and the fifth test (eleven
cases) fail; the two rejection tests (six cases) pass.

## After Texts (Migrated qa640_ Clone)

```
$ uptime
14:03  up  2:40, 5 users, load averages: 8.05 7.31 6.24
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY docs/qa/1106-incubator-comments/listing.py
clone qa640_1106_listing_* at schema version 152

metadata_updates (byte-identical to migration text: True, 1135 bytes)
Chunk metadata the storyteller declared for the pending draft, an apex_schema.ChunkMetadataUpdate object with keys: {chronology, world_layer, scene_weather, scene_boundary} and chronology.keys: {episode_transition, time_delta_minutes, time_delta_hours, time_delta_days, time_delta_description}. On a storyteller turn lore_adapter.extract_metadata_updates writes chronology when the response carries one, world_layer whenever it carries metadata, scene_weather only when the Skald sets one, and scene_boundary only when it is true; a response without metadata stores an empty object. The bootstrap opening writes chronology (new_episode, 0 minutes, Story begins) and world_layer primary. Staging and acceptance validate it against ChunkMetadataUpdate and ChronologyUpdate. Acceptance derives the new chunk season, episode and time delta from chronology (the scene is the parent scene plus one), writes world_layer (primary when absent) and scene_weather to chunk_metadata, and after the opening enqueues a scene experience job when scene_boundary is true. incubator_view lifts episode_transition, time_delta_description and world_layer.

entity_updates (byte-identical to migration text: True, 791 bytes)
State changes the storyteller declared for the pending draft, an apex_schema.StateUpdates object with keys: {characters, relationships, locations, factions}, each an array. On a storyteller turn lore_adapter.extract_entity_updates stores the whole object with None fields left out, so all four arrays are present; the bootstrap opening stores an empty object. Both writers set the column, so its empty-array default is never kept. Staging and acceptance validate it against StateUpdates. When it is not empty, acceptance resolves its entity ids and applies it to the entity tables (apply_state_updates_sync); the stored value also goes to the Orrery tick as the storyteller state updates. incubator_view exposes it as entity_changes and counts its characters, locations and factions entries.

reference_updates (byte-identical to migration text: True, 847 bytes)
Existing entities the pending draft names, an apex_schema.ReferencedEntities object with keys: {characters, places, factions, departures}. On a storyteller turn lore_adapter.extract_reference_updates always writes the characters, places and factions arrays, and adds departures (authored exits retained internally for reconciliation) only when there are any. The bootstrap opening writes the player character as present when known, other characters the prose names as mentioned, the starting place as setting, and an empty factions array. Staging and acceptance validate it against ReferencedEntities. Acceptance resolves characters, places and factions to ids, treats departures as explicit exits while it reconciles the scene with the parent roster, and writes the new chunk roster (roster.write_roster). incubator_view exposes it as references.

status (byte-identical to migration text: True, 522 bytes)
Draft state, always provisional. Both writers set provisional (lore_adapter.response_to_incubator and narrative_generation.generate_bootstrap_narrative), a replaced draft is written as provisional again, and no code writes another value. Acceptance deletes the row in the transaction that creates the new chunk, and DELETE /api/narrative/incubator and slot undo delete a discarded draft, so no other value occurs. Acceptance selects it without acting on it; incubator_view and GET /api/narrative/incubator pass it through.

llm_response_id (byte-identical to migration text: True, 337 bytes)
Debugging id of the generation behind the pending draft. The bootstrap opening stores bootstrap_ followed by eight hex digits. Storyteller turns store NULL: lore_adapter.response_to_incubator reads a response_id attribute that no StoryTurnResponse model defines. Acceptance selects it and copies it nowhere; incubator_view leaves it out.

authorial_directives (byte-identical to migration text: True, 314 bytes)
Unused; every row keeps the default empty array. Migration 040 added it for storyteller retrieval directives, but no current code writes it: neither incubator writer names it, and acceptance does not copy it to narrative_chunks.authorial_directives. incubator_view and GET /api/narrative/incubator pass it through.

orrery_proposal (byte-identical to migration text: True, 627 bytes)
Staged Orrery state for the pending draft; NULL for the bootstrap opening. On a storyteller turn lore_adapter stores the no-write OrreryTickProposal (OrreryTickProposal.to_dict) when one was resolved, plus the key _bleed_offer_resolution_ids: the orrery_resolutions ids whose Bleed offers this exact draft carried, possibly none. Without a proposal the object holds that key alone. Acceptance separates the two (lore_adapter.split_staged_orrery_payload), passes the proposal to the Orrery tick, which stamps it into the canonical Orrery tables, and counts each listed offer against the parent chunk (bleed.record_bleed_offers).

parent_chunk_id (byte-identical to migration text: True, 231 bytes)
Id of the accepted chunk the pending draft continues, or 0 for the bootstrap opening, which has no parent; the column has no foreign key. Draft validation and acceptance treat 0 as the opening and read no parent metadata or roster.

choice_object (byte-identical to migration text: True, 1072 bytes)
Choices the pending draft offers and the player selection among them, an object with presented (the choice texts) and selected, plus edited true when the player sent an edited version of the selected choice. A storyteller turn (lore_adapter.extract_choice_object) stores the presented choices with selected null when the response carries at least two, and the bootstrap opening does so when its response carries any; otherwise the column is NULL. When the player responds, the continue path and POST /api/narrative/select-choice rewrite it in the shape choice_handling.normalize_choice_object returns: selected is the 1-indexed number of the chosen presented choice, or null for freeform input (the continue path gives freeform text identical to a presented choice that number), and edited sits at the top level beside selected while the edited text itself lives in choice_text. Acceptance copies the normalized object to narrative_chunks.choice_object, filling a blank choice_text from the selected choice; incubator_view and GET /api/narrative/incubator pass it through.

generation_model (byte-identical to migration text: True, 359 bytes)
Registry model id that produced the pending storyteller text. write_to_incubator refuses a draft whose model id is missing or blank, and both the storyteller turn and the bootstrap opening are staged through it, so no current row holds NULL, although the column allows it. Acceptance copies it to chunk_metadata.generation_model; incubator_view leaves it out.

clear_incubator() (byte-identical to migration text: True, 210 bytes)
Deletes the singleton incubator row, discarding any pending draft. No code in nexus/ or scripts/ calls it: DELETE /api/narrative/incubator, slot undo and acceptance each delete the row with their own statement.
(exit 0; the psql restore chatter of the clone fixture on stdout before the
first line above, and the pg_dump circular-foreign-key warnings on stderr, are
omitted)
```

## Green Runs

```
$ uptime
14:01  up  2:39, 5 users, load averages: 5.44 6.86 5.99
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_incubator_column_comments_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_1106_comments_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
21 passed in 2.24s
```

```
$ uptime
14:01  up  2:39, 5 users, load averages: 5.37 6.80 5.98
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_incubator_column_comments_pg.py tests/test_enum_column_comment_labels_pg.py tests/test_schema_documentation_pg.py tests/test_migration_comment_lint.py tests/test_orrery/test_migrate.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 19 targets: postgres, qa640_1106_comments_*, qa640_816_lifecycle_test_provider, qa640_819_labels_*, qa640_885_ren_replay_* x4, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:59433 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:59436 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:59433 (psycopg2), save_04@local:59436 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
197 passed, 2 skipped, 2 warnings in 66.62s (0:01:06)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The two skips are the `@requires_corpus` owner-corpus probes at
`tests/test_orrery/test_card_identity.py:122`, which run only under
`NEXUS_RUN_CORPUS=1`. `test_migration_sequence_has_only_known_gaps` passes.

## Other Gates

```
$ PYTHONPATH=$PWD $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.

$ uptime
14:03  up  2:41, 5 users, load averages: 7.93 7.33 6.27
$ PGOPTIONS='-c default_transaction_read_only=on' PYTHONPATH=$PWD $PY scripts/migrate.py --status | grep -E '^\S|\[ \]'
Found 149 managed migrations in /Users/pythagor/nexus/.claude/worktrees/1106-S1/migrations
NEXUS_template:
  [ ] 152_incubator_column_comments
save_01: [LOCKED]
save_02:
  [ ] 152_incubator_column_comments
save_03:
  [ ] 152_incubator_column_comments
save_04:
  [ ] 152_incubator_column_comments
save_05:
  [ ] 152_incubator_column_comments

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

## Static Checks

```
$ $PY -m black --check tests/test_incubator_column_comments_pg.py docs/qa/1106-incubator-comments/listing.py
All done! ✨ 🍰 ✨
2 files would be left unchanged.
(exit 0)
$ $PY -m flake8 tests/test_incubator_column_comments_pg.py docs/qa/1106-incubator-comments/listing.py
(exit 0)
$ $PY -m mypy --explicit-package-bases tests/test_incubator_column_comments_pg.py docs/qa/1106-incubator-comments/listing.py
Success: no issues found in 2 source files
(exit 0)
```

Both files are new, so there is no `origin/main` version to compare.

## Offline Suites

The first offline command of the order (`tests --ignore=tests/test_api
--ignore=tests/test_orrery`) ran 624.54s before review, longer than the
ten-minute command limit, so it was re-run as two pieces that together cover
the same files (2151 + 1045 = 3196 passed, 610 + 89 = 699 skipped, as before).
The earlier single run, as recorded in this file at `4931cf24`:

```
$ nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
3196 passed, 699 skipped, 8 warnings in 624.54s (0:10:24)
```

```
$ nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/fixtures --ignore=tests/proofs --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
2151 passed, 610 skipped, 8 warnings in 531.16s (0:08:51)
(exit 0)
$ nice -n 15 $PY -m pytest -q tests/config tests/fixtures tests/proofs tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1045 passed, 89 skipped, 7 warnings in 167.12s (0:02:47)
(exit 0)
$ nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 49.73s
(exit 0)
$ $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 19.79s
(exit 0)
```

No file this branch changes is a declared `sources:` entry of `AGENTS.md`,
`docs/turn_flow_sequence.md` or any other `status: canonical` document.

## Review Fix: The Bite Test Goes Through the Guard (Commit `0ae1cb65`)

Review found that `test_pre_152_keys_in_convention_are_rejected` did its own
set arithmetic and never called `_model_mismatches`, the comparison the live
guard `test_json_column_comment_lists_its_model_keys` uses. Commit `0ae1cb65`
keeps the `_key_sets` prefix assertion and adds
`assert _model_mismatches(text, model, {}) == [f"top level ({model.__name__}): extra {sorted(extra)}, missing {sorted(missing)}"]`
(the empty nested map because the old key lists carry only a top-level set).
Only the test file changed, so the migration, listing and offline results above
still hold. Run on `0ae1cb65`:

```
$ uptime
14:24  up  3:02, 5 users, load averages: 18.74 13.25 11.00
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_incubator_column_comments_pg.py
.....................                                                    [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_1106_comments_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
21 passed in 2.48s
$ $PY -m pytest -q tests/test_doc_front_matter.py
66 passed, 5 warnings in 8.64s
$ $PY -m black --check tests/test_incubator_column_comments_pg.py
All done! ✨ 🍰 ✨
1 file would be left unchanged.
$ $PY -m flake8 tests/test_incubator_column_comments_pg.py
(exit 0)
$ $PY -m mypy --explicit-package-bases tests/test_incubator_column_comments_pg.py
Success: no issues found in 1 source file
```

The new assertion bites. A scratch script (session scratchpad,
`1106-S1/bite_check.py`) replaces `_model_mismatches` in memory with one that
reports nothing and calls the test for each column; all three fail:

```
$ PYTHONPATH=$PWD $PY <scratchpad>/1106-S1/bite_check.py
bite test failed for: ['entity_updates', 'metadata_updates', 'reference_updates']
(exit 0)
```

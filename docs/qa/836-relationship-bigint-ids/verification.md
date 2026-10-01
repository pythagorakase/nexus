# Verification: Migration 139 Widens character_relationships Ids to bigint (#836 S2)

Date: 2026-09-30. Code at `41783c1d` (origin/main; unchanged at push time).
Every database read below was read-only (`default_transaction_read_only=on`
or a read-only psycopg2 session). No `save_NN`, `NEXUS_template` or
`ref_codex_bakeoff_2026_07` was written. No paid call; no gateway started.

## Fleet Listing (Read-Only)

`max(schema_migrations.version)`, the two id types, and per view
`md5(pg_get_viewdef(oid, true))`, `md5(obj_description(oid, 'pg_class'))`,
`relacl`, owner; then `count(*)` of `character_relationships`.

```
== NEXUS_template
138|character1_id:integer,character2_id:integer
character_relationship_pairs|b6a065311f82626698e5231b3b47b7bc|7c8f9eae92a3c251388e75dfabeaaf4b||pythagor
character_relationship_summary|5377171baacbe9e70f04f984ebc37972|3a4e2c33216a42861b66302fb93e28c0||pythagor
entity_relationships_v|c09dd8617c1e293b96ce711c1321a609|8d50c14c081bbfc2f8bd8d9499af393f||pythagor
0
== save_01
138|character1_id:integer,character2_id:integer
character_relationship_pairs|b6a065311f82626698e5231b3b47b7bc|7c8f9eae92a3c251388e75dfabeaaf4b||pythagor
character_relationship_summary|5377171baacbe9e70f04f984ebc37972|3a4e2c33216a42861b66302fb93e28c0||pythagor
entity_relationships_v|c09dd8617c1e293b96ce711c1321a609|8d50c14c081bbfc2f8bd8d9499af393f||pythagor
84
== save_02
138|character1_id:integer,character2_id:integer
character_relationship_pairs|b6a065311f82626698e5231b3b47b7bc|7c8f9eae92a3c251388e75dfabeaaf4b||pythagor
character_relationship_summary|5377171baacbe9e70f04f984ebc37972|3a4e2c33216a42861b66302fb93e28c0||pythagor
entity_relationships_v|c09dd8617c1e293b96ce711c1321a609|8d50c14c081bbfc2f8bd8d9499af393f||pythagor
84
== save_03
138|character1_id:integer,character2_id:integer
character_relationship_pairs|b6a065311f82626698e5231b3b47b7bc|7c8f9eae92a3c251388e75dfabeaaf4b||pythagor
character_relationship_summary|5377171baacbe9e70f04f984ebc37972|3a4e2c33216a42861b66302fb93e28c0||pythagor
entity_relationships_v|c09dd8617c1e293b96ce711c1321a609|8d50c14c081bbfc2f8bd8d9499af393f||pythagor
11
== save_04
138|character1_id:integer,character2_id:integer
character_relationship_pairs|b6a065311f82626698e5231b3b47b7bc|7c8f9eae92a3c251388e75dfabeaaf4b||pythagor
character_relationship_summary|5377171baacbe9e70f04f984ebc37972|3a4e2c33216a42861b66302fb93e28c0||pythagor
entity_relationships_v|c09dd8617c1e293b96ce711c1321a609|8d50c14c081bbfc2f8bd8d9499af393f||pythagor
15
== save_05
138|character1_id:integer,character2_id:integer
character_relationship_pairs|b6a065311f82626698e5231b3b47b7bc|7c8f9eae92a3c251388e75dfabeaaf4b||pythagor
character_relationship_summary|5377171baacbe9e70f04f984ebc37972|3a4e2c33216a42861b66302fb93e28c0||pythagor
entity_relationships_v|c09dd8617c1e293b96ce711c1321a609|8d50c14c081bbfc2f8bd8d9499af393f||pythagor
0
```

`relacl` is empty (NULL) on all three views in all six databases; the most
rows any database holds is 84 (save_01, save_02).

## Catalog Facts on NEXUS_template (Read-Only)

`pg_depend` through `pg_rewrite` rules (distinct dependent view, referenced
relation):

```
         dependent_view         |          referenced
--------------------------------+------------------------------
 character_relationship_pairs   | character_relationships
 character_relationship_summary | character_relationship_pairs
 entity_relationships_v         | character_relationships
```

Every `pg_depend` row referencing one of the three views (other than its own
rule and type) is the `_RETURN` rule of `character_relationship_summary` on
`character_relationship_pairs`; nothing depends on `character_relationship_summary`
or `entity_relationships_v`. No foreign key references
`character_relationships` (`pg_constraint WHERE confrelid = ...`: 0 rows).

Foreign keys that reference `characters(id)` (`characters.id` is `bigint`;
`characters_id_seq` is `bigint`):

```
 assets.character_images         | character_id   | bigint
 character_aliases               | character_id   | bigint
 character_psychology            | character_id   | bigint
 character_relationships         | character1_id  | integer
 character_relationships         | character2_id  | integer
 chunk_character_references      | character_id   | bigint
 faction_character_relationships | character_id   | bigint
 global_variables                | user_character | bigint
 items                           | owner_id       | bigint
 character_identity_rulings      | character_id   | bigint
```

`faction_relationships.faction1_id/faction2_id` and
`faction_character_relationships.faction_id/character_id` are `bigint`.

`character_relationships` keeps five constraints
(`character_relationships_character1_id_fkey`, `..._character2_id_fkey`,
`character_relationships_check` `CHECK ((character1_id <> character2_id))`,
`character_relationships_pkey`, `character_relationships_valence_current_open_check`),
four indexes (the primary key plus `idx_character_relationships_character1`,
`..._character2`, `..._type`), and two triggers
(`trg_character_relationships_valence_boundary` ->
`fn_derive_character_relationship_valence`,
`trg_version_character_relationships` -> `fn_version_relationship_row`). The
only functions whose source names `character_relationships` or
`character1_id` is `fn_version_relationship_row`.

The view bodies in the migration were generated from
`pg_get_viewdef('public.<view>'::regclass, true)` on `NEXUS_template` in a
read-only psycopg2 session, and the five comment texts from
`obj_description` / `col_description` in the same session, quoted with `''`
doubling (none contains a quote).

## git grep Proofs (at 41783c1d)

```
$ git grep -n -i -P "(from|join|view)\s+(public\.)?character_relationship_(pairs|summary)\b"
(no output, rc=1)
$ git grep -n -P "character_relationship_summary" -- ':!docs/qa'
(no output, rc=1)
$ git grep -n -P "character_relationship_(pairs|summary)" -- ':!docs/qa'
migrations/137_view_comments.sql:31:-- entity_relationships_v: ... 1011-1034 (_load_character_relationship_pairs); ...
nexus/agents/orrery/resolver.py:1011:def _load_character_relationship_pairs(session: Any) -> Tuple[_EntityPair, ...]:
nexus/agents/orrery/resolver.py:1211:    _character_relationship_pairs: Optional[Tuple[_EntityPair, ...]] = field(
nexus/agents/orrery/resolver.py:1270:    def character_relationship_pairs(self) -> Tuple[_EntityPair, ...]:
nexus/agents/orrery/resolver.py:1271:        if self._character_relationship_pairs is None:
nexus/agents/orrery/resolver.py:1272:            self._character_relationship_pairs = _load_character_relationship_pairs(
nexus/agents/orrery/resolver.py:1275:        return self._character_relationship_pairs
nexus/agents/orrery/resolver.py:1546:        composition_cache.character_relationship_pairs()
nexus/agents/orrery/resolver.py:1548:        else _load_character_relationship_pairs(session)
$ git grep -n "entity_relationships_v" -- nexus
nexus/agents/orrery/audit.py:2171:            FROM entity_relationships_v
nexus/agents/orrery/knowledge_surfacing.py:675:        FROM entity_relationships_v
nexus/agents/orrery/resolver.py:404:            FROM entity_relationships_v relationship
nexus/agents/orrery/resolver.py:656:            FROM entity_relationships_v
nexus/agents/orrery/resolver.py:1024:                FROM entity_relationships_v er
nexus/agents/orrery/reveal.py:425:    FROM entity_relationships_v
nexus/agents/orrery/templates.py:704:#   * Trust hydration reads entity_relationships_v.valence_magnitude. Keep
```

(`reveal.py:423` is `_TRUST_SQL = """`.)

## Red Run

`migrations/139_character_relationship_bigint_ids.sql` moved into the scratch
subdirectory, then:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit \
    "tests/test_character_relationship_id_types_pg.py::test_relationship_ids_above_int4_max"
...
E           psycopg2.errors.NumericValueOutOfRange: integer out of range

tests/pg_fixtures.py:1166: NumericValueOutOfRange
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_836s2_int8_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_character_relationship_id_types_pg.py::test_relationship_ids_above_int4_max
1 failed in 1.59s
```

The file was moved back before the commit (`ls migrations | tail -1` ->
`139_character_relationship_bigint_ids.sql`).

## Quick First Pass

All runs below: worktree root, shared interpreter, `NEXUS_GATEWAY_PORT`,
`NEXUS_API_URL` and `NEXUS_SLOT` unset.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit \
    tests/test_character_relationship_id_types_pg.py tests/test_schema_documentation_pg.py \
    tests/test_orrery/test_migrate.py tests/test_new_story_setup.py \
    tests/test_orrery/test_valence_float_migration_pg.py \
    tests/test_orrery/test_relationship_provenance_pg.py \
    tests/test_orrery/test_orbit_distance_live.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 29 targets: ... qa640_836s2_int8_*, qa640_836s2_rerun_*, qa640_836s2_summary_drift_*, qa640_836s2_unknown_dependent_*, qa640_836s2_widen_*, ...
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
222 passed in 41.33s

$ PYTHONPATH=$PWD $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
(exit 0)
```

## Full Gate

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 219 targets: ...
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1642 passed, 42 skipped, 2 warnings in 396.35s (0:06:36)
```

(This run did not pass `-rs`, so its skip reasons were not printed.)

### `tests/test_orrery` Rerun With Skip Reasons

Rerun on commit `6e9491a5` (the same code as the run above) with `-rs`,
split in two alphabetical halves so each piece stays under the ten-minute
command limit; `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.
Together the halves give the same totals as the run above: 663 + 979 = 1642
passed, 31 + 11 = 42 skipped.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit $(ls tests/test_orrery/test_[a-l]*.py)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 101 targets: ...
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:121: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [18] tests/test_orrery/test_claim_propagation_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_claim_propagation_live.py:1075: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py:546: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_gaia_registry_schema_pg.py:347: Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.
SKIPPED [1] tests/test_orrery/test_live_cycle.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
663 passed, 31 skipped, 2 warnings in 214.69s (0:03:34)

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit $(ls tests/test_orrery/test_[m-z]*.py)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 119 targets: ...
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [1] tests/test_orrery/test_projects.py:609: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_orrery/test_recruit_ally_projects.py:808: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_orrery/test_retrograde_live.py:29: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_retrograde_maturation_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_retrograde_retrieval_live.py: NEXUS_RETROGRADE_RETRIEVAL_TEST_DB_URL is not configured
SKIPPED [1] tests/test_orrery/test_retrograde_wizard_live.py: Set NEXUS_RETROGRADE_WIZARD_E2E=1 to run the live cold-start proof.
SKIPPED [5] tests/test_orrery/test_stage2a_status_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
979 passed, 11 skipped, 2 warnings in 194.44s (0:03:14)
```

The 42 `tests/test_orrery` skips by reason: live LLM opt-in
(`NEXUS_RUN_LIVE_LLM`, 35), owner-corpus opt-in (`NEXUS_RUN_CORPUS`, 4), the
live Gaia enum-schema gate (`NEXUS_638_ENUM_E2E`, 1), the live retrograde
cold-start proof (`NEXUS_RETROGRADE_WIZARD_E2E`, 1), and an unset dedicated
retrieval-test database URL (`NEXUS_RETROGRADE_RETRIEVAL_TEST_DB_URL`, 1).
None is a `NEXUS_RUN_POSTGRES` skip. No failure and no error.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfEs -p tests.dbname_audit tests/test_api
FAILED tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render
  E AssertionError: COMMAND PID USER ... python3.1 53761 pythagor 10u IPv4 ... TCP 127.0.0.1:8018 (LISTEN)
  tests/scheduler_helpers.py:294: AssertionError
SKIPPED [1] tests/test_api/test_conversations.py:377: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_api/test_narrative_summary_paid_pg.py: Requires explicit two-call summary authorization
SKIPPED [1] tests/test_api/test_secrets_endpoints.py:268: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_api/test_secrets_endpoints.py:279: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
1 failed, 869 passed, 4 skipped, 9 warnings in 494.37s (0:08:14)
```

The one failure is the fixed lane 8018 held by another builder's test
process (not a listener this run started). After 60 seconds, the one file
rerun once:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfEs -p tests.dbname_audit tests/test_api/test_scheduler_corpus_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_turn_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
3 passed, 9 warnings in 26.75s
```

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfEs -p tests.dbname_audit tests \
    --ignore=tests/test_orrery --ignore=tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 240 targets: ...
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: ...
dbname audit: owner names admitted on registered clusters: save_04@local:50213 (psycopg2), save_04@local:50216 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
3007 passed, 42 skipped, 10 warnings in 998.71s (0:16:38)
```

Skip reasons in that run (tests skipped, summed from the `SKIPPED [n]` lines):
`NEXUS_RUN_LIVE_LLM` 25, `NEXUS_GOLDEN_PATH_E2E` 8, `NEXUS_RUN_CORPUS` 3, and
one each for `NEXUS_639_PRESENCE_E2E`, `NEXUS_CONSPIRACY_E2E`,
`NEXUS_ISSUE_600_LIVE`, `NEXUS_ISSUE_601_LIVE`, `NEXUS_RUN_SECRET_STORE`, and
the local DeBERTa cross-encoder model not being installed (42). Every skip is
a live-provider, owner-corpus, or local-model opt-in; none is a PostgreSQL
skip. No failure and no error.

(The admitted `save_04` names are on the disposable two-cluster fixture's own
servers, not on the owner server.)

## Other Checks

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_reachability.py
38 passed, 5 warnings in 10.57s
$ $PY -m black tests/test_character_relationship_id_types_pg.py   # reformatted once, then committed
$ $PY -m flake8 tests/test_character_relationship_id_types_pg.py  # exit 0
$ PYTHONPATH=$PWD $PY -m mypy tests/test_character_relationship_id_types_pg.py
Success: no issues found in 1 source file
```

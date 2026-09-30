# Issue 836: A Read-Only Parity and Invariant Report for Chunk Entity References

Date: 2026-09-30. Branch `claude/836-reference-parity`, cut from `origin/main`
at `172bd0e2`. No migration, no paid provider call, no gateway lane. No
`save_NN` or `NEXUS_template` was written: the tests ran on a disposable
`qa640_836_parity_*` clone under `-p tests.dbname_audit` (owner targets:
none), and the `save_01` run below is a read-only session.

## Why

Issue #836 replaces `chunk_character_references`, `chunk_faction_references`
and `place_chunk_references` with one typed `chunk_entity_references` table.
Its verifier amendment requires, before any old table or view is removed,
row-level parity per kind, every foreign-key, delete and uniqueness invariant
reproduced, and `place_chunk_references.evidence` preserved, with the counts
character 5,800, place 1,996, faction 632. `scripts/entity_reference_parity.py`
produces that proof.

## What the Script Does

- `--dbname` (required; `save_NN`, `qa640_*` or `ref_*` through
  `scripts.database_targets.metrics_dbname`), `--target` (default
  `chunk_entity_references_v`), `--limit` (example rows per list, default 10).
- Session: `default_transaction_read_only=on`, repeatable read, and
  `search_path` pinned to `pg_catalog, public`; the script reads back
  `transaction_read_only`, `transaction_isolation` and `search_path` and
  raises unless they are `on`, `repeatable read` and `pg_catalog, public`,
  as `scripts/qa_shift/prose_metrics.py` does for the first two. The pin
  makes every unqualified name (the junctions, subtype tables, `entities`
  and the target) resolve to the relations the invariant block reads.
  `build_report` reads `transaction_read_only` and `transaction_isolation`
  back again in its first query, raises unless they are `on` and
  `repeatable read`, and writes the values it read into `read_only` and
  `snapshot.isolation` (no literal).
- Expected rows: each junction left-joined to its subtype table and to
  `entities`, as `(chunk_id, entity_id, kind, reference_type, evidence)` with
  `kind` from `entities.kind`. A row whose subtype has no entity
  (`subtype_has_no_entity`) or whose entity kind differs from the junction's
  kind (`entity_kind_mismatch`) is an invariant violation.
- Parity: a multiset comparison per kind on the expected columns the target
  has (read from `pg_attribute`). Expected and target rows alike are
  attributed to a kind through `entities.kind` of their `entity_id`, so a
  kind mismatch is reported once, as an invariant violation, and not also as
  a missing and an extra row. Rows with no entity fall into an `unattributed`
  bucket on both sides (`expected`, `target`, `missing`, `extra`, `parity`),
  the one record of such rows. A column the target lacks is reported as
  `"carried": false` with its non-NULL expected count and does not fail the
  run. `expected_non_null_by_kind` uses the same attribution as the parity
  buckets: `entities.kind`, or `unattributed`.
- Invariants from `pg_catalog`: primary key and unique constraints, each
  with its columns, its `pg_get_constraintdef` definition,
  `nulls_not_distinct` (from the owning index) and `deferrable` /
  `initially_deferred`, so a unified key over the nullable `reference_type`
  shows whether it reproduces the faction and character keys; unique
  indexes (definition and `nulls_not_distinct`) not owned by the relation's own primary-key, unique or exclusion
  constraint (a foreign key elsewhere that references an index does not hide
  it), foreign keys with target and actions, NOT NULL columns, the role
  column's type and enum labels, row counts, NULL-evidence place rows, and
  (recorded, not enforced) multi-role place pairs and chunks with more than
  one `setting` place. The last two count distinct roles and distinct places,
  so a duplicated row in a keyless target changes neither.
- Exit status 0 on parity, 3 on any missing, extra or violating row in any
  kind or in the unattributed bucket. Errors raise (1); argument errors exit 2. Logging is configured only in
  `main()`; stdout carries only the JSON document.

## Read-Only Run on `save_01`

Rerun on 2026-09-30 at commit `0b571386`, after the second round of review
fixes; the numbers are unchanged from the first run except the fleet's
migration level, which moved from 135 to 136 between the first run and the
run on `5c89510c`. Each junction's primary key is an ordinary key
(`nulls_not_distinct`, `deferrable` and `initially_deferred` all false; its
columns are NOT NULL), and no junction has a unique constraint or a separate
unique index. The view has none of these.

```
$ PYTHONPATH=$PWD $PY scripts/entity_reference_parity.py --dbname save_01
INFO save_01 vs public.chunk_entity_references_v: parity
exit status: 0
```

The counts are the confirmed 5,800, 1,996 and 632 (view 8,428), with no
missing, extra or violating row. The view does not carry `kind` (8,428
non-NULL expected values) or `evidence` (1,994 non-NULL expected values; 2
place rows have NULL evidence). So a view-only reader already loses the
evidence on 1,994 rows today.

Two facts matter for the unified table's design:

- 22 `(place_id, chunk_id)` pairs hold more than one role, so the unified
  table's key must include the role (as `place_chunk_references`' key does),
  not `(chunk_id, entity_id)` alone.
- 176 chunks hold more than one `setting` place (chunk ids 4 to 1425).
  The production roster writer now refuses a second setting
  (`nexus/presence/roster.py`, `roster_from_resolved_references`), but the
  golden master holds these rows, so a one-setting-per-chunk constraint on the
  unified table would reject the backfill.

Summary of the JSON document. Each kind's `missing`, `extra` and
`invariant_violations` blocks are shown as their counts (every `examples`
list is empty), and the `columns` arrays inside the invariant blocks are
omitted:

```json
{
  "database": "save_01",
  "read_only": true,
  "snapshot": {
    "isolation": "repeatable read",
    "server_version_num": 170011,
    "migration_level": "136"
  },
  "target": {
    "relation": "public.chunk_entity_references_v",
    "relkind": "view",
    "columns": [
      "chunk_id",
      "entity_id",
      "reference_type"
    ]
  },
  "compared_columns": [
    "chunk_id",
    "entity_id",
    "reference_type"
  ],
  "parity": true,
  "exit_status": 0,
  "kinds": {
    "character": {
      "expected": 5800,
      "target": 5800,
      "missing": 0,
      "extra": 0,
      "invariant_violations": 0,
      "parity": true
    },
    "place": {
      "expected": 1996,
      "target": 1996,
      "missing": 0,
      "extra": 0,
      "invariant_violations": 0,
      "parity": true
    },
    "faction": {
      "expected": 632,
      "target": 632,
      "missing": 0,
      "extra": 0,
      "invariant_violations": 0,
      "parity": true
    }
  },
  "columns": {
    "chunk_id": {
      "carried": true,
      "expected_non_null": 8428,
      "expected_non_null_by_kind": {
        "character": 5800,
        "place": 1996,
        "faction": 632,
        "unattributed": 0
      }
    },
    "entity_id": {
      "carried": true,
      "expected_non_null": 8428,
      "expected_non_null_by_kind": {
        "character": 5800,
        "place": 1996,
        "faction": 632,
        "unattributed": 0
      }
    },
    "kind": {
      "carried": false,
      "expected_non_null": 8428,
      "expected_non_null_by_kind": {
        "character": 5800,
        "place": 1996,
        "faction": 632,
        "unattributed": 0
      }
    },
    "reference_type": {
      "carried": true,
      "expected_non_null": 7796,
      "expected_non_null_by_kind": {
        "character": 5800,
        "place": 1996,
        "faction": 0,
        "unattributed": 0
      }
    },
    "evidence": {
      "carried": false,
      "expected_non_null": 1994,
      "expected_non_null_by_kind": {
        "character": 0,
        "place": 1994,
        "faction": 0,
        "unattributed": 0
      }
    }
  },
  "unattributed": {
    "expected": 0,
    "target": 0,
    "missing": {
      "count": 0,
      "examples": []
    },
    "extra": {
      "count": 0,
      "examples": []
    },
    "parity": true
  },
  "invariants": {
    "chunk_character_references": {
      "relation": "public.chunk_character_references",
      "relkind": "table",
      "primary_key": {
        "name": "chunk_character_references_pkey",
        "columns": [
          "chunk_id",
          "character_id"
        ],
        "definition": "PRIMARY KEY (chunk_id, character_id)",
        "nulls_not_distinct": false,
        "deferrable": false,
        "initially_deferred": false
      },
      "unique_constraints": [],
      "unique_indexes": [],
      "foreign_keys": [
        {
          "name": "chunk_character_references_character_id_fkey",
          "columns": [
            "character_id"
          ],
          "references": "characters",
          "referenced_columns": [
            "id"
          ],
          "on_update": "CASCADE",
          "on_delete": "CASCADE"
        },
        {
          "name": "chunk_character_references_chunk_id_fkey",
          "columns": [
            "chunk_id"
          ],
          "references": "narrative_chunks",
          "referenced_columns": [
            "id"
          ],
          "on_update": "CASCADE",
          "on_delete": "CASCADE"
        }
      ],
      "not_null_columns": [
        "chunk_id",
        "character_id"
      ],
      "role_column": {
        "name": "reference",
        "type": "reference_type",
        "enum_labels": [
          "present",
          "mentioned"
        ]
      },
      "row_count": 5800
    },
    "place_chunk_references": {
      "relation": "public.place_chunk_references",
      "relkind": "table",
      "primary_key": {
        "name": "place_chunk_references_pkey",
        "columns": [
          "place_id",
          "chunk_id",
          "reference_type"
        ],
        "definition": "PRIMARY KEY (place_id, chunk_id, reference_type)",
        "nulls_not_distinct": false,
        "deferrable": false,
        "initially_deferred": false
      },
      "unique_constraints": [],
      "unique_indexes": [],
      "foreign_keys": [
        {
          "name": "place_chunk_references_chunk_id_fkey",
          "columns": [
            "chunk_id"
          ],
          "references": "narrative_chunks",
          "referenced_columns": [
            "id"
          ],
          "on_update": "CASCADE",
          "on_delete": "CASCADE"
        },
        {
          "name": "place_chunk_references_place_id_fkey",
          "columns": [
            "place_id"
          ],
          "references": "places",
          "referenced_columns": [
            "id"
          ],
          "on_update": "CASCADE",
          "on_delete": "CASCADE"
        }
      ],
      "not_null_columns": [
        "place_id",
        "chunk_id",
        "reference_type"
      ],
      "role_column": {
        "name": "reference_type",
        "type": "place_reference_type",
        "enum_labels": [
          "setting",
          "mentioned",
          "transit"
        ]
      },
      "row_count": 1996,
      "null_evidence_rows": 2,
      "recorded_not_enforced": {
        "multi_role_place_pairs": 22,
        "chunks_with_multiple_setting_places": 176
      }
    },
    "chunk_faction_references": {
      "relation": "public.chunk_faction_references",
      "relkind": "table",
      "primary_key": {
        "name": "chunk_faction_references_pkey",
        "columns": [
          "chunk_id",
          "faction_id"
        ],
        "definition": "PRIMARY KEY (chunk_id, faction_id)",
        "nulls_not_distinct": false,
        "deferrable": false,
        "initially_deferred": false
      },
      "unique_constraints": [],
      "unique_indexes": [],
      "foreign_keys": [
        {
          "name": "chunk_faction_references_chunk_id_fkey",
          "columns": [
            "chunk_id"
          ],
          "references": "narrative_chunks",
          "referenced_columns": [
            "id"
          ],
          "on_update": "CASCADE",
          "on_delete": "CASCADE"
        },
        {
          "name": "chunk_faction_references_faction_id_fkey",
          "columns": [
            "faction_id"
          ],
          "references": "factions",
          "referenced_columns": [
            "id"
          ],
          "on_update": "CASCADE",
          "on_delete": "CASCADE"
        }
      ],
      "not_null_columns": [
        "chunk_id",
        "faction_id"
      ],
      "role_column": null,
      "row_count": 632
    },
    "target": {
      "relation": "public.chunk_entity_references_v",
      "relkind": "view",
      "primary_key": null,
      "unique_constraints": [],
      "unique_indexes": [],
      "foreign_keys": [],
      "not_null_columns": [],
      "role_column": {
        "name": "reference_type",
        "type": "text",
        "enum_labels": null
      },
      "row_count": 8428,
      "recorded_not_enforced": {
        "multi_role_place_pairs": 22,
        "chunks_with_multiple_setting_places": 176
      }
    }
  }
}
```

## Tests

`tests/test_entity_reference_parity_pg.py` seeds a disposable clone through
`tests.pg_fixtures`: two turns accepted through `seed_accepted_turn`, whose
production commit writes every junction row through
`nexus.presence.roster.write_roster`. No direct junction row was needed:
the second turn's references give Fixture Plaza both `setting` and
`transit`, and the commit writes both rows. Seeded rows: character 3, place
5 (3 with evidence, 2 without), faction 3. No seed helper was added to
`tests/pg_fixtures.py`. The last test seeds a second clone the same way,
because it changes an entity's kind.

- `test_view_has_exact_parity_with_the_seeded_junctions`: the CLI exits 0
  with `read_only` true and isolation `repeatable read` as read from the
  session; per-kind expected and target counts equal the seeded counts (each
  non-zero) and the junction counts; the invariant block names each key (the
  character key with its definition and NULL semantics), role enum and the
  six `CASCADE`/`CASCADE` foreign keys.
- `test_place_with_two_roles_counts_as_two_rows_and_one_pair`: the plaza's
  two roles in one chunk are two expected and two target rows, and one
  multi-role pair on the junction and on the view.
- `test_evidence_not_carried_counts_rows_with_evidence`: `evidence` is
  `"carried": false` with `expected_non_null` equal to the 3 rows with
  evidence, all under `place` (and 0 `unattributed`); `null_evidence_rows`
  is 2.
- `test_unified_table_target_carries_every_column_and_catches_drift`: a table
  of the unified shape filled from the junctions shows parity with every
  column carried, and `null_evidence_rows` on the target counts place rows
  only (2, as on the junction); a second copy of one setting row is one extra
  row and no missing row (exit 3), and the recorded multi-role and
  multi-setting counts stay as on the junction, so the comparison is a
  multiset and the recorded counts are of distinct values; deleting one row
  shows exactly that row missing (exit 3);
  changing one role shows one missing and one extra row (exit 3); both at
  once show 2 missing and 1 extra, and `--limit 1` caps the examples.
- `test_connection_helper_refuses_writes`: the session's `search_path` is
  `pg_catalog, public`; a `DELETE` and a `CREATE TABLE` through
  `open_read_only_connection` raise `ReadOnlySqlTransaction`.
- `test_report_refuses_a_session_that_is_not_read_only_repeatable_read`:
  `build_report` handed a plain `connect()` session raises naming
  `transaction_read_only='off'` and `read committed`; the same session set
  read-only still raises naming `read committed`.
- `test_unique_constraints_report_their_null_semantics`: three unified-shape
  tables filled from the junctions, keyed `UNIQUE (chunk_id, entity_id,
  reference_type)`, `UNIQUE NULLS NOT DISTINCT (...)` and `UNIQUE (...)
  DEFERRABLE INITIALLY DEFERRED`, each show parity; their
  `unique_constraints` entries differ in `definition`, `nulls_not_distinct`
  and `deferrable`/`initially_deferred`. A second copy of a role-less faction
  row inserts into the first table and raises `UniqueViolation` on the
  second, so the difference the report shows is the one that matters.
- `test_kind_mismatch_and_unattributed_rows_fail_the_run`, on a second
  clone: `entities.kind` of Fixture Docks (one junction row) is set to
  `faction` directly, since no production writer reaches this case and
  `entities` has no trigger or check on `kind`. The view run exits 3 with
  one `entity_kind_mismatch`, no missing or extra row in any kind, and the
  row filed under `faction` on both sides; `reference_type`'s
  `expected_non_null_by_kind` counts that row under `faction` too (place 4,
  faction 1). With the kind restored, a unified table whose plain unique
  index another table's foreign key references lists that index under
  `unique_indexes` with `nulls_not_distinct` false. A unified row naming an
  absent entity gives `unattributed.target == 1`, one unattributed extra
  row, and exit 3.

Each fix was checked against its regression on a scratch copy of the script
(restored before the commit): counting rows instead of distinct roles, a set
difference instead of a multiset difference, the old unique-index exclusion,
and grouping expected rows by the junction's kind each fail exactly one of
these tests. The second round was checked the same way on `0b571386`
(`git checkout` restored the file after each): skipping the session
check in `build_report`, reporting `nulls_not_distinct` as always false, and
tallying non-NULL values by junction kind each fail exactly one test
(`1 failed, 7 passed` each).

## Proof

The first PostgreSQL tail below ran on commit `0b571386` (the second round
of review fixes); the second, and the offline tails after the first round,
ran on `5c89510c`. The first offline tails predate both rounds and are kept
as the original record. The second round changes only
`scripts/entity_reference_parity.py` and the PostgreSQL test file, which
the offline runs skip; `tests/test_reachability.py` was rerun on it.

PostgreSQL gate, from the worktree root with `PYTHONPATH=$PWD` and
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

On `0b571386`:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_entity_reference_parity_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_836_parity_* x2, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
149 passed, 2 warnings in 16.69s

$ $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.95s
```

On `5c89510c`:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_entity_reference_parity_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_836_parity_* x2, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
147 passed, 2 warnings in 13.32s
```

Offline gates before the review fixes:

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2608 passed, 396 skipped, 8 warnings in 403.65s (0:06:43)

$ $PY -m pytest -q tests/test_api tests/test_orrery -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1811 passed, 742 skipped, 7 warnings in 39.96s

$ $PY -m pytest -q tests/test_reachability.py -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.29s
```

Offline gates after the review fixes, on `5c89510c`. The two runs name
their files explicitly; pytest does not apply `--ignore` to a path given on
the command line, so the first run also collected `tests/test_api` and the
second `tests/test_orrery`, and together they are the whole offline tree
(4,419 passed and 1,139 skipped, against 4,419 and 1,138 before the fixes;
the one extra skip is the new PostgreSQL test):

```
$ $PY -m pytest -q -p no:cacheprovider tests/test_[a-m]* --ignore=tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1843 passed, 393 skipped, 8 warnings in 322.26s (0:05:22)

$ $PY -m pytest -q -p no:cacheprovider tests/test_[n-z]* tests/config tests/*_test.py --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2576 passed, 746 skipped, 7 warnings in 111.05s (0:01:51)

$ $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.87s
```

Black, flake8 and mypy on `scripts/entity_reference_parity.py` and
`tests/test_entity_reference_parity_pg.py`, on `5c89510c` and again on
`0b571386`: `2 files left unchanged`, no flake8 finding, `Success: no
issues found in 2 source files`.

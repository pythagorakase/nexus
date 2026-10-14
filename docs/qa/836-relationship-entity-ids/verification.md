# Relationship Entity IDs: Verification

Order 836-S6a (Refs #836). The lane was authored by Codex as a source
checkpoint on 2026-10-08 (base `ed5ce5a48409c77b65f0502467ee0c09be4b4a3e`)
without running the order's Proof Expected. The integrated-tree proof below
(2026-10-13) runs that proof on the wave-B integration tree that will land,
except the steps named "coordinator's step".

## Implemented Scope

- Migration 151 refuses stale historical subtype keys before any DDL;
  snapshots complete relationship rows and ledger identities; adds six
  entity-id columns, two composite unique targets, six composite foreign keys
  and three fill triggers; backfills with only the three version triggers
  disabled; rewrites `old_row` additively; and checks row multisets, original
  ledger values, the nullable count/maximum, the mappings and the restored
  trigger state.
- Replay skips a relationship entity-id column only when that key is absent
  from either compared document. `RELATIONSHIP_KEY_COLUMNS` stays on subtype
  ids; no checkpoint document is migrated.
- Two migration-139 expectations change, as baselines made stale by migration
  151: `TABLE_TRIGGERS` gains `trg_character_relationships_entity_ids`, and
  the constraint count rises from 5 to 7.
- `tests/test_relationship_entity_ids_pg.py`: seven ordinary cases (parity,
  empty ledger, writers, divergence, stale ledger, two checkpoint variants)
  and four `requires_corpus` fleet cases.

## Fixes on the Integrated Tree (2026-10-13)

On the integration head a563203a the lane's test file had two failures and a
consumer test failed (`2 failed, 5 passed, 4 skipped` for the lane file):

- `test_entity_ids_cannot_diverge`: the direct INSERTs omitted the NOT NULL
  `emotional_valence`, `dynamic`, `recent_events` and `history` columns, so
  the first INSERT failed on NOT NULL before reaching the composite key. Both
  direct INSERTs now carry `seed_relationship`'s payload; the assertions are
  unchanged.
- `test_migration_151_refuses_stale_ledger`: `_build_story_transition` calls
  `write_cache`, whose `require_slot_dbname` rejected the qa640 name. The
  `relationship_db` fixture now routes slot 3 with `route_slot_to_disposable`,
  as `disposable_need_clock_db` does. The run then met migration 144's
  `refuse_base_timestamp_change` (the reset keeps chunks and the wizard world
  names `STORY_BASE`), so this case seeds its pair on `STORY_BASE`.
- `tests/test_lore/test_character_dossier_tags_pg.py::test_dossier_place_and_relationship_names`
  failed with `character_relationships.character2_id = 999999 names no
  characters row` from `fn_relationship_entity_ids()`. The test deliberately
  corrupts one disposable transaction to exercise the reader's
  missing-endpoint guard; seeding a real row would no longer test that guard.
  The trigger stays strict: the test now lifts migration 151's fill trigger
  (`DISABLE TRIGGER`) and composite key (`DROP CONSTRAINT
  character_relationships_character2_entity_fkey`) in that same rolled-back
  transaction, alongside the subtype key it already dropped.
- The migration header had lost the space before each number ("migration143",
  "lock_timeout5s") and omitted most of the order's file:line facts. It now
  carries them, cited against this tree. The edit is comment-only:
  `diff <(git show HEAD:migrations/151_relationship_entity_ids.sql | grep -v '^--') <(grep -v '^--' migrations/151_relationship_entity_ids.sql)`, run with HEAD at f2d82e77 before the header commit,
  printed nothing ("non-comment lines identical").

Claims withdrawn from the source checkpoint: its Black result had no recorded
command (the Black run is recorded below instead), and the "independent
source-only test review" left no artifact, so that claim is dropped. The
missing-150 sequence expectation is removed: 149 and 150 are present on this
tree, and `test_migration_sequence_has_only_known_gaps` passes in the focused
set below.

## Integrated-Tree Proof (2026-10-13)

Every command ran from `/Users/pythagor/nexus/.claude/worktrees/fix-836-s6a`
on commit `7a503f5c` (the two fix commits above on a563203a), with
`PY=/Users/pythagor/nexus/.venv/bin/python` and `S` the fixer's scratch
directory `fix-waveb-r3-836-S6a`. `PYTHONPATH=$PWD $PY -c 'import nexus;
print(nexus.__file__)'` printed
`/Users/pythagor/nexus/.claude/worktrees/fix-836-s6a/nexus/__init__.py`.

Each PostgreSQL run went through one wrapper, which waits in a bounded loop
(cap 1,200 s) while the one-minute load is 24 or higher, records `uptime`, and
then runs
`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit <files>`.
No run waited (recorded `load wait: 0s` on each; one-minute loads 6.6 to 21.0).
No connection timed out and no gateway lane was busy, so no rerun was needed.

### Focused PostgreSQL Set

The order's 23 files plus `tests/test_lore/test_character_dossier_tags_pg.py`,
in three serial sessions:

```
# A: tests/test_relationship_entity_ids_pg.py tests/test_character_relationship_id_types_pg.py
#    tests/test_orrery/test_replay.py tests/test_orrery/test_reconstruction.py
#    tests/test_orrery/test_pursue_romance_replay.py tests/test_orrery/test_recruit_ally_replay.py
#    tests/test_orrery/test_relationship_provenance_pg.py tests/test_orrery/test_drift_live.py
#    tests/test_orrery/test_character_name_replay.py
load wait: 0s; uptime: 17:55  up 6 days,  4:35, 5 users, load averages: 20.98 15.79 12.79
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 30 targets: postgres, qa640_778s6a_played_*, qa640_778s6a_replay_* x7, qa640_836s2_int8_*, qa640_836s2_rerun_*, qa640_836s2_summary_drift_*, qa640_836s2_unknown_dependent_*, qa640_836s2_widen_*, qa640_836s6a_* x7, qa640_drift_* x2, qa640_reconstruction_*, qa640_replay_*, qa640_roster798_* x3, qa885_pursue_romance_replay_*, qa885_recruit_ally_replay_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
80 passed, 4 skipped, 2 warnings in 76.28s (0:01:16)

# B: tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_valence_float_migration_pg.py
#    tests/test_orrery/test_need_clock_anchor_pg.py tests/test_api/test_backstage_endpoints_pg.py
#    tests/test_trait_compiler_integration.py tests/test_pg_character_pair_seed.py
#    tests/test_orrery/test_migrate.py tests/test_orrery/test_migration_dead_strata_pg.py
load wait: 0s; uptime: 17:57  up 6 days,  4:37, 5 users, load averages: 9.94 13.79 12.43
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 576 targets: postgres, qa640_* x18, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_813_case_* x542, qa640_grieving_migration_*, qa640_membership_roles_*, qa640_mig088_*, qa640_uib_turn_*, qa640_vocab_migration_* x6, qa885_character_pair_* x2, qa885_trait_compiler_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
677 passed, 6 skipped, 9 warnings in 3623.79s (1:00:23)

# C: tests/test_schema_documentation_pg.py tests/test_new_story_setup.py tests/test_pg_disposable_target.py
#    tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py
#    tests/test_connection_lifecycle.py tests/test_lore/test_character_dossier_tags_pg.py
load wait: 0s; uptime: 18:58  up 6 days,  5:38, 5 users, load averages: 7.08 8.55 8.78
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 31 targets: nexus_m10_fresh_test_98198, nexus_m10_template_test_98198, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_816_lifecycle_test_provider, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_885_ren_replay_* x4, qa640_910_dossier_* x7, qa640_docs_refresh_*, qa640_schema_docs_* x3, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:49583 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:49584 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:49583 (psycopg2), save_04@local:49584 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
211 passed, 2 skipped, 7 warnings in 91.91s (0:01:31)
```

No failure anywhere, so `tests/test_character_relationship_id_types_pg.py`
passes and `test_migration_sequence_has_only_known_gaps` passes (149 and 150
are on this tree). The skips in A are the four `requires_corpus` fleet cases
of the lane file, run next; the six in B are the `requires_corpus` cases of
`test_migration_dead_strata_pg.py`.

### Corpus Fleet Selector

```
$ ENVX=NEXUS_RUN_CORPUS=1 <wrapper> tests/test_relationship_entity_ids_pg.py -k fleet
load wait: 0s; uptime: 19:00  up 6 days,  5:40, 5 users, load averages: 6.58 8.39 8.71
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 5 targets: postgres, qa640_836s6a_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
4 passed, 7 deselected in 43.99s
```

The fixture names its clones `qa640_836s6a_<12 hex>` (fixtures own their
names) and drops each one. Its `pg_dump` of `save_01`..`save_04` is a read of
those saves outside the Python connection audit.

### Red Runs

Each plant was applied by a scratch script, the named test ran through the
wrapper, and the file was restored with `git checkout -- <path>`; `git diff
--quiet -- <path>` succeeded and the SHA-256 matched before and after. No plant
was committed.

1. Drop the three `DISABLE`/`ENABLE TRIGGER trg_version_*` pairs (6 lines,
   `migrations/151_relationship_entity_ids.sql`, SHA-256 `f177b945…b8b1`
   before and after). `tests/test_relationship_entity_ids_pg.py::test_backfill_and_rewrite_parity`:

   ```
   >       assert migrate.migrate_database(relationship_db, skip_locked=False) == (1, 0)
   E       assert (0, 1) == (1, 0)
   ERROR    nexus.migrate:migrate.py:365   FAILED: 151_relationship_entity_ids - Migration 151: relationship version count or max id changed
   dbname audit: owner targets: none
   FAILED tests/test_relationship_entity_ids_pg.py::test_backfill_and_rewrite_parity
   1 failed in 2.60s
   ```

2. Drop the stale-ledger `DO` guard (46 lines, same SHA-256 before and after).
   `::test_migration_151_refuses_stale_ledger` passes its reset and id-reuse
   assertions and fails where the migration must refuse:

   ```
           assert all(replacements[key] != entity for key, entity in old.items())
           before = _snapshot(relationship_db)
   >       assert migrate.migrate_database(relationship_db, skip_locked=False) == (0, 1)
   E       assert (1, 0) == (0, 1)
   dbname audit: owner targets: none
   FAILED tests/test_relationship_entity_ids_pg.py::test_migration_151_refuses_stale_ledger
   1 failed in 2.78s
   ```

3. Revert item 2 (remove the seven-line entity-id skip from `_diff_section`;
   `nexus/agents/orrery/replay.py` SHA-256 `fa3b9e0c…c1a5` before and after).
   `-k test_verify_skips_entity_ids_absent_from_old_checkpoints`:

   ```
   >       assert verdict.drifts == []
   E       AssertionError: assert [Drift(sectio...ne, actual=5)] == []
   E         Left contains 4 more items, first extra item: Drift(section='character_relationships', row_key='(1, 2)', column='character1_entity_id', kind='value', expected=None, actual=3)
   dbname audit: owner targets: none
   FAILED tests/test_relationship_entity_ids_pg.py::test_verify_skips_entity_ids_absent_from_old_checkpoints[genesis]
   FAILED tests/test_relationship_entity_ids_pg.py::test_verify_skips_entity_ids_absent_from_old_checkpoints[interval]
   2 failed, 9 deselected in 5.15s
   ```

### Read-Only Fleet Survey

`PGOPTIONS='-c default_transaction_read_only=on' psql -X -v ON_ERROR_STOP=1 -d <db> -At -F' | ' -f survey.sql`;
columns: database, stamp, `character_relationships`, `faction_relationships`,
`faction_character_relationships`, `relationship_versions`, distinct
table/operation/producer, `state_checkpoints`, and ledger rows migration 151's
guard would call stale (the guard's own CTE):

```
save_01 | 148 | 84 | 0 | 0 | 84 | character_relationships/update/unattributed_pre_115 | 1 | 0
save_02 | 148 | 84 | 0 | 0 | 84 | character_relationships/update/unattributed_pre_115 | 1 | 0
save_03 | 148 | 11 | 0 | 0 | 176 | character_relationships/update/unattributed_pre_115 | 2 | 0
save_04 | 148 | 15 | 0 | 0 | 215 | character_relationships/update/unattributed_pre_115 | 2 | 0
save_05 | 148 | 0 | 0 | 0 | 0 |  | 0 | 0
NEXUS_template | 148 | 0 | 0 | 0 | 0 |  | 0 | 0
```

The counts equal the 2026-10-07 survey in the migration header. No database
has a stale key, so the guard will not refuse at landing.

### Zero-Change Proof

For N in 01..04, one script ran (transcript abridged to its results; paths
shortened):

```
createdb -T template0 qa640_836s6a_N
nice -n 15 pg_dump --format=custom --dbname save_N --file N.dump
nice -n 15 pg_restore --exit-on-error --no-owner --no-acl --dbname qa640_836s6a_N N.dump
PYTHONPATH=$PWD nice -n 15 $PY zc_premigrate.py qa640_836s6a_N mig150   # every migration but 151
zc_queries.sh qa640_836s6a_N 0 > before_N                              # the order's four queries
[03, 04] PYTHONPATH=$PWD nice -n 15 $PY zc_verify.py qa640_836s6a_N     # read-only REPEATABLE READ
PYTHONPATH=$PWD nice -n 15 $PY scripts/migrate.py --dbname qa640_836s6a_N
zc_queries.sh qa640_836s6a_N 1 > after_N   # same queries minus the six entity keys
cmp before_N after_N
[03, 04] verify again; dropdb qa640_836s6a_N
```

The fleet is at 148 and 151 lands after 149 and 150, so each clone was first
brought to 150 through `migrate.migrate_database(..., migrations_dir=<copy of
migrations/ without 151>)` (it returned `(2, 0)`); the `before` snapshot and
the first verify are therefore the state 151 will meet, and
`scripts/migrate.py --dbname` applied 151 alone (`Summary: 1 applied, 0
skipped/failed`, post stamp 151).

| Clone | Before: versions (count/max id), rows | `cmp` | Entity-id mismatches, live and ledger | Verify before | Verify after |
|---|---|---|---|---|---|
| 01 | 84/84; 84/0/0 | identical | 0 | n/a | n/a |
| 02 | 84/512; 84/0/0 | identical | 0 | n/a | n/a |
| 03 | 176/180; 11/0/0 | identical | 0 | 1 -> 2: drifts=0, skipped 106 | 1 -> 2: drifts=0, skipped 126 |
| 04 | 215/215; 15/0/0 | identical | 0 | 1 -> 2: drifts=0, skipped 106 | 1 -> 2: drifts=0, skipped 126 |

The mismatch count also counts any ledger row lacking either new key (0).
The skipped counts differ by 20 because the target checkpoint (2, chunk 28) on
both saves stores 10 `character_relationships` rows (read-only:
`jsonb_array_length(state->'character_relationships')` = 10) captured before
151; after the migration the live side carries two entity-id columns per row
that the stored document lacks, and item 2 skips each of those 10 x 2 = 20
columns as unknown. The other 106 are the existing unreproducible columns.
`psql -d postgres -Atc "select datname from pg_database where datname like
'qa640_836s6a%'"` printed nothing after the run.

(A first run on 03 echoed the query command into `before_03`/`after_03`, so
`cmp` reported a difference on line 1 only; `cmp` on lines 2 onward was
identical. The script was fixed and 03 rerun; the table shows the rerun.)

### Comment Catalog

From the migrated clone `qa640_836s6a_02` (before its drop),
`PYTHONPATH=$PWD nice -n 15 $PY comment_listing.py qa640_836s6a_02 migrations/151_relationship_entity_ids.sql`
read every `COMMENT ON` line of the migration in order, fetched the catalog
text through `col_description` or `obj_description` (`pg_constraint`,
`pg_proc`, `pg_trigger`), and compared byte for byte after undoubling `''`:

```
COLUMN public.character_relationships.character1_entity_id	identical
CONSTRAINT character_relationships_character1_entity_fkey ON public.character_relationships	identical
COLUMN public.character_relationships.character2_entity_id	identical
CONSTRAINT character_relationships_character2_entity_fkey ON public.character_relationships	identical
COLUMN public.faction_relationships.faction1_entity_id	identical
CONSTRAINT faction_relationships_faction1_entity_fkey ON public.faction_relationships	identical
COLUMN public.faction_relationships.faction2_entity_id	identical
CONSTRAINT faction_relationships_faction2_entity_fkey ON public.faction_relationships	identical
COLUMN public.faction_character_relationships.faction_entity_id	identical
CONSTRAINT faction_character_relationships_faction_entity_fkey ON public.faction_character_relationships	identical
COLUMN public.faction_character_relationships.character_entity_id	identical
CONSTRAINT faction_character_relationships_character_entity_fkey ON public.faction_character_relationships	identical
CONSTRAINT characters_id_entity_id_key ON public.characters	identical
CONSTRAINT factions_id_entity_id_key ON public.factions	identical
FUNCTION public.fn_relationship_entity_ids()	identical
TRIGGER trg_character_relationships_entity_ids ON public.character_relationships	identical
TRIGGER trg_faction_relationships_entity_ids ON public.faction_relationships	identical
TRIGGER trg_faction_character_relationships_entity_ids ON public.faction_character_relationships	identical
COLUMN public.relationship_versions.old_row	identical
19 comments listed; 0 differ from the migration text
```

(The listing also printed each catalog text; omitted here because it is the
migration's comment text, which it equals.)

### Static Checks and Offline Suites

```
$ $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
$ nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
$ nice -n 15 $PY -m black --check nexus/agents/orrery/replay.py tests/test_relationship_entity_ids_pg.py tests/test_character_relationship_id_types_pg.py tests/test_lore/test_character_dossier_tags_pg.py
All done! ✨ 🍰 ✨
4 files would be left unchanged.
```

flake8 and mypy, on the same four files at `7a503f5c` and on the
`origin/main` (f073b371) copies of the three pre-existing files
(`git show origin/main:<path>` into scratch):

- flake8 head: 12 E501 diagnostics, all in
  `tests/test_lore/test_character_dossier_tags_pg.py` on untouched lines
  (36, 44, 49, 53, 66, 79, 80, 84, 88, 92, 96, 136). origin/main: the same 12
  plus two more (241 and 315; 315 was the `DROP CONSTRAINT` line this fix
  split). No new diagnostic; the other three files are clean.
- mypy (`$PY -m mypy --explicit-package-bases <files>`) head: `Found 1 error
  in 1 file (checked 4 source files)`, the `seat` `arg-type` error at
  `test_character_dossier_tags_pg.py:340`. origin/main: the same error at
  `:330` (`checked 3 source files`). Pre-existing, on an untouched line.

```
$ env -u NEXUS_RUN_POSTGRES ... PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 16.14s
$ env -u NEXUS_RUN_POSTGRES ... PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3197 passed, 677 skipped, 8 warnings in 595.01s (0:09:55)
$ env -u NEXUS_RUN_POSTGRES ... PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
1 failed, 1912 passed, 1528 skipped, 7 warnings in 43.03s
```

The one offline failure is not this lane's and is deterministic when run
alone: `OrreryEpistemicsSettings` now raises `claim_event_types contains event
types emitted by background branches: ['ate']` before the birth-role check the
test matches (`Regex: 'without birth-role policies.*ate'`). That validator
text arrived in 8129b07a ("Record the integrated-tree proof for operator
inspection"), another lane's fix merged into a563203a; this lane touches no
settings model or epistemics code. Reported to the coordinator, not fixed
here.

No canonical document declares a changed path in its `sources:`; the
front-matter test above passes, and no `verified_commit` stamp moved (the
assembly already moved the canonical stamps to f073b371).

### Coordinator's Steps

- The whole-tree PostgreSQL gate on the final union.
- Fleet application at landing: `python scripts/migrate.py --all`, then
  `--slot 1 --write-locked-slot`, then `nexus doctor`, never
  `ref_codex_bakeoff_2026_07`; afterwards read-only
  `scripts/replay_state.py --slot 3 --verify` and `--slot 4 --verify` must
  report ok (expected skipped count 126, as above). A stale-key refusal is a
  STOP and never authorizes editing the ledger.
- A gateway restart is owed when services run again (`replay.py` changed).
- No paid call, owner service or state-surface regeneration is involved.

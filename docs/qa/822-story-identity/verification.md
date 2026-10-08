# Verification: Story Identity, Origin, Fork Lineage and Renewal (#822 S1)

Branch `claude/822-story-identity`, cut from `origin/main` at 364fef4b and
merged with `origin/main` at b0da93ea. One migration
(`migrations/146_story_identity.sql`). No paid call, no gateway lane, no write
to any `save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07`;
`scripts/backfill_story_identity.py` was never run against a slot.

## Resumed on 2026-10-07

The coordinator stopped the first builder at 12:50 CDT (machine load). A
first resume (15:08 to 15:39 CDT) merged `origin/main`, fixed Black and the
prompt-prose lint, moved both `verified_commit` values and ran the proof, but
its state-surface regeneration died with the session (`page.evaluate: Target
page, context or browser has been closed` at 1,731 s, unbatched) and it wrote
no evidence file and opened no PR. This resume (22:57 CDT) found a clean
worktree (`git status --short` empty) and the branch already pushed at
82751c7e.

| Commit | Order items covered | Left unfinished |
| --- | --- | --- |
| 120c9000 | 1 (migration 146), 2 (`nexus/api/story_identity.py`); reachability baseline gains the new production module | none |
| f2a2e054 | 3 (initialization mints), 4 (transition mints), 5 (clone forks), 6 (five disposable/rehearsal clone sites), 13 (need-clock fixture migrates its template clone) | none |
| 8d6ea915 | 7 (`story_id` is the UUID, `legacy_story_id` added), 8 (client key migration), tests: `test_reader_draft_identity_pg.py`, `reader-draft.test.ts` | state-surface receipt not regenerated |
| fdb26558 | 9 (backfill script and its `[[operators]]` root) | none |
| d71ac6ed | 10 (doctor checks, registry, docs/runtime.md rows, settings description), 11 (docs/database.md), readiness tests | none |
| 942af50b | tests: `tests/test_story_identity_pg.py`; owner-target guard exemption for the test's own data clone | none |
| 60619a97 | Black wrap in the new test | none |
| 002ec970 | merge of `origin/main` b0da93ea (conflict in `tests/pg_fixtures.py` resolved: migrate, then detach, then pin) | none |
| f7f18a94 | 12 (document freshness: both `verified_commit` values to b0da93ea) | none |
| 82751c7e | backfill `--write-locked-slot` help reworded (prompt-prose lint) | none |
| this resume | state-surface receipt regenerated in bounded batches; this evidence file; PR | — |

No uncommitted file was found or discarded.

## The Facts the Order Cites

Line references were re-read at 364fef4b (`git show 364fef4b:<path>`):
`nexus/api/slot_state.py:100` declares `story_id` and `:226-231` derives
`player:{id}:{created_at}`; `nexus/api/narrative_schemas.py:324` carries it;
`nexus/api/slot_endpoints.py:157` passes it; `ui/client/src/lib/reader-draft.ts:18-28`
keys drafts and actions by `JSON.stringify([slot, story_id])`;
`nexus/api/new_story_flow.py:130-138` reuses an existing database and reaches
`perform_transition` at `:595` and `:661`, and `reset_setup` reaches
initialization with `force=True` at `:735`; `nexus/api/new_story_db_mapper.py:590-602`
restarts the entity sequences, logs "Truncated entity tables for clean slate"
and then saves the setting; `scripts/new_story_setup.py:302` copies template
seed data, `:517` restores the source dump verbatim, `:528-535` is
`_post_clone_cleanup`; `scripts/migrate.py:48-50` keeps new migrations SQL.
`git grep -n story_uuid 364fef4b` finds nothing.

Fleet, read-only (`PGOPTIONS='-c default_transaction_read_only=on'`), 2026-10-07 23:01 CDT.
Columns: database, `to_regclass('public.story_identity')`,
`to_regclass('public.story_lineage')`, max migration, chunk count, chunk id
range, `slot_created_at`, character count:

```
NEXUS_template|||143|0|||0
save_01|||143|1425|1..1425|2026-01-14 18:22:29.574584-05|35
save_02|||143|1425|1..1425|2026-01-14 18:22:29.574584-05|35
save_03|||143|40|1..100|2026-07-30 00:49:44.071666-04|17
save_04|||143|46|1..49|2026-07-30 00:49:44.071666-04|23
save_05|||143|0||2026-09-23 11:29:52.574364-04|0
ref_codex_bakeoff_2026_07|{default_transaction_read_only=on}
save_01|{default_transaction_read_only=on}
```

The last two lines are `pg_db_role_setting`: `save_01` and
`ref_codex_bakeoff_2026_07` are locked.

## Rehearsal (Evidence, Not a Test)

Read-only `pg_dump --format=custom` archives of `save_01` and `save_02`,
restored into `qa640_822s1_01` and `qa640_822s1_02` (`createdb -T template0`,
`pg_restore --exit-on-error --no-owner --no-acl`), migrated with
`scripts/migrate.py --dbname <each>`, backfilled twice from Python with
`backfill_story_identity([01, 02], [ForkSpec(02, 01, HISTORICAL_FORKS[0].evidence)])`,
then dropped. The rerun changes nothing (same values, fork `present`):

```
+ pg_dump --format=custom -d save_01 -f <scratch>/rehearsal/save_01.dump (read-only)
+ createdb -T template0 qa640_822s1_01
+ pg_restore --exit-on-error --no-owner --no-acl -d qa640_822s1_01
+ scripts/migrate.py --dbname qa640_822s1_01
INFO Migrating qa640_822s1_01...
INFO   Applied: 146_story_identity
INFO 
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_822s1_01: 141 migration stamps; level 146
+ pg_dump --format=custom -d save_02 -f <scratch>/rehearsal/save_02.dump (read-only)
+ createdb -T template0 qa640_822s1_02
+ pg_restore --exit-on-error --no-owner --no-acl -d qa640_822s1_02
+ scripts/migrate.py --dbname qa640_822s1_02
INFO Migrating qa640_822s1_02...
INFO   Applied: 146_story_identity
INFO 
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_822s1_02: 141 migration stamps; level 146
run 1
qa640_822s1_01 1c58416e-e888-4e60-a2fa-4041df19416c backfill
qa640_822s1_02 c19e121d-74e7-4d6c-9d73-936500eb2a79 backfill
qa640_822s1_02 fork of qa640_822s1_01 c19e121d-74e7-4d6c-9d73-936500eb2a79 <- 1c58416e-e888-4e60-a2fa-4041df19416c recorded
{'qa640_822s1_01': '1c58416e-e888-4e60-a2fa-4041df19416c', 'qa640_822s1_02': 'c19e121d-74e7-4d6c-9d73-936500eb2a79'}
-- qa640_822s1_01
identity|1c58416e-e888-4e60-a2fa-4041df19416c||backfill|2026-10-08 00:00:35.525202-04
-- qa640_822s1_02
identity|c19e121d-74e7-4d6c-9d73-936500eb2a79||backfill|2026-10-08 00:00:35.548211-04
lineage|c19e121d-74e7-4d6c-9d73-936500eb2a79|1c58416e-e888-4e60-a2fa-4041df19416c|fork|qa640_822s1_01|save_02 was cloned from save_01 by the 2026-07-17 order; both held 1,425 chunks and slot_created_at 2026-01-14 18:22:29.574584-05 when this backfill ran (822-Q4).|2026-10-08 00:00:35.594795-04
run 2
qa640_822s1_01 1c58416e-e888-4e60-a2fa-4041df19416c backfill
qa640_822s1_02 c19e121d-74e7-4d6c-9d73-936500eb2a79 backfill
qa640_822s1_02 fork of qa640_822s1_01 c19e121d-74e7-4d6c-9d73-936500eb2a79 <- 1c58416e-e888-4e60-a2fa-4041df19416c present
{'qa640_822s1_01': '1c58416e-e888-4e60-a2fa-4041df19416c', 'qa640_822s1_02': 'c19e121d-74e7-4d6c-9d73-936500eb2a79'}
-- qa640_822s1_01
identity|1c58416e-e888-4e60-a2fa-4041df19416c||backfill|2026-10-08 00:00:35.525202-04
-- qa640_822s1_02
identity|c19e121d-74e7-4d6c-9d73-936500eb2a79||backfill|2026-10-08 00:00:35.548211-04
lineage|c19e121d-74e7-4d6c-9d73-936500eb2a79|1c58416e-e888-4e60-a2fa-4041df19416c|fork|qa640_822s1_01|save_02 was cloned from save_01 by the 2026-07-17 order; both held 1,425 chunks and slot_created_at 2026-01-14 18:22:29.574584-05 when this backfill ran (822-Q4).|2026-10-08 00:00:35.594795-04
+ dropdb qa640_822s1_01 qa640_822s1_02
0
```

## Red Run

A scratch plant removed the item 4 call (transition) and the item 5 calls
(clone replace and fork) and was reverted before any commit
(`git status --short` empty afterwards):

```
 nexus/api/new_story_db_mapper.py | 2 +-
 scripts/new_story_setup.py       | 4 ++--
 2 files changed, 3 insertions(+), 3 deletions(-)
diff --git a/nexus/api/new_story_db_mapper.py b/nexus/api/new_story_db_mapper.py
index 7dc43dfa..36ca442a 100644
--- a/nexus/api/new_story_db_mapper.py
+++ b/nexus/api/new_story_db_mapper.py
@@ -602,7 +602,7 @@ class NewStoryDatabaseMapper:
                     # Every story birth mints a new identity (822-Q20); it
                     # commits or rolls back with the world, and the previous
                     # story's lineage rows go with its identity row.
-                    replace_story_identity(cur, origin="wizard")
+                    pass  # red-run plant: item 4 removed
 
                     # Save setting (using shared cursor)
                     self.save_setting_to_globals(transition_data.setting, cursor=cur)
diff --git a/scripts/new_story_setup.py b/scripts/new_story_setup.py
index 635cfdab..2dce357a 100644
--- a/scripts/new_story_setup.py
+++ b/scripts/new_story_setup.py
@@ -540,8 +540,8 @@ def clone_slot_with_data(
                 )
             cur.execute("SELECT story_uuid::text FROM public.story_identity")
             copied = [row[0] for row in cur.fetchall()]
-            child = replace_story_identity(cur, origin="clone")
-            if copied:
+            child = copied[0] if copied else None  # red-run plant: item 5 removed
+            if False:
                 record_fork(
                     cur,
                     child_uuid=child,
```

The assertion lines and the full tail, from the saved log
(`<scratch>/822-S1-resume-2/red-run.log`, lines 34-37, 2108-2111 and
6511-6519):

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_story_identity_pg.py
E               AssertionError: assert [('8795adfd-d...n must drop')] == []
E                 
E                 Left contains one more item: ('8795adfd-d372-4ba8-8428-e1375bb5d9f5', '2a85d5d1-0a43-4c25-8a5b-eaa8c0db2594', 'fork', 'qa640_822_parent', 'a lineage row the transition must drop')
E                 Use -v to get more diff
...
E               AssertionError: assert 'wizard' == 'clone'
E                 
E                 - clone
E                 + wizard
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 17 targets: postgres, qa640_822_backfill_a_*, qa640_822_backfill_b_*, qa640_822_backfill_t_*, qa640_822_clone_*, qa640_822_clone_src_*, qa640_822_constraints_*, qa640_822_detach_*, qa640_822_detach_bare_*, qa640_822_detach_src_*, qa640_822_doctor_s_*, qa640_822_doctor_t_*, qa640_822_init_*, qa640_822_migration_*, qa640_822_reset_*, qa640_822_reset_src_*, qa640_822_transition_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_story_identity_pg.py::test_transition_renews_identity - Ass...
FAILED tests/test_story_identity_pg.py::test_clone_forks_with_lineage - Asser...
2 failed, 8 passed in 28.25s
```

## PostgreSQL Proof

Machine-load rule: the whole PostgreSQL gate and its three-piece split were
not run (the coordinator runs it at landing). The focused proof set ran in
three sequential sessions with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` unset and `nice -n 15`. Each followed the bounded load wait
(`<scratch>/822-S1-resume-2/waitload.sh`, which loops while the one-minute
load is 24 or more, capped at 20 minutes, then prints a `load check` line),
but the earlier resume did not save those `load check` lines, so no record
of the waits exists for these three sessions. The review-fix runs below
record theirs.

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_story_identity_pg.py tests/test_api/test_reader_draft_identity_pg.py tests/test_api/test_slot_state.py tests/test_new_story_setup.py tests/test_runtime/test_readiness_pg.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 58 targets: nexus_m10_fresh_test_70591, nexus_m10_template_test_70591, postgres, qa640_1013_readiness_* x2, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_822_backfill_a_*, qa640_822_backfill_b_*, qa640_822_backfill_t_*, qa640_822_clone_*, qa640_822_clone_bare_*, qa640_822_clone_src_*, qa640_822_constraints_*, qa640_822_detach_*, qa640_822_detach_bare_*, qa640_822_detach_src_*, qa640_822_doctor_s_*, qa640_822_doctor_t_*, qa640_822_init_*, qa640_822_migration_*, qa640_822_reset_*, qa640_822_reset_src_*, qa640_822_transition_*, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa951_identity_* x4, qa951_no_identity_*, qa951_overwrite_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_new_story_setup.py::test_fresh_database_is_baseline_stamped[fresh]
FAILED tests/test_new_story_setup.py::test_fresh_database_is_baseline_stamped[desktop-reset]
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
3 failed, 156 passed, 5 warnings in 101.40s (0:01:41)

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_need_clock_anchor_pg.py tests/test_api/test_mock_wizard_responses.py tests/test_orrery/test_retrograde_constraints_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 25 targets: nexus_test_issue_613_*, postgres, qa640_* x18, qa640_issue601_* x4, qa640_renamed_test_model_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
52 passed, 5 warnings in 18.39s

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: mock, postgres, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:49560 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:49564 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:49560 (psycopg2), save_04@local:49564 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
10 passed, 2 skipped, 2 warnings in 48.33s
```

The two skips in the last session are the `requires_corpus` tests of
`tests/test_orrery/test_card_identity.py` (`NEXUS_RUN_CORPUS` unset).

### Expected Branch Failures

1. `tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps`:
   migrations 144 (778-S1b) and 145 (783-S1a) are not on `main` yet, as the
   order states. `KNOWN_GAPS` is unchanged.

```
        assert min(versions) == "001"
>       assert missing == KNOWN_GAPS
E       AssertionError: assert {'013', '119', '144', '145'} == frozenset({'013', '119'})
E         
E         Extra items in the left set:
E         '145'
E         '144'
E         Use -v to get more diff

```

2. `tests/test_new_story_setup.py::test_fresh_database_is_baseline_stamped[fresh]`
   and `[desktop-reset]`: the file's `template_db` fixture
   (`tests/test_new_story_setup.py:69-138`) builds a hand-made template
   stand-in (a minimal schema plus every migration stamp), not a migrated
   database, so it has no `story_identity` table, and item 3's
   initialization write raises `UndefinedTable`. The order puts this file out
   of scope (809-S3b), so it is not edited. Run alone, `[desktop-reset]`
   fails the same way; in the combined run it fails with `DuplicateDatabase`
   because the `[fresh]` failure leaves its `nexus_m10_fresh_test_<pid>`
   database behind.

```
    replace_story_identity(cur, origin="wizard")
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cur = <cursor object at 0x10bbf7880; closed: -1>

    def replace_story_identity(cur: Any, *, origin: StoryOrigin) -> str:
        """Replace the database's identity with a new story_uuid and return it.
    
        Deleting the old row cascades to its story_lineage rows.
        """
>       cur.execute("DELETE FROM public.story_identity")
E       psycopg2.errors.UndefinedTable: relation "public.story_identity" does not exist
E       LINE 1: DELETE FROM public.story_identity
E                           ^

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit "tests/test_new_story_setup.py::test_fresh_database_is_baseline_stamped[desktop-reset]"
E       psycopg2.errors.UndefinedTable: relation "public.story_identity" does not exist
E       LINE 1: DELETE FROM public.story_identity
E                           ^
...
----------------------------- Captured stderr call -----------------------------
dropdb: error: database removal failed: ERROR:  database "nexus_m10_fresh_test_85266" is being accessed by other users
DETAIL:  There is 1 other session using the database.
------------------------------ Captured log call -------------------------------
WARNING  nexus.new_story_setup:new_story_setup.py:250 Dropped database nexus_m10_fresh_test_85266 if it existed
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: nexus_m10_fresh_test_85266, nexus_m10_template_test_85266, postgres
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_new_story_setup.py::test_fresh_database_is_baseline_stamped[desktop-reset]
1 failed in 6.27s
```

   A scratch plant that adds the `story_identity` table to that stand-in
   (reverted before commit) makes the whole file pass, so the only cause is
   the stand-in's missing table:

```
diff --git a/tests/test_new_story_setup.py b/tests/test_new_story_setup.py
index 7991c5b4..365bc99a 100644
--- a/tests/test_new_story_setup.py
+++ b/tests/test_new_story_setup.py
@@ -107,6 +107,14 @@ def template_db() -> Generator[str, None, None]:
                     CREATE TABLE public.retrograde_summaries (
                         id BIGSERIAL PRIMARY KEY, summary_text TEXT
                     );
+                    CREATE TABLE public.story_identity (
+                        id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
+                        story_uuid UUID NOT NULL UNIQUE
+                            DEFAULT gen_random_uuid(),
+                        title TEXT,
+                        origin TEXT NOT NULL,
+                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
+                    );
                     CREATE TABLE public.memory_idf_corpora (
                         corpus_kind TEXT PRIMARY KEY,
                         analyzer_version TEXT NOT NULL,

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: nexus_m10_fresh_test_86407, nexus_m10_template_test_86407, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
13 passed in 18.46s
```

   The failing test leaves its `nexus_m10_fresh_test_<pid>` database; three
   such databases remain on the server (`nexus_m10_fresh_test_23348`, `_70591`,
   `_85266`; re-read 2026-10-08 00:06 CDT, no session holds any of them).
   They are not `qa640_` names, so they were not dropped here. Both the
   stand-in edit (in `tests/test_new_story_setup.py`, which the order assigns
   to 809-S3b) and the drop are the coordinator's decisions; until one of
   them lands, both ids are known landing failures.

No other gate failure came from a narrative read, so no seed needed
`replace_story_identity` beyond the overwrite mirror the order names.

## Offline Suites

`tests --ignore=tests/test_api --ignore=tests/test_orrery` takes more than ten
minutes on this machine, so it ran in three pieces that together cover it
exactly: the top-level `tests/test_[a-l]*.py`, the top-level
`tests/test_[m-z]*.py`, and the subdirectories (every top-level file ignored).

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_[a-l]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
633 passed, 170 skipped, 5 warnings in 319.06s (0:05:19)
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_[m-z]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1373 passed, 319 skipped, 8 warnings in 139.84s (0:02:19)
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery $(for f in tests/test_*.py; do echo --ignore=$f; done)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
958 passed, 83 skipped, 7 warnings in 141.41s (0:02:21)
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1847 passed, 1370 skipped, 7 warnings in 51.37s
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
96 passed, 5 warnings in 19.57s
```

The one offline failure is expected failure 1 above.

## Static Checks

Rerun at b44fde18 (review fixes). `<fix>` is
`<scratch>/822-S1-resume-2/fix1`; `changed_py.txt` holds the 20 Python files
`git diff --name-only origin/main...HEAD -- '*.py'` lists, and
`preexisting.txt` the 17 of them that exist on `origin/main`. The `origin/main`
versions were extracted whole (`git archive origin/main nexus scripts tests
pyproject.toml .flake8 nexus.toml config | tar -x -C <fix>/main_full`) so the
same commands resolve the same imports there.

```
$ $PY -m black --check $(cat <fix>/changed_py.txt)
All done! ✨ 🍰 ✨
20 files would be left unchanged.

$ nice -n 15 $PY -m flake8 $(cat <fix>/changed_py.txt) > <fix>/flake8-branch.txt
branch rc=1 lines=63
$ cd <fix>/main_full && nice -n 15 $PY -m flake8 $(cat <fix>/preexisting.txt) > <fix>/flake8-main.txt
main rc=1 lines=63
$ sed -E 's/:[0-9]+:[0-9]+:/:/' flake8-branch.txt | sort > f8b.txt   # and the same for main into f8m.txt
$ comm -23 f8b.txt f8m.txt          # diagnostics new in branch
(empty)

$ nice -n 15 $PY -m mypy --explicit-package-bases $(cat <fix>/changed_py.txt) > <fix>/mypy-branch.txt
branch rc=1
Found 37 errors in 8 files (checked 20 source files)
$ cd <fix>/main_full && nice -n 15 $PY -m mypy --explicit-package-bases $(cat <fix>/preexisting.txt) > <fix>/mypy-main.txt
main rc=1
Found 316 errors in 59 files (checked 17 source files)
$ grep -F -f <(sed 's/$/:/' preexisting.txt) mypy-main.txt | grep -v '^Found' > mypy-main-checked.txt
$ grep -c ': error:' mypy-main-checked.txt mypy-branch.txt
mypy-main-checked.txt:37
mypy-branch.txt:37
$ sed -E 's/:[0-9]+: /: /' mypy-branch.txt | grep -v '^Found' | sort > mb.txt   # and mypy-main-checked.txt into mm.txt
$ comm -23 mb.txt mm.txt            # diagnostics new in branch
(empty)

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
$ $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
```

In the extracted `origin/main` tree mypy also reports errors in modules the
17 files import (316 in 59 files); the comparison keeps only the 37 errors
reported on the 17 checked files, which match the branch's 37 one for one.
The three new files (`nexus/api/story_identity.py`,
`scripts/backfill_story_identity.py`, `tests/test_story_identity_pg.py`) have
no flake8 or mypy diagnostic.

Pre-existing diagnostics: every flake8 and mypy diagnostic on the changed
files is on an untouched line and is also reported on `origin/main`.

## UI

`node_modules` came from `npm --prefix ui ci` in this worktree during the
first resume (15:09 CDT; `package-lock.json` is unchanged on this branch):

```
$ npm --prefix ui ci
added 959 packages, and audited 960 packages in 5s
```

`reader-draft.ts`, `useReaderDraft.ts`, `types/narrative.ts` and the new
`reader-draft.test.ts` are in the state-surface input closure, so the receipt
was regenerated with `npm --prefix ui run resolve-state-surfaces` in seven
bounded condition batches (four conditions each, the last three), then
assembled, under `nice -n 15`:

```
=== batch 1 start Wed Oct  7 22:58:32 CDT 2026 : w1101-1279/reduce,w1-639/reduce,w1-639/motion/start,w1-639/motion/trough
=== batch 1 end Wed Oct  7 23:05:04 CDT 2026 rc=0
=== batch 2 start Wed Oct  7 23:05:04 CDT 2026 : w640-760/reduce,w640-760/motion/start,w640-760/motion/trough,w761-767/reduce
=== batch 2 end Wed Oct  7 23:11:43 CDT 2026 rc=0
=== batch 3 start Wed Oct  7 23:11:43 CDT 2026 : w761-767/motion/start,w761-767/motion/trough,w768-1023/reduce,w768-1023/motion/start
=== batch 3 end Wed Oct  7 23:18:33 CDT 2026 rc=0
=== batch 4 start Wed Oct  7 23:18:33 CDT 2026 : w768-1023/motion/trough,w1024-1100/reduce,w1024-1100/motion/start,w1024-1100/motion/trough
=== batch 4 end Wed Oct  7 23:25:16 CDT 2026 rc=0
=== batch 5 start Wed Oct  7 23:25:16 CDT 2026 : w1101-1279/motion/start,w1101-1279/motion/trough,w1280/reduce,w1280/motion/start
=== batch 5 end Wed Oct  7 23:32:06 CDT 2026 rc=0
=== batch 6 start Wed Oct  7 23:32:06 CDT 2026 : w1280/motion/trough,w1281-1535/reduce,w1281-1535/motion/start,w1281-1535/motion/trough
=== batch 6 end Wed Oct  7 23:38:48 CDT 2026 rc=0
=== batch 7 start Wed Oct  7 23:38:48 CDT 2026 : w1536+/reduce,w1536+/motion/start,w1536+/motion/trough
=== batch 7 end Wed Oct  7 23:45:18 CDT 2026 rc=0
=== assemble Wed Oct  7 23:45:18 CDT 2026
=== ALL DONE rc=0 Wed Oct  7 23:45:20 CDT 2026
Resolved painted state surfaces: renders=103074; wall=2800.003s (sum of bounded capture shards); Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 27 media conditions; file://; network aborted; requests=0; errors=0
Wrote /Users/pythagor/nexus/.claude/worktrees/822-story-identity/ui/client/src/state-surfaces.resolved.json; module graph=2095 inputs; SHA-256 f9b4869510b1ee91d54813760373e2e28822473f85024fb8976a847d30580c43
```

The receipt shrank from 444,566,294 to 168,893,558 bytes (LFS pointer
sizes on `origin/main` and on this branch) because it was written by the
batched `resolve-state-surfaces -- --assemble` path, which writes compact
single-line JSON (`ui/scripts/resolve-state-surfaces.mjs:43`,
`JSON.stringify(merged)`), instead of the earlier unbatched write, which
pretty-prints (`:464`, `JSON.stringify(results, null, 2)`; the old receipt
had 13,680,322 lines, the new one has 1). Sample parity is unchanged, as
the comparison below shows.

Measurements are unchanged. Every painted core mean, histogram, core size and
mask size in the new receipt equals the previous one (a comparison script
walked every `meanLinear` sample under `conditions`); the media inventory is
identical, and the only changed fingerprint inputs are this branch's four UI
files:

```
{"samplesOld":101520,"samplesNew":101520,"missingInNew":0,"extraInNew":0,"meansDiffer":0,"maxAbsMeanDiff":0,"histogramsDiffer":0,"coreOrMaskSizeDiffer":0}
media identical: true
changed input files: client/src/hooks/useReaderDraft.ts, client/src/lib/reader-draft.ts, client/src/types/narrative.ts, client/src/lib/reader-draft.test.ts
```

```
$ nice -n 15 npm --prefix ui test
 Test Files  39 passed (39)
      Tests  602 passed (602)
   Start at  23:45:45
   Duration  56.49s (transform 2.71s, setup 8.17s, collect 15.71s, tests 69.65s, environment 40.04s, prepare 17.70s)

$ (nice -n 15 npm --prefix ui run check; echo rc=$?)    # rerun at b44fde18
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

rc=0
```

No UI element was added, so no shadcn component applies.

## Review Fixes (2026-10-08, Commit b44fde18)

`test_doctor_identity_outcomes` now runs every branch through the registered
check functions: `migrate.TEMPLATE_DB` is patched to a template clone for
`_check_template_story_identity`, and `_check_slot_story_identity` reads a
readiness context whose `[runtime.readiness].slots` is `[3, 4]`, with slot 3
routed to a clone and slot 4 to a name the server lacks
(`route_slots_to_disposable`). The remediations are asserted exactly,
including ` --write-locked-slot` on the locked routed slot.
`test_backfill_mints_and_links` adds the two refusals the script makes:
a fork whose child is not a target (`ValueError`, nothing written) and a
child that already forks another parent (`RuntimeError`, lineage
unchanged).

Each guard plant (reverted before commit; `git status --short` showed only
the test file afterwards) turns the extended test red:

```
$ git diff scripts/    # plant 1: <fix>/guard-plant-1.diff
-        if fork.child not in targets:
-            raise ValueError(f"fork child {fork.child} is not a backfill target")
+        pass  # plant: target guard removed
load check 00:03:02: { 17.24 21.40 24.63 }
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_story_identity_pg.py::test_backfill_mints_and_links
E           RuntimeError: qa640_822_backfill_b_1acf550d195b holds 0 story_identity rows; exactly one is required
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner server: local:5432
dbname audit: owner targets: none
1 failed in 4.02s

$ git diff scripts/    # plant 2: <fix>/guard-plant-2.diff (the `elif parents:` raise removed)
load check 00:03:14: { 20.25 21.91 24.77 }
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_story_identity_pg.py::test_backfill_mints_and_links
E           Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_story_identity_pg.py:299: Failed
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner server: local:5432
dbname audit: owner targets: none
1 failed in 4.28s
```

At b44fde18, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT`
unset:

```
load check 00:05:55: { 14.39 20.43 23.81 }
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_story_identity_pg.py tests/test_runtime/test_readiness_pg.py
...............                                                          [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 28 targets: postgres, qa640_1013_readiness_* x2, qa640_822_backfill_a_*, qa640_822_backfill_b_*, qa640_822_backfill_t_*, qa640_822_clone_*, qa640_822_clone_bare_*, qa640_822_clone_src_*, qa640_822_constraints_*, qa640_822_detach_*, qa640_822_detach_bare_*, qa640_822_detach_src_*, qa640_822_doctor_s_*, qa640_822_doctor_t_*, qa640_822_init_*, qa640_822_migration_*, qa640_822_reset_*, qa640_822_reset_src_*, qa640_822_transition_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
15 passed in 40.79s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
96 passed, 5 warnings in 16.38s
```

Not done here, because each needs the coordinator: the `story_identity`
table in `tests/test_new_story_setup.py`'s `template_db` stand-in (the order
assigns that file to 809-S3b), and dropping the three leftover
`nexus_m10_fresh_test_*` databases (not `qa640_` names). Until one of the
stand-in options lands, `test_fresh_database_is_baseline_stamped[fresh]`
and `[desktop-reset]` are known landing failures, beside
`test_migration_sequence_has_only_known_gaps`.

## Landing Notes for the Coordinator

Migration 146 lands after 144 and 145. Then `python scripts/migrate.py --all`,
`python scripts/migrate.py --slot 1 --write-locked-slot`, then
`python scripts/backfill_story_identity.py --all --write-locked-slot`, then
`nexus doctor` green (`template.story_identity_absent`,
`slots.story_identity_present`). Product code changes, so the gateway restart
is owed after the backfill (a narrative read raises `StoryIdentityError` on a
slot without a row), and `ui/` changes, so the UI bundle is rebuilt.


## Codex Review Fixes (2026-10-08)

This section supersedes the earlier outstanding preflight findings and expected
initialization/migration-sequence failures. The branch already includes
`origin/main` at `afd034f360e625f8bc4ffa8a717dda28422b19c7`, containing migrations
144 and 145. Import provenance printed this worktree's `nexus/__init__.py`.

- Clone setup validates both identity tables and the singleton row count in a
  read-only source connection before disposing or dropping its target. It also
  refuses a source equal to the target. The regression retains an occupied
  target's sentinel row when either a malformed identity or pre-146 source is
  rejected, and checks that the refusal leaves no open target connection.
- Backfill validates every target and external fork parent before any UUID
  insert: both tables, row counts, origins, existing lineage, self-parentage,
  and conflicting parent requests. Nine real-PostgreSQL failure cases prove
  that an earlier empty target stays empty. Existing successful minting,
  idempotence, lineage and locked-session tests remain green. Transactions are
  still per database; the script now states that connection failures or
  concurrent edits can leave a partial run rather than promising fleet atomicity.
- The deliberately stamped minimal template fixture now contains the full
  identity and lineage DDL, including all constraints. Both fresh and desktop
  reset initialization cases pass. The added identity imports in shared clone
  helpers follow their existing import groups. `_owner_fork` rejects values
  outside its two supported CLI choices even when called directly.

The PostgreSQL sessions ran one at a time, at nice 15, with load below 24.
Their exact commands and final summaries follow. The two skips are the existing
`requires_corpus` tests; no fleet data-clone test was opted into.

```text
uptime load averages: 3.85 3.81 3.50
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_story_identity_pg.py tests/test_new_story_setup.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 60 targets: nexus_m10_fresh_test_32152, nexus_m10_template_test_32152, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_822_backfill_a_*, qa640_822_backfill_b_*, qa640_822_backfill_t_*, qa640_822_clone_*, qa640_822_clone_bare_*, qa640_822_clone_invalid_*, qa640_822_clone_pre146_*, qa640_822_clone_src_*, qa640_822_constraints_*, qa640_822_detach_*, qa640_822_detach_bare_*, qa640_822_detach_src_*, qa640_822_doctor_s_*, qa640_822_doctor_t_*, qa640_822_init_*, qa640_822_migration_*, qa640_822_preflight_a_* x9, qa640_822_preflight_b_* x9, qa640_822_preflight_parent_* x9, qa640_822_reset_*, qa640_822_reset_src_*, qa640_822_transition_*, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
32 passed in 78.43s (0:01:18)
```

```text
uptime load averages: 9.30 6.18 4.48
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_api/test_reader_draft_identity_pg.py tests/test_api/test_slot_state.py tests/test_runtime/test_readiness_pg.py tests/test_runtime/test_readiness.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_orrery/test_need_clock_anchor_pg.py tests/test_api/test_mock_wizard_responses.py tests/test_orrery/test_retrograde_constraints_pg.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 57 targets: mock, nexus_test_issue_613_*, postgres, qa640_* x18, qa640_1013_readiness_* x2, qa640_885_ren_replay_* x4, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_issue601_* x4, qa640_renamed_test_model_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa951_identity_* x4, qa951_no_identity_*, qa951_overwrite_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:53225 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:53226 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:53225 (psycopg2), save_04@local:53226 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
224 passed, 2 skipped, 7 warnings in 95.09s (0:01:35)
```

```text
uptime load averages: 5.07 5.58 4.48
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_story_identity_pg.py::test_clone_forks_with_lineage tests/test_doc_front_matter.py tests/test_reachability.py tests/test_owner_target_guard.py tests/test_pg_target_contract.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 7 targets: postgres, qa640_822_clone_*, qa640_822_clone_bare_*, qa640_822_clone_invalid_*, qa640_822_clone_pre146_*, qa640_822_clone_src_*, qa804_fixture_target
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
286 passed in 26.88s
```

Static checks used the same seven edited Python files (`FILES` below); main
comparison used the five pre-existing files exported with
`git show origin/main:<path>` into `/tmp/822-story-identity-static`, with
`PYTHONPATH` and `MYPYPATH` pointing at this worktree. The two new branch files
have no diagnostics. Flake8 used the worktree's explicit `.flake8` in both
runs so its 88-column rule was identical. Removing only diagnostic line and
column numbers before comparison showed no new diagnostics.

```text
FILES="scripts/backfill_story_identity.py scripts/new_story_setup.py scripts/qa_shift/ann_gate.py scripts/qa_shift/historical_passage_limit.py tests/pg_fixtures.py tests/test_new_story_setup.py tests/test_story_identity_pg.py"
$ PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black --check $FILES
7 files would be left unchanged.
$ PYTHONPATH=$PWD MYPYPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m flake8 --config=$PWD/.flake8 $FILES
branch: 15 pre-existing diagnostics; main: 15 pre-existing diagnostics; new: 0
$ PYTHONPATH=$PWD MYPYPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases $FILES
branch: 8 errors in 4 files; main: 8 errors in 4 files; new: 0
$ PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
$ PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
$ git diff --check
(no output)
```

No UI source or generated UI artifact changed in this review fix; the earlier
UI proof remains recorded above. The coordinator still owes the combined
whole-tree gate. No owner database was mutated, no fleet migration/backfill
was run, and no service was restarted. This proof created no leftover
fixture database; the three historical leftovers named above were not touched.

Codex — GPT-6

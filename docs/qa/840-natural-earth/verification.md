# 840-S1 Verification: Pin and Load the Natural Earth Reference Dataset

Issue #840, work order 840-S1. Owner ruling Arachne Sequence 39 (geometry
dataset: Natural Earth); Decisions 840-Q1 (per-slot public table, vendored
files) and 840-Q2 (10m land, admin-0, admin-1). No paid call, no gateway lane,
no write to any `save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07`; every
database written below is a disposable `qa640_840_*` clone the test fixtures
create and drop.

## Resumed on 2026-10-07

The coordinator stopped the first builder at 12:50 CDT (machine load, not the
work). At resume the worktree was clean (`git status --short` empty) and the
branch held three commits over `364fef4b`:

| commit | order items covered | left unfinished |
|---|---|---|
| `e5f467c0` Vendor the pinned Natural Earth 5.1.1 10m layers | 1 (zips, `.gitignore`, `LICENSE.md`), 2 (`manifest.json`) | nothing |
| `f4e5e323` Load Natural Earth into a per-slot reference table and query it | 3 (migration 147), 4 (`geo_reference.py`), 5 (`load_natural_earth.py`), 6 (`TEMPLATE_SEED_TABLES` entry), both test files | nothing in code; no proof had run |
| `131f9c03` Document the Natural Earth reference and register its loader | 6 (`CLAUDE.md` recipe, `AGENTS.md` re-stamp), 7 (`docs/database.md`), 8 (`config/reachability.toml`) | `AGENTS.md` stamp went stale once main moved |

No uncommitted files existed, so nothing was discarded. Work done on resume:
reviewed every committed file against the order; re-checked every source fact
(below); merged `origin/main` (`b0da93ea`, a clean merge, commit `374dbbde`);
moved `AGENTS.md` `verified_commit` to the new merge base `b0da93ea` (commit
`f8521f4a`; `AGENTS.md` names no seed table, so its text stands); ran the
proof, both red runs, the static checks; wrote this file.

## Source Files

`shasum -a 256 data/natural_earth/*.zip`:

```
ce1ac7036499a0edd641fbc093cd209a98f96a49d2eca8480aaacad35138a7f6  data/natural_earth/ne_10m_admin_0_countries.zip
efc59726337323058f9446210adc96673179cd344e053666ee3d28cb58ba2b05  data/natural_earth/ne_10m_admin_1_states_provinces.zip
e547d749445eaa0964aba76738090ec88f5e63c4585122170f98c67a7ea922dc  data/natural_earth/ne_10m_land.zip
```

Sizes 4,930,492, 14,909,524 and 3,269,070 bytes, as the order's table. Each
zip's `<stem>.VERSION.txt` (`unzip -p ... | od -c`), and `.cpg`:

```
        7  05-08-2022 23:48   ne_10m_admin_0_countries.VERSION.txt
0000000    5   .   1   .   1  \r  \n
UTF-8
        7  05-08-2022 23:53   ne_10m_admin_1_states_provinces.VERSION.txt
0000000    5   .   1   .   1  \r  \n
UTF-8
        7  05-08-2022 23:54   ne_10m_land.VERSION.txt
0000000    5   .   1   .   1  \r  \n
UTF-8
```

`git check-attr -a data/natural_earth/ne_10m_land.zip` prints nothing: the zips
are plain git objects (`.gitattributes` routes only images and one resolved
JSON through LFS). `LICENSE.md` paragraphs compared against
`https://www.naturalearthdata.com/about/terms-of-use/` fetched 2026-10-07: the
text of both paragraphs matches (the page wraps the names in `<em>`).
`ogr2ogr --version`: `GDAL 3.8.5, released 2024/04/02`.

## Review Fixes (Commit `6a1be51d`)

The review of PR #1116 confirmed four code and evidence findings; commit
`6a1be51d` applies the code ones, and every PostgreSQL tail below from this
heading on ran on `6a1be51d` (the earlier tails ran on `78a92f35` and are
replaced).

- `require_reference` first reads `to_regclass('public.natural_earth_features')`
  and raises `ReferenceDataError` naming `land, admin_0, admin_1` ("table ...
  missing; apply migration 147") when it is NULL, so a database without
  migration 147 refuses instead of raising `UndefinedTable` and aborting the
  caller's transaction. New test `test_missing_table_refuses` drops the table
  in a rolled-back transaction on the empty clone, expects that error, proves
  the cursor still runs `SELECT 1` (transaction not aborted), and proves the
  table is back after the rollback.
- `write_reference` commits through `nexus.database.transaction()`
  (`with closing(conn), transaction(conn), conn.cursor() as cur:`, the
  `rebuild_memory_idf.py` model). `_load_target` catches `AmbiguousCommit`
  before `psycopg2.Error`, logs "outcome unknown ...; rerun to replace the
  rows", returns status `commit_unknown`, and `main` counts that status as a
  failure (exit 1). The `docs/database.md` section says so.
- `AmbiguousRegionError.__init__` gains `-> None`.
- Evidence: the source-fact read is rerun under `nice -n 15` after the bounded
  load wait, the `-99` fact is now counted from the raw source rows, and every
  pasted PostgreSQL tail runs from the guard line to the summary.

## Review Fixes, Round 2 (Commit `389c79e5`)

The second review of PR #1116 confirmed five findings (two describe one
defect, the untested `commit_unknown` path). Commit `389c79e5` applies them;
every tail in this section ran on its tree. The other sections keep their
tails from `6a1be51d`, whose claims these fixes do not change.

- `_read_features` no longer passes `check=True`: a non-zero `ogr2ogr` exit
  raises the new `NaturalEarthReadError(RuntimeError)` with the zip, the exit
  code, the shapefile and GDAL's own stderr (decoded with `errors="replace"`).
  The dedicated error was taken over reusing `NaturalEarthFeatureCountError`
  because nothing was counted. New test `test_ogr2ogr_failure_carries_gdal_message`
  asks the real `ogr2ogr` for a member the land zip does not hold and expects
  `ogr2ogr exited 1 reading qa840_missing.shp` and GDAL's
  `Unable to open datasource` in the message.
- New test `test_connection_lost_at_commit_is_commit_unknown` (modelled on
  `tests/test_rebuild_memory_idf_pg.py:536-605`) uses its own clone
  `qa640_840_commit_*`, because a deferred constraint trigger
  `AFTER INSERT ON natural_earth_features` that ends its own backend poisons
  every commit. It proves: `load_reference(clone)` raises `AmbiguousCommit`
  naming the clone; `_load_target(clone, read_reference_files(),
  write_locked_slot=False)` returns `("commit_unknown", None)`;
  `main(["--dbname", clone])` returns 1 and prints `<clone>: commit_unknown`;
  both ERROR records say "outcome unknown" and none says "rolled back"; the
  table still holds 0 rows (the fault ends the backend before the commit
  record); after the trigger is dropped, `main` exits 0 and the counts are
  11, 258, 4,596.
- `docs/database.md`, Natural Earth section only: the load is named as an
  exception to the never-replay rule, with the reason (one transaction deletes
  every row and inserts the same pinned, checksummed files, so a replay is
  idempotent whether or not the lost COMMIT landed). The rerun advice in the
  loader docstring and log message stays. The sentence at
  `docs/database.md:125-126` ("the one mutation a replay after
  `AmbiguousCommit` is allowed for") is outside this order's edit scope
  (item 7); the PR body carries a landing note to name both mutations there.
- `config/reachability.toml:27`: the operator reason now cites only
  `docs/database.md` (`CLAUDE.md` never names the loader).

Load: `uptime` read 23.10 (one-minute) before the green run; the red run
started at 31.43 without the bounded wait (an omission on my part; the run
is one 22-second test).

Green, `NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_geo_reference_pg.py`
with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

```
840 timings: load_reference 6.85s; initialize_slot_database from loaded clone 1.98s, from empty clone 0.99s
...                                                             [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_840_commit_*, qa640_840_empty_*, qa640_840_fresh_* x2, qa640_840_geo_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
12 passed in 57.25s
```

Red: `main`'s failure tuple planted as `("failed",)` (line 432 without
`"commit_unknown"`), same command with `-k commit_unknown`, plant reverted
afterwards:

```
>               assert load_natural_earth.main(["--dbname", dbname]) == 1
E               AssertionError: assert 0 == 1
E                +  where 0 = <function main at 0x10cfac860>(['--dbname', 'qa640_840_commit_b062a329896f'])
E                +    where <function main at 0x10cfac860> = load_natural_earth.main
...
ERROR    nexus.load_natural_earth:load_natural_earth.py:352 qa640_840_commit_b062a329896f: Natural Earth load outcome unknown (connection lost during COMMIT: Ambiguous commit for database qa640_840_commit_b062a329896f: server closed the connection unexpectedly This probably means the server terminated abnormally before or while processing the request.); rerun to replace the rows
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_840_commit_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_geo_reference_pg.py::test_connection_lost_at_commit_is_commit_unknown
1 failed, 11 deselected in 22.06s
```

Offline, `nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py tests/test_orrery/test_natural_earth_manifest.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
104 passed, 5 warnings in 15.64s
```

Black (`--check`), flake8 and `$PY -m mypy --explicit-package-bases` on
`scripts/load_natural_earth.py` and `tests/test_orrery/test_geo_reference_pg.py`:
`2 files would be left unchanged.`; flake8 exit 0; `Success: no issues found
in 2 source files`. `$PY -S scripts/check_exception_dispositions.py
--baseline-base-ref origin/main`: `OK: exception disposition coverage and
shrink-only baseline verified.`

## Loader Listing, Counts and Facts

The loader's invalid-feature listing (on `6a1be51d`, from the
`--log-cli-level=INFO` run of `tests/test_orrery/test_geo_reference_pg.py`
below; three loads in that file, each lists the same two features):

```
INFO     nexus.load_natural_earth:load_natural_earth.py:263 qa640_840_geo_0c7e457fd65e: invalid admin_0 feature ne_id=1159320575 source_index=161: Ring Self-intersection[35.6210871060001 23.1392929140001]
INFO     nexus.load_natural_earth:load_natural_earth.py:263 qa640_840_geo_0c7e457fd65e: invalid admin_1 feature ne_id=1159309897 source_index=3813: Ring Self-intersection[-47.3024818588507 -16.040054212432]
```

A read of a disposable clone loaded by `load_reference` (scratch script
`840-S1-resume/evidence_facts.py`, which creates `qa640_840_evidence_*`
through `disposable_slot_database` and drops it). Run on `6a1be51d` as
`PYTHONPATH=$PWD nice -n 15 $PY <scratch>/840-S1-resume/evidence_facts.py`
after the bounded load wait (`uptime` read `16.93 24.66 28.60`; the wait loop
returned at once, the one-minute load being below 24; `uptime` at start
`18.38 24.72 28.58`). Its first line counts the `ISO_A3` literal in the raw
`admin_0` rows that `ogr2ogr` reads (`_read_features`), before the loader
turns `-99` into NULL:

```
source admin_0 ISO_A3: features 258 | literal '-99': 22 | NULL: 0
load_reference {'land': 11, 'admin_0': 258, 'admin_1': 4596} 7.44s
counts: [('admin_0', 258), ('admin_1', 4596), ('land', 11)]
releases: [(['5.1.1'],)]
invalid/srid/type: [(0, 0, 0)]
pg_total_relation_size: [(31432704, '30 MB')]
vertices: [(2289967,)]
dup ne_id: [('admin_0', 0), ('admin_1', 0)]
dup adm0_a3 admin_0: [(0,)]
dup adm1_code admin_1: [(0,)]
repeated admin_1 names (non-NULL groups): [(95,)]
NULL admin_1 names: [(7,)]
admin_0 loaded iso_code NULL: [(22,)]
La Paz: [('BOL-1936',), ('HND-649',), ('SLV-1347',)]
Denver land: [(True,)]
Denver admin_1: [('Colorado', 'USA-3522')]
(-140,30) land: [(False,)]
repair admin_0 1159320575: ('EGY', None, 'Ring Self-intersection[35.6210871060001 23.1392929140001]', 1001058474902.3036, 1001058474902.3036, True, 'MULTIPOLYGON')
repair admin_1 1159309897: ('BRA', 'BRA-1294', 'Ring Self-intersection[-47.3024818588507 -16.040054212432]', 341247103614.5597, 341247103614.5597, True, 'MULTIPOLYGON')
```

22 source `ISO_A3` values are the literal `-99` and none is NULL, so the 22
loaded NULL `iso_code` rows are exactly the converted `-99` values. The repair
rows read: source validity reason, geography area of the source geometry,
geography area after the `method=structure` repair (equal), valid, type.
Every fact in the order's table and paragraph holds; nothing differs. (The
first read, on `78a92f35`, started at a one-minute load of 27.84 without the
wait; this rerun replaces it. Its numbers were the same except
`pg_total_relation_size` 31,440,896 bytes, also 30 MB.)

## Timings

From the focused proof run on `6a1be51d` (`test_fresh_slot_copies_reference`
prints them):

```
840 timings: load_reference 6.98s; initialize_slot_database from loaded clone 2.36s, from empty clone 1.18s
```

From the `--log-cli-level=INFO` run of the same file on `6a1be51d`:

```
840 timings: load_reference 7.15s; initialize_slot_database from loaded clone 2.15s, from empty clone 1.07s
```

Earlier runs on `78a92f35`: 7.56 s, 1.96 s and 1.02 s; 8.01 s, 2.15 s and
1.35 s. So once the template holds the rows, each default clone pays about
0.8 to 1.2 seconds more (the copy of a 30 MB table, about 2.3 million
vertices) under a one-minute machine load near 20.

## Red Runs

Both on `6a1be51d`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` unset, each after the bounded load wait.

Plant 1: in `read_reference_files` the checksum loop reads
`for layer in manifest.layers[:0]:` (step removed). Reverted with
`git checkout scripts/load_natural_earth.py`. The wait took 210 s (`uptime`
read `26.53 26.19 29.00` before it).

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_geo_reference_pg.py::test_checksum_mismatch_refuses
```

```
E       Failed: DID NOT RAISE <class 'scripts.load_natural_earth.NaturalEarthChecksumError'>
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_840_empty_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_geo_reference_pg.py::test_checksum_mismatch_refuses
1 failed in 9.54s
```

Plant 2: `"public.natural_earth_features"` removed from
`TEMPLATE_SEED_TABLES`. Reverted with `git checkout scripts/new_story_setup.py`.
No wait (`uptime` `19.93 25.94 28.45`).

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_geo_reference_pg.py::test_fresh_slot_copies_reference
```

```
>           assert _counts(fresh) == EXPECTED_COUNTS
E           AssertionError: assert {} == {'admin_0': 2...6, 'land': 11}
E             
E             Right contains 3 more items:
E             {'admin_0': 258, 'admin_1': 4596, 'land': 11}
E             Use -v to get more diff

tests/test_orrery/test_geo_reference_pg.py:310: AssertionError
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_840_empty_*, qa640_840_fresh_*, qa640_840_geo_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_geo_reference_pg.py::test_fresh_slot_copies_reference
1 failed in 12.03s
```

## PostgreSQL Proof

On `6a1be51d`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT`
unset, after the bounded load wait (no wait needed: `uptime`
`18.27 25.18 28.12`):

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_geo_reference_pg.py tests/test_orrery/test_natural_earth_manifest.py tests/test_new_story_setup.py tests/test_postgres_tools.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```
E       AssertionError: assert {'013', '119'... '145', '146'} == frozenset({'013', '119'})
E         
E         Extra items in the left set:
E         '145'
E         '144'
E         '146'
E         Use -v to get more diff

tests/test_orrery/test_migrate.py:266: AssertionError
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: mock, nexus_m10_fresh_test_19464, nexus_m10_template_test_19464, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_840_empty_*, qa640_840_fresh_* x2, qa640_840_geo_*, qa640_885_ren_replay_* x4, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:64469 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:64475 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:64469 (psycopg2), save_04@local:64475 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 294 passed, 2 skipped, 2 warnings in 119.83s (0:01:59)
```

The one failure is the expected migration gap: 144, 145 and 146 belong to
778-S1b, 783-S1a and 822-S1, still unmerged. `KNOWN_GAPS` is unchanged. The two
skips are the `requires_corpus` tests
`tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False|True]`
(`NEXUS_RUN_CORPUS` unset). The `save_04` admissions are on the two throwaway
clusters `test_connection_lifecycle.py` registers, not the owner server. One
more test passes than on `78a92f35` (293): `test_missing_table_refuses`.

The file on its own with logging, on `6a1be51d` (no wait needed: `uptime`
`20.39 23.38 26.95`):

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rs -o log_cli=true --log-cli-level=INFO tests/test_orrery/test_geo_reference_pg.py
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_840_empty_*, qa640_840_fresh_* x2, qa640_840_geo_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
============================= 10 passed in 29.16s ==============================
```

Per the machine-load rule the whole-tree PostgreSQL gate (three pieces) is not
run here; the coordinator runs it at landing.

## Offline Suites

The two large offline runs below ran on `78a92f35`; commit `6a1be51d` changes
only `geo_reference.py`, `load_natural_earth.py`, the PostgreSQL test file and
`docs/database.md`, whose tests ran above.

```
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2964 passed, 562 skipped, 8 warnings in 596.82s (0:09:56)
```

```
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
E       AssertionError: assert {'013', '119'... '145', '146'} == frozenset({'013', '119'})
E         Extra items in the left set:
E         '144'
E         '145'
E         '146'
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1855 passed, 1378 skipped, 7 warnings in 59.79s
```

The one failure is the same expected migration gap.

```
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_orrery/test_natural_earth_manifest.py tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
104 passed, 5 warnings in 15.14s
```

After the merge and the `AGENTS.md` re-stamp:

```
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
42 passed, 5 warnings in 4.75s
```

(Before the re-stamp, right after the merge, the same file failed
`test_declared_sources_carry_a_fresh_verified_commit`, as expected.)

On `6a1be51d`:

```
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_orrery/test_natural_earth_manifest.py tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
104 passed, 5 warnings in 17.40s
```

## Static Checks

```
$PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.

$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.

$PY -m black --check <5 changed Python files>
All done! ✨ 🍰 ✨
5 files would be left unchanged.

PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases nexus/agents/orrery/geo_reference.py scripts/load_natural_earth.py scripts/new_story_setup.py tests/test_orrery/test_geo_reference_pg.py tests/test_orrery/test_natural_earth_manifest.py
Success: no issues found in 5 source files
```

On `6a1be51d`, for the three Python files it changes:

```
$PY -m black --check nexus/agents/orrery/geo_reference.py scripts/load_natural_earth.py tests/test_orrery/test_geo_reference_pg.py
All done! ✨ 🍰 ✨
3 files would be left unchanged.

PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases nexus/agents/orrery/geo_reference.py scripts/load_natural_earth.py tests/test_orrery/test_geo_reference_pg.py
Success: no issues found in 3 source files

$PY -m flake8 nexus/agents/orrery/geo_reference.py scripts/load_natural_earth.py tests/test_orrery/test_geo_reference_pg.py
(no output, exit 0)

$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.

$PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
```

The new `AmbiguousCommit` handler in `_load_target` carries
`# nexus-exception-disposition: fail; reason=logged; safety=exit 1`.

flake8 on the five changed Python files reports only seven E501 lines in
`scripts/new_story_setup.py` (7, 51, 64, 111, 239, 340, 561); the same command
on `origin/main`'s copy reports the same seven (561 is 560 there, shifted by
the one added line). None is on a changed line.

### Pre-Existing Diagnostics

The seven `scripts/new_story_setup.py` E501 lines above. mypy: none.

## Codex Takeover on 2026-10-08

Merged `origin/main` at `afd034f3` into the branch in `ae4b4250`, kept the
reviewed runtime and migration code intact, and re-verified `AGENTS.md`.
Corrected the older IDF paragraph in `docs/database.md` to name both explicit
idempotent replay exceptions, matching the Natural Earth section.

Validation on `ae4b4250`:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_doc_front_matter.py tests/test_orrery/test_natural_earth_manifest.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
50 passed, 5 warnings in 4.56s
```

The initial run before committing the merge correctly refused the new stamp
as newer than the then-current merge base (`b0da93ea`): 1 failed, 49 passed.
The committed merge advances that base to `afd034f3`; the rerun above passes.
Existing independent review at `833ea270` found no actionable defect. The
combined migration 146–148 PostgreSQL gate is still pending; these focused
checks do not substitute for it. No owner database or service changed.

Codex — GPT-6

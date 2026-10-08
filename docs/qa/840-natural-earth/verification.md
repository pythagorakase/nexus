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

## Loader Listing, Counts and Facts

The loader's invalid-feature listing (pytest `--log-cli-level=INFO` on
`tests/test_orrery/test_geo_reference_pg.py`; three loads in that file, each
lists the same two features):

```
INFO     nexus.load_natural_earth:load_natural_earth.py:254 qa640_840_geo_d44ca170d8ab: invalid admin_0 feature ne_id=1159320575 source_index=161: Ring Self-intersection[35.6210871060001 23.1392929140001]
INFO     nexus.load_natural_earth:load_natural_earth.py:254 qa640_840_geo_d44ca170d8ab: invalid admin_1 feature ne_id=1159309897 source_index=3813: Ring Self-intersection[-47.3024818588507 -16.040054212432]
```

A read of a disposable clone loaded by `load_reference`
(scratch script `840-S1-resume/evidence_facts.py`, which creates
`qa640_840_evidence_*` through `disposable_slot_database` and drops it):

```
load_reference {'land': 11, 'admin_0': 258, 'admin_1': 4596} 7.97s
counts: [('admin_0', 258), ('admin_1', 4596), ('land', 11)]
releases: [(['5.1.1'],)]
invalid/srid/type: [(0, 0, 0)]
pg_total_relation_size: [(31440896, '30 MB')]
vertices: [(2289967,)]
dup ne_id: [('admin_0', 0), ('admin_1', 0)]
dup adm0_a3 admin_0: [(0,)]
dup adm1_code admin_1: [(0,)]
repeated admin_1 names (non-NULL groups): [(95,)]
NULL admin_1 names: [(7,)]
admin_0 iso_code NULL (source -99): [(22,)]
La Paz: [('BOL-1936',), ('HND-649',), ('SLV-1347',)]
Denver land: [(True,)]
Denver admin_1: [('Colorado', 'USA-3522')]
(-140,30) land: [(False,)]
repair admin_0 1159320575: ('EGY', None, 'Ring Self-intersection[35.6210871060001 23.1392929140001]', 1001058474902.3036, 1001058474902.3036, True, 'MULTIPOLYGON')
repair admin_1 1159309897: ('BRA', 'BRA-1294', 'Ring Self-intersection[-47.3024818588507 -16.040054212432]', 341247103614.5597, 341247103614.5597, True, 'MULTIPOLYGON')
```

The repair rows read: source validity reason, geography area of the source
geometry, geography area after the `method=structure` repair (equal), valid,
type. Every fact in the order's table and paragraph holds; nothing differs.
This read started at a one-minute load of 27.84 (I read `uptime` and ran
without waiting; every later PostgreSQL run waited for a load below 24).

## Timings

From the full proof run (`test_fresh_slot_copies_reference` prints them):

```
840 timings: load_reference 7.56s; initialize_slot_database from loaded clone 1.96s, from empty clone 1.02s
```

From the `--log-cli-level=INFO` rerun of the same file:

```
840 timings: load_reference 8.01s; initialize_slot_database from loaded clone 2.15s, from empty clone 1.35s
```

So once the template holds the rows, each default clone pays about 0.8 to 0.9
seconds more (the copy of a 30 MB table, about 2.3 million vertices) under a
machine load near 20.

## Red Runs

Plant 1: `read_reference_files` loops over `manifest.layers[:0]` in the
checksum step (step removed). Reverted with `git checkout`.

```
E       Failed: DID NOT RAISE <class 'scripts.load_natural_earth.NaturalEarthChecksumError'>
dbname audit: owner targets: none
FAILED tests/test_orrery/test_geo_reference_pg.py::test_checksum_mismatch_refuses
1 failed in 9.53s
```

Plant 2: `"public.natural_earth_features"` removed from
`TEMPLATE_SEED_TABLES`. Reverted with `git checkout`.

```
E           AssertionError: assert {} == {'admin_0': 2...6, 'land': 11}
E             Right contains 3 more items:
E             {'admin_0': 258, 'admin_1': 4596, 'land': 11}
dbname audit: owner targets: none
FAILED tests/test_orrery/test_geo_reference_pg.py::test_fresh_slot_copies_reference
1 failed in 14.22s
```

## PostgreSQL Proof

Run with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset, after
waiting about 11 minutes for the one-minute load to fall below 24 (it read
24.28, then 25.21; started at 22.34):

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_geo_reference_pg.py tests/test_orrery/test_natural_earth_manifest.py tests/test_new_story_setup.py tests/test_postgres_tools.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```
E       AssertionError: assert {'013', '119'... '145', '146'} == frozenset({'013', '119'})
E         Extra items in the left set:
E         '146'
E         '144'
E         '145'
tests/test_orrery/test_migrate.py:266: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: mock, nexus_m10_fresh_test_75901, nexus_m10_template_test_75901, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_840_empty_*, qa640_840_fresh_* x2, qa640_840_geo_*, qa640_885_ren_replay_* x4, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:49561 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:49565 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:49561 (psycopg2), save_04@local:49565 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 293 passed, 2 skipped, 2 warnings in 112.42s (0:01:52)
```

The one failure is the expected migration gap: 144, 145 and 146 belong to
778-S1b, 783-S1a and 822-S1, still unmerged. `KNOWN_GAPS` is unchanged. The two
skips are the `requires_corpus` tests
`tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False|True]`
(`NEXUS_RUN_CORPUS` unset). The `save_04` admissions are on the two throwaway
clusters `test_connection_lifecycle.py` registers, not the owner server.

The file on its own with logging (`-rs -o log_cli=true --log-cli-level=INFO`):

```
dbname audit: owner targets: none
============================== 9 passed in 31.77s ==============================
```

Per the machine-load rule the whole-tree PostgreSQL gate (three pieces) is not
run here; the coordinator runs it at landing.

## Offline Suites

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

flake8 on the five changed Python files reports only seven E501 lines in
`scripts/new_story_setup.py` (7, 51, 64, 111, 239, 340, 561); the same command
on `origin/main`'s copy reports the same seven (561 is 560 there, shifted by
the one added line). None is on a changed line.

### Pre-Existing Diagnostics

The seven `scripts/new_story_setup.py` E501 lines above. mypy: none.

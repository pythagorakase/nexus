# Schema Documentation Verification

## Scope and Catalog Evidence

Work order #819, branch `claude/819-schema-docs`, migration **127**. No application
server or paid provider was started. All hand-created databases use `qa640_*`;
existing PostgreSQL fixtures retain their own disposable names. No migration was
applied to `NEXUS_template`, the saves, or any other worktree.

The read-only template inventory contains **84 NEXUS-owned tables and 854
columns** in `public` and `assets`. Before 127, **15 tables and 294 columns** lack
comments. Migration 127 documents **all 15 tables and 280 columns**; **14 columns**
remain in the baseline with individual reasons. The work order's 16/299 totals
include the extension-owned `public.spatial_ref_sys` table and its five columns.
The gate excludes those objects through `pg_depend.deptype = 'e'`, not a table-name
allowlist (`tests/test_schema_documentation_pg.py:31`). The migration header
lists reader/writer evidence for each table; no existing comments are replaced.
The direct before/after proof preserves all **629 existing comments** and adds
**295 comments**, leaving **84/84 tables and 840/854 columns** documented.

Baseline debt: five cleared legacy wizard fields with no current reader; five
notebook columns with no column-specific reader/writer; the unused tag-clearance
override; two provider-era job provenance fields; and the legacy world-event
narration link. Exact qualified names and reasons live in `config/schema_docs_baseline.json`.

## PR #943 Review Corrections

Migration 127 is edited in place because the read-only fleet checks still show
zero 127 stamps. The two tag P1 findings now distinguish the last application
write from insertion and uncleared status from effective activity. Evidence:
`nexus/agents/orrery/tag_writer.py:897`, `:925`, and `:966` rewrite `applied_at`
and `applied_at_world_time`; `nexus/agents/orrery/resolver.py:450` and `:468`
apply the expiry predicate defined at `nexus/agents/orrery/tag_activity.py:20`.
A NULL clearance timestamp alone does not exclude an expired, unswept row.

All six baselined seed/zone columns were checked against `_row_to_cache` and
selected-seed/zone reconstruction, plus repository-wide reads under `nexus/`
and `scripts/`:

| Column in `assets.new_story_creator` | Result |
| --- | --- |
| `seed_potential_allies` | Documented and retired: merged into `SeedData.key_npcs` at `nexus/api/new_story_cache.py:566` and `:568`, exposed as `key_npcs` at `:396`. |
| `seed_initial_mystery` | Retained: no current reader; writer clears it at `nexus/api/new_story_cache.py:954`. |
| `seed_potential_obstacles` | Retained: no current reader; writer clears it at `nexus/api/new_story_cache.py:956`. |
| `seed_starting_location` | Retained: no current reader; writer clears it at `nexus/api/new_story_cache.py:953`. |
| `zone_approximate_area` | Retained: no current reader; writer clears it at `nexus/api/new_story_cache.py:964`. |
| `zone_boundary_description` | Retained: no current reader; writer clears it at `nexus/api/new_story_cache.py:963`. |

The five retained reasons now explicitly name the absent current reader instead
of appealing to unknown historical semantics. `global_variables.new_story` is
also documented and retired: `nexus/api/save_slots.py:68` selects it and `:113`
returns `is_active = not row.get("new_story", True)` for slot metadata. No flag
transition behavior is asserted. These retirements reduce the baseline from
16 to 14 columns and raise migration coverage from 278 to 280 column comments.

The sweep re-read all **55 timestamp column comments** in 127 and all **five
NULL-bearing comments**, checked template timestamp defaults read-only through
`pg_attribute`/`pg_attrdef`, and searched current writers for timestamp
assignments. In addition to the requested `entity_tags.applied_at` and
`entity_tags.cleared_at` corrections, it changed:

- `entity_tags.applied_at_world_time`: explicitly describes the most recent
  application and replacement/extension rewrites (`tag_writer.py:898`, `:926`,
  `:967`).
- `incubator.created_at`: describes insertion or most recent conditional draft
  replacement; `nexus/api/narrative_generation.py:584` updates the row and `:605`
  rewrites the timestamp to `NOW()`.

No further timestamp/NULL correction was identified. In particular, the lease
writer deletes an expired row before inserting its successor
(`nexus/api/narrative_lease.py:71`, `:101`), while embedding-claim replacement
already has explicit wording (`:185`). The other NULL comments remain supported:
`global_variables.model` follows model resolution (`nexus/config/story_model.py:140`),
lease `parent_chunk_id` is assigned on binding (`nexus/api/narrative_lease.py:125`),
relationship attribution is NULL when its transaction setting is absent
(`migrations/065_reconstructability.sql:103`), and an unstamped retrograde
embedding permits retry (`nexus/agents/orrery/retrograde_embedding.py:124`, `:158`).
The inventory-only enum/function/view counts were rechecked and are unchanged.

The required gates below were rerun for these amendments. No #885 exemption was
needed. No application server or paid provider was used.

## Inventory Beyond This Slice

The following are inventory only, excluding extension-owned objects in both
schemas by catalog OID and `pg_depend.deptype = 'e'`. Functions include ordinary
and window functions (`prokind IN ('f', 'w')`); views include ordinary and
materialized views (`relkind IN ('v', 'm')`).

| Object Kind | NEXUS-Owned Total | Without Comments |
| --- | ---: | ---: |
| Enums | 41 | 41 |
| Functions | 34 | 21 |
| Views | 16 | 5 |

Exact catalog query pattern (substitute the three rows below):

```sql
SELECT count(*) AS total,
       count(*) FILTER (
           WHERE nullif(btrim(obj_description(o.oid, '<catalog>')), '') IS NULL
       ) AS undocumented
FROM <catalog> o
JOIN pg_namespace n ON n.oid = o.<namespace_column>
WHERE n.nspname IN ('public', 'assets') AND <kind_predicate>
  AND NOT EXISTS (
      SELECT 1 FROM pg_depend d
      WHERE d.classid = '<catalog>'::regclass
        AND d.objid = o.oid AND d.deptype = 'e'
  );
```

| Kind | Catalog | Namespace Column | Kind Predicate |
| --- | --- | --- | --- |
| Enum | pg_type | typnamespace | o.typtype = 'e' |
| Function | pg_proc | pronamespace | o.prokind IN ('f', 'w') |
| View | pg_class | relnamespace | o.relkind IN ('v', 'm') |

Verbatim inventory output:

```text
enum: total=41, undocumented=41
function: total=34, undocumented=21
view: total=16, undocumented=5
Excluded PostGIS table: ('spatial_ref_sys', None, 5, 5)
```

## Import and Fleet Boundary

All commands run from this worktree with the shared interpreter. Import proof:

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/819-schema-docs/nexus/__init__.py
```

Read-only migration status command:

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/migrate.py --status
```

Relevant lines, verbatim (the runner omits per-migration status for locked saves):

```text
NEXUS_template:
  [ ] 127_schema_documentation
save_01: [LOCKED]
save_02:
  [ ] 127_schema_documentation
save_03:
  [ ] 127_schema_documentation
save_04:
  [ ] 127_schema_documentation
save_05:
  [ ] 127_schema_documentation
```

The read-only SQL `SELECT count(*) FROM schema_migrations WHERE version='127'`
returns zero on **all six fleet databases, including locked `save_01`**, as shown
in the proof below. The clone alone has the 127 stamp, and is then dropped.

## Red/Green Migration Proof

This invokes the exact ratchet test function against one real schema-only clone
before and after 127. The red assertion is expected and caught explicitly; it is
not counted as a passing unmigrated gate. The same clone then passes. Save the
following as `temp/819/proof.py` and run:

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python temp/819/proof.py
```

```python
from contextlib import closing
from tests.pg_fixtures import connect
from tests.test_schema_documentation_pg import (
    _schema_only_clone, _inventory, _baseline, test_schema_documentation_coverage,
)
from scripts import migrate
from pathlib import Path
MIGRATION = Path("migrations/127_schema_documentation.sql")

with _schema_only_clone('NEXUS_template') as dbname:
    with closing(connect(dbname)) as conn:
        before = _inventory(conn)
        missing = {key for key, value in before.items() if not (value or '').strip()}
        print('Before 127: undocumented tables=%d columns=%d; baseline=%d' % (
            sum(key.startswith('table:') for key in missing),
            sum(key.startswith('column:') for key in missing), len(_baseline())))
    try:
        test_schema_documentation_coverage(dbname)
    except AssertionError as exc:
        print('RED: test_schema_documentation_coverage raised AssertionError on clone without 127')
        print('Untracked undocumented objects:', len(missing - _baseline().keys()))
        print('First untracked object:', sorted(missing - _baseline().keys())[0])
    else:
        raise AssertionError('Unmigrated clone unexpectedly passed')
    with closing(connect(dbname)) as conn:
        assert migrate.apply_migration(conn, '127', 'schema_documentation', MIGRATION)
        after = _inventory(conn)
        assert all(after[key] == value for key, value in before.items() if value)
        with conn.cursor() as cur:
            cur.execute('SELECT version, name FROM schema_migrations')
            print('Clone stamps:', cur.fetchall())
    test_schema_documentation_coverage(dbname)
    print('GREEN: test_schema_documentation_coverage passed on the same clone with 127')
    print('Added comments:', sum(bool(after[key]) and not bool(value) for key, value in before.items()))
    print('Existing comments preserved:', sum(bool(value) for value in before.values()))
print('Proof clone dropped')
for dbname in ['NEXUS_template'] + [f'save_{n:02d}' for n in range(1, 6)]:
    with closing(connect(dbname)) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM schema_migrations WHERE version='127'")
            print(dbname, '127 stamps:', cur.fetchone()[0])
```

Verbatim output:

```text
INFO   Applied: 127_schema_documentation
Before 127: undocumented tables=15 columns=294; baseline=14
RED: test_schema_documentation_coverage raised AssertionError on clone without 127
Untracked undocumented objects: 295
First untracked object: column:assets.character_images.character_id
Clone stamps: [('127', 'schema_documentation')]
GREEN: test_schema_documentation_coverage passed on the same clone with 127
Added comments: 295
Existing comments preserved: 629
Proof clone dropped
NEXUS_template 127 stamps: 0
save_01 127 stamps: 0
save_02 127 stamps: 0
save_03 127 stamps: 0
save_04 127 stamps: 0
save_05 127 stamps: 0
```

## Required Gates

Offline suite (the PostgreSQL opt-in is unset; its skips are not used as the
PostgreSQL gate):

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```

Tail, verbatim:

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2804 passed, 945 skipped, 9 warnings in 126.75s (0:02:06)
```

The final PostgreSQL command uses the repository's actual fixtures, with no
fixture renaming, mocked database rows, or skipped PostgreSQL tests:

```bash
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_schema_documentation_pg.py tests/test_idf_dictionary_pg.py tests/test_orrery_tag_validation_pg.py
```

Tail, verbatim:

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 32.54s
```

The new tests exercise new tables, new columns, blank/removed comments, documented
and removed baseline debt, actual PostGIS ownership, schema-only refresh, the
production setup path with migration stamps suppressing comment replay, and
runner-created tracking tables. All catalog mutations occur on disposable clones;
regression probes roll back their transactions.

Production evidence: `scripts/new_story_setup.py:215` dumps both schemas with
`pg_dump -s`; `scripts/new_story_setup.py:251` restores with `ON_ERROR_STOP=1`;
`scripts/new_story_setup.py:261` copies seed rows and migration stamps before
running pending migrations. `scripts/migrate.py:150` now comments the tracking
table and columns when it creates them. The clone round-trip assertions are in
`tests/test_schema_documentation_pg.py:223` and `:239`.

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

```text
......................................                                   [100%]
38 passed in 7.73s
```

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check tests/test_schema_documentation_pg.py scripts/migrate.py
```

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

No UI files changed, so there is no Node build.

The amendment commit ran the repository hooks without bypassing them:

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.............(no files to check)Skipped
```

The config hook had no applicable Python/config changes; the catalog hook made
no file changes.

## Validation Iterations

The initial `PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1
/Users/pythagor/nexus/.venv/bin/python -m pytest -q
tests/test_schema_documentation_pg.py` run ended with:

```text
3 failed, 7 passed, 5 warnings in 3.21s
```

All three failures identified the same baseline spelling issue: PostgreSQL's
`quote_ident` produces `column:public.ai_notebook."timestamp"`. The baseline now
uses that catalog spelling. The next requested PostgreSQL gate ended with
`60 passed, 5 warnings in 31.70s`. The final run above follows the test changes
that make synthetic debt retirement independent of the remaining legacy debt and
avoid replaying 127 when it is already stamped on a future template.

The first Black check after those test edits reported one file needing
formatting; Black was run and the final check above is clean. No failing gate is
waived, and no #885 slot-5 exemption is needed for these focused PostgreSQL tests.

## Deferred Work and Coordinator Questions

Enums, functions, and views are inventoried only. The 14 baseline columns need
reader/writer evidence or an explicit retirement decision before documenting
them. The coordinator applies migration 127 to the template/fleet at land time;
this PR must not do so. No blocking design question remains.

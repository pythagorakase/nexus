# Issue 1013: IDF Rebuild Verification

Server: PostgreSQL 17.11 (Postgres.app), `server_version_num` 170011, on
2026-09-29. Branch `claude/1013-idf-rebuild`. No `save_NN` database or
`NEXUS_template` was written; every rebuild below ran on a disposable
`qa640_1013_*` clone that its fixture dropped.

## Fleet Dry Run (Read-Only)

`PYTHONPATH=$PWD python scripts/rebuild_memory_idf.py --all --dry-run --json`
(exit 0). The coordinator had already rebuilt `NEXUS_template` and
`save_02`..`save_05` by hand. Like `scripts/migrate.py --all --dry-run`, the
dry run skips the locked golden master `save_01` without
`--write-locked-slot`; the second run below reads it.

```json
{
  "dry_run": true,
  "ok": true,
  "databases": [
    {
      "dbname": "NEXUS_template",
      "status": "dry_run",
      "locked": false,
      "server_key": "pg_catalog.english/v1/170011",
      "corpora": [
        {
          "corpus_kind": "narrative",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 0,
          "source_documents": 0,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        },
        {
          "corpus_kind": "retrograde_summary",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 0,
          "source_documents": 0,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        }
      ],
      "error": null
    },
    {
      "dbname": "save_01",
      "status": "skipped_locked",
      "locked": true,
      "server_key": null,
      "corpora": [],
      "error": null
    },
    {
      "dbname": "save_02",
      "status": "dry_run",
      "locked": false,
      "server_key": "pg_catalog.english/v1/170011",
      "corpora": [
        {
          "corpus_kind": "narrative",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 1425,
          "source_documents": 1425,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        },
        {
          "corpus_kind": "retrograde_summary",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 0,
          "source_documents": 0,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        }
      ],
      "error": null
    },
    {
      "dbname": "save_03",
      "status": "dry_run",
      "locked": false,
      "server_key": "pg_catalog.english/v1/170011",
      "corpora": [
        {
          "corpus_kind": "narrative",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 39,
          "source_documents": 39,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        },
        {
          "corpus_kind": "retrograde_summary",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 18,
          "source_documents": 18,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        }
      ],
      "error": null
    },
    {
      "dbname": "save_04",
      "status": "dry_run",
      "locked": false,
      "server_key": "pg_catalog.english/v1/170011",
      "corpora": [
        {
          "corpus_kind": "narrative",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 45,
          "source_documents": 45,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        },
        {
          "corpus_kind": "retrograde_summary",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 27,
          "source_documents": 27,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        }
      ],
      "error": null
    },
    {
      "dbname": "save_05",
      "status": "dry_run",
      "locked": false,
      "server_key": "pg_catalog.english/v1/170011",
      "corpora": [
        {
          "corpus_kind": "narrative",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 0,
          "source_documents": 0,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        },
        {
          "corpus_kind": "retrograde_summary",
          "key_before": "pg_catalog.english/v1/170011",
          "documents_before": 0,
          "source_documents": 0,
          "stale": false,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        }
      ],
      "error": null
    }
  ]
}
```

The same run without `--json` (exit 0; stderr: `WARNING Database save_01 is LOCKED (read-only), skipping; rerun with --write-locked-slot to rebuild it`):

```
NEXUS_template: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 0 (source 0)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
save_01: skipped_locked [LOCKED]
save_02: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 1425 (source 1425)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
save_03: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 39 (source 39)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 18 (source 18)
save_04: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 45 (source 45)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 27 (source 27)
save_05: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 0 (source 0)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
```

`PYTHONPATH=$PWD python scripts/rebuild_memory_idf.py --slot 1
--write-locked-slot --dry-run --json` (exit 0), read-only: `save_01` still
carries the 17.10-era key.

```json
{
  "dry_run": true,
  "ok": true,
  "databases": [
    {
      "dbname": "save_01",
      "status": "dry_run",
      "locked": true,
      "server_key": "pg_catalog.english/v1/170011",
      "corpora": [
        {
          "corpus_kind": "narrative",
          "key_before": "pg_catalog.english/v1/170010",
          "documents_before": 1425,
          "source_documents": 1425,
          "stale": true,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        },
        {
          "corpus_kind": "retrograde_summary",
          "key_before": "pg_catalog.english/v1/170010",
          "documents_before": 0,
          "source_documents": 0,
          "stale": true,
          "key_after": null,
          "documents_after": null,
          "lexeme_rows_differing": null
        }
      ],
      "error": null
    }
  ]
}
```

Without `--json` (exit 0):

```
save_01: dry_run [LOCKED] (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170010 (stale), documents 1425 (source 1425)
  retrograde_summary: key pg_catalog.english/v1/170010 (stale), documents 0 (source 0)
```

## Migration 133 Is Pending on the Fleet and Untouched

`PYTHONPATH=$PWD python scripts/migrate.py --status` (exit 0), filtered to the
database headers and migration 133:

```
NEXUS_template:
  [ ] 133_idf_rebuild_command
save_01: [LOCKED]
  (locked - use --write-locked-slot to apply migrations)
save_02:
  [ ] 133_idf_rebuild_command
save_03:
  [ ] 133_idf_rebuild_command
save_04:
  [ ] 133_idf_rebuild_command
save_05:
  [ ] 133_idf_rebuild_command
```

## Rehearsal on a Clone of the Golden Master's Data

`tests.pg_fixtures.disposable_slot_database("qa640_1013_golden",
source_db="save_01", include_data=True)` restores `save_01`'s data read-only
into a clone and migrates it (through 133). On the clone: a probe insert is
refused with the new text, `rebuild_memory_idf.main(["--dbname", clone])`
rebuilds, and the probe insert then succeeds (rolled back). The clone was
dropped.

```
clone qa640_1013_golden_d5dbb9aceba2 migrated to 133
before: [('narrative', 'pg_catalog.english/v1/170010', 1425), ('retrograde_summary', 'pg_catalog.english/v1/170010', 0)]
probe insert refused: IDF analyzer mismatch for corpus narrative: expected pg_catalog.english/v1/170011, found pg_catalog.english/v1/170010; run python scripts/rebuild_memory_idf.py --slot N (or --template / --all)
qa640_1013_golden_d5dbb9aceba2: rebuilt (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170010 -> pg_catalog.english/v1/170011, documents 1425 -> 1425, lexeme rows differing 0
  retrograde_summary: key pg_catalog.english/v1/170010 -> pg_catalog.english/v1/170011, documents 0 -> 0, lexeme rows differing 0
exit 0
probe insert after rebuild succeeded, id 1428
```

Zero differing lexeme rows across 1,425 documents agrees with the
coordinator's `save_03` probe: 17.10 and 17.11 lex identically.

## `nexus doctor` (owner-host)

Run from the worktree with `NEXUS_KEYRING_DISABLE=1` so no secret store was
read; the `ui.bundle` and `secrets.seat_providers` failures are that
environment, not this change. Database lines:

```
pass  template.present               NEXUS_template exists
fail  template.migrations_current    NEXUS_template: 1 pending (133)  -> python scripts/migrate.py --template
fail  slots.migrations_current       save_01: 1 pending (133); save_02: 1 pending (133); save_03: 1 pending (133); save_04: 1 pending (133); save_05: 1 pending (133)  -> python scripts/migrate.py --slot 1 --write-locked-slot; python scripts/migrate.py --slot 2; python scripts/migrate.py --slot 3; python scripts/migrate.py --slot 4; python scripts/migrate.py --slot 5
pass  template.idf_analyzer_current  NEXUS_template at pg_catalog.english/v1/170011
fail  slots.idf_analyzer_current     save_01: narrative pg_catalog.english/v1/170010, retrograde_summary pg_catalog.english/v1/170010 (server pg_catalog.english/v1/170011); save_02 at pg_catalog.english/v1/170011; save_03 at pg_catalog.english/v1/170011; save_04 at pg_catalog.english/v1/170011; save_05 at pg_catalog.english/v1/170011  -> python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot
```

## Land-Time Fleet Steps

```bash
python scripts/migrate.py --all
python scripts/migrate.py --slot 1 --write-locked-slot
python scripts/rebuild_memory_idf.py --all --dry-run
python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot --dry-run
python scripts/rebuild_memory_idf.py --all
python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot
nexus doctor
```

## Test Gates

All with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset.

`NEXUS_RUN_POSTGRES=1 python -m pytest -q tests/test_rebuild_memory_idf_pg.py tests/test_new_story_setup.py tests/test_idf_dictionary_pg.py tests/test_runtime/test_readiness.py tests/test_runtime/test_readiness_pg.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
62 passed, 5 warnings in 54.33s
```

At 956f9295 this includes
`test_rebuild_counts_each_corrupted_lexeme_once` (one bumped narrative
frequency and one stray summary lexeme each report exactly 1 differing
lexeme, and the rebuilt rows equal `ts_stat`), the offline
`test_differing_lexemes_counts_each_lexeme_once`, and the explicit
`--dbname` refusals (a locked name exits 2, a missing one raises), as
`migrate.py --dbname` behaves.

`test_readiness_pg.py::test_idf_analyzer_check_names_the_stale_corpus_until_rebuilt`
drives `slot_idf_outcome`, the registered `slots.idf_analyzer_current` body
after the probed slots are named (existence lookup, lock probe, targets,
outcome), on a clone standing in for slot 9: current passes; a stale key
fails with the database in `observed` and `--slot 9` in `remediation`;
locked and stale adds `--write-locked-slot`; after
`rebuild_memory_idf.rebuild_database` it passes; an absent database is
reported; a dropped `memory_idf_corpora` names `migrate.py --slot 9`.

`test_readiness.py::test_slot_idf_targets_name_the_locked_override_and_absent_slots`
proves a locked slot's remediation is
`python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot` and an
absent slot is reported. In the contract-server test, `save_01` was locked
and stale during this run, so the assertion that the registered
`slots.idf_analyzer_current` check fails naming it with
`--slot 1 --write-locked-slot` ran against the live fleet.

`NEXUS_RUN_POSTGRES=1 python -m pytest -q -rfE tests/test_orrery/`, rerun on a
working tree equal to 956f9295:

```
57 failed, 1545 passed, 39 skipped, 7 warnings, 24 errors in 256.31s (0:04:16)
```

The full log of that run is committed as
[`pg_orrery_branch_log_956f9295.txt`](pg_orrery_branch_log_956f9295.txt)
(`.txt` because `*.log` is gitignored), so the claim can be re-run:
`grep -c 'analyzer mismatch' pg_orrery_branch_log_956f9295.txt` prints `0`.
Its failing-id set is identical to the earlier run's short summary in
[`pg_orrery_failures_branch.txt`](pg_orrery_failures_branch.txt) (pytest
printed the `-rfE` lines without message suffixes at the redirected width;
each failure's message is in the full log). The id comparison against the
baseline is committed as
[`pg_orrery_failures_diff_vs_main.txt`](pg_orrery_failures_diff_vs_main.txt).

Baseline `temp/gates/pg-orrery-main-e124bd54.log` (main at e124bd54, before
the hand rebuild): 173 failed, 1393 passed, 28 errors, 140 `analyzer mismatch`
lines, 201 failing ids, 130 of which carry `analyzer mismatch` in their
failure section. This run: 81 failing ids, 0 `analyzer mismatch` lines.
`comm -13` over the sorted id lists is empty: every branch id also fails in
the baseline (79 with the same outcome kind; the 2 `knowledge_surfacing` ids
moved from ERROR to FAILED). Ten of the 130 IDF-class ids still fail, each on
a different cause (the diff file gives each first error line): 8 in
`test_reveal_live.py` (slot 5 has no places, #885) and the 2
`knowledge_surfacing` ids (`RenderLimits`, below). The remainder by first
error:

- #885 slot-5 fixture classes: `need-clock anchor unavailable` (23 ids:
  communication_graph 8, claim_consumption 8 via setup, claim_accounts 5,
  migrate 1, orbit_distance 1), `cannot unpack non-iterable NoneType` and its
  siblings (`'NoneType' object is not subscriptable`, `NotNullViolation ... id
  ... narrative_chunks`, `replay project tests need one located uncommitted
  actor`, `save_05 must carry ...`) in test_replay (24), test_reconstruction
  (4), test_status_bestow_delta_live (3), test_reveal_live (9),
  test_faction_project_contexts_live (8), test_evidence (1),
  test_polymorphic_patron_live (1), test_tag_library (1),
  test_adjudication_history (1).
- `tests/test_orrery/test_retrograde_constraints_pg.py` (4 setup errors):
  `DuplicateColumn: column "provenance" of relation "character_aliases"
  already exists` when the fixture replays migration 123; also failing in the
  baseline, not IDF.
- Newly visible, not new: `test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True|False]`
  errored at setup on the IDF mismatch in the baseline; with IDF healthy it
  now reaches `TurnCycleManager._select_scene_payload` and fails with
  `ValidationError: 4 validation errors for RenderLimits` (the test harness
  settings carry no `lore.render_limits`).

Offline `python -m pytest -q -rfE`:

```
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
1 failed, 4079 passed, 1060 skipped in 290.20s (0:04:50)
```

The one failure is `assert 711 < 700` on the Gaia prompt word count
(`prompts/`, from #1011 at e124bd54); this change touches no prompt.

## Codex P2: Reject an Incomplete Corpus Set

The bot's inline P2 on `nexus/runtime/readiness.py`: a `memory_idf_corpora`
missing a corpus row passed readiness (only stale keys were failed), while
the next write to that corpus fails in `sync_memory_idf_document` at
`SELECT ... INTO STRICT` and the rebuild refused the incomplete set.

- Readiness (`AnalyzerState`, `idf_analyzer_outcome`): only exactly the
  `narrative` and `retrograde_summary` rows, each at the live key, pass. A
  missing or unexpected row fails, naming the database, the corpus kinds, and
  the rebuild command (`--slot N`, plus `--write-locked-slot` when locked, or
  `--template`). Zero rows fail (`missing corpora narrative and
  retrograde_summary`); the "no IDF corpus rows" pass is gone. A missing table
  on a database stamped with migration 114 fails the same way, naming the
  rebuild; while 114 is pending it names `python scripts/migrate.py`.
- Rebuild (`scripts/rebuild_memory_idf.py`): a missing row is inserted at the
  live key in the same transaction, before the recompute (migration 114's
  seed shape); the per-corpus report carries `seeded: true`. A seeded corpus
  starts at 0 and the guard requires it to end at the documents the trigger
  admits, counted under the table lock; every other corpus keeps its count.
  The `empty` status is gone: zero rows seed both. Unexpected rows and a
  missing table still fail loudly (the latter naming the migration runner).
- Tests: `test_rebuild_seeds_a_missing_corpus_row` (a summary write fails
  with `NoDataFound`; `--dry-run` reports the row as missing and changes
  nothing; `main(["--dbname", clone, "--json"])` seeds it, `seeded: true`,
  0 -> 1 documents, the rows equal `ts_stat`; a summary insert then succeeds;
  zero rows seed both; a dropped table fails naming `python scripts/migrate.py`),
  seeded-count assertions in the guard test, and
  `test_idf_analyzer_check_fails_on_missing_corpus_rows_until_rebuilt` (the
  registered slot check body on a clone standing in for slot 9: a deleted
  `narrative` row fails with `missing corpus narrative` and
  `python scripts/rebuild_memory_idf.py --slot 9`, a chunk insert fails, the
  tool seeds the row at the live key, the check passes, an insert succeeds;
  zero rows fail). The dropped-table tail of the stale-key test now asserts
  the rebuild for a 114-stamped clone and `migrate.py --slot 9` once the 114
  stamp is removed; this supersedes the dropped-table sentence under Test
  Gates above.

Run against the pre-fix code at b1d1a954 (fixed files swapped in and
restored byte-identical), the new tests fail on the defect; after deleting
the `narrative` row the check returned
`Outcome(passed=True, observed='qa640_1013_readiness_a54770687a98 at pg_catalog.english/v1/170011', remediation=None)`:

```
FAILED tests/test_rebuild_memory_idf_pg.py::test_rebuild_seeds_a_missing_corpus_row
FAILED tests/test_runtime/test_readiness_pg.py::test_idf_analyzer_check_fails_on_missing_corpus_rows_until_rebuilt
FAILED tests/test_runtime/test_readiness_pg.py::test_idf_analyzer_check_names_the_stale_corpus_until_rebuilt
3 failed, 5 warnings in 4.52s
```

With the fix, `NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD python -m pytest -q tests/test_rebuild_memory_idf_pg.py tests/test_runtime/test_readiness.py tests/test_runtime/test_readiness_pg.py tests/test_new_story_setup.py`
(`NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
45 passed, 5 warnings in 31.27s
```

`PYTHONPATH=$PWD python -m pytest -q tests/test_reachability.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.24s
```

Black (`4 files would be left unchanged`), flake8 (exit 0), and mypy
(`Success: no issues found in 4 source files`) on `nexus/runtime/readiness.py`,
`scripts/rebuild_memory_idf.py`, `tests/test_rebuild_memory_idf_pg.py`, and
`tests/test_runtime/test_readiness_pg.py`.

Every fleet database holds both rows, so no verdict changes.
`PYTHONPATH=$PWD python scripts/rebuild_memory_idf.py --all --dry-run` (exit 0):

```
NEXUS_template: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 0 (source 0)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
save_01: skipped_locked [LOCKED]
save_02: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 1425 (source 1425)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
save_03: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 39 (source 39)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 18 (source 18)
save_04: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 45 (source 45)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 27 (source 27)
save_05: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 0 (source 0)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
```

`nexus doctor` IDF lines (`NEXUS_KEYRING_DISABLE=1`), the same as before the
fix:

```
pass  template.idf_analyzer_current  NEXUS_template at pg_catalog.english/v1/170011
fail  slots.idf_analyzer_current     save_01: narrative pg_catalog.english/v1/170010, retrograde_summary pg_catalog.english/v1/170010 (server pg_catalog.english/v1/170011); save_02 at pg_catalog.english/v1/170011; save_03 at pg_catalog.english/v1/170011; save_04 at pg_catalog.english/v1/170011; save_05 at pg_catalog.english/v1/170011  -> python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot
```

# Issue 1013: IDF Rebuild Verification

Server: PostgreSQL 17.11 (Postgres.app), `server_version_num` 170011, on
2026-09-29. Branch `claude/1013-idf-rebuild`. No `save_NN` database or
`NEXUS_template` was written; every rebuild below ran on a disposable
`qa640_1013_*` clone that its fixture dropped.

## Fleet Dry Run (Read-Only)

`PYTHONPATH=$PWD python scripts/rebuild_memory_idf.py --all --dry-run --json`
(exit 0). The coordinator had already rebuilt `NEXUS_template` and
`save_02`..`save_05` by hand; only the locked golden master `save_01` still
carries the 17.10-era key. `--dry-run` reads locked databases through a
read-only session, so `save_01` is reported rather than skipped.

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

The same run without `--json`:

```
NEXUS_template: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 0 (source 0)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
save_01: dry_run [LOCKED] (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170010 (stale), documents 1425 (source 1425)
  retrograde_summary: key pg_catalog.english/v1/170010 (stale), documents 0 (source 0)
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
python scripts/rebuild_memory_idf.py --all
python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot
nexus doctor
```

## Test Gates

All with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset.

`NEXUS_RUN_POSTGRES=1 python -m pytest -q tests/test_rebuild_memory_idf_pg.py tests/test_new_story_setup.py tests/test_idf_dictionary_pg.py tests/test_runtime/test_readiness.py tests/test_runtime/test_readiness_pg.py`:

```
...........................................................              [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
59 passed in 55.20s
```

`NEXUS_RUN_POSTGRES=1 python -m pytest -q -rfE tests/test_orrery/`:

```
57 failed, 1545 passed, 39 skipped, 24 errors in 268.80s (0:04:28)
```

Baseline `temp/gates/pg-orrery-main-e124bd54.log` (main at e124bd54, before
the hand rebuild): 173 failed, 1393 passed, 28 errors, 140 `analyzer mismatch`
lines. This run: 81 failing ids, 0 `analyzer mismatch` lines; 79 of the 81 ids
also fail in the baseline. The remainder by first error:

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

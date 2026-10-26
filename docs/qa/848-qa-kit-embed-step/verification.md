# Verification: QA Kit Seed Alignment Embeds Retrograde History (848-R1b)

Branch `claude/848-qa-kit-embed-step`, cut from `origin/main` at c7ae2988.
Docs only, plus one offline test: no file under `nexus/`, no `.py` under
`scripts/`, no `.toml` change, no migration, no gateway, no paid call. Nothing
was run against any `save_NN` except the read-only SQL below.

## Cited Lines at c7ae2988

- `scripts/qa_shift/qa_shift.toml:3-6`: `slot = 4`, `gateway_port = 8012` (the
  disposable lane). `scripts/qa_shift/README.md:158-160` names `save_04`
  "`codex_qa` (`save_04`, historically contaminated adversarial QA)".
- `scripts/qa_shift/mission_prompt.md:84-105` (step 7): drop, restore,
  `scripts/migrate.py --slot N` (`:89`), the `global_variables` and queued-job
  alignment (`:90-96`), then `nexus logs gateway --mark` and the gateway start
  (`:100-105`). No step checked or repaired embeddings. `:107-108`: a failed
  preflight step stops the shift. `README.md:52-70` (Seeds) said nothing about
  embeddings.
- `nexus/cli_contract.py:143` (`"jobs": "database"`) and `:149`
  (`"retrograde-embed-history": "database"`).
- `nexus/cli.py:3612-3690` `run_retrograde_embed_history`: without
  `--execute` it opens `SET TRANSACTION READ ONLY` (`:3650`); only with it does
  it call `embed_retrograde_summaries` for the pending ids (`:3664-3666`).
- `nexus/agents/orrery/retrograde_persistence.py:2004-2014`: a stamped row
  missing an active-model vector is `stamped_missing_vectors` with
  `embedding_pending` true; `:2019-2027` a dry run reports a missing summary as
  `would_insert`; `:2038-2050` `--execute` inserts it (`inserted`).
- `nexus/cli.py:559-588` `_print_retrograde_embed_history`: prints
  `summary_rows: <n>`, one `- <event_ref>: <status> (...)` line per row,
  `embedding_pending_summary_ids: [...]`, and the embedded summaries.
- `nexus/cli.py:5210-5215`: `nexus jobs` prints
  `stamped_without_vectors: <table>=<count>, ...` only when a count is nonzero.
- `nexus.toml:950-955`: `[memnon.models."Octen-Embedding-4B"]`,
  `is_active = true`, `local_path = ".../models/Octen-Embedding-4B"` (the only
  active embedder; local, no provider call).
- `scripts/qa_shift/qa_shift.py:768-822` `_write_runtime_config` rewrites
  `MODEL_SELECTION_PATHS - {"local_models.model"}` (`:796-807`;
  `nexus/config/settings_models.py:32-46`) and sets `apex.provider` and the
  daily allowance (`:808-811`); no embedder key. `:825-849`
  `_write_environment` exports `NEXUS_RUNTIME_CONFIG`, `NEXUS_GATEWAY_PORT`,
  `NEXUS_API_URL`, `NEXUS_SLOT`.
- Command behavior on disposable clones:
  `tests/test_orrery/test_retrograde_embedding_pg.py:212`
  (`test_cli_repairs_stamped_summary_when_vector_table_is_missing`), `:381`,
  and `tests/test_jobs_cli_pg.py:366` (text line pinned at `:454-457`).

## Seed Manifest Facts (Quoted From the Order)

The newest seed is
`temp/qa_seeds/vesper_station_42chunks_40ex_4digests_2026-07-31.dump`
(gitignored; not read from the main checkout). Manifest:
`"database": "save_04"`, `"latest_migration": 100`,
`"promoted_at_utc": "2026-07-31T16:31:12Z"`. PR #671 (956f22d2, 2026-08-06),
which fixed #665's leaked loop variable, merged after that promotion.

## Read-Only SQL on `save_04` (2026-10-26)

All queries ran with `PGOPTIONS='-c default_transaction_read_only=on'`.

```
$ psql -d save_04 -Atc "SELECT version, applied_at FROM schema_migrations WHERE version::int BETWEEN 99 AND 114 ORDER BY version::int"
099|2026-07-29 07:55:21.076978-04
100|2026-07-31 00:34:57.339929-04
101|2026-08-21 00:35:39.507654-04
102|2026-08-21 00:35:39.513216-04
103|2026-08-21 00:35:39.516153-04
104|2026-08-21 00:35:39.516813-04
105|2026-08-21 00:35:39.522018-04
106|2026-08-21 00:35:39.528683-04
107|2026-08-21 00:35:39.532711-04
108|2026-08-21 00:35:39.534225-04
109|2026-08-21 00:35:39.535108-04
110|2026-08-21 00:35:39.536632-04
111|2026-08-21 00:35:39.540855-04
112|2026-08-21 00:35:39.541736-04
113|2026-08-21 00:35:39.54239-04
114|2026-09-06 00:35:38.700023-04
$ psql -d save_04 -Atc "SELECT max(version::int) FROM schema_migrations"
151
$ psql -d save_04 -Atc "SELECT count(*) FROM retrograde_summaries WHERE embedding_generated_at IS NOT NULL"
27
$ psql -d save_04 -Atc "SELECT string_agg(s.id::text, ', ' ORDER BY s.id), count(*) FROM retrograde_summaries s WHERE s.embedding_generated_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM retrograde_summary_embeddings_2560d e WHERE e.summary_id = s.id AND e.model = 'Octen-Embedding-4B')"
1, 2, 3, 5, 7, 8, 11, 13, 14, 15, 17, 19|12
$ psql -d save_04 -Atc "SELECT count(*) FROM character_experiences WHERE embedding_generated_at IS NOT NULL"
0
```

Migrations 101 through 113 were all applied in the same second on 2026-08-21:
the reseed from the 2026-07-31 seed (at 100), which removed the heal #665
recorded on 2026-08-06.

## Red Then Green

Red, at 937e4e4e (test committed, kit files unchanged):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_qa_shift.py::test_seed_alignment_repairs_retrograde_vectors_before_the_gateway_starts
        for phrase in ordered:
>           assert phrase in section, phrase
E           AssertionError: `nexus retrograde-embed-history --slot N`
tests/test_qa_shift.py:308: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_qa_shift.py::test_seed_alignment_repairs_retrograde_vectors_before_the_gateway_starts
1 failed, 5 warnings in 0.54s
```

Green, at 60cb49a0 (after Required Changes 1-4):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_qa_shift.py::test_seed_alignment_repairs_retrograde_vectors_before_the_gateway_starts
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1 passed, 5 warnings in 0.34s
```

The same command again at 35d1ab71 (after the re-stamp):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_qa_shift.py::test_seed_alignment_repairs_retrograde_vectors_before_the_gateway_starts
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1 passed, 5 warnings in 0.28s
```

## Re-Verification of Canonical Records

- `docs/decisions/0021-killed-c063.md` declares
  `scripts/qa_shift/mission_prompt.md` as a source. Its quoted cite
  `mission_prompt.md:32-43` still covers Hard Boundaries exactly (the insert is
  at step 7, after line 96; lines 1-96 are unchanged). The new step runs after
  `begin` (step 5) has written the usage baseline, and the repair is local
  (database transport, local Octen-Embedding-4B embedder, no provider call), so
  nothing lets provider-capable work run before the usage baseline. Its quoted
  text, including the stale `qa_shift.py:773-804`, is unchanged.
- `docs/decisions/0080-closing-the-embedding-orchestration-work.md`: absent on `origin/main` at the final merge (`git fetch` then `git merge origin/main`: "Already up to date." at c7ae2988); nothing to re-stamp.
- `verified_commit` in 0021 is moved to the merge base with `origin/main`
  after the final merge: `git merge-base origin/main HEAD` =
  `c7ae2988d07b443f627a04d3a4eed1816b1cd438`, which descends from the old
  stamp f073b371 (`git merge-base --is-ancestor` exits 0). The re-stamp is
  35d1ab71. The re-stamp check, run at 35d1ab71 (`git merge-base origin/main
  HEAD` still `c7ae2988d07b443f627a04d3a4eed1816b1cd438`):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 18.55s
```

  This evidence commit merges nothing from `origin/main` (which had not moved
  past c7ae2988 when it was written), so the merge base and the 0021 stamp are
  unchanged and the re-stamp still stands.

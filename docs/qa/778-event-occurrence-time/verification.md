# Event Occurrence Time Verification

Implementation commit: `4c04bb5ad848db33da891400c68d47a9129c071a`. Base and fetched/rebased `origin/main`:
`56b7854a1f6b62ccddb0417e0dda8446620ddcbd`. All line references below were rechecked at this implementation
commit; the subsequent evidence commit changes Markdown only.

## Scope and Isolation

This is frozen order 778-S2a, implementing only 778-R4. Read in order:
`_common_codex.md`, `778-S2a.md`, `issues/issue_778.md`, then
`gh issue view 778 --repo pythagorakase/nexus --comments`, including the migration
140 landing note and S4a report. No mechanism or owner question was reopened.
The user-supplied October 1 sequencing instructions supersede the order's older
sequencing paragraph. Migration 141 was absent from the fetched main tree and
this branch at proof time. `KNOWN_GAPS` remains exactly 013 and 119
(`tests/test_orrery/test_migrate.py:39`); 141 was neither taken nor exempted.

The shared interpreter's import proof printed:

```text
/Users/pythagor/nexus/.claude/worktrees/778-event-occurrence-time/nexus/__init__.py
```

The PostgreSQL fixture target agreement check passed against `postgres` before
any edit. Source sessions and pg_dump used source-only
`-c default_transaction_read_only=on`; every direct source connection checked
`SHOW transaction_read_only` and obtained `on`. The source option was supplied
per connection/process; no database options, locks, sessions, or source rows
were changed. `pg_restore` and all writes targeted uniquely named
`qa640_778s2a_*` clones. The source databases were `save_03`, then `save_04`;
no slot 2 calibration, owner service, gateway, fleet migration, or template write
was used. Tests used the existing TEST-only guard; corpus clones were pinned
through `write_story_settings(cur, StorySettings(skald_model='TEST', gaia_model=None))`
before migrating. The corpus driver makes no provider call. Paid calls: zero.

The ordered proof loaded `tests.dbname_audit` and ended `owner targets: none`.
It names the audit's existing unaudited C replication class explicitly; the
new tests use audited psycopg2 and asyncpg connections. The existing schema
fixture obtains template schema through its pg_dump subprocess, as documented
by the audit; new tests never open an owner database.

## Verified Premise and Current Behavior

At the base commit, the sync inserts omitted occurrence time at
`nexus/agents/orrery/events.py:6602` and `:6661`; the async inserts did so at
`:6746` and `:6806`. The two commit signatures (`:684`, `:973`) and emitter calls
(`:914`, `:1201`) lacked the occurrence input. These are baseline file references,
not the frozen order's older line numbers. Main versions were preserved through
`git show origin/main:<path>` and a complete `git archive origin/main` snapshot
under the order's scratch directory for static-check resolution.

At implementation commit `4c04bb5ad848db33da891400c68d47a9129c071a`:

| Contract | Evidence |
|---|---|
| Keyword-only aware override applies to every resolver deed and its signal | `events.py:684`, `:981`, forwarding at `:933`, `:1228`, validation at `:6575` |
| Resolve exactly once after the no-event return; missing/NULL exact clock raises | `events.py:6597-6608`, `:6756-6767`; default lookup calls only the exact-chunk readers |
| Four inserts bind the same resolved time, retaining async casts | `events.py:6634-6654`, `:6694-6714`, `:6791-6813`, `:6852-6874` |
| Exact-chunk readers differ from the substituting tick helpers | `events.py:5511-5530` versus `:5533-5592`; no emitter calls a tick helper |
| Migration rejects unresolved eligible rows before any update | `migrations/142_world_event_occurrence_time.sql:3-16` |
| Exact ordered UPDATE, no Retrograde or already timed row eligible | `migrations/142_world_event_occurrence_time.sql:18` |
| Exact authoritative comment, no new schema object/CHECK/default/tunable | `migrations/142_world_event_occurrence_time.sql:20-21`; full migration inspected |
| Nullable legacy event time and exact end-of-accepted-chunk clock | `migrations/083_claim_propagation_ledger.sql:11-15`, `migrations/118_world_clock_identity.sql:19-22` |
| Effective occurrence and scheduled acquisitions preserved | `nexus/agents/orrery/propagation.py:363-368`, `:804-817`, `:855-867` (unchanged) |
| Corpus must be captured before migration | `tests/pg_fixtures.py:193-243` versus empty target at `:269-290`; driver uses the latter |
| Production runner commits/stamps or rolls back failure, skipping stamps | `scripts/migrate.py:318-365`, `:368-392`, `:438-442` (unchanged) |
| Shipped detection rate and hash material retained | `nexus.toml:594-596`, `events.py:183-202` (unchanged) |
| Existing claim-ledger assertions preserved | `tests/test_orrery/test_events.py:888`, `:970` only add aware overrides |
| Travel implementation from PR #1068 preserved | `git diff 56b7854a1f6b62ccddb0417e0dda8446620ddcbd 4c04bb5ad848db33da891400c68d47a9129c071a -- nexus/agents/orrery/events.py`: no travel-section hunk |

The real-database proofs live in `tests/test_orrery/test_world_event_time_pg.py`:
accepted-turn factory acceptance at `:165`, resolver-based sync/async parity and
duplicate commits at `:206`, absent and NULL metadata with another valid chunk
at `:286`, naive override rejection at `:342`, complete-row migration comparisons
across distinct tick clocks and every existing non-Retrograde source at `:390`,
and committed unresolved-clock setups with a pending 142 stamp/restored 083
comment at `:438`. No new test mocks the resolver, draft, detection, connection,
or runner. Slot routing is the existing disposable routing fixture.

## Corpus Proof

Evidence driver (uncommitted): `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/corpus_backfill_proof.py`.
SHA-256: `23237a76a35724a64e5dbb36c1acf4651937431ced679df203fcae30c23a2ddd`.
All scratch artifacts, dumps, comparison snapshots, logs, and helper programs
are under this order's scratch directory.

Discovered prerequisites were copied through **140**, since 141 was not on main.
The prerequisite runner returned `(0, 0)` on both restored clones: the live
sources were already stamped through 140. These are post-140/pre-142 baselines;
no post-141 claim is made. Missing prerequisites were not manufactured.

The direct source check SQL was:

```sql
SHOW transaction_read_only;
SELECT current_database(), current_setting('port'), now(), max(version)
FROM schema_migrations;
SELECT source::text, count(*), count(*) FILTER (WHERE world_time IS NULL)
FROM world_events GROUP BY source ORDER BY source;
SELECT count(*)
FROM world_events we LEFT JOIN chunk_metadata cm ON cm.chunk_id=we.tick_chunk_id
WHERE we.world_time IS NULL AND we.source IS DISTINCT FROM 'retrograde'
AND cm.world_time IS NULL;
```

Both unresolved-source counts were 0. Dumps used
`pg_dump --format=custom --file <order-scratch>/<source>.dump --dbname <source>`
with `nexus.database.subprocess_env()` plus the read-only option. Restores used
`pg_restore --exit-on-error --no-owner --no-acl --dbname <clone> <archive>` with
the normal subprocess environment. Snapshots record complete JSON event rows,
tick clocks, effective COALESCE readings, complete participants/resolution
ledgers, exact comment, head replay result (including notes, approximate sections,
unreproducible fields and uncertain rows), and all checkpoint verdicts.

| Source | Raw NULL | Pre-142 NULL Through 140 | Eligible Changed | Remaining Eligible NULL | Retrograde NULL Unchanged | Events |
|---|---:|---:|---:|---:|---:|---:|
| save_03 | 96 | 96 | 75 | 0 | 21 | 96 |
| save_04 | 133 | 133 | 103 | 0 | 30 | 133 |

No count drift from the frozen order: total NULLs 96/133; eligible resolver NULLs 75/103; Retrograde NULLs 21/30.

### save_03

- Source identity/snapshot: `['save_03', '5432', '2026-10-01 09:25:07.381938+00:00', '140']`; read-only `on`.
- Clone: `qa640_778s2a_save_03_137cfbb695aa`.
- Raw and prerequisite-baseline counts by source: `[['resolver', 75, 75], ['retrograde', 21, 21]]` and `[['resolver', 75, 75], ['retrograde', 21, 21]]`; each tuple is `(source, total, NULL)`.
- After 142 counts by source: `[['resolver', 75, 0], ['retrograde', 21, 21]]`.
- Exact eligible IDs: `[30, 37, 38, 39, 41, 42, 44, 45, 46, 47, 48, 49, 50, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 69, 70, 72, 73, 74, 75, 76, 77, 78, 80, 81, 82, 83, 84, 85, 86, 88, 89, 91, 94, 98, 99, 100, 101, 102, 103, 105, 106, 107, 108, 109, 110, 111, 113, 114, 115, 116, 118, 119, 121, 122, 125, 127, 227, 228, 229, 231, 232, 233]`.
- Changed IDs equal exactly that eligible set; each complete row differs only in
  `world_time`, equal to its own tick chunk's canonical post-140 clock. All
  Retrograde rows and pre-existing non-NULL rows compare as complete rows.
  In these corpora the pre-existing non-NULL set is empty; the seeded migration
  test independently covers preservation of an earlier explicit instant.
- Event IDs/counts, participants and resolution ledgers are equal. Effective
  occurrence readings, clocks, replay state/uncertainty and checkpoint verdicts
  are equal. Replay head: `100`; checkpoint pairs: `1`;
  per-pair drift counts before and after: `[0]`.
- Before comment equals migration 083; after comment equals the exact ordered 142
  text. Reapply after deleting only clone 142 stamp: `[1, 0]`, identical
  rows/comment/full snapshot. Normal runner rerun: `[0, 0]`, identical snapshot.
- Cleanup verified: clone absent from pg_database after fixture teardown.
- Full machine snapshots: `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/save_03_before.json`,
  `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/save_03_after.json`; report in `corpus_results.json`.

### save_04

- Source identity/snapshot: `['save_04', '5432', '2026-10-01 09:25:08.928551+00:00', '140']`; read-only `on`.
- Clone: `qa640_778s2a_save_04_9e13c7d79a44`.
- Raw and prerequisite-baseline counts by source: `[['resolver', 103, 103], ['retrograde', 30, 30]]` and `[['resolver', 103, 103], ['retrograde', 30, 30]]`; each tuple is `(source, total, NULL)`.
- After 142 counts by source: `[['resolver', 103, 0], ['retrograde', 30, 30]]`.
- Exact eligible IDs: `[30, 37, 38, 39, 41, 42, 44, 45, 46, 47, 48, 49, 50, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 69, 70, 72, 73, 74, 75, 76, 77, 78, 80, 81, 82, 83, 84, 85, 86, 88, 89, 91, 94, 98, 99, 100, 101, 102, 103, 105, 106, 107, 108, 109, 110, 111, 113, 114, 115, 116, 118, 119, 121, 122, 125, 127, 129, 130, 131, 133, 135, 136, 137, 138, 139, 140, 142, 143, 144, 145, 146, 147, 148, 150, 151, 152, 153, 154, 155, 156, 163, 164, 165, 166, 167, 169, 170, 172, 173, 174]`.
- Changed IDs equal exactly that eligible set; each complete row differs only in
  `world_time`, equal to its own tick chunk's canonical post-140 clock. All
  Retrograde rows and pre-existing non-NULL rows compare as complete rows.
  In these corpora the pre-existing non-NULL set is empty; the seeded migration
  test independently covers preservation of an earlier explicit instant.
- Event IDs/counts, participants and resolution ledgers are equal. Effective
  occurrence readings, clocks, replay state/uncertainty and checkpoint verdicts
  are equal. Replay head: `49`; checkpoint pairs: `1`;
  per-pair drift counts before and after: `[0]`.
- Before comment equals migration 083; after comment equals the exact ordered 142
  text. Reapply after deleting only clone 142 stamp: `[1, 0]`, identical
  rows/comment/full snapshot. Normal runner rerun: `[0, 0]`, identical snapshot.
- Cleanup verified: clone absent from pg_database after fixture teardown.
- Full machine snapshots: `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/save_04_before.json`,
  `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/save_04_after.json`; report in `corpus_results.json`.

## Commands and Verbatim Tails

`PY=/Users/pythagor/nexus/.venv/bin/python` and
`SCRATCH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a`.
All final commands ran from the designated worktree with `PYTHONPATH=$PWD`.
Each gate was executed by the uncommitted `$SCRATCH/run_gate.py` wrapper as one
foreground subprocess with `timeout=580`, recording its exact argv and exit.
Harness-yielded processes were awaited to completion. Long suites were sequential.
`TMPDIR=$SCRATCH` kept their temporary files in this order's scratch space.

The original combined offline-other command was interrupted and is **not**
claimed as a completed gate. The completed subdirectory and root partitions
cover its entire scope. Root uses `-v` to expose progress while retaining `-q`.
Final code changes after those partitions were emitter docstrings and PG-test-only
assertions/type narrowing; no functional product change followed the offline gates.

### proof-final

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 TMPDIR=$SCRATCH /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_world_event_time_pg.py tests/test_orrery/test_signal_events.py tests/test_orrery/test_events.py tests/test_orrery/test_replay.py tests/test_world_clock_contract_pg.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_owner_target_guard.py
```

Exit `1`; verbatim tail:

```text
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
........................................................................ [ 23%]
.........................................................F.............. [ 47%]
........................................................................ [ 71%]
........................................................................ [ 95%]
.............                                                            [100%]
=================================== FAILURES ===================================
_________________ test_migration_sequence_has_only_known_gaps __________________

    def test_migration_sequence_has_only_known_gaps() -> None:
        """A new hole or a reused historical hole in the numbering fails."""
    
        versions = _on_disk_versions()
        head = max(int(version) for version in versions)
        missing = {f"{number:03d}" for number in range(1, head + 1)} - set(versions)
    
        assert min(versions) == "001"
>       assert missing == KNOWN_GAPS
E       AssertionError: assert {'013', '119', '141'} == frozenset({'013', '119'})
E         
E         Extra items in the left set:
E         '141'
E         Use -v to get more diff

tests/test_orrery/test_migrate.py:266: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: postgres, qa640_778s2a_time_* x14, qa640_clock_* x7, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_replay_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_signal_events_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 300 passed in 59.43s
```

### corpus

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 TMPDIR=$SCRATCH /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/corpus_backfill_proof.py
```

Exit `0`; verbatim tail:

```text
Prerequisite migrations copied through 140; 141 present: False
{"source": "save_03", "source_identity": ["save_03", "5432", "2026-10-01 09:25:07.381938+00:00", "140"], "source_read_only": "on", "clone": "qa640_778s2a_save_03_137cfbb695aa", "raw_counts": [["resolver", 75, 75], ["retrograde", 21, 21]], "prerequisite_head": 140, "prerequisite_result": [0, 0], "baseline_counts": [["resolver", 75, 75], ["retrograde", 21, 21]], "after_counts": [["resolver", 75, 0], ["retrograde", 21, 21]], "event_count": 96, "eligible_ids": [30, 37, 38, 39, 41, 42, 44, 45, 46, 47, 48, 49, 50, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 69, 70, 72, 73, 74, 75, 76, 77, 78, 80, 81, 82, 83, 84, 85, 86, 88, 89, 91, 94, 98, 99, 100, 101, 102, 103, 105, 106, 107, 108, 109, 110, 111, 113, 114, 115, 116, 118, 119, 121, 122, 125, 127, 227, 228, 229, 231, 232, 233], "changed": 75, "remaining_eligible_null": 0, "retrograde_null": 21, "reapply": [1, 0], "rerun": [0, 0], "replay_head": 100, "checkpoint_pairs": 1, "checkpoint_drifts": [0], "assertions": "all passed: complete rows, clocks, effective occurrence, participants, resolution ledgers, replay state and uncertainty, checkpoint verdicts, exact comment, reapply and normal rerun", "cleanup": "clone absent from pg_database after fixture teardown"}
{"source": "save_04", "source_identity": ["save_04", "5432", "2026-10-01 09:25:08.928551+00:00", "140"], "source_read_only": "on", "clone": "qa640_778s2a_save_04_9e13c7d79a44", "raw_counts": [["resolver", 103, 103], ["retrograde", 30, 30]], "prerequisite_head": 140, "prerequisite_result": [0, 0], "baseline_counts": [["resolver", 103, 103], ["retrograde", 30, 30]], "after_counts": [["resolver", 103, 0], ["retrograde", 30, 30]], "event_count": 133, "eligible_ids": [30, 37, 38, 39, 41, 42, 44, 45, 46, 47, 48, 49, 50, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 69, 70, 72, 73, 74, 75, 76, 77, 78, 80, 81, 82, 83, 84, 85, 86, 88, 89, 91, 94, 98, 99, 100, 101, 102, 103, 105, 106, 107, 108, 109, 110, 111, 113, 114, 115, 116, 118, 119, 121, 122, 125, 127, 129, 130, 131, 133, 135, 136, 137, 138, 139, 140, 142, 143, 144, 145, 146, 147, 148, 150, 151, 152, 153, 154, 155, 156, 163, 164, 165, 166, 167, 169, 170, 172, 173, 174], "changed": 103, "remaining_eligible_null": 0, "retrograde_null": 30, "reapply": [1, 0], "rerun": [0, 0], "replay_head": 49, "checkpoint_pairs": 1, "checkpoint_drifts": [0], "assertions": "all passed: complete rows, clocks, effective occurrence, participants, resolution ledgers, replay state and uncertainty, checkpoint verdicts, exact comment, reapply and normal rerun", "cleanup": "clone absent from pg_database after fixture teardown"}
| Source | Raw NULL | Pre-142 NULL | Eligible Changed | Remaining Eligible NULL | Retrograde NULL Unchanged | Events |
|---|---:|---:|---:|---:|---:|---:|
| save_03 | 96 | 96 | 75 | 0 | 21 | 96 |
| save_04 | 133 | 133 | 103 | 0 | 30 | 133 |
Assertions: all passed for both corpora; both clones dropped.
```

### migration-comments

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

Exit `0`; verbatim tail:

```text
OK: every object created after migration 129 has a comment.
```

### offline-other

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM PYTHONPATH=$PWD TMPDIR=$SCRATCH /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

Exit `2`; verbatim tail:

```text
........................................................................ [  2%]
.........................................................s.............. [  4%]
........................sssssss...ssss.................................. [  6%]
........................................................................ [  8%]
........................................................................ [ 10%]
..................................................................
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/selectors.py:415: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
414 passed, 14 skipped, 7 warnings in 147.62s (0:02:27)
```

### offline-subdirs

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM PYTHONPATH=$PWD TMPDIR=$SCRATCH /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/config tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
```

Exit `0`; verbatim tail:

```text
........................................................................ [ 14%]
........................................................................ [ 22%]
.........................s...........sssssss............................ [ 29%]
.................ss............ssssssss...............s................. [ 36%]
........................................................................ [ 44%]
...................sssssssss....................sssss...s......sssss.... [ 51%]
..sss..................s................................................ [ 58%]
..........s..ss......................................................... [ 66%]
............ssss.........................sss............................ [ 73%]
........................................................................ [ 81%]
...................sssss................................................ [ 88%]
ssssssssssss............................................................ [ 95%]
.........................................                                [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
907 passed, 70 skipped, 7 warnings in 83.77s (0:01:23)
```

### offline-root

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM PYTHONPATH=$PWD TMPDIR=$SCRATCH /Users/pythagor/nexus/.venv/bin/python -m pytest -q -v tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util
```

Exit `0`; verbatim tail:

```text
tests/test_travel_reachability_pg.py sss                                 [ 95%]
tests/test_turn_observation.py .................                         [ 96%]
tests/test_unowned_index_adoption_pg.py ssss.                            [ 96%]
tests/test_usage_recorder.py ....................                        [ 97%]
tests/test_wizard_agent.py .........................                     [ 98%]
tests/test_wizard_live.py ssssssssssssss                                 [ 99%]
tests/test_wizard_opening_presence_pg.py ssssss                          [ 99%]
tests/test_world_clock_contract_pg.py sssssss                            [100%]

=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
========== 1933 passed, 410 skipped, 8 warnings in 370.60s (0:06:10) ===========
```

### offline-api-orrery

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM PYTHONPATH=$PWD TMPDIR=$SCRATCH /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
```

Exit `1`; verbatim tail:

```text
        missing = {f"{number:03d}" for number in range(1, head + 1)} - set(versions)
    
        assert min(versions) == "001"
>       assert missing == KNOWN_GAPS
E       AssertionError: assert {'013', '119', '141'} == frozenset({'013', '119'})
E         
E         Extra items in the left set:
E         '141'
E         Use -v to get more diff

tests/test_orrery/test_migrate.py:266: AssertionError
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1830 passed, 766 skipped, 7 warnings in 37.15s
```

### reachability

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

Exit `0`; verbatim tail:

```text
......................................................                   [100%]
=============================== warnings summary ===============================
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.32s
```

### black

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/orrery/events.py tests/test_orrery/test_world_event_time_pg.py tests/test_orrery/test_events.py
```

Exit `0`; verbatim tail:

```text
All done! ✨ 🍰 ✨
3 files would be left unchanged.
```

### flake8-final

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/agents/orrery/events.py tests/test_orrery/test_world_event_time_pg.py tests/test_orrery/test_events.py
```

Exit `0`; verbatim tail:

```text

```

### flake8-main-correct

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/baseline/nexus/agents/orrery/events.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/baseline/tests/test_orrery/test_events.py
```

Exit `0`; verbatim tail:

```text

```

### mypy-final

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases nexus/agents/orrery/events.py tests/test_orrery/test_world_event_time_pg.py tests/test_orrery/test_events.py
```

Exit `1`; verbatim tail:

```text
nexus/agents/orrery/events.py:1294: error: Argument "key" to "sorted" has incompatible type "Callable[[OrreryResolutionDraft], int | None]"; expected "Callable[[OrreryResolutionDraft], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
nexus/agents/orrery/events.py:1294: error: Incompatible return value type (got "int | None", expected "SupportsDunderLT[Any] | SupportsDunderGT[Any]")  [return-value]
tests/test_orrery/test_events.py:105: error: Need type annotation for "executed" (hint: "executed: list[<type>] = ...")  [var-annotated]
tests/test_orrery/test_events.py:106: error: Need type annotation for "clearance_log_rows" (hint: "clearance_log_rows: list[<type>] = ...")  [var-annotated]
tests/test_orrery/test_events.py:109: error: Need type annotation for "_fetchall" (hint: "_fetchall: list[<type>] = ...")  [var-annotated]
tests/test_orrery/test_events.py:670: error: Argument 1 to "response_to_incubator" has incompatible type "MinimalStoryResponse"; expected "StorytellerResponseExtended | StorytellerResponseStandard | StorytellerResponseMinimal | StorytellerResponseBootstrap"  [arg-type]
tests/test_orrery/test_events.py:698: error: Argument 1 to "response_to_incubator" has incompatible type "ResponseWithAdjudication"; expected "StorytellerResponseExtended | StorytellerResponseStandard | StorytellerResponseMinimal | StorytellerResponseBootstrap"  [arg-type]
tests/test_orrery/test_events.py:1158: error: Argument "replacement_state_delta" to "OrreryAdjudication" has incompatible type "dict[str, list[str]]"; expected "OrreryReplacementStateDelta | None"  [arg-type]
Found 8 errors in 2 files (checked 3 source files)
```

### mypy-main-shadow

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --shadow-file nexus/agents/orrery/events.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/baseline/nexus/agents/orrery/events.py --shadow-file tests/test_orrery/test_events.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S2a/baseline/tests/test_orrery/test_events.py nexus/agents/orrery/events.py tests/test_orrery/test_events.py
```

Exit `1`; verbatim tail:

```text
nexus/agents/orrery/events.py:1278: error: Argument "key" to "sorted" has incompatible type "Callable[[OrreryResolutionDraft], int | None]"; expected "Callable[[OrreryResolutionDraft], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
nexus/agents/orrery/events.py:1278: error: Incompatible return value type (got "int | None", expected "SupportsDunderLT[Any] | SupportsDunderGT[Any]")  [return-value]
tests/test_orrery/test_events.py:105: error: Need type annotation for "executed" (hint: "executed: list[<type>] = ...")  [var-annotated]
tests/test_orrery/test_events.py:106: error: Need type annotation for "clearance_log_rows" (hint: "clearance_log_rows: list[<type>] = ...")  [var-annotated]
tests/test_orrery/test_events.py:109: error: Need type annotation for "_fetchall" (hint: "_fetchall: list[<type>] = ...")  [var-annotated]
tests/test_orrery/test_events.py:670: error: Argument 1 to "response_to_incubator" has incompatible type "MinimalStoryResponse"; expected "StorytellerResponseExtended | StorytellerResponseStandard | StorytellerResponseMinimal | StorytellerResponseBootstrap"  [arg-type]
tests/test_orrery/test_events.py:698: error: Argument 1 to "response_to_incubator" has incompatible type "ResponseWithAdjudication"; expected "StorytellerResponseExtended | StorytellerResponseStandard | StorytellerResponseMinimal | StorytellerResponseBootstrap"  [arg-type]
tests/test_orrery/test_events.py:1156: error: Argument "replacement_state_delta" to "OrreryAdjudication" has incompatible type "dict[str, list[str]]"; expected "OrreryReplacementStateDelta | None"  [arg-type]
Found 8 errors in 2 files (checked 2 source files)
```

## Pre-existing Diagnostics

No new diagnostics. Final flake8: empty output/exit 0, identical to the main
versions under the same .flake8 configuration. Final mypy: eight errors on
untouched pre-existing lines, exactly equal by file/message to the main snapshot
modulo line shifts (normalization assertion passed). Two sorted-key errors are
at branch events.py:1294 versus main :1278; three existing collection annotations
at test_events.py:105/106/109; two existing response-to-incubator argument errors
at :670/:698; one existing replacement-state-delta argument error at branch
:1158 versus main :1156. All eight messages are reproduced above. No diagnostic
falls on a changed/added line. The new PG file has no mypy diagnostics.

The complete main snapshot also produced these same eight direct-file diagnostics.
Mypy's `--shadow-file` run reads the saved `git show` main versions with the same
module paths/import resolution as the branch command, giving the exact eight-error
comparison shown above; it changes no files. Earlier scratch-cwd attempts had
different config/import discovery and were discarded as comparisons. Those two
attempts ran from the scratch baseline directory rather than the required worktree;
this command-location mistake was corrected, with all subsequent commands run
from the designated worktree. Their raw logs (`mypy-main.log`, `flake8-main.log`)
and the complete-snapshot attempt (`mypy-main-correct.log`) remain for audit.

No fingerprint, allowlist, exemption, or pinned-baseline delta was required;
no baseline rule was narrowed or removed.

## Development Iterations and Commit Checks

The initial focused command was `$PY -m pytest -q -x -p tests.dbname_audit
 tests/test_orrery/test_world_event_time_pg.py` with the same PostgreSQL environment
as the final proof. `focused-first.log` ended `1 error in 1.20s` (seed_zone needed
explicit bounds); `focused-second.log` ended `1 failed in 2.27s` and
`focused-third.log` ended `1 failed in 2.19s` (the real stochastic resolver chose
the unsignalled fallback, corrected by selecting a genuinely signal-bearing
anchor); `focused-fourth.log` ended `1 failed, 11 passed in 22.42s` (the seed used
an invalid source enum, corrected to shipped sources). The final full proof
passes all fourteen new cases. These were test-construction corrections, not
false product premises or changes to production selection/rates.

Initial flake8 found four new long lines; initial mypy found nine new optional
settings accesses. They were fixed by string splitting and a typed assertion
that the shipped Orrery section exists. The final checks above supersede them.

Implementation commit hooks all passed: regenerate-orrery-catalog,
validate-config/model drift, migration comments, and exception dispositions.
No catalog modification resulted. `git diff --check` passed. Fetch/rebase after
the implementation commit reported the branch up to date at the base listed
above; migration 141 remained absent.

## Coordinator Follow-up

No owner/product question remains for this slice. Migration 141 is the sole
sequencing dependency. After 141 lands, rebase/rerun the migration sequence gate
and corpus prerequisite pass through 141 before landing 142. Keep KNOWN_GAPS
unchanged. The coordinator applies fleet migrations, handles locked slot 1,
confirms template/all five saves and the Retrograde preservation counts, restarts
the gateway after pulling the product-code change, and runs the whole-tree
PostgreSQL gate at the final landed commit. No client bundle changed.

Do not merge this PR from the implementer run.

Prepared by Codex, running GPT-6.

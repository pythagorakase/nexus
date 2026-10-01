# STOP-REPORT: 778-S6a

## Status and Boundary

Implementation commit: `e628c92c232f9723568c575423e6cceda53d288b`. Base: `5b977eabcba5f7aedf1a64a6ee20c021ab290911`,
which contains migration 140 from PR #1073. This document is a subsequent
stop-report commit; the final handoff hash is supplied in the session response.
The worktree is `/Users/pythagor/nexus/.claude/worktrees/778-clock-contract-verify`
on `claude/778-clock-contract-verify`.

STOP under `_common_codex.md`'s escape hatch: “if honest attempts cannot satisfy
a rule or a gate, STOP and write a stop-report.” The required mypy command exits
2 before checking sources because test modules resolve twice. `MYPYPATH=$PWD`
does not resolve it. A diagnostic using `--explicit-package-bases` exits 1 with
22 errors on pre-existing lines in the two test files. The required flake8 gate
also exits 1 for an existing 110-character SQL line. No repository-wide typing,
module-layout, or unrelated test cleanup is authorized by this frozen order.
No push or PR was made; no merge or gateway action was performed.

The initial PostgreSQL proof had one new assertion failure: API `Z` and SQL
`+00:00` formatting differed despite equal parsed instants. The assertion is
corrected and the entire Backstage file was rerun successfully. This is not a
claim that the final combined PostgreSQL gate passed.

The coordinator/user reports migration 140 applied fleet-wide as of
2026-10-01 02:50 CDT. That live fleet assertion was not independently checked
before stopping. The on-branch migration file is verified. No fleet report or
violation-counter claim is made here, including for contaminated slot 2.

## Files Changed

- `nexus/agents/orrery/replay.py`: independent primary-clock report, ordered Drift categories, replay clock fields and full-table verifier.
- `scripts/replay_state.py`: guarded repeatable-read connection, clock verification before early returns, reconstruction clock output/JSON and exit status.
- `scripts/qa_shift/clock_contract.py`: separate read-only six-field family and selected/fleet slot CLI.
- `scripts/qa_shift/README.md`: Clock Contract command, counters, read-only and exit contract, contaminated slot 2 warning.
- `scripts/qa_shift/qa_shift.toml`: comment naming the family command; no setting changes.
- `config/reachability.toml`: operator and path classification for the new script.
- `tests/test_orrery/test_replay.py`: real metadata/TEST acceptance clock proofs, corruption outside checkpoint windows, missing metadata.
- `tests/test_qa_shift.py`: independent defect plants, empty/NULL cases, read-only guard/protection, missing singleton.
- `tests/test_api/test_backstage_endpoints_pg.py`: ordered base seeding, required clone prefixes, independent latest/earlier SQL equality.
- `docs/qa/778-clock-contract-verify/verification.md`: this partial verification and stop-report.

## Commands and Verbatim Tails

All commands ran from this worktree. `PY=/Users/pythagor/nexus/.venv/bin/python`.
Test runs also received `PYTHONPATH=$PWD`, `NEXUS_RUN_LIVE_LLM` unset, and
`TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a`. The long PostgreSQL processes ran sequentially in the
foreground under `subprocess.run(..., timeout=590)` with output redirected to
this order's scratch directory; their final exit codes were collected before
any subsequent work. No paid provider was called. The test-provider-only guard
was enabled. Import proof:

```sh
PYTHONPATH=$PWD "$PY" -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/778-clock-contract-verify/nexus/__init__.py
```

### Combined PostgreSQL Proof (Before the Assertion Correction)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q -p tests.dbname_audit tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py tests/test_world_clock_contract_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

Exit 1. Verbatim tail:

```text
tests/test_qa_shift.py::test_clock_contract_reports_all_violation_counts[disagreements]
tests/test_qa_shift.py::test_clock_contract_empty_and_null_deltas
  <frozen runpy>:128: RuntimeWarning: 'scripts.qa_shift.clock_contract' found in sys.modules after import of package 'scripts.qa_shift', but prior to execution of 'scripts.qa_shift.clock_contract'; this may result in unpredictable behaviour

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 28 targets: postgres, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_778s6a_family_* x9, qa640_778s6a_played_*, qa640_778s6a_replay_* x6, qa640_clock_* x7, qa640_replay_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_backstage_endpoints_pg.py::test_payload_assembles_every_committed_stream
1 failed, 244 passed, 13 warnings in 45.86s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

Failure excerpt (verbatim, before captured fixture setup output):

```text
            expected_clock = cur.fetchone()[0]
        assert datetime.fromisoformat(payload["header"]["world_time"]) == expected_clock
>       assert payload["header"] == {
            "slot": 4,
            "chunk_id": backstage_case["latest"],
            "chunk_label": "S01E01_004",
            "turn_label": "t.4",
            "world_time": expected_clock.isoformat(),
            "skald_status": "idle",
        }
E       AssertionError: assert {'chunk_id': ...slot': 4, ...} == {'chunk_id': ...slot': 4, ...}
E         
E         Omitting 5 identical items, use -vv to show
E         Differing items:
E         {'world_time': '2189-10-17T20:02:00Z'} != {'world_time': '2189-10-17T20:02:00+00:00'}
E         Use -v to get more diff

tests/test_api/test_backstage_endpoints_pg.py:436: AssertionError
---------------------------- Captured stdout setup -----------------------------
```

### Backstage Correction Proof

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q -p tests.dbname_audit tests/test_api/test_backstage_endpoints_pg.py
```

Exit 0. Verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_778s6a_backstage_*, qa640_778s6a_empty_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
9 passed, 7 warnings in 4.24s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Formatting and Static Gates

```sh
"$PY" -m black nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Exit 0. Final formatting run, verbatim:

```text
All done! ✨ 🍰 ✨
6 files left unchanged.
```

```sh
"$PY" -m black --check nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Exit 0, verbatim:

```text
All done! ✨ 🍰 ✨
6 files would be left unchanged.
```

```sh
"$PY" -m flake8 nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Exit 1, verbatim:

```text
tests/test_orrery/test_replay.py:1056:89: E501 line too long (110 > 88 characters)
```

The identical SQL literal exists in base commit `5b977eab` at
`tests/test_orrery/test_replay.py:1039`, verified with
`git show 5b977eab:tests/test_orrery/test_replay.py | nl -ba`.
It is at line 1056 in the implementation commit because imports were added.

```sh
"$PY" -m mypy nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
MYPYPATH=$PWD "$PY" -m mypy nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Each exits 2; each prints the same verbatim tail:

```text
tests/test_orrery/__init__.py: error: Source file found twice under different module names: "test_orrery" and "tests.test_orrery"
Found 1 error in 1 file (errors prevented further checking)
```

Diagnostic only, not a substitute for the required command:

```sh
"$PY" -m mypy --explicit-package-bases nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Exit 1, verbatim output:

```text
tests/test_qa_shift.py:187: error: "Collection[Collection[str]]" has no attribute "get"  [attr-defined]
tests/test_qa_shift.py:1073: error: No overload variant of "int" matches argument type "object"  [call-overload]
tests/test_qa_shift.py:1073: note: Possible overload variants:
tests/test_qa_shift.py:1073: note:     def __new__(cls, str | Buffer | SupportsInt | SupportsIndex | SupportsTrunc = ..., /) -> int
tests/test_qa_shift.py:1073: note:     def __new__(cls, str | bytes | bytearray, /, base: SupportsIndex) -> int
tests/test_orrery/test_replay.py:311: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:312: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:320: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:321: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:323: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:583: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:591: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:685: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:686: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:687: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1483: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1485: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1487: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1488: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1489: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1497: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1505: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1506: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1507: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:2171: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
Found 22 errors in 2 files (checked 6 source files)
```

All 22 diagnostic locations precede the new clock test blocks (replay clock block
begins at line 2274; family clock block at line 1618). `git diff 5b977eab` confirms
those statements are unchanged. The later explicit `Any` cast in the new CLI
helper was precautionary and does not fix an existing diagnostic. No diagnostic
rerun is claimed after that cast.

`git diff --check` returned exit 0 with no output before the implementation
commit. Commit hooks ran normally: Orrery catalog Passed; config/model drift
Passed; migration-comment hook Skipped (no migration files). The catalog
remained unchanged.

## Verified Behavior Citations at the Implementation Commit

These statements are source evidence supported by the initial PostgreSQL
results where noted; they do not stand in for unfinished gates.

- Independent inclusive primary-only PostgreSQL calculation and missing-singleton failure: `nexus/agents/orrery/replay.py:279`; the five category lists and exact datetime comparisons follow in that function. Neither the view nor a refresh function is used as its oracle.
- Replay clock fields: `nexus/agents/orrery/replay.py:260`; target-bound attachment, computed instant and missing-row finding: `:3315`. Existing state replay still runs first.
- Full-table verifier: `nexus/agents/orrery/replay.py:391`; CLI invokes it and counts metadata before its insufficient-checkpoint branch: `scripts/replay_state.py:98`. All three zero/one/two checkpoint variants passed in the initial PostgreSQL run.
- Guarded repeatable-read/read-only setup: `scripts/replay_state.py:45`; reconstruction text and JSON fields: `:77`; reconstruction findings produce exit 1 at `:95`.
- Family six-field contract and read-only measurement: `scripts/qa_shift/clock_contract.py:14`; `measure_connection` at `:24`, slot transaction at `:35`, CLI at `:43`. All new family PostgreSQL tests passed in the initial run, including actual rejected INSERT.
- Primary/non-primary/NULL valid-case coverage: `tests/test_orrery/test_replay.py:2322`; independent corrupted-column/view coverage: `:2340`; outside-window CLI coverage: `:2376`; clean real TEST acceptance CLI coverage: `:2405`.
- Backstage base seeding precedes prologue metadata: `tests/test_api/test_backstage_endpoints_pg.py:126`; later global-variable write sets only user_character: `:207`. Latest and explicit earlier header instants are compared to independent SQL: `:745`; that test passed both in the original and correction runs. Full corrected Backstage file: 9 passed.
- Product Backstage selection remains `nexus/agents/orrery/backstage.py:203` (selects cm.world_time), with header construction at `:689`. No Backstage product or UI file changed.
- Existing world_clock code and exact shape test are unchanged; shape contract remains `tests/test_world_clock_contract_pg.py:128`. That file passed in the initial PostgreSQL proof.
- Test connection audit: the exact proof tails above report `owner targets: none`. The audit itself notes the unaudited C ReplicationConnection class. Template cloning uses the repository fixture path; its pg_dump subprocesses are outside that audit and use pg_dump's own read-only transaction. No save or template write was made.

## Deferred Proof and Coordinator Questions

The following required commands were **not run** after the stop condition:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q tests/test_api tests/test_orrery
"$PY" -m pytest -q tests/test_reachability.py
PGOPTIONS="${PGOPTIONS:+$PGOPTIONS }-c default_transaction_read_only=on" PYTHONPATH="$PWD" "$PY" scripts/qa_shift/clock_contract.py
```

The exact played-clone standalone PYPROOF transcript from the order is also
pending. The initial test `test_replay_cli_reports_clean_played_clock` passed,
but it does not replace that requested transcript. Explicit CLI JSON-file and
corrupt reconstruction exit tests still need to be strengthened before claiming
all ordered proof complete. Fleet counters for slots 1–5 are unmeasured;
slot 2 must remain labeled contaminated, and any future empty slot's zero
counters prove only empty-state behavior.

Coordinator questions:

1. What sanctioned invocation or prerequisite fixes the required mypy module
   duplication, and who owns its 22 existing test typing errors?
2. Should the pre-existing flake8 SQL-line violation be repaired in a separate
   prerequisite or explicitly included in a revised frozen order?
3. Once those gates are executable, resume the remaining proof and tests, rebase
   onto newest origin/main, and open the ordered `Refs #778` PR. Landing still
   requires `nexus restart gateway` by name; no migration or UI rebuild is owed.

This slice adds, informs, and decides no owner question. The settled 778-Q7
answer remains “B. Elapsed delta in the header”; its display belongs to 778-S7.

Codex (GPT-6)

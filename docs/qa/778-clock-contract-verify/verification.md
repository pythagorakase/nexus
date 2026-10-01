# Verification Record: 778-S6a

## Status and Revisions

Verified on 2026-10-01 after coordinator Amendment 1 accepted the original stop.
Final implementation/proof commit: `d0c33d26c8b13d22e27206e0165680186b3d91d0`. Final handoff commit is the
verification-record commit on `claude/778-clock-contract-verify`; its immutable
hash is supplied in the PR/session handoff (a document cannot contain its own
commit hash). Base: `36ec0b2601811a0f89972542352e36c272be90c7`; migration 140 prerequisite from
PR #1073 is present. No merge is authorized or performed.

The original `e628c92c` implementation and `d913828b` stop-report were kept as
separate logical commits, with no squash or amend. The required rebase onto
newest origin/main mapped them to `ab9ec6ae` and `a36c3d17`; the follow-up is
`d0c33d26`. The original report is preserved below as a dated historical section,
whose pending items and old citations describe that stopped run only.

All commands ran from `/Users/pythagor/nexus/.claude/worktrees/778-clock-contract-verify`.
`PY=/Users/pythagor/nexus/.venv/bin/python`; `PYTHONPATH=$PWD`.
`NEXUS_RUN_LIVE_LLM` was unset. Test/played proof used TEST only and
`NEXUS_TEST_PROVIDER_ONLY=1`; no paid provider call was made. All scratch,
logs, caches, main-version copies, and pytest temp files are under
`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a` (denoted `$S` below). The scratch `run_gate.py` runs each long gate
sequentially in the foreground with `subprocess.run(..., timeout=590)`, captures
its full log and exit code, and sets `TMPDIR=$S`. Each command completed before
another gate started. No gateway was started and no owner runtime directory was
modified. No save or template writes or fleet DDL were performed.

Import proof before and after rebase:

```sh
PYTHONPATH=$PWD "$PY" -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/778-clock-contract-verify/nexus/__init__.py
```

## Files Changed

- `nexus/agents/orrery/replay.py`: independent inclusive primary-clock report, ordered findings, recomputed replay clock and full-table verifier.
- `scripts/replay_state.py`: guarded repeatable-read/read-only connection, full-table audit before early returns, text/JSON clock output and nonzero drift exits.
- `scripts/qa_shift/clock_contract.py`: separate six-field read-only family and selected/fleet slot CLI.
- `scripts/qa_shift/README.md`: command, counters, exit/read-only contract and contaminated-slot boundary.
- `scripts/qa_shift/qa_shift.toml`: comment naming the family; no settings values changed.
- `config/reachability.toml`: operator and alphabetically placed classification entry.
- `tests/test_orrery/test_replay.py`: real writer/TEST acceptance, independent corruption, checkpoint-window coverage, missing metadata, clean/corrupt CLI JSON proofs.
- `tests/test_qa_shift.py`: independent defect plants, exact shape/empty/NULL cases and real PostgreSQL read-only refusal.
- `tests/test_api/test_backstage_endpoints_pg.py`: base seeding before metadata and independent latest/earlier SQL clock equality on required disposable prefixes.
- `docs/qa/778-clock-contract-verify/verification.md`: completed proof, both static outputs, CLI/fleet transcripts and preserved dated stop-report.

## Refreshed Problem and Behavior Citations

Problem citations are against base `36ec0b26`: `replay.py:240` has no
clock fields, `:405` reads the stored clock, `:3194` delegates reconstruction,
and `:3330` verifies consecutive checkpoint pairs. Base `replay_state.py:43`
sets read-only without repeatable-read or its assertion; `:81`/`:92` can return
with too few checkpoints and no independent full-table clock audit. Base
Backstage test `:424` uses the header itself as expected and checks only
non-NULL. These are the replaced gaps, not descriptions of current behavior.

Current source and real-path proof:

- `nexus/agents/orrery/replay.py:279`: singleton SELECT and independent inclusive PostgreSQL primary-only sum; exact instant comparisons and five independently counted categories. No view, refresh function or wall-time fallback is the oracle. `:260` adds defaulted fields; `:391` is the full-table verifier; `:3315`/`:3336` attach the bounded report and computed target instant or a missing-row finding. Existing state-ledger semantics and `verify_checkpoints_sync:3468` pair return contract remain.
- `scripts/replay_state.py:45`: read-only/repeatable-read setup and transaction assertion. `:77` exposes reconstruction text and JSON; `:95` returns 1 for clock findings. `:98` runs all three audits, prints checked rows/findings and runs the clock audit before the insufficient-checkpoints return. Real zero/one/two-checkpoint plants pass in the PostgreSQL proof.
- `scripts/qa_shift/clock_contract.py:14`, `:24`, `:35`, `:43`: exact six fields, explicit read-only guard, repeatable-read slot connection, all-slot default and violation exit contract. `tests/test_qa_shift.py:1687` independently plants all five categories; `:1762` refuses writable measurement and `:1770` proves PostgreSQL rejects INSERT. The tests passed in the audited PostgreSQL proof.
- `tests/test_orrery/test_replay.py:2322`, `:2340`, `:2376`, `:2405`, `:2449`: valid `(0,7,7,7,7,7)` offsets; corruption while view/column agree; corruptions outside zero/one/two checkpoint windows; clean TEST CLI text/JSON; corrupt CLI JSON/exit 1. All passed. Missing-target metadata remains an explicit missing-row finding.
- `tests/test_api/test_backstage_endpoints_pg.py:126` seeds the base before metadata; `:207` later updates only user_character; `:431`/`:745`/`:760` compare parsed latest/earlier API clocks with independent SQL, and assert distinct instants. Backstage product `nexus/agents/orrery/backstage.py:203`/`:689` stays unchanged. No client bundle changes.
- `scripts/qa_shift/README.md:305` documents the family; `config/reachability.toml:49`/`:358` register/classify it. The first offline run exposed an out-of-order classification entry; the follow-up moves only that entry to its required sorted position.
- `scripts/qa_shift/world_clock.py` and its contract/shape assertions were not changed. `tests/test_world_clock_contract_pg.py:128` remains its three-field shape assertion and passed in the audited proof.

Connection audit tails below report the active secret-store guard and
`owner targets: none`. The audit explicitly lists the unaudited C
`ReplicationConnection` class. Repository fixture template-cloning pg_dump
subprocesses are outside that audit and use pg_dump's read-only transaction;
clones were fixture-owned disposable targets and dropped at teardown. Fleet
and prerequisite reads deliberately target saves/template with PostgreSQL
read-only protection, separately from test audits.

## Proof Commands and Verbatim Tails

Both offline suites passed before rebase (base `5b977eab`). New main then landed
#1063. After rebase, the complete PostgreSQL set and API/Orrery offline suite
were rerun; every remaining upstream-changed test file plus reachability/runtime
readiness ran as the offline delta proof. Static input files and origin/main
comparison copies were proven byte-identical after rebase. Standalone played
and fleet/prerequisite proofs were repeated on the rebased tree.

### PostgreSQL Proof After Rebase

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q -p tests.dbname_audit tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py tests/test_world_clock_contract_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

Exit 0; verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 29 targets: postgres, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_778s6a_family_* x9, qa640_778s6a_played_*, qa640_778s6a_replay_* x7, qa640_clock_* x7, qa640_replay_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
246 passed, 13 warnings in 49.27s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Offline Suite Outside API and Orrery

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

Exit 0; verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2732 passed, 466 skipped, 8 warnings in 440.99s (0:07:20)
```

### Offline API and Orrery After Rebase

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q tests/test_api tests/test_orrery
```

Exit 0; verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1829 passed, 757 skipped, 7 warnings in 34.66s
```

### Remaining Upstream Delta After Rebase

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q tests/test_commit_handler_sync.py tests/test_entity_tag_manifest_apply.py tests/test_faction_table_audit.py tests/test_orrery_tag_validation.py tests/test_orrery_tag_validation_pg.py tests/test_prompt_tag_vocabulary_pg.py tests/test_trait_compiler.py tests/test_reachability.py tests/test_runtime/test_readiness.py
```

Exit 0; verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
210 passed, 59 skipped, 5 warnings in 20.01s
```

### Explicit Reachability Gate

```sh
"$PY" -m pytest -q tests/test_reachability.py
```

Exit 0; verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.58s
```

### First Offline Failure and Correction

The first offline run failed because this order added its classification entry
out of sorted order. The readiness failure followed the same reachability
error. Only the added entry was moved; no unrelated file was fixed or skipped.
The full affected offline suite subsequently passed, as recorded above.

### First Offline Run

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 NEXUS_TEST_PROVIDER_ONLY=1 "$PY" -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

Exit 1; verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_reachability.py::test_repository_reachability_ratchet - Val...
FAILED tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app
FAILED tests/test_runtime/test_readiness.py::test_doctor_ci_runner_passes_on_this_checkout
3 failed, 2729 passed, 466 skipped, 8 warnings in 447.52s (0:07:27)
```

### Focused Correction Proof

```sh
"$PY" -m pytest -q tests/test_reachability.py tests/test_runtime/test_readiness.py::test_doctor_ci_runner_passes_on_this_checkout
```

Exit 0; verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
55 passed, 5 warnings in 14.53s
```

## Pre-existing Diagnostics

Amendment 1 changes these gates to no new diagnostics against origin/main.
The branch and baseline outputs are recorded in full below; their exit 1 is
pre-existing debt, not a clean-lint/type claim. The new script is included in
the six-source branch run and has no diagnostic; it does not exist on main,
whose comparison checks the five pre-existing sources. Main versions were
written by `git show origin/main:<path>` into `$S/origin-main/<path>` only.
Mypy uses `--shadow-file` to read those versions while keeping canonical module
names and running from this worktree; both runs use `--explicit-package-bases`
and isolated scratch caches. No main checkout or other worktree was modified.

### Black Check

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Exit 0; verbatim output:

```text
All done! ✨ 🍰 ✨
6 files would be left unchanged.
```

### Flake8 Branch

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Exit 1; verbatim output:

```text
tests/test_orrery/test_replay.py:1056:89: E501 line too long (110 > 88 characters)
```

### Flake8 Origin/Main

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/nexus/agents/orrery/replay.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/scripts/replay_state.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/tests/test_orrery/test_replay.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/tests/test_qa_shift.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/tests/test_api/test_backstage_endpoints_pg.py
```

Exit 1; verbatim output:

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/tests/test_orrery/test_replay.py:1039:89: E501 line too long (110 > 88 characters)
```

### Mypy Branch

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/mypy-branch-cache nexus/agents/orrery/replay.py scripts/replay_state.py scripts/qa_shift/clock_contract.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Exit 1; verbatim output:

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

### Mypy Origin/Main

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/mypy-main-cache --shadow-file nexus/agents/orrery/replay.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/nexus/agents/orrery/replay.py --shadow-file scripts/replay_state.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/scripts/replay_state.py --shadow-file tests/test_orrery/test_replay.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/tests/test_orrery/test_replay.py --shadow-file tests/test_qa_shift.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/tests/test_qa_shift.py --shadow-file tests/test_api/test_backstage_endpoints_pg.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/778-S6a/origin-main/tests/test_api/test_backstage_endpoints_pg.py nexus/agents/orrery/replay.py scripts/replay_state.py tests/test_orrery/test_replay.py tests/test_qa_shift.py tests/test_api/test_backstage_endpoints_pg.py
```

Exit 1; verbatim output:

```text
tests/test_qa_shift.py:176: error: "Collection[Collection[str]]" has no attribute "get"  [attr-defined]
tests/test_qa_shift.py:1062: error: No overload variant of "int" matches argument type "object"  [call-overload]
tests/test_qa_shift.py:1062: note: Possible overload variants:
tests/test_qa_shift.py:1062: note:     def __new__(cls, str | Buffer | SupportsInt | SupportsIndex | SupportsTrunc = ..., /) -> int
tests/test_qa_shift.py:1062: note:     def __new__(cls, str | bytes | bytearray, /, base: SupportsIndex) -> int
tests/test_orrery/test_replay.py:294: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:295: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:303: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:304: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:306: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:566: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:574: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:668: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:669: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:670: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1466: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1468: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1470: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1471: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1472: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1480: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1488: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1489: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1490: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:2154: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
Found 22 errors in 2 files (checked 5 source files)
```

Diagnostic comparison (exit 0; normalized counters preserve duplicate
messages, and difflib confirms every diagnostic line is unchanged):

```text
mypy: 22 branch errors = 22 origin/main errors, identical messages modulo line shifts; all diagnostic lines unchanged.
flake8: identical E501 SQL literal on unchanged branch line 1056 / main line 1039.
No new diagnostics.
Static inputs byte-identical after rebase; origin/main comparison sources byte-identical.
```

## Standalone Played-Clone CLI Transcript

The ordered command ran before and after rebase. Each run uses a fresh
`qa640_778s6a_cli_*` clone, TEST acceptance, checkpoints at actual boundaries,
and routed slot 4 before CLI connections. Each CLI mode asserts exit 0.
Clone setup emits normal restore chatter and a missing-ui-build warning;
no app starts. Raw logs remain in `$S/played-cli.log` and
`$S/played-cli-rebased.log`. The complete reconstruction/verify outputs follow.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_TEST_PROVIDER_ONLY=1 PYTHONPATH="$PWD" "$PY" - <<'PYPROOF'
import runpy, sys
from contextlib import closing
from datetime import timedelta
from tests.pg_fixtures import connect, disposable_slot_database, route_slot_to_disposable, seed_played_story, seed_accepted_turn
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
with disposable_slot_database("qa640_778s6a_cli") as dbname:
    route_slot_to_disposable(setattr, slot=4, dbname=dbname)
    first = seed_played_story(dbname, turns=1, slot=4)[-1]
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        capture_state_checkpoint_sync(cur, chunk_id=first, label="manual")
    last = seed_accepted_turn(dbname, slot=4, user_text="Continue.", storyteller_text="You wait in the plaza.", time_delta=timedelta(minutes=7))
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        capture_state_checkpoint_sync(cur, chunk_id=last, label="manual")
    for tail in (["--chunk", str(last)], ["--verify"]):
        sys.argv = ["scripts/replay_state.py", "--slot", "4", *tail]
        try:
            runpy.run_module("scripts.replay_state", run_name="__main__")
        except SystemExit as error:
            assert error.code in (None, 0), error.code
PYPROOF
```

### played-cli (Both Modes Exit 0)

```text
slot 4: state at chunk 2 (base checkpoint 2 at chunk 2)
  entity_tags                          0 rows  [exact]
  entity_pair_tags                     0 rows  [exact]
  entities                             2 rows  [exact]
    - checkpoint-forward activity with exact runtime-maturation death projections; an unledgered is_active change surfaces as verification drift
  characters                           1 rows  [exact]
  places                               1 rows  [exact]
  character_need_states                5 rows  [exact]
  character_travel_states              0 rows  [exact]
  character_project_states             0 rows  [exact]
  character_routine_anchors            0 rows  [exact]
    - checkpoint pass-through; the table has no runtime writer, but offline seed/backfill scripts are invisible between checkpoints
  claim_awareness                      0 rows  [exact]
    - rebuilt 0 mint row(s), 0 explicit revelation row(s), and 0 passive row(s) from producer provenance
  backstory_secrets                    0 rows  [exact]
    - rebuilt 0 authored row(s) and 0 lifecycle flip(s) from world-event provenance
  character_relationships              0 rows  [exact]
  faction_character_relationships      0 rows  [exact]
  faction_relationships                0 rows  [exact]
  world_time: 2100-01-01 00:07:00+00:00
  clock_drifts: 0 finding(s)
slot 4: chunk clocks: 2 checked row(s), 0 finding(s)
slot 4: checkpoint 1 (chunk 1) -> checkpoint 2 (chunk 2): ok
slot 4: correspondence provenance ok (authorial channel excluded from world-state replay; chunk-versioned undo invariants hold)
```

### played-cli-rebased (Both Modes Exit 0)

```text
slot 4: state at chunk 2 (base checkpoint 2 at chunk 2)
  entity_tags                          0 rows  [exact]
  entity_pair_tags                     0 rows  [exact]
  entities                             2 rows  [exact]
    - checkpoint-forward activity with exact runtime-maturation death projections; an unledgered is_active change surfaces as verification drift
  characters                           1 rows  [exact]
  places                               1 rows  [exact]
  character_need_states                5 rows  [exact]
  character_travel_states              0 rows  [exact]
  character_project_states             0 rows  [exact]
  character_routine_anchors            0 rows  [exact]
    - checkpoint pass-through; the table has no runtime writer, but offline seed/backfill scripts are invisible between checkpoints
  claim_awareness                      0 rows  [exact]
    - rebuilt 0 mint row(s), 0 explicit revelation row(s), and 0 passive row(s) from producer provenance
  backstory_secrets                    0 rows  [exact]
    - rebuilt 0 authored row(s) and 0 lifecycle flip(s) from world-event provenance
  character_relationships              0 rows  [exact]
  faction_character_relationships      0 rows  [exact]
  faction_relationships                0 rows  [exact]
  world_time: 2100-01-01 00:07:00+00:00
  clock_drifts: 0 finding(s)
slot 4: chunk clocks: 2 checked row(s), 0 finding(s)
slot 4: checkpoint 1 (chunk 1) -> checkpoint 2 (chunk 2): ok
slot 4: correspondence provenance ok (authorial channel excluded from world-state replay; chunk-versioned undo invariants hold)
```

## Migration-140 Prerequisite and Fleet Reports

The prerequisite is independently confirmed, read-only, for NEXUS_template
and save_01..save_05. No migration was run by this slice.

### Read-Only Prerequisite SQL

```sh
PGOPTIONS="${PGOPTIONS:+$PGOPTIONS }-c default_transaction_read_only=on" PYTHONPATH="$PWD" "$PY" - <<'PY'
from contextlib import closing
import psycopg2
from nexus.database import connection_kwargs
for dbname in ("NEXUS_template", "save_01", "save_02", "save_03", "save_04", "save_05"):
    with closing(psycopg2.connect(**connection_kwargs(dbname))) as conn:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_setting('transaction_read_only'), current_setting('transaction_isolation'), max(version), bool_or(version = '140') FROM schema_migrations")
            row=cur.fetchone()
            assert row[1:3] == ("on", "repeatable read") and row[4], row
            print(row)
PY
```

Exit 0; verbatim output:

```text
('NEXUS_template', 'on', 'repeatable read', '140', True)
('save_01', 'on', 'repeatable read', '140', True)
('save_02', 'on', 'repeatable read', '140', True)
('save_03', 'on', 'repeatable read', '140', True)
('save_04', 'on', 'repeatable read', '140', True)
('save_05', 'on', 'repeatable read', '140', True)
```

The fleet CLI ran twice; each exits 0. Every per-slot violation counter is
shown verbatim. Slot 2 is contaminated evidence, never calibration evidence.
Slot 5 has no metadata rows; its zero counters prove only empty-state behavior.
These are snapshots, not a claim that future writes remain clean. No data
repair is authorized by a nonzero future counter.

### Fleet Before Rebase

```sh
PGOPTIONS="${PGOPTIONS:+$PGOPTIONS }-c default_transaction_read_only=on" PYTHONPATH="$PWD" "$PY" scripts/qa_shift/clock_contract.py
```

Exit 0; verbatim output:

```text
{
  "family": "clock_contract",
  "slots": [
    {
      "slot": 1,
      "chunks": 1425,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    },
    {
      "slot": 2,
      "chunks": 1425,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    },
    {
      "slot": 3,
      "chunks": 40,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    },
    {
      "slot": 4,
      "chunks": 46,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    },
    {
      "slot": 5,
      "chunks": 0,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    }
  ]
}
```

### Fleet After Rebase

```sh
PGOPTIONS="${PGOPTIONS:+$PGOPTIONS }-c default_transaction_read_only=on" PYTHONPATH="$PWD" "$PY" scripts/qa_shift/clock_contract.py
```

Exit 0; verbatim output:

```text
{
  "family": "clock_contract",
  "slots": [
    {
      "slot": 1,
      "chunks": 1425,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    },
    {
      "slot": 2,
      "chunks": 1425,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    },
    {
      "slot": 3,
      "chunks": 40,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    },
    {
      "slot": 4,
      "chunks": 46,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    },
    {
      "slot": 5,
      "chunks": 0,
      "disagreements": 0,
      "primary_regressions": 0,
      "missing_base": 0,
      "nonprimary_contributions": 0,
      "bootstrap_nonzero": 0
    }
  ]
}
```

## Landing Notes and Coordinator Questions

Refs #778. No migration or fleet DDL. Prerequisite migration 140 from PR #1073
is fleet-wide, including locked slot 1. Coordinator must run
`nexus restart gateway` by name after landing because `replay.py` changes.
No nexus.toml/settings model or client bundle changes; no UI rebuild is owed.
Do not merge in this implementer run. The coordinator owns the whole-tree
PostgreSQL gate and review/merge.

No blocking question remains under Amendment 1. The 22 existing mypy errors
and one flake8 violation remain reported debt for separate coordinator triage.
This slice adds, informs, and decides no owner question. 778-Q7 stays verbatim:
“B. Elapsed delta in the header”; that display belongs to 778-S7.

`git diff --check` exits 0. Follow-up commit hooks passed (Orrery catalog,
config/model drift; migration-comment hook skipped with no migration files).
The final documentation commit runs the same hooks normally.

## Historical Stop-Report: 2026-10-01, Accepted at 03:20 CDT

The following is the preserved original report at `d913828b`; its pending items
were resolved by Amendment 1 and the verification above. Original headings
are demoted for this historical section; its text and evidence are preserved.

### STOP-REPORT: 778-S6a

#### Status and Boundary

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

#### Files Changed

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

#### Commands and Verbatim Tails

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

##### Combined PostgreSQL Proof (Before the Assertion Correction)

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

##### Backstage Correction Proof

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

##### Formatting and Static Gates

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

#### Verified Behavior Citations at the Implementation Commit

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

#### Deferred Proof and Coordinator Questions

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

Codex (GPT-6)

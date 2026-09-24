# Work Order 921 Verification

## Scope and Isolation

Branch: `claude/921-session-override`. No new migration, fleet writes, template
writes, paid provider calls, dependency installation, or UI changes. PostgreSQL
fixtures own and drop their `qa640_*` clones. The existing gateway fixture initially
used its hardcoded 8018 lane; it checked availability and shut down its own gateway.
The helper now honors `NEXUS_GATEWAY_PORT`, and the final proof ran on assigned
lane 8017 with `NEXUS_API_URL=http://127.0.0.1:8017`. Its teardown calls `nexus down`
with the same environment. A final `lsof -nP -iTCP:8017 -sTCP:LISTEN` returned no
output (exit 1).

Import preflight:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/921-session-override/nexus/__init__.py
```

## Behavior and Evidence

- `nexus/database.py:82`: the shared maintenance connector resolves the target,
  executes `SET default_transaction_read_only = off` in autocommit before opening
  a work transaction, and logs the database plus operation. It never issues
  `ALTER DATABASE` or terminates a backend.
- `scripts/migrate.py:277`: the explicit override bypasses only the lock skip and
  applies pending migrations through the shared connector. Without the flag,
  `--dbname` still refuses read-only targets and normal slot migrations skip them.
- `scripts/stamp_lore_pass_baseline.py:38` and `:116`: stamping and fingerprint
  refresh both route their write connection through the same session policy.
- `nexus/jobs/scheduler.py:108`: the first observed unlock starts a monotonic hold;
  lock observations reset it. The lock latch survives recovery errors, and each
  observed lock-clear transition is logged once. The hold defaults to the poll
  interval through `DeferredWorkSettings`; TOML documents the optional override.
- `tests/test_api/test_maintenance_locked_pg.py:45`: removes migration 120's
  objects and stamp only in a disposable clone, locks it with the same database
  setting used by slot locking, proves CLI refusal without the flag, and applies
  the actual pending migration with the flag.
- `tests/test_api/test_maintenance_locked_pg.py:80`: proves both stamp modes refuse
  without the flag, then succeed with it; refresh replaces a valid stale hash.
  Both tests check `pg_db_role_setting`, `SHOW default_transaction_read_only` on
  a fresh ordinary session, and `SELECT 1` on an already-connected observer.
- `tests/test_api/test_scheduler_locked_pg.py:118`: a running scheduler observes
  the unlock, stays an observer through a window shorter than its hold, observes
  re-lock, and leaves `SELECT count(*) FROM deferred_work_scheduler` at zero.
  A later sustained unlock receives a fresh hold and eventually acquires.
- `tests/test_api/test_scheduler_locked_pg.py:151`: a real division-by-zero SQL
  error passed through recovery cannot erase the prior lock observation.

## Proof Commands and Tail Output

All commands ran from this worktree root using the shared interpreter. The
PostgreSQL proof has no skipped tests; offline skips are the repository's normal
integration gates, not PostgreSQL proof. No #885 exemptions were needed.

### Final Offline Suite

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2658 passed, 823 skipped, 9 warnings in 94.76s (0:01:34)
```

### Final PostgreSQL and Settings Proof

```sh
export NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017
NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_scheduler_locked_pg.py tests/test_api/test_scheduler_pg.py tests/test_api/test_maintenance_locked_pg.py tests/test_api/test_scheduler_hold_settings.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
16 passed, 7 warnings in 24.08s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Black

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/database.py nexus/jobs/scheduler.py nexus/config/settings_models.py scripts/migrate.py scripts/stamp_lore_pass_baseline.py tests/test_api/test_scheduler_locked_pg.py tests/test_api/test_maintenance_locked_pg.py tests/test_api/test_scheduler_hold_settings.py tests/scheduler_helpers.py
```

```text
All done! ✨ 🍰 ✨
9 files would be left unchanged.
```

### Initial Offline Suite

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2655 passed, 822 skipped, 9 warnings in 100.05s (0:01:40)
```

## Iteration Results

Initial scheduler run: `NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_scheduler_locked_pg.py tests/test_api/test_scheduler_pg.py`

```text
FAILED tests/test_api/test_scheduler_locked_pg.py::test_locked_scheduler_observes_then_acquires
1 failed, 8 passed, 7 warnings in 18.66s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The test changed the poll interval after settings had already resolved the hold
from runtime defaults. It now sets its intended hold explicitly.

The next run added `tests/test_api/test_maintenance_locked_pg.py` to that command:

```text
FAILED tests/test_api/test_maintenance_locked_pg.py::test_stamp_and_refresh_locked_cli
1 failed, 11 passed, 7 warnings in 21.94s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The new test's stale fingerprint was invalid (`stale` instead of a 64-character
hex digest). Correcting the seed produced 15 passing tests. An assigned-lane run
also passed 15 tests before the recovery-latch regression was added; the final
proof above includes it. Neither failure was waived.

`git diff --check` passed without output. Black formatting was applied to touched
Python files before the final check. Both commit hooks passed:

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
```

## Deferred Work and Coordinator Questions

None. No migration or fleet operation is required. The coordinator retains review
and merge authority; this branch will be pushed and opened as a review-ready PR.

Codex — GPT-6 Astra

# Validation Command History

All commands ran from the assigned worktree with `PY=/Users/pythagor/nexus/.venv/bin/python`. Tails are verbatim; diagnostic failures were not represented as passes. PostgreSQL gate summaries retain the known #885 failures.

## Offline Baseline

Diagnostic run overlapped the settings edit and retained the old imported Settings class; it is not a valid unchanged-base result.

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline-baseline.log 2>&1
```

```text
422 failed, 2230 passed, 854 skipped, 9 warnings, 12 errors in 115.81s (0:01:55)
```

## PostgreSQL Baseline

Initial PostgreSQL selection: only the three exempt #885 failures.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg-baseline.log 2>&1
```

```text
3 failed, 156 passed, 2 skipped, 1412 deselected, 9 warnings in 33.58s
```

## Unit

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster.py tests/test_presence_reconciliation.py > /tmp/nexus-799-unit.log 2>&1
```

```text
47 passed, 1 skipped, 5 warnings in 0.30s
```

## Focused

Collection command named a nonexistent test file; corrected in the subsequent run.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py tests/test_new_story_db_mapper.py tests/test_trait_compiler.py > /tmp/nexus-799-focused.log 2>&1
```

```text
no tests ran in 0.00s
```

## Retrograde

Existing recording cursors needed the new catalog reads.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py > /tmp/nexus-799-retrograde.log 2>&1
```

```text
20 failed, 26 passed, 4 skipped, 5 warnings in 1.05s
```

## Identity

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_presence_roster_pg.py -k identity > /tmp/nexus-799-identity.log 2>&1
```

```text
13 passed, 12 deselected, 5 warnings in 6.49s
```

## Retrograde2

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py > /tmp/nexus-799-retrograde2.log 2>&1
```

```text
46 passed, 4 skipped, 5 warnings in 0.70s
```

## Offline

Intermediate fixture and reachability regressions; corrected before the final gate.

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline.log 2>&1
```

```text
9 failed, 2664 passed, 858 skipped, 9 warnings in 100.84s (0:01:40)
```

## PostgreSQL

Two old duplicate-stub expectations and one fixture missing migration 123 were corrected. Other failures were #885.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg.log 2>&1
```

```text
6 failed, 157 passed, 2 skipped, 1412 deselected, 9 warnings in 37.25s
```

## Regressions

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler.py tests/test_trait_compiler.py tests/test_lore/test_two_pass_pipeline.py tests/test_reachability.py > /tmp/nexus-799-regressions.log 2>&1
```

```text
113 passed, 5 warnings in 9.39s
```

## PostgreSQL2

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg2.log 2>&1
```

```text
3 failed, 165 passed, 2 skipped, 1412 deselected, 9 warnings in 42.50s
```

## Identity Final

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_orrery/test_character_identity_pg.py > /tmp/nexus-799-identity-final.log 2>&1
```

```text
17 passed, 5 warnings in 7.30s
```

## Offline Final

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline-final.log 2>&1
```

```text
2675 passed, 864 skipped, 9 warnings in 98.00s (0:01:38)
```

## PostgreSQL Final

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg-final.log 2>&1
```

```text
3 failed, 166 passed, 2 skipped, 1412 deselected, 9 warnings in 43.27s
```

## Final Regressions

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_commit_handler.py tests/test_trait_compiler.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py > /tmp/nexus-799-final-regressions.log 2>&1
```

```text
100 passed, 4 skipped, 5 warnings in 1.24s
```

## Offline Proof

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline-proof.log 2>&1
```

```text
2675 passed, 865 skipped, 9 warnings in 101.29s (0:01:41)
```

## PostgreSQL Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg-proof.log 2>&1
```

```text
3 failed, 167 passed, 2 skipped, 1412 deselected, 9 warnings in 45.28s
```

## CLI Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_character_identity_pg.py::test_identity_ambiguity_never_retries_test_provider > /tmp/nexus-799-cli-proof.log 2>&1
```

```text
1 passed, 5 warnings in 2.26s
```

## Scope Proof

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_commit_handler.py tests/test_trait_compiler.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py > /tmp/nexus-799-scope-proof.log 2>&1
```

```text
100 passed, 4 skipped, 5 warnings in 1.29s
```

## Offline Gate

Final offline gate.

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline-gate.log 2>&1
```

```text
2675 passed, 866 skipped, 9 warnings in 100.04s (0:01:40)
```

## PostgreSQL Gate

Final PostgreSQL gate: only exempt #885 failures.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg-gate.log 2>&1
```

```text
3 failed, 168 passed, 2 skipped, 1412 deselected, 9 warnings in 46.59s
```

## Formatting and Reachability

Black was applied to the affected Python files during implementation. Final check:

```python
import subprocess
import sys
paths = subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], text=True).splitlines()
raise SystemExit(subprocess.call([sys.executable, "-m", "black", "--check", *[path for path in paths if path.endswith(".py")]]))
```

```text
All done! ✨ 🍰 ✨
22 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY scripts/check_reachability.py
```

```json
{
  "maintained": 362,
  "reachable_by_kind": {
    "production": 189,
    "operator": 174,
    "migration": 171,
    "test": 234
  },
  "test_only": 34,
  "existing_unreachable": 85,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```


## PR #929 Review-Amendment Validation

All commands ran from this worktree. `$PY` denotes
`/Users/pythagor/nexus/.venv/bin/python`; each pytest command below used
`PYTHONPATH=$PWD`. These are diagnostic runs before the final post-merge gates
in `verification.md`. Failed diagnostic runs are retained as history, not
reported as passing gates.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py
```

```text
14 passed, 5 warnings in 0.32s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_orrery/test_character_identity_pg.py -k identity
```

Successive diagnostic-run tails:

```text
3 failed, 16 passed, 12 deselected, 5 warnings in 20.24s
1 failed, 22 passed, 12 deselected, 5 warnings in 25.45s
3 failed, 23 passed, 12 deselected, 5 warnings in 29.55s
```

The first caught a missing `scene_location` parameter in the maturation helper;
the second caught the existing manifest schema-version trigger; the third
caught missing JSON codecs in the newly added real async-acceptance fixture.
Each was fixed. The final required PostgreSQL selection includes all these tests.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
15 failed, 2663 passed, 877 skipped, 9 warnings in 98.94s (0:01:38)
```

This pre-merge diagnostic run caught SQL-shape and frontier-setting expectations
in existing recording fixtures, plus the new field description exceeding the
wire's 70-character budget. Existing fixtures were updated, the description was
shortened, and the final offline gate was rerun after merge.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler.py tests/test_orrery/test_retrograde_maturation.py
```

```text
1 failed, 29 passed, 4 skipped, 5 warnings in 0.76s
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler.py tests/test_commit_handler_sync.py tests/test_orrery/test_retrograde_maturation.py tests/test_orrery/test_retrograde_persistence.py
```

```text
1 failed, 66 passed, 5 skipped, 5 warnings in 1.22s
67 passed, 5 skipped, 5 warnings in 1.25s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_character_identity_pg.py::test_identity_maturation_failure_class_is_durable_and_terminal
```

```text
1 passed, 5 warnings in 1.51s
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_skald_wire.py tests/test_trait_compiler.py
```

```text
129 passed, 2 skipped, 5 warnings in 1.06s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py -k 'identity_declaration_binds'
```

```text
3 failed, 3 passed, 20 deselected, 5 warnings in 7.12s
6 passed, 20 deselected, 5 warnings in 7.55s
```

The failed run caught `deepcopy` attempting to pickle `asyncpg.Record`. Batch
validation now copies only mutable index containers and preserves read-only row
evidence. All six sync/async exact, alias, and novel/idempotent cases then passed.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_commit_handler.py tests/test_commit_handler_sync.py tests/test_orrery/test_retrograde_maturation.py tests/test_orrery/test_retrograde_persistence.py tests/test_skald_wire.py tests/test_trait_compiler.py
```

```text
210 passed, 7 skipped, 5 warnings in 1.71s
```

Black formatted changed Python files during development. The final check covers
every Python file changed against `origin/main`; its exact command and output
are in `verification.md`. Both commit hooks passed on fix commit `85f2fb7f`.
The clean main merge is `c74eec9c`.

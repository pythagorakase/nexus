# Verification for #817 S1: The Generated CLI Reference

Branch `claude/817-cli-reference`, cut from `origin/main` at `364fef4b` (still the merge base when this was written). Every command ran from the worktree root with the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`) and `PYTHONPATH=$PWD`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. `nexus` imported from the worktree (`.../worktrees/817-cli-reference/nexus/__init__.py`). No database writes, no gateway, no paid call.

## Parser Counts

Unchanged from the order's reading at `364fef4b`:

```
top-level: 39 groups: 3 ['inspect', 'tags', 'models'] subparsers: 49 leaves: 46
```

`docs/cli_reference.md` has 49 `### \`nexus <path>\`` sections (three groups, 46 leaves). The six arguments without help (`inspect-turn` `--slot`, `--session`, `--chunk`; `prune-manifests` `--slot`; `record-revelation` `--claim-id`, `--source-chunk-id`) render `—` in Description. `trait-audit` `--character-id` and `--character-entity-id` render Default `` `0` ``.

## Red Run

One character of the committed `docs/cli_reference.md` changed (the `nexus up` help line's final `.` to `!`), then restored from a scratch copy before any commit:

```
$ PYTHONPATH=$PWD $PY scripts/render_cli_reference.py --check
docs/cli_reference.md is stale.
Run: python -m scripts.render_cli_reference --write
exit=1
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_cli_reference_doc.py::test_cli_reference_is_current
________________________ test_cli_reference_is_current _________________________

    def test_cli_reference_is_current() -> None:
        """The committed file equals a fresh render of the real parser."""
        expected = render_cli_reference(cli.build_parser())
        if _committed() != expected:
>           raise AssertionError(f"{DOC_PATH} is stale.\nRun: {REGENERATE}")
E           AssertionError: /Users/pythagor/nexus/.claude/worktrees/817-cli-reference/docs/cli_reference.md is stale.
E           Run: python -m scripts.render_cli_reference --write

tests/test_cli_reference_doc.py:60: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_cli_reference_doc.py::test_cli_reference_is_current - Asser...
1 failed in 0.32s
```

After the restore, `--check` exited 0.

## PostgreSQL Proof Set

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_cli_reference_doc.py tests/test_cli_contract.py tests/test_doc_front_matter.py tests/test_reachability.py tests/test_orrery/test_catalog.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
282 passed in 134.13s (0:02:14)
```

## Offline Suites

The first full run of `$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery` took 10:59 and found one failure in this branch's own new file:

```
FAILED tests/test_prompt_lint.py::test_python_has_no_embedded_prompt_prose - ...
1 failed, 2951 passed, 559 skipped, 8 warnings in 659.49s (0:10:59)
```

`AssertionError: Move prompt prose to the registry: scripts/render_cli_reference.py:322`: the `--write` help opened with the imperative `Write`. Commit `24d8142e` rewords it (`Replace docs/cli_reference.md with a fresh render`); `tests/test_prompt_lint.py` then passed (22 passed). Because that run exceeded ten minutes, the rerun is split into three pieces that cover the same files (2,952 passed and 559 skipped in total, the same counts):

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_[a-l]*.py tests/*_test.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
625 passed, 172 skipped, 5 warnings in 434.43s (0:07:14)

$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_[m-z]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1369 passed, 306 skipped, 8 warnings in 190.29s (0:03:10)

$ PYTHONPATH=$PWD $PY -m pytest -q tests/config tests/fixtures tests/proofs tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
958 passed, 81 skipped, 7 warnings in 136.12s (0:02:16)

$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
655 passed, 262 skipped, 7 warnings in 35.18s

$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1210 passed, 1107 skipped, 7 warnings in 13.02s
```

`tests/test_reachability.py` and `tests/test_doc_front_matter.py` ran inside the first two pieces.

## Generator, Reachability, and Dispositions

```
$ PYTHONPATH=$PWD $PY scripts/render_cli_reference.py --check
exit=0
$ $PY -m scripts.render_cli_reference --check
exit=0
$ PYTHONPATH=$PWD $PY -S scripts/check_reachability.py
exit=0
  "newly_unreachable": [],
  "baseline_add_production_paths": [],
  "unclassified_paths": [],
  "classified_paths_not_in_repository": [],
  "class_graph_mismatches": [],
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
exit=0
```

No reachability baseline entry changed.

## Static Checks

Branch:

```
$ $PY -m black --check nexus/cli_contract.py scripts/render_cli_reference.py tests/test_cli_reference_doc.py
All done! ✨ 🍰 ✨
3 files would be left unchanged.
$ $PY -m flake8 nexus/cli_contract.py scripts/render_cli_reference.py tests/test_cli_reference_doc.py
exit=0
$ $PY -m mypy --explicit-package-bases nexus/cli_contract.py scripts/render_cli_reference.py tests/test_cli_reference_doc.py
Success: no issues found in 3 source files
```

`origin/main`'s `nexus/cli_contract.py` (from `git show origin/main:nexus/cli_contract.py` into a scratch directory):

```
$ $PY -m flake8 <scratch>/nexus/cli_contract.py
exit=0
$ $PY -m mypy --explicit-package-bases nexus/cli_contract.py   (in the scratch directory, MYPYPATH=<worktree>)
Success: no issues found in 1 source file
```

No new diagnostics; no pre-existing diagnostics.

## Landing Notes

No migration and no fleet application. No gateway restart owed: only `nexus/cli.py` imports `nexus.cli_contract`, and nothing under `nexus/` imports `nexus.cli`:

```
$ git grep -n "cli_contract" -- nexus
nexus/cli.py:34:nexus/cli_contract.py.
nexus/cli.py:67:from nexus.cli_contract import (
nexus/cli.py:6081:    """Entry point for the NEXUS CLI; exit codes follow nexus.cli_contract."""
$ git grep -nE "from nexus import cli\b|from nexus\.cli import|import nexus\.cli\b" -- nexus
(no match; exit 1)
```

No `ui/` change, no UI rebuild, no state-surface regeneration.

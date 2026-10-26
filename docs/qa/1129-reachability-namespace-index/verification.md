# Reachability Namespace Index Verification

Work order 1129-S1, branch `claude/1129-reachability-index`, cut from `origin/main`
at `c7ae2988`. No migration, no paid call, no gateway lane, no write to any
`save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07`.

All commands run from the worktree root with
`PY=/Users/pythagor/nexus/.venv/bin/python` and `PYTHONPATH=$PWD`, with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. `$SCRATCH` is the
session scratchpad subdirectory `1129-S1/`. The import proof, taken before the
commit-1 test run and the readiness timings, printed:

```text
/Users/pythagor/nexus/.claude/worktrees/1129-S1/nexus/__init__.py
```

## Commits

| Commit | Content |
| --- | --- |
| `ded7980f` (1) | Six behavioral tests in `tests/test_reachability.py` only |
| `fa00557f` (2) | `namespace_parents` set and the membership test |
| `a34cf1f5` (3) | `scaling_benchmark.py` only; every measurement below that names commit 3 |
| (4) | This file |

`git merge origin/main` after commit 3 printed `Already up to date.`
(`origin/main` = `c7ae2988d07b443f627a04d3a4eed1816b1cd438`, rechecked before
commit 4). `docs/decisions/0075-a-behavior-preserving-reachability-index.md` does
not exist on that `origin/main`, so nothing was re-stamped, and no `status:
canonical` document lists a changed file in its `sources:` (a search of every
canonical document for `check_reachability`, `test_reachability` and
`1129-reachability` found none).

## Cited Lines (c7ae2988)

- `scripts/check_reachability.py:423`: `elif any(module.startswith(name + ".") for
  module in modules):`, inside `ImportVisitor.record()` (`:404-450`), reached when
  `resolve()` (`:377-395`) returns no file. `record()` runs per `import` name
  (`:457`), per `from` statement (`:469`) and per imported item with
  `required=False` (`:474`).
- The issue measured 16,346,085 iterations of that generator (2.469s cumulative of
  8.971s under cProfile) and 4.92s unprofiled wall time at f073b371. On c7ae2988
  one read-only run of `python -S scripts/check_reachability.py` in the main
  checkout took 6.14s wall and exited 0 (coordinator check, 2026-10-26).
- `modules` is built once (`:209-211`) and only read afterwards (`:229`,
  `:365-368`, `:383-391`, `:423`, `:428`, `:583`).
- `resolve()` rewrites an aliased name into its own local variable (`:377-395`,
  the alias loop at `:378-382`). The namespace check (`:423`) and the `required`
  branch (`:444-450`) both test the caller's original `name`. The ancestor walk is
  `:426-443`. The three branches are an `if`/`elif`/`elif` chain, so a name that
  takes the namespace branch never reaches the `required` branch.
- The live config has one alias (`config/reachability.toml:148-152`, `utils` to
  `nexus.agents.lore.utils` for `nexus/agents/lore/lore.py`) and two search-path
  declarations (`:198-205`). `nexus/agents/lore/utils/` has no `__init__.py`. The
  three live aliased imports (`nexus/agents/lore/lore.py:56-58`) resolve directly.
- Test gaps in `tests/test_reachability.py` at c7ae2988, and the new test that
  closes each:
  - `unresolved_internal_imports` only asserted empty (`:110`, `:235`, `:893`):
    `test_missing_internal_import_is_reported_with_source_and_line` and
    `test_dotted_prefix_collision_is_not_a_namespace_package`.
  - External names only checked for a blank name (`:236`, `:255`):
    `test_external_imports_are_top_level_names_without_edges`.
  - Namespace coverage module-level only (`:1060-1087`):
    `test_nested_namespace_initializes_each_regular_ancestor_only`.
  - The deferred namespace edge from `:97` never asserted:
    `test_deferred_namespace_import_carries_function_scope`.
  - No test used `import_aliases` (`git grep import_aliases tests` was empty):
    `test_alias_rewrite_keeps_the_unaliased_namespace_check`.
    `import_search_paths` already had a test (`:329-360`).
- The readiness doctor runs the gate as a subprocess, `[sys.executable, "-S",
  script]`, under `[runtime.readiness].reachability_timeout_seconds`
  (`nexus/runtime/readiness.py:1338-1380`; `nexus.toml:1467`, 120.0;
  `nexus/config/settings_models.py:773-780`). The script path is
  `ctx.checkout / "scripts" / "check_reachability.py"` (`readiness.py:1340`), and
  `checkout` defaults to `repo_root()` (`:148`).
  `tests/test_runtime/test_readiness.py:1093-1108` runs it on the checkout. CI runs
  it through `nexus doctor --target ci-runner`
  (`.github/workflows/reachability-check.yml:35-44`).

## The Change

`namespace_parents` holds every proper dotted prefix of an inventoried module
name, built once after the ambiguity check. `module.startswith(name + ".")` holds
exactly when `name == module[:i]` for an index `i` with `module[i] == "."`, so
`name in namespace_parents` equals the old `any(...)` for every string. The empty
name (from `from . import x` at the root, :460-469) and leading-dot names are
exact too: `module[:0] == ""` is in the set exactly when some module name starts
with "." (a hidden root file, `_module_name` :52-56), which is when
`module.startswith(".")` held. The ancestor walk, the `required` branch and the
branch order are byte for byte unchanged.

## Tests on Commit 1 (Unchanged Script)

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
60 passed, 5 warnings in 12.15s
```

## Red Runs (Scratch Plants on Commit 2, Each Reverted)

Plant A: the membership line as `elif any(module.startswith(name) for module in
modules):`.

```text
E       AssertionError: assert [] == [{'line': 1, ...'pkg/cli.py'}]
E         Right contains 2 more items, first extra item: {'line': 1, 'name': 'pkg.name', 'source': 'pkg/cli.py'}
tests/test_reachability.py:1132: AssertionError
FAILED tests/test_reachability.py::test_dotted_prefix_collision_is_not_a_namespace_package
1 failed, 59 passed, 5 warnings in 10.78s
```

Plant B: the ordered `rewritten()` helper after `resolve()` and the membership
line as `elif rewritten(name, self.source) in namespace_parents:` (walk left on
`name`). Line 1238 is the pass-1 external-name assertion.

```text
>       assert "utils" in report["external_or_unresolved_top_level_names"]
E       AssertionError: assert 'utils' in []
tests/test_reachability.py:1238: AssertionError
FAILED tests/test_reachability.py::test_alias_rewrite_keeps_the_unaliased_namespace_check
1 failed, 59 passed, 5 warnings in 9.41s
```

After each plant, `git checkout scripts/check_reachability.py` restored commit 2
and `git status --short` was empty.

## Byte-Identical Report (Decision 1129-D4, Commit 3)

`git show origin/main:scripts/check_reachability.py >
$SCRATCH/check_reachability_before.py`; `git diff c7ae2988 origin/main --
scripts/check_reachability.py` is empty. Both scripts ran against the same tree
(the worktree at commit 3, clean):

```text
$PY -S $SCRATCH/check_reachability_before.py --root $PWD --report $SCRATCH/before.json > $SCRATCH/before-stdout.json; echo $?
0
$PY -S scripts/check_reachability.py --root $PWD --report $SCRATCH/after.json > $SCRATCH/after-stdout.json; echo $?
0
cmp $SCRATCH/before.json $SCRATCH/after.json                 -> identical (2,347,105 bytes each)
cmp $SCRATCH/before-stdout.json $SCRATCH/after-stdout.json   -> identical
```

## Unprofiled Gate Wall Time (Commit 3)

`/usr/bin/time -p nice -n 15 $PY -S <script> --root $PWD > /dev/null`, 7
interleaved pairs, before then after. `uptime` before the batch: `16:16 up 4:53,
5 users, load averages: 29.79 26.81 22.05` (other builders were running).

| Pair | Before `real` (s) | After `real` (s) |
| --- | --- | --- |
| 1 | 5.61 | 4.33 |
| 2 | 5.54 | 4.33 |
| 3 | 5.64 | 4.31 |
| 4 | 5.52 | 4.32 |
| 5 | 5.60 | 4.56 |
| 6 | 5.74 | 4.41 |
| 7 | 5.82 | 4.46 |
| Median | 5.61 | 4.33 |
| Minimum | 5.52 | 4.31 |
| Maximum | 5.82 | 4.56 |

## In-Process Analyzer Time (Commit 3)

`nice -n 15 $PY -S docs/qa/1129-reachability-namespace-index/scaling_benchmark.py
<script> --repo $PWD --repeat 7` (load average 27.97 at the start). This times
`analyze_repository` only, without process startup or the classification pass.

| Script | Modules | Median (s) | Minimum (s) | Maximum (s) |
| --- | --- | --- | --- | --- |
| Before (origin/main copy) | 406 | 5.701 | 5.507 | 6.110 |
| After (branch) | 406 | 4.441 | 4.194 | 4.510 |

## Readiness Doctor Test Time

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q
tests/test_runtime/test_readiness.py::test_doctor_ci_runner_passes_on_this_checkout
--durations=1`, 5 runs each; the `call` duration is recorded. Before: commit 1
(load 17.19). After: commit 2 (load 14.41). Every run passed.

| Run | Commit 1 call (s) | Commit 2 call (s) |
| --- | --- | --- |
| 1 | 5.59 | 4.48 |
| 2 | 5.55 | 4.51 |
| 3 | 5.52 | 4.37 |
| 4 | 5.60 | 4.42 |
| 5 | 5.61 | 4.43 |
| Median | 5.59 | 4.43 |
| Spread (min to max) | 5.52 to 5.61 | 4.37 to 4.51 |

## cProfile (Commit 3)

`nice -n 15 $PY -S -m cProfile -s cumulative <script> --root $PWD`; both exited 0.

Before (`58302508 function calls (54408775 primitive calls) in 10.541 seconds`):

```text
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
    24756    0.018    0.000    3.736    0.000 check_reachability_before.py:404(record)
    28629    0.664    0.000    3.613    0.000 {built-in method builtins.any}
      881    0.000    0.000    2.997    0.003 ast.py:33(parse)
      883    2.996    0.003    2.996    0.003 {built-in method builtins.compile}
 17352908    1.952    0.000    2.936    0.000 check_reachability_before.py:423(<genexpr>)
```

After (`23596742 function calls (19703009 primitive calls) in 7.256 seconds`):

```text
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      881    0.001    0.000    3.321    0.004 ast.py:33(parse)
      883    3.321    0.004    3.321    0.004 {built-in method builtins.compile}
    24756    0.012    0.000    0.123    0.000 check_reachability.py:412(record)
        1    0.001    0.001    0.001    0.001 check_reachability.py:214(<setcomp>)
```

`grep -c ":423(<genexpr>)" $SCRATCH/profile-after.txt` prints `0`. In the after
profile `ast.parse` is 3.321s of 7.256s (45.8%), almost all of it in
`builtins.compile` (3.321s). In the before profile it was 2.997s of 10.541s
(28.4%). The parse path is unchanged (Decision 1129-D3).

## Synthetic Scaling (Commit 3)

`nice -n 15 $PY -S docs/qa/1129-reachability-namespace-index/scaling_benchmark.py
<script>` with the defaults (load average 16.29 at the start).

Before:

```json
{
  "script": "/private/tmp/claude-501/-Users-pythagor-nexus/9dcd8ba0-5aed-4efa-8d64-38cffa54a15d/scratchpad/1129-S1/check_reachability_before.py",
  "python": "3.11.12",
  "mode": "synthetic",
  "imports": 2000,
  "repeat": 5,
  "results": [
    {
      "modules": 250,
      "median_s": 0.052484666999589535,
      "min_s": 0.050825624999561114,
      "max_s": 0.054055582999353646
    },
    {
      "modules": 500,
      "median_s": 0.09428433399989444,
      "min_s": 0.09320820799985086,
      "max_s": 0.09686725000028673
    },
    {
      "modules": 1000,
      "median_s": 0.18310449999989942,
      "min_s": 0.18127649999951245,
      "max_s": 0.1850119579994498
    },
    {
      "modules": 2000,
      "median_s": 0.36346858400065685,
      "min_s": 0.3554982919995382,
      "max_s": 0.3738446669995028
    }
  ]
}
```

After:

```json
{
  "script": "scripts/check_reachability.py",
  "python": "3.11.12",
  "mode": "synthetic",
  "imports": 2000,
  "repeat": 5,
  "results": [
    {
      "modules": 250,
      "median_s": 0.016902874998777406,
      "min_s": 0.016653541999403387,
      "max_s": 0.01847795799949381
    },
    {
      "modules": 500,
      "median_s": 0.02796916700026486,
      "min_s": 0.0276035420010885,
      "max_s": 0.030016374999831896
    },
    {
      "modules": 1000,
      "median_s": 0.0515202920014417,
      "min_s": 0.05097629199917719,
      "max_s": 0.05294016700099746
    },
    {
      "modules": 2000,
      "median_s": 0.10014112499993644,
      "min_s": 0.09273170800042863,
      "max_s": 0.10773637500096811
    }
  ]
}
```

## Final Test Tails (Branch at Commit 3, Merged With `origin/main`)

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
60 passed, 5 warnings in 8.90s
```

`NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p
tests.dbname_audit tests/test_reachability.py tests/test_runtime/test_readiness.py`
(load average 14.08 before the run; no skips):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
104 passed in 26.85s
```

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api
--ignore=tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3202 passed, 678 skipped, 8 warnings in 638.18s (0:10:38)
```

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 48.91s
```

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 6.29s
```

## Static Checks

- `$PY -m black --check` on the three files: `3 files would be left unchanged.`
- `$PY -m flake8` on the three files: no output, exit 0. On the `origin/main`
  copies of the two pre-existing files: no output, exit 0.
- `$PY -m mypy --explicit-package-bases` on the three files: 4 errors in
  `scripts/check_reachability.py` (`:426`, `:442`, `:455` `"AST" has no attribute
  "lineno"`; `:691` `Incompatible types in assignment`). The `origin/main` copies
  report the same 4 errors at `:418`, `:434`, `:447` and `:683`; they moved by the
  8 inserted lines and none is on a changed line. The benchmark and the test file
  report none.
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  `OK: exception disposition coverage and shrink-only baseline verified.`; no
  handler added and the baseline is unchanged.

## Consumers

`git grep -n check_reachability -- 'nexus/**/*.py'` shows only the readiness
subprocess call and a description string:

```text
nexus/config/settings_models.py:778:            "(python -S scripts/check_reachability.py)"
nexus/runtime/readiness.py:1338:def _check_reachability_gate(ctx: ReadinessContext) -> Outcome:
nexus/runtime/readiness.py:1340:    script = ctx.checkout / "scripts" / "check_reachability.py"
nexus/runtime/readiness.py:1341:    command = "python -S scripts/check_reachability.py"
nexus/runtime/readiness.py:1487:        _check_reachability_gate,
```

Nothing under `nexus/` imports the script, so no gateway restart is owed.
`nexus.toml`, `config/reachability.toml` and `config/reachability_baseline.json`
are unchanged.

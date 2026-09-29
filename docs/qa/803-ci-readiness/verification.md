# Verification: CI Runs the Readiness Contract (#803)

Branch `claude/803-ci-readiness`, cut from `origin/main` at 45a14f0c. PR #1022.

## What CI Runs

`.github/workflows/reachability-check.yml` (job `reachability`):

1. `pipx install poetry`, then `actions/setup-python@v5` with `cache: poetry`
   (key: Python version plus `poetry.lock` hash).
2. `poetry install --only main` installs the locked runtime dependencies and the
   project itself as editable, so `repo_root()` (`nexus/runtime/home.py:57-59`)
   is the workspace and `scripts/check_reachability.py` is found.
3. `poetry run nexus doctor --target ci-runner --json | tee readiness-report.json`
   under `bash -e -o pipefail`, so the doctor's exit 1 fails the step.
4. Only when an earlier step failed (`if: failure()`):
   `poetry run python -S scripts/check_reachability.py --report
   reachability-report.json || true`, so the log lists each offending path
   under its finding key and the full import graph is written.
5. `readiness-report.json` and, after a failure, `reachability-report.json`
   are uploaded as the `ci-runner-readiness` artifact (`if: always()`). When
   the doctor crashes before it prints JSON, `tee` has still created
   `readiness-report.json`, so that file is uploaded empty and the traceback
   is only in the step log.

## No Silent Narrowing

`_check_reachability_gate` (`nexus/runtime/readiness.py:998-1043`) runs
`[sys.executable, "-S", "scripts/check_reachability.py"]` with
`cwd=ctx.checkout`. The checker's defaults are `--root` = its own parent
directory (`scripts/check_reachability.py:19,808`) and
`--config config/reachability.toml` (`:20,809`), which names
`config/reachability_baseline.json`. The old step passed only `--report`,
which writes the graph file and changes nothing else: locally the summary
with and without `--report` is byte-identical (`cmp` below). So the doctor
validates the same graph against the same baseline, still under `-S` (the
venv interpreter with site-packages skipped). No second `-S` step is needed.

The gate is at least as strict as the old step: it fails on a non-zero exit
and also on any non-empty list in the summary.

What we lose: on a green run, `reachability-report.json` (the full import
graph) is no longer uploaded, because the gate passes no `--report`. The
doctor's own report gives only a count per finding list (for example
`exit 1: newly_unreachable (1)`), so the workflow reruns the checker directly
after a failure. A red run therefore still prints the offending paths and
still uploads the graph; see Failure Diagnostics below.

```
$ $PY -S scripts/check_reachability.py --report $S/reach-report.json > $S/direct.json; echo direct_exit=$?
direct_exit=0
$ $PY -S scripts/check_reachability.py > $S/direct-noreport.json; echo exit=$?
exit=0
$ cmp $S/direct.json $S/direct-noreport.json && echo identical-summary
identical-summary
reachable_by_kind: {'production': 214, 'operator': 225, 'migration': 196, 'test': 270}; non-empty finding lists: {}
```

## Local Run of the CI Step

```
$ cd <worktree> && PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/803-ci-readiness/nexus/__init__.py
$ PYTHONPATH=$PWD $PY -m nexus.cli doctor --target ci-runner --json; echo exit=$?
{
  "checks": [
    {
      "depends_on": [],
      "id": "config.valid",
      "observed": "/Users/pythagor/nexus/.claude/worktrees/803-ci-readiness/nexus.toml (checkout)",
      "remediation": null,
      "status": "pass",
      "targets": [
        "owner-host",
        "owner-client",
        "ci-runner"
      ]
    },
    {
      "depends_on": [
        "config.valid"
      ],
      "id": "reachability.gate",
      "observed": "214 production modules reachable, no findings",
      "remediation": null,
      "status": "pass",
      "targets": [
        "ci-runner"
      ]
    }
  ],
  "ok": true,
  "omitted": [],
  "schema_version": 1,
  "target": "ci-runner"
}
exit=0   (4.5 s wall)
```

Failure path, with the workflow's shell options (`bash -e -o pipefail`) and a
missing config:

```
$ bash -e -o pipefail -c "PYTHONPATH=$PWD $PY -m nexus.cli doctor --target ci-runner --json --config $S/missing.toml | tee $S/fail.json"; echo pipeline_exit=$?
... "id": "config.valid", "status": "fail", "observed": "<scratchpad>/missing.toml does not exist" ...
... "id": "reachability.gate", "status": "skip", "observed": "config.valid failed" ...
"ok": false
pipeline_exit=1
```

Failure diagnostics, in a scratch copy of the tracked files with one
added orphan module (`nexus/zz_orphan_803.py`), running the doctor step and
then the failure-only step exactly as the workflow does:

```
$ env -u NEXUS_HOME -u NEXUS_RUNTIME_CONFIG bash -e -o pipefail -c "PYTHONPATH=\$PWD $PY -m nexus.cli doctor --target ci-runner --json | tee readiness-report.json"; echo doctor_step_exit=$?
... "id": "config.valid", ... "status": "pass" ...
      "id": "reachability.gate",
      "observed": "exit 1: newly_unreachable (1)",
      "remediation": "Run python -S scripts/check_reachability.py; record an intended change with --write-baseline --reason.",
      "status": "fail",
  "ok": false,
doctor_step_exit=1
$ $PY -S scripts/check_reachability.py --report reachability-report.json || true; echo step_exit=$?
{
  "maintained": 376,
  "reachable_by_kind": {
    "production": 214,
    "operator": 225,
    "migration": 196,
    "test": 270
  },
  "test_only": 41,
  "existing_unreachable": 62,
  "newly_unreachable": [
    "nexus/zz_orphan_803.py"
  ],
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
step_exit=0
$ ls -la readiness-report.json reachability-report.json
-rw-r--r--@ 1 pythagor  wheel  1941163 Sep 29 18:34 reachability-report.json
-rw-r--r--@ 1 pythagor  wheel      805 Sep 29 18:34 readiness-report.json
```

## Local Parity

The doctor checks the checkout that its imported `nexus` package belongs to
(`ReadinessContext.checkout` defaults to `repo_root()`,
`nexus/runtime/readiness.py:140`, which is `nexus/runtime/home.py:57-59`); the
working directory does not change it. From this worktree, which shares the
main checkout's venv, the venv's `nexus` console script checks the main
checkout, while `python -m nexus.cli` with `PYTHONPATH=$PWD` checks the
worktree. `docs/runtime.md` names both commands.

```
$ env -u NEXUS_HOME -u NEXUS_RUNTIME_CONFIG PYTHONPATH=$PWD $PY -m nexus.cli doctor --target ci-runner --json   (summarized)
True [('config.valid', 'pass', '/Users/pythagor/nexus/.claude/worktrees/803-ci-readiness/nexus.toml (checkout)'), ('reachability.gate', 'pass', '214 production modules reachable, no findings')]
exit=0
$ env -u NEXUS_HOME -u NEXUS_RUNTIME_CONFIG /Users/pythagor/nexus/.venv/bin/nexus doctor --target ci-runner --json   (config.valid observed)
/Users/pythagor/nexus/nexus.toml (checkout)
```

## GitHub Actions Runs on PR #1022

| Run | Head | Install | Result | Job time |
| --- | --- | --- | --- | --- |
| https://github.com/pythagorakase/nexus/actions/runs/36644250936 | 64788d72 | `pip install -e .` (unlocked) | failure | 1m33s |
| https://github.com/pythagorakase/nexus/actions/runs/36644838541 | a7372e9e | `poetry install --only main`, cold cache | success | 2m13s |
| https://github.com/pythagorakase/nexus/actions/runs/36645090955 | a3160bf3 | `poetry install --only main`, warm cache | success | 50s |
| https://github.com/pythagorakase/nexus/actions/runs/36645262937 | d8c10f20 | `poetry install --only main`, warm cache (restore 44 s) | success | 1m23s |
| https://github.com/pythagorakase/nexus/actions/runs/36646110349 | 4f232462 | `poetry install --only main`, warm cache (restore 41 s); failure-only step added | success | 1m04s |

The first run is why the install uses the lock: the unlocked resolve took
opentelemetry-api 1.45.0 (the lock pins 1.39.1), and pydantic-ai-slim 1.30.1
imports `opentelemetry._events`, which 1.45 no longer has:

```
❌ Error validating /home/runner/work/nexus/nexus/nexus.toml:
   No module named 'opentelemetry._events'
...
  File "/home/runner/work/nexus/nexus/nexus/config/settings_models.py", line 1376, in _validate_weather_contract
    from nexus.agents.orrery.weather import WEATHER_VALUES
...
ModuleNotFoundError: No module named 'opentelemetry._events'
##[error]Process completed with exit code 1.
```

Step timings, cold run 36644838541:

```
Checkout                              5s
Install Poetry                       19s
Set up Python                         3s   (cache miss)
Install NEXUS                        68s
Run the ci-runner readiness checks   11s
Post Set up Python                   25s   (cache saved)
```

Step timings, warm run 36645090955:

```
Checkout                              1s
Install Poetry                        7s
Set up Python                        28s   (Cache hit ... Cache restored successfully)
Install NEXUS                         1s
Run the ci-runner readiness checks   11s
```

Step timings, warm run 36645262937 (head d8c10f20):

```
Checkout                              6s
Install Poetry                       14s
Set up Python                        44s   (cache hit 23:27:28, restored 23:28:10: about 42 s)
Install NEXUS                         1s
Run the ci-runner readiness checks   12s
```

Step timings, run 36646110349 (head 4f232462, after the review fixes):

```
Checkout                              3s
Install Poetry                        7s
Set up Python                        41s   (cache hit 23:36:46, restored 23:37:26)
Install NEXUS                         1s
Run the ci-runner readiness checks    8s   ("ok": true; "214 production modules reachable, no findings")
Print the reachability findings       skipped (no earlier step failed)
Save readiness evidence               0s   ("With the provided path, there will be 1 file uploaded" ... "Final size is 423 bytes")
```

On a green run the failure-only step is skipped and `reachability-report.json`
does not exist, so the artifact holds only `readiness-report.json`.

Cost of `cache: poetry`: the cache holds the whole locked `--only main`
virtualenv, including torch, transformers, and sentence-transformers. One
entry is 2.42 GiB (`gh cache list`:
`setup-python-Linux-x64-python-3.11.16-poetry-v2-c40aa032...  2.42 GiB`; the
runner log reports `Cache Size: ~2488 MB (2608434451 B)`), about a quarter of
the 10 GB per-repository Actions cache limit, and each `poetry.lock` change
adds another entry of about that size. Restoring it takes 28 to 44 s,
against a 68 s cold install plus 25 s to save the cache. So a warm cache
saves roughly 25 to 40 s of install time per run; whether that pays for the
quota is the owner's call (deferred in the PR body).

Doctor step output on the runner (run 36644838541; identical on 36645090955),
verbatim from `gh run view 36644838541 --log` with the timestamps and the
command echo removed:

```
shell: /usr/bin/bash --noprofile --norc -e -o pipefail {0}
env:
  pythonLocation: /opt/hostedtoolcache/Python/3.11.16/x64
  PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.11.16/x64/lib/pkgconfig
  Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.11.16/x64
  Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.11.16/x64
  Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.11.16/x64
  LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.11.16/x64/lib
##[endgroup]
{
  "checks": [
    {
      "depends_on": [],
      "id": "config.valid",
      "observed": "/home/runner/work/nexus/nexus/nexus.toml (checkout)",
      "remediation": null,
      "status": "pass",
      "targets": [
        "owner-host",
        "owner-client",
        "ci-runner"
      ]
    },
    {
      "depends_on": [
        "config.valid"
      ],
      "id": "reachability.gate",
      "observed": "214 production modules reachable, no findings",
      "remediation": null,
      "status": "pass",
      "targets": [
        "ci-runner"
      ]
    }
  ],
  "ok": true,
  "omitted": [],
  "schema_version": 1,
  "target": "ci-runner"
}
```

The 5-minute timeout stays: the cold job took 2m13s.

## Local Test Gates

```
$ $PY -m pytest -q tests/test_reachability.py tests/test_runtime/test_readiness.py
61 passed, 5 warnings in 15.44s

$ $PY -m pytest -q -p no:cacheprovider
4130 passed, 1075 skipped, 8 warnings in 290.45s (0:04:50)
```

Rerun after the review fixes (workflow and docs only):

```
$ $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py tests/test_runtime/test_readiness.py
61 passed, 5 warnings in 14.91s

$ $PY -m pytest -q -p no:cacheprovider tests/test_cli_contract.py
51 passed, 5 warnings in 24.29s
```

No Python file changed, so Black, flake8, and mypy have nothing to check.

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
4. `readiness-report.json` is uploaded as the `ci-runner-readiness` artifact
   (`if: always()`).

## No Silent Narrowing

`_check_reachability_gate` (`nexus/runtime/readiness.py:998-1039`) runs
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

What changes: `reachability-report.json` (the full import graph) is no longer
uploaded. The gate cannot write it (it passes no `--report`), so per the
order the doctor report is the artifact; the full graph is one local
`python -S scripts/check_reachability.py --report <path>` away.

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

## GitHub Actions Runs on PR #1022

| Run | Head | Install | Result | Job time |
| --- | --- | --- | --- | --- |
| https://github.com/pythagorakase/nexus/actions/runs/36644250936 | 64788d72 | `pip install -e .` (unlocked) | failure | 1m33s |
| https://github.com/pythagorakase/nexus/actions/runs/36644838541 | a7372e9e | `poetry install --only main`, cold cache | success | 2m13s |
| https://github.com/pythagorakase/nexus/actions/runs/36645090955 | a3160bf3 | `poetry install --only main`, warm cache | success | 50s |

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

Doctor step output on the runner (run 36644838541; identical on 36645090955):

```
shell: /usr/bin/bash --noprofile --norc -e -o pipefail {0}
{
  "checks": [
    {
      "depends_on": [],
      "id": "config.valid",
      "observed": "/home/runner/work/nexus/nexus/nexus.toml (checkout)",
      "remediation": null,
      "status": "pass",
      "targets": ["owner-host", "owner-client", "ci-runner"]
    },
    {
      "depends_on": ["config.valid"],
      "id": "reachability.gate",
      "observed": "214 production modules reachable, no findings",
      "remediation": null,
      "status": "pass",
      "targets": ["ci-runner"]
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

No Python file changed, so Black, flake8, and mypy have nothing to check.

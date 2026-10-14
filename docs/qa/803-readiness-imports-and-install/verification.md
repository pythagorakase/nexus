# Readiness Imports and Desktop Install Checks

Status: the ordered proof ran on the integrated wave-B tree at
`2beee6030315631ff358eed21f9ca09b35b48e87` (integration head `a563203a` plus the
review fixes); see "Integrated-Tree Proof (2026-10-13)" at the end. The
whole-tree gate, the offline whole-tree split and landing remain the
coordinator's steps. The sections before that one are the lane's original
Codex record. Its two ordered S1 initial red cases and separate manual before
reproduction completed with the intended failures on tests-only head
`d9b26cfc6d7b95901b9a8e467ce1c9cdb556dc5d`, when product code was byte-identical
to main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. That record still cites
`4ae8b8d2`; the assembly has since moved the canonical documents'
`verified_commit` stamps to `f073b371`. Initial evidence was committed as
`be88df8de6e4b9be3a49016e648c44562867b8f5` before any product change.

The frozen order is `temp/orders_2026_10_07/803-S1.md`, including the 803-S7
install-check scope and its settled Q13 bundled-copy amendment. The live
[recorded rulings](https://github.com/pythagorakase/nexus/issues/803#issuecomment-5915946885)
were read on 2026-10-08: Q9 places the narrow ImportError guard in the runner,
Q6 defines owner-client diagnostics, and Q13 chooses environment, checkout,
then bundled desktop configuration. No owner decision is requested here.

`test_runner_reports_an_import_failure_as_a_failed_check` invokes a real
missing module import in a two-check ci-runner registry. It expects the root
finding to name the module and check, the ordered install remediation, and
the dependent to skip without running. Before the guard, the import should
escape. Access to the future remediation constant occurs only after the
runner returns, so its current absence does not break collection.

`test_doctor_json_reports_a_broken_install` writes the prescribed raising
`pydantic_ai` package in its private pytest directory, places it before this
worktree on the child `PYTHONPATH`, and runs the actual JSON ci-runner CLI
with the worktree config. The child inherits only OS process basics, then
receives disabled Keychain, the TEST-provider guard, disabled bytecode and
its own absolute receipt directory. Runtime/routing, PostgreSQL, live,
pytest and provider-credential variables are excluded. It requires exit 1,
no traceback, a valid failed report, skipped reachability and a retained
`config.load_settings` ModuleNotFoundError receipt. It is bounded to 30
seconds and has no PostgreSQL opt-in, provider operation or owner-client run.

## Initial Red and Manual Before Proof

The coordinator admitted exactly the two offline nodes and the separate
ci-runner reproduction. [Initial metadata](initial-red.json) records the
exact argv, worktree import, unchanged source/tree pins, allowlisted
environment key names and receipt-root metadata. The load was 7.93017578125;
the outer deadline was 120 seconds and the CLI child's timeout 30 seconds.
Both expected failures were inspected in full: the runner's real missing
module escapes at `spec.run(ctx)`, and the child CLI exits 1 with the stub's
`opentelemetry._events` traceback. Neither failure is collection/setup,
missing-remediation-constant or receipt setup. Raw
[stdout](initial-red.stdout.txt), [stderr](initial-red.stderr.txt) and
[JUnit](initial-red.junit.xml) are preserved unchanged.

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner targets: none
2 failed in 0.70s
```

The audit reports `psycopg2.extensions.ReplicationConnection` as an unaudited
connection class. It also does not cover the separate CLI subprocess. That
child selects only ci-runner config validation and dependent reachability;
the unconditional stub import stops config before any dependent can run.
No live, PostgreSQL, corpus or secret-store opt-in was enabled.

The separate [manual-before metadata](manual-before.json) records its fresh
private scratch, exact same worktree import and source, allowlisted
environment, command and receipt inventory. Load was 9.0625. The
actual `python -m nexus.cli --json doctor --target ci-runner --config ...`
exited 1, printed [zero stdout bytes](manual-before.stdout.txt), and emitted
the existing loader diagnostic followed by the escaping
[traceback](manual-before.stderr.txt). Its private `receipts/home` contains
one retained 1210-byte [config-load receipt](manual-before.receipt.jsonl.txt).
The exact [stub bytes](manual-stub.py.txt) remain available for after proof.

For both phases, this worktree's `.nexus/receipts` and the user's
`~/.nexus/receipts` were absent before and after. The manual child was outside
pytest: no pytest guard or database-audit coverage is claimed for it. Its
bounds were the ci-runner target, unconditional import failure, disabled
Keychain, credential-free allowlist and explicit private receipt seam. The
loader's diagnostic and failure receipt are preserved behavior. The raw
sources remain in private scratch; [SHA256 provenance](initial-proof-provenance.json)
verifies every copied artifact byte-for-byte. No scratch cleanup is claimed.

## Source Implementation Checkpoint

The source now adds only the runner's narrow `ImportError` finding around
`spec.run(ctx)`, inside its existing settings scope. Other exceptions and
dependency skipping retain their behavior. The loader's existing stderr,
exception and private receipt paths are unchanged, as are all existing
readiness exception handlers and their baseline entries.

`desktop_config.py` mirrors the current Rust struct's aliases, defaults,
lookup precedence, origin override/normalization, working-directory anchor
and program search. Its three strict integer fields reject bool/coercion,
negatives and values above `2**64 - 1`; neither timeout clamp is copied.
The module uses only stdlib and existing Pydantic. Its documented residual
is that Python cannot discover the running shell executable or build tree;
the fallback JSON ships beside the Python package. `pyproject.toml` adds
exactly that include entry; the lock and installed environment are unchanged.

The three owner-client checks follow `gateway.version`: config compares the
actual profile gateway origin and status path, credentials diagnoses Access
and the target's auth contract without printing token values, and command
resolution checks a real executable and working directory without spawning
it. Existing 822 checks remain. The separate 812 artifact check and 803-S6
init-plan implementation are not on this frozen base; integration must keep
their registry entries and dynamic behavior when merging them.

Authored tests use actual files and executables plus the existing loopback
runtime fixture. They cover precedence with invalid/missing/empty explicit
paths, packaged fallback, Rust field-name parity, all three u64 boundaries,
PATH/fixed-directory resolution, the nine ordered target cases plus wrong
status path/blank credential variable/empty command/missing working directory,
and a no-network Access refusal with the in-memory secret store. The three
existing owner-client CLI tests gain the auth block, private desktop config
and exact six-check output; the unreadable Access-store test is unchanged.

The original record said that Black and the reachability generator ran
here, but it kept no command or output for either, so those two claims are
withdrawn. The integrated-tree section below records `black --check` on the
four files and `scripts/check_reachability.py` (no `--write-baseline`) with
their output. What the lane diff itself shows is the committed baseline
delta: `nexus/runtime/desktop_config.py` joins the production list and the
`reason` text changes; nothing else changes.
Current actual canonical frontmatter declares none of these changed source
paths, so no freshness stamp is changed in this checkpoint. Recalculate
closure after predecessor landings rather than rewriting decision quotations.

## Remaining Proof (Superseded)

This section is the lane's original list; the integrated-tree section below
runs each item or names it as the coordinator's step.

The next admitted focused run must cover `test_readiness.py`, new
`test_desktop_config.py`, `test_readiness_pg.py`, `test_runtime_status.py`,
`test_supervisor.py`, `test_cli_contract.py`, card identity and connection
lifecycle, followed by the coordinator's doc/reachability and static checks.
The two S1 cases need green on the implementation, and the exact private
manual-before reproduction needs an after counterpart with its receipt
retained. No further test or manual run has occurred since the initial red.

Two independent restoring controls remain required: remove only `_run_check`'s
guard and require both S1 cases to fail; swap explicit-env and checkout lookup
precedence and require `test_lookup_follows_the_shell_order` to fail. Record
before/planted/restored hashes, exact failure identities and every guard.

Packaging (`poetry check --lock`, a scratch-only wheel, member listing and
exact artifact cleanup), the bounded owner-client diagnostic, changed-file
flake8/mypy comparisons, full focused PG proof and the coordinator's final
gate all await admission. Owner-host doctor, installation, provider calls,
services and owner database operations remain excluded. No migration,
fleet application, UI source/build/receipt or shell rebuild is owed. A
gateway restart is owed when owner services next run; publication and
landing remain coordinator-owned.

Codex — GPT-6

## Integrated-Tree Proof (2026-10-13)

Run by the wave-B fixer (Claude Opus 5.5) in worktree
`.claude/worktrees/fix-803-s1`, branch `claude/waveb-fix-803-s1`, cut from the
integration head `a563203a` (origin/main `f073b371` plus the wave-B lanes).
Every run below is on commit `2beee6030315631ff358eed21f9ca09b35b48e87`
("Tighten the desktop readiness checks after review"), which applies the
review findings listed under "Review Fixes". `PY` is
`/Users/pythagor/nexus/.venv/bin/python`; `PYTHONPATH=$PWD` resolves `nexus` to
`/Users/pythagor/nexus/.claude/worktrees/fix-803-s1/nexus/__init__.py`.
`$S` is the fixer's private scratch directory.

### Review Fixes

- `readiness.py`: the over-long `desktop.config` f-string is split (flake8 E501).
- `readiness.py`: `desktop.credentials` raises `RuntimeError("gateway.reachable has
  not passed in this readiness run")` when `ctx.runtime_status` is `None`, after
  the Cloudflare Access rule (a), instead of reading `{}` and misreporting a
  missing auth block. The Access test still passes: rule (a) needs no status.
- `desktop_config.py`: `normalize_runtime_origin` checks the scheme outside the
  `try`, so the error is the shell's own text, `runtimeOrigin must use http or
  https, got "ftp"` (`lib.rs` formats the scheme with `{:?}`), not wrapped in
  `invalid runtime origin ...`.
- `desktop_config.py`: a new `_condense` helper formats pydantic errors as
  `one_line` does (`loc: msg`, at most three, `(+N more)`); `_read_config`
  catches `ValidationError` (which includes invalid JSON) and reports
  `<path> is invalid: <condensed>`. The helper repeats `one_line` because
  `readiness.py` imports this module.
- `test_readiness.py`: the over-long expected `gateway.version` line is split.
  `test_desktop_checks_against_a_runtime` gains `bare-missing-program` (bare
  `qa803-absent-cli`, `PATH` an empty tmp directory, `HOME` a tmp directory;
  observed is exactly `qa803-absent-cli not found on PATH or the shell's fixed
  directories` and the remediation names the desktop config path) and
  `bare-program-on-path` (observed is `<tmp>/on-path/qa803-path-cli (via PATH) in
  <tmp>`). `missing-program` and `not-executable` now assert their exact
  `... is missing or not executable` text.
- `test_desktop_config.py`: the strict-integer loop variable is `bad`, not a
  reused `value` (mypy). The origin test asserts the exact unwrapped scheme
  text; the invalid-field test asserts `<path> is invalid: authHeader: Input
  should be a valid string`, and a four-error file ends in ` (+1 more)` with
  no `errors.pydantic.dev` link.

### Static Checks

```text
$ set -- nexus/runtime/readiness.py nexus/runtime/desktop_config.py tests/test_runtime/test_readiness.py tests/test_runtime/test_desktop_config.py
$ $PY -m black --check "$@"
All done! ✨ 🍰 ✨
4 files would be left unchanged.
$ $PY -m flake8 "$@"; echo "exit $?"
exit 0
$ nice -n 15 $PY -m mypy --explicit-package-bases "$@"
Success: no issues found in 4 source files
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

flake8 and mypy report nothing on the four files, so there is no new
diagnostic to compare against `origin/main` (a run of mypy on the
`origin/main` copies from a scratch directory resolved `nexus` to the
installed package and is not a like-for-like comparison, so it is not cited).

### Red Controls (Planted, Run, Restored)

Plant A removes only the guard from `_run_check` (diff in
[red-unguarded-run-check.plant.diff.txt](red-unguarded-run-check.plant.diff.txt)).
`readiness.py` SHA-256 before and after restoring:
`491cd3a7c780aec66849b83a7d2375d4a664249c50b41060fa331fe35125c575`.

```text
$ nice -n 15 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_runtime/test_readiness.py -k "test_runner_reports_an_import_failure_as_a_failed_check or test_doctor_json_reports_a_broken_install"
>       __import__("nexus_803_absent_module")
E       ModuleNotFoundError: No module named 'nexus_803_absent_module'
...
E           File ".../nexus/runtime/readiness.py", line 1529, in _run_check
E           File ".../nexus/runtime/readiness.py", line 262, in _check_config
E         ModuleNotFoundError: No module named 'opentelemetry._events'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_runtime/test_readiness.py::test_runner_reports_an_import_failure_as_a_failed_check
FAILED tests/test_runtime/test_readiness.py::test_doctor_json_reports_a_broken_install
2 failed, 42 deselected in 0.77s
$ git checkout -- nexus/runtime/readiness.py; git diff --quiet -- nexus/runtime/readiness.py && echo "restored: git diff --quiet clean"
restored: git diff --quiet clean
```

Plant B swaps the `NEXUS_DESKTOP_CONFIG` and checkout branches of
`load_effective_desktop_config` (diff in
[red-precedence-swap.plant.diff.txt](red-precedence-swap.plant.diff.txt)).
`desktop_config.py` SHA-256 before and after restoring:
`f89f5cafa7f6f82e92d963c6f306b29009fad54b04c5c7d0e1cbdea642ed291c`.

```text
$ nice -n 15 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_runtime/test_desktop_config.py::test_lookup_follows_the_shell_order
>       assert (effective.source, effective.path) == ("NEXUS_DESKTOP_CONFIG", explicit)
E       AssertionError: assert ('checkout', ...esktop.json')) == ('NEXUS_DESKT...chosen.json'))
E         At index 0 diff: 'checkout' != 'NEXUS_DESKTOP_CONFIG'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_runtime/test_desktop_config.py::test_lookup_follows_the_shell_order
1 failed in 0.29s
$ git checkout -- nexus/runtime/desktop_config.py; git diff --quiet -- nexus/runtime/desktop_config.py && echo "restored: git diff --quiet clean"
restored: git diff --quiet clean
```

Full logs: [red-unguarded-run-check.log.txt](red-unguarded-run-check.log.txt),
[red-precedence-swap.log.txt](red-precedence-swap.log.txt).

### Focused PostgreSQL Proof

The order's set, split into two sequential sessions. `uptime` before each:
`load averages: 7.01 5.73 6.46` and `load averages: 17.95 9.38 7.78`; the
bounded wait loop (`until [ "$(sysctl -n vm.loadavg | awk '{print int($2)}')" -lt 24 ] || [ $n -ge 40 ]; do sleep 30; ...`) ran zero iterations both times.

```text
$ NEXUS_RUN_POSTGRES=1 nice -n 15 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings -p tests.dbname_audit tests/test_runtime/test_readiness.py tests/test_runtime/test_desktop_config.py tests/test_runtime/test_readiness_pg.py tests/test_api/test_runtime_status.py tests/test_runtime/test_supervisor.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 11 targets: postgres, qa640_1013_readiness_* x2, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
130 passed in 87.70s (0:01:27)

$ NEXUS_RUN_POSTGRES=1 nice -n 15 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings -p tests.dbname_audit tests/test_cli_contract.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 6 targets: postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:53161 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:53162 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:53161 (psycopg2), save_04@local:53162 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
205 passed, 2 skipped in 198.96s (0:03:18)
```

The two skips are the `requires_corpus` tests (`NEXUS_RUN_CORPUS` unset):
`pytest --co -m requires_corpus` on the same three files collects exactly
`2/207 tests collected (205 deselected)`. No `readiness803*` or
`qa640_1013_readiness*` database remained afterwards (checked with a
`pg_database` query). Logs: [integrated-pg-runtime.log.txt](integrated-pg-runtime.log.txt),
[integrated-pg-consumers.log.txt](integrated-pg-consumers.log.txt).

### Stub Reproduction After the Change

The same stub bytes as before (`manual-stub.py.txt`, SHA-256
`edd94fbb3018a0260d6e43a2deea97655a971cc4a1f33e5a7586168c6d33fc58`) as
`$M/stub/pydantic_ai/__init__.py`, run from `$M` with the before run's
allowlisted environment:

```text
$ env -i HOME=$HOME PATH=$PATH LANG=en_US.UTF-8 TMPDIR=$TMPDIR NEXUS_KEYRING_DISABLE=1 NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_TEST_RECEIPTS_DIR=$M/receipts PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$M/stub:$WT nice -n 15 $PY -m nexus.cli --json doctor --target ci-runner --config $WT/nexus.toml > $M/stdout.txt 2> $M/stderr.txt; echo "exit $?"
exit 1
stdout bytes: 856
Traceback in stderr: 0
--- stderr
❌ Error validating /Users/pythagor/nexus/.claude/worktrees/fix-803-s1/nexus.toml:
   No module named 'opentelemetry._events'
stdout parses as JSON
```

`config.valid` fails with `import of opentelemetry._events failed in
config.valid: No module named 'opentelemetry._events'` and the
`INSTALL_REMEDIATION` text; `reachability.gate` is `skip` (`config.valid
failed`). The loader's stderr line and its private failure receipt are
unchanged behavior (806-S1 owns the stderr print). Files:
[manual-after.stdout.txt](manual-after.stdout.txt),
[manual-after.stderr.txt](manual-after.stderr.txt),
[manual-after.receipt.jsonl.txt](manual-after.receipt.jsonl.txt).

### Live Owner-Client Doctor (Read-Only)

No listener on 8002 (`lsof -nP -iTCP:8002 -sTCP:LISTEN` printed nothing).
`NEXUS_KEYRING_DISABLE=1` was added as a safety bolt; the owner-client target
reads no secret.

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_DESKTOP_CONFIG -u NEXUS_DESKTOP_RUNTIME_ORIGIN NEXUS_KEYRING_DISABLE=1 PYTHONPATH=$PWD nice -n 15 $PY -m nexus.cli --json doctor --target owner-client
exit 1
config.valid             pass  /Users/pythagor/nexus/.claude/worktrees/fix-803-s1/nexus.toml (checkout)
gateway.reachable        fail  http://127.0.0.1:8002/runtime/status: [Errno 61] Connection refused
gateway.version          skip  gateway.reachable failed
desktop.config           pass  /Users/pythagor/nexus/.claude/worktrees/fix-803-s1/ui/src-tauri/nexus.desktop.json (checkout): http://127.0.0.1:8002/runtime/status
desktop.credentials      skip  gateway.reachable failed
desktop.runtime_command  pass  /Users/pythagor/.local/bin/poetry (via PATH) in /Users/pythagor/nexus/.claude/worktrees/fix-803-s1/ui/src-tauri/../..
```

(Rows condensed from the JSON; stderr was empty. Full report:
[live-owner-client.stdout.txt](live-owner-client.stdout.txt).)

### Packaging

```text
$ poetry --version
Poetry (version 2.1.2)
$ poetry check --lock
All set!
$ nice -n 15 poetry build -f wheel -o "$S/803-wheel"
Building nexus (0.1.0)
  - Building wheel
  - Built nexus-0.1.0-py3-none-any.whl
$ unzip -l $S/803-wheel/nexus-0.1.0-py3-none-any.whl > $S/wheel-listing.txt
 22037891                     567 files
      430  01-01-2016 00:00   ui/src-tauri/nexus.desktop.json
      192  01-01-2016 00:00   prompts/ambient_scene_seeds.md
      228  01-01-2016 00:00   prompts/correspondence/digest_retry.md
prompts/ members: 147
     8576  01-01-2016 00:00   nexus/runtime/desktop_config.py
$ rm -rf $S/803-wheel; git status --short; ls dist
ls: dist: No such file or directory
```

The desktop config sits at the wheel root beside `prompts/`, so an installed
package holds it at `repo_root() / "ui/src-tauri/nexus.desktop.json"`. The
wheel is deleted and the worktree is clean. Full listing:
[wheel-listing.txt](wheel-listing.txt).

### Reachability and Document Freshness

```text
$ PYTHONPATH=$PWD nice -n 15 $PY scripts/check_reachability.py
exit 0
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "unresolved_internal_imports": [],
  "unclassified_paths": [],
  "route_reachability": "not_proven"
$ nice -n 15 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed in 20.20s
```

Full generator output: [integrated-check-reachability.json.txt](integrated-check-reachability.json.txt).
`nexus/runtime/desktop_config.py` is in the baseline's production list (line 265).

### Coordinator's Steps

- The whole-tree PostgreSQL gate, and the order's offline whole-tree split
  (`tests --ignore=tests/test_api --ignore=tests/test_orrery`, then
  `tests/test_api tests/test_orrery`): the coordinator runs the whole tree.
- Landing, the gateway restart owed when the owner's services next run, and
  the PR body.
- No fleet migration, no state-surface regeneration, no `ui/` change, and no
  reinstall (`poetry.lock` is unchanged; `poetry check --lock` passes).

### Deferred (Known Residual)

For the bundled copy, a relative `workingDirectory` is anchored at the bundled
file's directory. The shell anchors its compiled copy at the build checkout
(`NEXUS_BUILD_CONFIG_DIR`, `lib.rs` `resolve_working_directory`) and refuses to
start when that checkout is absent. The shipped config uses `"workingDirectory":
"../.."`, so on a machine without a checkout the doctor resolves it under
`site-packages` and can pass all three `desktop.*` checks while the shell
cannot load its config. The check does not model that rule yet; the module
docstring of `nexus/runtime/desktop_config.py` records the same residual. The
PR body's Deferred section should carry it.

Claude Opus 5.5 (wave-B fixer)

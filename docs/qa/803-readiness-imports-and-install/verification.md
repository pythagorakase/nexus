# Readiness Imports and Desktop Install Checks

Status: S1/S7 implementation and authored tests are ready for source review;
green, after-reproduction, packaging and broader proof remain pending. The
two ordered S1 initial red cases and separate manual before reproduction
completed with the intended failures on tests-only head
`d9b26cfc6d7b95901b9a8e467ce1c9cdb556dc5d`, when product code was byte-identical
to main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. Initial evidence was
committed as `be88df8de6e4b9be3a49016e648c44562867b8f5` before any product
change. No green proof or publication readiness is claimed.

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

At load 11.662109375, Black completed over the four changed/new Python files:
two reformatted and two unchanged. The prescribed source-only reachability
generator completed with no findings and exactly one production-path
addition, `nexus/runtime/desktop_config.py`, plus the recorded reason. It
reports `route_reachability: not_proven`; no dynamic route proof is claimed.
Current actual canonical frontmatter declares none of these changed source
paths, so no freshness stamp is changed in this checkpoint. Recalculate
closure after predecessor landings rather than rewriting decision quotations.

## Remaining Proof

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

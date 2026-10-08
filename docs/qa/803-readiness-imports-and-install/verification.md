# Readiness Import Failure Tests-Only Checkpoint

Status: the two ordered 803-S1 initial red cases and separate manual before
reproduction completed with the intended failures on tests-only head
`d9b26cfc6d7b95901b9a8e467ce1c9cdb556dc5d`. Product code remains byte-identical to main
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. No passing proof, implementation
completion or publication readiness is claimed.

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

## Remaining Work

Implementation, green/after proof, mypy, wheel packaging, build, owner doctor,
broader tests and the final coordinated gate remain pending. No database
operation, service startup or paid call ran for this checkpoint.
The later implementation must preserve 806 receipts, 812 artifact checks,
822 registry entries and dynamic 803-S6 init-plan behavior on integration.
Its strict Rust u64 fields require both zero and `2**64 - 1` bounds; packaging
is one include entry with no lock/dependency change or installation.

Codex — GPT-6

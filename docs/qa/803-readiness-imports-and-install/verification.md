# Readiness Import Failure Tests-Only Checkpoint

Status: the two ordered 803-S1 regression tests are authored; their initial
red run and the manual before reproduction are pending coordinator admission.
Product code remains byte-identical to main
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

The initial proof will select exactly these two nodes with the shared
interpreter, exact worktree import admission, `nice -n 15`, load at most 24,
an overall 120-second deadline, disabled Keychain and all session guards.
Every initial failure will be inspected; a collection/setup/receipt failure
will not count as the intended red. Manual before/after CLI reproductions
must use fresh private scratch with the same stub and private receipt seam,
preserving the raw streams and exit status. The loader's existing stderr
diagnostic and receipt are part of that behavior, not removed by the fix.

No tests, manual CLI probes, mypy, wheel packaging, build, owner doctor,
database access, service startup or paid call has run for this checkpoint.
The later implementation must preserve 806 receipts, 812 artifact checks,
822 registry entries and dynamic 803-S6 init-plan behavior on integration.
Its strict Rust u64 fields require both zero and `2**64 - 1` bounds; packaging
is one include entry with no lock/dependency change or installation.

Codex — GPT-6

# Init Plan Source Checkpoint

Status: implementation and tests authored; behavioral proof is pending the
coordinator's serial test slot. This is not a passing-test or publication claim.
Base: `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`.

The plan projects the current owner-host readiness report in registry order,
retaining complete remediation strings and blocked check IDs. The CLI requires
`--plan` and provides no `--apply`. It retains both existing self-diagnostic
commands, `doctor` and `receipts`; invalid configuration still records the
existing diagnostic receipt. The tests isolate those receipts under `tmp_path`.
The production readiness registry is unchanged. PostgreSQL tests select their
own explicit eight-check subset and create healthy disposable stand-ins before
making any migration stamp stale or locking a clone.

Two independent source reviews found no blocking defect. No owner database,
gateway, Keychain or live owner-host readiness command was used.

Completed lightweight source preparation, with the shared interpreter and
`PYTHONPATH=$PWD` in this worktree:

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black nexus/cli.py nexus/cli_contract.py nexus/runtime/init_plan.py tests/test_runtime/test_init_plan.py tests/test_runtime/test_init_plan_pg.py
3 files reformatted, 2 files left unchanged.

nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m scripts.render_cli_reference --write
Wrote docs/cli_reference.md

nice -n 15 /Users/pythagor/nexus/.venv/bin/python scripts/check_reachability.py --write-baseline --reason '#803 S6: nexus/runtime/init_plan.py is imported by nexus/cli.py (run_init), so it joins production_reachable'
maintained: 399; production reachable: 219; no reported findings
```

The reachability baseline changes only its reason and the added production path
`nexus/runtime/init_plan.py`. Decision 0009 was reverified and restamped because
it declares `nexus/cli.py`; its body and quoted ruling are unchanged.

Pending: real focused PostgreSQL/CLI/receipt proof, required reverted sorting
control, plan samples, clone cleanup evidence, static diagnostics comparison,
freshness tests, current-main merge and regeneration, and coordinator integration
gate. No separate whole-suite or offline-suite result is claimed.

Deferred: `--apply` remains parked under 803-Q2. The existing `doctor`/`init`
transport label is `local_operator`, although owner-host checks open read-only
database sessions; the coordinator retains this mismatch for #817. Descriptive
copy says “applies no setup changes” to preserve #806 failure receipts without
changing the quoted owner ruling.

Codex — GPT-6

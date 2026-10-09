# Operator Inspection Source Checkpoint

Status: implementation authored; execution proof pending. This checkpoint is
not a passing focused or whole-suite gate and is not ready for publication.

## Scope and Provenance

The frozen order is `temp/orders_2026_10_07/815-S5.md`, with the shared rules
and the coordinator's `coord/cli-wave-b-refresh.md` adaptation. The branch is
`codex/815-operator-inspect`, based on main
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. This is a deliberate source-only
scheduling advance while the coordinator's shared PostgreSQL gate runs.
No shared ref was fetched or moved.

The live [#815 decisions](https://github.com/pythagorakase/nexus/issues/815#issuecomment-5915949407)
were read on 2026-10-08. Q3 keeps new operator reads local-only and preserves
the existing commands' remote behavior. Q4 assigns interactions inspection
to #787. This slice does not decide Q1's global success envelope transition
or #769's serving-boundary spoiler policy.

## Source Findings and Implementation

- The base CLI has seven story inspect verbs and no settings or secrets-status
  reader. Both operator GET routes already exist and are classified read-only,
  without provider effects, in `nexus/api/route_capabilities.py`.
- `nexus/api/settings_endpoints.py::_build_payload` returns the materialized
  raw sections plus `settings_meta`, dropping `secrets`. The new CLI reader
  returns that actual response unchanged after requiring an object and
  refusing a `secrets` key.
- `nexus/api/secrets_endpoints.py::SecretStatus` declares the six allowed
  fields; `_status_for` produces `last4`, and `get_secrets_status` optionally
  resolves slot pins. The new reader checks exact fields, Boolean `present`,
  null or at most four characters in `last4`, and exact `seat`/`model` fields
  in every `required_by` object before either output format sees the result.
- Reader-generated failures for a successful JSON body's invalid shape never
  interpolate body values. The frozen scope deliberately does not validate
  the string values of `provider`, `account`, `seat` or `model`, or broaden the
  existing non-2xx error-message behavior. It does not add a general-purpose
  redaction policy for arbitrary endpoint contents.
- `nexus/cli_contract.py` declares `operator_api` for the two new verbs and
  refuses it for either a remote runtime profile or a non-loopback API URL.
  The existing `clear`, `lock`, `unlock` and `model` flag transports remain
  unchanged. Settings takes no slot; secrets accepts an optional validated
  slot. The commands send only GET requests.
- `tests/test_cli_contract.py` adds real loopback entry-point cases for exact
  success bodies/queries, route capabilities, both remote causes, preserved
  lock/unlock behavior, value-free malformed-body errors in both output
  formats, invalid slot refusal, and text record separation.
- `tests/test_cli_inspect_pg.py` appends a real-gateway comparison using the
  private TEST config, a disposable `qa640_815s5_operator` clone, routed
  children, the in-memory secret store, and a stopped scheduler. The existing
  story-inspection test and its tables are unchanged. The sentinel in the
  authored tests is invented fixture data, not a stored credential.

Production changes are limited to `nexus/cli.py` and `nexus/cli_contract.py`.
The source search `rg -n 'nexus\.cli' nexus --glob '*.py'` finds only those
two files, so this CLI slice owes no gateway restart. There are no changes
to API handlers, route capabilities, migrations, `nexus.toml` or `ui/`;
no fleet application, UI build or surface regeneration
is required by these source changes.

## Canonical Documentation

A source-only scan of actual leading front matter on tracked Markdown files
finds one affected canonical document:
`docs/decisions/0009-dollars-in-the-ledger.md` declares `nexus/cli.py`.
`AGENTS.md` and `docs/turn_flow_sequence.md` declare none of this slice's
changed sources. Decision 0009 was reverified: `run_usage`, `_print_usage`,
`nexus/telemetry/usage.py::summarize_usage` and `[usage]` still report tokens
without a price table or dollar column. Its status, source list, body and
verbatim owner quotation are preserved; only `verified_commit` moves to the
main base above. The formal freshness test is pending.

The CLI guide preserves the #806 receipts paragraph. The generated reference
adds only the two verbs and their transport row. On the later main merge,
retain the pending #815 paging/spoiler paragraph, #815 review verbs, #803 init,
#812 model commands and #820 home progress changes; regenerate the reference
from the combined parser and recompute canonical closure and freshness.

## Completed Local Source Operations

Only permitted formatting, reference generation and normal commit hooks run
at this checkpoint; no pytest, mypy, PostgreSQL, gateway, browser, paid call,
model-folder operation or owner secret-store access has run for this slice.

With the exact worktree `PYTHONPATH`, shared interpreter, keyring disabled,
TEST-provider-only guard, and inherited `PYTEST_*`, `NEXUS_*` and libpq target
overrides cleared, one-minute load was 9.5380859375 for both commands:

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black nexus/cli.py nexus/cli_contract.py tests/test_cli_contract.py tests/test_cli_inspect_pg.py
reformatted tests/test_cli_inspect_pg.py
reformatted tests/test_cli_contract.py

All done! ✨ 🍰 ✨
2 files reformatted, 2 files left unchanged.

nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m scripts.render_cli_reference --write
Wrote /Users/pythagor/.codex/worktrees/resume-operator-inspect/nexus/docs/cli_reference.md
```

The generator was inspected before running: it walks the local parser and
contract and writes only `docs/cli_reference.md`; no command is dispatched.
An independent source review of both production diffs found no blocker
against the frozen order. It was a source review, not execution validation.

The first normal commit attempt passed catalog regeneration and configuration
validation but stopped at the exception-disposition hook. Changing the
existing `run_inspect` failure result to use optional `slot` invalidated its
baselined fingerprint:

```text
nexus/cli.py:1703: missing exception disposition: nexus/cli.py|run_inspect|99ad9d2727539f9676b732627bef9dd9d5ec69a8bf0e8c4e763ee8769752e534|1
nexus/cli.py:1: stale exception disposition baseline entry: nexus/cli.py|run_inspect|3556798c7fe27816b5e12d2fe4a86e5fdc7727e9d38389a03f8f370dc8950a02|1
```

The handler now explicitly declares `fail`: the failed read remains an error
result and exits 1 through the existing CLI envelope path. Exactly that one
stale baseline entry is removed; no entry is added and no error is suppressed.

## Deferred Proof and Controls

Request the shared heavy slot before any of these commands. Reconfirm exact
worktree imports, clean source head, current approved main, load at most 24,
and cleared runtime/libpq/pytest overrides. Run one session at a time with
the existing secret-store, owner-target and receipt-isolation guards.

```bash
NEXUS_RUN_POSTGRES=1 nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_cli_inspect_pg.py tests/test_cli_contract.py \
  tests/test_cli_reference_doc.py tests/test_api/test_route_capabilities.py \
  tests/test_api/test_secrets_endpoints.py tests/test_api/test_settings_endpoints.py \
  tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py \
  tests/test_connection_lifecycle.py

nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_reachability.py tests/test_doc_front_matter.py
```

Two source-restoring negative controls remain pending:

1. Set only the two new `COMMAND_TRANSPORTS` values to `http`. Run
   `tests/test_cli_contract.py::test_remote_runtime_refuses_operator_inspect_before_any_request`;
   require the four intended refusal assertions to fail, preserve the raw tail,
   and restore exact source bytes with before/planted/restored hashes.
2. Remove only the new `last4` check. Run
   `tests/test_cli_contract.py::test_inspect_secrets_refuses_an_unmasked_status_without_printing_it[full-last4]`;
   require that exact failure, preserve the raw tail, and restore exact source
   bytes and hashes. The existing remote operator-write guard has no red
   requirement because it protects behavior already present on main.

Also pending: Black check, generated reference check, exception-disposition
check against the then-approved main, and flake8/mypy comparisons on the four
changed Python files against their main versions. Use
`mypy --explicit-package-bases`; review diagnostics on changed lines, without
waiving new diagnostics based only on aggregate counts. The coordinator owns
the combined whole-suite gate and publication; this branch does not run
redundant full or offline partitions independently.

The frozen order requests fresh owner interaction row counts. The current
dispatch explicitly excludes owner database reads, so no such query was run
and no October 7 count is represented as current evidence. That proof remains
deferred for coordinator disposition. No interaction implementation depends
on it. The final signed #815 landing note and ready PR are coordinator-owned
after the later main merge and coordinated validation.

Codex — GPT-6

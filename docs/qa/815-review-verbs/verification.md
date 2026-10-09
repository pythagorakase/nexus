# Review Verbs Verification

## Scope and Checkpoint

Work order 815-S3 adds `nexus accept --slot N`, the developer verb that commits
the incubator draft through the existing player-plane approve route. `undo`
continues to discard the draft and reset its parent's choice. No migration,
configuration value, provider call, UI change, new success envelope, or API
route change is part of this slice. Refs #815.

This is a source checkpoint after the coordinator confirmed the initial red.
The focused green, static comparison, required document tests and combined
PostgreSQL gate are **pending**. It is not a validated publication checkpoint.

Tests were committed first at
`90c331ffc7e66c622e18ff55172e43deffe43acd`, tree
`8fbe81c005036d546c797089806c385de92ee4f4`, based on main
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The implementation was added
after the actual red run. No history was rewritten.

## Existing Behavior and Implementation

At that tests-only head, `build_parser` had no `accept` parser and
`COMMAND_TRANSPORTS` had no `accept` entry. The existing implementation is
`nexus/api/narrative.py:1315` (`POST /api/narrative/approve`): no pending draft
produces the 404 at line 1344; a committed answer carries `status` and `chunk_id`
at line 1411. `nexus/api/slot_endpoints.py:294` clears the parent choice in the
existing undo transaction. Those source paths remain unchanged.

`run_accept` posts only `slot` and `commit: true`, using the existing
`turn_request_timeout_seconds`. It accepts only `status == "committed"` and an
integer chunk ID, explicitly excluding booleans. Non-empty warnings are kept.
Existing HTTP helpers retain transport, access and malformed-answer failures.
The parser adds only the required slot argument; dispatch and slot validation
include the command. The legacy HTTP-handler AST coverage was already included
in the tests-first commit. The registry classifies accept as HTTP without
changing `ENVELOPE_COMMANDS`.

The settings edit describes the existing 120-second turn budget; it changes no
value or validation. `docs/cli.md` documents commit versus discard and the
timeout. `docs/cli_reference.md` was generated from this branch's parser.
Decision 0009 was re-read against `run_usage` and its telemetry implementation:
usage still reports tokens, with no price table or dollars column. Only its
freshness stamp advances to the branch's actual merge base `4ae8b8d2`; its
quote, source list, body, links and status are unchanged.

## Initial Red: Nine Missing-Command Failures

The coordinator ran the admitted proof at the exact tests-only head above.
The [raw result manifest](initial-red/results.json) records every argument,
environment name cleared, load, timeout, import path, exit code and log hash.
The [runner](initial-red/runner.py.txt), [complete log](initial-red/initial-red.txt),
[JUnit output](initial-red/initial-red.xml),
[import-path proof](initial-red/import-path.txt) and
[clone-cleanup read](initial-red/clone-cleanup-read-only.txt) are byte copies of
that run, not reconstructed evidence.

The runner used the shared interpreter with this worktree's `PYTHONPATH`,
`NEXUS_RUN_POSTGRES=1`, keyring disabled, provider-only protection, private
receipts, and the dbname audit. It selected all nine new cases, including the
boolean-ID case and both real-gateway PostgreSQL cases. Every failure was the
missing `accept` parser returning exit 2; there were no setup errors or skips.

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 3 targets: postgres, qa640_815_review_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_cli_contract.py::test_http_command_unanswered_request_exits_four[accept]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[accept-502]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[accept-html]
FAILED tests/test_cli_contract.py::test_accept_sends_slot_and_commit_and_reports_the_chunk
FAILED tests/test_cli_contract.py::test_accept_refuses_an_answer_without_a_chunk_id[not-committed]
FAILED tests/test_cli_contract.py::test_accept_refuses_an_answer_without_a_chunk_id[missing-id]
FAILED tests/test_cli_contract.py::test_accept_refuses_an_answer_without_a_chunk_id[bool-id]
FAILED tests/test_cli_review_pg.py::test_accept_commits_the_draft_and_keeps_the_parent_choice
FAILED tests/test_cli_review_pg.py::test_accept_without_a_draft_is_an_api_error
9 failed, 2 warnings in 14.58s
```

The post-run read returned `[]`: no `qa640_815_review` clone remained.

## Source Checkpoint Checks

With one-minute load 3.47 and explicit worktree `PYTHONPATH`,
`NEXUS_KEYRING_DISABLE=1` and `NEXUS_TEST_PROVIDER_ONLY=1`:

```bash
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black \
  nexus/cli.py nexus/cli_contract.py nexus/config/settings_models.py
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m scripts.render_cli_reference --write
git diff --check
```

Black left all three files unchanged; the generator wrote the reference, whose
only change is accept's transport membership and its slot-only command section;
the whitespace check passed. No tests, provider requests, gateway operations or
owner database operations were run for this implementation checkpoint.

## Remaining Proof and Landing

Run the ordered focused PostgreSQL proof, the CLI contract/reference,
reachability, prompt lint and canonical-document checks, then compare flake8
and mypy against the applicable main versions. The coordinator owns the serial
combined gate. Preserve 815-S2 range/spoiler additions, 820's type-only import
grouping and 812's model verbs when merging main; regenerate CLI reference
from the merged parser rather than resolving generated prose by hand.

The `nexus.toml` timeout comment remains deferred as ordered. The historical QA
script keeps its raw approve POST. There is no fleet application or UI rebuild;
the product-code restart is owed when owner services are next resumed.

Codex — GPT-6

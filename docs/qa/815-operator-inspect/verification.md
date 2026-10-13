# Operator Inspection Source Checkpoint

Status: the order's Proof Expected ran on the integrated wave-B tree on
2026-10-13 (see "Integrated-Tree Proof (2026-10-13)" at the end): the focused
PostgreSQL set is green with the live-gateway test passed, both red runs fail
as ordered, interactions hold 0 rows on save_01 to save_05, and Black, flake8,
mypy and the exception-disposition check show no new diagnostics. The
whole-tree PostgreSQL gate remains the coordinator's step. The sections before
that heading are the lane author's source-only record on base 4ae8b8d2, kept
with corrections marked.

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
verbatim owner quotation are preserved. Correction (2026-10-13): the lane
commit ad89b357 moved its `verified_commit` to 4ae8b8d2; the wave-B assembly
then moved it to f073b371 (origin/main), which is the stamp on the integrated
tree. On that tree, `tests/test_doc_front_matter.py` passes and a grep of
`nexus/telemetry/usage.py`, `run_usage`/`_print_usage` in `nexus/cli.py` and
`[usage]` in `nexus.toml` for dollar, price or USD finds nothing.

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
Correction (2026-10-13): both commands above ran on the lane's pre-merge
source in `/Users/pythagor/.codex/worktrees/resume-operator-inspect`, not on
the integrated tree; the integrated-tree Black check and reference check are
recorded at the end. The "independent source review" has no recorded command
or output; what is known is the Opus review of the integrated diff, whose
findings this record answers.

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

## Deferred Proof and Controls (Superseded)

Everything this section lists as pending ran on 2026-10-13; see the
integrated-tree proof below. The text is the author's original plan.

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

## Integrated-Tree Proof (2026-10-13)

Run by the 815-S5 fixer (Claude Opus 5.5) in worktree
`.claude/worktrees/fix-815-s5`, branch `claude/waveb-fix-815-s5`, cut from
the wave-B integration head 7eb9a10c (origin/main f073b371 plus fifteen
wave-B lanes, the 777 shell and a palette commit). Every command below ran on
commit 91b06277 (7eb9a10c plus the docs-only `docs/cli.md` rewrap) with a
clean tree except during the two plants. `$PY` is
`/Users/pythagor/nexus/.venv/bin/python`; every pytest run had
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset (`env -u`),
`PYTHONPATH=$PWD`, `nice -n 15` and `-p tests.dbname_audit`. The machine has no
`timeout` binary, so the harness's ten-minute limit bounded each command. The
one-minute load was between 4.4 and 11.1 before every run, below the cap of
24, so no load wait was needed. One pytest session ran at a time.

Import check:

```text
$ PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/fix-815-s5/nexus/__init__.py
```

### Focused PostgreSQL Set

Load before the run: `load averages: 10.06 9.17 9.39`. Port 8018 had no
listener.

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 \
    PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rA -p tests.dbname_audit \
    tests/test_cli_inspect_pg.py tests/test_cli_contract.py \
    tests/test_cli_reference_doc.py tests/test_api/test_route_capabilities.py \
    tests/test_api/test_secrets_endpoints.py tests/test_api/test_settings_endpoints.py \
    tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py \
    tests/test_connection_lifecycle.py
pytest exit 0
PASSED tests/test_cli_inspect_pg.py::test_continue_waits_then_inspect_reads_the_played_clone
PASSED tests/test_cli_inspect_pg.py::test_operator_inspect_reads_the_live_gateway_masked
SKIPPED [1] tests/test_api/test_secrets_endpoints.py:384: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_api/test_secrets_endpoints.py:395: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 9 targets: postgres, qa640_815_inspect_*, qa640_815s5_operator_*, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_offline_gate_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:52976 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:52992 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:52976 (psycopg2), save_04@local:52992 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
353 passed, 4 skipped, 9 warnings in 240.12s (0:04:00)
```

`test_operator_inspect_reads_the_live_gateway_masked` PASSED; it did not
skip. The four skips are gated by design: two need a paid live provider call
(`NEXUS_RUN_LIVE_LLM=1`) and two need owner-corpus clones
(`NEXUS_RUN_CORPUS=1`); neither is in this order's scope. After the run,
`psql -d postgres -Atc "select datname from pg_database where datname like
'qa640_815%'"` returned no rows.

### Red Run 1: Both Verbs Planted as `http`

```text
before:  0708a6b33c96fdd76a7c2c3098d08812871fddbdbdc4c26eac33e1e0fdd85bbe  nexus/cli_contract.py
$ sed -i '' -e 's/"inspect settings": "operator_api",/"inspect settings": "http",/' \
    -e 's/"inspect secrets": "operator_api",/"inspect secrets": "http",/' nexus/cli_contract.py
planted: 878d97bceac5e1c9e369a7812cdaa571aaa086ab96e287cd246bf83aa60941c3  nexus/cli_contract.py
-        "inspect settings": "operator_api",
-        "inspect secrets": "operator_api",
+        "inspect settings": "http",
+        "inspect secrets": "http",
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 \
    $PY -m pytest -q -p tests.dbname_audit \
    "tests/test_cli_contract.py::test_remote_runtime_refuses_operator_inspect_before_any_request"
pytest exit 1
>       assert completed.returncode == ExitCode.TRANSPORT_REFUSED, completed.stderr
E       AssertionError: {
E           "code": "api_unreachable",
E           "error": "Cannot connect to API server at https://nexus.example.invalid: HTTPSConnectionPool(host='nexus.example.invalid', port=443): Max retries exceeded with url: /api/secrets/status (Caused by NameResolutionError(\"<urllib3.connection.HTTPSConnection object at 0x10793c410>: Failed to resolve 'nexus.example.invalid' ([Errno 8] nodename nor servname provided, or not known)\"))",
E           "ok": false,
E           "partial": {}
E         }
E
E       assert 4 == <ExitCode.TRANSPORT_REFUSED: 3>
tests/test_cli_contract.py:1643: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_cli_contract.py::test_remote_runtime_refuses_operator_inspect_before_any_request[profile-settings]
FAILED tests/test_cli_contract.py::test_remote_runtime_refuses_operator_inspect_before_any_request[profile-secrets]
FAILED tests/test_cli_contract.py::test_remote_runtime_refuses_operator_inspect_before_any_request[api_url-settings]
FAILED tests/test_cli_contract.py::test_remote_runtime_refuses_operator_inspect_before_any_request[api_url-secrets]
4 failed in 4.02s
$ cp <scratch>/cli_contract.py.orig nexus/cli_contract.py
restored: 0708a6b33c96fdd76a7c2c3098d08812871fddbdbdc4c26eac33e1e0fdd85bbe  nexus/cli_contract.py
$ git diff --quiet -- nexus/cli_contract.py && echo clean
clean
```

All four cases fail with the plant. (A first attempt prefixed the pytest
command with `timeout 500`; the machine has no `timeout`, so pytest never ran
and the file was restored to the same hash before the run above.)

### Red Run 2: The `last4` Check Removed

```text
before:  f2869f82bb1a6344739fc9145c82a68c3b2f85238069e027b9601ae58c100fe9  nexus/cli.py
$ sed -i '' '1663,1668d' nexus/cli.py
planted: edac4b2cd9e67b30b4d21dda84b9f645653d41fbec2a40a72bf509c02846d98f  nexus/cli.py
-        if last4 is not None and not (isinstance(last4, str) and len(last4) <= 4):
-            raise InspectFailure(
-                "invalid_response",
-                f"GET /api/secrets/status record {i} carries more than the last four "
-                "characters of a key",
-            )
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 \
    $PY -m pytest -q -p tests.dbname_audit \
    "tests/test_cli_contract.py::test_inspect_secrets_refuses_an_unmasked_status_without_printing_it[full-last4]"
pytest exit 1
>               assert completed.returncode == ExitCode.DOMAIN_FAILURE
E               assert 0 == <ExitCode.DOMAIN_FAILURE: 1>
E                +  where 0 = CompletedProcess(args=['/Users/pythagor/nexus/.venv/bin/python', '-m', 'nexus.cli', 'inspect', 'secrets', '--json'], r...  "provider": "openai",\n      "required": false,\n      "required_by": []\n    }\n  ],\n  "ok": true\n}\n', stderr='').returncode
E                +  and   <ExitCode.DOMAIN_FAILURE: 1> = ExitCode.DOMAIN_FAILURE
tests/test_cli_contract.py:1714: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_cli_contract.py::test_inspect_secrets_refuses_an_unmasked_status_without_printing_it[full-last4]
1 failed in 1.18s
$ cp <scratch>/cli.py.orig nexus/cli.py
restored: f2869f82bb1a6344739fc9145c82a68c3b2f85238069e027b9601ae58c100fe9  nexus/cli.py
$ git diff --quiet -- nexus/cli.py && echo clean
clean
```

The first case fails: without the check, the full sentinel credential
passes through as `last4` with exit 0. `<scratch>` is
`scratchpad/fix-waveb-r2-815-S5/` in the coordinator session.

### Interaction Row Counts (Read-Only)

```text
$ for N in 1 2 3 4 5; do PGOPTIONS='-c default_transaction_read_only=on' \
    psql -d save_0$N -Atc 'SELECT count(*) FROM interactions'; \
    PGOPTIONS='-c default_transaction_read_only=on' \
    psql -d save_0$N -Atc 'SELECT count(*) FROM interaction_events'; done
save_01 interactions: 0  interaction_events: 0
save_02 interactions: 0  interaction_events: 0
save_03 interactions: 0  interaction_events: 0
save_04 interactions: 0  interaction_events: 0
save_05 interactions: 0  interaction_events: 0
```

The order's premise holds on 2026-10-13: there are no interaction rows to
inspect, so Decision 815-Q4 (inspection moves to #787) stands.

### Static Checks Against origin/main

The four files are `nexus/cli.py`, `nexus/cli_contract.py`,
`tests/test_cli_contract.py` and `tests/test_cli_inspect_pg.py`. The
origin/main (f073b371) versions came from
`git archive origin/main nexus tests scripts .flake8 pyproject.toml` extracted
to `<scratch>/main`, so flake8 reads the same `.flake8` there.

```text
$ nice -n 15 $PY -m black --check <four files>
All done! ✨ 🍰 ✨
4 files would be left unchanged.

$ nice -n 15 $PY -m flake8 <four files>            # HEAD 91b06277
nexus/cli.py:983:89: E501 line too long (92 > 88 characters)
nexus/cli.py:4486:89: E501 line too long (93 > 88 characters)
nexus/cli.py:4997:89: E501 line too long (113 > 88 characters)
nexus/cli.py:5026:89: E501 line too long (118 > 88 characters)
nexus/cli.py:5066:89: E501 line too long (90 > 88 characters)
nexus/cli.py:5151:89: E501 line too long (151 > 88 characters)
nexus/cli.py:5177:89: E501 line too long (94 > 88 characters)
nexus/cli.py:5178:89: E501 line too long (103 > 88 characters)
nexus/cli.py:5197:89: E501 line too long (101 > 88 characters)

$ (cd <scratch>/main && nice -n 15 $PY -m flake8 <four files>)   # origin/main
nexus/cli.py:981:89: E501 line too long (92 > 88 characters)
nexus/cli.py:4349:89: E501 line too long (93 > 88 characters)
nexus/cli.py:4845:89: E501 line too long (113 > 88 characters)
nexus/cli.py:4874:89: E501 line too long (118 > 88 characters)
nexus/cli.py:4914:89: E501 line too long (90 > 88 characters)
nexus/cli.py:4999:89: E501 line too long (151 > 88 characters)
nexus/cli.py:5025:89: E501 line too long (94 > 88 characters)
nexus/cli.py:5026:89: E501 line too long (103 > 88 characters)
nexus/cli.py:5045:89: E501 line too long (101 > 88 characters)

$ diff <(HEAD's nine flagged lines) <(main's nine flagged lines) && echo identical
flake8: the nine E501 lines are byte-identical on HEAD and origin/main
```

No new flake8 diagnostic: the nine E501 findings are on pre-existing lines
that 815-S5 and the other lanes did not touch; they only moved.

```text
$ nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/mypy_cache_head <four files>
Success: no issues found in 4 source files
$ (cd <scratch>/main && nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/mypy_cache_main <four files>)
Found 287 errors in 53 files (checked 4 source files)
  # 0 of them in the four files
$ git archive HEAD nexus tests scripts .flake8 pyproject.toml | tar -x -C <scratch>/head
$ (cd <scratch>/head && nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/mypy_cache_headx <four files>)
Found 286 errors in 53 files (checked 4 source files)
  # 0 of them in the four files
```

The in-worktree run reports nothing because the worktree lies under
`/Users/pythagor/nexus`, which the shared venv puts on `sys.path` through its
editable-install `.pth`, so mypy silences errors in the modules it follows.
The scratch exports are outside that path, so the followed modules report.
For a like-for-like comparison, both exports ran from outside the venv path.
Neither the origin/main nor the HEAD export has a diagnostic in the four
files. The 286-against-287 difference is in `nexus/api/setup_endpoints.py` and
`nexus/api/wizard_chat.py`, which other wave-B lanes changed. Pre-existing
diagnostics: the nine flake8 E501 lines above; none from mypy in the four
files.

```text
$ nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
exit 0
$ PYTHONPATH=$PWD nice -n 15 $PY -m scripts.render_cli_reference --check
exit 0
```

This lane's only baseline change is the removal of
`nexus/cli.py|run_inspect|3556798c…|1`; the handler now carries
`# nexus-exception-disposition: fail; reason=read; safety=exit 1`
(`nexus/cli.py:1724`).

Restart grep (product code does not reach the API process):

```text
$ grep -rn "nexus\.cli\b\|from nexus import cli\|nexus\.cli_contract" nexus --include='*.py' \
    | grep -v "^nexus/cli.py:\|^nexus/cli_contract.py:"
(no output)
```

The lane diff (917cc1d5..8d2e4999) touches no migration, `nexus.toml` or
`ui/` file, so no fleet application, gateway restart, UI rebuild or
state-surface regeneration is owed by this lane.

### Offline Suites

The order's two offline commands were split into groups so that each command
stays under ten minutes. The 144 top-level `tests/test_*.py` files, in `ls`
order, went into five groups (aa: `test_backfill_review_packet.py` to
`test_entity_reference_parity_pg.py`; ab: `test_entity_tag_manifest_apply.py`
to `test_name_reveal_staged_bindings_pg.py`; ac:
`test_name_reveal_staged_bindings.py` to `test_prompt_lint.py`; ad:
`test_prompt_tag_vocabulary_pg.py` to `test_trait_compiler_integration.py`;
ae: `test_trait_compiler.py` to `test_world_clock_contract_pg.py`). The
subdirectories ran together (`tests/test_config tests/test_ir_eval_v2
tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts
tests/test_util tests/proofs`), then `tests/test_api`, then
`tests/test_orrery`. Each ran as
`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit <group>`.
Every tail shows `secret-store guard: active; nexus-api: denied; disposable
keychain: denied` and `dbname audit: owner targets: none`.

```text
aa      677 passed, 107 skipped, 2 warnings in 349.14s (0:05:49)
ab      171 passed, 119 skipped, 3 warnings in 31.99s
ac      630 passed, 148 skipped, 2 warnings in 33.77s
ad      2 failed, 528 passed, 167 skipped, 2 warnings in 69.49s (0:01:09)
ae      1 failed, 143 passed, 39 skipped, 2 warnings in 6.05s
dirs    2 failed, 905 passed, 89 skipped, 7 warnings in 146.35s (0:02:26)
api     2 failed, 547 passed, 330 skipped, 7 warnings in 33.01s
orrery  9 failed, 1349 passed, 1187 skipped, 2 warnings in 13.59s
```

None of the 16 failures is in a file or path this lane changes. They belong to
other wave-B lanes and go to the coordinator for triage:

- `tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module`:
  `tests/test_orrery/test_place_point_required_pg.py:11` (added by ed5ce5a4,
  merged with 840-S2) and `tests/test_runtime/test_init_plan_pg.py:23`
  (merged with 803-S6) bind a wrapper module.
- `tests/test_skald_wire.py::test_wire_schema_size_and_description_budget`:
  `NewEntityDeclaration.coordinates` description is over budget (ed5ce5a4,
  840-S2).
- `tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged`
  (gaia fingerprint changed) and
  `tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained`
  (`assert 732 < 700`): `prompts/storyteller_gaia.md` changed in ed5ce5a4
  (840-S2).
- `tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp`
  and `tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]`
  and `[setting_confirmed]`: "Unit test attempted psycopg2.connect; mark it
  requires_postgres" (the wizard path changed in the wave-B tree; the
  confirmation tests were last touched by the 776-S3 merge).
- `tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy`
  and eight `tests/test_orrery/test_worker.py` tests: settings validation errors
  (`claim_event_types contains event types emitted by background branches`,
  `orrery.projects.milestone_magnitude must be >= orrery.promote.magnitude_threshold`);
  `nexus/orrery/worker.py` and the tests were changed by dec6f76c (809-S1).

`tests/test_reachability.py` and `tests/test_doc_front_matter.py` also ran
alone:

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 \
    $PY -m pytest -q -p tests.dbname_audit tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
120 passed in 18.76s
```

### Coordinator's Steps

- The whole-tree PostgreSQL gate on the final integration head.
- `npm --prefix ui run resolve-state-surfaces` (this lane changes no `ui/`
  file).
- Fleet migrations (this lane has none).
- The two `NEXUS_RUN_LIVE_LLM=1` cases in `tests/test_api/test_secrets_endpoints.py`
  (paid provider calls) and the two `NEXUS_RUN_CORPUS=1` cases in
  `tests/test_orrery/test_card_identity.py`.
- The #815 landing note (settings and secrets-status verbs landed local-only
  under Decision 815-Q3; queues stay with `nexus jobs --slot N --json`;
  interactions moved to #787 under Decision 815-Q4).

### Review Findings Answered

- Proof pending (P1/P2, four findings): answered by the runs above.
- `docs/cli.md` overwide lines (P3, two findings, one defect): commit 91b06277
  rewraps the paragraphs at 146-159 and 165-169 to at most 78 columns. A
  word-sequence diff of the whole file against its parent (`tr -s ' \n'
  '\n\n'` on both sides, then `diff`) is empty, so the wording is unchanged.

Claude Opus 5.5 (fixer)

# Verification Record: 776-S1a

## Disposition and Scope

Completed the frozen order with Amendment 1, retaining the partial work from
original commit `443ec076` (rebased as `4a175e61`, without squash or amendment).
The implementation commit is `7e598ada`; the final evidence commit also contains
only an explicit expansion-output dictionary copy, local import ordering, and
the migration header's verified pre-change base reference. The branch is
`claude/776-genesis-run-ledger`, rebased onto `origin/main` at `5b977eab`.
Migration 139 and migration 140 are now on that base. Migration 141 is this
slice's only new migration; `KNOWN_GAPS` is unchanged.

The dedicated PostgreSQL proof passes all 331 tests with the secret-store guard
active and `dbname audit: owner targets: none`. The UI suite passes 161 tests,
and TypeScript/design-preview checks pass. The final offline gates pass except
for one initial CLI timing assertion in an unchanged file, which passed on a
full-file rerun; both results are retained below for coordinator triage. Whole-tree
PostgreSQL qualification at the final commit is the coordinator's job under the
2026-10-01 Codex-specific working rules and was not run here.

Every command ran from this worktree. The shared interpreter imported this
worktree's package. No gateway was started, no paid-provider opt-in was set,
and offline tests retained the TEST-provider-only and secret-store guards.
Generation proofs replace only the ordered provider boundaries; the real cache,
packet builder, mapper, connection pool, ledger, migrations, and route run.
No save database or NEXUS_template was written. The owner listing used explicit
read-only transactions; only disposable clones were migrated or dropped.
This qualifies storage and client protocol behavior, not live paid inference.

## Current Behavior and Evidence

All current line references below are to the final source in this branch.
The pre-change references name `5b977eab`, not the order's stale line numbers.

| Claim | Implementation and Proof |
| --- | --- |
| Run identity and stages survive another worker/process. | `retrograde_orchestrator.py:118-158` commits own-connection run/stage writes; `:209-257` reads the latest run. `test_genesis_ledger_pg.py:152-210` runs a real thread and a separately routed Python process, observing this run at packet/running. |
| Successful stage outputs survive a later refusal. | `retrograde_orchestrator.py:160-170,306-307,322-323,344-346`; `new_story_flow.py:553-573` saves derivation (SQL NULL when absent). `test_genesis_ledger_pg.py:72-92` asserts saved packet, seeds, expansion and closed stages after mapper refusal. |
| Every raised transition exception records failure at its current stage, including no stage. | `new_story_flow.py:504-505,699-701`; ledger failure at `retrograde_orchestrator.py:173-183`. Parametrized real-route proof at `test_genesis_ledger_pg.py:95-149` covers derivation, packet, seeds, expansion, persistence and NULL stage, matching the raised error text. |
| Persistence output and skipped completion share the world transaction. | `new_story_flow.py:590-592,639-661`; caller-cursor writers at `retrograde_orchestrator.py:186-206`. `test_genesis_ledger_pg.py:225-237` proves rollback leaves persistence open and commit closes it; `:213-222` commits the real skipped TEST world and its done/mock_wizard_model run. |
| Missing/finished runs and invalid stages fail loudly. | Checked row-count guard at `retrograde_orchestrator.py:104-107`; vocabulary validation at `:136-137`. `test_genesis_ledger_pg.py:240-258` asserts ValueError/RuntimeError and no extra stage insert. |
| Any gateway worker reads the durable record off the event loop. | `wizard_chat.py:1427-1451` uses `asyncio.to_thread`, returns run_status/error and no-run nulls; player-projection proof in `test_route_capabilities.py:215-240` routes slot 4 through offline_gate_db, never slot 5. |
| A ready wizard attaches only to a running run on mount, then opens the story on completion. | `InteractiveWizard.tsx:681-740`; shared `openStory` at `:530-575`; polling at `:107-137`. Transition tests at `InteractiveWizard.transition.test.tsx:517-591` cover running/done, failed/Retry, read error/Cancel, derivation with all pips dim, terminal mount records and skipped completion. |
| Detach/unmount aborts reads, polling and bootstrap; no completion after abort. | Controller cleanup at `InteractiveWizard.tsx:308-311,739`; Cancel at `:786-802`; completion guard at `:554-556`. Transition tests at `:485-515,607-622` cover pending mount read, running poll and bootstrap unmount. |
| Status metadata is validated before rendering. | `narrative-api.ts:290-297,336-344`; API tests include missing run_status and inconsistent run/error combinations. |
| Completed ledger rows are retained; fingerprint/session fields are deferred. | Migration 141 at `:21-65` contains both tables and comments, and no deletion path is added. TEST-world proof `test_genesis_ledger_pg.py:221` asserts input_fingerprint/opening_session_id remain NULL. Catalog below shows retention schema and comments. |

Only `resumeData.current_phase === "ready"` gets the mount read. Terminal records
at the mount read leave the artifact review in place. A run that settles after
attachment displays its failure or composes the existing bootstrap POST. The
poller's previous-run branch never settles on the prior run's terminal record.
Confirm's callback now follows isLoading, and onComplete is kept in a ref so a
parent artifact update cannot restart the mount effect and abort its controller;
`WizardShell.test.tsx:139-169` exercises that parent flow.

## Verified Pre-Change Premises

At pre-change base `5b977eab`, the process registry was
`retrograde_orchestrator.py:61-62`, its writer `:97-124`, reader `:127-146`, and
reset `:149-166`; `wizard_chat.py:1427-1444` returned idle/run-null from that
process-local reader. Packet/seeds/expansion only lived in the returned bundle
(`retrograde_orchestrator.py:196-256`), and derived inputs only in transition_data
(`new_story_flow.py:535-557,599-614`; unchanged `trait_input_derivation.py:343-374`).
Only persistence and embedding explicitly wrote failed
(`new_story_flow.py:628-648`); persistence was emitted inside the transaction hook
(`retrograde_orchestrator.py:290`). The retry docstring used the undefined
clean-slate preamble at `new_story_flow.py:468-472`.

The old UI polled only inside performTransition (`InteractiveWizard.tsx:521-660`,
first read `:551`, failure stage update `:589`), while Cancel only aborted its
client request (`:706-722`). The transition route still runs in a worker thread
(`wizard_chat.py:1393`). The process-local operating note at pre-change
`nexus.toml:730-732` is deleted; the poll setting is unchanged at current `:729`.

World commit and cache clearing remain at current
`new_story_db_mapper.py:694-701`. Cache presence defines wizard mode at unchanged
`slot_state.py:113-116`; this is why post-world-commit reattach is outside S1a.

## Amendment 1 and Deferred Finding

The staged fixture sets ready_for_transition=True and validated=True at
`tests/test_orrery/test_retrograde_wizard_live.py:261-262`.
`TransitionData.validate_completeness` at current
`nexus/api/new_story_schemas.py:1367-1404` recomputes readiness only when every
required field is present; with a missing field it returns the previously set
flag. Therefore the amended refusal proofs copy the staged transition with
`zone=None, ready_for_transition=False, validated=False`
(`test_genesis_ledger_pg.py:75-77,124-126`). This reaches the intended real mapper
refusal at `new_story_db_mapper.py:525-542` before any world write, with
`ValueError("Transition data is incomplete. Missing: zone")`.

**Deferred for the coordinator to file:** a transition whose readiness was set
earlier and whose required field was later cleared passes that guard and fails
inside the world transaction with AttributeError (`new_story_db_mapper.py:175`).
The validator should recompute the flag in both branches under loud-failure
doctrine. Neither validator, mapper, nor staging fixture is changed in S1a.
The accepted stop-report's reproduction and original failure stack remain below.

Other deferrals required by the order:

- A run whose gateway dies stays running and the wizard reattaches until Cancel;
  run ownership/single-open-run/idempotency and output reuse belong to S1b/Q5.
- A reload after world commit (embedding through bootstrap POST) is not attached
  because clear_cache ends wizard mode, so this wizard never mounts; S2 owns it.
- Derivation keeps idle/no pip, and RETROGRADE_STAGES/WaitScreen are unchanged.
- The UI still composes bootstrap, pendingBootstrapSession remains the existing
  handoff, and opening_session_id is NULL. S2 converts every bootstrap caller.
- No fingerprint writes, transcript cutover, hosted-thread discard, wizard-cache
  migration, CLI workflow changes or paid live front-door qualification.

## Read-Only Owner Wizard Listing and Migrated Clone Catalog

Command (TEST-only; the script calls conn.set_session(readonly=True) for every
owner read, rolls back, then invokes disposable_slot_database for catalog work):

```sh
PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_KEYRING_DISABLE=1 TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/catalog_evidence.py > /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/catalog.log 2>&1
```

```text
Snapshot at 2026-10-01T07:36:57.748460+00:00
Owner read-only session: ('save_01', 'on')
save_01 assets.new_story_creator: []
Owner read-only session: ('save_02', 'on')
save_02 assets.new_story_creator: []
Owner read-only session: ('save_03', 'on')
save_03 assets.new_story_creator: []
Owner read-only session: ('save_04', 'on')
save_04 assets.new_story_creator: []
Owner read-only session: ('save_05', 'on')
save_05 assets.new_story_creator: [('conv_6ab3f072abc081948e94e1f5c8b8c0be000d0e6233839786', 5, True, False, datetime.datetime(2026, 9, 23, 18, 4, 12, 670662, tzinfo=datetime.timezone.utc))]
Migrated disposable clone: qa640_776_catalog_dd5c8f289413
Migration stamp: [('141',)]
                                                                                                                                   Table "public.genesis_runs"
       Column       |           Type           | Collation | Nullable |      Default      | Storage  | Compression | Stats target |                                                                          Description
--------------------+--------------------------+-----------+----------+-------------------+----------+-------------+--------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------
 run_id             | uuid                     |           | not null |                   | plain    |             |              | Attempt UUID minted by start_genesis_run; API callers use its 32-character hex form.
 status             | text                     |           | not null |                   | extended |             |              | Operational running, failed or done state written by start_genesis_run, record_retrograde_progress, record_genesis_failure and finish_skipped_genesis_run.
 stage              | text                     |           |          |                   | extended |             |              | Last entered genesis stage, NULL before the first stage; record_retrograde_progress writes it and record_genesis_failure preserves it.
 skip_reason        | text                     |           |          |                   | extended |             |              | Reason Retrograde was skipped, written with the world by finish_skipped_genesis_run.
 error              | text                     |           |          |                   | extended |             |              | Raised exception type and text for a failed attempt, written by record_genesis_failure.
 input_fingerprint  | text                     |           |          |                   | extended |             |              | NULL in S1a; 776-S1b writes the whole-run input fingerprint for safe output reuse.
 opening_session_id | uuid                     |           |          |                   | plain    |             |              | NULL in S1a; a later #776 slice writes the gateway-owned opening generation session UUID.
 started_at         | timestamp with time zone |           | not null | clock_timestamp() | plain    |             |              | Operational wall-clock attempt start, defaulted by the start_genesis_run insert; never story time.
 updated_at         | timestamp with time zone |           | not null | clock_timestamp() | plain    |             |              | Operational wall-clock latest run-state write by start_genesis_run, record_retrograde_progress, record_genesis_failure or finish_skipped_genesis_run.
 finished_at        | timestamp with time zone |           |          |                   | plain    |             |              | Operational wall-clock completion or failure, NULL while running; record_retrograde_progress, record_genesis_failure or finish_skipped_genesis_run writes it.
Indexes:
    "genesis_runs_pkey" PRIMARY KEY, btree (run_id)
Check constraints:
    "genesis_runs_check" CHECK ((status = 'running'::text) = (finished_at IS NULL))
    "genesis_runs_check1" CHECK ((status = 'failed'::text) = (error IS NOT NULL))
    "genesis_runs_check2" CHECK (skip_reason IS NULL OR status = 'done'::text)
    "genesis_runs_stage_check" CHECK (stage = ANY (ARRAY['derivation'::text, 'packet'::text, 'seed_candidates'::text, 'expansion'::text, 'persistence'::text, 'embedding'::text, 'done'::text]))
    "genesis_runs_status_check" CHECK (status = ANY (ARRAY['running'::text, 'failed'::text, 'done'::text]))
Foreign-key constraints:
    "genesis_runs_opening_session_id_fkey" FOREIGN KEY (opening_session_id) REFERENCES narrative_generation_sessions(session_id)
Referenced by:
    TABLE "genesis_run_stages" CONSTRAINT "genesis_run_stages_run_id_fkey" FOREIGN KEY (run_id) REFERENCES genesis_runs(run_id) ON DELETE CASCADE
Access method: heap


                                                                                                                             Table "public.genesis_run_stages"
   Column    |           Type           | Collation | Nullable |      Default      | Storage  | Compression | Stats target |                                                                          Description
-------------+--------------------------+-----------+----------+-------------------+----------+-------------+--------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------
 run_id      | uuid                     |           | not null |                   | plain    |             |              | Owning attempt UUID written by record_retrograde_progress; links the stage to genesis_runs.
 stage       | text                     |           | not null |                   | extended |             |              | Entered genesis stage name written by record_retrograde_progress; unique per attempt.
 detail      | jsonb                    |           | not null | '{}'::jsonb       | extended |             |              | Player progress detail for the stage, written by record_retrograde_progress.
 output      | jsonb                    |           |          |                   | extended |             |              | Stage output saved by record_genesis_stage_output or finish_genesis_persistence; SQL NULL means no output value.
 started_at  | timestamp with time zone |           | not null | clock_timestamp() | plain    |             |              | Operational wall-clock stage entry, defaulted by record_retrograde_progress; never story time.
 finished_at | timestamp with time zone |           |          |                   | plain    |             |              | Operational wall-clock stage close, written by record_retrograde_progress, record_genesis_stage_output, record_genesis_failure or finish_genesis_persistence.
Indexes:
    "genesis_run_stages_pkey" PRIMARY KEY, btree (run_id, stage)
Check constraints:
    "genesis_run_stages_stage_check" CHECK (stage = ANY (ARRAY['derivation'::text, 'packet'::text, 'seed_candidates'::text, 'expansion'::text, 'persistence'::text, 'embedding'::text, 'done'::text]))
Foreign-key constraints:
    "genesis_run_stages_run_id_fkey" FOREIGN KEY (run_id) REFERENCES genesis_runs(run_id) ON DELETE CASCADE
Access method: heap


Disposable catalog clone dropped by fixture.
```

The owner query was:

```sql
SELECT current_database(), current_setting('transaction_read_only');
SELECT thread_id, target_slot, setting_genre IS NOT NULL AS setting_present,
       seed_type IS NOT NULL AS seed_present, updated_at
FROM assets.new_story_creator ORDER BY id;
```

The column tuple is (thread_id, target_slot, setting_present, seed_present,
updated_at). Only save_05 has a cached incomplete wizard, matching the owner's
identified hosted-thread setup. Affected wizard slots: **none**; save_05's cache
is untouched. The coordinator must recheck every slot for the later cutover
slice; this snapshot is not permission to discard it.

The catalog is captured before the final rebase; the final PostgreSQL proof
creates new disposable clones with migration 140 and 141 on the final base.
Both ledger table definitions are unchanged across that rebase. The helper uses
the canonical migration runner and drops the clone in its finally block.

## Commands and Verbatim Tails

Long pytest gates ran under the scratch run_gate.py wrapper, which uses
subprocess.run(timeout=590), waits for completion, and preserves the subprocess
exit code. Each tail below comes from its named log. No background command was
left running. Gateway lane variables were unset throughout these gates.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/776-genesis-run-ledger/nexus/__init__.py
```

### Final PostgreSQL Proof (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/proof-final.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_mock_wizard_responses.py tests/test_orrery/test_retrograde_orchestrator.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_owner_target_guard.py --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-final
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: nexus_m10_fresh_test_19757, nexus_m10_template_test_19757, nexus_test_issue_613_*, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_offline_gate_* x12, qa640_renamed_test_model_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
331 passed, 7 warnings in 47.69s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Final Offline Coverage

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/offline-rest-final.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore-glob='tests/test_cli*.py' --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-offline-rest-final
```

```text
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2381 passed, 456 skipped, 8 warnings in 167.62s (0:02:47)
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/offline-api-orrery-final.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-offline-api-orrery-final
```

```text
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1824 passed, 758 skipped, 7 warnings in 33.36s
```

The CLI subset is unchanged by the final rebase. Its initial failure is not
hidden or reclassified as an exempt slot-5 failure:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/offline-cli.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_cli*.py --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-offline-cli
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_cli_session_wait.py::test_wait_times_out_while_the_session_still_runs
1 failed, 350 passed, 1 skipped, 5 warnings in 246.74s (0:04:06)
```

Failure tail:

```text
_______________ test_wait_times_out_while_the_session_still_runs _______________

api_url = <function api_url.<locals>.point at 0x10de7b880>

    def test_wait_times_out_while_the_session_still_runs(api_url) -> None:
        """The overall budget ends a wait on a session that never finishes."""
        session = Session(statuses=["initiated"])
        with _gateway(session) as base_url:
            api_url(base_url)
            started = time.monotonic()
            with pytest.raises(cli.SessionWaitFailure) as caught:
                cli.wait_for_session(SESSION, slot=5, timeout=0.5, interval=0.1)
            elapsed = time.monotonic() - started

        assert (caught.value.status, caught.value.code) == ("timeout", "domain_failure")
>       assert caught.value.detail == "Generation timed out"
E       AssertionError: assert 'Generation t...r within 0.5s' == 'Generation timed out'
E
E         - Generation timed out
E         + Generation timed out: no status answer within 0.5s

tests/test_cli_session_wait.py:242: AssertionError
```

No code/test was changed for that timing assertion. The entire file passed
on a focused rerun (exit 0):

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/offline-cli-wait-rerun.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_cli_session_wait.py --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-cli-wait-rerun
```

```text
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
27 passed, 5 warnings in 31.48s
```

### Reachability and Focused Output-Callback Proof

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-reachability
```

```text
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 9.69s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_retrograde_orchestrator.py --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-output-copy
```

```text
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
10 passed, 5 warnings in 0.84s
```

The reachability tests also ran in the final offline-rest gate. The focused
callback run followed the final explicit dict(expansion_plan) copy.

### UI Build and Tests

```sh
npm --prefix ui ci
```

```text
added 957 packages, and audited 958 packages in 3s

27 vulnerabilities (2 low, 8 moderate, 16 high, 1 critical)

To address issues that do not require attention, run:
  npm audit fix

To address all issues (including breaking changes), run:
  npm audit fix --force

Run `npm audit` for details.
```

```sh
npm --prefix ui test -- src/components/NewStoryWizard src/lib/narrative-api.retrograde.test.ts
```

```text

 Test Files  8 passed (8)
      Tests  161 passed (161)
   Start at  02:36:28
   Duration  5.38s (transform 657ms, setup 369ms, collect 1.96s, tests 6.02s, environment 2.29s, prepare 326ms)
```

```sh
npm --prefix ui run check
```

```text

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
```

### Formatting, Comments, Lint and Types

```sh
/Users/pythagor/nexus/.venv/bin/python -m black nexus/agents/orrery/retrograde_orchestrator.py nexus/api/new_story_flow.py nexus/api/wizard_chat.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_orrery/test_retrograde_orchestrator.py
```

```text
All done! ✨ 🍰 ✨
7 files left unchanged.
```

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
```

Whole-file flake8 exits 1 on 22 existing warnings (unchanged source lines in
new_story_flow and wizard_chat); whole-file mypy exits 1 on 34 existing errors
in those same files. These are **not claimed green**. Exact source-line and
diagnostic multisets match the origin/main snapshot; no new lint/type diagnostic
was introduced, and no out-of-scope cleanup was performed. The baseline files
were exported with git show into this order's scratch directory. They are
identical at d05481d8 and 5b977eab for all six baseline files.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/agents/orrery/retrograde_orchestrator.py nexus/api/new_story_flow.py nexus/api/wizard_chat.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_orrery/test_retrograde_orchestrator.py
```

```text
nexus/api/new_story_flow.py:12:1: F401 'pathlib.Path' imported but unused
nexus/api/new_story_flow.py:725:89: E501 line too long (100 > 88 characters)
nexus/api/new_story_flow.py:731:89: E501 line too long (90 > 88 characters)
nexus/api/new_story_flow.py:753:89: E501 line too long (94 > 88 characters)
nexus/api/wizard_chat.py:25:1: F401 'nexus.api.config_utils.get_new_story_model' imported but unused
nexus/api/wizard_chat.py:95:89: E501 line too long (136 > 88 characters)
nexus/api/wizard_chat.py:378:89: E501 line too long (108 > 88 characters)
nexus/api/wizard_chat.py:398:89: E501 line too long (101 > 88 characters)
nexus/api/wizard_chat.py:403:89: E501 line too long (92 > 88 characters)
nexus/api/wizard_chat.py:418:89: E501 line too long (93 > 88 characters)
nexus/api/wizard_chat.py:486:89: E501 line too long (100 > 88 characters)
nexus/api/wizard_chat.py:490:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:522:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:569:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:876:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:885:89: E501 line too long (97 > 88 characters)
nexus/api/wizard_chat.py:904:89: E501 line too long (89 > 88 characters)
nexus/api/wizard_chat.py:913:89: E501 line too long (92 > 88 characters)
nexus/api/wizard_chat.py:1130:89: E501 line too long (91 > 88 characters)
nexus/api/wizard_chat.py:1163:89: E501 line too long (93 > 88 characters)
nexus/api/wizard_chat.py:1327:89: E501 line too long (94 > 88 characters)
nexus/api/wizard_chat.py:1412:89: E501 line too long (91 > 88 characters)
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m mypy --follow-imports=silent --ignore-missing-imports --explicit-package-bases --no-error-summary --hide-error-context nexus/agents/orrery/retrograde_orchestrator.py nexus/api/new_story_flow.py nexus/api/wizard_chat.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_orrery/test_retrograde_orchestrator.py
```

```text
nexus/api/wizard_chat.py:993: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:996: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:1005: error: Argument "thread_id" to "from_request" of "WizardContext" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:1015: error: Argument 1 to "build_message_history" has incompatible type "list[Message]"; expected "Sequence[dict[str, Any]]"  [arg-type]
```

The initial mypy invocation without explicit package bases/untype-library
handling stopped at the environment/module-path errors (exit 2):

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m mypy --follow-imports=silent nexus/agents/orrery/retrograde_orchestrator.py nexus/api/new_story_flow.py nexus/api/wizard_chat.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_orrery/test_retrograde_orchestrator.py
```

```text
nexus/api/wizard_chat.py:19: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
nexus/api/wizard_chat.py:19: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
tests/test_orrery/__init__.py: error: Source file found twice under different module names: "test_orrery" and "tests.test_orrery"
Found 2 errors in 2 files (errors prevented further checking)
```

The same adjusted baseline command used --shadow-file for each original file;
exact command saved at /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/mypy-baseline-command.txt. Its diagnostic summary is:

```text
nexus/api/new_story_flow.py:738: error: Incompatible return value type (got "dict[int, str]", expected "dict[str, str]")  [return-value]
nexus/api/wizard_chat.py:312: error: No overload variant of "run" of "AbstractAgent" matches argument types "str", "WizardContext", "list[Any]", "Any", "ModelSettings"  [call-overload]
nexus/api/wizard_chat.py:352: error: Item "None" of "WizardCache | None" has no attribute "confirmation_metadata"  [union-attr]
nexus/api/wizard_chat.py:409: error: Incompatible types in assignment (expression has type "str", variable has type "Literal['setting', 'character', 'seed'] | None")  [assignment]
nexus/api/wizard_chat.py:563: error: Argument "model" to "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:565: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:599: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:601: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:602: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:606: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:612: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:621: error: Argument "thread_id" to "from_request" of "WizardContext" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:631: error: Argument 1 to "build_message_history" has incompatible type "list[Message]"; expected "Sequence[dict[str, Any]]"  [arg-type]
nexus/api/wizard_chat.py:653: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:682: error: Argument "thread_id" to "_handle_accept_fate_traits" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:685: error: Argument 3 to "_artifact_response" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:694: error: No overload variant of "run" of "AbstractAgent" matches argument types "str | None", "WizardContext", "list[ModelRequest | ModelResponse]", "Model", "ModelSettings"  [call-overload]
nexus/api/wizard_chat.py:725: error: Argument after ** must be a mapping, not "dict[str, Any] | None"  [arg-type]
nexus/api/wizard_chat.py:821: error: Argument 3 to "_artifact_response" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:834: error: "str" has no attribute "choices"  [attr-defined]
nexus/api/wizard_chat.py:837: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:843: error: Argument "thread_id" to "_record_text_reply" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:844: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:851: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:896: error: Incompatible types in assignment (expression has type "str", variable has type "Literal['setting', 'character', 'seed'] | None")  [assignment]
nexus/api/wizard_chat.py:956: error: Argument "model" to "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:957: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:986: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:988: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:989: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:993: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:996: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:1005: error: Argument "thread_id" to "from_request" of "WizardContext" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:1015: error: Argument 1 to "build_message_history" has incompatible type "list[Message]"; expected "Sequence[dict[str, Any]]"  [arg-type]
```

```sh
python3 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/compare_baseline.py
```

```text
flake8: current 22, baseline 22, new 0
mypy: current 34, baseline 34, new 0
Exact source-line and diagnostic multisets match origin/main 5b977eab.
```

### Earlier Gate Results Retained (Not Final Passes)

Before migration 140 landed, the dedicated proof and API/Orrery offline gate
had exactly the expected sequence failure naming 140; neither KNOWN_GAPS nor
migration 140 was taken by this branch. The final runs above replace that result.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/proof-resumed.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_mock_wizard_responses.py tests/test_orrery/test_retrograde_orchestrator.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_owner_target_guard.py --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-resumed
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: nexus_m10_fresh_test_67643, nexus_m10_template_test_67643, nexus_test_issue_613_*, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_offline_gate_* x12, qa640_renamed_test_model_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 330 passed, 7 warnings in 54.75s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/offline-api-orrery.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-offline-api-orrery
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1823 passed, 758 skipped, 7 warnings in 35.62s
```

The initial combined offline gate was deliberately interrupted and replaced
by complete smaller gates. It is **not a pass** (exit 2):

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/offline-other.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-offline-other
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/selectors.py:415: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
452 passed, 14 skipped, 7 warnings in 219.54s (0:03:39)
```

The first replacement offline-rest run, before the final rebase, also passed:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a /Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/offline-rest.log /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore-glob='tests/test_cli*.py' --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-offline-rest
```

```text
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2365 passed, 447 skipped, 8 warnings in 178.81s (0:02:58)
```

## Landing Notes and Coordinator Questions

Refs #776. Land migration 141 after 139 and 140 (both now on main).
Coordinator runs `python scripts/migrate.py --all`, then
`python scripts/migrate.py --slot 1 --write-locked-slot`. Restart the owner
gateway for product code changes and rebuild the UI bundle. Affected wizard
slots: none; save_05's cache is untouched. No fleet migration or merge occurred
in this implementer run.

Questions/actions for the coordinator:

1. File the amended stale-readiness validator finding with the cited current
   lines; S1a deliberately leaves it unfixed.
2. Triage the unchanged CLI 0.5-second timeout assertion (initial failure and
   full-file passing rerun above), and the existing whole-file lint/type debt.
3. Run the coordinator's whole-tree PostgreSQL gate at landing and preserve
   the ownership/post-commit reattach deferrals for S1b and S2.

## Accepted Stop-Report (2026-10-01; Original Commit 443ec076)

<details>
<summary>Original accepted stop-report, retained verbatim</summary>

# STOP-REPORT: 776-S1a

Implementation stopped at the first proof run because the frozen order's
incomplete-transition premise is false at base `9ac0caf6`. No PR was opened,
no branch was pushed, and this partial implementation is not ready to land.
The latest fetched `origin/main` was `d05481d8`; no rebase was attempted after
the stop condition. This report records partial work, not a completed proof.

## Binding Stop Rule

The working rules at
`/Users/pythagor/nexus/temp/orders_2026_09_30/_common_codex.md` say:
“If the order's premise turns out to be false, write a stop-report instead of
improvising.” The user's instruction repeats that rule. I did not change the
mapper, the schema validator, or the existing staging fixture to make the
specified tests pass.

## False Premise and Diagnosis

The order specifies `zone=None` as an incomplete transition that the real
mapper refuses with `ValueError("Transition data is incomplete")`, including
the skipped TEST-model case with no open stage row. The actual staged fixture
sets `ready_for_transition=True` and `validated=True` at
`tests/test_orrery/test_retrograde_wizard_live.py:261-262`.
`TransitionData.validate_completeness` at
`nexus/api/new_story_schemas.py:1374-1404` recomputes those flags only when all
required fields are present; with a missing zone it returns the existing true
flag. Therefore the mapper's guard at
`nexus/api/new_story_db_mapper.py:525-542` does not reject the data. It enters
the world transaction, reaches `create_location_hierarchy` at `:652`, and raises
`AttributeError: 'NoneType' object has no attribute 'name'` at `:175`.

These three unchanged files have no diff against the base. The proof's actual
stack (first failing test) is:

```text
nexus/api/new_story_flow.py:661: in perform_transition_with_retrograde
    mapper.perform_transition(transition_data, in_transaction=_persist_hook)
nexus/api/new_story_db_mapper.py:652: in perform_transition
    location_ids = self.create_location_hierarchy(
nexus/api/new_story_db_mapper.py:469: in create_location_hierarchy
    return _execute_hierarchy(cursor)
nexus/api/new_story_db_mapper.py:395: in _execute_hierarchy
    zone_record = self.map_zone_to_db(zone, layer_id)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <nexus.api.new_story_db_mapper.NewStoryDatabaseMapper object at 0x1335a2910>
zone = None, layer_id = 1

    def map_zone_to_db(self, zone: ZoneDefinition, layer_id: int) -> Dict[str, Any]:
        """
        Map ZoneDefinition to zones table format.

        Database columns:
        - name, summary, layer (FK)
        - boundary (PostGIS polygon, not set during creation)

        Args:
            zone: ZoneDefinition from structured output
            layer_id: ID of the parent layer

        Returns:
            Dictionary ready for database insertion
        """
        return {
>           "name": zone.name,
            "summary": zone.summary,
            "layer": layer_id,
            # boundary will be NULL initially (can be set later with PostGIS)
        }
E       AttributeError: 'NoneType' object has no attribute 'name'

nexus/api/new_story_db_mapper.py:175: AttributeError

```

The same AttributeError occurs in
`test_failure_is_recorded_at_each_stage[persistence]` and
`test_failure_is_recorded_at_each_stage[None]`. These are unexpected failures;
I did not reclassify them as acceptable or replace the required assertions.

A corrected, database-free reproduction was run from this worktree:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'from nexus.api.new_story_schemas import TransitionData; d=TransitionData.model_construct(setting=None, character=None, seed=None, layer=None, zone=None, location=None, base_timestamp=None, thread_id=None, ready_for_transition=True, validated=True); print("zone:", d.zone); print("ready_for_transition:", d.ready_for_transition); print("validated:", d.validated); print("validate_completeness():", d.validate_completeness())'
```

```text
zone: None
ready_for_transition: True
validated: True
validate_completeness(): True
```

An earlier exploratory reproduction omitted required model_construct fields
and itself raised `AttributeError: 'TransitionData' object has no attribute
'setting'`; the corrected reproduction above supplies every accessed field.

## Partial Files Changed

- `migrations/141_genesis_run_ledger.sql`: COMMENT-complete retained run and stage tables with wall-clock timestamps and the specified constraints.
- `nexus/agents/orrery/retrograde_orchestrator.py`: durable ledger writers/readers and generation output callbacks; process registry removed.
- `nexus/api/new_story_flow.py`: per-attempt ledger, all-stage failure recording, and transaction-coupled persistence/skip completion.
- `nexus/api/wizard_chat.py`: durable status read through asyncio.to_thread, including run_status and error.
- `nexus.toml`: removed the process-local operating note.
- `docs/database.md`: described the ledger and its transaction boundary.
- `docs/orrery_retrograde_spec.md`: changed status-record lifetime documentation.
- `tests/test_api/test_genesis_ledger_pg.py`: specified disposable PostgreSQL proofs, including the three failing required assertions.
- `tests/test_api/test_route_capabilities.py`: player status proof routed through offline_gate_db on slot 4.
- `tests/test_api/test_wizard_weird_level.py`: adjusted ledger boundaries and transaction statement assertions.
- `tests/test_orrery/test_retrograde_orchestrator.py`: removed process-registry tests and asserted stage output callbacks.
- `docs/qa/776-genesis-run-ledger/verification.md`: this stop-report and exact evidence.

The UI implementation and Vitest changes have not begun. `npm --prefix ui ci`,
UI tests/check, the offline suites, reachability, flake8, and mypy have not run.
No full PostgreSQL gate was run (the user's newer sequencing instruction assigns
that gate to the coordinator). No migrated-clone catalog snapshot or read-only
owner wizard listing was collected before the stop. No resumable output reuse,
input fingerprint writes, bootstrap ownership, or wizard-cache cutover was added.

## Commands and Verbatim Tails

Import provenance, run before trusting test results:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/776-genesis-run-ledger/nexus/__init__.py
```

Formatting:

```sh
/Users/pythagor/nexus/.venv/bin/python -m black nexus/agents/orrery/retrograde_orchestrator.py nexus/api/new_story_flow.py nexus/api/wizard_chat.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_orrery/test_retrograde_orchestrator.py
```

```text
reformatted tests/test_api/test_genesis_ledger_pg.py
reformatted tests/test_orrery/test_retrograde_orchestrator.py
reformatted nexus/api/new_story_flow.py
reformatted nexus/agents/orrery/retrograde_orchestrator.py
reformatted tests/test_api/test_wizard_weird_level.py
reformatted nexus/api/wizard_chat.py

All done! ✨ 🍰 ✨
6 files reformatted, 1 file left unchanged.
```

Proof set (foreground shell command, harness returned a session; waited until
exit before continuing; exit 1):

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_mock_wizard_responses.py tests/test_orrery/test_retrograde_orchestrator.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_owner_target_guard.py --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-proof > /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/proof.log 2>&1
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: nexus_m10_fresh_test_49901, nexus_m10_template_test_49901, nexus_test_issue_613_*, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_offline_gate_* x12, qa640_renamed_test_model_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_genesis_ledger_pg.py::test_stage_rows_and_outputs_persist
FAILED tests/test_api/test_genesis_ledger_pg.py::test_failure_is_recorded_at_each_stage[persistence]
FAILED tests/test_api/test_genesis_ledger_pg.py::test_failure_is_recorded_at_each_stage[None]
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
4 failed, 327 passed, 7 warnings in 50.34s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

```

Migration sequence failure is expected under the user's sequencing update:

```text
E       AssertionError: assert {'013', '119', '140'} == frozenset({'013', '119'})
E         Extra items in the left set:
E         '140'
```

`KNOWN_GAPS` was not changed, and migration 140 was not taken.

Migration comments check:

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
```

## Scope and Coordinator Questions

The pytest secret-store guard denied nexus-api and the test-only provider guard
was not overridden. The dbname audit reported owner targets: none; the proofs
used disposable clones through offline_gate_db. The change adds no code that
resets wizard caches or accesses save_05 specifically. No gateway was started,
and no migration was applied to an owner save or NEXUS_template. This is offline
protocol/storage evidence only; it does not qualify any live provider.

1. Should the frozen order be amended to set ready_for_transition=False as well
   as zone=None for the validation-refusal proofs, or is a separate fix for
   TransitionData.validate_completeness required first? Either choice needs the
   coordinator's revised scope; this run did neither.
2. Once that premise is resolved, should implementation resume from this partial
   branch or should the coordinator issue a new order? UI reattach and the
   remaining proof gates are outstanding.

If this work later lands, the original notes still apply: migration 141 after
139 and 140; coordinator fleet migration then locked-slot-1 migration; owner
gateway restart and UI rebuild; no affected wizard caches, save_05 untouched.
Gateway death/run ownership and reattach after world commit remain deferred to
S1b/Q5 and S2 respectively. No landing is authorized by this report.

Authored by Codex, running GPT-6.

</details>

Authored by Codex, running GPT-6.

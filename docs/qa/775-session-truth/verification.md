# Durable Session Truth Verification

Work order 775; branch `claude/775-session-truth`. Migration 121 is applied only to disposable test databases. The coordinator must apply it to the fleet at landing.

## Contract

- The existing session UUID identifies the attempt. `phase` records retrieval, assembly, writer, gaia, staging, and complete. `status=complete` means a draft is available; its final disposition remains unset until an explicit acceptance, replacement, or discard.
- Acceptance binds `terminal_outcome=accepted` and the actual `INSERT ... RETURNING id` in the accepting transaction. A successful regenerate binds `superseded` and `replaced_by_session_id` in the same transaction that replaces the incubator. Errors retain their class. Legacy complete rows retain unknown outcomes: historical predicted IDs cannot prove acceptance.
- Staging and session completion share a transaction. Heartbeats renew the lease; an expired lease becomes a durable `GenerationLeaseExpired` error when read or reclaimed.
- `GET /api/narrative/active?slot=N` reads the lease owner, or the latest session after lease release, directly from durable rows. Both discovery and `/status/{session}?slot=N` require the explicit slot. WebSockets require `?slot=N` and send only that slot's hints.
- The reader discovers on mount, reconnect, visibility return, and a configured timer gap. It polls active sessions to a completed draft or terminal outcome, then refetches slot and narrative state. Idle discovery catches turns started elsewhere. No recovery path submits inference. Only connectivity drives OFFLINE.
- Poll, wake, and request-timeout values come from `[api.narrative_generation]` through typed slot-state and read-only preferences payloads. Preferences bootstrap recovery independently of database reads. Stale timeout remains server-owned. The TEST writer delay is configurable under `[api.test_provider]`.

## Environment and Commands

All commands run from `/Users/pythagor/nexus/.claude/worktrees/775-session-truth`, using the shared interpreter without installing Python dependencies.

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/775-session-truth/nexus/__init__.py
```

`npm --prefix ui ci` installed this worktree's dependencies. No node_modules symlink was used.

## Final Gates

Re-run after merging fetched `origin/main` (`607c393c`) in `b1a09dbd`.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2659 passed, 827 skipped, 9 warnings in 94.59s (0:01:34)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api -k 'session or lease or status or recover or continue'
```

```text
63 passed, 323 deselected, 9 warnings in 76.80s (0:01:16)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
npm --prefix ui run check
```

```text

> nexus-ui@1.0.0 check
> tsc
```

```sh
npm --prefix ui test
```

```text
   ✓ CONTINUE > checks the most recently used slot and resumes its wizard directly 794ms

 Test Files  22 passed (22)
      Tests  239 passed (239)
   Start at  15:08:20
   Duration  2.04s (transform 1.30s, setup 1.31s, collect 5.07s, tests 2.62s, environment 8.25s, prepare 1.92s)
```

```sh
npm --prefix ui run build
```

```text
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 2.48s

PWA v1.0.3
mode      generateSW
precache  22 entries (2276.92 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/proofs/proof_session_truth.py
```

```text
1 passed, 9 warnings in 115.01s (0:01:55)
```

The offline skips are opt-in PostgreSQL/live-provider markers. The required PostgreSQL selection has no skips. No #885 exemption was needed. Both pre-commit hooks passed.

## Review Amendments

- Recovery listeners and the socket mount without waiting for slot state. Database-independent preferences bootstrap the timing configuration and retry failed configuration reads; discovery retries on the configured cadence.
- Each discovery/status fetch, including its response body, uses an AbortController with `request_timeout_seconds`. Visibility return, wake, and reconnect cancel the previous recovery request and immediately rediscover. A pending POST prevents duplicate submission but does not suppress reads.
- Bootstrap and continuation wrappers explicitly chain exceptions. Durable failures traverse the complete cause chain. Real PostgreSQL tests use the delayed TEST provider to record `ReadTimeout` and invalid bootstrap input to record `ValueError`; a real Pydantic validation failure through two HTTP wrappers retains `ValidationError`.
- The ledger displays retrieval, assembly, writer, gaia, staging, complete once and in that order. Legacy wire names normalize at the API parsing boundary. A rendered component test checks increasing progress through all six phases and absence of telemetry at rest.

## Source Evidence

- `nexus/api/commit_handler_sync.py:435`: the inserted narrative row supplies the chunk ID; line 457 records acceptance in that transaction.
- `nexus/api/narrative_generation.py:607`: replacement lineage shares the conditional incubator replacement transaction; line 617 completes the new session before that transaction commits.
- `nexus/api/narrative_lease.py:337`: heartbeat renewal and phase writes use lease-first locking; line 361 discovers and reaps from the lease/session rows.
- `nexus/api/narrative.py:1064`: discovery requires an explicit slot; line 1077 exposes durable status for the requested slot.
- `ui/client/src/hooks/useNarrativeEngine.ts:116`: independent preferences bootstrap; line 152 installs cancellation and the configured discovery cadence; line 170 bounds each fetch; line 272 implements recovery boundaries.
- `nexus/api/preferences_endpoints.py:36`: read-only recovery settings in the existing preferences response.
- `nexus/api/narrative_generation.py:44`: innermost cause extraction; lines 267 and 306 explicitly chain bootstrap/continuation wrappers.
- `tests/test_api/test_session_truth_pg.py:131`: real provider timeout and bootstrap validation failures persisted in PostgreSQL.
- `tests/test_api/test_narrative_generation.py:469`: nested validation cause regression (see function `test_session_error_class_unwraps_nested_validation_failure`).
- `ui/client/src/components/nexus/RightLedger.test.tsx:35`: rendered phase order, monotonic progress, and idle visibility.

## Browser and Database Proof

`tests/proofs/proof_session_truth.py` uses Chromium with the built reader, the repository TEST HTTP provider with a three-second writer delay, and a `qa640_775_browser_*` data clone of read-only source `save_04`. It checks lane 8014 with `lsof` before starting, stops its own gateway, runs `nexus down` with the same lane environment, and drops the clone through the fixture.

The proof submits a continuation through the real reader, observes `writer` in the server session, closes the entire page/socket, waits beyond the TEST response delay, and verifies completion before opening a fresh reader. That reader discovers and reads the completed session without posting a continuation. Its next explicit input accepts the recovered draft. A subsequent regenerate replaces the next draft and records its session UUID in the superseded attempt. Visibility return, a closed/reconnected socket, and a real browser timer gap trigger discovery without inference retries.

The expanded proof withholds the response from a real continuation POST while asserting that the mounted reader still polls status. The fresh reader then loses its first two slot-state reads and first discovery, stalls the next discovery and first status request until their configured timeouts, and still adopts the completed attempt. For each recovery boundary it stalls another discovery and requires cancellation and a successful rediscovery before the request timeout. These are transport disruptions around the real server; no generation/status payloads are fabricated.

See [session rows](session-rows.json), [TEST provider usage](provider-usage.json), and [recovered reader](recovered-reader.png). The usage assertions require every correlated turn event to use `TEST`, including both `skald_writer` and `gaia`. This proves lifecycle and identity, not paid-provider output quality.

The SQL snapshots use:

```sql
SELECT session_id::text, operation, status, phase, terminal_outcome,
       chunk_id, replaced_by_session_id::text, error_class,
       created_at::text, heartbeat_at::text
FROM narrative_generation_sessions
ORDER BY created_at DESC LIMIT 4;
```

The accepted ID is independently checked against `narrative_chunks.id`. Additional PostgreSQL tests cover phase persistence, heartbeat renewal, stale expiry, slot-isolated HTTP/status/socket traffic, atomic acceptance and replacement, and existing rollback/undo behavior.


### Recorded Session Transitions

| Snapshot | Session | Phase | Outcome | Chunk | Replacement |
| --- | --- | --- | --- | --- | --- |
| Writer Active Before Disconnect | 3f232fe3-0b84-4311-a405-73a65f66c61e | writer | pending | — | — |
| Complete While Client Absent | 3f232fe3-0b84-4311-a405-73a65f66c61e | complete | pending | — | — |
| Recovered Draft Accepted With Inserted Chunk | 8a9ff221-e495-4232-9aac-780c93eb05cf | assembly | pending | — | — |
| Recovered Draft Accepted With Inserted Chunk | 3f232fe3-0b84-4311-a405-73a65f66c61e | complete | accepted | 51 | — |
| Regenerate Replacement Lineage | fb1b21ca-09c0-4224-903c-a1bd37e01995 | complete | pending | — | — |
| Regenerate Replacement Lineage | 8a9ff221-e495-4232-9aac-780c93eb05cf | complete | superseded | — | fb1b21ca-09c0-4224-903c-a1bd37e01995 |
| Regenerate Replacement Lineage | 3f232fe3-0b84-4311-a405-73a65f66c61e | complete | accepted | 51 | — |

## Earlier Attempts

- An initial offline run overlapped edits to the TOML configuration after pytest imported the previous model definition, causing spurious `extra_forbidden` failures. It is not baseline evidence.
- The next offline run found the required reachability-baseline entry for the new telemetry module missing; that entry was added.
- The first PostgreSQL slice found draft deletion still needed a durable discard outcome; deletion and undo now record it in their own transactions.
- One overlapping offline/PostgreSQL run collided on the existing Keychain test account: `RuntimeError: Keychain write failed for account 'test-secret-455' (security exit 45).` The gate was rerun without overlapping those suites.
- Another slice encountered an already occupied port 8018 in the repository scheduler fixtures. No foreign listener was stopped or fixture lane renamed.
- The first browser probe timed out during local model loading. The HTTP probe budget was increased. The embedding CLI independently rejects disposable names in its subprocess; the fixture now uses its existing `--db-url` interface for the clone while executing the real script. No embedding output is fabricated.
- An expanded proof passed the lifecycle assertions but its evidence exporter initially included prompt-window records that have no `run_id`; the exporter now selects only correlated provider-usage records.

## Amendment Validation History

Before the merge, targeted Python checks passed (13 tests), the two real PostgreSQL error-class cases passed, and the expanded lifecycle proof passed. The first UI run found two existing fetch-call assertions receiving an unnecessary `signal: undefined`; the fetch helper now preserves the one-argument call when no signal is supplied. An initial focused command used the nonexistent filename `test_preferences_endpoints.py`; the corrected `test_preferences.py` run passed.

Additional targeted checks before the merge:

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_narrative_generation.py tests/test_api/test_preferences.py
```

```text
13 passed, 7 warnings in 1.49s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s tests/test_api/test_session_truth_pg.py -k error_class
```

```text
2 passed, 2 deselected, 7 warnings in 8.07s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

## Cleanup

After the final proof, lane 8014 has no listener, its fixture ran `nexus down` with the same lane environment, and the proof database `qa640_775_browser_429c7810ea26` is absent from `pg_database`. The provider evidence contains only TEST events. No saved-slot or template migration was applied; migration 121 remains the coordinator's landing task.

# Durable Session Truth Verification

Work order 775; branch `claude/775-session-truth`. Migration 121 is applied only to disposable test databases. The coordinator must apply it to the fleet at landing.

## Contract

- The existing session UUID identifies the attempt. `phase` records retrieval, assembly, writer, gaia, staging, and complete. `status=complete` means a draft is available; its final disposition remains unset until an explicit acceptance, replacement, or discard.
- Acceptance binds `terminal_outcome=accepted` and the actual `INSERT ... RETURNING id` in the accepting transaction. A successful regenerate binds `superseded` and `replaced_by_session_id` in the same transaction that replaces the incubator. Errors retain their class. Legacy complete rows retain unknown outcomes: historical predicted IDs cannot prove acceptance.
- Staging and session completion share a transaction. Heartbeats renew the lease; an expired lease becomes a durable `GenerationLeaseExpired` error when read or reclaimed.
- `GET /api/narrative/active?slot=N` reads the lease owner, or the latest session after lease release, directly from durable rows. Both discovery and `/status/{session}?slot=N` require the explicit slot. WebSockets require `?slot=N` and send only that slot's hints.
- The reader discovers on mount, reconnect, visibility return, and a configured timer gap. It polls active sessions to a completed draft or terminal outcome, then refetches slot and narrative state. Idle discovery catches turns started elsewhere. No recovery path submits inference. Only connectivity drives OFFLINE.
- Poll and wake values come from `[api.narrative_generation]` through the typed slot-state payload. Stale timeout remains server-owned. The TEST writer delay is configurable under `[api.test_provider]`.

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

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2655 passed, 821 skipped, 9 warnings in 100.79s (0:01:40)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api -k 'session or lease or status or recover or continue'
```

```text
60 passed, 316 deselected, 9 warnings in 68.88s (0:01:08)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_session_truth_pg.py tests/test_api/test_acceptance_staging_pg.py
```

```text
19 passed, 7 warnings in 18.62s
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

 Test Files  22 passed (22)
      Tests  238 passed (238)
   Start at  14:48:11
   Duration  1.99s (transform 1.47s, setup 1.10s, collect 5.81s, tests 2.89s, environment 8.12s, prepare 1.37s)

```

```sh
npm --prefix ui run build
```

```text
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 3.08s

PWA v1.0.3
mode      generateSW
precache  22 entries (2275.63 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/proofs/proof_session_truth.py
```

```text
1 passed, 9 warnings in 105.69s (0:01:45)
```

The offline skips are the repository's opt-in PostgreSQL/live-provider markers; the required PostgreSQL slice has no skips. No #885 exemption was needed. The 19-test acceptance run preceded the final expanded slot-isolation test; the final 60-test slice includes both session-truth tests. Both pre-commit hooks passed for the implementation commit.

## Source Evidence

- `nexus/api/commit_handler_sync.py:435`: the inserted narrative row supplies the chunk ID; line 457 records acceptance in that transaction.
- `nexus/api/narrative_generation.py:598`: replacement lineage shares the conditional incubator replacement transaction; line 608 completes the new session before that transaction commits.
- `nexus/api/narrative_lease.py:337`: heartbeat renewal and phase writes use lease-first locking; line 361 discovers and reaps from the lease/session rows.
- `nexus/api/narrative.py:1064`: discovery requires an explicit slot; line 1077 exposes durable status for the requested slot.
- `ui/client/src/hooks/useNarrativeEngine.ts:114`: configuration comes from slot state; line 232 implements recovery boundaries and the following socket/timer handlers accelerate durable reads.

## Browser and Database Proof

`tests/proofs/proof_session_truth.py` uses Chromium with the built reader, the repository TEST HTTP provider with a three-second writer delay, and a `qa640_775_browser_*` data clone of read-only source `save_04`. It checks lane 8014 with `lsof` before starting, stops its own gateway, runs `nexus down` with the same lane environment, and drops the clone through the fixture.

The proof submits a continuation through the real reader, observes `writer` in the server session, closes the entire page/socket, waits beyond the TEST response delay, and verifies completion before opening a fresh reader. That reader discovers and reads the completed session without posting a continuation. Its next explicit input accepts the recovered draft. A subsequent regenerate replaces the next draft and records its session UUID in the superseded attempt. Visibility return, a closed/reconnected socket, and a real browser timer gap trigger discovery without inference retries.

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
| Writer Active Before Disconnect | `e897e067-b2f0-42cf-a35b-fc92d8f32256` | writer | pending | — | — |
| Complete While Client Absent | `e897e067-b2f0-42cf-a35b-fc92d8f32256` | complete | pending | — | — |
| Recovered Draft Accepted With Inserted Chunk | `59cebfbd-1411-4f36-bba5-92e46264af2b` | assembly | pending | — | — |
| Recovered Draft Accepted With Inserted Chunk | `e897e067-b2f0-42cf-a35b-fc92d8f32256` | complete | accepted | 51 | — |
| Regenerate Replacement Lineage | `de029a5c-3d5c-4075-a0c9-3b4611fb6833` | complete | pending | — | — |
| Regenerate Replacement Lineage | `59cebfbd-1411-4f36-bba5-92e46264af2b` | complete | superseded | — | de029a5c-3d5c-4075-a0c9-3b4611fb6833 |
| Regenerate Replacement Lineage | `e897e067-b2f0-42cf-a35b-fc92d8f32256` | complete | accepted | 51 | — |

## Earlier Attempts

- An initial offline run overlapped edits to the TOML configuration after pytest imported the previous model definition, causing spurious `extra_forbidden` failures. It is not baseline evidence.
- The next offline run found the required reachability-baseline entry for the new telemetry module missing; that entry was added.
- The first PostgreSQL slice found draft deletion still needed a durable discard outcome; deletion and undo now record it in their own transactions.
- One overlapping offline/PostgreSQL run collided on the existing Keychain test account: `RuntimeError: Keychain write failed for account 'test-secret-455' (security exit 45).` The gate was rerun without overlapping those suites.
- Another slice encountered an already occupied port 8018 in the repository scheduler fixtures. No foreign listener was stopped or fixture lane renamed.
- The first browser probe timed out during local model loading. The HTTP probe budget was increased. The embedding CLI independently rejects disposable names in its subprocess; the fixture now uses its existing `--db-url` interface for the clone while executing the real script. No embedding output is fabricated.
- An expanded proof passed the lifecycle assertions but its evidence exporter initially included prompt-window records that have no `run_id`; the exporter now selects only correlated provider-usage records.

## Cleanup

After the final proof, `lsof -nP -iTCP:8014 -sTCP:LISTEN` returned no listener. A query of `pg_database` for `qa640_775_browser_5179e7573b46` returned `[]`, confirming the disposable proof database was dropped. The recorded six provider events are all `TEST` (three writer and three Gaia calls).

## Deferred and Coordinator Questions

Migration 121 is not applied to saved stories or the template. Apply it at landing before serving the new API. Historical accepted mappings and replacement lineages cannot be reconstructed from predicted IDs and are intentionally not guessed. Manifests, retention, inspect-turn tooling, and the remaining #764 scope are deferred. No product questions remain.

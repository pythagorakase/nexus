# Caller Inventory for the Orphan API Surfaces (#807)

Base: `origin/main` at `0da9c613`, which includes the route-capability
registry from #984. This records who still reaches the three modules this
slice retires, and what each served, before anything was deleted.

## Modules

| Module | Importers outside itself and tests | Reached in production by |
|---|---|---|
| `nexus/api/storyteller.py` | `nexus/api/__init__.py` (PEP 562 `app` export, deferred) | Nothing that resolves `nexus.api.app`. The reachability chain is `nexus/api/mock_openai.py` (service root) → package initialization of `nexus/api/__init__.py` → the deferred import in `__getattr__`. No service command, CLI entry point, or script names `nexus.api:app` or `nexus.api.storyteller`. |
| `nexus/api/session_manager.py` | `nexus/api/storyteller.py` only | Only through `storyteller.py`. It was the sole writer of the ignored `<repo>/sessions/` directory, created on import of the Storyteller app. |
| `nexus/api/chunk_workflow.py` | `nexus/api/storyteller.py` and `nexus/api/narrative.py` | The gateway imports `ChunkWorkflow` (unused) and `get_default_workflow`, whose only call is the broken `GET /api/chunks/states`. |

Test importers: `tests/test_storyteller_context_privacy.py`,
`tests/test_session_manager.py`, `tests/test_api/test_chunk_workflow_integration.py`,
`tests/test_api/test_import_side_effects.py`,
`tests/test_api/test_wizard_model_resolution.py` (one test of the Storyteller
app's setup-start handler, beside the gateway setup test that stays),
`tests/test_orrery/test_playable_narrative_boundary.py`, and dead
`chunk_workflow` monkeypatches in `tests/test_api/test_narrative_continue_validation.py`,
`tests/test_api/test_attempt_manifest_pg.py`, and
`tests/proofs/proof_session_truth.py`. `tests/test_prompt_lint.py` allowlisted
two `storyteller.py` literals. `ir_eval/` and `scripts/` import none of the
three modules.

## Routes

Searched `ui/client/src`, `nexus/cli.py`, `ui/src-tauri`, `scripts`, `ir_eval`,
and `docs` (historical `docs/qa` evidence excluded):

```sh
git grep -n -F "$route" -- ui/client/src nexus/cli.py ui/src-tauri scripts ir_eval docs ':!docs/qa'
```

| Route on the Storyteller app | On the gateway | Callers |
|---|---|---|
| `POST /api/story/session/create` | No | None |
| `GET /api/story/sessions` | No | None |
| `GET /api/story/session/{session_id}` | No | None |
| `DELETE /api/story/session/{session_id}` | No | None |
| `GET /api/story/history/{session_id}` | No | None |
| `GET /api/story/context/{session_id}` | No | None |
| `WS /api/story/stream/{session_id}` | No (`/ws/narrative` is the gateway's socket) | None |
| `POST /api/story/turn` | No; already answered 410 | Prose in `docs/generation_attempt_identity.md` only |
| `POST /api/story/regenerate` | No; already answered 410 | Prose in `docs/generation_attempt_identity.md` only |
| `POST /api/story/new/setup/start` | Yes (`setup_endpoints`) | UI, CLI, and `scripts/test_setup_flow.py`, all against the gateway |
| `GET /api/story/new/setup/resume` | Yes | UI, against the gateway |
| `POST /api/story/new/setup/record` | Yes | UI, against the gateway |
| `POST /api/story/new/setup/reset` | Yes | UI and CLI, against the gateway |
| `POST /api/story/new/slot/select` | Yes | UI, against the gateway |
| `GET /api/chunks/states` | Yes, and broken | None |

The UI's `/api/narrative/chunks/...` reads are reader routes on the gateway
and do not touch `ChunkWorkflow`. Every live `/api/story/new/*` call targets a
route the gateway serves, so no client depends on the Storyteller app.

The duplicates had also drifted. On the base, mypy reports `Argument after **
must be a mapping, not "WizardCache"` for the Storyteller app's resume handler,
and `Too many arguments for "get_chunk_states" of "ChunkWorkflow"` for the
gateway's chunk-state route.

## Base Behavior of `GET /api/chunks/states`

The gateway handler calls `get_default_workflow().get_chunk_states(start, end,
slot)`, but the method takes `(start_chunk, end_chunk)`. Before reaching it,
`get_default_workflow()` builds a `ChunkWorkflow` for `save_01` whatever the
requested slot, and its constructor runs `ALTER TABLE narrative_chunks` for
any missing lifecycle column.

The reproduction created a throwaway database with a real `narrative_chunks`
table, let the real constructor run against it, installed that workflow as
the default, and called the route through `TestClient(nexus.api.narrative.app)`:

```text
INFO Added state column to narrative_chunks
INFO Added finalized_at column to narrative_chunks
INFO Added embedding_generated_at column to narrative_chunks
INFO Added regeneration_count column to narrative_chunks
direct two-argument call: [{'id': 1, 'state': 'draft', 'finalized_at': None, 'embedding_generated_at': None, 'regeneration_count': 0}, {'id': 2, 'state': 'draft', 'finalized_at': None, 'embedding_generated_at': None, 'regeneration_count': 0}]
ERROR Error fetching chunk states: ChunkWorkflow.get_chunk_states() takes 3 positional arguments but 4 were given
GET /api/chunks/states -> 500 {"detail":"ChunkWorkflow.get_chunk_states() takes 3 positional arguments but 4 were given"}
```

Without a preinstalled workflow the route fails earlier, on the `save_01`
connection, and still answers 500.

## Parent Embedding Semantics

`ChunkWorkflow.accept_chunk` queued an embedding for the previous playable
chunk when its `embedding_generated_at` was null, skipping Retrograde's
synthetic prologue. The gateway never called it. Production acceptance
claims the parent's embedding through `narrative_lease.claim_parent_embedding`,
whose `enqueue_locked_embeddings` queues every playable chunk older than the
parent whose `embedding_generated_at` is null. The PostgreSQL test that
proved the prologue boundary on `accept_chunk` moves to that claim.

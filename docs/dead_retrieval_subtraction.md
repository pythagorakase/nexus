# Deterministic Retrieval Subtraction

This records the code-only slices of issue #813 (brainstorm C077), not
completion of its schema cleanup scope.

## Removed Surface and Reachability Evidence

- `TurnCycleManager.query_entity_states()` issued `SELECT` queries against
  `events` and `threats`, then suppressed missing-table errors. Neither relation
  exists in the inspected `NEXUS_template`; canonical `world_events` does exist.
  These queries, their empty payload/count fields, and their exception handlers
  are removed. Character, place, faction, and relationship queries remain.
- The removed queries were the only runtime consumers of
  `include_all_active_events`, `include_all_active_threats`,
  `active_event_statuses`, `active_threat_statuses`, `max_total_events`, and
  `max_total_threats`. These fields and the two related provider overrides are
  removed from `[lore.entity_inclusion]` and its validation models. External
  configs containing them now fail validation and must remove them.
- Repository-wide references to `DivergenceDetector` consisted of its declaration,
  one import, and one constructor invocation. Its `detect()` method always
  returned no divergence and had no callers. The class and its construction are
  removed. `DivergenceResult` stays at `nexus.memory.divergence` with its existing
  fields and serialization; `ContextMemoryManager._detect_divergence()` still
  uses `HighSpecificityEntityDetector` backed by character names, aliases,
  places, and factions.

The generic payload formatter and token-budget utilities retain their existing
ability to consume caller-supplied event/threat data; this slice removes the
invalid production database queries, not unrelated formatting contracts.

## Verification and Remaining Work

`tests/test_lore/test_entity_phase_subtraction_pg.py` initializes a disposable
canonical template clone and runs the real entity phase. SQL observation proves
no query attempts either nonexistent relation while populated entity dossiers
still arrive. The fixture's canonical `world_events` rows are unchanged. A
second case loads real entity records and an alias through the memory manager,
checks positive and negative divergence, and pins the retained result contract.
No provider calls or live-slot changes are needed.

No tables, enums, functions, overloads, reset statements, legacy corpora,
psychology, episode, season, or vector data are removed here. The remaining
#813 schema work still requires the exact drop manifest and dependency/row
preflights mandated by its verifier amendments. Other reliability facades are
outside this commit's scope.

## Retry Facade and MEMNON Registry Subtraction

A second code-only slice of #813 removes the remaining reliability facades and
MEMNON's unread tier registries. It changes no schema, story data, or runtime
configuration.

### Removed Surface and Reachability Evidence

- `nexus/api/retry_handler.py` (`RetryConfig`, `RateLimiter`,
  `retry_with_backoff`, `async_retry_with_backoff`, `CircuitBreaker`,
  `with_timeout`, `FallbackChain`, and their module-level singletons) and
  `nexus/api/resilient_openai.py` (`ResilientOpenAI`, `AsyncResilientOpenAI`,
  their wrappers, and `create_resilient_client`) are deleted. A
  repository-wide search for every exported name found no production, operator,
  migration, or script importer. `resilient_openai.py` was already a baselined
  orphan, and `retry_handler.py` was reached only from it and from two
  PostgreSQL tests. The one other hit, `.with_timeout(3)` in
  `ui/src-tauri/src/lib.rs`, is an unrelated Rust builder method.
  `scripts/check_reachability.py --write-baseline` dropped the stale orphan
  exemption from `config/reachability_baseline.json`.
- `nexus.database.is_connection_failure` stays. The scheduler, Orrery worker,
  Retrograde maturation, experience rendering, and compaction use it.
- `tests/test_api/test_db_pool_pg.py` keeps its no-replay proofs without the
  facades. `test_terminated_commit_raises_ambiguous_commit_once` runs the interrupted
  mutation directly. It still requires `AmbiguousCommit` caused by
  `OperationalError`, zero committed rows, and a sequence witness of a single
  insert attempt. `test_scheduler_does_not_replay_wrapped_connection_failure`
  (formerly `test_fallback_and_scheduler_do_not_replay`) raises the same
  domain-wrapped connection failure for raw and pooled commits. It still
  requires `SlotScheduler._recover` to stop in the `failed` state. The
  sync/async parameter existed only for the deleted `FallbackChain`.
- MEMNON built `memory_tiers` and `query_types` in its constructor and never
  read them. They named the absent `events` and `threats` relations and the
  empty `ai_notebook` and `items` tables. The `query_types` key in LORE's
  deep-query phase state is an unrelated per-turn counter and is unchanged.
- `events` is removed from `READONLY_SQL_ALLOWED_TABLES`.
  `tests/test_lore/test_entity_phase_subtraction_pg.py` asserts that
  `to_regclass('events')` is null on a canonical template clone.
  `world_events` remains allowed.
- The five `ai_notebook` column entries in `config/schema_docs_baseline.json`
  keep their keys. Their reason no longer cites the deleted MEMNON listing.

The retry-wrapper rows in `docs/qa/804-connection-preflight/verification.md`
remain a dated audit of the modules as they stood then.

### Remaining Guarded Schema Manifest

The following drops still need PostgreSQL preflights after #810 and #812. Each
must count rows and inspect `pg_depend`, views, and function bodies on
`NEXUS_template` and every restored slot. The guarded migration must abort, not
discard, when it finds unexpected rows or dependents.

| Object | Current Evidence | Coupled Changes |
| --- | --- | --- |
| `public.items` and `items_id_seq` | The issue verifier found zero rows in all three inspected databases. No code reads the table after this slice. | Remove `DELETE FROM items` and `ALTER SEQUENCE items_id_seq RESTART WITH 1` from the new-story reset in `nexus/api/new_story_db_mapper.py`, plus the table note in `nexus/agents/logon/apex_schema.py`, in the same change. |
| `public.ai_notebook` | Zero rows per the issue verifier. No code reader or writer remains. | Retire its five baselined columns (`id`, `agent`, `level`, `log_entry`, `"timestamp"`) from `config/schema_docs_baseline.json` in the same change. |
| Obsolete retrieval function overloads | These cannot be enumerated offline. | List them from `pg_proc` on a template clone and prove that no code, view, or trigger calls each signature before its drop. |

Psychology, episode, season, and legacy-vector data stay outside this cleanup
pending separate rulings.

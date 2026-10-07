# Deterministic Retrieval Subtraction

This records the code slices of issue #813 (brainstorm C077) and the guarded
table/enum retirement in migration 143. The six legacy vector-helper functions
remain deferred to #812; this is not completion of the entire issue.

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

### Guarded Table and Enum Retirement (2026-10-01)

Migration `143_drop_dead_schema_strata.sql` retires exactly `public.items` and
`public.ai_notebook`, their owned `public.items_id_seq` and
`public.ai_notebook_id_seq`, and these nine enums:

- `public.agent_type` and `public.log_level_type`, after their notebook columns.
- `public.emotional_valence`, `public.entity_type`, `public.item_type`,
  `public.relationship_type`, `public.threat_domain_type`,
  `public.threat_lifecycle_type`, and `public.trait` (813-Q2: all seven).

Full-data read-only `pg_dump` clones of `NEXUS_template` and `save_01` through
`save_05` agreed on emptiness, target definitions and dependency identities.
The frozen fixture and manifest under `tests/fixtures/813_pre143_*` record all
16 columns, nine enum label sets, four named constraints and four internal FK
triggers, the item update trigger, row types/arrays, owned sequences and TOAST
objects: 66 explicit catalog addresses and 62 dependency edges. Slot 2 is used
for schema and emptiness evidence only, not chronology evidence.

Both tables are locked before counting rows. Identity, ownership, frozen
columns/defaults/constraints, exact closure and outgoing edges, and catalog-aware
SQL/PLpgSQL body checks precede every restrictive drop. Unexpected data or use
refuses the migration and the normal runner rolls back the comment and stamp as
well as the schema. The shared `set_updated_at()` body and character/place
triggers survive; its comment now names only the two surviving triggers.

The new-story mapper loses only its two `items` reset statements. The obsolete
chunk-schema table notes and unused Python `EntityType` class/source-list bullet
are removed. Only the five notebook-column and nine enum debt entries are
retired; the six function entries and the documentation ratchet stay intact.
See `docs/qa/813-drop-dead-strata/verification.md` for source/clone identities,
preflight SQL, refusal outcomes, preservation assertions and command tails.
Fleet application is the coordinator's landing action, not an implementer write.

### Deferred Vector-Helper Function Manifest

813-Q1 binds: “The guarded drop of the dead tables and enums no longer waits for
#810 and #812. The six vector-helper functions wait for #812's legacy inventory.”
Migration 143 leaves all six definitions unchanged and permits a real
`hybrid_search` caller. Their fully qualified catalog identities, with the exact
`pg_get_function_identity_arguments` text frozen from all six clones, are:

- `public.hybrid_search(query_text text, query_embedding bytea, vector_weight double precision, text_weight double precision, k integer, model_name text)`.
- `public.hybrid_search(query_text text, query_embedding vector, vector_weight double precision, text_weight double precision, k integer, model_name text)`.
- `public.hybrid_search(query_text text, query_embedding vector, vector_weight double precision, text_weight double precision, k integer, model_name text, alias_terms_input text[])`.
- `public.migrate_embeddings()`.
- `public.pad_vector_384_to_1024(v vector)`.
- `public.pad_vector_to_1024(v vector)`.

The complete `pg_get_functiondef` definitions and original comments are committed
in `tests/fixtures/813_pre143_manifest.json` (`deferred_functions`), not inferred
from names. Current retrieval delegates to the multi-model scorer in
`nexus/agents/memnon/utils/db_access.py`; that does not authorize these drops.
#810 already removed the obsolete MEMNON setup methods and hybrid-search
Markdown document; migration 143 neither recreates nor edits them.

The runner's fleet is `NEXUS_template` plus five save slots. Deprecated `NEXUS`,
mock databases, backups and rehearsals are outside that fleet. Psychology,
episodes, seasons and legacy-vector tables/data remain outside this cleanup.
813-Q3 retains the documented unused labels; the separate 813-Q5 MEMNON SQL
subtraction is unchanged. This slice completes no deferred 813-R5 function drop
and adds or reopens no owner question.

### Read-Only SQL Subtraction and Retained Labels (2026-10-07)

813-Q5 binds: "Delete execute_readonly_sql only". `MEMNON.execute_readonly_sql`,
its `READONLY_SQL_ALLOWED_TABLES` allowlist, and
`tests/test_orrery/test_memnon_whitelist.py`, which tested only the allowlist,
are deleted. No caller existed under `nexus/`, `scripts/`, `tests/` or `ui/`.
Its FROM/JOIN patterns were raw strings with doubled backslashes, so the
allowlist matched no table, and it discarded a failed
`SET LOCAL statement_timeout`. Its two baselined handlers leave
`config/exception_disposition_baseline.json`. `MEMNON.get_schema_summary` stays
unchanged. It returns column names but no comments, because its comment queries
run after its connection closes; `CLAUDE.md` now says so and names no caller,
because none exists.

813-Q3 binds: "Keep the labels, documented. Migration 135's comments already say
no writer uses them." The `event_source_kind` labels `apex`, `narrator` and
`bleed` and the `orrery_narration_status` label `leased` stay, and no migration
rebuilds either type. A read-only check on 2026-10-07 found no `world_events` or
`orrery_resolutions` row with any of these labels in `NEXUS_template` or
`save_01` through `save_05`.

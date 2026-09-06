# Deterministic Retrieval Subtraction

This is the code-only slice of issue #813 (brainstorm C077), not completion of
its reliability and schema cleanup scope.

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

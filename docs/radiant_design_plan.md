# Off-Screen Behavior Resolver — Design Plan (Post-Review v4)

**Status:** Post-multi-model-review + grounding pass against the live codebase. Round 2's neutrally-framed re-review of the entity super-table converged on a staged identity-spine approach (Option C), changing the round-1 verdict. v4 corrects hook-seam line numbers, disambiguates the "Phase 7" naming collision, tightens schema declarations, and resolves a `tick_chunk_id` timing gap.

**Originating artifacts:** `temp/radiant/off_screen_resolver_spec.md`, `temp/radiant/behavior_substrate.py`, `temp/radiant/package_simulator.jsx`
**Review trace:** `temp/radiant/design_plan_edited.md` (round 1: GPT-5.5-Pro, Codex, separate-Claude, Gemini) + `temp/radiant/super_table_question.md` (round 2: GPT-5.5-Pro, Claude Opus 4.7 chat) + v4 grounding pass against current `main` (claude-opus-4-7).

**Terminology in v4:**
- **LORE Phase N** = a phase of `LORE.process_turn()` (`turn_context.py:12-21`: USER_INPUT, WARM_ANALYSIS, ENTITY_STATE, DEEP_QUERIES, PAYLOAD_ASSEMBLY, APEX_GENERATION, INTEGRATION).
- **Radiant Stage N** = a stage of the off-screen pipeline (Resolve / Commit / Clear / Promote / Narrate / Bleed / [deferred Stage 7]). v3 used "Phase 7" for the deferred prose stage, which collided with LORE Phase 7 = INTEGRATION; v4 reserves "Phase" for LORE and uses "Stage" for Radiant.

---

## Context

NEXUS today asks the storyteller LLM to confabulate off-stage character activity each turn, with heuristic instructions about narrative debt and ambient texture. There is no architectural guarantee that any specific character gets updated, no continuity beyond the context window, and no provenance — distant sirens in the prose are decoration, not the audible signature of a real package execution sitting in the database.

The proposal is a Bethesda-inspired off-screen behavior subsystem: a pipeline (`Resolve → Commit → Promote → Narrate → Bleed`) that simulates what every tracked entity does between player turns. Most state changes resolve deterministically in pure Python; a small subset is promoted to local-LLM judgment, then to frontier-model prose, then offered to the storyteller as an optional menu of perceivable ambient peripherals.

**Motivating test case:** an NPC the player forcefully interrogated fifty chunks ago protested that their life was over. Behind the scenes, a package on that NPC ticks through fifty chunks of pure state resolution. Eventually a branch fires that's high-magnitude enough to promote: the retaliation. Prose generated, persisted, never surfaced. Two chunks later the player is in an intimacy scene in an entirely different part of the city and the storyteller has the option of hearing sirens in the distance — or not. If they do, MEMNON has substrate for retrieval. If they don't, the dramatic irony lives in the database, available to inform any future scene where it matters.

---

## Pipeline Summary

| Stage | Cost class | What runs | When |
|---|---|---|---|
| **Resolve** (Stage 1) | Free (pure Python) | Evaluate templates against per-entity bindings; produce a `RadiantTickProposal` (no writes, no `tick_chunk_id` yet) | In-cycle, during a new LORE Phase 4.5 (between `DEEP_QUERIES` and `PAYLOAD_ASSEMBLY`) |
| **Commit** (Stage 2) | Free (SQL transaction) | Stamp `tick_chunk_id`, then atomically materialize the proposal into canonical tables (entity deltas, tag mutations, `world_events`, `radiant_resolutions`, enqueue narration jobs) | Inside the same transaction as accepted-chunk commit |
| **Clear** (Stage 3) | Local-LLM (batched) + deterministic | Event-based clearance runs in the commit transaction; semantic clearance runs post-commit, async, results available for next tick | Commit (event) + post-commit (semantic) |
| **Promote** (Stage 4) | Local-LLM (batched) | Decide which resolutions deserve frontier prose | Post-commit |
| **Narrate** (Stage 5) | Frontier-LLM, async via durable outbox | Generate prose for promoted resolutions; persist into `offscreen_narrations` (separate from `narrative_chunks`) | Async after commit; durable across process restart |
| **Bleed** (Stage 6) | Local-LLM at storyteller-time, hard 2s budget | Filter recent narrated resolutions for perceptibility; produce optional menu | LORE Phase 5 (`payload_assembly`), each player turn |
| **Stage 7 (deferred)** | — | Middle-tier journalistic prose | Metric-gated; see "Deferred — Radiant Stage 7" |

**Cost shape (load-bearing):** Resolve is free and runs at full breadth. Each downstream stage is more expensive per call but operates on a smaller surface. Frontier prose only generates for resolutions that survived two earlier gates.

---

## Load-Bearing Invariant: CommitRadiantTick

> **The resolver computes; only the accepted-chunk commit path writes.**

Resolve runs in-cycle during `LORE.process_turn()` for latency reasons, but every canonical write — entity deltas, tag mutations, `world_events`, `radiant_resolutions`, narration job enqueue — flows through the same transaction that promotes the incubator chunk to canon. This collapses three concerns into one seam:

- **Rollback.** Incubator rejection means the transaction never happened. Zero cleanup logic needed.
- **Idempotency.** Commit is keyed to the accepted tick via `UNIQUE (tick_chunk_id, template_id, binding_hash)` on `radiant_resolutions`. Regeneration cannot double-write.
- **Visibility.** Nothing canonical exists until acceptance, so warm-slice retrieval cannot see provisional state.

Two phases:

1. **In-cycle (LORE Phase 4.5)**: Resolve produces a `RadiantTickProposal` carried on `TurnContext.radiant_proposal`. No writes. The proposal carries `(template_id, binding_hash, bindings, state_delta, magnitude, ...)` *without* `tick_chunk_id` — that field is unknown at this point.
2. **Commit-time**: `CommitRadiantTick` runs inside the accepted-chunk commit transaction. The new chunk's id is generated by `insert_narrative_chunk` (returned at `commit_handler.py:394` / `commit_handler_sync.py:354`); every proposal row is stamped with that id, and the `UNIQUE (tick_chunk_id, template_id, binding_hash)` idempotency guard is enforced at write time.

**Exact hook locations (verified against current `main`):**
- **Async wrapper** (used only by tests): `nexus/api/commit_handler.py::commit_incubator_to_database` (L320). Transaction opens at L348. Insert `CommitRadiantTick` as **Step 8.5**: after `apply_state_updates(conn, state_updates)` returns at L420, before `clear_incubator(conn, session_id)` at L423.
- **Sync wrapper** (production path — see PR 3): `nexus/api/commit_handler_sync.py::commit_incubator_to_database_sync` (L233). Insert `CommitRadiantTick` after `apply_state_updates_sync(conn, state_updates)` at L415, before the incubator-clear `DELETE` at L418.
- The acceptance seam that *invokes* the sync commit wrapper lives in `nexus/api/narrative.py::_approve_narrative_impl` (L387), which calls `commit_incubator_to_database_sync` at L407.

---

## Settled Architecture

### Entity Identity Spine (Staged Super-Table)

A new `entities` table acts as the identity spine for polymorphic references. Existing subtype tables keep their primary keys unchanged; each gains a unique `entity_id` column FK'd to the spine. All new Radiant tables FK directly to `entities(id)` without a discriminator column. The existing six triplicate relationship/reference tables are NOT touched in this PR — they remain a stable wart with a deferred collapse plan.

The spine uses a dedicated `entity_kind` ENUM (distinct from the existing Python `apex_enums.py:EntityType`, which includes `'item'` — out of scope here):

```sql
-- spine-supported entity kinds (deliberately excludes 'item'; cross-link to apex_enums.py:41)
CREATE TYPE entity_kind AS ENUM ('character', 'faction', 'place');

-- the new identity spine: pure identity, no fields duplicated from subtype tables
CREATE TABLE entities (
  id           bigserial PRIMARY KEY,
  kind         entity_kind NOT NULL,
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_entities_kind ON entities (kind);

-- name stays on subtype tables (where it already lives and where character renames are
-- already handled via character_aliases). Polymorphic name access goes through a view:
CREATE VIEW entity_names_v AS
    SELECT e.id, e.kind, c.name
    FROM entities e
    JOIN characters c ON c.entity_id = e.id
    WHERE e.kind = 'character'
  UNION ALL
    SELECT e.id, e.kind, f.name
    FROM entities e
    JOIN factions f ON f.entity_id = e.id
    WHERE e.kind = 'faction'
  UNION ALL
    SELECT e.id, e.kind, p.name
    FROM entities e
    JOIN places p ON p.entity_id = e.id
    WHERE e.kind = 'place';
```

**Backfill pattern (lock-aware, staged):** A naive `ADD COLUMN ... UNIQUE REFERENCES entities(id) NOT NULL` plus backfill takes an AccessExclusive lock and validates the FK against every existing row in one shot. Save-slot databases are not multi-tenant prod, but slots with non-trivial row counts (`save_01` has the bulk of the canonical narrative) will stall noticeably. Use the staged pattern:

```sql
-- Stage A: nullable, FK created with NOT VALID (no full-table scan)
ALTER TABLE characters
  ADD COLUMN entity_id bigint REFERENCES entities(id) NOT VALID;
-- (and equivalents for factions, places)

-- Stage B: backfill in batches (Python migration; see below)
--   For each existing row in {characters, factions, places}:
--     INSERT INTO entities(kind) VALUES (...) RETURNING id;
--     UPDATE <subtype> SET entity_id = <new_id> WHERE id = <subtype_id>;

-- Stage C: validate the FK (scans existing rows once but doesn't block writes)
ALTER TABLE characters VALIDATE CONSTRAINT characters_entity_id_fkey;

-- Stage D: build the unique index concurrently, then promote it to a constraint
CREATE UNIQUE INDEX CONCURRENTLY ix_characters_entity_id_unique ON characters (entity_id);
ALTER TABLE characters
  ADD CONSTRAINT characters_entity_id_unique UNIQUE USING INDEX ix_characters_entity_id_unique;

-- Stage E: enforce NOT NULL (cheap once every row is populated)
ALTER TABLE characters ALTER COLUMN entity_id SET NOT NULL;
```

Because `scripts/migrate.py` is single-shot (it runs each migration file in one transaction with no inter-stage hooks), the backfill must be a **Python migration** (`migrations/018_radiant_schema.py`, following the precedent of `008_populate_mock_database.py`), not a `.sql` file. The Python migration can run each stage as its own transaction and emit batched UPDATEs for the backfill.

```sql
-- kind-correctness enforced by triggers (after Stage E)
CREATE TRIGGER trg_characters_entity_kind BEFORE INSERT OR UPDATE ON characters
  FOR EACH ROW EXECUTE FUNCTION ensure_entity_kind('character');
-- (and equivalents for factions and places)
```

**Cascade-semantics policy** (per-table, deliberate):
- `entity_tags.entity_id` → `ON DELETE CASCADE`. Tags die with the entity.
- `world_events.actor_entity_id` and `target_entity_id` → `ON DELETE RESTRICT`. Events outlive their participants; deletion requires explicit reckoning.
- `world_event_entities.entity_id` → `ON DELETE RESTRICT`. Same rationale.
- `radiant_resolutions.actor_entity_id` → `ON DELETE RESTRICT`.

Future polymorphic tables follow this pattern.

**Compatibility views** over the existing triplicate tables, so new code reads through the unified identity surface without forcing legacy rewrite:

```sql
-- read-only convenience view over the three chunk-reference tables
CREATE VIEW chunk_entity_references_v AS
  SELECT ccr.chunk_id, c.entity_id, ccr.reference::text AS reference_type
  FROM chunk_character_references ccr
  JOIN characters c ON c.id = ccr.character_id
UNION ALL
  SELECT cfr.chunk_id, f.entity_id, NULL::text AS reference_type
  FROM chunk_faction_references cfr
  JOIN factions f ON f.id = cfr.faction_id
UNION ALL
  SELECT pcr.chunk_id, p.entity_id, pcr.reference_type::text
  FROM place_chunk_references pcr
  JOIN places p ON p.id = pcr.place_id;

-- equivalent view over the three relationship tables → entity_relationships_v
```

**Deferred legacy collapse triggers** (revisit when one becomes true):
1. A fourth real entity kind appears.
2. `chunk_entity_references_v` or `entity_relationships_v` becomes a frequent write target rather than just a read convenience.
3. Grep of the codebase shows repeated `UNION ALL` or kind-branching logic spreading into many modules.

Until then, the six triplicate tables stay. They are awkward but stable; their wrongness does not compound.

### Tag System

```sql
-- enum for application provenance (includes auto_registered for the Vocabulary Growth contract below)
CREATE TYPE entity_tag_source_kind AS ENUM (
  'authored', 'llm_generated', 'system', 'template', 'auto_registered'
);

-- registry (unchanged)
CREATE TABLE tags (
  id                       bigserial PRIMARY KEY,
  tag                      text UNIQUE NOT NULL,
  category                 text NOT NULL,
  is_ephemeral             boolean NOT NULL DEFAULT false,
  clearance_kind           text,                   -- 'event' | 'semantic' | 'authored'; NULL when not ephemeral
  reapplication_policy     text,                   -- 'new_row' | 'extend_expiry' | 'replace'
  clear_on                 jsonb,
  synonym_for              bigint REFERENCES tags(id),
  deprecated               boolean NOT NULL DEFAULT false,
  description              text,
  created_at               timestamp DEFAULT now(),
  CHECK (is_ephemeral = (clearance_kind IS NOT NULL))
);

-- application: single FK to entities, no entity_kind discriminator
CREATE TABLE entity_tags (
  id                     bigserial PRIMARY KEY,
  entity_id              bigint NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  tag_id                 bigint NOT NULL REFERENCES tags(id),
  applied_at             timestamp NOT NULL DEFAULT now(),
  applied_at_world_time  timestamptz,
  clear_on_override      jsonb,
  cleared_at             timestamp,                 -- NULL means current
  template_id            text,                      -- if applied by a template
  source_kind            entity_tag_source_kind NOT NULL,
  UNIQUE (entity_id, tag_id, applied_at)
);

-- view excludes cleared, deprecated, synonyms; joins entities for kind
-- (callers that need entity_name JOIN entity_names_v explicitly)
CREATE VIEW entity_tags_current AS
  SELECT et.id AS entity_tag_id, et.entity_id, e.kind AS entity_kind,
         t.tag, t.category, t.is_ephemeral, t.clearance_kind,
         et.applied_at, et.applied_at_world_time, et.source_kind, et.template_id
  FROM entity_tags et
  JOIN entities e ON e.id = et.entity_id
  JOIN tags t ON t.id = et.tag_id
  WHERE t.deprecated = false
    AND et.cleared_at IS NULL
    AND (t.synonym_for IS NULL);

-- audit log
CREATE TABLE tag_clearance_log (
  id                      bigserial PRIMARY KEY,
  entity_tag_id           bigint NOT NULL REFERENCES entity_tags(id),
  cleared_at              timestamp NOT NULL DEFAULT now(),
  cleared_at_world_time   timestamptz,
  mechanism               text NOT NULL,                 -- 'event' | 'semantic' | 'authored'
  triggering_event_id     bigint REFERENCES world_events(id),
  justification           jsonb,
  source_chunk_id         bigint REFERENCES narrative_chunks(id)
);
```

**Locked-in choices:**
- 3NF registry + join + view
- Single `tags` table with `is_ephemeral` boolean
- Surrogate `entity_tags.id` (not composite key)
- `entity_id REFERENCES entities(id)` — single FK, no discriminator column, real cascade
- `cleared_at` column for cheap current-view reads
- Three clearance kinds: `event` / `semantic` / `authored`
- No clock-based expiry
- `source_kind` as a real PG enum (`entity_tag_source_kind`) — values include `'auto_registered'` so apex-sourced unknowns satisfy the Vocabulary Growth contract without sneaking a string in past the schema

### Event Stream

```sql
-- enums for event provenance + participant roles (replacing the v3 'text' columns)
CREATE TYPE event_source_kind AS ENUM (
  'apex', 'resolver', 'narrator', 'bleed', 'authored'
);
CREATE TYPE event_role_kind AS ENUM (
  'actor', 'target', 'observer', 'beneficiary', 'witness'
);

CREATE TABLE event_types (
  type           text PRIMARY KEY,
  category       text NOT NULL,
  severity       text,
  description    text,
  deprecated     boolean NOT NULL DEFAULT false,
  synonym_for    text REFERENCES event_types(type)
);

CREATE TABLE world_events (
  id                     bigserial PRIMARY KEY,
  event_type             text NOT NULL REFERENCES event_types(type),
  tick_chunk_id          bigint NOT NULL REFERENCES narrative_chunks(id),
  narration_chunk_id     bigint REFERENCES offscreen_narrations(id),

  -- single FK actor/target; no entity_kind columns
  actor_entity_id        bigint REFERENCES entities(id) ON DELETE RESTRICT,
  target_entity_id       bigint REFERENCES entities(id) ON DELETE RESTRICT,

  -- location stays place-specific (per GPT-5.5-Pro): spatial semantics, not "entity" semantics
  location_id            bigint REFERENCES places(id) ON DELETE RESTRICT,

  -- world_time joined from chunk_metadata at read; see "World Time Denormalization"
  world_layer            world_layer_type,
  source                 event_source_kind NOT NULL,
  changed_fields         text[] NOT NULL DEFAULT '{}',                   -- controlled vocab, auto-derived from Pydantic StateUpdate models
  magnitude              numeric(4,3),
  resolution_id          bigint REFERENCES radiant_resolutions(id),
  payload                jsonb NOT NULL DEFAULT '{}',
  superseded_by_event_id bigint REFERENCES world_events(id),
  created_at             timestamptz DEFAULT now()
);

-- participation join table (multi-entity events): also single FK
CREATE TABLE world_event_entities (
  event_id      bigint NOT NULL REFERENCES world_events(id) ON DELETE CASCADE,
  role          event_role_kind NOT NULL,
  entity_id     bigint NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
  PRIMARY KEY (event_id, role, entity_id)
);
```

**`world_layer_type` precondition:** the Python enum `WorldLayerType` exists at `apex_enums.py:196` (`primary`, `flashback`, `dream`, ...), but the *Postgres* type `world_layer_type` is not declared in any tracked migration (only referenced as a JSONB field in `migrations/005_add_incubator_choice_object.sql`). PR 0 must confirm whether `world_layer_type` already exists in `NEXUS_template`; if not, prepend a `CREATE TYPE world_layer_type AS ENUM (...)` to migration 018 (mirroring `WorldLayerType` values) before any column that uses it.

**Locked-in choices:**
- Append-only; supersession only for in-world retcons
- `tick_chunk_id` and `narration_chunk_id` split — no overloaded `chunk_id`
- Single-FK polymorphism: `actor_entity_id`, `target_entity_id` FK to `entities`; no `_kind` columns
- `location_id REFERENCES places(id)` stays as a deliberate exception — places have spatial semantics distinct from entity-ness; if a place participates as an actor or target, use `actor_entity_id`/`target_entity_id`
- `world_event_entities` join table replaces flat actor/target columns for multi-participant events; `role` is an enum so typos surface at INSERT time
- `source` is an enum (`event_source_kind`), not free text
- `changed_fields text[]` with controlled vocab auto-derived from `StateUpdate` Pydantic models (see `apex_schema.py:631`)
- `magnitude` for Promote scoring without unpacking payload
- `resolution_id` FK back to `radiant_resolutions` when resolver-sourced
- `world_layer` filtering keeps dream/flashback events out of resolver's recent-event window
- Event-type registry mirrors tags
- Writer must validate every `entity_id` exists in `entities` before insert (now a real FK, so violation surfaces as a SQL error rather than silent rot — consistent with the project's "errors surface visibly" preference in `CLAUDE.md`)

### Radiant Resolutions

```sql
CREATE TABLE radiant_resolutions (
  id                  bigserial PRIMARY KEY,
  tick_chunk_id       bigint NOT NULL REFERENCES narrative_chunks(id),
  template_id         text NOT NULL,
  binding_hash        text NOT NULL,                  -- stable hash of bindings dict
  actor_entity_id     bigint REFERENCES entities(id) ON DELETE RESTRICT,
  priority            integer NOT NULL,
  magnitude           numeric(4,3),
  state_delta         jsonb NOT NULL,
  brief               text,                           -- deterministic non-literary one-liner (PR 3)
  event_ids           bigint[],                       -- world_events rows produced by this resolution
  promotion_status    text NOT NULL DEFAULT 'pending',  -- 'pending' | 'promoted' | 'skipped'
  promotion_verdict   jsonb,
  narration_status    text NOT NULL DEFAULT 'none',   -- 'none' | 'queued' | 'leased' | 'succeeded' | 'failed'
  narration_chunk_id  bigint REFERENCES offscreen_narrations(id),

  -- bleed surfacing bookkeeping (Codex)
  last_offered_chunk_id   bigint REFERENCES narrative_chunks(id),
  offer_count             integer NOT NULL DEFAULT 0,
  first_surfaced_chunk_id bigint REFERENCES narrative_chunks(id),

  created_at          timestamptz DEFAULT now(),
  UNIQUE (tick_chunk_id, template_id, binding_hash)  -- idempotency guard, enforced at Stage 2 (Commit)
);
```

Note: `tick_chunk_id` is `NOT NULL`, but the in-cycle `RadiantTickProposal` carries no `tick_chunk_id` — the field is stamped during `CommitRadiantTick` after `insert_narrative_chunk` returns the new chunk's id at `commit_handler.py:394` / `commit_handler_sync.py:354`. The `UNIQUE` constraint therefore fires at write time, not at proposal time.

### Narration Outbox

```sql
CREATE TABLE radiant_narration_jobs (
  id              bigserial PRIMARY KEY,
  resolution_id   bigint NOT NULL REFERENCES radiant_resolutions(id),
  slot            text NOT NULL,                       -- save slot identifier
  state           text NOT NULL DEFAULT 'queued',      -- 'queued' | 'leased' | 'succeeded' | 'failed'
  attempts        integer NOT NULL DEFAULT 0,
  available_at    timestamptz DEFAULT now(),
  lease_until     timestamptz,
  locked_by       text,
  last_error      text,
  provider        text,
  model_ref       text,
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);
```

Durable outbox surviving process restart. Dispatched via `FastAPI BackgroundTasks` — mirror the established pattern at `nexus/api/narrative.py:281` and `nexus/api/storyteller.py:561, 666`. Concretely: after `commit_incubator_to_database_sync` returns successfully in `_approve_narrative_impl`, call `background_tasks.add_task(drain_narration_outbox, slot)`. Also drainable via standalone CLI: `python -m nexus.agents.radiant.worker --slot 5`.

### Off-Screen Narration Storage (Structural Visibility Separation)

```sql
CREATE TABLE offscreen_narrations (
  id              bigserial PRIMARY KEY,
  resolution_id   bigint NOT NULL REFERENCES radiant_resolutions(id),
  tick_chunk_id   bigint NOT NULL REFERENCES narrative_chunks(id),
  -- world_time joined from chunk_metadata at read
  world_layer     world_layer_type,                   -- usually 'primary'; not chronologically counted
  text            text NOT NULL,
  perceptual_descriptor jsonb,                        -- thin descriptor consumed by Bleed (sensory channel + brief)
  embedding_status text DEFAULT 'pending',            -- own embedding pipeline; MEMNON indexes both tables
  created_at      timestamptz DEFAULT now()
);
```

`narrative_chunks` is always player-visible; `offscreen_narrations` never is. MEMNON's retrieval logic queries both tables with explicit semantic intent (warm-slice → `narrative_chunks` only; off-screen retrieval → both, with `offscreen_narrations` clearly labeled). `narrative_view.world_time` does NOT count off-screen narrations toward chronological advancement.

**MEMNON safety claim, sharpened:** `nexus/agents/memnon/memnon.py::get_recent_chunks` (L1486) already queries only `narrative_chunks` — no change needed there. The real risk surface is `query_memory` and the underlying `SearchManager`, which run hybrid (vector + text) retrieval. PR 0 task: confirm `query_memory` and `SearchManager` never union or join `offscreen_narrations` into warm-slice results, and add an integration test that asserts the warm slice returned from `query_memory` is disjoint from `offscreen_narrations`.

### Bleed Selector

**Local LLM produces a menu, never a decision.** Perceptibility filtering only: given the player's current location, time, activity — which recent narrated off-screen events could plausibly register at all? Output is a curated list of N candidates (typically N ≤ 3), each annotated with sensory channel (auditory, news fragment, secondhand mention, faction graffiti) and a thin perceptual descriptor — *not* the narrator's full prose.

**Hook point.** Bleed runs at the start of LORE Phase 5 (`assemble_context_payload`, `nexus/agents/lore/utils/turn_cycle.py:489`). Its output populates `turn_context.bleed_menu`, which `assemble_context_payload` then reads when building the payload. Concretely, the Bleed entry point is a new method on `TurnCycleManager` invoked from `assemble_context_payload` before payload assembly proper begins.

**Latency budget: hard 2-second cap, enforced via `asyncio.wait_for`.** If the local-LLM call exceeds budget, the bleed menu for this turn is empty and the overrun logged loudly. Empty bleed is a valid outcome.

**Candidate query is typed**: reads from `radiant_resolutions` JOIN `world_events` JOIN `offscreen_narrations` with filters on age, location proximity, sensory plausibility, surfacing history. The local LLM call uses `LocalLLMManager.structured_query(prompt, response_model)` (`nexus/agents/lore/utils/local_llm.py:642`) — signature is `(prompt, response_model, *, temperature=None, max_tokens=None, system_prompt=None)`. The existing helper handles SDK-vs-fallback parsing; no new structured-output plumbing required.

**Surfacing bookkeeping** prevents nag (Codex): `last_offered_chunk_id`, `offer_count`, `first_surfaced_chunk_id` (on `radiant_resolutions`). Distinguish "offered to storyteller" from "actually surfaced" — only the latter creates a visible-world surfacing record.

**Payload framing:** "ambient peripherals available — ignore any or all, render at any density from overt to invisible." Zero is a valid inclusion count.

### Tick, Resolver Firing, World Time

- **Tick = the *accepted* player-visible chunk's id**, not the latest `narrative_chunks` row. The id is generated at `commit_handler.py:394` / `commit_handler_sync.py:354` and stamped onto every Radiant write in the same transaction.
- **Resolve runs in-cycle** during a new **LORE Phase 4.5**, inserted between `DEEP_QUERIES` (Phase 4) and `PAYLOAD_ASSEMBLY` (Phase 5). Pure Python; produces `RadiantTickProposal` carried on `TurnContext.radiant_proposal`; no writes.
- **CommitRadiantTick** runs as Step 8.5 inside `commit_incubator_to_database` (L320) / `commit_incubator_to_database_sync` (L233), between the existing `apply_state_updates*` call and `clear_incubator`. All canonical writes happen here.
- **Clear (event)** runs in the same commit transaction as the triggering event.
- **Clear (semantic)** runs post-commit, async, batched, filtered to entities with recent relevant events.
- **Promote** runs post-commit, async, batched per tick.
- **Narrate** is async via durable outbox. Bleed reads only `state='succeeded'` narrations + deterministic briefs.
- **Bleed** runs synchronously at storyteller-time (LORE Phase 5) with hard latency budget.

### World Time Denormalization

`world_time` denormalized onto **`chunk_metadata`**, not `world_events`. The cumulative-SUM of `narrative_view.world_time` means a `time_delta` edit on chunk K invalidates every later event row — fan-out unbounded. Per-chunk denormalization keeps fan-out bounded to "every chunk from K to current" — still O(N) on edits but materialized once per chunk, not per event.

```sql
ALTER TABLE chunk_metadata ADD COLUMN world_time timestamptz;

CREATE FUNCTION refresh_world_time_from_chunk(changed_chunk_id bigint)
RETURNS void AS $$
  -- recompute world_time for changed_chunk_id and every chunk_id > changed_chunk_id
  -- (cumulative SUM of time_delta from the canonical baseline)
$$ LANGUAGE sql;

-- trigger on chunk_metadata.time_delta change updates affected chunks only
```

`world_events.world_time` becomes a JOIN: `SELECT we.*, cm.world_time FROM world_events we JOIN chunk_metadata cm ON we.tick_chunk_id = cm.chunk_id`. Stamped only at accepted commit. Off-screen narrations never advance chronology.

### EntityRef Helper (Now Thin, Backed by Real FK)

```python
class EntityRef(BaseModel):
    id: int                                     # FK to entities.id
    kind: Optional[EntityKind] = None           # populated on read from entities.kind
    name: Optional[str] = None                  # populated on read via entity_names_v
                                                # (never duplicated on entities table)

    def canonical_key(self) -> str:
        return f"entity:{self.id}"
```

With the identity spine in place, `EntityRef.validate_exists()` is no longer needed at write time — Postgres enforces it via the FK. `EntityRef` survives as a typed read-side convenience: it's what binding composers, condition primitives, and bleed candidates carry. The `name` field is populated at read time from `entity_names_v` (which UNION-joins through the subtype tables); the spine itself carries no name column, so there's no drift surface between subtype names and spine names.

### Vocabulary Growth Contract

When a tag or event_type is referenced that the registry hasn't seen:
- **Resolver-sourced**: fail loudly. Templates must register their vocabulary before use.
- **Apex-sourced**: auto-register with `source_kind='auto_registered'` (a real enum value on `entity_tag_source_kind`) and `description='AUTO: pending review'`. Surfaces in periodic curation.

### ALWAYS-Fallback Invariant for Templates

Every template MUST end with an `ALWAYS`-conditioned branch. Validated at template-load time via pytest fixture.

### Sliding-Window Binding Scope

Binding composer filters to recently-relevant entities: (referenced in `chunk_character_references` in last N chunks) ∪ (has an active ephemeral tag) ∪ (has un-superseded `world_events` in last N chunks). N config-tunable via `nexus.toml` `[radiant.binding] window_chunks`. Default suggested: 30.

### `nexus.toml` Section Layout

Follow the established nesting style from `[lore]` / `[lore.token_budget]` and `[memnon.retrieval.hybrid_search.weights_by_query_type.character]`. The proposed Radiant sections:

```toml
[radiant]
enabled = true

[radiant.binding]
window_chunks = 30

[radiant.narration]
mode = "async"                                          # "async" | "sync"
provider = "anthropic"
model_ref = "@anthropic.default"                        # resolved via [global.model.api_models]

[radiant.bleed]
latency_budget_ms = 2000
max_candidates = 3

[radiant.promote]
provider = "local"
```

Every model reference uses the `@provider.role` syntax that the existing config loader resolves against `[global.model.api_models]` — never a hardcoded ID in runtime code (per `CLAUDE.md` "Testing Defaults").

### Things Deliberately Out of Scope

- Replacing the storyteller
- Real-time simulation
- Full Bethesda parity (no NPC pathing, no real-time combat)
- Procedural template authoring at runtime
- Items as first-class entities (NEXUS is not an inventory game)
- Full collapse of legacy triplicate tables (deferred per trigger list above)
- Event-sourcing inversion (Pattern C from round-1 review)

---

## Resolved Open Items

### [OPEN 1] Narrate sync/async — RESOLVED: Async with durable outbox

Unanimous. `radiant_narration_jobs` table; enqueued inside accepted-commit transaction; `FastAPI BackgroundTasks` triggers a draining worker function (mirroring `narrative.py:281` and `storyteller.py:561, 666`); standalone CLI for catch-up; `[radiant.narration] mode = "async" | "sync"` config switch. Promoted resolutions durable immediately; narration eventually durable. Bleed reads only succeeded + deterministic briefs.

### [OPEN 2] Producer wiring — RESOLVED: Pattern B (dedicated event writer)

Unanimous. `nexus/agents/radiant/events.py` exports `emit_state_updates_events(state_updates, tick_chunk_id, conn)` and `emit_event(...)`. Both `commit_incubator_to_database` (L320, async) and `commit_incubator_to_database_sync` (L233, sync — the production path) call into it at Step 8.5. Direct INSERTs to `world_events` forbidden by convention. Field-mapping from Pydantic `StateUpdate` models lives as a data table, not branchy code.

### [OPEN 3] Entity super-table — RESOLVED: Staged identity spine (round-2 consensus)

Round 1's framing biased reviewers toward "defer" by stating it as user direction. Round 2's neutral re-framing converged on **Option C: adopt the `entities` super-table now as an identity spine, but do not renumber existing PKs or collapse the legacy triplicate tables**. Implementation locked into the "Entity Identity Spine" section above, with the staged lock-aware backfill pattern called out so an implementer doesn't trip the naive ADD-COLUMN-with-FK-and-NOT-NULL lock storm.

The round-1 verdict ("defer + EntityRef") was load-bearing on the framing — when reviewers were free to propose a third option, both independently landed on the staged shape. EntityRef survives as a thin read-side convenience rather than the primary safety mechanism; Postgres FKs do the heavy lifting.

### [OPEN 4] Bootstrap blocker — RESOLVED: Moot

PR #191 merged to `main` as `44aedba`. All phases unblocked. PR 2's structural split (hydration / dry-pass vs. canonical write wiring) retained for cognitive surface reasons.

### [OPEN 5] Radiant Stage 7 — RESOLVED: Defer Stage 7, promote deterministic briefs into PR 3

Unanimous. Deterministic briefs (pure string formatting from known fields → `radiant_resolutions.brief`) land in PR 3. Radiant Stage 7's actual LLM prose stage fires only when ≥ 2 of 3 instrumented counters deteriorate over a 50-tick playtest: Promote pass rate < 2%, bleed candidate scarcity < 3/scene, MEMNON retrieval misses on player-described off-screen events.

### [OPEN 6] Denormalized summary columns — RESOLVED: `changed_fields text[]` only

Unanimous. No fixed boolean columns. Controlled vocabulary auto-generated from `StateUpdate` Pydantic models (`apex_schema.py:631`); build-step generator produces canonical constants. GIN-indexed. Resolver primitive takes a tuple: `recent_event(changed_fields_any_of=('character.current_location', 'character.activity'), actor=X)`.

### [OPEN 7] `world_time` denormalization staleness — RESOLVED: Denormalize onto `chunk_metadata`

Per-chunk, not per-event. Stamped only at accepted commit. `world_events.world_time` becomes a JOIN at read time. Off-screen narrations never advance chronology.

---

## Phased Delivery

### PR 0 — Seam Audit & Invariants

- Confirm the production commit path is `nexus/api/narrative.py::_approve_narrative_impl` (L387) → `commit_incubator_to_database_sync` (L233). The async sibling `commit_incubator_to_database` (L320) is test-only today; document this in PR 3 commit hook prose.
- Confirm `query_memory` and `SearchManager` retrieval surfaces never join or union `offscreen_narrations` into warm-slice results; add an integration test asserting the warm slice is disjoint from `offscreen_narrations`. (Note: `memnon.py::get_recent_chunks` at L1486 is already safe — it queries only `narrative_chunks`.)
- Update `nexus/agents/memnon/memnon.py::execute_readonly_sql` allowed-tables list (L492-495 — current set: `{"characters", "episodes", "seasons", "events", "factions", "places", "chunk_metadata", "narrative_chunks"}`). Additions: `entities`, `entity_names_v`, `entity_tags_current`, `world_events`, `world_event_entities`, `radiant_resolutions`, `offscreen_narrations`, `event_types`, `tags`. Excluded (internal-only): `radiant_narration_jobs`, `tag_clearance_log`, raw `entity_tags`.
- Confirm `world_layer_type` Postgres ENUM exists in `NEXUS_template`. If not, prepend `CREATE TYPE world_layer_type AS ENUM (...)` to `migrations/018_*` mirroring `apex_enums.py:WorldLayerType`.
- Note that `chunk_workflow.py` is *not* on the commit path — it manages downstream embedding state transitions only. Do not hook `CommitRadiantTick` there.

### PR 1 — Substrate + Schema + Identity Spine

- Move substrate from `temp/radiant/behavior_substrate.py` to `nexus/agents/radiant/`
- Port `EVADE_PURSUERS`, `PURSUE_GHOST_LEAD`, `MAINTAIN_COVER` from JSX simulator
- Extend condition library: `has_relationship_of_type`, `count_co_located`, `since_last_event`, `faction_member`, `relative_orbit_distance`, `recent_event(changed_fields_any_of=..., actor=...)`
- Add ALWAYS-fallback validator (pytest fixture)
- **Migration `018_radiant_schema.py`** (Python, not SQL — `scripts/migrate.py` is single-shot per file; the staged FK backfill needs multi-transaction control. Precedent: `008_populate_mock_database.py`):
  - **Type prerequisites**: `entity_kind`, `entity_tag_source_kind`, `event_source_kind`, `event_role_kind`. If `world_layer_type` doesn't already exist in template (per PR 0 audit), create it too.
  - **Identity spine**: `entities` table (id, kind, is_active, timestamps — no name column) + `entity_id` columns on `characters`/`factions`/`places`, added via the staged `NOT VALID → backfill → VALIDATE → CONCURRENTLY UNIQUE INDEX → SET NOT NULL` pattern + kind-correctness triggers
  - **Polymorphic name view**: `entity_names_v` (UNION over subtype tables; spine has no duplicated name field)
  - **Compatibility views**: `chunk_entity_references_v`, `entity_relationships_v`
  - **Tag system**: `tags`, `entity_tags` (single FK), `entity_tags_current` view, `tag_clearance_log`
  - **Event stream**: `event_types`, `world_events` (single-FK actor/target, `source` + `world_event_entities.role` as real enums), `world_event_entities`
  - **Radiant tables**: `radiant_resolutions` (with `UNIQUE` idempotency key + surfacing bookkeeping columns), `radiant_narration_jobs`, `offscreen_narrations`
  - **Time denormalization**: `chunk_metadata.world_time` column + `refresh_world_time_from_chunk` trigger function
- `EntityRef` Pydantic helper in `nexus/agents/radiant/entity_ref.py` (thin read-side type; uses `EntityKind` enum mirroring the new `entity_kind` Postgres type)
- Generator script: derive `changed_fields` vocabulary from `apex_schema.py::StateUpdates` Pydantic models (`apex_schema.py:631`)
- Backfill durable tags from existing entity records (LLM-assisted; reviewed before commit)
- Seed initial `event_types` vocabulary
- Demo: `python -m nexus.agents.radiant.demo` runs four templates against synthetic `WorldState`

### PR 2 — Hydration + Dry-Pass Resolver (no canonical writes)

- `hydrate_world_state(tick_chunk_id) -> WorldState`. One bulk SELECT per source.
- Sliding-window binding composer for `ACTOR`-only templates
- Resolver loop produces `RadiantTickProposal` (no `tick_chunk_id` in the proposal — see Stage 1 note above)
- **New LORE Phase 4.5**: add `TurnPhase.RADIANT_RESOLVE = "radiant_resolve"` to `turn_context.py:12` enum; insert phase between `DEEP_QUERIES` (Phase 4) and `PAYLOAD_ASSEMBLY` (Phase 5) in `lore.py::process_turn` (L289+); add corresponding `TurnCycleManager` method invoked from there.
- **Extend `TurnContext`** (`turn_context.py:24-41`, a `@dataclass`) with two fields:
  - `radiant_proposal: Optional["RadiantTickProposal"] = None`
  - `bleed_menu: List["BleedCandidate"] = field(default_factory=list)`
- `[radiant]` section in `nexus.toml` (see "`nexus.toml` Section Layout" above)
- **No canonical writes yet.** Proposal is buffered, inspectable, but does not mutate any table
- Verification: real turn against `save_01`; storyteller output identical to control; proposal contents validated

### PR 3 — CommitRadiantTick + Promote + Narrate + Clear

- **`CommitRadiantTick` writer**: Step 8.5 inside `commit_incubator_to_database_sync` (L233 — the production path; insert between `apply_state_updates_sync` at L415 and incubator clear at L418) and parity inside `commit_incubator_to_database` (L320 — async, test-only; insert between `apply_state_updates` at L420 and `clear_incubator` at L423). Both call into the unified event writer in `nexus/agents/radiant/events.py`.
- **Stamp `tick_chunk_id`** on every proposal row at this step, after `insert_narrative_chunk` returns the new chunk id.
- Promote discriminator: `LocalLLMManager.structured_query(prompt, PromotionVerdict)` (existing API at `local_llm.py:642`). Fail loudly on malformed local-model output.
- Deterministic brief generator → `radiant_resolutions.brief`.
- Frontier narration via durable outbox; trigger drain via `BackgroundTasks` from `_approve_narrative_impl` after commit returns; standalone CLI worker for catch-up.
- Narrator persistence to `offscreen_narrations` (not `narrative_chunks`); embedding pipeline shared with MEMNON.
- Clear (event) in commit transaction; Clear (semantic) post-commit async, batched, filtered.
- `tag_clearance_log` rows with justification.
- Instrumented counters for the Radiant Stage 7 trigger metrics.
- Verification: engineered fifty-chunk scenario (motivating test case), idempotency, incubator rejection, warm-slice contamination, local-LLM failure, async-worker state transitions.

### PR 4 — Bleed Selector + Storyteller Integration

- Bleed selector wired into LORE Phase 5 (`assemble_context_payload`, `turn_cycle.py:489`); reads `turn_context.bleed_menu` populated by a new selector method invoked at the start of that phase.
- Typed candidate query over `radiant_resolutions` ⋈ `world_events` ⋈ `offscreen_narrations`.
- Hard 2-second latency budget enforced via `asyncio.wait_for`; overrun = empty menu + loud log.
- Surfacing bookkeeping increments.
- Menu injected into payload with framing "ambient peripherals — optional, ignore freely, render at any density".
- System-prompt edit at `lore_system_prompt.md:253-265`.
- Verification: apt-bleed + null-bleed + spoiler-boundary + chronology tests.

### Radiant Stage 7 — Middle-Tier Journalistic Prose (Deferred, Metric-Gated)

Fires only when ≥ 2 of 3 instrumented counters deteriorate over a 50-tick playtest. (Renamed from "Phase 7" in v3 to disambiguate from LORE turn-cycle Phase 7 = INTEGRATION.)

### Deferred — Legacy Triplicate Table Collapse

Revisit when: fourth real entity kind appears, compatibility view becomes write target, or repeated UNION/kind-branching spreads into many modules.

---

## Critical Files / Integration Points

**LORE turn cycle**
- `nexus/agents/lore/lore.py:289` — `process_turn`; new LORE Phase 4.5 inserts here
- `nexus/agents/lore/utils/turn_context.py:12-41` — `TurnPhase` enum (add `RADIANT_RESOLVE`) and `TurnContext` dataclass (add `radiant_proposal`, `bleed_menu`)
- `nexus/agents/lore/utils/turn_cycle.py:489` — `assemble_context_payload` (LORE Phase 5); Bleed selector hooks at the start
- `nexus/agents/lore/utils/local_llm.py:642` — `structured_query(prompt, response_model, *, temperature=None, max_tokens=None, system_prompt=None)` — used by Promote, Clear (semantic), Bleed

**Commit path (production = sync)**
- `nexus/api/narrative.py:281` — existing `BackgroundTasks` pattern to mirror
- `nexus/api/narrative.py:387` — `_approve_narrative_impl`; acceptance seam that invokes the commit
- `nexus/api/narrative.py:407` — calls `commit_incubator_to_database_sync`
- **`nexus/api/commit_handler_sync.py:233`** — `commit_incubator_to_database_sync`; `CommitRadiantTick` inserts at Step 8.5 (after `apply_state_updates_sync` at L415, before incubator clear at L418)
- `nexus/api/commit_handler_sync.py:354` — where the new chunk id is created in the sync path
- **`nexus/api/commit_handler.py:320`** — `commit_incubator_to_database`; async parity hook (Step 8.5 between L420 and L423)
- `nexus/api/commit_handler.py:394` — async path's chunk-id creation point
- `nexus/api/db_converters.py` — reference resolution only; NOT the StateUpdates apply path

**Not on the commit path**
- `nexus/api/chunk_workflow.py` — narrative-chunk state machine (`DRAFT/PENDING_REVIEW/FINALIZED/EMBEDDED`); downstream embedding only. Do not hook here.

**Schema sources**
- `nexus/agents/logon/apex_schema.py:631` — `StateUpdates` Pydantic models (source for `changed_fields` vocab)
- `nexus/agents/logon/apex_enums.py:41` — existing `EntityType` enum (includes `'item'`); spine declares its own narrower `entity_kind`
- `nexus/agents/logon/apex_enums.py:196` — `WorldLayerType` (Python); `world_layer_type` Postgres ENUM presence to be confirmed in PR 0

**MEMNON**
- `nexus/agents/memnon/memnon.py:1486` — `get_recent_chunks` (already `narrative_chunks`-only; no change needed)
- `nexus/agents/memnon/memnon.py::query_memory` and `SearchManager` — PR 0 audit target (must not union `offscreen_narrations`)
- `nexus/agents/memnon/memnon.py:469-538` — `execute_readonly_sql`; whitelist at L492-495 needs additions per PR 0
- `nexus/agents/memnon/utils/content_processor.py:214` — reference; new `store_offscreen_narration` wrapper writes to `offscreen_narrations`

**Background dispatch (BackgroundTasks pattern)**
- `nexus/api/narrative.py:281` — `background_tasks.add_task(generate_narrative_async, ...)`
- `nexus/api/storyteller.py:561, 666` — `background_tasks.add_task(manager.finalize_turn, ...)`
- Mirror in `_approve_narrative_impl` post-commit to drain the narration outbox

**Config + system prompt**
- `nexus.toml` — new `[radiant]`, `[radiant.binding]`, `[radiant.narration]`, `[radiant.bleed]`, `[radiant.promote]` sections; use `@provider.role` syntax per `[global.model.api_models]` registry
- `nexus/agents/lore/lore_system_prompt.md:253-265` — minor edit in PR 4

**New artifacts**
- `migrations/018_radiant_schema.py` — Python migration (multi-transaction; SQL alone insufficient for staged FK backfill)
- New module: `nexus/agents/radiant/` (substrate, `events.py` writer, `entity_ref.py`, `worker.py`, `demo.py`)

---

## Verification Approach

All tests use real LLM calls, no mocks (per `CLAUDE.md` testing philosophy).

- **PR 0:** Integration test asserting `query_memory` warm-slice is disjoint from `offscreen_narrations`; `execute_readonly_sql` whitelist updated and tested with a SELECT against each new allowed table; `world_layer_type` confirmed in template.
- **PR 1:** Substrate demo runs against four templates; migration applies cleanly via `scripts/migrate.py --slot 5` (or `--template` first); entity spine backfill validated (every existing character/faction/place has an `entity_id`; staged FK validation succeeded); kind-enforcement triggers tested; compatibility views return expected unions; durable-tag backfill reviewed.
- **PR 2:** Dry-pass against `save_01`; proposal contents inspected; storyteller output identical to control. Verify `TurnContext.radiant_proposal` carries no `tick_chunk_id` at this phase.
- **PR 3:** Engineered fifty-chunk motivating scenario (interrogated NPC → fifty ticks → retaliation prose persisted to `offscreen_narrations`, never surfaced); idempotency (regeneration cannot double-write — UNIQUE key fires); rejection (incubator rejection rolls everything back, including the Step 8.5 writes); warm-slice contamination (none); local-LLM failure (Promote fails loud); async-worker state transitions (`queued → leased → succeeded|failed`).
- **PR 4:** Apt-bleed (audible peripheral surfaces in distant scene); null-bleed (irrelevant resolutions produce empty menu); spoiler-boundary (resolutions before the player's current world-time are eligible; future resolutions are not); chronology tests (`offscreen_narrations` never advance `narrative_view.world_time`); latency-budget overrun produces empty menu and logs loudly.

---

## v3 → v4 Change Log

1. **Hook seams corrected.** `CommitRadiantTick` hooks the *transaction-wrapping* functions (`commit_incubator_to_database` L320 async; `commit_incubator_to_database_sync` L233 sync) at Step 8.5, not the `apply_state_updates*` workers at L223/L451.
2. **Sync path called out as production.** Only `narrative.py:407` calls a commit function in production code, and it calls the sync variant. Async kept in parity for tests.
3. **`chunk_workflow.py` removed from PR 0 audit.** It is not on the commit path; replaced with an audit of `narrative.py::_approve_narrative_impl` (L387).
4. **Bleed hook point named.** Runs at the start of LORE Phase 5 (`assemble_context_payload`, `turn_cycle.py:489`); 2s budget enforced via `asyncio.wait_for`.
5. **Pipeline stages renamed.** "Phase N" reserved for LORE turn cycle; Radiant pipeline uses "Stage N". Deferred "Phase 7" → "Radiant Stage 7".
6. **`TurnContext` extension spelled out.** Two new dataclass fields + one new `TurnPhase` enum value.
7. **`world_layer_type` precondition.** Postgres ENUM not in tracked migrations; PR 0 confirms or PR 1 declares.
8. **`entity_kind` ENUM is distinct from `EntityType`** (which includes `'item'`); spine deliberately narrower.
9. **`source_kind` enum gains `'auto_registered'`** to satisfy the Vocabulary Growth contract.
10. **Backfill pattern spelled out.** `NOT VALID → batch backfill → VALIDATE → CONCURRENTLY UNIQUE INDEX → SET NOT NULL`. Migration becomes Python, not SQL, because `scripts/migrate.py` is single-transaction-per-file.
11. **`world_events.source` and `world_event_entities.role` promoted to real enums** (`event_source_kind`, `event_role_kind`), consistent with the rest of the controlled vocabulary.
12. **`LocalLLMManager.structured_query` signature noted.** Existing API at `local_llm.py:642`; no new structured-output plumbing needed.
13. **`BackgroundTasks` pattern cross-referenced** to existing call sites (`narrative.py:281`, `storyteller.py:561, 666`).
14. **`tick_chunk_id` timing clarified.** Not known during Resolve (Stage 1); stamped during CommitRadiantTick (Stage 2) after `insert_narrative_chunk` returns the new chunk's id. The UNIQUE idempotency constraint fires at write time.
15. **MEMNON safety claim sharpened.** `get_recent_chunks` is already safe; real audit target is `query_memory` / `SearchManager`.
16. **`execute_readonly_sql` whitelist additions enumerated.**
17. **`nexus.toml` section layout** explicitly modeled on existing `[lore]` / `[memnon]` nesting.

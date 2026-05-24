# Orrery — Off-Screen Behavior Resolver

Orrery is NEXUS's deterministic off-screen behavior subsystem. While the player interacts with a focused on-screen scene, Orrery resolves what every tracked off-screen entity is doing each tick — their state, who they're in conflict with, what they might be in transit to, what they're working on. The world keeps going even where attention isn't pointed.

## Inspirations

Orrery's shape borrows openly from two reference points:

- **Bethesda's Radiant AI** (Skyrim, Fallout): NPCs have schedules, dispositions, and faction-affiliated routines that run independent of player presence. Off-screen state isn't fiction; it's the canonical answer to "what is this NPC doing right now?"
- **Dwarf Fortress**: autonomous agents with needs, relationships, and emergent off-screen events that produce historical record. The world simulates regardless of where attention is currently pointed.

What distinguishes Orrery from either of those is LLM-native integration: deterministic resolution feeds prose generation, prose feeds a *curated bleed menu*, and the storyteller (Skald) retains full authorial latitude over what makes it into the actual narrative chunk. The deterministic substrate decides what's *true*; the storyteller decides what's *said*.

## Motivating Example

An NPC the player interrogated fifty chunks ago protested that their life was over. Behind the scenes, packages on that NPC tick through fifty chunks of deterministic state resolution. Eventually a high-magnitude branch fires — say, the NPC's retaliation against the player's faction. Prose is generated, persisted into `offscreen_narrations`, never directly surfaced. Two chunks later the player is in an intimacy scene in an entirely different part of the city, and the storyteller has the option of having a character hear distant sirens. If they do, MEMNON has substrate for retrieval and the moment connects to the long-ago interrogation. If they don't, the dramatic irony lives quietly in the database, available for any future scene that wants it.

This is the shape: the world ticks for everyone, the dramatic salience filter is deterministic, the authorial choice is LLM-authored.

## What Orrery Is Not

- A replacement for the storyteller. Bleed offers a menu, never a decision.
- Real-time simulation. Orrery resolves once per accepted player turn.
- Full Bethesda parity. No game-engine pathfinding, no per-step animations, no combat resolution. (Travel has its own dedicated sub-system within Orrery — see *Routing*.)
- Procedural template authoring at runtime. Packages are authored in Python and committed via migrations.
- Inventory-game state. Items aren't first-class entities.
- Event-sourcing inversion. Canonical state lives in row-shaped tables; events annotate, they don't replace.

## Terminology

- **LORE Phase N**: a phase of `LORE.process_turn()` (`turn_context.py:12-21`). Phases: USER_INPUT, WARM_ANALYSIS, ENTITY_STATE, DEEP_QUERIES, ORRERY_RESOLVE (4.5), PAYLOAD_ASSEMBLY, APEX_GENERATION, INTEGRATION.
- **Orrery Stage N**: a stage of the off-screen pipeline (Resolve / Commit / Clear / Promote / Narrate / Bleed). "Phase" is reserved for LORE; "Stage" is Orrery, avoiding the historical Phase 7 / Stage 7 ambiguity.

---

## Pipeline

| Stage | Cost class | What runs | When |
|---|---|---|---|
| **Resolve** (Stage 1) | Free (pure Python) | Evaluate templates against per-entity bindings; produce an `OrreryTickProposal` (no writes) | In-cycle, during LORE Phase 4.5 |
| **Commit** (Stage 2) | Free (SQL) | Stamp `tick_chunk_id`, materialize the proposal into canonical tables, enqueue narration jobs | Inside the accepted-chunk commit transaction |
| **Clear** (Stage 3) | Deterministic | Event-based clearance runs in the commit transaction; semantic clearance currently no-op | Commit (event-driven) |
| **Promote** (Stage 4) | Deterministic | Decide which resolutions deserve frontier prose | Post-commit |
| **Narrate** (Stage 5) | Frontier LLM, async via durable outbox | Generate prose for promoted resolutions; persist into `offscreen_narrations` | Async after commit; durable across process restart |
| **Bleed** (Stage 6) | Deterministic, storyteller-time | Offer a bounded menu from already-filtered succeeded narrations | LORE Phase 5 (`payload_assembly`), each player turn |

**Cost shape (load-bearing):** Resolve is free and runs at full breadth. Each downstream stage is more expensive per call but operates on a smaller surface. Frontier prose only generates for resolutions that survive two earlier gates — salience-based promotion, then optional bleed selection. The only LLM call in the Orrery path is the Narration step; Promote and Bleed are both deterministic.

---

## Load-Bearing Invariant: CommitOrreryTick

> **The resolver computes; only the accepted-chunk commit path writes.**

Resolve runs in-cycle during `LORE.process_turn()` for latency reasons, but every canonical write — entity deltas, tag mutations, `world_events`, `orrery_resolutions`, narration job enqueue — flows through the same transaction that promotes the incubator chunk to canon. This collapses three concerns into one seam:

- **Rollback.** Incubator rejection means the transaction never happened. Zero cleanup logic needed.
- **Idempotency.** Commit is keyed to the accepted tick via `UNIQUE (tick_chunk_id, template_id, binding_hash)` on `orrery_resolutions`. Regeneration cannot double-write.
- **Visibility.** Nothing canonical exists until acceptance, so warm-slice retrieval cannot see provisional state.

Two phases:

1. **In-cycle (LORE Phase 4.5)**: Resolve produces an `OrreryTickProposal` carried on `TurnContext.orrery_proposal`. No writes. The proposal carries `(template_id, binding_hash, bindings, state_delta, magnitude, ...)` *without* `tick_chunk_id` — that field is unknown at this point.
2. **Commit-time**: `CommitOrreryTick` runs inside the accepted-chunk commit transaction. The new chunk's id is generated by `insert_narrative_chunk` (returned at `commit_handler.py:394` / `commit_handler_sync.py:354`); every proposal row is stamped with that id, and the `UNIQUE (tick_chunk_id, template_id, binding_hash)` idempotency guard is enforced at write time.

**Hook locations:**
- **Sync wrapper** (production path): `nexus/api/commit_handler_sync.py::commit_incubator_to_database_sync`. `CommitOrreryTick` runs as **Step 8.5**, after `apply_state_updates_sync(conn, state_updates)` returns, before the incubator-clear `DELETE`.
- **Async wrapper** (test-only): `nexus/api/commit_handler.py::commit_incubator_to_database`. Same Step 8.5 position.
- The acceptance seam that *invokes* the sync commit wrapper lives in `nexus/api/narrative.py::_approve_narrative_impl`.

---

## Authority Model: Skald-Adjudicated Commit

> **Orrery proposes; Skald has final authorial authority.**

Current-tick Orrery resolutions are surfaced to Skald as `orrery_imminent_activity` in the storyteller context payload — each proposal carries a stable `proposal_id`. Skald may optionally adjudicate any proposal via a structured `orrery_adjudications` field in the storyteller response; absence of an adjudication ratifies the proposal at commit time. This is the design call landed via PR #276 (issue #275).

**Three explicit actions:**

- **`defer`** — skip materialization this tick. The persistent substrate pressure can reappear on later ticks if the underlying state still warrants it. Useful for "this is plausible but not now — push it later."
- **`replace`** — skip the original proposal in favor of Skald's substitute. If Skald provides `replacement_state_delta`, commit materializes that limited Orrery-compatible delta instead. If `replacement_event_type` is also provided, commit emits a canonical `world_event`. If neither is provided, commit assumes Skald handled the replacement through normal structured `state_updates` or prose.
- **`void`** — skip materialization. Logs that Skald considers the proposal definitively wrong or no longer true. Strictly stronger than `defer` — the proposal does not get re-queued.

**Implicit `replace` detection:** commit also infers `replace` without prose parsing when Skald's structured character `state_updates` touch the same actor/field that an Orrery proposal would change. This prevents Orrery from overwriting ordinary authoritative state writes such as `current_activity` or movement-related `current_location`.

**Replacement scope is bounded.** `OrreryReplacementStateDelta` accepts only a constrained vocabulary (e.g., `character_current_activity`, `entity_tags_add`, `entity_tags_remove`, `entity_tags_target_add`) — Skald cannot replace with arbitrary world-state mutations. This is the safety property that keeps replacement from being arbitrary world-rewriting.

**Audit:** every adjudication writes a row to `orrery_adjudication_log` with `adjudication_source: 'explicit' | 'structured_state_update'`, `original_state_delta`, `replacement_state_delta`, and optional `skald_note`. The log enables retrospective questions: how often does Skald veto? Replace? What patterns of intervention exist?

**No `narrative_debt` flag.** Skald is fully sovereign — even player-action consequences (the 50-chunks-later NPC retaliation example) can be vetoed. The structural counterweights are (a) careful prompting that encourages allowing meaningful consequences and (b) path-of-least-resistance defaults — off-screen events happen by default if Skald takes no action.

**Schema:**

```sql
ALTER TABLE incubator
ADD COLUMN IF NOT EXISTS orrery_adjudications JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE orrery_adjudication_log (
    id                       bigserial PRIMARY KEY,
    tick_chunk_id            bigint NOT NULL REFERENCES narrative_chunks(id),
    proposal_id              text NOT NULL,
    template_id              text NOT NULL,
    binding_hash             text NOT NULL,
    action                   text NOT NULL
        CHECK (action IN ('defer', 'replace', 'void')),
    adjudication_source      text NOT NULL DEFAULT 'explicit'
        CHECK (adjudication_source IN ('explicit', 'structured_state_update')),
    skald_note               text,
    original_state_delta     jsonb NOT NULL DEFAULT '{}'::jsonb,
    replacement_state_delta  jsonb,
    replacement_event_type   text REFERENCES event_types(type),
    applied_resolution_id    bigint REFERENCES orrery_resolutions(id),
    created_at               timestamptz NOT NULL DEFAULT now()
);
```

---

## New-Story Trait Compiler

The new-story wizard's trait choices are a front door into Orrery state, but the compiler is deliberately auditable rather than magical. `nexus/api/trait_compiler.py` compiles the three selected protagonist traits into deterministic substrate writes where the current MVP has enough typed input; every selected trait produces either mechanical output or a structured prose-only remainder.

Current mechanical surface:

- `Resources` → exclusive `role.resources:<level>` single-entity tag.
- `Fame` / legacy `Reputation` → exclusive `role.fame:<level>` single-entity tag.
- `Status` → `status:<level>(character → faction)` pair-tag.
- `Allies`, `Contacts`, `Enemies` → `character_relationships` rows from structured targets, with optional pair-tags (`ally`, `contact:<kind>`, `hostile_to`) only when a package gate explicitly needs the binary edge.

Current prose-only surface: `Domain`, `Patron`, `Dependents`, and `Obligations` return `UnresolvedTrait` entries in `TraitCompileResult.prose_only_remainders` when they are selected and their typed compilers have not landed. The required wildcard is persisted separately in `characters.extra_data.wildcard` and can carry Skald-bestowed `orrery_tags`; it is not part of the selected-trait compiler loop yet.

Two execution modes exist:

- **Final bootstrap apply:** `nexus/api/new_story_db_mapper.py` applies compilation after protagonist insertion and persists the audit result to both `characters.extra_data.trait_compile_result` and `assets.new_story_creator.trait_compile_result`.
- **CLI dry-run audit:** `nexus trait-audit --slot N` runs the same compiler with `dry_run=True` against wizard cache. `--trait-inputs` can provide typed inputs for testing, and `--fail-on-remainders` gives automation loops a nonzero exit when fallback remains. This is intentionally opt-in; the default wizard and React UI do not add another confirmation screen.

This is the resolution of the "no silent prose fallback" design requirement: fallback is allowed, but it must be visible as structured audit data.

---

## Architecture

### Entity Identity Spine

A dedicated `entities` table is the identity spine for polymorphic references. Existing subtype tables (`characters`, `factions`, `places`) each have a unique `entity_id` column FK'd to the spine. All Orrery tables FK directly to `entities(id)` without a discriminator column.

```sql
CREATE TYPE entity_kind AS ENUM ('character', 'faction', 'place');

CREATE TABLE entities (
  id           bigserial PRIMARY KEY,
  kind         entity_kind NOT NULL,
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE VIEW entity_names_v AS
    SELECT e.id, e.kind, c.name FROM entities e JOIN characters c ON c.entity_id = e.id WHERE e.kind = 'character'
  UNION ALL
    SELECT e.id, e.kind, f.name FROM entities e JOIN factions f ON f.entity_id = e.id WHERE e.kind = 'faction'
  UNION ALL
    SELECT e.id, e.kind, p.name FROM entities e JOIN places p ON p.entity_id = e.id WHERE e.kind = 'place';
```

The spine carries no name column. Polymorphic name access goes through `entity_names_v`. Kind-correctness is enforced by `BEFORE INSERT OR UPDATE` triggers on each subtype table.

Cascade semantics, deliberate per table:
- `entity_tags.entity_id` → `ON DELETE CASCADE`. Tags die with the entity.
- `world_events.actor_entity_id` and `target_entity_id` → `ON DELETE RESTRICT`. Events outlive their participants; deletion requires explicit reckoning.
- `world_event_entities.entity_id` → `ON DELETE RESTRICT`. Same rationale.
- `orrery_resolutions.actor_entity_id` → `ON DELETE RESTRICT`.

The existing six triplicate relationship/reference tables (`chunk_character_references` / `chunk_faction_references` / `place_chunk_references` and their relationship counterparts) remain in place behind compatibility views `chunk_entity_references_v` and `entity_relationships_v`. Collapse is deferred until one of these holds: a fourth real entity kind appears, the views become frequent write targets, or kind-branching logic spreads into many modules.

### Tag System

```sql
CREATE TYPE entity_tag_source_kind AS ENUM (
  'authored', 'llm_generated', 'system', 'template', 'auto_registered', 'skald_inline'
);

CREATE TABLE tags (
  id                       bigserial PRIMARY KEY,
  tag                      text UNIQUE NOT NULL,
  category                 text NOT NULL,
  is_ephemeral             boolean NOT NULL DEFAULT false,
  clearance_kind           entity_tag_clearance_kind,   -- NULL when not ephemeral
  reapplication_policy     entity_tag_reapplication_policy,
  clear_on                 jsonb,
  synonym_for              bigint REFERENCES tags(id),
  deprecated               boolean NOT NULL DEFAULT false,
  description              text,
  created_at               timestamp DEFAULT now(),
  CHECK (is_ephemeral = (clearance_kind IS NOT NULL))
);

CREATE TABLE entity_tags (
  id                     bigserial PRIMARY KEY,
  entity_id              bigint NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  tag_id                 bigint NOT NULL REFERENCES tags(id),
  applied_at             timestamp NOT NULL DEFAULT now(),
  applied_at_world_time  timestamptz,
  clear_on_override      jsonb,
  cleared_at             timestamp,                   -- NULL means current
  template_id            text,                        -- if applied by a template
  source_kind            entity_tag_source_kind NOT NULL,
  UNIQUE (entity_id, tag_id, applied_at)
);

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

CREATE TABLE tag_clearance_log (
  id                      bigserial PRIMARY KEY,
  entity_tag_id           bigint NOT NULL REFERENCES entity_tags(id),
  cleared_at              timestamp NOT NULL DEFAULT now(),
  cleared_at_world_time   timestamptz,
  mechanism               entity_tag_clearance_kind NOT NULL,
  triggering_event_id     bigint REFERENCES world_events(id),
  justification           jsonb,
  source_chunk_id         bigint REFERENCES narrative_chunks(id)
);
```

Design constraints:
- 3NF registry + join + view (not a single denormalized table).
- Single `tags` registry with `is_ephemeral` boolean (no separate ephemeral table).
- Surrogate `entity_tags.id` (not composite key); allows multiple historical applications.
- Single FK to `entities(id)`, no discriminator column.
- `cleared_at` column for cheap current-view reads.
- Three clearance kinds: `event` / `semantic` / `authored`. No clock-based expiry.
- `source_kind` as a real PG enum. `'auto_registered'` satisfies the Vocabulary Growth contract; `'skald_inline'` is the runtime path from Skald tagging during structured-output entity registration.

### Event Stream

```sql
CREATE TYPE event_source_kind AS ENUM ('apex', 'resolver', 'narrator', 'bleed', 'authored');
CREATE TYPE event_role_kind AS ENUM ('actor', 'target', 'observer', 'beneficiary', 'witness');

CREATE TABLE event_types (
  type           text PRIMARY KEY,
  category       text NOT NULL,
  severity       event_severity_kind,
  description    text,
  deprecated     boolean NOT NULL DEFAULT false,
  synonym_for    text REFERENCES event_types(type)
);

CREATE TABLE world_events (
  id                     bigserial PRIMARY KEY,
  event_type             text NOT NULL REFERENCES event_types(type),
  tick_chunk_id          bigint NOT NULL REFERENCES narrative_chunks(id),
  narration_chunk_id     bigint REFERENCES offscreen_narrations(id),
  actor_entity_id        bigint REFERENCES entities(id) ON DELETE RESTRICT,
  target_entity_id       bigint REFERENCES entities(id) ON DELETE RESTRICT,
  location_id            bigint REFERENCES places(id) ON DELETE RESTRICT,
  world_layer            world_layer_type,
  source                 event_source_kind NOT NULL,
  changed_fields         text[] NOT NULL DEFAULT '{}',
  magnitude              numeric(4,3),
  resolution_id          bigint REFERENCES orrery_resolutions(id),
  payload                jsonb NOT NULL DEFAULT '{}',
  superseded_by_event_id bigint REFERENCES world_events(id),
  created_at             timestamptz DEFAULT now()
);

CREATE TABLE world_event_entities (
  event_id      bigint NOT NULL REFERENCES world_events(id) ON DELETE CASCADE,
  role          event_role_kind NOT NULL,
  entity_id     bigint NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
  PRIMARY KEY (event_id, role, entity_id)
);
```

Design constraints:
- Append-only; supersession only for in-world retcons (the `superseded_by_event_id` chain).
- Separate `tick_chunk_id` and `narration_chunk_id` columns; no overloaded `chunk_id`.
- Single-FK polymorphism for actor/target. `location_id` keeps the `places(id)` FK because places have spatial semantics distinct from entity-ness; a place participating as actor/target uses `actor_entity_id`/`target_entity_id`.
- `world_event_entities` join table for multi-participant events; `role` is an enum.
- `source` is an enum (`event_source_kind`), not free text.
- `changed_fields text[]` with controlled vocab derived from `StateUpdate` Pydantic models (`apex_schema.py:631`).
- `magnitude` enables Promote scoring without unpacking payload.
- `world_layer` filtering keeps dream/flashback events out of the resolver's recent-event window.

### Orrery Resolutions

```sql
CREATE TABLE orrery_resolutions (
  id                  bigserial PRIMARY KEY,
  tick_chunk_id       bigint NOT NULL REFERENCES narrative_chunks(id),
  template_id         text NOT NULL,
  binding_hash        text NOT NULL,
  actor_entity_id     bigint REFERENCES entities(id) ON DELETE RESTRICT,
  priority            integer NOT NULL,
  magnitude           numeric(4,3),
  state_delta         jsonb NOT NULL,
  brief               text,
  event_ids           bigint[],
  promotion_status    orrery_promotion_status NOT NULL DEFAULT 'pending',
  promotion_verdict   jsonb,
  narration_status    orrery_narration_status NOT NULL DEFAULT 'none',
  narration_chunk_id  bigint REFERENCES offscreen_narrations(id),

  last_offered_chunk_id   bigint REFERENCES narrative_chunks(id),
  offer_count             integer NOT NULL DEFAULT 0,
  first_surfaced_chunk_id bigint REFERENCES narrative_chunks(id),

  created_at          timestamptz DEFAULT now(),
  UNIQUE (tick_chunk_id, template_id, binding_hash)
);
```

`tick_chunk_id` is `NOT NULL`, but the in-cycle `OrreryTickProposal` carries no `tick_chunk_id` — it's stamped during `CommitOrreryTick` after `insert_narrative_chunk` returns the new chunk's id. The `UNIQUE` constraint fires at write time, not at proposal time.

### Narration Outbox

```sql
CREATE TABLE orrery_narration_jobs (
  id              bigserial PRIMARY KEY,
  resolution_id   bigint NOT NULL REFERENCES orrery_resolutions(id),
  slot            text NOT NULL,
  state           orrery_job_state NOT NULL DEFAULT 'queued',
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

Durable outbox surviving process restart. Dispatched via FastAPI `BackgroundTasks` from `_approve_narrative_impl` after commit returns. Standalone CLI worker for catch-up: `python -m nexus.agents.orrery.worker --slot N`; status-only inspection: `--status`.

### Off-Screen Narration Storage

```sql
CREATE TABLE offscreen_narrations (
  id              bigserial PRIMARY KEY,
  resolution_id   bigint NOT NULL REFERENCES orrery_resolutions(id),
  tick_chunk_id   bigint NOT NULL REFERENCES narrative_chunks(id),
  world_layer     world_layer_type,
  text            text NOT NULL,
  perceptual_descriptor jsonb,
  embedding_status offscreen_embedding_status DEFAULT 'pending',
  created_at      timestamptz DEFAULT now()
);
```

`narrative_chunks` is always player-visible; `offscreen_narrations` never is. MEMNON's retrieval logic queries both tables with explicit semantic intent: warm-slice → `narrative_chunks` only; off-screen retrieval → both, with `offscreen_narrations` clearly labeled. `narrative_view.world_time` does NOT count off-screen narrations toward chronological advancement.

### Bleed Selector — Cross-Turn Ambient Surfacing

**Bleed handles cross-turn grace, not current-tick proposals.** Current-tick proposals flow through the authority model above — Skald sees them directly in `orrery_imminent_activity` and adjudicates. Bleed's role is narrower: surfacing *prior-turn* narrated events that weren't included in any chunk yet but remain eligible to bleed through within a temporal grace window.

Storyteller-time Bleed chooses deterministically from these eligible narrated events. Output is a bounded list (typically N ≤ 3), each annotated with a sensory channel (auditory, news fragment, secondhand mention, faction graffiti) and a thin perceptual descriptor — not the narrator's full prose.

**Hook point**: runs at the start of LORE Phase 5 (`assemble_context_payload`, `turn_cycle.py:489`). Its output populates `turn_context.bleed_menu`, which `assemble_context_payload` then reads when building the payload.

**No inference budget.** Bleed makes no storyteller-time model call; empty bleed remains a valid outcome.

**Candidate query**: reads from `orrery_resolutions` JOIN `world_events` JOIN `offscreen_narrations` with filters on age, location proximity, sensory plausibility, and surfacing history. Selection is deterministic from the SQL ordering, capped by `[orrery.bleed] max_candidates`.

**Surfacing bookkeeping** prevents nag: `last_offered_chunk_id`, `offer_count` (≤ 3 by current policy), `first_surfaced_chunk_id`. Distinguishes "offered to storyteller" from "actually surfaced" — only the latter creates a visible-world surfacing record.

**Payload framing**: "ambient peripherals available — ignore any or all, render at any density from overt to invisible." Zero is a valid inclusion count.

### Tick, Resolver Firing, World Time

- **Tick = the accepted player-visible chunk's id**, not the latest `narrative_chunks` row. The id is generated at `commit_handler_sync.py:354` and stamped onto every Orrery write in the same transaction.
- **Resolve runs in-cycle** during LORE Phase 4.5 (`TurnPhase.ORRERY_RESOLVE`), between `DEEP_QUERIES` and `PAYLOAD_ASSEMBLY`. Pure Python; no writes.
- **CommitOrreryTick** runs as Step 8.5 inside `commit_incubator_to_database{,_sync}`. All canonical writes happen here.
- **Clear (event)** runs in the same commit transaction as the triggering event.
- **Clear (semantic)** is currently a conservative no-op until a non-local clearance signal exists.
- **Promote** runs post-commit, deterministically, batched per tick.
- **Narrate** is async via durable outbox. Bleed reads only `state='succeeded'` narrations + deterministic briefs.
- **Bleed** runs synchronously at storyteller-time without inference.

### World Time Denormalization

`world_time` denormalized onto `chunk_metadata`, not `world_events`. The cumulative-SUM of `narrative_view.world_time` means a `time_delta` edit on chunk K invalidates every later event row — fan-out unbounded. Per-chunk denormalization keeps fan-out bounded to "every chunk from K to current."

```sql
ALTER TABLE chunk_metadata ADD COLUMN world_time timestamptz;

CREATE FUNCTION refresh_world_time_from_chunk(changed_chunk_id bigint)
RETURNS void AS $$
  -- recompute world_time for changed_chunk_id and every chunk_id > changed_chunk_id
$$ LANGUAGE sql;
```

`world_events.world_time` becomes a JOIN: `SELECT we.*, cm.world_time FROM world_events we JOIN chunk_metadata cm ON we.tick_chunk_id = cm.chunk_id`. Stamped only at accepted commit. Off-screen narrations never advance chronology.

### Routing

For travel-related packages, NEXUS uses an Earth/Earth-mirror geography constraint: every place anchors to real-world coordinates in `places.coordinates`, even when the fiction is non-Earth. This keeps GIS tooling, OSM-derived graph imports, and travel-time estimates available without inventing alternate map projections per world.

Travel-state lifecycle is additive to existing location tracking. `characters.current_location` remains the canonical `places(id)` anchor used by LORE / LOGON / MEMNON / Orrery; `character_travel_states` records whether a character is at a place, planning travel, or in transit. While in transit, location predicates treat the anchor as non-physical so the resolver does not pretend the character is still co-located there.

Travel route selection cascades: local OSM-derived `osm_graph` routing first, then authored `orrery_travel_edges`, then a coordinate-distance estimate. The graph path is intentionally offline — normal Orrery ticks read only local tables and never call map APIs or inference. Authored edges (`mixed` generic, plus authored overrides) are an exception surface. See `docs/orrery_route_graph.md` for the graph importer contract.

### EntityRef Helper

```python
class EntityRef(BaseModel):
    id: int                                     # FK to entities.id
    kind: Optional[EntityKind] = None           # populated on read from entities.kind
    name: Optional[str] = None                  # populated on read via entity_names_v

    def canonical_key(self) -> str:
        return f"entity:{self.id}"
```

Postgres FKs enforce existence; `EntityRef` is a typed read-side convenience that binding composers, condition primitives, and bleed candidates carry. The `name` field is populated at read time from `entity_names_v`; the spine itself carries no name column.

---

## Invariants and Contracts

### Vocabulary Growth Contract

When a tag or `event_type` is referenced that the registry hasn't seen:
- **Resolver-sourced**: fail loudly. Templates must register their vocabulary before use.
- **Apex/Skald-sourced**: auto-register with `source_kind='auto_registered'` or `'skald_inline'` and `description='AUTO: pending review'`. Surfaces in periodic curation.

### ALWAYS-Fallback Invariant

Every template MUST end with an `ALWAYS`-conditioned branch. Validated at template-load time via pytest fixture.

### Gate-Cooldown Coverage

If a template package gate includes `since_last_event_at_least(...)` cooldowns, every `event_type` emitted by any branch MUST appear in that gate's cooldown chain. Otherwise one branch can bypass the template's pacing intent by emitting an event the outer gate never checks. Validated by `tests/test_orrery/test_substrate.py::test_gate_cooldown_chain_covers_branch_events`.

### Sliding-Window Binding Scope

The binding composer filters to recently-relevant entities: `(referenced in chunk_character_references in last N chunks) ∪ (has an active ephemeral tag) ∪ (has un-superseded world_events in last N chunks)`. N is config-tunable via `[orrery.binding] window_chunks`; default is 30.

---

## Configuration

```toml
[orrery]
enabled = true

[orrery.binding]
window_chunks = 30

[orrery.narration]
mode = "async"                                  # "async" | "sync"
provider = "anthropic"
model_ref = "@anthropic.default"                # resolved via [global.model.api_models]

[orrery.bleed]
max_candidates = 3

[orrery.promote]
priority_threshold = 50.0
magnitude_threshold = 0.5
perceptual_summary_max_chars = 240
```

Every model reference uses the `@provider.role` syntax that the config loader resolves against `[global.model.api_models]` — never a hardcoded model ID in runtime code (per `CLAUDE.md` "Testing Defaults").

---

## Critical Files / Integration Points

**LORE turn cycle**
- `nexus/agents/lore/lore.py:289` — `process_turn`; LORE Phase 4.5 hook
- `nexus/agents/lore/utils/turn_context.py:12-41` — `TurnPhase` enum + `TurnContext` dataclass (`orrery_proposal`, `bleed_menu`)
- `nexus/agents/lore/utils/turn_cycle.py:489` — `assemble_context_payload` (LORE Phase 5); Bleed selector hooks at the start
- `nexus/agents/orrery/worker.py` — deterministic Promote policy, durable narration outbox drain, conservative semantic-clearance no-op

**Commit path (production = sync)**
- `nexus/api/narrative.py:387` — `_approve_narrative_impl`; acceptance seam
- `nexus/api/narrative.py:407` — calls `commit_incubator_to_database_sync`
- `nexus/api/commit_handler_sync.py:233` — `commit_incubator_to_database_sync`; `CommitOrreryTick` at Step 8.5
- `nexus/api/commit_handler_sync.py:354` — where the new chunk id is created
- `nexus/api/commit_handler.py:320` — async parity (test-only)

**Not on the commit path**
- `nexus/api/chunk_workflow.py` — narrative-chunk state machine (DRAFT / PENDING_REVIEW / FINALIZED / EMBEDDED); downstream embedding only. Do not hook Orrery here.

**MEMNON**
- `nexus/agents/memnon/memnon.py:1486` — `get_recent_chunks` (warm slice; `narrative_chunks`-only)
- `nexus/agents/memnon/memnon.py::query_memory` and `SearchManager` — warm-slice retrieval must remain disjoint from `offscreen_narrations`
- `nexus/agents/memnon/memnon.py::execute_readonly_sql` — whitelist exposes public Orrery tables; internal queue/raw tables excluded

**Schema sources**
- `nexus/agents/logon/apex_schema.py:631` — `StateUpdates` Pydantic models (source for `changed_fields` vocab)
- `nexus/agents/logon/apex_enums.py:41` — existing `EntityType` enum (includes `'item'`); spine declares its own narrower `entity_kind`
- `nexus/api/trait_compiler_schemas.py` — trait compiler audit/result schemas (`TraitCompileResult`, `UnresolvedTrait`, applied tag/relationship rows)

**Orrery module**
- `nexus/agents/orrery/substrate.py` — package primitive (`Template`, `Branch`, predicates, `evaluate`, `evaluate_stack`)
- `nexus/agents/orrery/templates.py` — package catalog
- `nexus/agents/orrery/resolver.py` — `resolve_dry_run` + binding composers
- `nexus/agents/orrery/events.py` — canonical event writer (`emit_state_updates_events`, `emit_event`)
- `nexus/agents/orrery/bleed.py` — bleed candidate query + offer bookkeeping
- `nexus/agents/orrery/worker.py` — Promote / narration outbox drain
- `nexus/api/trait_compiler.py` — new-story trait → Orrery compiler, final apply, dry-run compile, and pair-tag/relationship drift reconciliation

**Catalogs**
- `docs/orrery_packages.md` — generated human-readable package reference (kept in lockstep with `templates.py` via the `regenerate-orrery-catalog` pre-commit hook)
- `docs/orrery_route_graph.md` — route graph importer contract

**Specialized Subsystem Docs**
- `docs/orrery_needs.md` — design rationale for the physiological and interpersonal need packages (SLEEP, EAT, DRINK, SOCIALIZE, INTIMACY): the substrate-vs-storyteller principle, the graduated severity pattern, the stimulant gate-suppression pattern, modulator tags, intimacy suppressors, the Pete worked example, and open questions. Companion to the mechanical catalog at `docs/orrery_packages.md`.
- `docs/orrery_retrograde_spec.md` — design spec for deep-history generation (Orrery run backward at wizard-time and per-entity stub maturation at runtime). Phase 3+ work.
- `docs/orrery_tag_vocabulary.md` — registry-level closed-vocabulary specification for tag categories (single-entity tags, multi-entity pair tags, place / faction categories, trait_menu alignment).

---

## Verification Approach

Verification uses live NEXUS flows where the feature touches LORE, LOGON, MEMNON, or database state. Pure substrate/package tests remain deterministic unit tests because their purpose is to validate package logic without paying model or API costs.

- **Substrate tests** (`tests/test_orrery/`): template loading, gate predicates, branch evaluation, ALWAYS-fallback invariant, gate-cooldown coverage.
- **Resolver tests**: hydration shape, binding composition (actor-only and actor-target), `evaluate_stack` semantics, dry-run against fixture `WorldState`.
- **Integration tests**: idempotency (UNIQUE key fires on regeneration), incubator-rejection rollback (Step 8.5 writes get reverted), warm-slice contamination (none), deterministic promotion behavior, async-worker state transitions (`queued → leased → succeeded|failed`).
- **Bleed tests**: apt-bleed (ambient peripheral surfaces in payload), null-bleed (no candidates produces empty menu and no inference call), chronology/surfacing boundary (only accepted prior narrated resolutions are eligible).
- **Live dry-runs** against mature-state slots (typically slot 2) to validate package behavior against canonical narrative content; see `scripts/orrery_sample.py` for the harness.
- **Trait compiler audits**: `poetry run nexus trait-audit --slot N` for opt-in wizard-cache inspection, plus `--fail-on-remainders` when a test loop should fail on any prose-only fallback.

---

## Package Author Notes

The cleanest contribution format for a new package is a small template sketch in `nexus/agents/orrery/templates.py` plus a markdown catalog note that names: package goal, slots, gate, branches, event types, state deltas, required tags, and any pressure-only behavior. The current source of truth for implemented packages is `templates.py`; the human-readable generated reference is `docs/orrery_packages.md` (regenerated automatically on commit when `templates.py` / `substrate.py` / `catalog.py` change).

New durable vocabulary belongs in explicit migrations. Backfill and application of tags is data work, not package-author side effects — keep schema and content changes separate.

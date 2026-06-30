# Orrery: Auditability and Resolution-Quality Brainstorm

Working notes from a fresh read of `nexus/agents/orrery/` (resolver, substrate, templates,
worker, retrograde cluster, tag_writer, migrations 023/024). Goal: move Orrery from "works"
toward "reliably generates appropriate and dynamic resolutions," and design a dashboard that
makes its reasoning visible and auditable.

## Current Checkout Delta

These notes originally framed an explain-evaluator as the first backend gap. In the current
checkout, that primitive already exists:

- `nexus/agents/orrery/explain.py` provides `trace_condition()`, `explain_template()`, and
  `explain_stack()`.
- The trace model already returns condition-tree pass/fail results, branch traces, whole-stack
  winner/shadowed metadata, drive band, present-target policy, event type, magnitude, narrative
  stub, and state delta.
- `nexus/agents/orrery/demo.py --explain` emits the shape the dashboard should consume.
- `tests/test_orrery/test_explain.py` guards the important invariant: explain output must match
  production `evaluate_stack()` selection while retaining the shadowed packages.

So the next step is not "invent explainability"; it is **connect the existing explain stack to
real slot hydration, entity name/context hydration, overrides, and a localhost UI**.

---

## Two Findings That Reframe the Work

### The Clock Is Mostly an Illusion Today

`hydrate_world_state(anchor_chunk_id=N)` only rewinds two things: **recent events**
(`_load_recent_events` filters by the chunk window) and **world-time / time-of-day**
(`_load_world_time`). Everything else is read from *current* projections with no as-of filter:

- tags from `entity_tags_current` (a `VIEW` of `entity_tags WHERE cleared_at IS NULL`)
- locations/activities from `characters.current_location` / `current_activity` (scalar columns)
- relationships/trust from `entity_relationships_v`
- pair tags from `entity_pair_tags WHERE cleared_at IS NULL`
- needs, travel, routine anchors — all current

So "load slot 1, set clock to chunk 1400" would show **1400-era events and time of day, but
today's tags, positions, and relationships.** For an audit tool that is a correctness trap —
you would be auditing a chimera and drawing wrong conclusions about why a package fired.

How expensive is honest reconstruction? Mixed, and worth knowing precisely:

- **Cheap-ish:** tags, pair-tags, relationships are append-only with `cleared_at`. As-of state
  is `bestowed <= T AND (cleared_at IS NULL OR cleared_at > T)`. The work is writing as-of
  variants of ~6 hydration queries. Bounded and mechanical. (Caveat: confirm rows carry a
  chunk-id bestowal key, not just wall-clock `now()`.)
- **Expensive:** `characters.current_location` / `current_activity` are scalar "current"
  columns with **no history**. Reconstructing position as-of-tick needs movement/activity
  **event replay** from `world_events`. This is the real cost.
- **Contaminated:** need debt is derived from `world_time`, so it partly rewinds — but a need
  fulfilled *after* T pollutes the "time since last fulfillment" math.

**Implication for the dashboard:** offer three honest modes rather than one dishonest clock.
1. *Current-state* (default): real now. "What fires this tick."
2. *What-if / sandbox*: current state + dev overrides (toggle a tag, move an actor, set a
   need, inject a recent event), then re-resolve live. `WorldState` is a frozen dataclass, so
   "copy with overrides" is trivial. **This is the highest-value mode and the cheapest to
   build.**
3. *True as-of* (fast-follow): real reconstruction for tags/pairs/relationships, with an
   explicit "position approximate" flag until event-replay lands.

Label every mode in the UI so we never silently audit a chimera.

### "Why Did This Fire?" Now Has a Core Primitive

Conditions are opaque `bool`-returning callables (`Condition`), composed via
`CompoundCondition(op, children)`. `evaluate()` returns only the winning branch — no record of
which gate clauses passed, which branches lost, or why. The hover-audit UX ("what tags and
conditions triggered the package") used to have no backend to read from.

Good news: the condition tree is already introspectable. `_condition_tree_leaves()` walks it;
`CompoundCondition` exposes `.op` and `.children`; leaf predicates carry human names via
`__name__` (e.g. `has_any_intimacy_suppressor(@actor)`). `nexus/agents/orrery/explain.py`
now uses those surfaces to produce a whole-stack trace without touching the production resolver
hot path.

What it does today:

- walks compound gates exhaustively and records pass/fail at each node
- renders predicate prose through the same catalog machinery as `docs/orrery_packages.md`
- cross-checks each explanation against production `evaluate()` and fails loudly on divergence
- returns every priority-ordered template, with the actual winner and shadowed packages flagged

What it does **not** do yet:

- expose the underlying values that made a leaf predicate true/false (`sleep debt = 18.4`,
  `actor tags include off_grid`, etc.)
- explain real slot actors in an API response; the existing demo harness is preset-based
- combine traces with rich entity hover data, adjudication history, or sandbox overrides

---

## How Resolution Actually Works (Ground Truth)

Per off-screen actor, every tick:

1. **Package selection is winner-take-all by static priority.** `evaluate_stack()` sorts
   templates by `priority` descending and returns the **first** whose gate passes *and* has a
   firing branch. Exactly one package fires per actor. Every other package that *would* have
   fired is silently discarded.
2. **Branch selection is first-passing in authored order.** `evaluate()` iterates
   `template.branches` and returns the **first** branch whose conditions pass. Branches are
   authored in descending `magnitude` with a terminal `ALWAYS` fallback (enforced by
   `validate_always_fallbacks`). So first-passing ≈ highest-magnitude-that-passes — *by
   authoring convention, not by the engine.*
3. **It is fully deterministic.** Same state ⇒ same package ⇒ same branch, every time.
4. **`magnitude` is salience, not a selector.** It orders branches by convention and rides
   along as an output, but never actually drives a choice.

`priority` is a fixed global int. The `drive_band_priority_warnings()` lint exists precisely
because a static ladder across 25 packages is brittle to author — that lint is a smell pointing
at finding #3 below.

---

## The Categories You Asked About

Yes — real categories exist in the backend, beyond the SunHelm trio.

### Drive Bands (the backend taxonomy)

`DriveBand` is a 5-value enum on every `Template`, with a canonical urgency order
(`DRIVE_BAND_ORDER`). This is the natural top-level grouping for the dashboard — it matches
both the engine and the way you already think:

| Band | Packages |
|---|---|
| `CRISIS_CONSTRAINT` | EVADE_PURSUERS, PROTECT_KIN, TEND_WOUNDED, HIDE, WARN_ALLY, MAINTAIN_COVER |
| `EMBODIED_MAINTENANCE` | **SLEEP, DRINK, EAT** (the SunHelm trio) |
| `ANCHORED_ROUTINE` | ROUTINE_COMMUTE, TRAVEL, WORK |
| `AFFILIATION` | CHECK_ON_DEPENDENT, KEEP_VIGIL, REACH_OUT_TO_KIN, MOURN_LOSS, SOCIALIZE, INTIMACY |
| `PROJECT_IDENTITY` | EXTRACT_VENGEANCE, HONOR_DEBT, PURSUE_GHOST_LEAD, CULTIVATE_INFORMANT, SURVEIL, CONSULT_RIVAL, TEND_CRAFT |

### Cross-Cutting Axes (filter/highlight, not primary grouping)

- **Slot arity — the multi-entity axis you most want visible.** Single-actor (`ACTOR`) vs
  two-party (`ACTOR, TARGET`). The two-party set is exactly the "entities interact" cluster:
  PROTECT_KIN, EXTRACT_VENGEANCE, TEND_WOUNDED, WARN_ALLY, CHECK_ON_DEPENDENT,
  CULTIVATE_INFORMANT, KEEP_VIGIL, SURVEIL, REACH_OUT_TO_KIN, CONSULT_RIVAL. Make this a
  first-class flag/lane.
- **Present-target policy.** The two-party packages also carry
  `present_target_policy = STORYTELLER_PRESSURE` — they can exert scene pressure on on-screen
  entities (prompt-only, routed through Skald, no state mutation). A distinct behavioral class
  worth flagging.
- **Event families (the causal web).** Packages emit `event_type`s, and *other* packages' gates
  trigger on those events. `threat_issued` → WARN_ALLY + CONSULT_RIVAL; `compliance_alert` →
  EVADE_PURSUERS + HIDE + SURVEIL; `faction_realignment` → CONSULT_RIVAL. This is genuine
  emergent chaining and it is currently invisible. Strong candidate to visualize and to tune
  (decay windows, propagation).
- **Tag families (suppressor/enabler linkages).** Curated frozensets in `substrate.py` couple
  behavior across many packages: `INTIMACY_SUPPRESSOR_TAGS`, `HIDDEN_TAGS` (composed into
  `DRAMATIC_CONTACT_TAGS`), `CONSTRAINED_TAGS`, `PUBLIC_MOBILITY_TAGS`, `PUBLIC_PLACE_CLASSES`,
  `ESTABLISHED_PARTNER_RELATIONSHIP_TYPES`. A single ephemeral like `grudge_active` silently
  suppresses several other packages. When a resolution feels "wrong," an invisible family tag is
  often the cause — so the hover-audit must name the family responsible.

### The SunHelm Trio in Context

SLEEP/DRINK/EAT *are* the `EMBODIED_MAINTENANCE` band — your intuition maps onto a real backend
category. Their shared unique mechanic is `need.fulfill` (quality + discharge) over need-debt
scoring. EAT and DRINK are further coupled: DRINK's gate defers when hunger is high and a meal
is imminent. So "the trio" is really "a band with an extra intra-band coupling."

---

## Ideas to Move From "Works" to "Reliably Appropriate and Dynamic"

### Dynamism (the "same state ⇒ same beat" problem)

1. **Seeded stochastic branch selection.** Today `evaluate()` returns the first passing branch.
   Instead, collect *all* passing branches and sample weighted by `magnitude` (softmax with a
   temperature from `nexus.toml`). Key the PRNG on `(entity_id, tick, template_id)` so it stays
   **reproducible** (tests still assert exact outcomes) while a character no longer "drinks
   routinely" identically every eligible tick. Smallest change, biggest dynamism payoff.
2. **Intensity-modulated temperature.** Let how *hard* the gate matched lower the temperature:
   desperate states (sleep debt 48) resolve sharply; mild states wander. This needs a scalar
   "match intensity" alongside today's boolean traces; the explain layer is the natural place
   to expose it once predicates can report structured evidence.

### Appropriateness (winner-take-all flattens off-screen life)

3. **Soft dynamic scoring instead of a static ladder.** Replace (or wrap) fixed `priority` with
   `effective_score = base + situational modifiers` (need-debt intensity, event recency decay,
   trust extremity). Turns the brittle global ladder into a scoreboard, raises appropriateness,
   and dissolves the very inversions `drive_band_priority_warnings()` is forced to police.
   More invasive; highest ceiling.
4. **Primary + ambient layering.** Surface one primary resolution *plus* optionally one ambient
   embodied-maintenance beat, so a hunted-and-hungry character isn't monomaniacally "just
   evading." Makes off-screen life feel layered. (Also a dashboard requirement: always show the
   shadowed stack, not only the winner.)
5. **Light hysteresis for project-identity arcs.** A small bias to continue an in-progress arc
   (PURSUE_GHOST_LEAD, CULTIVATE_INFORMANT) rather than scatter, so multi-tick projects read as
   intentional. Event cooldowns already prevent thrash; this adds positive momentum.

### Multi-Entity Interaction (the richest untapped vein)

6. **Reciprocal/conflict pass.** Two-party packages resolve independently from the actor's
   side. Add a second pass that detects reciprocal (A→B *and* B→A) and conflicting pairs and
   composes them into a single joint beat — a handshake, a missed connection, an ambush. This
   is where genuine off-screen drama between characters emerges, and exactly the interaction
   you want to inspect.

### Authoring and Coverage

7. **Tag-family transparency + lint.** Make the suppressor/enabler families first-class and
   documented; lint for over-broad suppression (a tag silently killing too many bands).
8. **Coverage analyzer over real history.** Run the resolver across a window of historical
   chunks and report: actors with *no* firing package (coverage gaps), packages that *never*
   win or *always* win, dead branches (conditions unreachable given the gate). The dashboard's
   batch-over-chunks mode *is* this analyzer — auditing and coverage testing are the same tool.

---

## The Audit Dashboard

### Form Factor — Recommendation: Localhost Dev Surface First

Build a localhost dev surface now; fold it into the desktop app as a hidden developer pane only
once the information architecture has stabilized. "Standalone" should mean "isolated from the
player UI and safe to iterate," not necessarily "a totally separate tech stack." In the current
repo, two shapes both fit:

- a small FastAPI app plus single-page frontend dedicated to Orrery auditing
- a dev-only `/dev/orrery` route in the existing React/Vite app, backed by `/api/dev/orrery/*`
  endpoints and excluded from production/player affordances

Reasons:

- The resolver is already pure-Python and side-effect-free (`resolve_dry_run` writes nothing),
  so a thin FastAPI + single-page frontend is a short path. `demo.py --explain` is already a
  standalone JSON harness to crib from.
- Dev affordances (raw JSON, override forms, batch-over-chunks, coverage reports) should never
  ship in the player UI.
- It iterates independently of the desktop release cycle.
- It doubles as the anti-mock test/CI surface you like: real DB, real resolver, real API-free
  determinism — assert resolver behavior over real historical slots.

This fits NEXUS conventions cleanly: configurable via `nexus.toml`, surfaces errors loudly,
keeps writes out of the audit path, and avoids mocks.

### Backend — What Exists vs. What to Add

Already there: `hydrate_world_state()`, `compose_actor_bindings()` /
`compose_actor_target_bindings()`, `resolve_dry_run()` → `OrreryTickProposal`,
`_load_entity_names()`, `OrreryResolutionDraft.to_dict()`, `explain_stack()`,
`StackExplanation.to_dict()`, and the `demo.py --explain` JSON payload.

To add:
- A slot-backed explained resolver: hydrate real slot `WorldState`, compose actor/target
  bindings, run `explain_stack()` for each binding set, and attach entity names.
- An entity hover/context hydrator: tags grouped durable/ephemeral/family, pair tags,
  relationships/trust, needs, travel state, routine anchors, current place/classes, recent
  events.
- An overrides layer on `WorldState` for what-if mode (toggle tag, move actor, set need, inject
  event) without touching canonical tables.
- As-of hydration variants for tags/pairs/relationships.
- Three minimal endpoints: `GET /catalog` → templates grouped by drive band with cross-cutting
  metadata; `POST /resolve` → full per-actor stack **with traces and the shadowed stack**;
  `POST /context/entities` → hover/context payload for the entity ids visible in a result.
- Optional later endpoint: `GET /history/adjudications` to compare proposal → Skald
  adjudication → committed resolution patterns.

One caveat for the current `explain_stack()`: it records pass/fail, not the raw values read by
leaf predicates. That is enough for the first dashboard. A richer "why this leaf was true"
layer probably requires predicate helpers to return structured evidence, not just booleans.

### Organization

Primary grouping by **drive band** (matches backend + your "categories make my brain happy").
A prominent **multi-entity lane/flag** cuts across all bands. Filters for the other axes
(present-target, event family, tag family). Within a group, order by the actual resolver
decision (priority/score) and clearly mark **winner vs. shadowed**.

### UX

- **Clock + override panel**, with the honest-mode label from finding #1. Overrides (toggle
  tag, move actor, set need, inject event) make it a true sandbox.
- **Per-actor resolution card:** winner package + branch + narrative + magnitude + event;
  expandable to the **shadowed stack** (every other package that would have fired, in order).
- **Hover-audit on any entity:** tags grouped permanent/ephemeral *and by family*,
  relationships, needs, location/place-class; the specific tags/conditions that
  triggered/suppressed the hovered package highlighted.
- **"Why" popover on a resolution:** the explain-tree — gate clauses with per-node pass/fail,
  and for the chosen branch, why higher-magnitude branches were skipped. The killer feature.
- **Multi-entity interaction graph** for the tick: edges where a package targets another
  entity; reciprocal and conflicting pairs highlighted.
- **Health strip:** counts per band, coverage gaps, priority-inversion warnings (existing
  lint), never/always-win packages across the loaded window.

### Questions the Dashboard Should Answer Fast

- Why did this actor get this package instead of another plausible package?
- Which package would have fired if the winner were disabled or deprioritized?
- Which specific tag, pair tag, need, location class, recent event, or cooldown suppressed the
  package I expected?
- Which actors have no plausible package at all?
- Which packages never win in this slot, and which branches are dead behind their gates?
- Which two-party packages are targeting on-screen entities as scene pressure rather than
  committing off-screen state?
- How often does Skald defer, replace, or void each package after seeing the proposal?
- Is the current "clock" mode an honest replay, or a current-state what-if with older event
  windows?

---

## Suggested Sequence

1. Slot-backed `POST /resolve` that wraps the existing `explain_stack()` and returns per-actor
   stacks with traces, winners, and shadowed packages. (Unlocks the whole audit experience on
   current-state.)
2. Localhost SPA or dev-only `/dev/orrery` route: drive-band grouping, resolution cards,
   hover-audit, why-popover.
3. Override/sandbox layer on `WorldState` (the high-value what-if mode).
4. Coverage analyzer (batch over historical chunks) — auditing doubles as CI.
5. True as-of reconstruction for tags/pairs/relationships; flag position as approximate until
   event-replay lands.
6. Engine experiments, validated *in* the dashboard: seeded stochastic branches (#1), then the
   reciprocal multi-entity pass (#6), then soft dynamic scoring (#3).

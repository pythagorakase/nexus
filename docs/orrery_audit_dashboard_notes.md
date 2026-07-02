# Orrery: Auditability and Resolution-Quality Brainstorm

Working notes from a fresh read of `nexus/agents/orrery/` (resolver, substrate, templates, worker, retrograde cluster, tag_writer, migrations 023/024/041). Goal: move Orrery from "works" toward "reliably generates appropriate and dynamic resolutions," and design a dashboard that makes its reasoning visible and auditable.

**Verification pass (2026-07-01):** every load-bearing claim below was checked against the code and the live databases (`NEXUS_template`, `save_02`, `save_05`). Corrections are applied inline rather than appended, so this document reads as current truth. The headline changes: as-of reconstruction is *harder* than first written (the bestowal-key caveat resolved negative), the explain-evidence layer is *cheaper* than first written, event chaining is aspirational rather than emergent, "one package per actor" was wrong (it's one per binding set), and the form-factor question is resolved in favor of a dev-only route in the existing app.

## Current Checkout Delta

These notes originally framed an explain-evaluator as the first backend gap. In the current checkout, that primitive already exists:

- `nexus/agents/orrery/explain.py` provides `trace_condition()` (:174), `explain_template()` (:207), and `explain_stack()` (:280). `trace_condition` is its own recursive walker over `CompoundCondition.op/.children` and leaf `__name__`s (it does not use substrate's `_condition_tree_leaves()`).
- `StackExplanation.to_dict()` already returns: bindings, winner id, shadowed ids, and per template — priority, drive band, blurb, required slots, present-target policy, gate pass/fail with full gate trace, fired flag, chosen branch, per-branch traces, magnitude, event type, narrative stub, state delta, winner/shadowed flags.
- Three `Resolution` fields are currently **dropped** by `TemplateExplanation.to_dict()` and must be restored for the dashboard: `scene_pressure_stub` (needed for the "scene pressure on on-screen entities" question), `changed_fields`, and `binding_hash` (the dedup key for multi-binding stacks).
- Branch traces are exhaustive only up to the first passing branch: later branches carry `considered=False, trace=None` (explain.py:220–231). Gate traces *are* exhaustive. So a single explain payload cannot answer "which branches are dead behind their gates" — that is coverage-analyzer territory (or an opt-in exhaustive-trace mode).
- `nexus/agents/orrery/demo.py --explain` emits the JSON shape to crib from (preset-based).
- `tests/test_orrery/test_explain.py` guards the important invariant: explain output must match production `evaluate_stack()` selection while retaining the shadowed packages. Note it guards **single-stack parity only** — see the stack-split trap below. The divergence `AssertionError` path itself is untested; worth a deliberately-impure-predicate fixture.

So the next step is not "invent explainability"; it is **connect the existing explain stack to real slot hydration, entity name/context hydration, overrides, and a dev dashboard** — while replicating production's stack splitting faithfully.

---

## Three Findings That Reframe the Work

### The Clock Is Mostly an Illusion Today — and Honest Rewind Is Harder Than Hoped

`hydrate_world_state(anchor_chunk_id=N)` (resolver.py:239–457) rewinds: **recent events** (window filter), **world time / time-of-day**, the **need-debt accrual tail** (accrual is computed against the anchor's world time), and — outside hydration — **the actor roster** (`_present_actor_ids_at_anchor`, binding windows). Everything else reads *current* projections:

- tags from `entity_tags_current` (a `VIEW` of `entity_tags WHERE cleared_at IS NULL`)
- locations/activities from `characters.current_location` / `current_activity` (scalars)
- relationships/trust from `entity_relationships_v`
- pair tags from `entity_pair_tags WHERE cleared_at IS NULL`
- travel states, routine anchors, faction memberships, weather (a static story-seed value) — all current, no as-of variant

So "load slot 2, set clock to chunk 1400" shows a 1400-era roster, events, and clock wrapped around today's tags, positions, and relationships. The historical roster makes the chimera *more* convincing, not less — for an audit tool that is a correctness trap.

The original caveat — "confirm rows carry a chunk-id bestowal key" — **resolves negative**, and the "cheap mechanical query rewrite" framing dies with it:

- `entity_tags` / `entity_pair_tags` have **no chunk-id column**. `applied_at` is wall-clock `now()`; `applied_at_world_time` is nullable and unreliably populated (the resolver's own template bestowals leave it NULL — save_05 has 22/35 NULL; save_02 is dense only because retrograde backfill sets it).
- The tables are **not append-only in practice**: reapplication policies `replace` / `extend_expiry` UPDATE `applied_at` / `applied_at_world_time` in place on the active row (tag_writer.py:488–533), destroying original bestowal history.
- Clearance is wall-clock `cleared_at` on-row. Chunk/world-time clearance provenance exists only in `tag_clearance_log`, which not all clear paths write (save_02: 398 of 403 cleared rows have no log entry) and which **does not cover pair tags at all**.
- `entity_relationships` is not a table: `entity_relationships_v` is a UNION view over three **mutable, unversioned** current-state tables. There is nothing to rewrite — though in practice relationships are near-static today (no runtime writer applies `RelationshipUpdate`), so "assume static, label unversioned" is honest.
- Position: `world_events` cannot support replay — the movement vocab exists but **zero movement rows exist in any slot**, and resolution events carry no destination. The real Orrery-side replay source is `orrery_resolutions.state_delta` (`travel.arrive.destination_place_id`). Even perfect replay can't reconstruct position, because the Skald on-screen commit path overwrites `current_location` **with no event of any kind** (commit_handler_sync.py:625–638).
- Need debt: the accrual formula clamps elapsed time to no-op when a fulfillment postdates T (needs.py:290–291) — so it is not "partly polluted"; whenever any post-T fulfillment exists, the rewind is exactly zero. Full honest replay *is* feasible from `orrery_resolutions` promoted `need.fulfill` deltas plus accrual rates.

**Verdict per state axis:**

| Axis | Honest as-of is… |
|---|---|
| Recent events, world time, time-of-day, roster | Already honest |
| Single-entity tags | Event reconstruction with gaps (bestowal-side filter works only where world time is populated; cleared/replaced rows partly unrecoverable) |
| Pair tags | Same, worse (no clearance log exists) |
| Relationships/trust | Impossible by schema; near-static in practice — label as unversioned |
| Position/activity | Impossible for Skald-driven changes (no instrumentation); replayable for Orrery-driven changes via `orrery_resolutions.state_delta` |
| Need debt | Fully replayable from `orrery_resolutions` deltas |
| Travel state, routine anchors, faction membership, weather | No history; frozen in every mode |

Two standing rules fall out: **never use wall clocks as chunk proxies** (retrograde backfill wrote months of world time at one wall-clock instant; as-of predicates must be world-time based via `chunk_metadata.world_time`, which is fully populated), and **provenance is per-row, not global** (`source_kind` × has-world-time × has-clearance-log determines whether each tag's as-of answer is exact, approximate, or unknowable — a single "position approximate" flag is too coarse).

**Cheap forward-fix migrations** make tags/pairs truly mechanical *going forward*: add `source_chunk_id` to bestowals (the apply path already holds it), populate `applied_at_world_time` in the resolver's bestowal INSERTs, and extend clearance logging to pair tags and tag_writer clears. Pre-migration rows stay approximate; the hover-audit renders a per-row provenance epoch.

**Implication for the dashboard:** offer three honest modes rather than one dishonest clock.

1. *Current-state* (default): real now. "What fires this tick."
2. *What-if / sandbox*: current state + dev overrides (toggle a tag, move an actor, set a need, inject a recent event), then re-resolve live. `WorldState` is a frozen dataclass, so "copy with overrides" is trivial. **This is the highest-value mode and the cheapest to build.**
3. *True as-of* (fast-follow, gated on the forward-fix migrations): honest rewind for tags / pairs / need debt with per-row provenance; relationships labeled unversioned; position labeled non-rewindable until new instrumentation exists.

The mode label must enumerate which axes rewind, not present a binary honest/chimera switch.

#### Reconstruction Sufficiency — the Design Bar for Logging

A sharper way to state the goal: **could a fully instrumented run reconstruct world state at any historical chunk?** Reconstruction at arbitrary T requires exactly two artifacts — a snapshot of initial state, plus a complete, totally ordered, chunk-keyed log of every mutation since. Orrery's half is already event-sourced: `orrery_resolutions` persists the full `state_delta` JSONB of every committed resolution (tag bestowals/clears, `need.fulfill` with discharge, `travel.arrive` with destination, activity changes) keyed by `tick_chunk_id` and stamped with `promotion_status`, and `chunk_metadata.world_time` provides a reliable replay clock. Replaying deltas 1→T over a genesis state reconstructs every Orrery-driven axis, cheaply.

But sufficiency is a property of the **whole write surface**, not of Orrery alone — and even a from-day-one run would leak. save_05 is the natural experiment: a slot where Orrery ran live from the start, already exhibiting the pathologies. The leaks:

- **Skald's on-screen commit path** moves characters and sets activity with no event of any kind — invisible to any replay, forever. No amount of Orrery-side logging compensates. This is the single biggest hole.
- **Skald inline tags** are written without world-time stamps (19 of save_05's 30 NULL-world-time bestowals are `skald_inline`).
- **Pair-tag clears** are never logged on any path.
- **Tag reapplication** (`replace`/`extend_expiry`) mutates the projection row in place — survivable only because the authoritative record lives in `state_delta`, not the projection.
- **Relationships** sit on mutable, unversioned tables; the first runtime writer to land will destroy history on contact.
- **No genesis snapshot exists as an artifact.** The wizard's initial state is written as current-state rows that then mutate in place, so "initial" is recoverable only if every later mutation was logged — which is circular.
- **Decision history is a separate ledger from state history**, and only the latter is (mostly) covered: ratified proposals and scene pressures leave no record at all, so one can reconstruct what the world looked like but not always what Orrery proposed and Skald silently accepted.

**The "sufficient-from-now-on" requirements** (this is the design bar the forward-fix migrations should aim at):

1. **Skald-side chunk-keyed delta logging** on the on-screen commit path — a peer requirement to Orrery's own logging, not an afterthought. Once it exists, position/activity become replayable going forward.
2. **A genesis snapshot, plus periodic checkpoints** (every N chunks): bounds replay cost, and gives mature slots like #1 an explicit instrumentation-era boundary — exact after the checkpoint, approximate before.
3. The forward-fix migrations above (bestowal `source_chunk_id`, world-time population in resolver INSERTs, pair-tag + tag_writer clearance logging).
4. **Relationship versioning before any runtime writer lands.**

Two dividends follow. *Determinism:* because the resolver is pure and deterministic, a complete log enables not just reconstruction but **counterfactual re-resolution** — run today's (or an experimental) resolver against honest chunk-T state and diff outcomes; that is the coverage analyzer and the engine-experiment validation loop, unlocked by the same artifact. *RNG compatibility:* the seeded stochastic branch selection proposed below does not threaten reconstructability — the PRNG is keyed on values persisted with every resolution (actor, tick chunk, template, plus any configured salt), and the committed `state_delta` log, **not a re-run of the sampler, remains the replay authority**. Re-running the engine to reconstruct state would require the identical code version and temperature config; replaying logged deltas requires neither. The rule: "re-resolve" is for counterfactuals, "replay the log" is for reconstruction — never substitute one for the other.

### "Why Did This Fire?" Now Has a Core Primitive — and Evidence Is Cheaper Than Hoped

Conditions are opaque `bool`-returning callables (`Condition`), composed via `CompoundCondition(op, children)`. Production `evaluate()` returns only the winning branch. The explain layer walks compound gates exhaustively, records pass/fail at each node, renders predicate prose through the same catalog machinery as `docs/orrery_packages.md`, cross-checks each explanation against production `evaluate()` (fails loudly on divergence), and returns every priority-ordered template with winner and shadowed packages flagged.

What it does **not** do yet:

- expose the underlying values that made a leaf predicate true/false (`sleep debt = 18.4`, `actor tags include off_grid`)
- explain real slot actors; the demo harness is preset-based
- combine traces with entity hover data, adjudication history, or sandbox overrides

The evidence gap is smaller than originally framed. Predicates are closures built by ~57 factory functions in `substrate.py`, each stamped with a machine-parseable `__name__` (e.g. `has_need_debt_at_or_above(sleep,12@actor)`) that the catalog already regex-parses (`_PREDICATE_PARSERS`). So **config parameters (tag names, thresholds, slots) are already fully recoverable without touching substrate**. Only *observed* values need new code, and two paths exist:

1. **Parse-and-recompute (recommended first):** an evidence resolver in explain.py keyed on predicate kind recomputes observed values from `(state, bindings)` — `WorldState` is a plain frozen dataclass. No substrate changes; drift risk is covered by the existing production cross-check. Predicate purity is institutionalized (each already runs ~3× per explain), so recomputation is safe by construction.
2. **Evidence closures at the factory:** extend `_named()` to attach an optional `condition.evidence(state, bindings) -> dict`. Single-source but touches all 57 factories.

Either way, evidence for `has_any_*` family predicates must report **which family member matched** — "the hover-audit must name the family responsible" is unmeetable with a bare bool.

Payload hygiene notes: non-fired templates carry default `magnitude=0.0` / `event_type=null` (Resolution defaults) — null them out when `fired=False` so the UI can't render them as meaningful. Compound-node `raw`/`prose` are low-value (`"AND(3)"`, `"and"`); the UI should own compound presentation off `op`/`children`.

### Event Chaining Is Aspirational, Not Emergent (New Finding)

The gates are real; the emitters are not. Verified consumer map:

- `threat_issued` → gates WARN_ALLY, CONSULT_RIVAL, SURVEIL, and PROTECT_KIN
- `compliance_alert` → gates EVADE_PURSUERS, WARN_ALLY, CONSULT_RIVAL; appears in a HIDE *branch* condition (affects how, not whether)
- `faction_realignment` → gates CONSULT_RIVAL
- `encoded_message` → gates HONOR_DEBT

**No package branch emits any of these four event types.** They exist only in demo presets; in production they can arrive solely from exogenous writers (e.g. a Skald `replace` ruling that supplies `replacement_event_type`, or future systems). Package→package chaining (A fires → B's gate opens) therefore cannot occur today. The only live cross-package coupling is *inhibitory*: shared cooldowns via `since_last_event_at_least` on genuinely emitted types (`contact_made` et al.).

Three consequences:

- A tick-scoped "causal web" visualization would render nearly empty. The interaction graph should visualize **package → target-entity edges** (real today) and *potential* event edges (gate-consumed types), styled distinctly from *realized* ones.
- The health strip gets a cheap, high-value static lint: cross-reference gate-consumed vs branch-emitted event types and flag **dead gate arms** — unreachable without an external writer.
- Lighting up genuine chaining (letting packages or Skald emit these types) is itself a cheap, high-leverage engine experiment, and the dashboard is where its effects become visible.

---

## How Resolution Actually Works (Ground Truth)

Every tick, `resolve_dry_run` splits templates into **two independent stacks** and runs winner-take-all **per binding set**, not per actor:

1. **Actor-only stack:** one `evaluate_stack()` per off-screen actor.
2. **Two-party stack:** one `evaluate_stack()` per composed (actor, target) pair — both orderings of every relationship edge are composed, so A→B and B→A drafts coexist.
3. **Present-target pass:** scene pressures against on-screen entities (prompt-only).

So an actor with N live relationship edges can emit 1 + N resolutions plus pressures in a single tick. "Exactly one package per actor" — the original claim here — is wrong, and the per-actor dashboard card must be a per-actor **group**.

Within a stack:

- **Package selection is winner-take-all by static priority.** Sort descending, first template whose gate passes and has a firing branch wins; the rest are silently discarded. **Priority ties exist** (CULTIVATE_INFORMANT = KEEP_VIGIL = 50; MOURN_LOSS = SLEEP = 25) and are broken by authored tuple order in `BUILTIN_TEMPLATES` — an invisible dependency the dashboard should surface.
- **Branch selection is first-passing in authored order.** Branches are authored in roughly descending `magnitude` with a terminal `ALWAYS` fallback — but that ordering is convention, not engine (INTIMACY's fallback magnitude 0.10 exceeds its preceding private branch's 0.06), and `validate_always_fallbacks` is enforced at **test time**, not import time (only the fame validator runs at import).
- **It is fully deterministic.** Same state ⇒ same package ⇒ same branch, every time.
- **`magnitude` is salience, not a selector — in the resolver.** Downstream it *does* drive promotion: `worker.py` promotes on `priority >= 30 OR magnitude >= 0.35` (`[orrery.promote]`). The promote threshold 30 sits deliberately in the 26→35 priority seam; MAINTAIN_COVER is priority 0 and band-exempt. Any priority/scoring experiment must account for this coupling.

Two catalog caveats: `drive_band_priority_warnings()` currently returns `()` on the builtin set — every inversion is rationalized or exempt, so the lint is a tripwire for *future* authoring, not an outstanding smell. And the per-need scene pressures (`{need}_need_pressure`, priorities from `[orrery.sunhelm]`) are **pseudo-templates outside the catalog** — a drive-band-grouped view must include them explicitly or they vanish.

**The stack-split trap (dashboard-critical):** `explain_stack()` takes one template iterable. Tracing a two-party template with only `ACTOR` bound makes every `@target` leaf read `None` and report `False` — rendering "not applicable, no target bound" indistinguishable from "gate failed." The `/resolve` endpoint must replicate production's stack splitting and binding composition, and the payload needs an explicit **not-applicable marker** distinct from gate failure. `tests/test_orrery/test_explain.py` does not guard this; the endpoint tests must.

---

## The Categories You Asked About

Yes — real categories exist in the backend, beyond the SunHelm trio.

### Drive Bands (the Backend Taxonomy)

`DriveBand` is a 5-value enum on every `Template`, with a canonical urgency order (`DRIVE_BAND_ORDER`). This is the natural top-level grouping for the dashboard — it matches both the engine and the way you already think. (Band membership verified template-by-template; the table is accurate.)

| Band | Packages |
|---|---|
| `CRISIS_CONSTRAINT` | EVADE_PURSUERS, PROTECT_KIN, TEND_WOUNDED, HIDE, WARN_ALLY, MAINTAIN_COVER |
| `EMBODIED_MAINTENANCE` | **SLEEP, DRINK, EAT** (the SunHelm trio) |
| `ANCHORED_ROUTINE` | ROUTINE_COMMUTE, TRAVEL, WORK |
| `AFFILIATION` | CHECK_ON_DEPENDENT, KEEP_VIGIL, REACH_OUT_TO_KIN, MOURN_LOSS, SOCIALIZE, INTIMACY |
| `PROJECT_IDENTITY` | EXTRACT_VENGEANCE, HONOR_DEBT, PURSUE_GHOST_LEAD, CULTIVATE_INFORMANT, SURVEIL, CONSULT_RIVAL, TEND_CRAFT |

A happy accident for the UI: five bands, five `--chart-1..5` theme tokens. One color identity per band, reused everywhere (rail, card edges, health strip).

### Cross-Cutting Axes (Filter/Highlight, Not Primary Grouping)

- **Slot arity — the multi-entity axis you most want visible.** Single-actor (`ACTOR`) vs two-party (`ACTOR, TARGET`). The two-party set is exactly the "entities interact" cluster: PROTECT_KIN, EXTRACT_VENGEANCE, TEND_WOUNDED, WARN_ALLY, CHECK_ON_DEPENDENT, CULTIVATE_INFORMANT, KEEP_VIGIL, SURVEIL, REACH_OUT_TO_KIN, CONSULT_RIVAL. Make this a first-class flag/lane.
- **Present-target policy.** All 10 two-party packages carry `present_target_policy = STORYTELLER_PRESSURE` — the two axes are **100% coextensive today**, so the UI needs one lane with two chips, not two lanes; if they ever diverge the distinction is already modeled.
- **Event families.** See the finding above: visualize potential vs realized edges distinctly; lint dead gate arms.
- **Tag families (suppressor/enabler linkages).** Curated frozensets in `substrate.py` couple behavior across many packages: `INTIMACY_SUPPRESSOR_TAGS`, `HIDDEN_TAGS` (composed into `DRAMATIC_CONTACT_TAGS`), `CONSTRAINED_TAGS`, `PUBLIC_MOBILITY_TAGS`, `PUBLIC_PLACE_CLASSES`, `ESTABLISHED_PARTNER_RELATIONSHIP_TYPES`. A single ephemeral like `grudge_active` silently suppresses several other packages. When a resolution feels "wrong," an invisible family tag is often the cause — so the hover-audit must name the family *and the specific member that matched* (hence the evidence requirement above).

### The SunHelm Trio in Context

SLEEP/DRINK/EAT *are* the `EMBODIED_MAINTENANCE` band — your intuition maps onto a real backend category. Their shared unique mechanic is `need.fulfill` (quality + discharge) over need-debt scoring. EAT and DRINK are further coupled: DRINK's gate defers when hunger is high and a meal is imminent. So "the trio" is really "a band with an extra intra-band coupling."

---

## Ideas to Move From "Works" to "Reliably Appropriate and Dynamic"

### Dynamism (the "Same State ⇒ Same Beat" Problem)

1. **Seeded stochastic branch selection.** Collect *all* passing branches and sample weighted by `magnitude` (softmax with a temperature from `nexus.toml`). Key the PRNG on `(entity_id, tick, template_id)` — `binding_hash` (sha256 of sorted bindings) is a ready-made ingredient — so it stays **reproducible** while a character no longer "drinks routinely" identically every eligible tick. Implementation constraints discovered: selection logic must live in **one shared, seed-keyed function used by both `evaluate()` and `explain_template()`**, because the two cross-check each other and raise on divergence; and sampling requires evaluating all branches, which changes the `BranchTrace.considered` semantics (a payload version bump, and the dead-branch question becomes answerable for free). New knobs go through `OrrerySettings` (`extra="forbid"` — Pydantic plumbing plus nexus.toml entries, per the no-hardcoded-tunables directive; note template priorities themselves currently violate its spirit). Reconstruction-safe by design: the seed inputs are persisted with every resolution, and the committed `state_delta` log — not a re-run of the sampler — remains the replay authority (see Reconstruction Sufficiency above).
2. **Intensity-modulated temperature.** Let how *hard* the gate matched lower the temperature: desperate states (sleep debt 48) resolve sharply; mild states wander. Needs the structured-evidence layer first — which is now the cheap parse-and-recompute path, not a substrate rewrite.

### Appropriateness (Winner-Take-All Flattens Off-Screen Life)

3. **Soft dynamic scoring instead of a static ladder.** Replace (or wrap) fixed `priority` with `effective_score = base + situational modifiers` (need-debt intensity, event recency decay, trust extremity). Turns the brittle global ladder into a scoreboard and dissolves the tie-by-tuple-order dependency. **Caveat found in verification:** the promotion pipeline reads the *persisted* `priority` from `orrery_resolutions` against `[orrery.promote].priority_threshold = 30`, calibrated to the static ladder's 26→35 seam — dynamic scores need a new persisted column or a recalibration, surfaced in the UI. Most invasive; highest ceiling.
4. **Primary + ambient layering.** Surface one primary resolution *plus* optionally one ambient embodied-maintenance beat, so a hunted-and-hungry character isn't monomaniacally "just evading." (Also a dashboard requirement: always show the shadowed stack, not only the winner.)
5. **Light hysteresis for project-identity arcs.** A small bias to continue an in-progress arc (PURSUE_GHOST_LEAD, CULTIVATE_INFORMANT) rather than scatter. Event cooldowns already prevent thrash; this adds positive momentum. The defer-streak metric from the adjudication log (below) is the natural evidence for tuning it.

### Multi-Entity Interaction (the Richest Untapped Vein)

6. **Reciprocal/conflict pass.** Cheaper than originally framed: `compose_actor_target_bindings` already emits both orderings of every relationship edge, so A→B and B→A drafts coexist in one `OrreryTickProposal`. A reciprocal/conflict detector is a **pure post-pass over `proposal.resolutions`** keyed on reversed (actor, target) — no resolver change — that composes matches into a single joint beat: a handshake, a missed connection, an ambush. This is where genuine off-screen drama between characters emerges.
7. **Emit the dormant trigger events.** Give EXTRACT_VENGEANCE / SURVEIL / faction machinery branches that emit `threat_issued` / `compliance_alert` / `faction_realignment`, or let Skald rulings emit them routinely — turning today's dead gate arms into real chains.

### Authoring and Coverage

8. **Tag-family transparency + lint.** Make the suppressor/enabler families first-class and documented; lint for over-broad suppression (a tag silently killing too many bands).
9. **Coverage analyzer over real history.** Run the resolver across a window of historical chunks and report: actors with *no* firing package, packages that *never* or *always* win, dead branches (needs exhaustive traces), dead gate arms (static, from the emit/consume cross-reference), and data-quality findings (NULL bestowal world times, wall-clock backfill epochs). The dashboard's batch-over-chunks mode *is* this analyzer — auditing and coverage testing are the same tool.

---

## The Audit Dashboard

### Form Factor — Decided: Dev-Only Route in the Existing App

The standalone-SPA alternative is dropped. The repo already contains the exact precedent: `DevMarkdownPreview` is lazy-loaded only when `import.meta.env.DEV` and registered at `/dev/markdown` (App.tsx). The gateway is a single FastAPI app (`nexus/api/narrative.py`) with modular `/api/<area>` routers, the Vite dev server proxies `/api` to it, and `nexus up` already manages the process — a new router plus a new page costs zero new process, port, CORS, or proxy work. A standalone SPA would need its own `[runtime.services.*]` block and could not reuse the compiled component library without living inside `ui/client` anyway. Decisive for prototyping: the design-sync harness means a Claude Design prototype authored against `nexus-ui` ports ~1:1 into a `/dev/orrery` page.

**Server-side gating is required, not optional.** `import.meta.env.DEV` gates only the client bundle; the gateway has no auth, CORS `*`, and is slated for Cloudflare exposure (issue #415). Register the dev router conditionally behind a `[orrery.dashboard] enabled = false` key under the existing `[orrery]` section — one boolean satisfies the no-hardcoded-settings directive and closes the tunnel hole in one move. (The eventual "hidden developer pane in the desktop app" cannot reuse `import.meta.env.DEV` either — the Tauri build loads the production bundle — so the same runtime flag serves both.)

This fits NEXUS conventions cleanly: configurable via `nexus.toml`, surfaces errors loudly, keeps writes out of the audit path, and avoids mocks — the resolver is deterministic and API-free, so FastAPI TestClient against real slot DBs is the anti-mock CI surface.

### Backend — What Exists vs. What to Add

Already there: `hydrate_world_state()`, `compose_actor_bindings()` / `compose_actor_target_bindings()`, `resolve_dry_run()` → `OrreryTickProposal`, `_load_entity_names()`, `explain_stack()`, `StackExplanation.to_dict()`, the `demo.py --explain` payload, slot plumbing (`require_slot_dbname`, `/api/slot`), and the full adjudication persistence layer (`incubator.orrery_proposal/orrery_adjudications`, `orrery_adjudication_log`, `orrery_resolutions.promotion_status/promotion_verdict`).

To add:

- **A slot-backed explained resolver** that mirrors `resolve_dry_run` exactly: hydrate real slot `WorldState`, split stacks, compose bindings per arity, run `explain_stack()` per binding set, attach entity names, mark not-applicable vs gate-failed, null magnitude/event on non-fired templates, restore the three dropped `Resolution` fields, and include the need-pressure pseudo-templates. Endpoint tests must assert parity with `resolve_dry_run` winners (the existing test only covers single-stack parity).
- **An entity hover/context hydrator:** tags grouped durable/ephemeral/family (with per-row provenance), pair tags, relationships/trust (labeled unversioned), needs, travel state, routine anchors, current place/classes, recent events.
- **An overrides layer on `WorldState`** for what-if mode (toggle tag, move actor, set need, inject event) — frozen-dataclass copy, no canonical writes.
- **The evidence resolver** (parse-and-recompute) enriching leaf traces with observed values and matched family members.
- **As-of hydration variants** for tags/pairs/need-debt, gated on the forward-fix migrations.
- **Reconstructability logging** (see Reconstruction Sufficiency): Skald-side chunk-keyed delta logging on the on-screen commit path, genesis snapshot + periodic checkpoints, relationship versioning before any runtime writer lands.
- Endpoints, following repo convention under `/api/dev/orrery/*`:
  - `GET /api/dev/orrery/catalog` — templates + pseudo-templates grouped by drive band with cross-cutting metadata, tag families, and the emit/consume event map.
  - `POST /api/dev/orrery/resolve` — full per-actor groups with traces, shadowed stacks, scene pressures; accepts slot, anchor, mode, overrides.
  - `POST /api/dev/orrery/context/entities` — hover payload for visible entity ids.
  - Later: `GET /api/dev/orrery/history/adjudications` (see below).

**Adjudication history — feasible now, with known holes.** The vocabulary is exactly `defer / replace / void` (Pydantic, JSON schema, engine, and DB CHECK all agree). Per-package rates are computable today by joining `orrery_adjudication_log` with `orrery_resolutions`. The holes to design around (and cheaply fix):

- Ratified proposals leave **no record at all** (a log row exists only when a ruling does), and the full proposal (bindings, names, stub) lives only in the incubator row, which is deleted at commit. "Proposal patterns" reconstruct as a two-table union with per-draft context lost for non-committed proposals.
- The storyteller prompt renders only the **first 5** proposals (and 5 pressures) with ratify-by-omission semantics, and nothing records which were shown — so "Skald saw and ratified" vs "never saw" is currently indistinguishable. Log the shown set.
- `adjudication_source='structured_state_update'` rows are machine-inferred replaces, not authored rulings — always facet on source.
- The log has **no `actor_entity_id`** (`binding_hash` is an opaque sha256): once the incubator clears you cannot say *who* a deferred proposal was about. Add `actor_entity_id` (+ optionally bindings JSONB) at insert time — the draft is in hand.
- A replace-with-delta whose resolution insert hits `ON CONFLICT DO NOTHING` skips the log write entirely; scene pressures have zero persistence (the "pressure on on-screen entities" question is answerable live, never historically, until pressure drafts are logged at commit).
- The funnel has a **third stage** worth including: proposal → adjudication → committed → promoted/narrated (`promotion_status`, narration pipeline) — full lifecycle per package.
- The single most diagnostic derived metric: **defer streaks** (`proposal_id` = `template_id:binding_hash` is stable across ticks and indexed) — "package X deferred N consecutive ticks before ratification/void."

**Slot reality for auditing:** save_01 (golden master) contains zero Orrery data; save_02 is the dense audit target (retrograde-backfilled history, with the wall-clock-epoch caveat); save_05 is small live-runtime data exhibiting the NULL-world-time bestowal pathology — itself worth surfacing as a health-strip data-quality finding. Default the dashboard to save_02.

### Organization

Primary grouping by **drive band** (matches backend + your "categories make my brain happy"), band color identity from `--chart-1..5`. A prominent **multi-entity lane/flag** cuts across all bands. Filters for the other axes (present-target, event family, tag family). Within a group, order by the actual resolver decision and distinguish **four** template states — not two: *winner*, *shadowed* (fired, outranked), *gate-failed* (evaluated, refused), and *not-applicable* (no target bound — never conflate with failure).

---

## Claude Design Prototype Brief

Everything in this section is written to be handed to Claude Design as-is. The design project already carries the synced `nexus-ui` package (the real compiled component library) and the Veil theme; author the prototype by importing from `nexus-ui` and wrapping the screen in `DesignThemeRoot`, so the JSX ports ~1:1 into `ui/client/src/pages/` afterward.

**Visual language.** Veil theme, dark only: deep blue-black background, warm cream foreground, magenta-rose primary, coral accent. Use theme token utilities exclusively (`bg-background`, `bg-card`, `text-foreground`, `text-muted-foreground`, `border-border`, `bg-primary`, `text-accent`, `--chart-1..5`) — never raw hex. Type: Spectral for content, Cinzel for chrome labels (uppercase only in chrome, per house style), Megrim reserved for the one display moment if any. Content (character names, narrative stubs, predicate prose) renders in natural case. House minimalism doctrine applies even to this dev surface: this dashboard is *data-dense but label-sparse* — the trace tree and the cards ARE the explanation; no explanatory paragraphs, no eyebrow-title-subtitle stacks, one label per section, counts as badges not sentences.

**Canvas.** Desktop, ~1440 wide, a single working screen with three regions plus a top strip. Use `Resizable` panels for the three regions.

**Top strip — the tick bar.** One slim row: slot selector (Select), anchor-chunk stepper with current world-time readout (mono), a mode chip group (`CURRENT` / `WHAT-IF` / `AS-OF`), and a re-resolve action (icon button). The mode chip is the honesty label: `WHAT-IF` state wraps the entire canvas in a dashed accent-colored frame so a sandboxed state can never be mistaken for canon; `AS-OF` opens a small Popover enumerating per-axis honesty (events ✓, tags ≈, relationships frozen, position frozen) rather than pretending a binary. Transient resolve progress lives here and vanishes when idle.

**Left rail — bands and filters.** Sidebar listing the five drive bands in urgency order, each row: band color dot (chart token), band name (Cinzel), count Badge of winners this tick. Below, a thin filter cluster: two-party lane toggle, tag-family filter (Command palette picker), event-family filter, "show gate-failed" and "show not-applicable" visibility toggles (both off by default).

**Center — the actor stream.** One collapsible group per off-screen actor (actor name + portrait chip + location chip). Within a group: the actor-only winner card, then one card per (actor → target) two-party resolution, then scene-pressure chips (outline Badge with a small arrow glyph pointing at the on-screen target's name). Card anatomy (Card component): 3px left edge in band color; package name; branch label (muted); narrative stub in Spectral italic; right-aligned magnitude as a small radial or numeric chip; event-type Badge if emitted. Beneath each winner, a Collapsible labeled only by a count Badge ("3") expands the shadowed stack: same card anatomy at reduced opacity, in priority order. Gate-failed and not-applicable templates render (when toggled on) as ghost rows — single line, dimmed, no fill; not-applicable rows carry a slot-glyph marker distinguishing them from failures. After a what-if re-resolve, cards whose outcome changed vs. the pre-override tick get a small accent diff dot; unchanged cards stay quiet.

**Right panel — the inspector.** Opens on card select (single click; no card navigates away). Contents, top to bottom: the winning package header (band color, name, priority, tie marker if priority was tied and tuple order decided); the **gate tree** — an indented tree of AND/OR/NOT nodes with per-node pass/fail glyphs (check / cross, never color-only), leaf predicate prose in natural case, observed evidence values right-aligned in mono (`sleep debt 18.4 ≥ 12`), and the matched family member named on family predicates; then the **branch ladder** — every branch in authored order with magnitude, the selected one marked, branches above it showing their failing leaf inline, branches below it marked unevaluated; then the state delta and emitted event as compact key-value rows. The failing path from any failed node up to the root is emphasized (weight, not color alone).

**Hover-audit.** HoverCard on *any* entity name anywhere on screen: header (name, place, place-class chips); needs as five thin meters; tag chips grouped durable / ephemeral, each carrying its family membership as a subtle prefix glyph, with a per-row provenance dot (solid = exact, ring = approximate, hollow = unknowable); relationship rows (type, trust, "unversioned" watermark); recent events (last 3, mono timestamps). Hovering a tag chip while the inspector is open highlights every node in the trace that reads that tag or its family.

**What-if drawer.** The mode chip's `WHAT-IF` state opens a Sheet from the right edge (over the inspector): override rows — toggle tag (Command picker over the tag vocabulary), set need (Slider per need), move actor (place picker), inject recent event (event-type picker + payload stub). Each active override renders as a removable accent chip pinned under the tick bar. Apply = re-resolve; the dashed sandbox frame appears with the first override.

**Health strip.** A bottom drawer (Collapsible) — not persistent chrome — with four ChartContainer tiles keyed to band colors: winners per band this tick; coverage gaps (actors with no firing package, listed by name); never/always-win packages over the loaded window; dead gate arms + data-quality warnings (NULL bestowal world times, wall-clock epochs) as a short table. Everything in the strip is drill-through: clicking a gap actor scrolls the stream to them.

**Multi-entity interaction graph** (second tab of the center region, same tick): nodes = actors (portrait chips), directed edges = two-party resolutions this tick in band color; reciprocal pairs (A→B and B→A both fired) drawn as a doubled edge with a joint-beat marker; conflicting pairs flagged; scene-pressure edges drawn dashed toward a distinct on-screen entity row at the graph's edge. Potential-but-unrealized event edges (gate-consumed, never-emitted types) render as faint dotted arcs only when the event-family filter is active — the visual admission that chaining is aspirational.

Prototype with realistic seeded data shaped like save_02: real package names from the drive-band table above, 6–10 off-screen actors, at least one actor with an actor-only winner plus two two-party resolutions and one scene pressure, at least one priority-tie case, one what-if diff state, and one actor with zero firing packages (to exercise the gap treatment).

---

## Questions the Dashboard Should Answer Fast

Annotated with the layer that answers each:

- Why did this actor get this package instead of another plausible package? — *v1 resolve payload*
- Which package would have fired if the winner were disabled or deprioritized? — *v1 (shadowed stack)*
- Which specific tag, pair tag, need, location class, recent event, or cooldown suppressed the package I expected — and which family member did it? — *v1 + evidence layer*
- Is this template inapplicable (no target bound) or actually refused? — *v1 (not-applicable marker)*
- Which actors have no plausible package at all? — *v1 per tick; coverage analyzer over windows*
- Which packages never win in this slot, and which branches are dead behind their gates? — *coverage analyzer (branch-level needs exhaustive traces)*
- Which gate arms are unreachable because nothing emits their trigger events? — *static lint, catalog endpoint*
- Which two-party packages are exerting scene pressure on on-screen entities? — *v1 live; historical only after pressure logging lands*
- How often does Skald defer, replace, or void each package — and what are the defer streaks? — *adjudication endpoint, faceted by source, after log enrichment*
- Is the current "clock" mode honest, and on which axes? — *mode chip, per-axis*
- Could world state at chunk T be reconstructed exactly, and if not, which writer leaked? — *reconstructability logging + health strip, once the sufficiency bar is met*

---

## Suggested Sequence

1. **Backend v1:** `/api/dev/orrery/` router behind `[orrery.dashboard] enabled` — `GET catalog`, `POST resolve` (production-faithful stack split, entity names, not-applicable markers, restored fields, pseudo-templates, nulled non-fired magnitude/event), `POST context/entities`. Parity tests against `resolve_dry_run` winners on real slots.
2. **Claude Design prototype** from the brief above; port 1:1 into a `/dev/orrery` page (wouter route, `import.meta.env.DEV` + the toml flag).
3. **Override/sandbox layer** on `WorldState` (the high-value what-if mode) + the what-if drawer and diff dots.
4. **Evidence layer** (parse-and-recompute; matched-family-member reporting) enriching the inspector.
5. **Coverage analyzer** (batch over historical chunks) + dead-gate-arm lint + data-quality findings — auditing doubles as CI.
6. **Adjudication history:** log-enrichment migration (`actor_entity_id`, bindings, shown-proposal set, scene-pressure logging, close the ON CONFLICT log skip), then `GET history/adjudications` with lifecycle funnel and defer streaks.
7. **Reconstructability:** forward-fix migrations (bestowal `source_chunk_id`, populate `applied_at_world_time` in resolver inserts, pair-tag + tag_writer clearance logging), **Skald-side chunk-keyed delta logging on the on-screen commit path**, **genesis snapshot + periodic checkpoints**, and relationship versioning before any runtime writer lands — the full sufficiency bar from Reconstruction Sufficiency. Then as-of hydration for tags/pairs/need-debt with per-row provenance; position becomes replayable going forward once Skald-side logging exists.
8. **Engine experiments, validated in the dashboard:** seeded stochastic branches (shared selection function, `OrrerySettings` knobs, reconstruction-safe per the seeding rule), then the reciprocal multi-entity post-pass, then emitting the dormant trigger events, then soft dynamic scoring (with promote-pipeline recalibration).

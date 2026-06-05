# Orrery Retrograde — Deep-History Generation Spec

**Status:** Design spec, deliberately compressed. Phase A0 now has a non-mutating dry-run packet surface, and Phase A1 adds a non-mutating R4/R5 seed-generation request contract inside that packet. Larger implementation decisions remain deferred and flagged inline as **[OPEN]**.
**One-line frame:** Deep history is Orrery run backward. Same substrate, same vocabulary, opposite temporal direction. Output is `world_events` rows retrieved by MEMNON identically to play-generated history. Fires at wizard-time (whole-world cold start, pre-game tick stamps) and at runtime (per-entity stub maturation, current tick stamps) — see Stub Maturation below.

---

## Purpose

Cure Orrery's cold-start problem: a new narrative begins with an empty `world_events` table and feels lived-in only after many forward ticks. Retrograde front-loads connected backstory at setup time, when latency doesn't matter and inference budget is cheap, so the world has texture from scene one.

Non-goal: DF-style exhaustive deep history. We generate *shallow-but-connected* history — enough to ground starting state and seed surprise, not a full legends corpus.

---

## Stub Maturation — Wizard-Time and Runtime

The pipeline below runs at two distinct lifecycle points with the same substrate and largely the same logic, but very different cost budgets. The wizard-time firing — cold-starting a whole world from wizard input — is the primary frame above. The runtime firing handles a separate but mechanically identical problem: when *Skald-as-narrator* (the runtime narrative agent, distinct from *Skald-as-weaver* in Stage R6) introduces a new entity in prose (a passing NPC, a named place, an off-screen faction), that entity needs to become a connected, package-ready node before the player engages with it.

### Two-Tier Promotion

Entities enter the world in two stages, not one:

| Stage | Trigger | Cost | Output |
|---|---|---|---|
| **Stub creation** | Skald introduces a new entity in prose | Cheap — single declaration as part of Skald's structured response | Row in `characters` / `places` / `factions` + minimum viable tag set + the 1–2 sentence summary Skald wrote |
| **Maturation** | Engagement signal — player chooses a branch leading to the entity, asks about it, plans interaction with it | Expensive — full Stage R4–R6 pass | Connected relationship graph, history seeds in `world_events`, package-ready tag density |

A bare stub is enough to avoid the *forgotten throwaway line* failure mode — the entity exists, can be referenced consistently across chunks, can't be re-invented with conflicting attributes. But it's not mechanically active and can't participate in packages. Full maturation is what makes an NPC capable of pursuing, mentoring, retaliating, etc. — but it's expensive, so the system only pays for it on signal.

### Trigger: Skald Declares

The mid-narrative trigger is **Skald declaring new entities via structured output**, not a separate detection pass. Skald already has full context and is already producing a structured response per chunk; declaration becomes an additional field:

```json
"new_entities": [
  {"kind": "character", "name": "Lansky's old fence", "summary": "..."},
  {"kind": "place", "name": "The Drowned Atrium", "summary": "..."}
]
```

The writer pipeline that persists Skald's response is responsible for instantiating row stubs from these declarations with a minimum viable tag set. A lightweight rule-based audit (regex / NER + DB existence check, no LLM inference) MAY run as belt-and-suspenders to catch entities Skald mentioned in prose but failed to declare — but audit-derived stubs are lower quality (no Skald-curated summary), so the declaration path is the canonical one.

This trigger design is philosophically aligned with the post-LORE retrieval architecture: the frontier model already has the context, so the system does not insert a "smart" intermediate stage that could degrade the signal. The bitter lesson that retired LORE applies here too — let the capable consumer (Skald) tell us directly what's new rather than running a parallel detection pass.

### A/B/C Branch Economics

The motivating case: Skald offers the player A/B/C options leading to different new NPCs or locations. The player picks B. By the time the storyteller reaches B in the next chunk, B should be fully realized — and A and C should not become inert throwaway lines that never appear again.

**The maturation pipeline runs speculatively against all branches in parallel during the user's turn-composition pause.** The rendering layer only blocks on the chosen branch; unchosen branches' maturations complete in the background and persist — they're "warmed" if the player ever returns to them, hears about them, or asks. The cost of wasted maturation work on unchosen branches is the price of zero-stall on the chosen one. The economics are favorable because the work runs *between* turns, not *during* them.

**Implementation requirement:** the maturation pipeline must be **fire-and-forget against a job queue**, not a synchronous call. Designing it as async from the start is more work than synchronous expansion but is the difference between "this works for choice branches" and "this doesn't."

### Timing Budget Contrast

| Context | Budget | Knob settings |
|---|---|---|
| Wizard-time (whole-world cold start) | Minutes per slot | Latency irrelevant; over-generate 5×+ at Stage R4 and prune to 1×; slow frontier-model expansion at Stage R6 is fine |
| Runtime (single-entity maturation) | ~5–30 seconds in the async window | Tighter over-generation (~2×); may need faster model for Stage R6; async job queue non-negotiable |

Same pipeline, different knob settings. The pipeline isn't bifurcated — only the budget and concurrency model differ between firing contexts.

### Minimum Viable Tag Set

When Stage R4 (seed generation) introduces *implied* entities (the spouse of a stubbed NPC, the vanished sister implied by a foundational wound), those implied entities receive a **minimum viable tag set**: enough for the seed to be mechanically meaningful (e.g., `vanished`, `kin(→ Alex)`, a faction tag if implied) but no relationship graph of their own. They do not recursively trigger full maturation. Promotion to full maturation happens only through the runtime trigger (engagement signal), via the same mechanism that handles Skald-as-narrator's mid-narrative stub introductions.

This is what keeps Retrograde non-recursive: implied entities accrete just enough mechanical weight to matter, and pay for full realization only if and when narrative attention lands on them.

**Closed-vocabulary binding.** "Minimum viable tag set" is a *subset of registered `tags.tag` values*, not free-form strings. Retrograde inherits the runtime-write vocabulary lockdown shipped in #293 — neither wizard-time generation nor runtime maturation may write a tag absent from the `tags` registry. Stage R1 (vocabulary-table enumeration, issue #297) is what makes this binding mechanical rather than a prose assertion; the writer path enforces it via the same predicates the runtime tag-bestowal path uses.

---

## Pipeline

Six stages, labeled **R1–R6** to disambiguate from the forward Orrery pipeline's Stage 1–6 (Resolve/Commit/Clear/Promote/Narrate/Bleed in `orrery_design_plan.md`). Each consumes the prior; **[OPEN]** boundaries may merge during implementation.

- **R1. Vocabulary table.** Enumerate the seed-eligible primitives: event types, tags, relationship types, and semantic place classes already in the Orrery registries. Retrograde generates *only* in existing vocabulary so output is substrate-legal by construction. New vocabulary is out of scope for a generation run. The first-pass enumerator exists at `nexus/agents/orrery/retrograde_vocabulary.py`; pass a target slot `dbname` once migrations are applied so it folds live `tag_category_registry` / `tags` rows into the template-derived primitive set. The enumerator now also classifies registered tag categories as `stable_seed`, `event_anchored`, or `prompt_visible_only`: stable categories may appear as present-state seed outcomes, event-anchored categories require an explicit causing/recent-refresh event, and prompt-visible-only categories may guide prose but not mechanical seed writes.

  Phase A0/A1 packet assembly exists at `nexus/agents/orrery/retrograde_packet.py` and is exposed as `nexus retrograde-packet --slot N [--weird low|medium|high] [--weird-raw FLOAT] [--output packet.json]`. It reads wizard cache + vocabulary + configured weird bands, writes no canonical rows, and produces candidate prompt material plus a seed-generation request for Skald-as-weaver.

  The first Skald-facing seed surface exists at `nexus/agents/orrery/retrograde_seed_candidates.py`: it renders the seed-generation prompt, exposes a Pydantic JSON schema for candidate responses, validates returned mechanics against budgets and the seed-eligible vocabulary, and can make the live Skald call. This is still non-mutating. The CLI surface is `nexus retrograde-seed-candidates --slot N ...` when a wizard cache is active, or `nexus retrograde-seed-candidates --packet packet.json --output seeds.json` for a saved/reviewable packet. `--max-tokens` can override the normal wizard cap for calibration/demo runs because seed candidate responses are larger than ordinary wizard chat turns. The prompt includes a compact response contract while the full schema remains in the packet and the Pydantic AI `output_type`. A valid response can propose candidate-local events, stable single-entity tags, event-anchored tags with explicit supporting events, pair tags, and relationship hints. The validator rejects prompt-visible-only tag writes, unknown primitives, invalid pair-tag kind constraints, duplicate/unknown candidate ids, and selections that exceed the request target.

- **R2. Stub generator.** From wizard choices (setting, genre, starting characters, selected traits), emit entity stubs and a sparse relationship graph — the *intentional core*. This is deterministic-ish scaffolding, low entropy, fully implied by wizard input.

- **R3. Graph builder.** Expand the sparse core into a candidate relationship/event graph with open attachment points (dangling edges where history could connect).

- **R4. Seed generation (high-entropy, high-friction).** Over-generate candidate seeds — events, grudges, debts, secrets, vanished parties — that are *directionally connected* to the graph but NOT implied by it. This is where surprise is injected. Generate more than will be kept. The current implementation renders a Skald prompt from the dry-run packet, makes an explicit Skald call when requested, and requires JSON matching the seed-candidate response schema; no generated seed is persisted at this stage.

- **R5. Semi-constrained selection.** Filter/weight the candidate seeds by wizard choices (especially character traits) and the weird setting (below). Select a subset. **Discarded seeds cost only inference.** The current response schema lets Skald return `selected_seed_ids` / `rejected_seed_ids`; validation enforces that selected ids exist and stay within the `select_target` budget.

- **R6. Expansion pass (Skald-as-weaver).** Weave surviving seeds into a coherent web. The expansion model may **reject** seeds that won't cohere without contortion, not merely connect them. Every surviving thread must terminate by connecting to present canon (see Anchoring). Output: `world_events` rows + tag/relationship state, consistency-validated. *(The label "Skald-as-weaver" distinguishes this invocation from the runtime narrative agent — see Stub Maturation. Whether the two invocations literally use the same model is an implementation choice; the prompts and output schemas are not interchangeable.)*

---

## Entropy / coherence control

Two opposing forces, one tunable band:

- **Seed stage** pushes toward variance (friction, orthogonality, surprise).
- **Expansion stage** pushes toward coherence (connection, consistency).

Quality lives in a band whose location shifts by genre. Too tame → closed system, coherent but boring (only produces history the wizard input already implies). Too wild → expansion fails to connect, or connects with visible strain.

**Control surface:**
- **Dev instrument:** a raw CLI float, MidJourney `--weird` style, for calibration. Used to find where each genre's good band sits.
- **Production interface:** coarse `WEIRD: low | medium | high`. The float is remapped per-genre behind the three labels — **[OPEN]** whether one range with genre-shifted thresholds or several discrete ranges. `medium` means "medium *for this genre*," not a universal number.
- **Never expose the float to the player.** Coarseness is a feature: (a) the genre remapping makes a raw number dishonest; (b) high-weird seeds are candidates for later revelation, and fine control invites inspecting surprises whose value depends on not being inspected. The dial is a statement of *appetite* and *consent to be ambushed*, not an audited instruction.

---

## The seven-function rubric — checklist, NOT scaffold

The Creative-Writing-101 categories (foundational wound, current power arrangement, hidden truth, trait-bound hooks, opening pressure, optional mythic layer, unresolved ledger) are **not** the generative scaffold. Structuring seed generation around them re-imports the conservatism bug: each is a slot pinned to a present-state function, which kills the orthogonal high-entropy material the pipeline exists to inject. A frontier model already has rich representations of these; instructing it to "generate a foundational wound" narrows rather than helps.

Deploy the rubric in two non-generative positions instead:

- **Coverage check (expansion stage).** After weaving, ask whether the web is missing a load-bearing structural element. Catches gaps without constraining origins. Editorial, not generative.
- **Weighting prior (selection stage).** A seed that can serve one of the seven functions is more load-bearing. At **low** weird, favor those. At **high** weird, relax the preference and admit seeds serving none of the seven — pure orthogonal strangeness, the late-secret candidates. The rubric is what the weird-dial modulates against; this gives the dial a concrete mechanical meaning beyond "more friction."

---

## Anchoring discipline

**Anchor at the leaf, not at the seed.** Seeds may be wild at origin (unimplied by wizard input). The expansion pass must terminate every *surviving* thread by connecting it, eventually, to something in the present configuration. A seed can start strange as long as the web it grows into touches a starting entity somewhere.

This is the synthesis of bounded-vs-open: history stays *about this story* (not free-floating worldbuilding the player never touches) while the long tail stays varied and surprising. Pin-at-the-seed = closed and boring; connect-at-the-leaf = open and grounded.

---

## Deferred-secret path & validation

High-weird seeds held back as latent secrets are the hard engineering.

A deferred seed must stay consistent not only with the *visible* woven web but with the *trajectory that web implies* — i.e., with future canon the system is only partially authoring. A secret that contradicts established canon by the time it surfaces is a bug, not a twist.

**Requirement:** the consistency validator checks deferred seeds against the implied forward trajectory, not just the current visible state. **[OPEN]** how far forward to project, and whether deferred seeds carry explicit reveal-preconditions (tags/events that gate surfacing) vs. remain free-floating for Skald to surface opportunistically.

This is the most iteration-prone component. Budget for it.

---

## Player-facing surface

- Player sees and shapes the **intentional core** in the wizard (stages R2–R3 output).
- Player sets the **strangeness dial** (low/medium/high).
- Player does **not** see the specific high-entropy seeds, so the expansion's results can ambush them later in play.
- **[OPEN]** hybrid degree: how much of the woven web is shown at setup vs. held. Default lean: show core + intentional relationships; hold the high-entropy long tail.

---

## Integration / reuse

- **Substrate:** reuse Orrery's `world_events`, `entity_tags`, relationship tables, vocabulary registries. Generation writes the same row shapes forward play does; tick stamps are pre-game (negative or pre-epoch — **[OPEN]** stamping scheme).
- **MEMNON:** retrieves generated history identically to play-generated. No special-casing; the storyteller cannot and need not distinguish setup-authored from play-accumulated history.
- **Dehydrated-entity pattern:** generate for first-class starting entities and their pairwise relationships only. Implied others (spouses, children, vanished parties) stay tags/stubs until narrative attention promotes them. Retrograde must NOT recursively generate full histories for implied entities — that reopens the "it never ends" hole. **[OPEN]** exact promotion trigger reuse from the live dehydration mechanism.
- **Reuse over rebuild:** stages R4–R6 are conceptually a short backward-Orrery pass with variance turned up. Prefer adapting existing resolver/event-writer machinery to building a parallel system.

---

## Failure modes to watch

- **Mediocre sticky backstory.** Generated canon that's interesting enough to honor but not enough to deserve it. Once in `world_events`, the storyteller treats it as real. Generate less than feels satisfying; let play fill the rest.
- **Over-determination.** Too much canonical past constrains the storyteller. Minimal seeds = maximal downstream freedom.
- **Contradiction surface.** Larger here than in the bounded version; scales with weird. The validator is the cost of the better creative output.
- **Tonal collision.** Friction must scale with genre register (sharp for grimdark, soft for cozy). Genre is a friction input alongside trait weighting.

---

## Open implementation decisions (consolidated)

1. Per-genre weird remapping: single range w/ shifted thresholds vs. discrete ranges.
2. Stage boundaries R2–R3 and R5–R6: merge or keep distinct.
3. Pre-game tick-stamping scheme **and `tick_chunk_id` FK resolution.** `world_events.tick_chunk_id` is `bigint NOT NULL REFERENCES narrative_chunks(id)` (verified at migration 023, live `save_01` schema). Pre-game writes are unreachable as currently specced. Three mutually-exclusive resolutions: (a) synthetic prologue `narrative_chunks` rows as wizard-time anchors; (b) make `tick_chunk_id` nullable when `source = 'retrograde'` (migration required, breaks existing index assumptions); (c) separate table with union view in MEMNON — contradicts the "no special-casing" claim directly. This is a schema constraint question, not a numbering question.
4. Deferred-secret reveal mechanism: explicit preconditions vs. opportunistic.
5. Forward-trajectory projection depth for validating deferred seeds.
6. How much of the woven web surfaces in the wizard vs. stays hidden.
7. Promotion-trigger reuse from the live dehydrated-entity pattern. *Partially addressed by Stub Maturation — Skald-as-narrator structured-output declarations cover the introduction surface; archaeology of the legacy live-dehydration mechanism is still needed for stubs already present.*
8. Generation budget caps (seeds generated vs. kept; entities covered). *Partially addressed for R4/R5 by the dry-run request budget and candidate-response validator; entity-coverage caps still need to be specified before R6 writes.*
9. Skald-as-narrator structured-output schema for `new_entities` declarations (kind, name, summary, optional registered tag/pair-tag hints).
10. Async job-queue infrastructure for runtime maturation — fire-and-forget contract, branch-parallel speculative execution, persistence on completion regardless of branch chosen.
11. Audit-pass design for catching Skald-as-narrator declarations missed in prose — pure rule-based (regex / NER + DB existence check), no LLM inference. Confidence threshold, false-positive tolerance. This is a belt-and-suspenders check only; it must not reintroduce the retired local-LLM entity detector pattern.
12. Engagement-signal taxonomy — what counts as "player chose this branch" / "player asked about this entity" / "player plans interaction" for triggering full maturation. Initially conservative; expand as signal patterns emerge.
13. `event_source_kind` enum migration — add `'retrograde'` variant. Current values: `'apex', 'resolver', 'narrator', 'bleed', 'authored'`. Using `'authored'` for retrograde rows would conflate wizard-time LLM generation with hand-authored content. Migration follows the pattern in migration 036 (`ALTER TYPE ... ADD VALUE IF NOT EXISTS`).
14. `CommitOrreryTick` bypass contract for wizard-time Retrograde. The forward Orrery invariant ("only the accepted-chunk commit path writes") is violated by wizard-time writes that happen outside any tick. Required specifications: explicit idempotency key (what prevents double-generation if wizard re-runs?), partial-failure rollback semantics (what happens if Stage R6 expansion fails after R4 wrote seeds?), and visibility boundary (when do partial retrograde writes become MEMNON-visible — atomically at completion, or progressively?).
15. Skald-as-weaver expansion contract for Stage R6 (paired with #9). Distinct invocation surface from Skald-as-narrator: different prompt, different output schema (seeds → `world_events` rows + tag/relationship state), potentially different model configuration. Specify the prompt template and output schema before R6 implementation begins.

---

*Frame to hold throughout: this runs Orrery's own logic backward with variance up. The fifty-chunk retaliation works because a small seed ripens through quiet ticks into weight. Retrograde does the same in reverse and compressed — small high-entropy seeds, an expansion pass that ripens them into a web, a result with the texture of lived history because it was made by the same kind of process that makes lived history forward.*

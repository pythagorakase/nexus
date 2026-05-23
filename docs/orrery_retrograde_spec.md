# Orrery Retrograde — Deep-History Generation Spec

**Status:** Design spec, deliberately compressed. Implementation decisions deferred to downstream agents; flagged inline as **[OPEN]**.
**One-line frame:** Deep history is Orrery run backward. Same substrate, same vocabulary, opposite temporal direction. Output is `world_events` rows retrieved by MEMNON identically to play-generated history. Fires at wizard-time (whole-world cold start, pre-game tick stamps) and at runtime (per-entity stub maturation, current tick stamps) — see Stub Maturation below.

---

## Purpose

Cure Orrery's cold-start problem: a new narrative begins with an empty `world_events` table and feels lived-in only after many forward ticks. Retrograde front-loads connected backstory at setup time, when latency doesn't matter and inference budget is cheap, so the world has texture from scene one.

Non-goal: DF-style exhaustive deep history. We generate *shallow-but-connected* history — enough to ground starting state and seed surprise, not a full legends corpus.

---

## Stub Maturation — Wizard-Time and Runtime

The pipeline below runs at two distinct lifecycle points with the same substrate and largely the same logic, but very different cost budgets. The wizard-time firing — cold-starting a whole world from wizard input — is the primary frame above. The runtime firing handles a separate but mechanically identical problem: Skald introduces a new entity in prose (a passing NPC, a named place, an off-screen faction) and that entity needs to become a connected, package-ready node before the player engages with it.

### Two-Tier Promotion

Entities enter the world in two stages, not one:

| Stage | Trigger | Cost | Output |
|---|---|---|---|
| **Stub creation** | Skald introduces a new entity in prose | Cheap — single declaration as part of Skald's structured response | Row in `characters` / `places` / `factions` + minimum viable tag set + the 1–2 sentence summary Skald wrote |
| **Maturation** | Engagement signal — player chooses a branch leading to the entity, asks about it, plans interaction with it | Expensive — full Stage 4–6 pass | Connected relationship graph, history seeds in `world_events`, package-ready tag density |

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
| Wizard-time (whole-world cold start) | Minutes per slot | Latency irrelevant; over-generate 5×+ at Stage 4 and prune to 1×; slow frontier-model expansion at Stage 6 is fine |
| Runtime (single-entity maturation) | ~5–30 seconds in the async window | Tighter over-generation (~2×); may need faster model for Stage 6; async job queue non-negotiable |

Same pipeline, different knob settings. The pipeline isn't bifurcated — only the budget and concurrency model differ between firing contexts.

### Minimum Viable Tag Set

When Stage 4 (seed generation) introduces *implied* entities (the spouse of a stubbed NPC, the vanished sister implied by a foundational wound), those implied entities receive a **minimum viable tag set**: enough for the seed to be mechanically meaningful (e.g., `vanished`, `kin(→ Alex)`, a faction tag if implied) but no relationship graph of their own. They do not recursively trigger full maturation. Promotion to full maturation happens only through the runtime trigger (engagement signal), via the same mechanism that handles Skald's mid-narrative stub introductions.

This is what keeps Retrograde non-recursive: implied entities accrete just enough mechanical weight to matter, and pay for full realization only if and when narrative attention lands on them.

---

## Pipeline

Six stages. Each consumes the prior; **[OPEN]** boundaries may merge during implementation.

1. **Vocabulary table.** Enumerate the seed-eligible primitives: event types, tags, relationship types, place affordances already in the Orrery registries. Retrograde generates *only* in existing vocabulary so output is substrate-legal by construction. New vocabulary is out of scope for a generation run.

2. **Stub generator.** From wizard choices (setting, genre, starting characters, selected traits), emit entity stubs and a sparse relationship graph — the *intentional core*. This is deterministic-ish scaffolding, low entropy, fully implied by wizard input.

3. **Graph builder.** Expand the sparse core into a candidate relationship/event graph with open attachment points (dangling edges where history could connect).

4. **Seed generation (high-entropy, high-friction).** Over-generate candidate seeds — events, grudges, debts, secrets, vanished parties — that are *directionally connected* to the graph but NOT implied by it. This is where surprise is injected. Generate more than will be kept.

5. **Semi-constrained selection.** Filter/weight the candidate seeds by wizard choices (especially character traits) and the weird setting (below). Select a subset. **Discarded seeds cost only inference.**

6. **Expansion pass (Skald).** Weave surviving seeds into a coherent web. Skald may **reject** seeds that won't cohere without contortion, not merely connect them. Every surviving thread must terminate by connecting to present canon (see Anchoring). Output: `world_events` rows + tag/relationship state, consistency-validated.

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

- Player sees and shapes the **intentional core** in the wizard (stages 2–3 output).
- Player sets the **strangeness dial** (low/medium/high).
- Player does **not** see the specific high-entropy seeds, so the expansion's results can ambush them later in play.
- **[OPEN]** hybrid degree: how much of the woven web is shown at setup vs. held. Default lean: show core + intentional relationships; hold the high-entropy long tail.

---

## Integration / reuse

- **Substrate:** reuse Orrery's `world_events`, `entity_tags`, relationship tables, vocabulary registries. Generation writes the same row shapes forward play does; tick stamps are pre-game (negative or pre-epoch — **[OPEN]** stamping scheme).
- **MEMNON:** retrieves generated history identically to play-generated. No special-casing; the storyteller cannot and need not distinguish setup-authored from play-accumulated history.
- **Dehydrated-entity pattern:** generate for first-class starting entities and their pairwise relationships only. Implied others (spouses, children, vanished parties) stay tags/stubs until narrative attention promotes them. Retrograde must NOT recursively generate full histories for implied entities — that reopens the "it never ends" hole. **[OPEN]** exact promotion trigger reuse from the live dehydration mechanism.
- **Reuse over rebuild:** stages 4–6 are conceptually a short backward-Orrery pass with variance turned up. Prefer adapting existing resolver/event-writer machinery to building a parallel system.

---

## Failure modes to watch

- **Mediocre sticky backstory.** Generated canon that's interesting enough to honor but not enough to deserve it. Once in `world_events`, the storyteller treats it as real. Generate less than feels satisfying; let play fill the rest.
- **Over-determination.** Too much canonical past constrains the storyteller. Minimal seeds = maximal downstream freedom.
- **Contradiction surface.** Larger here than in the bounded version; scales with weird. The validator is the cost of the better creative output.
- **Tonal collision.** Friction must scale with genre register (sharp for grimdark, soft for cozy). Genre is a friction input alongside trait weighting.

---

## Open implementation decisions (consolidated)

1. Per-genre weird remapping: single range w/ shifted thresholds vs. discrete ranges.
2. Stage boundaries 2–3 and 5–6: merge or keep distinct.
3. Pre-game tick-stamping scheme.
4. Deferred-secret reveal mechanism: explicit preconditions vs. opportunistic.
5. Forward-trajectory projection depth for validating deferred seeds.
6. How much of the woven web surfaces in the wizard vs. stays hidden.
7. Promotion-trigger reuse from the live dehydrated-entity pattern. *Partially addressed by Stub Maturation — Skald structured-output declarations cover the introduction surface; archaeology of the legacy live-dehydration mechanism is still needed for stubs already present.*
8. Generation budget caps (seeds generated vs. kept; entities covered).
9. Skald structured-output schema for `new_entities` declarations (kind, name, summary, optional MV-tag hints).
10. Async job-queue infrastructure for runtime maturation — fire-and-forget contract, branch-parallel speculative execution, persistence on completion regardless of branch chosen.
11. Audit-pass design for catching Skald declarations missed in prose — pure rule-based (regex / NER + DB existence check), no LLM inference. Confidence threshold, false-positive tolerance.
12. Engagement-signal taxonomy — what counts as "player chose this branch" / "player asked about this entity" / "player plans interaction" for triggering full maturation. Initially conservative; expand as signal patterns emerge.

---

*Frame to hold throughout: this runs Orrery's own logic backward with variance up. The fifty-chunk retaliation works because a small seed ripens through quiet ticks into weight. Retrograde does the same in reverse and compressed — small high-entropy seeds, an expansion pass that ripens them into a web, a result with the texture of lived history because it was made by the same kind of process that makes lived history forward.*

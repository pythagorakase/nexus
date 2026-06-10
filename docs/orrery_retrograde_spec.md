# Orrery Retrograde — Deep-History Generation Spec

**Status:** Design spec, deliberately compressed. Phase A0 has a non-mutating dry-run packet surface, Phase A1 adds a non-mutating R4/R5 seed-generation request contract, R6 can make a live Skald-as-weaver expansion call, and the first persistence surface can now dry-run or apply row-shaped expansion output into canonical Orrery tables when blockers are clear. As of M4 the whole pipeline fires automatically inside the new-story wizard's ready -> narrative transition (`nexus/agents/orrery/retrograde_orchestrator.py`, composed by `nexus.api.new_story_flow.perform_transition_with_retrograde`); the stage CLI verbs remain as calibration surfaces over the same core. Remaining implementation decisions are flagged inline as **[OPEN]**.
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

*Status (M8, Phase B-Lite):* the fire-and-forget queue and committed-branch maturation shipped — see decisions 9/10/12 below and `nexus/agents/orrery/retrograde_maturation.py`. Branch-parallel speculative execution is **post-1.0**; v1 matures declared entities on the committed branch only, which preserves the queue contract speculation will later ride on.

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

- **R1. Vocabulary table.** Enumerate the seed-eligible primitives: event types, tags, relationship types, and semantic place classes already in the Orrery registries. Retrograde generates *only* in existing vocabulary so output is substrate-legal by construction. New vocabulary is out of scope for a generation run. The first-pass enumerator exists at `nexus/agents/orrery/retrograde_vocabulary.py`; pass a target slot `dbname` once migrations are applied so it folds live `tag_category_registry` / `tags` rows into the template-derived primitive set. The enumerator now also classifies registered tag categories as `stable_seed`, `event_anchored`, or `prompt_visible_only`: stable categories may appear as present-state seed outcomes, event-anchored categories require an explicit causing/recent-refresh event, and prompt-visible-only categories may guide prose but not mechanical seed writes. **The seed-eligible vs prompt-visible split is settled (issue #300, M4):** every category in the live registry is classified explicitly in `retrograde_vocabulary.py` — stable identity/role/affordance categories (incl. `bodyform`, `role`, `profession_lite`, `place_affordance`, `ideology_axis`, `resource_class`, `legitimacy_status`, `operational_secrecy`, `power_posture`, `history_class`) are `stable_seed`; pressure/relational categories needing a causing event (`state`, `place_threat`, `power_status`, `agenda`, `hidden_agenda_class`, `relationship_risk`) are `event_anchored`; all `orrery_*` forward-runtime bookkeeping categories are pinned `prompt_visible_only` (the tick loop owns those writes). Unclassified future categories default to `prompt_visible_only` — new vocabulary ships locked until a deliberate edit promotes it.

  Phase A0/A1 packet assembly exists at `nexus/agents/orrery/retrograde_packet.py` and is exposed as `nexus retrograde-packet --slot N [--weird low|medium|high] [--weird-raw FLOAT] [--output packet.json]`. It reads wizard cache + vocabulary + configured weird bands, writes no canonical rows, and produces candidate prompt material plus a seed-generation request for Skald-as-weaver.

  The first Skald-facing seed surface exists at `nexus/agents/orrery/retrograde_seed_candidates.py`: it renders the seed-generation prompt, exposes a Pydantic JSON schema for candidate responses, validates returned mechanics against budgets and the seed-eligible vocabulary, and can make the live Skald call. This is still non-mutating. The CLI surface is `nexus retrograde-seed-candidates --slot N ...` when a wizard cache is active, or `nexus retrograde-seed-candidates --packet packet.json --output seeds.json` for a saved/reviewable packet. `--max-tokens` can override the normal wizard cap for calibration/demo runs because seed candidate responses are larger than ordinary wizard chat turns. The prompt includes a compact response contract while the full schema remains in the packet and the Pydantic AI `output_type`. A valid response can propose candidate-local events, stable single-entity tags, event-anchored tags with explicit supporting events, pair tags, and relationship hints. The validator rejects prompt-visible-only tag writes, unknown primitives, invalid pair-tag kind constraints, duplicate/unknown candidate ids, and selections that exceed the request target.

  The first R6 expansion surface exists at `nexus/agents/orrery/retrograde_expansion.py`: it consumes a packet plus a seed-candidate response, renders the Skald-as-weaver expansion prompt, exposes a Pydantic JSON schema for row-shaped event/tag/relationship plans, validates selected-seed accounting and vocabulary legality, and can make the live Skald call. The CLI surface is `nexus retrograde-expand-seeds --packet packet.json --seed-candidates seeds.json --output expansion.json`. This remains non-mutating: outputs carry future `world_events` / `entity_tags` / `entity_pair_tags` / relationship-table plans, not database ids or writes.

  The first persistence surface exists at `nexus/agents/orrery/retrograde_persistence.py`: `nexus retrograde-apply-expansion --slot N --packet packet.json --seed-candidates seeds.json --expansion expansion.json [--execute] [--create-stubs] [--output persistence.json]`. Default mode is a read-only dry run. Execute mode writes a synthetic prologue `narrative_chunks` anchor, `world_events` stamped `source = 'retrograde'`, single-entity tags, pair tags stamped `source_kind = 'retrograde'`, and character-character relationship rows. It refuses to guess prompt-local references by default: unresolved or ambiguous entity refs remain execute blockers. `--create-stubs` is an explicit opt-in that lets exact missing refs stage minimum viable `characters`, `places`, or `factions` rows; dry-run reports the would-create rows, and execute inserts the stubs before canonical Retrograde rows once every other blocker is clear. Ambiguous existing refs still block. `relationship_plan` currently accepts only character-character rows because `character_relationships` carries the generic relationship vocabulary; faction/place pressure should be expressed through events or pair tags until `faction_relationships` / `faction_character_relationships` get their own explicit mapping policy.

- **R2. Stub generator.** From wizard choices (setting, genre, starting characters, selected traits), emit entity stubs and a sparse relationship graph — the *intentional core*. This is deterministic-ish scaffolding, low entropy, fully implied by wizard input.

- **R3. Graph builder.** Expand the sparse core into a candidate relationship/event graph with open attachment points (dangling edges where history could connect).

- **R4. Seed generation (high-entropy, high-friction).** Over-generate candidate seeds — events, grudges, debts, secrets, vanished parties — that are *directionally connected* to the graph but NOT implied by it. This is where surprise is injected. Generate more than will be kept. The current implementation renders a Skald prompt from the dry-run packet, makes the Skald call when invoked via `nexus retrograde-seed-candidates`, and requires JSON matching the seed-candidate response schema; no generated seed is persisted at this stage.

- **R5. Semi-constrained selection.** Filter/weight the candidate seeds by wizard choices (especially character traits) and the weird setting (below). Select a subset. **Discarded seeds cost only inference.** The current response schema lets Skald return `selected_seed_ids` / `rejected_seed_ids`; validation enforces that selected ids exist and stay within the `select_target` budget.

- **R6. Expansion pass (Skald-as-weaver).** Weave surviving seeds into a coherent web. The expansion model may **reject** seeds that won't cohere without contortion, not merely connect them. Every surviving thread must terminate by connecting to present canon (see Anchoring). Current implementation output is an expansion *plan*: future `world_events` rows + tag/relationship state deltas, consistency-validated, with no canonical writes until commit blockers resolve. *(The label "Skald-as-weaver" distinguishes this invocation from the runtime narrative agent — see Stub Maturation. Whether the two invocations literally use the same model is an implementation choice; the prompts and output schemas are not interchangeable.)*

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
- Hybrid degree — **resolved (decision 6, M4):** the transition API response (`TransitionResponse.retrograde.surface`) carries only the **visible** layer — the woven entity roster (first-class starting entities the expansion touched plus any minimum-viable stubs it introduced) and the intentional relationship edges (subject, object, relationship type) — plus `hidden_counts` (events, tags, pair tags, woven/deferred/rejected seeds) as bare numbers. Event prose, tag bestowals, and deferred seeds never leave the database via the wizard surface. The U-track renders the visible layer; the counts let the UI say "history exists" without disclosing it.

---

## Integration / reuse

- **Substrate:** reuse Orrery's `world_events`, `entity_tags`, relationship tables, vocabulary registries. Wizard-time generated history now anchors to a synthetic finalized prologue `narrative_chunks` row rather than weakening `world_events.tick_chunk_id` or special-casing MEMNON. `world_events` rows use `source = 'retrograde'`; generated `entity_tags` / `entity_pair_tags` rows use `source_kind = 'retrograde'`.
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
3. Pre-game `tick_chunk_id` FK resolution — **resolved for the first writer.** `world_events.tick_chunk_id` remains `bigint NOT NULL REFERENCES narrative_chunks(id)`. Retrograde uses a synthetic finalized prologue `narrative_chunks` row, with matching `chunk_metadata`, as the wizard-time anchor. This preserves existing indexes and MEMNON retrieval without nullable tick ids or a parallel history table.
4. Deferred-secret reveal mechanism: explicit preconditions vs. opportunistic.
5. Forward-trajectory projection depth for validating deferred seeds.
6. How much of the woven web surfaces in the wizard vs. stays hidden — **resolved (M4).** The default lean shipped: show core + intentional relationships, hold the high-entropy long tail. `TransitionResponse.retrograde.surface.visible` lists woven entities (name, kind, status) and relationship edges; `surface.hidden_counts` exposes only counts of events/tags/pair tags/deferred seeds. The hidden material reaches the player exclusively through play (MEMNON retrieval and future reveals), never through the setup surface. See Player-facing surface above.
7. Promotion-trigger reuse from the live dehydrated-entity pattern. *Partially addressed by Stub Maturation — Skald-as-narrator structured-output declarations cover the introduction surface; archaeology of the legacy live-dehydration mechanism is still needed for stubs already present.*
8. Generation budget caps (seeds generated vs. kept; entities covered) — **resolved for wizard-time R6 writes (M4).** Seed counts stay on the existing per-weird-level `SEED_BUDGETS` (R4/R5). Entity coverage: woven history (events, relationships, tags) targets the **first-class starting set** — the wizard-cache core (protagonist, starting place/zone/layer, named seed NPCs) plus every canonical row created in the same transition transaction, which includes trait-compiler stubs, all resolvable by name at persistence time. Entities the expansion implies beyond that set become **minimum-viable stubs only** (dehydrated-entity pattern; matured later on engagement signal), capped by `[orrery.retrograde.wizard].max_new_entity_stubs` (default 6). The cap rides the seed request budget into the R4 and R6 prompts, is enforced at R6 response validation (ModelRetry repair), and is enforced again as a hard gate at the persistence dry-run (`entity_stub_budget_exceeded` blocker -> transaction rollback). Because stub refs become canonical `name` values (`characters.name`/`places.name` are `varchar(50)`), every R4/R6 entity ref is bounded by `ENTITY_REF_MAX_LENGTH` (50, `retrograde_vocabulary.py`) at the Pydantic response boundary — refs are proper names, never descriptions; violations fail loudly with a ModelRetry repair shot instead of mid-transaction truncation errors. Runtime-maturation budgets remain open with decision 10.
9. Skald-as-narrator structured-output schema for `new_entities` declarations — **resolved (M8, 2026-06-10).** `NewEntityDeclaration` in `nexus/agents/logon/apex_schema.py`: kind (`character`/`place`/`faction`), name, one-line summary, optional registered `tag_hints` (single-entity) and `pair_tag_hints` (tag + other-endpoint name + declared-entity role). The field rides `StorytellerResponseMinimal/Standard/Extended`, through the incubator (`incubator.new_entities`, migration 062), and is processed at commit time by `enqueue_declared_entity_maturations` (`nexus/agents/orrery/retrograde_maturation.py`): hints are validated against the live `tags` / `pair_tags` registries — unregistered, deprecated, or kind-incompatible names fail the commit loudly — stub rows are created for declared entities absent from the database (Skald-curated summary becomes the stub summary; tag hints become the minimum viable tag set via the standard bestowal path), and pair-tag hints feed the maturation packet as prompt material rather than being written directly. The declaration duty is documented sparingly in `prompts/storyteller_core.md` (declare only entities likely to recur).
10. Async job-queue infrastructure for runtime maturation — **resolved for the fire-and-forget core (M8, 2026-06-10).** Durable queue `orrery_maturation_jobs` (migration 062) mirrors the narration outbox's lease/retry discipline: enqueued inside the chunk-commit transaction (atomic with the chunk — the outbox boundary), drained by the post-commit Orrery worker (`drain_maturation_jobs_sync`, wired into `process_orrery_outbox_sync`). Per job the worker composes existing pipeline functions: scoped single-entity packet (`build_runtime_maturation_packet`, reusing the wizard request builder with tighter budgets) → R4/R5 seed generation → R6 expansion → `build_retrograde_persistence_plan` execute → summary-chunk embedding (M3 machinery). Event refs are namespaced per job so per-slot `payload.retrograde_event_ref` idempotency keys never collide; the unique index on `entity_id` plus an already-connected world-events guard make maturation idempotent per entity (a matured entity never re-matures). Failed jobs record `last_error` and requeue with a delay until the attempt cap, then stay `failed` and visible; a job whose manifest already records persisted rows resumes at the embedding step instead of regenerating history. Knobs in `nexus.toml [orrery.retrograde.maturation]` (enabled, budget, drain/attempt caps, seed budgets, model ref). **Post-1.0:** branch-parallel speculative execution (maturing A/B/C options during the turn-composition pause, persistence regardless of branch chosen) — v1 matures on the committed branch only.
11. Audit-pass design for catching Skald-as-narrator declarations missed in prose — pure rule-based (regex / NER + DB existence check), no LLM inference. Confidence threshold, false-positive tolerance. This is a belt-and-suspenders check only; it must not reintroduce the retired local-LLM entity detector pattern. **Post-1.0:** deliberately not built in M8; the declaration path is the only stub-introduction surface for v1.
12. Engagement-signal taxonomy — **resolved conservatively for v1 (M8, 2026-06-10).** The initial signal set is exactly one signal: the entity was declared via `new_entities` AND its name appears in the committed chunk's text — declaration + commit IS the signal. Declared entities absent from the committed prose get a stub but no job. Player-asks / player-plans detection is **explicitly deferred**; expand the taxonomy as signal patterns emerge from play.
13. Retrograde source-kind migrations — **resolved for events and tag rows.** Migration 060 adds `'retrograde'` to both `event_source_kind` and `entity_tag_source_kind`, keeping wizard-time generated history distinct from hand-authored content, generic offline backfills, and runtime Skald inline edits.
14. `CommitOrreryTick` bypass contract for wizard-time Retrograde — **resolved for the MEMNON visibility boundary (M3, 2026-06-10).** Generated history becomes retrievable at persistence time through per-event summary chunks: execute mode writes one finalized `narrative_chunks` row per persisted Retrograde world event (raw_text = the Skald-woven event summary; provenance markers `orrery:retrograde_event_summary` plus `orrery:retrograde_event:<event_ref>` in `authorial_directives`; `chunk_metadata` in the season-0/episode-0 prologue block; `world_events.payload.retrograde_summary_chunk_id` cross-link), then the standard chunk embedding lifecycle embeds them immediately after commit — embedded == ironman, same as play chunks. Surface discipline mirrors the off-screen narration boundary: Retrograde chunks are excluded from MEMNON's recent-chunks/warm-slice surface (generated history is memory, not recent narration) but participate fully in vector and text search, which is what fulfills "MEMNON retrieves generated history identically to play-generated" — aged play history is reached the same way. The synthetic prologue anchor chunk stays an unembedded FK anchor (decision 3 unchanged). Config: `[orrery.retrograde.retrieval]` in `nexus.toml` (`summary_chunks`, `embed_after_apply`); backfill and inspection via `nexus retrograde-embed-history --slot N [--execute]`. **The wizard-time product boundary is now also resolved (M4):** Retrograde persistence executes *inside the same transaction* as the wizard transition writes (`perform_transition`'s `in_transaction` hook). The non-mutating frontier stages (packet, R4/R5, R6) run first; only then does the world commit together with its history. If expansion succeeds but persistence is blocked, `RetrogradePersistenceBlockedError` aborts the transaction: no protagonist, no places, no history rows land, the wizard cache survives, the slot stays in wizard-ready, and the API surfaces the blocker list as a loud HTTP error. Retrying the transition re-runs the full pipeline from `perform_transition`'s clean-slate preamble — a history-less world can never silently enter narrative mode. Post-commit embedding failure is the one partial state: history is canonical but unembedded; the error names the remediation (`nexus retrograde-embed-history --slot N --execute`) and pending chunks stay retryable because `embedding_generated_at` remains NULL. Wizard-time progress states (packet -> seed_candidates -> expansion -> persistence -> embedding -> done/failed) are exposed at `GET /api/story/new/retrograde/status?slot=N`.
15. Skald-as-weaver expansion contract for Stage R6 (paired with #9). *Partially addressed by `retrograde_expansion.py` and `retrograde_persistence.py`: distinct prompt, output schema, live-call CLI, selected-seed accounting, non-mutating row-shaped plans, prologue anchoring, and event/tag/pair-tag persistence planning exist. Character-character relationship writing and wizard integration (the M4 orchestrator) are done; remaining work is faction/place relationship-table mapping policy and runtime maturation jobs.*

---

*Frame to hold throughout: this runs Orrery's own logic backward with variance up. The fifty-chunk retaliation works because a small seed ripens through quiet ticks into weight. Retrograde does the same in reverse and compressed — small high-entropy seeds, an expansion pass that ripens them into a web, a result with the texture of lived history because it was made by the same kind of process that makes lived history forward.*

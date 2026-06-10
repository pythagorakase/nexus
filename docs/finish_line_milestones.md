# NEXUS Backend v1.0 - Finish Line

*Snapshot 2026-06-09, reconstructed from git history, PR #368, issues #300/#282/#369, the Retrograde spec's decision ledger, and live save-slot state. Sizes: S = about a day, M = days, L = a week or more.*

## The MVP in One Paragraph

A player starts a new story through the wizard and the backend does the rest: Retrograde cold-starts a connected world history before turn 1; every turn flows input -> MEMNON retrieval (raw chunk text straight into the IR engine - no LLM query rewriting) -> deterministic context assembly -> Skald generation -> incubator -> committed chunk with embeddings; and the Orrery resolves off-screen NPC behavior each tick so the world demonstrably lives while nobody is watching. All slot-aware, on real API calls, with no local LLMs anywhere in the loop, gated by a green suite and one scripted golden-path run. The UI is a separate project; v1.0 is the engine.

## Where We Are

| Subsystem | State |
|---|---|
| Turn-cycle orchestration, MEMNON retrieval, LOGON/Skald | Done, production-quality; fully deterministic (LORE's local-LLM layer was fired after the retrieval bakeoff - raw chunk text beat LLM-generated queries) |
| Wizard + trait compiler | Wizard done; 4 of 8 traits compile (Resources, Fame, Status, Contacts) - Domain, Patron, Dependents, Obligations still prose-only |
| Schema, vocabulary lockdown, package library | Done (migrations 001-060, #293, ~60 packages) |
| Orrery engine | Built; Commit/adjudication already live-proven on slot 5, but Resolve/Bleed are flag-gated off and Promote->Narrate->Bleed has never fired (0 promotions at current thresholds) |
| Retrograde Phase A (R1-R6 + persistence) | Built and live-validated on slot 5. PR #368 is the landing PR; its final review hardening enforces tag/entity-kind compatibility before canonical tag writes. |
| Retrograde retrieval | **Gap**: generated history lands in `world_events`, which MEMNON's vector search never sees; prologue anchor is an unembedded stub |
| Retrograde Phase B (runtime stub maturation) | Designed (spec decisions 9-12), not built |
| Database fleet | Drifted: template=046, slots range 040-060; fresh slots would clone a stale schema |

## Milestones

**M1 - Land Retrograde Persistence (PR #368)** - S
Merge and prune the landing PR. The work is already live-validated on slot 5; this is consolidation, not unblocking.

**M2 - Bring the Database Fleet to 060** - S
`scripts/migrate.py --all --template` so NEXUS_template and every slot carry migrations 047-060 (unlock slot 1, migrate, re-lock). Hard prerequisite for cold-starting fresh slots: today a new slot clones template@046 and would be missing the Retrograde enums entirely.

**M3 - Make Retrograde History Retrievable** - M
The spec promises MEMNON retrieves generated history identically to play-generated; today it can't. Decide and build the surface: embed real prologue prose chunks, embed per-event summaries as chunks, or accept structured-only visibility for v1.0 (and say so). This is the unstated implementation half of spec decision 14.

**M4 - Wire Retrograde Into the New-Story Wizard** - M
The pipeline exists only as CLI verbs (zero references in `nexus/api/`). New-story flow should run R1-R6 + persistence automatically at slot creation. Requires settling decision 14's product boundary (when generated history becomes visible; behavior when expansion succeeds but persistence is blocked), decision 8's entity-coverage caps, and the seed-eligible vs prompt-visible category split.

**M5 - Finish the Trait Compiler** - M
Implement the four remaining compilers - Domain, Patron, Dependents, Obligations - following the #295 pattern (affective traits -> relationship row primary; pair-tags only where packages gate). Patron and Dependents create stub entities, which is exactly the input Retrograde Phase A matures at wizard time - so this lands best before M4, letting cold-start history cover compiled relationships.

**M6 - Turn On the Orrery, End to End** - M
Flip `orrery.enabled = true` and make the full cycle actually fire on slot 5 with real API calls: Resolve proposals -> Skald adjudication -> CommitOrreryTick -> worker Promote -> Narrate -> Bleed. The flag flip is trivial; the work is promotion-threshold tuning (104/106 resolutions currently skip at defaults - Promote has never promoted) and the first live Narrate/Bleed exercise, plus a decision on the orphaned `offscreen_narrations` embedding path (wire it or explicitly defer). Ship default-on.

**M7 - Retrograde Phase B-Lite: Runtime Stub Maturation** - L
When Skald declares `new_entities` mid-narrative, mature them. MVP cut: the structured-output declaration schema (decision 9), a conservative engagement-signal set (decision 12), and the fire-and-forget job contract with persistence-on-completion (the core of decision 10) - running only on the *committed* branch. Deferred past 1.0: A/B/C speculative branch maturation (decision 10's tail) and the rule-based prose-audit pass (decision 11).

**M8 - Golden-Path Release Gate** - M
One scripted end-to-end run, real API calls, fresh slot: wizard -> Retrograde cold start -> ~10 live turns with Orrery on -> assert chunk persistence, embedding lifecycle, retrieval of retrograde-sourced history (per M3's chosen surface), and at least one off-screen event bleeding into prose. Codified as a repeatable `NEXUS_RUN_LIVE_LLM=1` test. Passing this run *is* the MVP.

**M9 - Release Hygiene** - M
Close #369 (side-effect-free API imports). Reconcile nexus.toml/settings.json drift. Document intentional flag states (`structured_data_enabled = false` stays off). Rewrite README to match reality. Update stale issue/spec checklists (#300 prerequisites). Tag v1.0.0.

## Dependency Sketch

M1, M2, M5, M6 can all start today, in parallel. M3 and M7 follow M1; M4 follows M1+M2 (and wants M5 first). M8 gates on M3-M7. M9 closes.

## Scope Calls I Made - Correct Me Here

1. **Phase B is in, but cut down.** Mid-story entities with no history break the lived-in-world promise, so runtime maturation is MVP; branch-parallel speculation and the NER audit pass are optimizations the spec itself calls expandable/belt-and-suspenders, so they wait.
2. **Orrery default-on is part of v1.0.** "Backend ready" means the world is alive, not that the simulator compiles. That includes making Promote actually promote.
3. **Retrograde retrievability is in.** M3 exists even though no issue tracks it: the spec's core promise ("texture of lived history") depends on it, and the golden path can't honestly pass without it.
4. **Deferred-secret mechanics ship opportunistic.** Decisions 4-5 resolve to "no explicit reveal-preconditions; Skald surfaces secrets when fitting" - the simplest thing that preserves the feature.
5. **Out of scope:** UI rebuild (#341 track), package self-awareness (#282), gaia/psyche/nemesis agents, re-enabling structured-data search.

# NEXUS Backend v1.0 - Finish Line

*Snapshot 2026-06-09, reconstructed from git history, PR #368, issues #300/#282/#369, the Retrograde spec's decision ledger, and live save-slot state. Revised 2026-06-10: full trait-compiler scope, UI track added from the Iris design handoff. Sizes: S = about a day, M = days, L = a week or more.*

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
| UI (Iris design system) | Handoff received 2026-06-10, vendored at `design_handoff/`: Veil theme canonical, full kit at `ui_kits/nexus_iris/`; NexusLayout demolition merged (#341, 74fc63df) - canvas is clear |

## Milestones

**M1 - Land Retrograde Persistence (PR #368)** - S - DONE 2026-06-10
Merged as 6b5e0b4c (squash, via Codex cleanup); branch pruned.

**M2 - Bring the Database Fleet to 060** - S - DONE 2026-06-10
All six databases (NEXUS_template + save_01..05) now at migration 060; slot 1 unlocked, migrated (20 applied), re-locked. 66 migrations applied total, 0 failures.

**M3 - Make Retrograde History Retrievable** - M - DONE 2026-06-10 (PR #373, 6ac8de74)
Shipped as per-event embedded summary chunks (excluded from the warm slice, fully searchable; live top-hit 0.95 on save_05). The spec promises MEMNON retrieves generated history identically to play-generated; today it can't. Decide and build the surface: embed real prologue prose chunks, embed per-event summaries as chunks, or accept structured-only visibility for v1.0 (and say so). This is the unstated implementation half of spec decision 14.

**M4 - Wire Retrograde Into the New-Story Wizard** - M - DONE 2026-06-10 (PR #378, 27dfd911; decisions 6/8/14 settled, two green destructive e2e runs on slot 5, varchar ref-overflow fixed at the Pydantic boundary)
The pipeline exists only as CLI verbs (zero references in `nexus/api/`). New-story flow should run R1-R6 + persistence automatically at slot creation. Requires settling decision 14's product boundary (when generated history becomes visible; behavior when expansion succeeds but persistence is blocked), decision 8's entity-coverage caps, and the seed-eligible vs prompt-visible category split.

**M5 - Finish the Trait Compiler** - M - DONE 2026-06-10 (PR #372, fae2ebd5)
Every trait except the wildcard compiles to mechanical state - no prose-only remainders. Implement the four remaining compilers (Domain, Patron, Dependents, Obligations) following the #295 pattern (affective traits -> relationship row primary; pair-tags only where packages gate), with latitude to expand or tune the trait vocabulary where the registry lacks what a compiler needs - design-time registry additions via migration stay compatible with the #293 runtime lockdown. Patron and Dependents create stub entities, which is exactly the input Retrograde Phase A matures at wizard time - so this lands best before M4, letting cold-start history cover compiled relationships.

**M6 - Turn On the Orrery, End to End** - M - DONE 2026-06-10 (PR #371, c6ab59e2)
Live-proven on slot 2: 9 promotions, 9/9 real narrations, 3 Bleed candidates woven into prose; thresholds recalibrated (priority 30.0, magnitude 0.35) with corpus evidence; offscreen-narrations embedding explicitly deferred. Original scope: flip `orrery.enabled = true` and make the full cycle actually fire on slot 5 with real API calls: Resolve proposals -> Skald adjudication -> CommitOrreryTick -> worker Promote -> Narrate -> Bleed. The flag flip is trivial; the work is promotion-threshold tuning (104/106 resolutions currently skip at defaults - Promote has never promoted) and the first live Narrate/Bleed exercise, plus a decision on the orphaned `offscreen_narrations` embedding path (wire it or explicitly defer). Ship default-on.

**M7 - Package Self-Awareness (#282)** - M - DONE 2026-06-10 (PR #375, 7552b84d; zero vocabulary additions, fame-in-entry-gates structurally banned, 17 branch shifts on tagged profiles / 0 diffs on untagged corpus)
Branch selection reads the acting entity's own properties (fame, resources, disposition) per the locked three-stage design: entry-gating / branch-selection / outcome. Deliberately sequenced after M6: the first live Promote/Narrate/Bleed runs establish a branch-selection baseline, so threshold tuning and self-awareness don't confound each other. Runs parallel with M8.

**M8 - Retrograde Phase B-Lite: Runtime Stub Maturation** - L - DONE 2026-06-10 (PR #379; live-proven on slot 2: Skald-declared entity matured with 4 events in 171s, retrievable via MEMNON; maturation drain detached from the play loop, +3.2min -> +106ms)
When Skald declares `new_entities` mid-narrative, mature them. MVP cut: the structured-output declaration schema (decision 9), a conservative engagement-signal set (decision 12), and the fire-and-forget job contract with persistence-on-completion (the core of decision 10) - running only on the *committed* branch. Deferred past 1.0: A/B/C speculative branch maturation (decision 10's tail) and the rule-based prose-audit pass (decision 11).

**M8.5 - Wizard Multi-Model Support** - M (added 2026-06-10 per user)
The wizard and its Retrograde calls should route through the same pluggable provider layer as the main narrative engine: gpt-5.5 stays the default testing workhorse, Anthropic models become selectable (config + settings UI dropdown), structured-output paths provider-agnostic. No literal model IDs in runtime code.

**M9 - Golden-Path Release Gate** - M
One scripted end-to-end run, real API calls, fresh slot: wizard -> Retrograde cold start -> ~10 live turns with Orrery on -> assert chunk persistence, embedding lifecycle, retrieval of retrograde-sourced history (per M3's chosen surface), and at least one off-screen event bleeding into prose. Codified as a repeatable `NEXUS_RUN_LIVE_LLM=1` test. Passing this run *is* the MVP.

**M10 - Release Hygiene** - M - DONE except the tag, 2026-06-10 (PR #380, ac3734e6; #369 closed, settings.json retired, fresh-slot migration stamping fixed, README rewritten; v1.0.0 tag fires after M9 passes)
Close #369 (side-effect-free API imports). Reconcile nexus.toml/settings.json drift. Document intentional flag states (`structured_data_enabled = false` stays off). Rewrite README to match reality. Update stale issue/spec checklists (#300 prerequisites). Tag v1.0.0.

## UI Track (Parallel Lane)

Backend milestones take priority on contention; v1.0 means engine + new face. Design source: `design_handoff/` (NEXUS IRIS design system, Veil theme canonical). Read `design_handoff/nexus-iris-design-system/project/README.md` and the chat transcripts before implementing - the intent lives in the chats.

**U1 - Vendor the Design System** - S - DONE 2026-06-10 (PR #370, efd72c22)
Tokens, keeper fonts, and theme CSS into `ui/` (`colors_and_type.css` -> theme layer; Veil at `:root`, Gilded/Vector as override classes). Licensed assets follow the established per-set convention with TOS PDFs at `licenses/`.

**U2 - Veil Splash per the Chosen Hero** - M - DONE 2026-06-10 (PR #370; Frame composition, kit-locked values)
Port the kit's splash composition (locked values hard-coded in `ui_kits/nexus_iris/splash.jsx`) into the React/TS `VeilSplash`. Wizard preserved as-is; Gilded and Vector splashes untouched.

**U3 - NexusLayout Rebuild** - L - DONE 2026-06-10 (PR #374, 90164362; also fixed the never-working /ws/narrative proxy)
The refreshed reading surface per the kit: 60px icon rail, typeset reader with voice-by-color (warm cream / muted cream + thin hr dividers, no prefix glyphs), choices 1-3 plus freeform slot 0 inline, Session Ledger right rail (phase telemetry, scene cast, hierarchy), no CommandBar, typewriter reveal. Wired to the live narrative API, not kit mock data. Characters pane at kit fidelity.

**U4 - Full MapTab Rebuild** - L - DONE 2026-06-10 (PR #376, 54dc609d; all four spec failure modes mitigated + tested, first vitest suite in ui/)
Real map per `docs/maptab_rebuild_spec.md` - all four documented failure modes addressed (label culling, zoom anchoring, pointer capture, GeoJSON lng/lat order) - restyled in the new design language.

**U5 - Settings Pane Wiring** - M - DONE 2026-06-10 (PR #377, 154e5150; all seven sections live against nexus.toml, nothing deferred - U-TRACK COMPLETE)
Kit settings pane (theme, typography, narrative mode, model, token budget, PWA icon) wired to real `/api/settings` persistence instead of local draft state.

## Dependency Sketch

M1, M2, M5, M6 can all start today, in parallel. M3 and M8 follow M1; M4 follows M1+M2 (and wants M5 first). M7 follows M6. M9 gates on M3-M8. U1 -> U2 -> U3 -> U4/U5 run as a parallel lane; backend wins contention. M10 closes after M9 plus the UI track.

## Scope Calls I Made - Correct Me Here

1. **Phase B is in, but cut down.** Mid-story entities with no history break the lived-in-world promise, so runtime maturation is MVP; branch-parallel speculation and the NER audit pass are optimizations the spec itself calls expandable/belt-and-suspenders, so they wait.
2. **Orrery default-on is part of v1.0.** "Backend ready" means the world is alive, not that the simulator compiles. That includes making Promote actually promote.
3. **Retrograde retrievability is in.** M3 exists even though no issue tracks it: the spec's core promise ("texture of lived history") depends on it, and the golden path can't honestly pass without it.
4. **Deferred-secret mechanics ship opportunistic.** Decisions 4-5 resolve to "no explicit reveal-preconditions; Skald surfaces secrets when fitting" - the simplest thing that preserves the feature.
5. **Out of scope:** gaia/psyche/nemesis agents, re-enabling structured-data search. (The UI rebuild joined the campaign 2026-06-10 as the U-track.)

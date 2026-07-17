# Skald Bake-Off — Slot-5 Native Playthrough, July 2026

Compiled 2026-07-17 from three evidence tiers: the orchestrating session's transcript (chunks 1–75, Phases A–C), `.nexus/runtime/slot5_sol_progress.log` (chunks 76–148, Phases D–E, machine-readable per-turn records), and the session summaries carried across the Fable→Sol→Fable handoffs. Slot 5 (`save_05`) is the first Orrery-native slot: Orrery and Retrograde ticked from the wizard phase onward, so every turn below exercised the full live pipeline. Per-chunk provenance is backfilled into `chunk_metadata.generation_model` (migration 082) for every chunk with direct evidence; chunks 77–78 remain NULL (absent from the surviving logs).

## Verdict Table

| Model | Phase / Chunks | Turns | Clean Rate | Latency | Verdict |
|---|---|---|---|---|---|
| gpt-5.5 | A · 1–36 | ~36 | not individually benchmarked | — | Incumbent baseline; ran unnoticed via the #498 wizard model-clobber bug |
| gpt-5.6-terra | B · 37–58 | 15 | 15/15 clean | ~35–45s/turn | **Default-Skald recommendation**: reliable, quality prose, half of sol's price; two legitimate multi-chunk sequences (44–47, 52–55) |
| gpt-5.6-sol | C · 59–66 | 8 | 8/8 clean | median 142.5s | Reliable but ~3× terra's latency at 2× the price; no quality edge observed over terra at this task |
| claude-fable-5 | C · 67–74 | 4 | 2 incidents in 4 turns | ~257s observed | Richest prose of the field; a `did not include JSON output` structured-output flake (storyteller-path, intermittent) makes it ineligible for the driver seat until that's hunted |
| hermes-4-70b (local) | C · 75 | 2 | continuity regression + schema hallucination | 26.5–28.6 min/turn | **FAIL**: unusable latency even after the ctx/parallel fixes (prefill 54.5 tok/s); emitted unregistered vocabulary (`role.resources`, the #501 wedge) |
| hermes-4.3-36b Q8_0 (local) | D · 79–83 | 5 | **1/5 accepted** | median 16.4 min; max 36 min (incl. one 1800s provider timeout + retry) | **FAIL** for the driver seat: four of five submissions rejected on semantic QA — restaged completed scenes, redeclared existing entities, contradictory character IDs, ignored player choices. The one accept was "short but continuity-safe" |
| gpt-5.6-terra | E · 84–148 | 66 (incl. D-phase repairs) | 59/66 clean (~89%) | median 48.1s, max 94.7s | Confirmed the Phase-B verdict at 4× the sample size; every Hermes rejection was repaired by terra in ~45s |

## Phase D Detail (Previously Unreported)

Sol ran Hermes 4.3-36B for five submissions against live continuation state (chunks 79–83), each rejected submission immediately repaired by gpt-5.6-terra so the playthrough never stalled:

- Submission 1 (983.7s): thin non-advancing prose; redeclared existing Nneka/Low Current/Underlevel Market; ID–name/location mismatches; seven defer adjudications carrying unrelated shared replacement deltas. Rejected.
- Submission 2 (1021.5s): replayed the pre-repair chunk-76 ledger scene; ignored the selected Saltline contact; redeclared existing entities with conflicting records. Rejected.
- Submission 3 (655.9s): short but continuity-safe relay-threat beat; IDs resolved; actor-scoped defers clean. **Accepted.**
- Submission 4 (2162.1s total): first provider attempt timed out at 1800s after 12,211 tokens; automatic retry succeeded in 333s — output restaged a completed escape, ignored journey prep, reverted resolved character IDs. Rejected.
- Submission 5 (691.3s): ignored the player's choice to take Orji; only 2 choices; contradictory character IDs; misattributed action. Rejected.

Pattern across both local Hermes models: latency is disqualifying on its own (13–36 minutes per turn on an M-series Mac against terra's ~45s), and the failure mode is not schema syntax (structured output held) but **stateful continuity** — restaging completed scenes, redeclaring known entities, dropping player choices. The local-Skald path (#416) remains viable for schema-compliant output but needs either much smaller context or a fundamentally different continuation-state strategy before it can drive.

## Standing Conclusions

1. **gpt-5.6-terra is the default Skald** — the only model in the field that is simultaneously fast, cheap, and reliable at realistic context sizes, now over an 81-turn combined sample.
2. **claude-fable-5 is the prose ceiling** and worth a dedicated flake-hunt (the storyteller-path JSON incident) before any driver-seat retrial.
3. **Local Hermes models are retired from Skald duty** at current hardware/latency; their role, if any, is offline/background generation where wall-clock is free.
4. Chunk provenance is now recorded at generation (migration 082) — future bake-offs read `chunk_metadata.generation_model` instead of reconstructing ranges from session logs. This document exists because that column didn't.

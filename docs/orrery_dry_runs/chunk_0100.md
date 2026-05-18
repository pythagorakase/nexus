# Orrery Dry Run — chunk_0100

- **Slot**: 2
- **Anchor chunk**: 100
- **World time**: 2073-10-14 14:59:00-04:00
- **Window**: 30 chunks (71 → 100)
- **Candidate actors (raw → after existence filter)**: 18 → 7 (11 filtered as not-yet-existing)
- **Bindings evaluated**: 7 actor-only + 0 actor-target
- **Templates available**: 24

## Filtered as not-yet-existing (11)

Actors whose first appearance in `chunk_entity_references_v` postdates anchor chunk 100. These would not exist in production Orrery at this point in the narrative; they only appear in our candidate set because slot 2 is a backfilled corpus where every entity is pre-loaded.

| Actor | First-reference chunk | Sources (would-have-been) |
|---|---|---|
| Emilia (character) | 124 | ephemeral:recently_protective, ephemeral:recently_tended |
| SIX (character) | 349 | ephemeral:captive |
| Raven (character) | 1376 | ephemeral:under_active_pursuit |
| Vasquez (character) | 174 | ephemeral:cns_stimulated, ephemeral:under_active_pursuit |
| Page (character) | 420 | ephemeral:captive |
| The Cradle Dweller (character) | 893 | ephemeral:captive |
| Dr. Oliver Cross (character) | 238 | ephemeral:intelligence_asset_active |
| Naomi Kurata (character) | 110 | ephemeral:intelligence_asset_active |
| Elliot Tran (character) | 182 | ephemeral:under_active_pursuit |
| Boiler (character) | 254 | ephemeral:bereaved |
| Frederick "Rick" Zhao (character) | 197 | ephemeral:reputation_compromised, ephemeral:wounded, ephemeral:captive |

## Scene context (first ~320 chars)

> <!-- SCENE BREAK: S01E05_007 (storyteller heading) --> ## Storyteller ### **CORPO SNAKE – MAKING THE HUNTERS FEEL HUNTED**  Pete **blinks, then grins wide.** **“Oh, that’s *evil*.”**    Alina’s **LED eyes flicker.** **“You’re going to annoy them into leaving?”**    You **shrug.** **“They want to be invisible. Let’s mak

## Candidate actors (7)

| Actor | Sources |
|---|---|
| Victor Sato (character) | ephemeral:intelligence_asset_active |
| Lansky (character) | chunk-ref |
| Asmodeus (character) | ephemeral:cns_stimulated, ephemeral:grudge_active, ephemeral:reputation_compromised |
| Celia (character) | ephemeral:cns_stimulated |
| Reza "Wraith" Kader (character) | ephemeral:under_active_pursuit |
| Juno (character) | ephemeral:under_active_pursuit, ephemeral:recently_violent, ephemeral:grudge_active |
| Talon (character) | ephemeral:recently_violent, ephemeral:wounded, ephemeral:grudge_active |

## Fired (7)

| Actor | Target | Template | Pri | Branch | Rendered stub | event_type | mag |
|---|---|---|---|---|---|---|---|
| Reza "Wraith" Kader (character) | — | `evade_pursuers` | 100 | Reach a safe house through contacts | Reza "Wraith" Kader pings a broker through a low-bandwidth dead-drop and takes a four-hop route to a safe house. | evade_pursuit | 0.58 |
| Juno (character) | — | `evade_pursuers` | 100 | Reach a safe house through contacts | Juno pings a broker through a low-bandwidth dead-drop and takes a four-hop route to a safe house. | evade_pursuit | 0.58 |
| Victor Sato (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Victor Sato trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Lansky (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Lansky trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Celia (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Celia trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Talon (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Talon trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Asmodeus (character) | — | `tend_craft` | 15 | Maintain and improve the tools of the trade | Asmodeus attends to the equipment — the part that's been annoying them for weeks, the upgrade they keep meaning to install, the calibration that's been just slightly off — and emerges with the tools a small degree better than they were. | craft_tended | 0.18 |

### State deltas for fired resolutions

- **Reza "Wraith" Kader (character) / `evade_pursuers`**: `{'character.current_activity': 'relocating through safe contacts'}`
- **Juno (character) / `evade_pursuers`**: `{'character.current_activity': 'relocating through safe contacts'}`
- **Victor Sato (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Lansky (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Celia (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Talon (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Asmodeus (character) / `tend_craft`**: `{'character.current_activity': 'maintaining equipment', 'entity_tags.add': ['recently_tended_craft']}`

## Priority-loss (7)

| Actor | Target | Template | Pri | Would-fire branch | Stub |
|---|---|---|---|---|---|
| Victor Sato (character) | — | `tend_craft` | 15 | Keep the household running | Victor Sato does the work that holds a household together — the meals, the cleaning, the small attentions no one particularly thanks anyone for but whose absence would be felt immediately. It is enough work for a full day, every day, by itself. |
| Lansky (character) | — | `tend_craft` | 15 | Maintain and improve the tools of the trade | Lansky attends to the equipment — the part that's been annoying them for weeks, the upgrade they keep meaning to install, the calibration that's been just slightly off — and emerges with the tools a small degree better than they were. |
| Celia (character) | — | `tend_craft` | 15 | Make the weapon ready for what comes next | Celia takes the weapon apart with the slow patience of someone who has done this enough times to know the geometry of each piece by feel, and puts it back together the same way, attentive to small things only they will notice. |
| Victor Sato (character) | — | `work` | 14 | Keep administrative obligations moving | Victor Sato moves necessary work through the quiet machinery: forms, messages, rosters, notes, approvals, the kind of paper trail that decides what can happen tomorrow. |
| Lansky (character) | — | `work` | 14 | Keep administrative obligations moving | Lansky moves necessary work through the quiet machinery: forms, messages, rosters, notes, approvals, the kind of paper trail that decides what can happen tomorrow. |
| Asmodeus (character) | — | `work` | 14 | Keep administrative obligations moving | Asmodeus moves necessary work through the quiet machinery: forms, messages, rosters, notes, approvals, the kind of paper trail that decides what can happen tomorrow. |
| Celia (character) | — | `work` | 14 | Work a public-facing shift | Celia gives the day to work that other people can see: the counter, the ledger, the bargaining, the small maintenance of trust that keeps trade from becoming chaos. |

## No-branch-match (0)

(none)

## Gate-fail summary (84 total, top 10 templates by frequency)

| Template | Bindings rejected |
|---|---|
| `honor_debt` | 7 |
| `pursue_ghost_lead` | 7 |
| `mourn_loss` | 7 |
| `sleep` | 7 |
| `drink` | 7 |
| `eat` | 7 |
| `travel` | 7 |
| `socialize` | 7 |
| `intimacy` | 7 |
| `maintain_cover` | 7 |

## No-candidate actors (0)

Actors who survived candidate selection but had zero gate-passing templates.

(none — every candidate actor had at least one template apply)

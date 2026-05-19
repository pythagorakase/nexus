# Orrery Dry Run — chunk_0100

- **Slot**: 2
- **Anchor chunk**: 100
- **World time**: 2073-10-14 14:59:00-04:00
- **Window**: 30 chunks (71 → 100)
- **Candidate actors (raw → after existence filter)**: 16 → 6 (10 filtered as not-yet-existing)
- **Bindings evaluated**: 6 actor-only + 0 actor-target (off-screen) + 4 scene-pressure (present-target)
- **Templates available**: 24

## Filtered as not-yet-existing (10)

Actors whose first appearance in `chunk_entity_references_v` postdates anchor chunk 100. These would not exist in production Orrery at this point in the narrative; they only appear in our candidate set because slot 2 is a backfilled corpus where every entity is pre-loaded.

| Actor | First-reference chunk | Sources (would-have-been) |
|---|---|---|
| Emilia (character) | 124 | ephemeral:recently_protective, ephemeral:recently_tended |
| SIX (character) | 349 | ephemeral:captive |
| Sam (character) | 308 | ephemeral:recently_tended_craft |
| Vasquez (character) | 174 | ephemeral:cns_stimulated |
| Page (character) | 420 | ephemeral:recently_tended_craft, ephemeral:captive |
| The Cradle Dweller (character) | 893 | ephemeral:captive, ephemeral:recently_tended_craft |
| Dr. Oliver Cross (character) | 238 | ephemeral:intelligence_asset_active |
| Naomi Kurata (character) | 110 | ephemeral:intelligence_asset_active |
| Boiler (character) | 254 | ephemeral:bereaved |
| Frederick "Rick" Zhao (character) | 197 | ephemeral:reputation_compromised, ephemeral:wounded, ephemeral:captive |

## Scene context (first ~320 chars)

> <!-- SCENE BREAK: S01E05_007 (storyteller heading) --> ## Storyteller ### **CORPO SNAKE – MAKING THE HUNTERS FEEL HUNTED**  Pete **blinks, then grins wide.** **“Oh, that’s *evil*.”**    Alina’s **LED eyes flicker.** **“You’re going to annoy them into leaving?”**    You **shrug.** **“They want to be invisible. Let’s mak

## Candidate actors (6)

| Actor | Sources |
|---|---|
| Victor Sato (character) | ephemeral:intelligence_asset_active |
| Lansky (character) | chunk-ref |
| Asmodeus (character) | ephemeral:cns_stimulated, ephemeral:grudge_active, ephemeral:recently_tended_craft, ephemeral:reputation_compromised |
| Celia (character) | ephemeral:cns_stimulated |
| Juno (character) | ephemeral:recently_violent, ephemeral:grudge_active |
| Talon (character) | ephemeral:recently_violent, ephemeral:wounded, ephemeral:grudge_active |

## Fired — off-screen activity (6)

| Actor | Target | Template | Pri | Branch | Rendered stub | event_type | mag |
|---|---|---|---|---|---|---|---|
| Victor Sato (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Victor Sato trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Lansky (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Lansky trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Celia (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Celia trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Juno (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Juno trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Talon (character) | — | `hide` | 84 | Go dark and reduce signal exposure | Talon trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there. | signal_exposure_reduced | 0.36 |
| Asmodeus (character) | — | `tend_craft` | 15 | Maintain and improve the tools of the trade | Asmodeus attends to the equipment — the part that's been annoying them for weeks, the upgrade they keep meaning to install, the calibration that's been just slightly off — and emerges with the tools a small degree better than they were. | craft_tended | 0.18 |

### State deltas for fired resolutions

- **Victor Sato (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Lansky (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Celia (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Juno (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Talon (character) / `hide`**: `{'character.current_activity': 'reducing signal exposure'}`
- **Asmodeus (character) / `tend_craft`**: `{'character.current_activity': 'maintaining equipment', 'entity_tags.add': ['recently_tended_craft']}`

## Fired — scene pressures (present-target) (4)

Pressure-policy templates fired against on-screen targets. These don't appear in `orrery_resolutions` like off-screen drafts; production routes them as Storyteller-facing scene pressures.

| Actor | Present target | Template | Pri | Branch | Rendered stub | event_type | mag |
|---|---|---|---|---|---|---|---|
| Asmodeus (character) | Alex (character) | `extract_vengeance` | 90 | Watch and document, waiting for a better window | Asmodeus continues to observe Alex's patterns from cover — shift changes, contacts, the geometry of their movements — letting the grudge stay sharp without spending it prematurely. | retaliation_attempted | 0.34 |
| Victor Sato (character) | Alex (character) | `surveil` | 48 | Intercept signal traffic | Victor Sato watches the signal field around Alex: not the person directly, not yet, but the traffic and absences that make a life legible to someone patient enough. | surveillance_performed | 0.48 |
| Lansky (character) | Alex (character) | `surveil` | 48 | Intercept signal traffic | Lansky watches the signal field around Alex: not the person directly, not yet, but the traffic and absences that make a life legible to someone patient enough. | surveillance_performed | 0.48 |
| Celia (character) | Alex (character) | `surveil` | 48 | Keep tabs from a distance | Celia keeps tabs on Alex without touching the line between them: a pattern noticed, a channel checked, a small confirmation that does not become contact. | surveillance_performed | 0.44 |

## Priority-loss (8)

| Actor | Target | Template | Pri | Would-fire branch | Stub |
|---|---|---|---|---|---|
| Victor Sato (character) | — | `tend_craft` | 15 | Keep the household running | Victor Sato does the work that holds a household together — the meals, the cleaning, the small attentions no one particularly thanks anyone for but whose absence would be felt immediately. It is enough work for a full day, every day, by itself. |
| Lansky (character) | — | `tend_craft` | 15 | Maintain and improve the tools of the trade | Lansky attends to the equipment — the part that's been annoying them for weeks, the upgrade they keep meaning to install, the calibration that's been just slightly off — and emerges with the tools a small degree better than they were. |
| Celia (character) | — | `tend_craft` | 15 | Make the weapon ready for what comes next | Celia takes the weapon apart with the slow patience of someone who has done this enough times to know the geometry of each piece by feel, and puts it back together the same way, attentive to small things only they will notice. |
| Juno (character) | — | `tend_craft` | 15 | Make the weapon ready for what comes next | Juno takes the weapon apart with the slow patience of someone who has done this enough times to know the geometry of each piece by feel, and puts it back together the same way, attentive to small things only they will notice. |
| Victor Sato (character) | — | `work` | 14 | Keep administrative obligations moving | Victor Sato moves necessary work through the quiet machinery: forms, messages, rosters, notes, approvals, the kind of paper trail that decides what can happen tomorrow. |
| Lansky (character) | — | `work` | 14 | Keep administrative obligations moving | Lansky moves necessary work through the quiet machinery: forms, messages, rosters, notes, approvals, the kind of paper trail that decides what can happen tomorrow. |
| Asmodeus (character) | — | `work` | 14 | Keep administrative obligations moving | Asmodeus moves necessary work through the quiet machinery: forms, messages, rosters, notes, approvals, the kind of paper trail that decides what can happen tomorrow. |
| Celia (character) | — | `work` | 14 | Work a public-facing shift | Celia gives the day to work that other people can see: the counter, the ledger, the bargaining, the small maintenance of trust that keeps trade from becoming chaos. |

## No-branch-match (0)

(none)

## Gate-fail summary (106 total, top 10 templates by frequency)

| Template | Bindings rejected |
|---|---|
| `evade_pursuers` | 6 |
| `honor_debt` | 6 |
| `pursue_ghost_lead` | 6 |
| `mourn_loss` | 6 |
| `sleep` | 6 |
| `drink` | 6 |
| `eat` | 6 |
| `travel` | 6 |
| `socialize` | 6 |
| `intimacy` | 6 |

## No-candidate actors (0)

Actors who survived candidate selection but had zero gate-passing templates.

(none — every candidate actor had at least one template apply)

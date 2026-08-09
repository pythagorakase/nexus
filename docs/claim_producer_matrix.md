# Tracked-at-Birth Claim Producer Matrix

Issue #679 producer audit and shipped tracked-at-birth policy.

## Audit boundary and rules

- The active registry is reconstructed from migrations 024 through 091. It has
  109 non-deprecated event types in this checkout.
- `nexus/agents/orrery/templates.py` supplies 87 primary event types and three
  detected signal event types to the sync/async live emitters in
  `nexus/agents/orrery/events.py`. Those emitters persist only the scalar
  `actor` and `target` bindings (`faction` substitutes for a missing target).
  They do not receive a scene-presence or proximity roster.
- Relationship drift, claim propagation, and backstory secret lifecycle events
  have separate producers. The remaining 14 registry types have no live
  Orrery producer in this checkout.
- Retrograde can author any registered event type from explicitly resolved
  participant references. That historical authoring path is not a live-event
  producer and is outside Phase 2: no allowlist decision below authorizes a
  historical backfill.
- Visibility is an epistemic treatment: **public** means implicit/common under
  the #495 sparse rule, including low-stakes ambient actions; **bounded** means
  a finite, named audience; **private** means only the named holder/actor is
  guaranteed to know.
- A roster is verifiable only when the producer already carries it in bindings,
  `world_event_entities`, or an explicit secret/propagation record. Co-location
  or narrative proximity never adds a knower.
- Birth acquisition uses `participant` for `actor`, `target`, or `beneficiary`,
  and `witness` only for an explicit `observer`/`witness` row. `told` and
  `granted` are later revelation/manual-acquisition tiers, not live-event birth
  tiers. No generic resolver event currently has an admissible witness roster.

## Live tracking allowlist

These are the exact 18 live event types in the implemented allowlist. All other
event types remain excluded for the reasons documented below.

| Event type | Live producer / verifiable roster | Visibility | Eligible roles and tiers | Track? | Rationale |
| --- | --- | --- | --- | --- | --- |
| `compliance_alert` | Detected signal from `surveil` / `act_on_intel`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | A detected enforcement/surveillance signal changes the subject's threat behavior; the signal row exists only after detection. |
| `encoded_message` | Detected `cultivate_informant` signal; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | A covert message is a private two-party communication with later obligation/intelligence consequences. |
| `hunt_called_off` | `extract_vengeance`; explicit actor + target, but only actor is guaranteed to know | private | actor -> participant | Yes | Ending a hunt changes later threat behavior; withholding target awareness prevents false relief. |
| `hunt_declared` | `extract_vengeance`; explicit actor + target, but only actor is guaranteed to know | private | actor -> participant | Yes | A private decision to begin an active hunt is consequential; target knowledge is represented separately by a detected `threat_issued` signal. |
| `informant_contact` | `cultivate_informant`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | Handler/asset contact is a bounded private exchange that can drive later intelligence behavior. |
| `intel_acquired` | `cultivate_informant`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | Material intelligence acquisition is consequential and both named exchange participants are authoritative knowers. |
| `intel_acted_on` | `act_on_intel`; explicit actor + subject target, but branches do not consistently inform the subject | private | actor -> participant | Yes | Selling, confronting with, or consolidating intelligence changes later pressure; actor-only is the safe common audience across all branches. |
| `protective_intervention` | `protect_kin`; explicit actor + target, but several branches are travel, signaling, or vigil without target receipt | private | actor -> participant | Yes | Intervention around an active threat can change later behavior, while actor-only avoids leaking unreceived aid to the target. |
| `pursue_romance_completed` | `advance_pursue_romance`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | Mutual acceptance establishes a bounded relationship-status change, not merely project progress. |
| `recruit_ally_completed` | `advance_recruit_ally`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | A named commitment establishes ally status and directly changes later package eligibility. |
| `relationship_drift_milestone` | Drift producer; explicit directed source + target dyad in `world_event_entities` | private | actor/source -> participant | Yes | Keep the existing tracked type because the source's valence rung affects later behavior, but do not grant the target knowledge of another character's internal drift. |
| `retaliation_attempted` | `extract_vengeance`; explicit actor + target, but branches include covert reputation attack/surveillance | private | actor -> participant | Yes | A consequential hostile act is worth tracking; actor-only is safe across branches and avoids subject leakage. |
| `retaliation_executed` | `extract_vengeance`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | Direct violence against the named target is a consequential bounded incident; no unnamed bystander is inferred. |
| `rival_consulted` | `consult_rival`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | A truce meeting or received routed message is a bounded private deal that changes later relationship behavior. |
| `seek_redemption_completed` | `advance_seek_redemption`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | Accepted amends are a named two-party reconciliation and relationship-state change. |
| `surveillance_performed` | `surveil`; explicit actor + subject target, but no observer/detection roster | private | actor -> participant | Yes | Covert surveillance is consequential; the subject learns only through a separately detected `compliance_alert`. |
| `threat_issued` | Detected signal from `extract_vengeance` / `act_on_intel`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | Existing tracked type; the detected signal is an explicit threat to a named target and drives protective/evasion behavior. |
| `warning_delivered` | `warn_ally`; explicit actor + target | bounded | actor -> participant; target -> participant | Yes | Delivery and the target's `forewarned` state establish a bounded warning with later behavioral effects. |

## Resolver exclusions

Each row below is deliberately excluded. “Actor only” or “actor + target” means
the endpoint roster is verifiable, not that additional witnesses may be
inferred.

| Event type | Live producer / verifiable roster | Visibility | Eligible roles and tiers if tracked | Track? | Exclusion rationale |
| --- | --- | --- | --- | --- | --- |
| `ate` | `eat`; actor only | public | actor -> participant | No | Ambient need fulfillment; mechanical need/cooldown projection. |
| `build_venture_abandoned` | `advance_build_venture`; actor only | public | actor -> participant | No | Actor-owned project lifecycle projection, not a bounded incident. |
| `build_venture_completed` | `advance_build_venture`; actor only | public | actor -> participant | No | Opening a venture/proprietor status is public world state and stays implicit. |
| `build_venture_milestone` | `advance_build_venture`; actor only | public | actor -> participant | No | Mechanical stage projection. |
| `build_venture_progressed` | `advance_build_venture`; actor only | public | actor -> participant | No | Mechanical progress projection. |
| `build_venture_stalled` | `advance_build_venture`; actor only | public | actor -> participant | No | Mechanical stall projection. |
| `build_venture_started` | `start_build_venture`; actor only | public | actor -> participant | No | Venture setup is ordinary project state, not a bounded consequential audience event. |
| `contact_deferred` | `reach_out`; actor + target binding, only actor guaranteed to know | private | actor -> participant | No | A withheld contact is low-stakes internal intent and primarily a cooldown projection. |
| `contact_made` | Four contact packages; explicit actor + target | bounded | actor -> participant; target -> participant | No | Generic/routine contact is deliberately sparse background knowledge. |
| `counter_surveillance_sweep` | `hide`; actor only | private | actor -> participant | No | Mechanical concealment maintenance; it does not identify a discovered observer or secret. |
| `court_patron_abandoned` | Character or faction patron project; actor + target/faction | bounded | actor -> participant; target/faction -> participant only where receipt is explicit | No | One event type conflates rejection with actor-only timeout/withdrawal; project lifecycle remains implicit. |
| `court_patron_completed` | Character or faction patron project; actor + target/faction | public | actor -> participant; target/faction -> participant | No | Authored branches explicitly grant public favor or faction standing, so the status is implicit under #495. |
| `court_patron_milestone` | Character or faction patron project; actor + target/faction | bounded | actor -> participant | No | Mechanical stage projection; the counterparty is not guaranteed to observe every milestone. |
| `court_patron_progressed` | Character or faction patron project; actor + target/faction | bounded | actor -> participant | No | Mechanical progress projection. |
| `court_patron_stalled` | Character or faction patron project; actor + target/faction | private | actor -> participant | No | Mechanical stall projection. |
| `court_patron_started` | Character or faction patron project; actor + target/faction | bounded | actor -> participant | No | “Working to gain notice” does not prove counterparty receipt; actor-owned project start remains implicit. |
| `craft_tended` | `tend_craft`; actor only | public | actor -> participant | No | Routine maintenance/cooldown event. |
| `drank` | `drink`; actor only | public | actor -> participant | No | Ambient need fulfillment; mechanical need/cooldown projection. |
| `errands_run` | `run_errands`; actor only | public | actor -> participant | No | Mundane ambient activity. |
| `evade_pursuit` | `evade_pursuers`; actor only | private | actor -> participant | No | The producer cannot name a pursuer or witness, and the event primarily clears/updates pursuit state. |
| `hideout_maintained` | `hide`; actor only | private | actor -> participant | No | Steady-state concealment maintenance, not a new consequential disclosure. |
| `honor_debt` | `honor_debt`; actor only | private | actor -> participant | No | The obligation counterparty is absent from bindings, so the producer lacks the deal's bounded audience. |
| `household_work_performed` | `work`; actor only | public | actor -> participant | No | Routine work projection. |
| `intel_reviewed` | `surveil`; actor + subject target, only actor guaranteed to know | private | actor -> participant | No | Reviewing already-held intel is mechanical maintenance and creates no new discovery. |
| `intimacy_deferred` | `intimacy`; actor only | private | actor -> participant | No | Internal need/project maintenance without a named counterparty. |
| `intimacy_fulfilled` | `intimacy`; actor only | private | actor -> participant | No | The event type has no partner binding and cannot name a complete bounded audience. |
| `intimacy_partial` | `intimacy`; actor only | private | actor -> participant | No | Mechanical need fulfillment without a named counterparty. |
| `intimacy_pursued` | `intimacy`; actor only | private | actor -> participant | No | Actor-only intent/need projection, not a verified deal or outcome. |
| `kin_visit` | `reach_out`; explicit actor + target | bounded | actor -> participant; target -> participant | No | Ordinary social contact stays implicit. |
| `maintain_cover` | `maintain_cover`; actor only | private | actor -> participant | No | Steady-state cover maintenance, not a new discovery or exposure. |
| `mourning_act` | `mourn_loss`; actor only | public | actor -> participant | No | Ordinary emotional activity/cooldown. |
| `mourning_completed` | `mourn_loss`; actor only | public | actor -> participant | No | Mechanical grief-state clearance; no bounded audience. |
| `pursue_identity_lead` | `uncover_past`; actor only | private | actor -> participant | No | Following a lead is not itself a discovered secret, and no source/witness is bound. |
| `pursue_romance_abandoned` | `advance_pursue_romance`; actor + target binding | private | actor -> participant | No | Event type conflates rebuff with actor-only timeout/withdrawal; target knowledge is not uniform. |
| `pursue_romance_milestone` | `advance_pursue_romance`; actor + target | bounded | actor -> participant | No | Mechanical courtship-stage projection; target receipt is not guaranteed by every branch. |
| `pursue_romance_progressed` | `advance_pursue_romance`; actor + target | bounded | actor -> participant | No | Mechanical progress projection. |
| `pursue_romance_stalled` | `advance_pursue_romance`; actor + target | private | actor -> participant | No | Mechanical stall projection. |
| `pursue_romance_started` | `start_pursue_romance`; actor + target | private | actor -> participant | No | “Testing the waters” is actor-owned project intent, not proven mutual awareness. |
| `recreation_taken` | `recreate`; actor only | public | actor -> participant | No | Mundane ambient activity. |
| `recruit_ally_abandoned` | `advance_recruit_ally`; actor + target binding | private | actor -> participant | No | Event type conflates hostile refusal with actor-only delay/withdrawal; target knowledge is not uniform. |
| `recruit_ally_milestone` | `advance_recruit_ally`; actor + target | bounded | actor -> participant | No | Mechanical recruitment-stage projection. |
| `recruit_ally_progressed` | `advance_recruit_ally`; actor + target | bounded | actor -> participant | No | Mechanical progress projection. |
| `recruit_ally_stalled` | `advance_recruit_ally`; actor + target | private | actor -> participant | No | Mechanical stall projection. |
| `recruit_ally_started` | `start_recruit_ally`; actor + target | private | actor -> participant | No | “Sounding out” a contact does not prove mutual agreement; project start remains implicit. |
| `relocation_plan_abandoned` | `advance_relocation_plan`; actor only | private | actor -> participant | No | Mechanical actor-owned project lifecycle. |
| `relocation_plan_completed` | `advance_relocation_plan`; actor only | private | actor -> participant | No | Mechanical handoff from project to travel; no named recipient/witness. |
| `relocation_plan_milestone` | `advance_relocation_plan`; actor only | private | actor -> participant | No | Mechanical stage projection. |
| `relocation_plan_progressed` | `advance_relocation_plan`; actor only | private | actor -> participant | No | Mechanical progress projection. |
| `relocation_plan_stalled` | `advance_relocation_plan`; actor only | private | actor -> participant | No | Mechanical stall projection. |
| `relocation_plan_started` | `start_relocation_plan`; actor only | private | actor -> participant | No | Private plan intent with no additional audience and primarily project state. |
| `seek_redemption_abandoned` | `advance_seek_redemption`; actor + target binding | private | actor -> participant | No | Event type conflates rejection with actor-only delay/withdrawal; target knowledge is not uniform. |
| `seek_redemption_milestone` | `advance_seek_redemption`; actor + target | bounded | actor -> participant | No | Mechanical amends-stage projection. |
| `seek_redemption_progressed` | `advance_seek_redemption`; actor + target | bounded | actor -> participant | No | Mechanical progress projection. |
| `seek_redemption_stalled` | `advance_seek_redemption`; actor + target | private | actor -> participant | No | Mechanical stall projection. |
| `seek_redemption_started` | `start_seek_redemption`; actor + target | bounded | actor -> participant | No | Actor-owned project start does not guarantee the wronged party has received the attempt. |
| `signal_exposure_reduced` | `hide`; actor only | private | actor -> participant | No | Mechanical concealment-state maintenance. |
| `slept` | `sleep`; actor only | private | actor -> participant | No | Ambient need fulfillment; mechanical need/cooldown projection. |
| `social_travel_departed` | `socialize`; actor only | public | actor -> participant | No | Routine movement/need setup stays implicit. |
| `socialized` | `socialize`; actor only; companions are not bound | public | actor -> participant | No | Ambient social need fulfillment with no authoritative companion roster. |
| `socialized_alone` | `socialize`; actor only | public | actor -> participant | No | Ambient need fulfillment. |
| `stroll_taken` | `stroll`; actor only | public | actor -> participant | No | Mundane ambient activity. |
| `tended_wound` | `tend_wounded`; explicit actor + target | bounded | actor -> participant; target -> participant | No | Routine care is a mechanical wound-state maintenance event, not the consequential incident itself. |
| `training_performed` | `train`; actor only | public | actor -> participant | No | Mundane maintenance/cooldown activity. |
| `travel_arrived` | `travel`; actor only | public | actor -> participant | No | Public movement/state projection stays implicit. |
| `travel_delayed` | `travel`; actor only | public | actor -> participant | No | Mechanical route progress projection. |
| `travel_departed` | `travel` / `routine_commute`; actor only | public | actor -> participant | No | Public movement/state projection stays implicit. |
| `travel_prepared` | `travel` / `routine_commute`; actor only | public | actor -> participant | No | Mechanical travel setup. |
| `travel_progressed` | `travel`; actor only | public | actor -> participant | No | Mechanical route progress projection. |
| `upkeep_done` | `upkeep`; actor only | public | actor -> participant | No | Mundane ambient activity. |
| `vigil_held` | `keep_vigil`; explicit actor + target | bounded | actor -> participant; target -> participant | No | Routine care/cooldown, not a new consequential disclosure or status change. |
| `welfare_check` | `check_on_dependent`; explicit actor + target | bounded | actor -> participant; target -> participant | No | Ordinary duty-of-care contact stays implicit. |
| `work_performed` | `work`; actor only | public | actor -> participant | No | Routine work projection. |
| `wound_healed` | `tend_wounded`; explicit actor + target | bounded | actor -> participant; target -> participant | No | Mechanical wound-state clearance; the injury/violence incident, not its routine resolution, is epistemically consequential. |

## Specialized producers and vocabulary-only exclusions

| Event type | Producer / verifiable roster | Visibility | Eligible roles and tiers if tracked | Track? | Exclusion rationale |
| --- | --- | --- | --- | --- | --- |
| `backstory_revealed` | Reveal drain; holder plus participants already attached to the secret's source event, filtered to that explicit set | bounded | holder keeps existing awareness; newly revealed participant -> told | No | This event promotes and grants awareness of an existing secret claim; minting a second claim would duplicate the account. |
| `backstory_secret_authored` | Secret authoring; explicit holder and pre-existing private claim | private | holder -> granted on the existing claim | No | This is a ledger event for an already-authored private claim, not a new event claim. |
| `captivity_ended` | No live producer (registry only) | public | none | No | Canonical state-clearance vocabulary; no emitting site or bounded roster. |
| `circumstance_reversed` | No live producer (registry only) | public | none | No | Canonical state-clearance vocabulary; no emitting site or bounded roster. |
| `claim_propagated` | Contagion drain; explicit teller/root/listener in propagation plan | bounded | listener -> told on existing/delivered claim | No | Mechanical awareness ledger event; the validator explicitly forbids it in `claim_event_types`. |
| `confrontation_resolved` | No live producer (registry only) | public | none | No | Canonical state-clearance vocabulary; no emitting site or bounded roster. |
| `cured` | No live producer (registry only) | public | none | No | Canonical care-state clearance with no live audience source. |
| `death_recorded` | No live producer (registry only) | public | none | No | Canonical/public world state stays implicit; no live roster exists. |
| `discovered` | No live producer (registry only) | bounded | none until an emitter supplies discoverer/subject | No | Semantically eligible, but there is no live producer to name the discoverer or any witness. |
| `escaped` | No live producer (registry only) | public | none | No | Canonical movement/state clearance with no live audience source. |
| `exposed` | No live producer (registry only) | bounded | none until an emitter supplies exposed subject/observers | No | Semantically eligible, but the vocabulary alone cannot establish an audience. |
| `faction_realignment` | No live producer (registry only) | bounded | none until an emitter supplies faction/participants/witnesses | No | A limited-witness faction change could qualify, but this checkout has no producer or roster. |
| `recovered_from_illness` | No live producer (registry only) | public | none | No | Canonical care-state clearance with no live audience source. |
| `regained_consciousness` | No live producer (registry only) | public | none | No | Canonical state clearance with no live audience source. |
| `relationship_drift_drained` | Drift drain summary; no participant rows, only aggregate counts | public | none | No | Pure mechanical projection of the drain, without an audience roster. |
| `revealed` | No live producer (registry only) | bounded | none until an emitter supplies revealed subject/observers | No | Semantically eligible, but the vocabulary alone cannot establish an audience. |
| `threat_removed` | No live producer (registry only) | public | none | No | Canonical threat-state clearance with no live audience source. |
| `unmasked` | No live producer (registry only) | bounded | none until an emitter supplies unmasked subject/recognizers | No | Semantically eligible, but the vocabulary alone cannot establish an audience. |

## Approval set

Proposed `claim_event_types`, sorted for review:

```toml
claim_event_types = [
    "compliance_alert",
    "encoded_message",
    "hunt_called_off",
    "hunt_declared",
    "informant_contact",
    "intel_acquired",
    "intel_acted_on",
    "protective_intervention",
    "pursue_romance_completed",
    "recruit_ally_completed",
    "relationship_drift_milestone",
    "retaliation_attempted",
    "retaliation_executed",
    "rival_consulted",
    "seek_redemption_completed",
    "surveillance_performed",
    "threat_issued",
    "warning_delivered",
]
```

Phase 2 must derive awareness per event type rather than reuse the global
actor/target mapping. In particular, actor-only recommendations above treat a
bound target as the claim's subject, not as a knower. It must not add observers
from location or Storyteller-presence inference. Existing retrograde rows are
not revisited.

"""Built-in Orrery behavior package catalog."""

from __future__ import annotations

from nexus.agents.orrery.substrate import (
    ALWAYS,
    AND,
    NOT,
    OR,
    Branch,
    Slot,
    Template,
    co_located,
    count_co_located,
    has_any_tag,
    has_ephemeral,
    has_relationship_of_type,
    has_symmetric_relationship_of_type,
    has_tag,
    in_location_class,
    lacks_tag,
    recent_event,
    since_last_event_at_least,
    time_of_day_in,
    trust_at_least,
    trust_below,
    weather_is,
)


EVADE_PURSUERS = Template(
    id="evade_pursuers",
    priority=100,
    blurb="When the city is closing in.",
    required_slots=(Slot.ACTOR,),
    package_gate=OR(
        has_ephemeral("under_active_pursuit"),
        recent_event("compliance_alert", within_ticks=5, target_slot=Slot.ACTOR),
    ),
    branches=(
        Branch(
            label="Go to ground in flooded tunnels",
            conditions=AND(in_location_class("the_roots"), weather_is("rain")),
            narrative_stub=(
                "{actor} slips off a Rootline platform into a flooded service "
                "corridor and kills every transmitter on their person."
            ),
            state_delta={
                "character.current_activity": "hiding from active pursuit",
                "entity_tags.add": ["off_grid"],
            },
            event_type="evade_pursuit",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.72,
        ),
        Branch(
            label="Reach a safe house through contacts",
            conditions=has_tag("contacts_available"),
            narrative_stub=(
                "{actor} pings a broker through a low-bandwidth dead-drop and "
                "takes a four-hop route to a safe house."
            ),
            state_delta={
                "character.current_activity": "relocating through safe contacts",
            },
            event_type="evade_pursuit",
            changed_fields=("character.current_activity",),
            magnitude=0.58,
        ),
        Branch(
            label="Keep moving, blend into public flow",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} joins the densest pedestrian current nearby, never "
                "stopping long enough to make a clean pattern."
            ),
            state_delta={"character.current_activity": "blending into public flow"},
            event_type="evade_pursuit",
            changed_fields=("character.current_activity",),
            magnitude=0.42,
        ),
    ),
)


HONOR_DEBT = Template(
    id="honor_debt",
    priority=80,
    blurb="A binding obligation surfaces from the blank years.",
    required_slots=(Slot.ACTOR,),
    package_gate=OR(
        has_ephemeral("debt_pulse_active"),
        recent_event("encoded_message", within_ticks=3, target_slot=Slot.ACTOR),
    ),
    branches=(
        Branch(
            label="Activate the Ghostprint Key at a sympathetic node",
            conditions=AND(
                has_tag("ghostprint_active"), in_location_class("the_roots")
            ),
            narrative_stub=(
                "{actor} finds a half-decommissioned authentication terminal "
                "and pulses the Key against it."
            ),
            state_delta={
                "character.current_activity": "signaling through a sympathetic node",
            },
            event_type="honor_debt",
            changed_fields=("character.current_activity",),
            magnitude=0.66,
        ),
        Branch(
            label="Fulfill obligation through a dead-drop",
            conditions=has_tag("contacts_available"),
            narrative_stub=(
                "{actor} tucks an encoded microdrive behind a loose ceramic "
                "tile and leaves a mark for the recipient."
            ),
            state_delta={"character.current_activity": "servicing an old debt"},
            event_type="honor_debt",
            changed_fields=("character.current_activity",),
            magnitude=0.5,
        ),
        Branch(
            label="Leave a public sign",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} pays a street artist in physical cash to place a "
                "specific glyph where only the intended recipient will read it."
            ),
            state_delta={"character.current_activity": "leaving a coded public sign"},
            event_type="honor_debt",
            changed_fields=("character.current_activity",),
            magnitude=0.38,
        ),
    ),
)


PURSUE_GHOST_LEAD = Template(
    id="pursue_ghost_lead",
    priority=60,
    blurb="The fragments of a buried identity tug at the actor.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_tag("seeking_identity"),
        time_of_day_in("evening", "night"),
        lacks_tag("under_active_pursuit"),
        NOT(has_ephemeral("under_active_pursuit")),
    ),
    branches=(
        Branch(
            label="Recon a hideout their body remembers",
            conditions=in_location_class("the_roots"),
            narrative_stub=(
                "{actor} picks through maintenance corridors to a place their "
                "body recognizes before memory can explain why."
            ),
            state_delta={"character.current_activity": "reconning remembered terrain"},
            event_type="pursue_identity_lead",
            changed_fields=("character.current_activity",),
            magnitude=0.64,
        ),
        Branch(
            label="Probe the data fog with the Key",
            conditions=has_tag("ghostprint_active"),
            narrative_stub=(
                "{actor} brushes against a mid-tier operator, ducks into a "
                "kiosk, and lets the Key scrape fragments from the ledger noise."
            ),
            state_delta={"character.current_activity": "probing identity records"},
            event_type="pursue_identity_lead",
            changed_fields=("character.current_activity",),
            magnitude=0.57,
        ),
        Branch(
            label="Query the broker network",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} visits a broker who owes them a favor and leaves with "
                "one new question and one dangerous name."
            ),
            state_delta={"character.current_activity": "querying the broker network"},
            event_type="pursue_identity_lead",
            changed_fields=("character.current_activity",),
            magnitude=0.44,
        ),
    ),
)


MAINTAIN_COVER = Template(
    id="maintain_cover",
    priority=0,
    blurb="Baseline activity that keeps the behavioral ledger plausible.",
    required_slots=(Slot.ACTOR,),
    package_gate=ALWAYS,
    branches=(
        Branch(
            label="Run a low-level courier job",
            conditions=in_location_class("the_glow"),
            narrative_stub=(
                "{actor} picks up a benign data packet, walks it across the "
                "district, and earns just enough to register as ordinary."
            ),
            state_delta={"character.current_activity": "running low-level cover work"},
            event_type="maintain_cover",
            changed_fields=("character.current_activity",),
            magnitude=0.16,
        ),
        Branch(
            label="Drift through public space",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} moves through public space at the pace of someone "
                "with somewhere to be, generating forgettable civilian noise."
            ),
            state_delta={"character.current_activity": "maintaining public cover"},
            event_type="maintain_cover",
            changed_fields=("character.current_activity",),
            magnitude=0.1,
        ),
    ),
)


# ----------------------------------------------------------------------------
# Package-library expansion (multi-slot templates)
#
# The three templates below depend on the multi-slot binding composer in
# resolver.py::compose_actor_target_bindings. They share an authoring lineage:
# drafted by a frontier-model conversation partner (temp/orrery/orrery_
# package_contributions.md), integrated here with the following deliberate
# divergences:
#
#   * PROTECT_KIN: the contribution draft listed `lover` as a relationship_type;
#     substituted with `romantic` (already in the enum and semantically broader).
#   * Symmetric relationships (family/romantic/chosen_kin/comrade for kin,
#     enemy/rival for vendetta) use has_symmetric_relationship_of_type to keep
#     the gates readable; the helper expresses bidirectional lookup against the
#     stored-direction-only WorldState hydration.
#
# Two contracts that PR 3 (CommitOrreryTick) will need to honor or revisit:
#
#   * Cross-actor state_delta keys (entity_tags_target.add/remove) are
#     preserved verbatim from the draft. The substrate accepts arbitrary
#     Mapping keys, so they're decorative here; PR 3 must parse and route
#     them by convention (no enum/TypedDict yet). Define a state_delta
#     schema alongside the writer if the implicit-string approach proves
#     too brittle in implementation.
#   * Trust hydration is un-implemented (resolver.py:177 TODO). Any branch
#     gated on trust_at_least(N) with N > 0 or trust_below(N) with N < 0
#     is currently unreachable — WorldState.trust defaults to 0 for every
#     pair. The affected branches are flagged with TODO comments below;
#     they remain in the catalog because they're the intended firing
#     paths once trust hydration lands.
# ----------------------------------------------------------------------------


EXTRACT_VENGEANCE = Template(
    id="extract_vengeance",
    priority=90,
    blurb="A grudge ripens until the moment is right to settle it.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Cooldown is intentionally actor-global (no target_slot=): an active
    # grudge has a refractory period after any attempt regardless of
    # target — the actor needs to "calm down," not just back off a
    # specific target.
    package_gate=AND(
        has_ephemeral("grudge_active"),
        OR(
            has_symmetric_relationship_of_type("enemy"),
            has_symmetric_relationship_of_type("rival"),
            # TODO: trust_below(-2) is unreachable until resolver.py:177's
            # trust hydration TODO is resolved. The OR keeps the predicate
            # documented; the enemy/rival arms carry the gate today.
            trust_below(-2),
        ),
        since_last_event_at_least("retaliation_attempted", minimum_ticks=8),
        NOT(has_ephemeral("under_active_pursuit")),
    ),
    branches=(
        Branch(
            label="Strike directly when opportunity opens",
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                NOT(count_co_located(2, slot=Slot.TARGET)),
                has_any_tag("vendetta_holder", "violent_history"),
            ),
            narrative_stub=(
                "{actor} moves on {target} in the moment the corridor clears — "
                "no warning, no negotiation, the years of waiting compressed "
                "into the time it takes to close a few meters of distance."
            ),
            state_delta={
                "character.current_activity": "executing retaliation",
                "entity_tags.add": ["recently_violent"],
                "entity_tags_target.remove": ["grudge_active"],
            },
            event_type="retaliation_executed",
            changed_fields=(
                "character.current_activity",
                "entity_tags",
                "world_events",
            ),
            magnitude=0.85,
        ),
        Branch(
            label="Surface a reputation attack in the right channels",
            conditions=AND(
                has_tag("contacts_available"),
                in_location_class("the_glow"),
            ),
            narrative_stub=(
                "{actor} feeds a curated dossier on {target} into three brokers "
                "in the Glow, taking pains to make the leak look like an accident "
                "of incautious clients rather than deliberate sabotage."
            ),
            state_delta={
                "character.current_activity": "running a reputation attack",
                "entity_tags_target.add": ["reputation_compromised"],
            },
            event_type="retaliation_attempted",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.58,
        ),
        Branch(
            label="Watch and document, waiting for a better window",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} continues to observe {target}'s patterns from cover — "
                "shift changes, contacts, the geometry of their movements — "
                "letting the grudge stay sharp without spending it prematurely."
            ),
            state_delta={
                "character.current_activity": "surveilling a grudge target",
            },
            event_type="retaliation_attempted",
            changed_fields=("character.current_activity",),
            magnitude=0.34,
        ),
    ),
)


PROTECT_KIN = Template(
    id="protect_kin",
    priority=95,
    blurb="A bond pulls the actor toward someone in active danger.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    package_gate=AND(
        OR(
            has_symmetric_relationship_of_type("family"),
            has_symmetric_relationship_of_type("romantic"),
            has_symmetric_relationship_of_type("chosen_kin"),
            has_symmetric_relationship_of_type("comrade"),
        ),
        OR(
            has_ephemeral("under_active_pursuit", slot=Slot.TARGET),
            has_ephemeral("wounded", slot=Slot.TARGET),
            recent_event(
                "threat_issued",
                within_ticks=4,
                target_slot=Slot.TARGET,
            ),
        ),
        NOT(has_ephemeral("under_active_pursuit")),
    ),
    branches=(
        Branch(
            label="Physically intervene at the target's location",
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                has_ephemeral("under_active_pursuit", slot=Slot.TARGET),
            ),
            narrative_stub=(
                "{actor} reaches {target} as the noose tightens — pulling them "
                "off the line of sight, into a service corridor whose layout "
                "{actor} has memorized for exactly this kind of moment."
            ),
            state_delta={
                "character.current_activity": "shielding kin from active threat",
                "entity_tags.add": ["recently_protective"],
                "entity_tags_target.remove": ["under_active_pursuit"],
            },
            event_type="protective_intervention",
            changed_fields=(
                "character.current_activity",
                "entity_tags",
                "world_events",
            ),
            magnitude=0.78,
        ),
        Branch(
            label="Travel toward the target's last known location",
            conditions=AND(
                has_tag("contacts_available"),
                NOT(co_located(Slot.ACTOR, Slot.TARGET)),
            ),
            narrative_stub=(
                "{actor} drops what they were doing and starts moving — calling "
                "in favors at every transit checkpoint to shave minutes off the "
                "route to {target}, knowing the minutes might matter."
            ),
            state_delta={
                "character.current_activity": "moving to reach kin in danger",
            },
            event_type="protective_intervention",
            changed_fields=("character.current_activity",),
            magnitude=0.52,
        ),
        Branch(
            label="Signal kin networks to converge on the target",
            conditions=has_symmetric_relationship_of_type("comrade"),
            narrative_stub=(
                "{actor} pushes a coded distress beacon through the kin network — "
                "the kind of signal that pulls three or four people toward "
                "{target} from different directions without coordination."
            ),
            state_delta={
                "character.current_activity": "coordinating kin response",
            },
            event_type="protective_intervention",
            changed_fields=("character.current_activity",),
            magnitude=0.41,
        ),
        Branch(
            label="Maintain vigil and wait for resolution",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} can't reach {target} in time, can't call who they would "
                "need to call — and stays close to a comm, monitoring channels, "
                "waiting for the news that will determine what comes next."
            ),
            state_delta={
                "character.current_activity": "waiting on news of kin",
                "entity_tags.add": ["distressed"],
            },
            event_type="protective_intervention",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.22,
        ),
    ),
)


CULTIVATE_INFORMANT = Template(
    id="cultivate_informant",
    priority=50,
    blurb="Patient intelligence work with a specific asset.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Cooldowns here are per-(actor, target) via target_slot=: handler A
    # contacting informant B must not block A from contacting informant C.
    # Contrast with EXTRACT_VENGEANCE's actor-global retaliation cooldown.
    package_gate=AND(
        has_tag("informant_handler"),
        OR(
            has_relationship_of_type("handler", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("asset", Slot.TARGET, Slot.ACTOR),
        ),
        since_last_event_at_least(
            "informant_contact",
            minimum_ticks=4,
            target_slot=Slot.TARGET,
        ),
        time_of_day_in("evening", "night"),
        NOT(has_ephemeral("under_active_pursuit")),
        NOT(has_ephemeral("grudge_active")),
    ),
    branches=(
        Branch(
            label="Press for material intel when trust is sufficient",
            # TODO: trust_at_least(2) is unreachable until resolver.py:177's
            # trust hydration TODO is resolved. WorldState.trust defaults
            # to 0, so this branch routes to the ALWAYS fallback today.
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                trust_at_least(2),
                since_last_event_at_least(
                    "intel_acquired",
                    minimum_ticks=6,
                    target_slot=Slot.TARGET,
                ),
            ),
            narrative_stub=(
                "{actor} meets {target} in a place that looks ordinary to "
                "anyone watching and asks the question they've been working "
                "toward for weeks. {target} doesn't answer immediately. Then "
                "they do."
            ),
            state_delta={
                "character.current_activity": "acquiring material intelligence",
                "entity_tags.add": ["intelligence_asset_active"],
            },
            event_type="intel_acquired",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.62,
        ),
        Branch(
            label="Routine contact to maintain the relationship",
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                trust_at_least(0),
            ),
            narrative_stub=(
                "{actor} sees {target} in passing — a transactional exchange "
                "with nothing to it, except that the exchange itself is the "
                "point. The relationship needs maintenance whether or not "
                "there is anything to report."
            ),
            state_delta={
                "character.current_activity": "maintaining informant contact",
            },
            event_type="informant_contact",
            changed_fields=("character.current_activity",),
            magnitude=0.28,
        ),
        Branch(
            label="Place a small overture from a distance",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} routes a small gift or unexpected courtesy to "
                "{target} through indirect channels — the kind of gesture "
                "that lands without obligation but accumulates over time "
                "into something the asset will eventually want to repay."
            ),
            state_delta={
                "character.current_activity": "courting an informant remotely",
            },
            event_type="informant_contact",
            changed_fields=("character.current_activity",),
            magnitude=0.18,
        ),
    ),
)


BUILTIN_TEMPLATES = (
    EVADE_PURSUERS,
    PROTECT_KIN,
    EXTRACT_VENGEANCE,
    HONOR_DEBT,
    PURSUE_GHOST_LEAD,
    CULTIVATE_INFORMANT,
    MAINTAIN_COVER,
)

"""Built-in Orrery behavior package catalog."""

from __future__ import annotations

from nexus.agents.orrery.substrate import (
    ALWAYS,
    AND,
    NOT,
    OR,
    Branch,
    Condition,
    DriveBand,
    ESTABLISHED_PARTNER_RELATIONSHIP_TYPES,
    PresentTargetPolicy,
    Slot,
    Template,
    can_move_publicly,
    co_located,
    count_co_located,
    direct_contact_is_dramatic,
    fame_at_or_above,
    fame_below,
    has_any_intimacy_suppressor,
    has_any_current_tag,
    has_any_pair_tag,
    has_any_status_at_or_above,
    has_any_tag,
    has_contact_of_kind,
    has_ephemeral,
    has_established_partner_co_located,
    has_inbound_pair_tag,
    has_location_class_destination,
    has_minimal_context,
    has_need_debt_at_or_above,
    has_pair_tag,
    has_pair_tag_to_current_location,
    has_relationship_of_type,
    has_symmetric_relationship_of_type,
    has_tag,
    has_travel_destination,
    count_recent_events_at_least,
    has_routine_anchor,
    in_location_class,
    is_constrained,
    is_hidden,
    is_in_transit,
    knows_recent_event,
    lacks_pair_tag,
    project_due,
    project_target_is,
    project_target_is_active,
    recent_event,
    relationship_is_asymmetric,
    relationship_is_mutual_warm,
    resources_at_or_above,
    resources_below,
    at_routine_anchor,
    away_from_routine_anchor,
    routine_anchor_due,
    routine_anchor_has_destination,
    since_last_event_at_least,
    time_of_day_in,
    travel_progress_at_or_above,
    travel_purpose_is,
    travel_risk_is,
    trust_at_least,
    trust_below,
    validate_mood_affinities,
    validate_no_fame_in_entry_gates,
    validate_no_mood_in_entry_gates,
    weather_is,
)


def _place_any(*classes: str) -> Condition:
    if not classes:
        raise ValueError("_place_any requires at least one place class")
    conditions = tuple(in_location_class(location_class) for location_class in classes)
    return conditions[0] if len(conditions) == 1 else OR(*conditions)


def _place_all(*classes: str) -> Condition:
    if not classes:
        raise ValueError("_place_all requires at least one place class")
    conditions = tuple(in_location_class(location_class) for location_class in classes)
    return conditions[0] if len(conditions) == 1 else AND(*conditions)


ROOTS_TRANSIT_PLACE = _place_all("subterranean", "transit")
SAFEHOUSE_PLACE = _place_any("haven")
URBAN_PUBLIC_FLOW_PLACE = _place_any(
    "urban_dense", "place_open", "transit", "commerce", "meeting"
)
URBAN_BROKERAGE_PLACE = _place_any("urban_dense", "commerce", "meeting")
REMEMBRANCE_PLACE = _place_any("tomb", "sacred")
TRANSIT_PLACE = _place_any("transit")
WORKPLACE_PLACE = _place_any(
    "administration", "craft", "military", "place_medical", "production"
)
WORKSITE_PLACE = _place_any("craft", "military", "production")

# Non-corporeal minds have no body to walk, train, provision, or tidy with.
# Mirrors NEED_IMMUNITY_TAGS in needs.py: embodied-inorganic forms (androids,
# constructs) keep full access to the physical mundane packages.
NON_CORPOREAL_TAGS = ("virtual", "digital_mind", "bodyform:non_corporeal")
ADMINISTRATION_PLACE = _place_any("administration")
PUBLIC_MEETING_PLACE = _place_any("meeting", "commerce", "place_open")
DWELLING_PLACE = _place_any("dwelling")
HOME_PLACE = AND(DWELLING_PLACE, has_pair_tag_to_current_location("resides_at"))
SAFE_LODGING_PLACE = _place_any("dwelling", "haven")
PUBLIC_DRINK_PLACE = _place_any("commerce", "entertainment", "meeting")
PUBLIC_WATER_PLACE = _place_any("water_source", "wilderness")
PUBLIC_DINING_PLACE = _place_any("commerce", "entertainment", "meeting", "production")
SOCIAL_VENUE_PLACE = _place_any("commerce", "entertainment", "meeting", "place_open")
INTIMATE_SOCIAL_PLACE = _place_any("entertainment", "meeting")
INTIMATE_SERVICES_PLACE = _place_any("commerce", "entertainment")
PRIVATE_PLACE = _place_any("dwelling", "place_restricted")


EVADE_PURSUERS = Template(
    id="evade_pursuers",
    priority=100,
    drive_band=DriveBand.CRISIS_CONSTRAINT,
    blurb="When the city is closing in.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        OR(
            has_inbound_pair_tag("hunting"),
            recent_event("compliance_alert", within_ticks=5, target_slot=Slot.ACTOR),
        ),
        NOT(is_constrained()),
        OR(
            ROOTS_TRANSIT_PLACE,
            has_contact_of_kind("lodging"),
            can_move_publicly(),
        ),
    ),
    branches=(
        Branch(
            label="Go to ground in flooded tunnels",
            conditions=AND(ROOTS_TRANSIT_PLACE, weather_is("rain")),
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
            label="Buy a discreet extraction",
            conditions=AND(
                fame_at_or_above("renowned"),
                resources_at_or_above("wealthy"),
            ),
            narrative_stub=(
                "{actor} knows their face does half the pursuers' work for "
                "them, so they pay for the kind of exit that never touches "
                "public flow: a closed vehicle, a bought route, a driver "
                "whose business is not remembering."
            ),
            state_delta={
                "character.current_activity": "buying a discreet extraction",
            },
            event_type="evade_pursuit",
            changed_fields=("character.current_activity",),
            magnitude=0.64,
        ),
        Branch(
            label="Reach a safe house through contacts",
            conditions=has_contact_of_kind("lodging"),
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
            # Self-awareness: blending into a crowd only works for actors
            # whose ambient detection radius is narrow. Renowned-or-better
            # actors cannot disappear into pedestrian flow; without funds
            # for an extraction they fall through to breaking line of sight.
            conditions=AND(can_move_publicly(), fame_below("renowned")),
            narrative_stub=(
                "{actor} joins the densest pedestrian current nearby, never "
                "stopping long enough to make a clean pattern."
            ),
            state_delta={"character.current_activity": "blending into public flow"},
            event_type="evade_pursuit",
            changed_fields=("character.current_activity",),
            magnitude=0.42,
        ),
        Branch(
            label="Break line of sight without a clean route",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} cannot rely on a clean public path, so they buy "
                "seconds instead: doors, stairwells, service gaps, and any "
                "angle that keeps the pursuit from becoming certain."
            ),
            state_delta={"character.current_activity": "breaking pursuit pattern"},
            event_type="evade_pursuit",
            changed_fields=("character.current_activity",),
            magnitude=0.28,
        ),
    ),
)


HIDE = Template(
    id="hide",
    priority=84,
    drive_band=DriveBand.CRISIS_CONSTRAINT,
    blurb="Steady-state concealment for people who are already living out of sight.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_minimal_context(),
        is_hidden(),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(is_constrained()),
        since_last_event_at_least("hideout_maintained", minimum_ticks=6),
        since_last_event_at_least("signal_exposure_reduced", minimum_ticks=6),
        since_last_event_at_least("counter_surveillance_sweep", minimum_ticks=6),
    ),
    branches=(
        # Stage-2 self-awareness (issue #282 worked example): concealment
        # escalates with the actor's own fame because a wide detection radius
        # makes laying low ineffective. Each escalation tier must also be
        # affordable; an actor who cannot pay for their tier falls through to
        # the cheaper measure below it. Obscure actors ride out concealment
        # with the lay-low maintenance branches further down.
        Branch(
            label="Erase the identity and vanish completely",
            conditions=AND(
                fame_at_or_above("legendary"),
                resources_at_or_above("magnate"),
            ),
            narrative_stub=(
                "{actor} is too widely known to be hidden by walls or "
                "habits, so they spend what almost no one can spend: the "
                "records, the debts, the face in the right databases — an "
                "identity dismantled piece by piece until there is nothing "
                "left to recognize."
            ),
            state_delta={
                "character.current_activity": "erasing their identity",
            },
            event_type="hideout_maintained",
            changed_fields=("character.current_activity",),
            magnitude=0.62,
        ),
        Branch(
            label="Relocate to safer ground",
            conditions=AND(
                fame_at_or_above("renowned"),
                resources_at_or_above("wealthy"),
            ),
            narrative_stub=(
                "{actor} accepts that a recognizable face cannot outlast "
                "the neighborhood that recognizes it, and pays for the "
                "quiet logistics of being somewhere else entirely before "
                "anyone thinks to look."
            ),
            state_delta={
                "character.current_activity": "relocating to safer ground",
            },
            event_type="hideout_maintained",
            changed_fields=("character.current_activity",),
            magnitude=0.52,
        ),
        Branch(
            label="Change the face they show the street",
            conditions=AND(
                fame_at_or_above("known"),
                resources_at_or_above("comfortable"),
            ),
            narrative_stub=(
                "{actor} is recognizable enough that habit alone will not "
                "protect them, so they spend on the cosmetic arithmetic of "
                "not being noticed: hair, clothes, gait, the small paid "
                "alterations that make a familiar face unfamiliar."
            ),
            state_delta={
                "character.current_activity": "altering their appearance",
            },
            event_type="hideout_maintained",
            changed_fields=("character.current_activity",),
            magnitude=0.44,
        ),
        Branch(
            label="Harden or sanitize a safehouse",
            conditions=AND(
                SAFEHOUSE_PLACE,
                OR(
                    has_contact_of_kind("lodging"),
                    has_any_current_tag(
                        "fixer",
                        "route_familiar",
                        "safehouse_operator",
                        "survivalist",
                    ),
                ),
            ),
            narrative_stub=(
                "{actor} spends the turn making the safe place safer: "
                "cleaning traces, changing habits, checking exits, and "
                "removing the small comforts that become evidence."
            ),
            state_delta={
                "character.current_activity": "hardening a safehouse",
            },
            event_type="hideout_maintained",
            changed_fields=("character.current_activity",),
            magnitude=0.40,
        ),
        Branch(
            label="Go dark and reduce signal exposure",
            conditions=OR(
                has_contact_of_kind("social"),
                has_any_current_tag(
                    "ghostprint_active",
                    "hacker",
                    "off_grid",
                    "paranoid",
                    "signal_operator",
                ),
            ),
            narrative_stub=(
                "{actor} trims their signal down to almost nothing — no "
                "unnecessary pings, no sentimental check-ins, no pattern "
                "that would let a watcher say yes, there."
            ),
            state_delta={
                "character.current_activity": "reducing signal exposure",
            },
            event_type="signal_exposure_reduced",
            changed_fields=("character.current_activity",),
            magnitude=0.36,
        ),
        Branch(
            label="Run a counter-surveillance sweep",
            conditions=OR(
                has_any_current_tag(
                    "combat_trained",
                    "hacker",
                    "informant_handler",
                    "paranoid",
                    "scout",
                    "surveillance_capable",
                ),
                recent_event(
                    "compliance_alert",
                    within_ticks=8,
                    target_slot=Slot.ACTOR,
                ),
            ),
            narrative_stub=(
                "{actor} checks whether anyone has learned the shape of their "
                "absence: doubled-back routes, watcher positions, unusual "
                "queries, and the tiny repetitions that turn hiding into a map."
            ),
            state_delta={
                "character.current_activity": "running counter-surveillance",
            },
            event_type="counter_surveillance_sweep",
            changed_fields=("character.current_activity",),
            magnitude=0.34,
        ),
        Branch(
            label="Shift a mobile route without surfacing",
            conditions=AND(
                OR(is_in_transit(), has_travel_destination()),
                has_any_current_tag(
                    "fugitive",
                    "route_familiar",
                    "travel_ready",
                    "wanted",
                ),
            ),
            narrative_stub=(
                "{actor} changes the route without making the change look like "
                "a change, letting timing and terrain do what panic would ruin."
            ),
            state_delta={
                "character.current_activity": "shifting concealed route",
            },
            event_type="hideout_maintained",
            changed_fields=("character.current_activity",),
            magnitude=0.30,
        ),
        Branch(
            label="Preserve the silence another day",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} does the unglamorous work of staying missing: small "
                "routines, smaller footprints, and the discipline not to reach "
                "toward the people who would make the silence easier to bear."
            ),
            state_delta={
                "character.current_activity": "preserving concealment",
            },
            event_type="hideout_maintained",
            changed_fields=("character.current_activity",),
            magnitude=0.22,
        ),
    ),
)


HONOR_DEBT = Template(
    id="honor_debt",
    priority=80,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Honor/debt pressure is a story obligation that may preempt ordinary "
        "maintenance when the relevant ledger is hot."
    ),
    blurb="A binding obligation surfaces from the blank years.",
    required_slots=(Slot.ACTOR,),
    package_gate=OR(
        has_ephemeral("debt_pulse_active"),
        recent_event("encoded_message", within_ticks=3, target_slot=Slot.ACTOR),
    ),
    branches=(
        Branch(
            label="Activate the Ghostprint Key at a sympathetic node",
            conditions=AND(has_tag("ghostprint_active"), ROOTS_TRANSIT_PLACE),
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
            conditions=has_contact_of_kind("social"),
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


UNCOVER_PAST = Template(
    id="uncover_past",
    priority=60,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Digging into one's own buried past is a long-arc motive with "
        "explicit clue pressure, so it can outrank routine maintenance."
    ),
    blurb="Fragments of the actor's own buried past demand investigation.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_tag("seeking_identity"),
        time_of_day_in("evening", "night"),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Revisit a place their body remembers",
            conditions=ROOTS_TRANSIT_PLACE,
            narrative_stub=(
                "{actor} works their way back to a place their body "
                "recognizes before memory can explain why — a doorway, a "
                "stairwell, a smell — and stands in it, waiting for the "
                "past to blink first."
            ),
            state_delta={"character.current_activity": "revisiting remembered ground"},
            event_type="pursue_identity_lead",
            changed_fields=("character.current_activity",),
            magnitude=0.64,
        ),
        Branch(
            label="Search the records for their own name",
            conditions=has_any_tag(
                "scholar",
                "researcher",
                "academic",
                "loremaster",
                "hacker",
                "investigator",
            ),
            narrative_stub=(
                "{actor} takes their questions to the records — whatever "
                "form this world keeps them in — and hunts for the entry "
                "that proves the person they used to be existed."
            ),
            state_delta={
                "character.current_activity": "searching records for their past"
            },
            event_type="pursue_identity_lead",
            changed_fields=("character.current_activity",),
            magnitude=0.57,
        ),
        Branch(
            label="Ask someone who trades in answers",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} finds someone who deals in other people's "
                "histories and leaves the exchange with one new question "
                "and one dangerous name."
            ),
            state_delta={
                "character.current_activity": "buying answers about their past"
            },
            event_type="pursue_identity_lead",
            changed_fields=("character.current_activity",),
            magnitude=0.44,
        ),
    ),
)


MAINTAIN_COVER = Template(
    id="maintain_cover",
    priority=0,
    drive_band=DriveBand.CRISIS_CONSTRAINT,
    drive_band_priority_exempt=True,
    priority_override_rationale=(
        "Public-cover upkeep is crisis/constraint-flavored, but it is "
        "intentionally a floor package that should not force routine needs or "
        "story obligations to justify outranking it."
    ),
    blurb="Specific public-cover maintenance, not a universal fallback.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_minimal_context(),
        NOT(is_constrained()),
        NOT(is_hidden()),
        NOT(is_in_transit()),
        OR(
            has_any_current_tag(
                "broker",
                "cover_identity",
                "fixer",
                "operative",
                "public_role",
                "undercover",
            ),
        ),
        URBAN_PUBLIC_FLOW_PLACE,
        since_last_event_at_least("maintain_cover", minimum_ticks=6),
    ),
    branches=(
        # Self-awareness inversion: a recognizable actor cannot maintain
        # cover by generating anonymous civilian noise — their cover IS the
        # public pattern people expect to see. Fame is unvalenced detection
        # radius; here visibility composes into an asset.
        Branch(
            label="Be seen exactly where they are expected",
            conditions=fame_at_or_above("renowned"),
            narrative_stub=(
                "{actor} cannot be nobody, so they are conspicuously, "
                "boringly themselves: the usual table, the usual hours, the "
                "usual complaints — a public pattern so consistent that "
                "nobody thinks to ask what it covers."
            ),
            state_delta={
                "character.current_activity": "performing the expected public pattern",
            },
            event_type="maintain_cover",
            changed_fields=("character.current_activity",),
            magnitude=0.14,
        ),
        Branch(
            label="Run a low-level courier job",
            conditions=AND(
                URBAN_PUBLIC_FLOW_PLACE,
                can_move_publicly(),
                fame_below("renowned"),
            ),
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
            label="Maintain a specific cover identity",
            conditions=has_any_current_tag(
                "cover_identity",
                "public_role",
                "undercover",
            ),
            narrative_stub=(
                "{actor} services the identity that keeps questions from "
                "forming: one believable errand, one ordinary exchange, one "
                "small proof that the mask has a life of its own."
            ),
            state_delta={"character.current_activity": "maintaining cover identity"},
            event_type="maintain_cover",
            changed_fields=("character.current_activity",),
            magnitude=0.14,
        ),
        Branch(
            label="Keep a public role legible",
            conditions=has_any_current_tag("broker", "fixer", "operative"),
            narrative_stub=(
                "{actor} keeps their visible role legible to the people who "
                "expect to see it — enough routine, enough responsiveness, "
                "enough plausible friction to look like a life."
            ),
            state_delta={"character.current_activity": "keeping public role legible"},
            event_type="maintain_cover",
            changed_fields=("character.current_activity",),
            magnitude=0.12,
        ),
        Branch(
            label="Drift through public space",
            conditions=AND(can_move_publicly(), fame_below("renowned")),
            narrative_stub=(
                "{actor} moves through public space at the pace of someone "
                "with somewhere to be, generating forgettable civilian noise."
            ),
            state_delta={"character.current_activity": "maintaining public cover"},
            event_type="maintain_cover",
            changed_fields=("character.current_activity",),
            magnitude=0.1,
        ),
        Branch(
            label="Keep the ledger plausible from a fixed post",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} makes no dramatic move. They answer what must be "
                "answered, neglect what can be neglected, and keep their "
                "visible life plausible without pretending to be free of it."
            ),
            state_delta={"character.current_activity": "maintaining fixed cover"},
            event_type="maintain_cover",
            changed_fields=("character.current_activity",),
            magnitude=0.08,
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
# Writer contract:
#
#   * Cross-actor state_delta keys (entity_tags_target.add/remove and narrow
#     target-directed pair-tag clears) are routed by convention to Slot.TARGET
#     by CommitOrreryTick. Define a state_delta TypedDict/dataclass if the
#     implicit-string convention grows past this small vocabulary.
#   * present_target_policy=STORYTELLER_PRESSURE allows a present TARGET only
#     as prompt-only scene pressure. Present ACTORs are still excluded, and
#     pressure drafts never commit state deltas or world events directly.
#   * Trust hydration reads entity_relationships_v.valence_magnitude. Keep
#     package thresholds on the -5..+5 enum-derived integer scale unless a
#     future package needs a separate normalized float at model-input time.
# ----------------------------------------------------------------------------


EXTRACT_VENGEANCE = Template(
    id="extract_vengeance",
    priority=90,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Active vengeance is a high-pressure identity project; left alone, it "
        "should interrupt ordinary life."
    ),
    blurb="A grudge ripens until the moment is right to settle it.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Cooldown is intentionally actor-global (no target_slot=): an active
    # grudge has a refractory period after any attempt regardless of
    # target — the actor needs to "calm down," not just back off a
    # specific target.
    #
    # Gate must cover both emitted retaliation events; otherwise a direct
    # execution branch can bypass the attempted-retaliation cooldown.
    package_gate=AND(
        has_ephemeral("grudge_active"),
        OR(
            has_symmetric_relationship_of_type("enemy"),
            has_symmetric_relationship_of_type("rival"),
            trust_below(-2),
        ),
        since_last_event_at_least("retaliation_attempted", minimum_ticks=8),
        since_last_event_at_least("retaliation_executed", minimum_ticks=8),
        since_last_event_at_least("hunt_declared", minimum_ticks=8),
        since_last_event_at_least("hunt_called_off", minimum_ticks=8),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        # Lifecycle terminal: a hunt that has produced nothing for a long
        # stretch goes cold, and the outbound `hunting` edge is released so
        # the quarry's suppressed social/routine bands can reopen. Without
        # an off-ramp, hunting is an absorbing state from the prey's side.
        Branch(
            label="Let the hunt go cold",
            # NOT co_located: a hunter who finally has access strikes (the
            # branch below), they do not shrug at the finish line. The
            # clear is subject-scoped: abandoning one's own hunt must not
            # release another hunter's live edge into the same target.
            conditions=AND(
                has_pair_tag("hunting"),
                NOT(co_located(Slot.ACTOR, Slot.TARGET)),
                since_last_event_at_least(
                    "hunt_declared", minimum_ticks=18, target_slot=Slot.TARGET
                ),
            ),
            narrative_stub=(
                "{actor} stops feeding the hunt for {target} — the watchers "
                "wander off, the standing questions expire — not forgiveness, "
                "just the quiet arithmetic of effort against a target who "
                "will not surface."
            ),
            state_delta={
                "character.current_activity": "letting a hunt go cold",
                "entity_pair_tags.clear_outbound": ["hunting"],
            },
            event_type="hunt_called_off",
            changed_fields=("character.current_activity", "entity_pair_tags"),
            magnitude=0.30,
            preemptive=True,
            scene_pressure_stub=(
                "{actor} has quietly stopped hunting {target}. If the scene "
                "touches it, show the pressure lifting — a tail that is no "
                "longer there — rather than an announcement."
            ),
        ),
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
            # The ACTOR's grudge_active (the tag this gate reads) is
            # digested by tag clearance: clear_on -> retaliation_executed.
            state_delta={
                "character.current_activity": "executing retaliation",
                "entity_tags.add": ["recently_violent"],
                "mood.set": {"mood": "restless"},
            },
            event_type="retaliation_executed",
            signal_event_type="threat_issued",
            changed_fields=(
                "character.current_activity",
                "entity_tags",
                "world_events",
            ),
            magnitude=0.85,
            mood_affinities={"restless": 2.0, "grim": 1.5},
            scene_pressure_stub=(
                "{actor}'s grudge is close enough to {target}'s current scene "
                "to become immediate pressure. Treat it as a possible threat, "
                "interruption, warning sign, or delayed consequence rather than "
                "an automatic attack."
            ),
        ),
        Branch(
            label="Surface a reputation attack in the right channels",
            conditions=AND(
                has_contact_of_kind("social"),
                URBAN_BROKERAGE_PLACE,
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
            signal_event_type="threat_issued",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.58,
            scene_pressure_stub=(
                "{actor} is trying to compromise {target}'s reputation through "
                "off-screen channels. If useful, let the current scene show a "
                "rumor, message, social consequence, or pressure wave instead "
                "of a direct state change."
            ),
        ),
        # The only writer of the `hunting` pair tag: vengeance without
        # access escalates into an open hunt, which arms the entire
        # predator/prey machinery (EVADE_PURSUERS, HIDE, WARN_ALLY,
        # PROTECT_KIN all consume the inbound edge). The off-ramp branch
        # above and PROTECT_KIN's protective clear are the release valves.
        Branch(
            label="Declare the hunt",
            conditions=AND(
                NOT(co_located(Slot.ACTOR, Slot.TARGET)),
                has_any_tag("vendetta_holder", "violent_history"),
                NOT(has_pair_tag("hunting")),
            ),
            narrative_stub=(
                "{actor} stops waiting for {target} to wander into reach and "
                "starts hunting in earnest — questions placed with the right "
                "people, routes watched, a price quietly attached to a "
                "location. The grudge acquires infrastructure."
            ),
            state_delta={
                "character.current_activity": "hunting a grudge target",
                "entity_pair_tags.add_outbound": ["hunting"],
            },
            event_type="hunt_declared",
            signal_event_type="threat_issued",
            changed_fields=(
                "character.current_activity",
                "entity_pair_tags",
                "world_events",
            ),
            magnitude=0.66,
            scene_pressure_stub=(
                "{actor} has begun actively hunting {target}. The scene may "
                "surface this as watchers, questions asked about {target}, "
                "or a warning reaching them — the hunt exists off-screen "
                "either way."
            ),
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
            scene_pressure_stub=(
                "{actor} is watching {target}'s current patterns from cover. "
                "This can surface as unease, surveillance traces, or a later "
                "setup, but {target}'s on-screen choices remain yours."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


PROTECT_KIN = Template(
    id="protect_kin",
    priority=95,
    drive_band=DriveBand.CRISIS_CONSTRAINT,
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
            has_inbound_pair_tag("hunting", slot=Slot.TARGET),
            has_ephemeral("wounded", slot=Slot.TARGET),
            recent_event(
                "threat_issued",
                within_ticks=4,
                target_slot=Slot.TARGET,
            ),
        ),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Physically intervene at the target's location",
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                has_inbound_pair_tag("hunting", slot=Slot.TARGET),
            ),
            narrative_stub=(
                "{actor} reaches {target} as the noose tightens — pulling them "
                "off the line of sight, into a service corridor whose layout "
                "{actor} has memorized for exactly this kind of moment."
            ),
            state_delta={
                "character.current_activity": "shielding kin from active threat",
                "entity_tags.add": ["recently_protective"],
                "entity_pair_tags_target.clear_inbound": ["hunting"],
            },
            event_type="protective_intervention",
            changed_fields=(
                "character.current_activity",
                "entity_tags",
                "world_events",
            ),
            magnitude=0.78,
            scene_pressure_stub=(
                "{actor} may be close enough to intervene around {target}'s "
                "current danger. Treat this as potential off-screen support or "
                "complication for the scene, not as an automatic rescue."
            ),
        ),
        Branch(
            label="Travel toward the target's last known location",
            conditions=AND(
                has_contact_of_kind("social"),
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
            scene_pressure_stub=(
                "{actor} is moving toward {target}'s current location because "
                "they believe the danger is real. You may foreshadow, delay, "
                "or ignore their arrival based on the active scene."
            ),
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
            scene_pressure_stub=(
                "{actor} has signaled a kin network around {target}. This can "
                "become outside help, cross-traffic, noise, or a looming option "
                "if it fits the live scene."
            ),
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
            scene_pressure_stub=(
                "{actor} is monitoring {target}'s danger from off-screen. This "
                "is emotional and logistical pressure, not a command to change "
                "what {target} does in the scene."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


SURVEIL = Template(
    id="surveil",
    priority=48,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Surveillance usually serves live threat or investigation arcs, so it "
        "can sit above routine and social maintenance."
    ),
    blurb="Watching from afar without turning observation into contact.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    package_gate=AND(
        has_minimal_context(),
        NOT(project_due("ready")),
        NOT(project_due("ready", project_type="recruit_ally")),
        NOT(project_due("ready", project_type="pursue_romance")),
        NOT(project_due("ready", project_type="court_patron")),
        NOT(project_due("ready", project_type="seek_redemption")),
        NOT(is_constrained()),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("grudge_active")),
        OR(
            is_hidden(),
            has_contact_of_kind("social"),
            has_any_current_tag(
                "broker",
                "hacker",
                "informant_handler",
                "intelligence_asset_active",
                "paranoid",
                "researcher",
                "signal_operator",
                "surveillance_capable",
            ),
            has_relationship_of_type("captor", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("guardian", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("handler", Slot.ACTOR, Slot.TARGET),
            trust_below(-2),
            knows_recent_event(
                "threat_issued", within_ticks=8, target_slot=Slot.TARGET
            ),
        ),
        since_last_event_at_least(
            "surveillance_performed", minimum_ticks=6, target_slot=Slot.TARGET
        ),
        since_last_event_at_least(
            "intel_reviewed", minimum_ticks=6, target_slot=Slot.TARGET
        ),
    ),
    branches=(
        Branch(
            label="Intercept signal traffic",
            conditions=has_any_current_tag(
                "ghostprint_active",
                "hacker",
                "researcher",
                "signal_operator",
                "surveillance_capable",
            ),
            narrative_stub=(
                "{actor} watches the signal field around {target}: not the "
                "person directly, not yet, but the traffic and absences that "
                "make a life legible to someone patient enough."
            ),
            state_delta={
                "character.current_activity": "intercepting target signals",
            },
            event_type="surveillance_performed",
            signal_event_type="compliance_alert",
            changed_fields=("character.current_activity",),
            magnitude=0.48,
            scene_pressure_stub=(
                "{actor} may be reading signal traffic around {target}'s "
                "current scene. Use it as optional pressure or atmosphere, "
                "not as a canonical breach unless the scene earns it."
            ),
        ),
        Branch(
            label="Keep tabs from a distance",
            conditions=OR(is_hidden(), trust_below(-2)),
            narrative_stub=(
                "{actor} keeps tabs on {target} without touching the line "
                "between them: a pattern noticed, a channel checked, a "
                "small confirmation that does not become contact."
            ),
            state_delta={
                "character.current_activity": "keeping tabs from a distance",
            },
            event_type="surveillance_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.44,
            scene_pressure_stub=(
                "{actor} is keeping tabs on {target} from off-screen. Treat "
                "this as possible pressure, unease, traces, or delayed setup; "
                "do not turn it into automatic contact or control of "
                "{target}'s choices."
            ),
        ),
        Branch(
            label="Collect a proxy watcher report",
            conditions=OR(
                has_contact_of_kind("social"),
                has_any_current_tag(
                    "broker",
                    "fixer",
                    "informant_handler",
                ),
            ),
            narrative_stub=(
                "{actor} does not go near {target}. They let someone else "
                "look, then read the report for what the watcher understood "
                "and what they were too ordinary to notice."
            ),
            state_delta={
                "character.current_activity": "collecting a proxy watcher report",
            },
            event_type="surveillance_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.38,
            scene_pressure_stub=(
                "{actor} has someone off-screen watching for signs around "
                "{target}. This can surface as a watcher, rumor, false alarm, "
                "or nothing at all."
            ),
        ),
        Branch(
            label="Review accumulated intel",
            conditions=has_any_current_tag(
                "academic",
                "intelligence_asset_active",
                "paranoid",
                "researcher",
            ),
            narrative_stub=(
                "{actor} stops gathering and starts reading: old logs, "
                "half-useful reports, fragments whose meaning only appears "
                "after the same question has been asked too many times."
            ),
            state_delta={
                "character.current_activity": "reviewing accumulated intel",
            },
            event_type="intel_reviewed",
            changed_fields=("character.current_activity",),
            magnitude=0.34,
            scene_pressure_stub=(
                "{actor} is reviewing accumulated intel related to {target}. "
                "If useful, let the scene feel watched or anticipated; the "
                "review itself does not force new facts into canon."
            ),
        ),
        Branch(
            label="Follow the public pattern",
            conditions=can_move_publicly(slot=Slot.TARGET),
            narrative_stub=(
                "{actor} follows the public shape of {target}'s life: where "
                "they appear, what routes repeat, which absences look chosen "
                "and which look imposed."
            ),
            state_delta={
                "character.current_activity": "following target public pattern",
            },
            event_type="surveillance_performed",
            signal_event_type="compliance_alert",
            changed_fields=("character.current_activity",),
            magnitude=0.30,
            scene_pressure_stub=(
                "{actor} may have mapped the public pattern around {target}. "
                "Use this only as Storyteller-controlled scene pressure or a "
                "future setup."
            ),
        ),
        Branch(
            label="Keep the target in view without contact",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} keeps {target} in view at the lowest useful "
                "resolution, choosing continued uncertainty over the kind of "
                "move that would make the watching visible."
            ),
            state_delta={
                "character.current_activity": "surveilling without contact",
            },
            event_type="surveillance_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.24,
            scene_pressure_stub=(
                "{actor} is watching around {target} but has not made contact. "
                "The Storyteller may adapt, delay, ignore, or incorporate that "
                "pressure without letting Orrery decide what {target} does."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


ACT_ON_INTEL = Template(
    id="act_on_intel",
    priority=52,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Spending accumulated surveillance is a deliberate project move that "
        "outranks continuing to watch (SURVEIL, 48): intel hoarded forever "
        "is the dominance pathology this package exists to break."
    ),
    blurb="Watching turns into acting: accumulated intel gets spent.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Entry demands a real stockpile: three surveillance passes on this
    # specific target inside the hydration window. The long per-target
    # cooldown makes acting rare relative to watching — watch, watch,
    # watch, act.
    package_gate=AND(
        count_recent_events_at_least(
            "surveillance_performed",
            within_ticks=25,
            min_count=3,
            target_slot=Slot.TARGET,
        ),
        since_last_event_at_least(
            "intel_acted_on", minimum_ticks=12, target_slot=Slot.TARGET
        ),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(is_constrained()),
    ),
    branches=(
        Branch(
            label="Sell the dossier",
            conditions=OR(has_contact_of_kind("social"), URBAN_BROKERAGE_PLACE),
            narrative_stub=(
                "{actor} packages what watching {target} has taught them — "
                "patterns, contacts, weaknesses — and trades it to someone "
                "who pays in favors or coin. The knowledge stops being "
                "private the moment it changes hands."
            ),
            state_delta={
                "character.current_activity": "selling gathered intelligence",
            },
            event_type="intel_acted_on",
            signal_event_type="compliance_alert",
            changed_fields=("character.current_activity", "world_events"),
            magnitude=0.62,
            scene_pressure_stub=(
                "{actor} has sold intelligence about {target}. The scene may "
                "surface this as {target} noticing new attention, a contact "
                "warning them, or consequences arriving from a third party."
            ),
        ),
        Branch(
            label="Confront the subject with what they know",
            conditions=co_located(Slot.ACTOR, Slot.TARGET),
            narrative_stub=(
                "{actor} stops pretending not to watch and puts what they "
                "know in front of {target} — names, times, patterns — to "
                "see what the knowledge is worth when spent face to face."
            ),
            state_delta={
                "character.current_activity": "confronting a surveilled subject",
            },
            event_type="intel_acted_on",
            signal_event_type="threat_issued",
            changed_fields=("character.current_activity", "world_events"),
            magnitude=0.58,
            scene_pressure_stub=(
                "{actor} is confronting {target} with gathered intelligence. "
                "Treat as charged pressure the scene can play as threat, "
                "negotiation, or revelation."
            ),
        ),
        Branch(
            label="File it and keep the watch alive",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} consolidates what watching {target} has produced — "
                "cross-checking, indexing, pruning dead leads — turning "
                "scattered observation into something that could be used "
                "on short notice."
            ),
            state_delta={
                "character.current_activity": "consolidating intelligence",
            },
            event_type="intel_acted_on",
            changed_fields=("character.current_activity",),
            magnitude=0.30,
            scene_pressure_stub=(
                "{actor} is quietly consolidating what they know about "
                "{target}. Background pressure only; nothing reaches "
                "{target} this tick."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


CULTIVATE_INFORMANT = Template(
    id="cultivate_informant",
    priority=50,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Informant cultivation is relationship-shaped, but it serves an active "
        "project rather than ordinary affiliation."
    ),
    blurb="Patient intelligence work with a specific asset.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Cooldowns here are per-(actor, target) via target_slot=: handler A
    # contacting informant B must not block A from contacting informant C.
    # Contrast with EXTRACT_VENGEANCE's actor-global retaliation cooldown.
    #
    # Gate must cover both emitted contact events: material intel and routine
    # contact are different event types, but both should pace this package.
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
        since_last_event_at_least(
            "intel_acquired",
            minimum_ticks=4,
            target_slot=Slot.TARGET,
        ),
        time_of_day_in("evening", "night"),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("grudge_active")),
    ),
    branches=(
        Branch(
            label="Press for material intel when trust is sufficient",
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
            scene_pressure_stub=(
                "{actor} may be trying to extract material intel from {target} "
                "while {target} is in the current scene. Use it only if it "
                "creates a believable opening, signal, or complication."
            ),
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
            scene_pressure_stub=(
                "{actor} is maintaining contact with {target} through a subtle "
                "off-screen channel. It can surface as a message, glance, coded "
                "exchange, or be deferred."
            ),
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
            signal_event_type="encoded_message",
            changed_fields=("character.current_activity",),
            magnitude=0.18,
            scene_pressure_stub=(
                "{actor} has placed a small indirect overture for {target}. "
                "Treat it as optional atmosphere or a hook the Storyteller can "
                "choose to pick up."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


# ----------------------------------------------------------------------------
# Round 2 expansion (universal care + maintenance + contact quartet)
#
# Eight templates drafted by the frontier-model conversation partner in
# temp/orrery/orrery_package_contributions_round2.md, integrated here with
# the divergences documented below. Authoring intent: universal shape with
# culturally-specific branches — the same gate fires in fantasy, cyberpunk,
# contemporary, or pigeon-dating-sim contexts; tag-discriminated branches
# express the cultural specifics.
#
# Deliberate divergences from the contribution draft:
#
#   * CONSULT_RIVAL gate: the contribution had `has_ephemeral("grudge_active")`
#     in the shared-circumstance OR clause AND `NOT(has_ephemeral("grudge_active"))`
#     in the same gate's AND list — a logical contradiction. The NOT is the
#     intended exclusion (EXTRACT_VENGEANCE owns grudge-active space; priority
#     90 vs CONSULT_RIVAL's 35 ensures vengeance fires first anyway, but the
#     NOT is the documented safety belt). The contradictory OR-arm is removed
#     here.
#
#   * KEEP_VIGIL gate: the contribution used `has_tag("captive", slot=TARGET)`
#     for the captive-vigil case. The migration seeds `captive` as ephemeral
#     (captivity is a condition, not an identity — escape/freedom/death ends
#     it), so this gate uses `has_ephemeral` instead. Branch prose unchanged.
#
#   * TEND_WOUNDED's magical-healing branch clears `wounded` from the target
#     via `entity_tags_target.remove`, matching PROTECT_KIN's target-directed
#     clear of inbound `hunting` pair-tags.
#
#   * `grieving` / `dying` / `unconscious` ephemerals are seeded with
#     event-based clearance pointing at `mourning_completed` / `death_recorded`
#     / `regained_consciousness`. MOURN_LOSS emits `mourning_completed`
#     itself via its preemptive "Lay the grief down" branch — grief is a
#     resolver-owned lifecycle. `death_recorded` and `regained_consciousness`
#     remain externally authored (CommitOrreryTick or future world-state
#     systems); KEEP_VIGIL never emits them.
# ----------------------------------------------------------------------------


# Section A — Universal care behaviors


TEND_WOUNDED = Template(
    id="tend_wounded",
    priority=88,
    drive_band=DriveBand.CRISIS_CONSTRAINT,
    blurb="A wounded body pulls the actor toward the small work of mending.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Gate must cover both emitted care events: healing the wound is higher
    # impact than tending it, but both should reset the package's cadence.
    package_gate=AND(
        has_ephemeral("wounded", slot=Slot.TARGET),
        co_located(Slot.ACTOR, Slot.TARGET),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_inbound_pair_tag("hunting", slot=Slot.TARGET)),
        since_last_event_at_least(
            "tended_wound", minimum_ticks=2, target_slot=Slot.TARGET
        ),
        since_last_event_at_least(
            "wound_healed", minimum_ticks=2, target_slot=Slot.TARGET
        ),
    ),
    branches=(
        Branch(
            label="Channel restorative power through hands and voice",
            conditions=has_tag("magical_healing"),
            narrative_stub=(
                "{actor} kneels beside {target} and places hands where the "
                "damage lives. Something passes between them — a quiet "
                "exchange of warmth and pain — and the body begins to "
                "remember how to be whole."
            ),
            state_delta={
                "character.current_activity": "channeling restorative power",
                "entity_tags_target.remove": ["wounded"],
                "entity_tags.add": ["recently_drained"],
            },
            event_type="wound_healed",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.74,
            scene_pressure_stub=(
                "{actor} may be close enough to attempt restorative work on "
                "{target}'s wound in the active scene. Treat as offered help "
                "the scene can accept, defer, or complicate, not as automatic "
                "healing."
            ),
        ),
        Branch(
            label="Work the wound with trained hands",
            conditions=has_any_tag("surgical_training", "medical_skill"),
            narrative_stub=(
                "{actor} cleans the wound by feel, finds what needs to be "
                "found, and does the work the body cannot do for itself. "
                "{target} watches the ceiling and counts something silently."
            ),
            state_delta={
                "character.current_activity": "providing skilled medical care",
                "entity_tags_target.remove": ["wounded"],
                "entity_tags_target.add": ["recently_tended"],
            },
            event_type="tended_wound",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.58,
            scene_pressure_stub=(
                "{actor} is moving to provide skilled medical care to "
                "{target}. The scene may show this as a quiet competent "
                "interruption, a wait for stabilization, or a beat of "
                "trust between them."
            ),
        ),
        Branch(
            label="Apply what first-aid the moment allows",
            conditions=has_tag("first_aid_trained"),
            narrative_stub=(
                "{actor} works from memory — pressure here, elevation there, "
                "the things that buy time when time is the thing you need. "
                "It won't be enough on its own, but it's enough for now."
            ),
            state_delta={
                "character.current_activity": "applying field first aid",
                "entity_tags_target.add": ["recently_tended"],
            },
            event_type="tended_wound",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.42,
            scene_pressure_stub=(
                "{actor} has practical first-aid training and is at "
                "{target}'s side. Treat as a stabilizing presence the scene "
                "can use without granting full recovery."
            ),
        ),
        Branch(
            label="Stay with the wound and do what can be done",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} has no real skill for this. They press a cloth "
                "where there is bleeding and speak softly so {target} has "
                "a voice to follow back from wherever the body has gone."
            ),
            state_delta={
                "character.current_activity": "keeping watch over the wounded",
            },
            event_type="tended_wound",
            changed_fields=("character.current_activity",),
            magnitude=0.24,
            scene_pressure_stub=(
                "{actor} is present at {target}'s side without medical "
                "ability. Use this as accompaniment and witness — not as "
                "intervention."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


MOURN_LOSS = Template(
    id="mourn_loss",
    priority=25,
    drive_band=DriveBand.AFFILIATION,
    priority_override_rationale=(
        "Fresh grief suppresses ordinary social, intimacy, and routine loops; "
        "it should beat low-grade bodily maintenance."
    ),
    blurb="A loss settles into the body across many quiet days.",
    required_slots=(Slot.ACTOR,),
    # The mourning_completed cooldown paces back-to-back griefs: completion
    # clears `grieving`, so a fresh loss landing immediately afterward
    # should not be laid down again within the same handful of ticks.
    package_gate=AND(
        has_ephemeral("grieving"),
        since_last_event_at_least("mourning_act", minimum_ticks=3),
        since_last_event_at_least("mourning_completed", minimum_ticks=8),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        # Lifecycle terminal: enough mourning acts inside the hydration
        # window means the grief has been worked, and the completion event
        # lets the tag-clearance machinery digest `grieving`
        # (clear_on -> mourning_completed). Without this branch nothing
        # ever emits mourning_completed and grief is an absorbing state
        # that suppresses the actor's entire routine/social band
        # indefinitely. Preemptive so stochastic branch sampling cannot
        # keep re-selecting a flavor branch past the threshold.
        Branch(
            label="Lay the grief down",
            conditions=count_recent_events_at_least(
                "mourning_act", within_ticks=30, min_count=4
            ),
            narrative_stub=(
                "{actor} reaches for the grief out of habit and finds it "
                "has changed shape — still there, but carried now rather "
                "than carrying them. Whatever small act marks an ending in "
                "this world, {actor} performs it, and lets the day be an "
                "ordinary day."
            ),
            state_delta={
                "character.current_activity": "laying a long grief down",
            },
            event_type="mourning_completed",
            changed_fields=("character.current_activity",),
            magnitude=0.34,
            preemptive=True,
        ),
        Branch(
            label="Visit the place of remembrance",
            conditions=REMEMBRANCE_PLACE,
            narrative_stub=(
                "{actor} returns to the place where the dead are kept — "
                "stone, name, photograph, marker, whatever this world has "
                "made for the purpose — and stands long enough to be still "
                "and remember, before going back to the work of being alive."
            ),
            state_delta={
                "character.current_activity": "tending the dead",
            },
            event_type="mourning_act",
            changed_fields=("character.current_activity",),
            magnitude=0.42,
        ),
        Branch(
            label="Sit with others who carry the same loss",
            conditions=count_co_located(1, with_ephemeral="grieving"),
            narrative_stub=(
                "{actor} finds the others who knew the dead and sits with "
                "them — wordlessly, mostly. The presence of someone else "
                "who is also not over it makes the grief feel less like "
                "evidence of personal failure."
            ),
            state_delta={
                "character.current_activity": "gathering with co-mourners",
            },
            event_type="mourning_act",
            changed_fields=("character.current_activity",),
            magnitude=0.38,
        ),
        Branch(
            label="Pour the loss into the day's work",
            conditions=has_any_tag(
                "musician",
                "writer",
                "artisan",
                "scholar",
                "arcane_caster",
                "soldier",
                "keeps_shop",
                "domestic_role",
            ),
            narrative_stub=(
                "{actor} returns to their work — the thing the loss hasn't "
                "taken — and does it with the dead person sitting somewhere "
                "just behind them, watching the work with the particular "
                "silence the dead have."
            ),
            state_delta={
                "character.current_activity": "working through grief",
            },
            event_type="mourning_act",
            changed_fields=("character.current_activity",),
            magnitude=0.28,
        ),
        Branch(
            label="Carry the weight in private",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} goes through the day's motions with the loss "
                "settled inside them like a second heartbeat — not louder "
                "than the day, just underneath it, the way these things "
                "tend to be once the first weeks are past."
            ),
            state_delta={
                "character.current_activity": "carrying private grief",
            },
            event_type="mourning_act",
            changed_fields=("character.current_activity",),
            magnitude=0.14,
        ),
    ),
)


KEEP_VIGIL = Template(
    id="keep_vigil",
    priority=50,
    drive_band=DriveBand.AFFILIATION,
    priority_override_rationale=(
        "Vigil is affiliation under acute pressure, so it can outrank ordinary "
        "maintenance while a target is wounded or dying."
    ),
    blurb="The actor remains present through a slow, uncertain hour.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Divergence: `captive` is ephemeral (per migration 027), so the captive
    # case uses has_ephemeral rather than the draft's has_tag.
    package_gate=AND(
        co_located(Slot.ACTOR, Slot.TARGET),
        OR(
            has_ephemeral("wounded", slot=Slot.TARGET),
            has_ephemeral("dying", slot=Slot.TARGET),
            has_ephemeral("unconscious", slot=Slot.TARGET),
            has_ephemeral("captive", slot=Slot.TARGET),
        ),
        OR(
            has_relationship_of_type("family"),
            has_relationship_of_type("romantic"),
            has_relationship_of_type("chosen_kin"),
            has_relationship_of_type("comrade"),
            has_relationship_of_type("ward"),
            has_relationship_of_type("guardian"),
            has_relationship_of_type("captor"),
        ),
        since_last_event_at_least("vigil_held", minimum_ticks=2),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Maintain prayerful or meditative presence",
            conditions=has_any_tag("devout", "contemplative", "ritual_practitioner"),
            narrative_stub=(
                "{actor} sits beside {target} with hands quiet, breathing "
                "matched to whatever rhythm {target}'s body is still "
                "finding. The prayers — if they are prayers — are not for "
                "any audience but for the work of staying."
            ),
            state_delta={
                "character.current_activity": "holding meditative vigil",
                "entity_tags.add": ["at_vigil"],
            },
            event_type="vigil_held",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.46,
            scene_pressure_stub=(
                "{actor} is keeping a contemplative vigil over {target}. "
                "Use this as an emotional anchor in the scene, not an "
                "active intervention."
            ),
        ),
        Branch(
            label="Speak softly through the long hours",
            conditions=has_ephemeral("unconscious", slot=Slot.TARGET),
            narrative_stub=(
                "{actor} tells {target} small things — what the light is "
                "doing outside, what the others said today, the kind of "
                "stories one tells someone who may or may not be hearing — "
                "in the belief that whatever can be reached should be reached."
            ),
            state_delta={
                "character.current_activity": "speaking through the long hours",
                "entity_tags.add": ["at_vigil"],
            },
            event_type="vigil_held",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.38,
            scene_pressure_stub=(
                "{actor} is speaking to an unresponsive {target} through "
                "a long stretch. Treat as audible presence the scene can "
                "thread through quieter moments."
            ),
        ),
        Branch(
            label="Stand watch with attention but without intervention",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} stays. Not doing anything — that's the point of "
                "being here. {target} is alone with whatever is happening "
                "to them, and {actor} is the witness who makes that "
                "aloneness less complete."
            ),
            state_delta={
                "character.current_activity": "standing vigil",
                "entity_tags.add": ["at_vigil"],
            },
            event_type="vigil_held",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.32,
            scene_pressure_stub=(
                "{actor} is keeping silent vigil over {target}. Use this "
                "as ambient presence — a witness who shapes the scene by "
                "being there, not by acting."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


# Section B — Maintenance of self


ROUTINE_COMMUTE = Template(
    id="routine_commute",
    priority=26,
    drive_band=DriveBand.ANCHORED_ROUTINE,
    priority_override_rationale=(
        "Commute resolves where a routine-bound actor should be before nearby "
        "maintenance packages pick a place-shaped branch."
    ),
    blurb="Ordinary home/work movement from explicit routine anchors.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_minimal_context(),
        NOT(is_constrained()),
        NOT(is_in_transit()),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("wounded")),
        NOT(has_ephemeral("grieving")),
        OR(
            AND(
                has_routine_anchor("work"),
                routine_anchor_due("work"),
                away_from_routine_anchor("work"),
            ),
            AND(
                has_routine_anchor("home"),
                routine_anchor_due("home"),
                away_from_routine_anchor("home"),
            ),
        ),
    ),
    branches=(
        Branch(
            label="Commute to the scheduled workplace",
            conditions=AND(
                has_routine_anchor("work"),
                routine_anchor_due("work"),
                away_from_routine_anchor("work"),
                routine_anchor_has_destination("work"),
            ),
            narrative_stub=(
                "{actor} follows the ordinary route toward work: not a quest, "
                "not a crisis, just the daily movement that keeps a normal "
                "life legible."
            ),
            state_delta={
                "character.current_activity": "commuting to work",
                "travel.start": {
                    "destination_anchor": "work",
                    "mode": "mixed",
                    "initial_progress": 0.05,
                },
            },
            event_type="travel_departed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.status",
                "character_travel_states.progress_ratio",
            ),
            magnitude=0.16,
        ),
        Branch(
            label="Commute home after the day's obligations",
            conditions=AND(
                has_routine_anchor("home"),
                routine_anchor_due("home"),
                away_from_routine_anchor("home"),
                routine_anchor_has_destination("home"),
            ),
            narrative_stub=(
                "{actor} turns toward home with the unremarkable certainty of "
                "someone whose day has a next place."
            ),
            state_delta={
                "character.current_activity": "commuting home",
                "travel.start": {
                    "destination_anchor": "home",
                    "mode": "mixed",
                    "initial_progress": 0.05,
                },
            },
            event_type="travel_departed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.status",
                "character_travel_states.progress_ratio",
            ),
            magnitude=0.14,
        ),
        Branch(
            label="Recheck routine before moving",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} pauses at the edge of routine and checks the "
                "ordinary facts before moving: where they are, where the "
                "day says they should be, and whether the next leg is real."
            ),
            state_delta={
                "character.current_activity": "checking routine timing",
            },
            event_type="travel_prepared",
            changed_fields=("character.current_activity",),
            magnitude=0.04,
        ),
    ),
)


TRAVEL = Template(
    id="travel",
    priority=21,
    drive_band=DriveBand.ANCHORED_ROUTINE,
    blurb=(
        "A character moves between meaningful places without pretending the "
        "road is a room."
    ),
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        OR(is_in_transit(), has_travel_destination()),
        NOT(has_ephemeral("wounded")),
        NOT(has_ephemeral("grieving")),
    ),
    branches=(
        Branch(
            label="Arrive where people can be encountered",
            conditions=AND(
                is_in_transit(),
                travel_progress_at_or_above(0.95),
                travel_purpose_is("socialize"),
            ),
            narrative_stub=(
                "{actor} reaches the place they picked because other people "
                "would be there. The route ends, and the social possibility "
                "becomes immediate rather than theoretical."
            ),
            state_delta={
                "character.current_activity": "arriving where people gather",
                "travel.arrive": True,
            },
            event_type="travel_arrived",
            changed_fields=(
                "character.current_location",
                "character.current_activity",
                "character_travel_states.status",
            ),
            magnitude=0.36,
        ),
        Branch(
            label="Arrive at the planned destination",
            conditions=AND(is_in_transit(), travel_progress_at_or_above(0.95)),
            narrative_stub=(
                "{actor} reaches the destination at last. The route drops "
                "away behind them into the ordinary unreliability of maps, "
                "and the place ahead becomes immediate."
            ),
            state_delta={
                "character.current_activity": "arriving at destination",
                "travel.arrive": True,
            },
            event_type="travel_arrived",
            changed_fields=(
                "character.current_location",
                "character.current_activity",
                "character_travel_states.status",
            ),
            magnitude=0.34,
        ),
        Branch(
            label="Lose time to bad conditions or route friction",
            conditions=AND(
                is_in_transit(),
                OR(
                    travel_risk_is("high", "extreme"),
                    weather_is("rain", "snow", "fog"),
                ),
            ),
            narrative_stub=(
                "{actor} loses time to the route itself — weather, traffic, "
                "closed access, or the thousand small refusals a city can "
                "make when someone is trying to cross it."
            ),
            state_delta={
                "character.current_activity": "delayed in transit",
                "travel.delay": {"risk": "moderate"},
            },
            event_type="travel_delayed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.risk",
            ),
            magnitude=0.24,
        ),
        Branch(
            label="Make steady progress along the route",
            conditions=is_in_transit(),
            narrative_stub=(
                "{actor} keeps moving: transfers, crossings, service "
                "corridors, streets whose names matter less than the fact "
                "that each one puts the destination a little closer."
            ),
            state_delta={
                "character.current_activity": "traveling toward destination",
                "travel.advance": {"progress_delta": 0.35},
            },
            event_type="travel_progressed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.progress_ratio",
            ),
            magnitude=0.18,
        ),
        # Self-awareness route styles: the actor's own wealth and fame shape
        # HOW they depart before the generic departure logic applies. Wealth
        # substitutes for preparation (a charter is bought, not packed);
        # fame forces recognizable travelers off public flow onto covert
        # routings, which still demand real preparation.
        Branch(
            label="Charter private transport",
            conditions=AND(
                has_travel_destination(),
                NOT(is_in_transit()),
                resources_at_or_above("wealthy"),
            ),
            narrative_stub=(
                "{actor} does not queue, transfer, or wait. Money turns the "
                "journey into a closed door and a window: a private vehicle, "
                "a paid schedule, a route that exists because they asked "
                "for it."
            ),
            state_delta={
                "character.current_activity": "departing by chartered transport",
                "travel.start": {"mode": "vehicle", "initial_progress": 0.05},
            },
            event_type="travel_departed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.status",
                "character_travel_states.progress_ratio",
            ),
            magnitude=0.30,
        ),
        Branch(
            label="Slip out along covert routes",
            conditions=AND(
                has_travel_destination(),
                NOT(is_in_transit()),
                fame_at_or_above("renowned"),
                OR(
                    has_tag("travel_ready"),
                    has_tag("travel_provisioned"),
                    has_tag("route_familiar"),
                ),
            ),
            narrative_stub=(
                "{actor} cannot ride public flow without being a sighting, "
                "so the route runs through the city's blind spots: service "
                "levels, freight corridors, the hours and angles where a "
                "recognizable face passes unwitnessed."
            ),
            state_delta={
                "character.current_activity": "departing along covert routes",
                "travel.start": {"mode": "covert", "initial_progress": 0.05},
            },
            event_type="travel_departed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.status",
                "character_travel_states.progress_ratio",
            ),
            magnitude=0.32,
        ),
        Branch(
            label="Depart toward the planned destination",
            conditions=AND(
                has_travel_destination(),
                NOT(is_in_transit()),
                OR(
                    has_tag("travel_ready"),
                    has_tag("travel_provisioned"),
                    has_tag("route_familiar"),
                    TRANSIT_PLACE,
                ),
            ),
            narrative_stub=(
                "{actor} starts the journey with enough of a route in mind "
                "to make the first leg real. The exact path can change; the "
                "destination no longer can."
            ),
            state_delta={
                "character.current_activity": "departing toward destination",
                "travel.start": {"mode": "mixed", "initial_progress": 0.05},
            },
            event_type="travel_departed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.status",
                "character_travel_states.progress_ratio",
            ),
            magnitude=0.28,
        ),
        Branch(
            label="Prepare the journey rather than starting badly",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} does not start badly. They check timing, supplies, "
                "weather, access, and the parts of the route that might "
                "betray them before they have earned the right to improvise."
            ),
            state_delta={
                "character.current_activity": "preparing route and supplies",
                "entity_tags.add": ["travel_ready"],
            },
            event_type="travel_prepared",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.12,
        ),
    ),
)


WORK = Template(
    id="work",
    priority=14,
    drive_band=DriveBand.ANCHORED_ROUTINE,
    blurb=(
        "The recurring work that keeps a life, household, or organization "
        "functioning."
    ),
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        OR(
            AND(
                has_routine_anchor("work"),
                routine_anchor_due("work"),
                at_routine_anchor("work"),
            ),
            has_tag("work_obligation"),
            has_any_tag("domestic_role", "cares_for_household", "field_worker"),
        ),
        NOT(is_in_transit()),
        since_last_event_at_least("work_performed", minimum_ticks=4),
        since_last_event_at_least("household_work_performed", minimum_ticks=4),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("wounded")),
        NOT(has_ephemeral("grieving")),
    ),
    branches=(
        # Self-awareness: the actor's own wealth tier shapes what "work"
        # means before role or place do. Destitution makes work a matter of
        # survival; magnate-tier wealth makes it a matter of direction.
        Branch(
            label="Take whatever paying work the day offers",
            conditions=resources_below("poor"),
            narrative_stub=(
                "{actor} cannot afford the luxury of work that matches who "
                "they are. They take what the day pays for — hauling, "
                "queueing, standing in for someone luckier — and count the "
                "result in meals, not meaning."
            ),
            state_delta={
                "character.current_activity": "scraping together day labor",
            },
            event_type="work_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.20,
        ),
        Branch(
            label="Direct the work rather than perform it",
            conditions=resources_at_or_above("wealthy"),
            narrative_stub=(
                "{actor} does not stand a shift; they decide what the "
                "shifts are for. An hour of instructions, approvals, and "
                "quiet corrections moves more value than a day at any "
                "counter would."
            ),
            state_delta={
                "character.current_activity": "directing the work of others",
            },
            event_type="work_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.16,
        ),
        Branch(
            label="Work a public-facing shift",
            conditions=OR(
                WORKPLACE_PLACE,
                in_location_class("commerce"),
                has_any_tag("keeps_shop", "merchant", "innkeeper", "trader"),
            ),
            narrative_stub=(
                "{actor} gives the day to work that other people can see: "
                "the counter, the ledger, the bargaining, the small "
                "maintenance of trust that keeps trade from becoming chaos."
            ),
            state_delta={
                "character.current_activity": "working a public-facing shift",
            },
            event_type="work_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.18,
        ),
        Branch(
            label="Handle field or maintenance work",
            conditions=OR(WORKSITE_PLACE, has_tag("field_worker")),
            narrative_stub=(
                "{actor} spends the hour in practical labor: repairs, "
                "inspection, hauling, checking systems whose importance "
                "only becomes visible when they fail."
            ),
            state_delta={
                "character.current_activity": "handling field maintenance work",
            },
            event_type="work_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.20,
        ),
        Branch(
            label="Keep administrative obligations moving",
            # Self-scoped status read: senior-or-better standing toward any
            # faction means the actor's work is rosters, approvals, and
            # institutional upkeep even away from an administration place.
            conditions=OR(
                ADMINISTRATION_PLACE,
                has_any_tag("researcher", "academic", "soldier"),
                has_any_status_at_or_above("senior"),
            ),
            narrative_stub=(
                "{actor} moves necessary work through the quiet machinery: "
                "forms, messages, rosters, notes, approvals, the kind of "
                "paper trail that decides what can happen tomorrow."
            ),
            state_delta={
                "character.current_activity": "handling administrative work",
            },
            event_type="work_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.16,
        ),
        Branch(
            label="Do the labor that holds a household together",
            conditions=has_any_tag("domestic_role", "cares_for_household"),
            narrative_stub=(
                "{actor} does household work with the competence of someone "
                "who knows that ordinary life is not self-maintaining: food, "
                "cleaning, repairs, care, the small logistics of everyone "
                "getting through the day."
            ),
            state_delta={
                "character.current_activity": "doing household work",
            },
            event_type="household_work_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.18,
        ),
        Branch(
            label="Keep the obligation from slipping",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} takes care of the work that would otherwise start "
                "to fray — not enough to become a story by itself, but "
                "enough that the world does not have to break here today."
            ),
            state_delta={
                "character.current_activity": "keeping obligations current",
            },
            event_type="work_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.10,
        ),
    ),
)


TEND_CRAFT = Template(
    id="tend_craft",
    priority=15,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Craft is the low-pressure identity/project floor and intentionally "
        "sits just above generic work."
    ),
    blurb="A small act of care for the work that defines them.",
    required_slots=(Slot.ACTOR,),
    # Discipline: TEND_CRAFT is for characters with identity-defining
    # craft. Without this gate filter, the ALWAYS-fallback branch would
    # fire for every actor every tick and displace MAINTAIN_COVER
    # (priority 0) entirely. Restrict to actors carrying at least one
    # craft tag; non-craft actors fall through to MAINTAIN_COVER.
    package_gate=AND(
        has_any_tag(
            # combat
            "combat_trained",
            "soldier",
            "warrior",
            "fighter",
            # arcane
            "arcane_caster",
            # engineering / tinkering
            "engineer",
            "mechanic",
            "tinkerer",
            "hacker",
            "artificer",
            # creative
            "musician",
            "dancer",
            "performer",
            "artist",
            "writer",
            "artisan",
            # athletic / physical
            "athlete",
            "martial_artist",
            "ranger",
            "scout",
            "monk",
            # commerce
            "keeps_shop",
            "merchant",
            "innkeeper",
            "trader",
            # domestic
            "domestic_role",
            "cares_for_household",
            "matriarch",
            "patriarch",
            # scholarly
            "scholar",
            "researcher",
            "academic",
            "loremaster",
        ),
        since_last_event_at_least("craft_tended", minimum_ticks=4),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("wounded")),
        NOT(has_ephemeral("grieving")),
    ),
    branches=(
        # Self-awareness: wealth changes how craft is tended — money buys
        # materials, commissions, and time that poorer practitioners must
        # improvise around (the improvisation IS the branches below).
        Branch(
            label="Put real money into the craft",
            conditions=resources_at_or_above("wealthy"),
            narrative_stub=(
                "{actor} spends on the work the way only someone with money "
                "can: the proper materials instead of the workable ones, "
                "the commissioned part instead of the salvaged one, the "
                "bought afternoon of uninterrupted attention."
            ),
            state_delta={
                "character.current_activity": "investing in the craft",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Make the weapon ready for what comes next",
            conditions=has_any_tag("combat_trained", "soldier", "warrior", "fighter"),
            narrative_stub=(
                "{actor} takes the weapon apart with the slow patience of "
                "someone who has done this enough times to know the "
                "geometry of each piece by feel, and puts it back together "
                "the same way, attentive to small things only they will "
                "notice."
            ),
            state_delta={
                "character.current_activity": "making the weapon ready",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Lay hands on the arcane work-in-progress",
            conditions=has_tag("arcane_caster"),
            narrative_stub=(
                "{actor} spends an unhurried hour with whatever is "
                "currently between their hands and the world's underlying "
                "grammar — checking small things, adjusting smaller things, "
                "letting the work tell them what it still needs."
            ),
            state_delta={
                "character.current_activity": "tending arcane work",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Maintain and improve the tools of the trade",
            conditions=has_any_tag(
                "engineer", "mechanic", "tinkerer", "hacker", "artificer"
            ),
            narrative_stub=(
                "{actor} attends to the equipment — the part that's been "
                "annoying them for weeks, the upgrade they keep meaning to "
                "install, the calibration that's been just slightly off — "
                "and emerges with the tools a small degree better than "
                "they were."
            ),
            state_delta={
                "character.current_activity": "maintaining equipment",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Run through the work that keeps the work possible",
            conditions=has_any_tag(
                "musician", "dancer", "performer", "artist", "writer", "artisan"
            ),
            narrative_stub=(
                "{actor} works through the practice that no one will ever "
                "see — the scales, the exercises, the small motions that "
                "the public version of the art rests on — for an hour, the "
                "way the practice has to be done if the work is to stay "
                "alive."
            ),
            state_delta={
                "character.current_activity": "practicing the unseen work",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Move the body through its daily reckoning",
            conditions=has_any_tag(
                "athlete", "martial_artist", "ranger", "scout", "monk"
            ),
            narrative_stub=(
                "{actor} puts the body through its daily reckoning — the "
                "run, the forms, the small punishments that keep the body "
                "ready for whatever the next demand will be — and finishes "
                "marginally sharper than they began."
            ),
            state_delta={
                "character.current_activity": "conditioning the body",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Tend the small shop's quiet machinery",
            conditions=has_any_tag("keeps_shop", "merchant", "innkeeper", "trader"),
            narrative_stub=(
                "{actor} does the things a place of business needs in "
                "order to keep being a place of business: the count, the "
                "ledger, the small repairs, the conversations with regulars "
                "who came in for something other than the thing they "
                "actually bought."
            ),
            state_delta={
                "character.current_activity": "tending the shop's rhythms",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Keep the household running",
            conditions=has_any_tag(
                "domestic_role", "cares_for_household", "matriarch", "patriarch"
            ),
            narrative_stub=(
                "{actor} does the work that holds a household together — "
                "the meals, the cleaning, the small attentions no one "
                "particularly thanks anyone for but whose absence would be "
                "felt immediately. It is enough work for a full day, every "
                "day, by itself."
            ),
            state_delta={
                "character.current_activity": "tending the household",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Return to the unfinished study",
            conditions=has_any_tag("scholar", "researcher", "academic", "loremaster"),
            narrative_stub=(
                "{actor} returns to the long work that is always almost "
                "but never finished — reading carefully, taking notes that "
                "may yet matter, following a thread that may yet lead "
                "somewhere — and gives the work another quiet evening of "
                "the only thing it really needs."
            ),
            state_delta={
                "character.current_activity": "advancing the long study",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.18,
        ),
        Branch(
            label="Take a small action of care for the work that is theirs",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} does a small thing for the work that defines "
                "them — they would not call it that, probably, but that "
                "is what it is — and the day is briefly better for it."
            ),
            state_delta={
                "character.current_activity": "tending the work that is theirs",
                "entity_tags.add": ["recently_tended_craft"],
            },
            event_type="craft_tended",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.12,
        ),
    ),
)


# Section C — The contact quartet
#
# All four templates set present_target_policy=STORYTELLER_PRESSURE so contact
# with an on-screen target manifests as scene pressure (a ring, a knock, an
# arriving message) instead of silent off-screen state mutation.


WARN_ALLY = Template(
    id="warn_ally",
    priority=75,
    drive_band=DriveBand.CRISIS_CONSTRAINT,
    blurb="A threat surfaces; word reaches the people who need to know.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # No contact cooldown — urgency overrides ordinary contact pacing.
    package_gate=AND(
        OR(
            has_symmetric_relationship_of_type("family"),
            has_symmetric_relationship_of_type("romantic"),
            has_symmetric_relationship_of_type("chosen_kin"),
            has_symmetric_relationship_of_type("comrade"),
            has_symmetric_relationship_of_type("ally"),
        ),
        OR(
            recent_event(
                "threat_issued",
                within_ticks=3,
                target_slot=Slot.TARGET,
            ),
            recent_event(
                "compliance_alert",
                within_ticks=3,
                target_slot=Slot.TARGET,
            ),
            has_inbound_pair_tag("hunting", slot=Slot.TARGET),
        ),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Reach the ally face-to-face before the word gets out",
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                NOT(direct_contact_is_dramatic()),
            ),
            narrative_stub=(
                "{actor} catches {target} before they have time to "
                "compose themselves and tells them quickly, in a voice "
                "stripped to the load-bearing words, what is coming and "
                "what they should do about it."
            ),
            state_delta={
                "character.current_activity": "delivering urgent warning in person",
                "entity_tags_target.add": ["forewarned"],
            },
            event_type="warning_delivered",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.66,
            scene_pressure_stub=(
                "{actor} is moving to deliver an urgent warning to "
                "{target}. The scene may show this as interruption, "
                "intrusion, or a beat the storyteller folds into the "
                "current moment."
            ),
        ),
        Branch(
            label="Send word through whatever channel will reach them quickest",
            conditions=NOT(direct_contact_is_dramatic()),
            narrative_stub=(
                "{actor} sends the warning through whatever channel will "
                "reach {target} fastest — a call, a runner, a sealed "
                "message, a coded signal, a prayer through a familiar "
                "spirit — and hopes the gap between sending and receiving "
                "is short enough to matter."
            ),
            state_delta={
                "character.current_activity": "sending urgent warning",
                "entity_tags_target.add": ["forewarned"],
            },
            event_type="warning_delivered",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.52,
            scene_pressure_stub=(
                "{actor} has sent {target} an urgent warning by remote "
                "means. The scene may show this as an incoming message, "
                "a vague disturbance, a half-heard signal, or it may not "
                "land in time."
            ),
        ),
        Branch(
            label="Leak the warning without breaking cover",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} still sends the warning, but strips their own hand "
                "from it: a proxy, a coded leak, an anonymous ping, something "
                "that can reach {target} without making contact itself the "
                "story."
            ),
            state_delta={
                "character.current_activity": "leaking urgent warning",
                "entity_tags_target.add": ["forewarned"],
            },
            event_type="warning_delivered",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.40,
            scene_pressure_stub=(
                "{actor} has sent {target} an indirect warning. It may appear "
                "as a leak, proxy message, coded signal, or not land in time; "
                "Orrery is not deciding how {target} responds."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


CHECK_ON_DEPENDENT = Template(
    id="check_on_dependent",
    priority=55,
    drive_band=DriveBand.AFFILIATION,
    priority_override_rationale=(
        "Dependent care is affiliation with responsibility attached, so it can "
        "preempt ordinary maintenance."
    ),
    blurb="A duty of care surfaces between the actor and someone in their charge.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Discipline: CULTIVATE_INFORMANT (priority 50) owns the
    # informant-tradecraft handler/asset relationship. Exclude actors
    # tagged informant_handler so welfare-check and intel-cultivation
    # don't fight over the same binding.
    #
    # Cooldown: gate must check BOTH events any branch can emit
    # (welfare_check from the face-to-face branch, contact_made from the
    # remote branch). Checking only one lets the other bypass the
    # cooldown — the gate-vs-event asymmetry caught by claude[bot] on PR #223.
    package_gate=AND(
        NOT(has_tag("informant_handler")),
        OR(
            has_relationship_of_type("handler", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("mentor", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("patron", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("guardian", Slot.ACTOR, Slot.TARGET),
        ),
        since_last_event_at_least(
            "contact_made", minimum_ticks=12, target_slot=Slot.TARGET
        ),
        since_last_event_at_least(
            "welfare_check", minimum_ticks=12, target_slot=Slot.TARGET
        ),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("grudge_active")),
    ),
    branches=(
        Branch(
            label="Drop by in person when the moment allows",
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                since_last_event_at_least(
                    "welfare_check", minimum_ticks=6, target_slot=Slot.TARGET
                ),
            ),
            narrative_stub=(
                "{actor} stops by — ostensibly for something else, the way "
                "these visits often are — and uses the small window to "
                "read {target}'s state: how they look, what they say "
                "without saying, what they decline to mention. It will "
                "be enough information for now."
            ),
            state_delta={
                "character.current_activity": "checking on a dependent in person",
            },
            event_type="welfare_check",
            changed_fields=("character.current_activity",),
            magnitude=0.44,
            scene_pressure_stub=(
                "{actor} is making a casual welfare check on {target}. "
                "Treat as a low-key social presence the scene can absorb "
                "or use as a beat of relationship texture."
            ),
        ),
        Branch(
            label="Reach out through customary channels",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} sends the kind of message they always send — "
                "brief, light in tone, asking nothing real but leaving the "
                "door open for {target} to say something real if they "
                "want to — and watches for what comes back."
            ),
            state_delta={
                "character.current_activity": "checking in on a dependent",
            },
            event_type="contact_made",
            changed_fields=("character.current_activity",),
            magnitude=0.22,
            scene_pressure_stub=(
                "{actor} has sent {target} a routine welfare-check "
                "message. The scene may use this as an unread notification, "
                "an answered exchange, or texture for {target}'s "
                "decisions."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


REACH_OUT = Template(
    id="reach_out",
    priority=40,
    drive_band=DriveBand.AFFILIATION,
    priority_override_rationale=(
        "Relationship maintenance is allowed to beat everyday "
        "self-maintenance when the bond has gone quiet long enough."
    ),
    blurb="A small thread of contact between people who hold each other.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Cooldown: gate must check BOTH events any branch can emit
    # (kin_visit from the face-to-face branch, contact_made from the
    # remote branch). See CHECK_ON_DEPENDENT for the same pattern.
    #
    # The bond OR spans kin AND chosen social ties (friend, companion);
    # the warmth/asymmetry OR below is what keeps casual edges from
    # firing hollow contact beats.
    package_gate=AND(
        OR(
            has_symmetric_relationship_of_type("family"),
            has_symmetric_relationship_of_type("romantic"),
            has_symmetric_relationship_of_type("chosen_kin"),
            has_symmetric_relationship_of_type("comrade"),
            has_symmetric_relationship_of_type("friend"),
            has_symmetric_relationship_of_type("companion"),
        ),
        OR(
            relationship_is_mutual_warm(),
            relationship_is_asymmetric(),
            direct_contact_is_dramatic(),
        ),
        since_last_event_at_least(
            "contact_made", minimum_ticks=8, target_slot=Slot.TARGET
        ),
        since_last_event_at_least(
            "kin_visit", minimum_ticks=8, target_slot=Slot.TARGET
        ),
        since_last_event_at_least(
            "contact_deferred", minimum_ticks=8, target_slot=Slot.TARGET
        ),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("grudge_active")),
    ),
    branches=(
        Branch(
            label="Find the moment for a real face-to-face conversation",
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                relationship_is_mutual_warm(),
                NOT(direct_contact_is_dramatic()),
                since_last_event_at_least(
                    "kin_visit", minimum_ticks=5, target_slot=Slot.TARGET
                ),
            ),
            narrative_stub=(
                "{actor} makes the small effort that finding-time-for-someone "
                "requires — clearing a half hour, choosing a place, "
                "showing up — and {target} arrives, and for a while they "
                "are the kind of present together that distance erodes."
            ),
            state_delta={
                "character.current_activity": (
                    "spending real time with someone held dear"
                ),
            },
            event_type="kin_visit",
            changed_fields=("character.current_activity",),
            magnitude=0.36,
            scene_pressure_stub=(
                "{actor} is meeting {target} in person for a real "
                "conversation. Use this as a relationship beat the scene "
                "can fold in or hold for later, not as a guaranteed "
                "off-screen event."
            ),
        ),
        Branch(
            label="Send a message that says less than it means",
            conditions=AND(
                relationship_is_mutual_warm(),
                NOT(direct_contact_is_dramatic()),
            ),
            narrative_stub=(
                "{actor} sends {target} the small message that means "
                "more than the words it contains — a check-in, a shared "
                "joke, a question that doesn't really need answering — "
                "and the thread between them stays warm for another while."
            ),
            state_delta={
                "character.current_activity": "keeping a close bond warm",
            },
            event_type="contact_made",
            changed_fields=("character.current_activity",),
            magnitude=0.16,
            scene_pressure_stub=(
                "{actor} has sent {target} a small affectionate message. "
                "Treat as ambient relationship-warmth — possibly an "
                "incoming notification, possibly not surfaced at all."
            ),
        ),
        Branch(
            label="Draft the message and leave it unsent",
            conditions=OR(relationship_is_asymmetric(), direct_contact_is_dramatic()),
            narrative_stub=(
                "{actor} writes the message anyway, or composes the call in "
                "their head, and then does not send it. The wanting is real; "
                "so is the cost of turning it into contact."
            ),
            state_delta={
                "character.current_activity": "drafting unsent contact",
            },
            event_type="contact_deferred",
            changed_fields=("character.current_activity",),
            magnitude=0.18,
            scene_pressure_stub=(
                "{actor} is holding back a loaded attempt to reach {target}. "
                "Use this as optional emotional pressure or a future story "
                "beat; Orrery has not made contact happen."
            ),
        ),
        Branch(
            label="Let the silence stand for now",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} lets the thread remain unpulled. Whatever exists "
                "between them and {target}, it is not made warmer by forcing "
                "the wrong kind of contact today."
            ),
            state_delta={
                "character.current_activity": "deferring contact",
            },
            event_type="contact_deferred",
            changed_fields=("character.current_activity",),
            magnitude=0.08,
            scene_pressure_stub=(
                "{actor} is choosing not to contact {target} for now. Treat "
                "this as optional subtext, not as a visible scene event."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


CONSULT_RIVAL = Template(
    id="consult_rival",
    priority=35,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Rival consultation is a deliberate project move, not casual social "
        "contact, and can outrank routine obligations."
    ),
    blurb="Two people who do not trust each other are forced into contact anyway.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    # Divergence: the draft included `has_ephemeral("grudge_active")` in the
    # shared-circumstance OR; the same gate excludes it via NOT below. The
    # OR-arm is removed. EXTRACT_VENGEANCE (priority 90) owns grudge-active
    # space; the NOT here is the documented safety belt.
    #
    # Cooldown: gate must check BOTH events any branch can emit
    # (rival_consulted from the meaningful branches, contact_made from the
    # ALWAYS fallback). Without the rival_consulted cooldown the high-
    # magnitude branches could refire next tick — caught by Codex on PR #223.
    # #530 review: favorable `complex` now records reconciliation, so it is
    # not itself a fraught tie. Genuine distrust remains covered by the
    # adjacent trust_below arm.
    package_gate=AND(
        OR(
            has_relationship_of_type("rival"),
            has_symmetric_relationship_of_type("enemy"),
            trust_below(0),
        ),
        OR(
            recent_event("compliance_alert", within_ticks=10),
            recent_event("threat_issued", within_ticks=10),
            recent_event("faction_realignment", within_ticks=15),
        ),
        since_last_event_at_least(
            "contact_made", minimum_ticks=20, target_slot=Slot.TARGET
        ),
        since_last_event_at_least(
            "rival_consulted", minimum_ticks=20, target_slot=Slot.TARGET
        ),
        NOT(has_ephemeral("grudge_active")),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Meet face-to-face on neutral ground",
            conditions=AND(
                co_located(Slot.ACTOR, Slot.TARGET),
                PUBLIC_MEETING_PLACE,
            ),
            narrative_stub=(
                "{actor} and {target} arrange to be in the same place at "
                "the same time without quite arranging it — both of them "
                "drinking something they don't particularly want, both of "
                "them speaking carefully — because whatever is happening "
                "is bigger than what they have between them, and they "
                "both know it."
            ),
            state_delta={
                "character.current_activity": "meeting a rival under truce",
                "entity_tags.add": ["under_truce"],
                "entity_tags_target.add": ["under_truce"],
            },
            event_type="rival_consulted",
            changed_fields=("character.current_activity", "entity_tags"),
            magnitude=0.62,
            scene_pressure_stub=(
                "{actor} is in a tense face-to-face meeting with {target}, "
                "a known rival. Treat as charged co-presence — the scene "
                "can show this as observed truce, ambient discomfort, or "
                "delayed consequence."
            ),
        ),
        Branch(
            label="Send a carefully-worded message through indirect channels",
            conditions=has_contact_of_kind("social"),
            narrative_stub=(
                "{actor} sends {target} a message routed through an "
                "intermediary they both trust slightly more than they "
                "trust each other — a message worded with enough care "
                "that the indirect-channel relay can be denied later, "
                "but with enough substance that {target} cannot reasonably "
                "ignore it."
            ),
            state_delta={
                "character.current_activity": (
                    "reaching out to a rival via intermediary"
                ),
            },
            event_type="rival_consulted",
            changed_fields=("character.current_activity",),
            magnitude=0.48,
            scene_pressure_stub=(
                "{actor} has sent {target} a carefully-routed message via "
                "intermediary. Treat as off-screen pressure — the scene "
                "may show {target} reacting to it, or it may resurface "
                "later."
            ),
        ),
        Branch(
            label=("Leave a sign the rival will recognize and a door they can open"),
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} doesn't quite reach out — but they place a sign "
                "where {target} will see it, the kind of signal that says "
                "*I am willing to talk if you are*, without committing to "
                "anything. If {target} reads the sign, the contact has "
                "begun. If they don't, it hasn't."
            ),
            state_delta={
                "character.current_activity": (
                    "leaving a tentative overture for a rival"
                ),
            },
            event_type="contact_made",
            changed_fields=("character.current_activity",),
            magnitude=0.34,
            scene_pressure_stub=(
                "{actor} has placed a discreet overture for {target} to "
                "find. Treat as a passive hook the scene can pick up if "
                "useful, or leave dormant."
            ),
        ),
    ),
    present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
)


SLEEP = Template(
    id="sleep",
    priority=25,
    drive_band=DriveBand.EMBODIED_MAINTENANCE,
    blurb="The body asks for the thing without which it cannot continue.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        OR(
            AND(
                time_of_day_in("night"),
                has_need_debt_at_or_above("sleep", 8),
            ),
            has_need_debt_at_or_above("sleep", 16),
        ),
        NOT(has_ephemeral("cns_stimulated")),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Collapse into deferred sleep",
            conditions=has_need_debt_at_or_above("sleep", 48),
            narrative_stub=(
                "{actor} stops negotiating with exhaustion. Whatever place "
                "they have reached becomes the place where the body claims "
                "its overdue sleep."
            ),
            state_delta={
                "character.current_activity": "collapsing into deferred sleep",
                "need.fulfill": {
                    "type": "sleep",
                    "duration_hours": 4,
                    "quality": "collapse_rough",
                    "discharge_debt": 4,
                },
            },
            event_type="slept",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.74,
        ),
        Branch(
            label="Sleep at home",
            conditions=HOME_PLACE,
            narrative_stub=(
                "{actor} reaches familiar shelter and lets sleep take them "
                "where the room already knows their shape."
            ),
            state_delta={
                "character.current_activity": "sleeping at home",
                "need.fulfill": {
                    "type": "sleep",
                    "duration_hours": 8,
                    "quality": "good",
                    "discharge_debt": 10,
                },
            },
            event_type="slept",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.22,
        ),
        Branch(
            label="Sleep in safe lodgings",
            conditions=OR(
                SAFE_LODGING_PLACE,
                has_contact_of_kind("lodging"),
            ),
            narrative_stub=(
                "{actor} finds a place secure enough to become temporary "
                "shelter and lets the unfamiliar room do enough of the work."
            ),
            state_delta={
                "character.current_activity": "sleeping in safe lodgings",
                "need.fulfill": {
                    "type": "sleep",
                    "duration_hours": 7,
                    "quality": "adequate",
                    "discharge_debt": 7,
                },
            },
            event_type="slept",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.28,
        ),
        Branch(
            label="Sleep rough in cover or transit",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} sleeps in fragments, taking what rest the place "
                "allows and waking with some part of the debt still unpaid."
            ),
            state_delta={
                "character.current_activity": "sleeping rough",
                "need.fulfill": {
                    "type": "sleep",
                    "duration_hours": 5,
                    "quality": "rough",
                    "discharge_debt": 3,
                },
            },
            event_type="slept",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.36,
        ),
    ),
)


DRINK = Template(
    id="drink",
    priority=24,
    drive_band=DriveBand.EMBODIED_MAINTENANCE,
    blurb="The body asks for water; what it accepts shapes the small hour.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_need_debt_at_or_above("thirst", 2),
        OR(
            has_need_debt_at_or_above("thirst", 16),
            NOT(
                AND(
                    has_need_debt_at_or_above("hunger", 4),
                    time_of_day_in("morning", "afternoon", "evening"),
                    OR(HOME_PLACE, PUBLIC_DINING_PLACE),
                )
            ),
        ),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Drink desperately, whatever is available",
            conditions=has_need_debt_at_or_above("thirst", 16),
            narrative_stub=(
                "{actor} drinks with the single-mindedness that severe "
                "thirst produces, past concern for source or dignity."
            ),
            state_delta={
                "character.current_activity": "drinking to relieve severe thirst",
                "need.fulfill": {
                    "type": "thirst",
                    "quality": "desperate",
                    "discharge_debt": 9999,
                },
            },
            event_type="drank",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.56,
        ),
        Branch(
            label="Drink in a public room",
            conditions=PUBLIC_DRINK_PLACE,
            narrative_stub=(
                "{actor} drinks what the room serves and lets the small "
                "ritual of holding a cup make the hour easier."
            ),
            state_delta={
                "character.current_activity": "drinking in company",
                "need.fulfill": {
                    "type": "thirst",
                    "quality": "social",
                    "discharge_debt": 9999,
                },
            },
            event_type="drank",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.22,
        ),
        Branch(
            label="Drink from a public or wild source",
            conditions=PUBLIC_WATER_PLACE,
            narrative_stub=(
                "{actor} drinks from whatever the place provides, and the "
                "relief of water makes the rest of the day briefly simpler."
            ),
            state_delta={
                "character.current_activity": "drinking from an available source",
                "need.fulfill": {
                    "type": "thirst",
                    "quality": "available_source",
                    "discharge_debt": 9999,
                },
            },
            event_type="drank",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.14,
        ),
        Branch(
            label="Drink routinely from what is at hand",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} drinks because the body has been quietly asking, "
                "then returns to the shape of the hour."
            ),
            state_delta={
                "character.current_activity": "drinking routinely",
                "need.fulfill": {
                    "type": "thirst",
                    "quality": "routine",
                    "discharge_debt": 9999,
                },
            },
            event_type="drank",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.10,
        ),
    ),
)


EAT = Template(
    id="eat",
    priority=22,
    drive_band=DriveBand.EMBODIED_MAINTENANCE,
    blurb=(
        "The body asks for fuel; what it gets matters more than the cookbook "
        "suggests."
    ),
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_need_debt_at_or_above("hunger", 4),
        OR(
            time_of_day_in("morning", "afternoon", "evening"),
            has_need_debt_at_or_above("hunger", 8),
        ),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Eat ravenously, whatever is available",
            conditions=has_need_debt_at_or_above("hunger", 16),
            narrative_stub=(
                "{actor} eats with the inattention of real hunger, relief "
                "overtaking any concern about what the food ought to be."
            ),
            state_delta={
                "character.current_activity": "eating to relieve severe hunger",
                "need.fulfill": {
                    "type": "hunger",
                    "quality": "desperate",
                    "discharge_debt": 9999,
                },
            },
            event_type="ate",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.62,
        ),
        Branch(
            label="Eat at home with household",
            conditions=AND(
                HOME_PLACE,
                has_any_tag("married", "parent", "extended_household"),
            ),
            narrative_stub=(
                "{actor} sits down to the meal that home means and lets "
                "being-with stand in for being-alone for a while."
            ),
            state_delta={
                "character.current_activity": "sharing a household meal",
                "need.fulfill": {
                    "type": "hunger",
                    "quality": "household_meal",
                    "discharge_debt": 9999,
                },
            },
            event_type="ate",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.22,
        ),
        Branch(
            label="Eat at home alone",
            conditions=HOME_PLACE,
            narrative_stub=(
                "{actor} makes the kind of meal home makes possible: "
                "unremarkable, private, and enough to let the evening "
                "continue on ordinary terms."
            ),
            state_delta={
                "character.current_activity": "eating at home",
                "need.fulfill": {
                    "type": "hunger",
                    "quality": "home_meal",
                    "discharge_debt": 9999,
                },
            },
            event_type="ate",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.20,
        ),
        Branch(
            label="Eat in a public dining place",
            conditions=PUBLIC_DINING_PLACE,
            narrative_stub=(
                "{actor} eats something the place can provide and watches "
                "the room continue its public life around them."
            ),
            state_delta={
                "character.current_activity": "eating in a public place",
                "need.fulfill": {
                    "type": "hunger",
                    "quality": "public_meal",
                    "discharge_debt": 9999,
                },
            },
            event_type="ate",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.26,
        ),
        Branch(
            label="Forage or hunt from the country",
            conditions=AND(
                in_location_class("wilderness"),
                has_any_tag("forager", "hunter", "survivalist", "ranger", "scout"),
            ),
            narrative_stub=(
                "{actor} works the country for what the season has put "
                "within reach and makes a meal out of survival knowledge."
            ),
            state_delta={
                "character.current_activity": "foraging for a meal",
                "need.fulfill": {
                    "type": "hunger",
                    "quality": "wild_meal",
                    "discharge_debt": 9999,
                },
            },
            event_type="ate",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.38,
        ),
        Branch(
            label="Eat from rations or what was packed",
            conditions=has_tag("travel_provisioned"),
            narrative_stub=(
                "{actor} eats what was packed for exactly this kind of hour: "
                "practical, portable, and enough."
            ),
            state_delta={
                "character.current_activity": "eating travel rations",
                "need.fulfill": {
                    "type": "hunger",
                    "quality": "rations_meal",
                    "discharge_debt": 9999,
                },
            },
            event_type="ate",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.18,
        ),
        Branch(
            label="Find something and eat it",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} eats what is nearest and workable, attentive mostly "
                "to the fact that the body can stop asking for now."
            ),
            state_delta={
                "character.current_activity": "eating opportunistically",
                "need.fulfill": {
                    "type": "hunger",
                    "quality": "opportunistic_meal",
                    "discharge_debt": 9999,
                },
            },
            event_type="ate",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.14,
        ),
    ),
)


SOCIALIZE = Template(
    id="socialize",
    priority=18,
    drive_band=DriveBand.AFFILIATION,
    priority_override_rationale=(
        "Accumulated social debt is allowed to interrupt generic work/routine "
        "before it becomes a crisis."
    ),
    blurb=(
        "The need for the company of others, on whatever terms a character "
        "can have it."
    ),
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_need_debt_at_or_above("socialize", 24),
        since_last_event_at_least("socialized", minimum_ticks=4),
        since_last_event_at_least("socialized_alone", minimum_ticks=4),
        since_last_event_at_least("social_travel_departed", minimum_ticks=4),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("grieving")),
        NOT(has_ephemeral("wounded")),
    ),
    branches=(
        # Self-awareness: a renowned-or-better actor cannot get casual
        # anonymous company from a public room — the room reorganizes
        # around them. Their socializing happens on ground they control,
        # with people they already know. Listed before the disposition
        # branch below deliberately: fame structurally constrains WHERE
        # company can happen, so it outranks disposition (which only
        # shapes the medium) when both match.
        Branch(
            label="Host chosen company on their own ground",
            conditions=AND(
                fame_at_or_above("renowned"),
                has_contact_of_kind("social"),
            ),
            narrative_stub=(
                "{actor} does not go looking for company in rooms that "
                "would turn to watch them enter. They summon it instead: a "
                "few chosen people, a door that closes, an evening where "
                "nobody performs recognition."
            ),
            state_delta={
                "character.current_activity": "hosting chosen company privately",
                "need.fulfill": {
                    "type": "socialize",
                    "quality": "private_company",
                    "discharge_debt": 9999,
                },
            },
            event_type="socialized",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.24,
        ),
        Branch(
            label="Seek company after extended isolation",
            conditions=AND(
                has_need_debt_at_or_above("socialize", 168),
                NOT(count_co_located(1)),
                NOT(SOCIAL_VENUE_PLACE),
                can_move_publicly(),
                fame_below("renowned"),
                has_location_class_destination(
                    "commerce", "entertainment", "meeting", "place_open"
                ),
            ),
            narrative_stub=(
                "{actor} feels the particular pressure that comes from going "
                "too long without other people in their life, and moves "
                "toward somewhere there will be voices, even if those voices "
                "are not for them."
            ),
            state_delta={
                "character.current_activity": "seeking company after isolation",
                "travel.start": {
                    "destination_place_classes": [
                        "commerce",
                        "entertainment",
                        "meeting",
                        "place_open",
                    ],
                    "mode": "mixed",
                    "purpose": "socialize",
                    "purpose_need": "socialize",
                    "initial_progress": 0.05,
                },
            },
            event_type="social_travel_departed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.status",
                "character_travel_states.progress_ratio",
            ),
            magnitude=0.54,
        ),
        Branch(
            label="Engage with company already present",
            conditions=count_co_located(1),
            narrative_stub=(
                "{actor} spends real attention on the people around them — "
                "not transactional attention, the other kind — for long "
                "enough that the social need is briefly met without anyone "
                "naming it as such."
            ),
            state_delta={
                "character.current_activity": "engaging with present company",
                "need.fulfill": {
                    "type": "socialize",
                    "quality": "present_company",
                    "discharge_debt": 9999,
                },
            },
            event_type="socialized",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.22,
        ),
        # Self-awareness: dispositionally private actors with someone to
        # call prefer a trusted voice over an anonymous crowd, even when a
        # public venue is reachable.
        Branch(
            label="Seek a trusted voice rather than a crowd",
            conditions=AND(
                has_any_tag("solitary", "reserved"),
                has_contact_of_kind("social"),
            ),
            narrative_stub=(
                "{actor} weighs the noise of a public room against the "
                "particular relief of one familiar voice, and chooses the "
                "voice — a long, unhurried exchange with someone who does "
                "not need anything explained."
            ),
            state_delta={
                "character.current_activity": "talking with a trusted contact",
                "need.fulfill": {
                    "type": "socialize",
                    "quality": "trusted_contact",
                    "discharge_debt": 72,
                },
            },
            event_type="socialized",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.22,
        ),
        Branch(
            label="Set out toward public company",
            conditions=AND(
                NOT(count_co_located(1)),
                NOT(SOCIAL_VENUE_PLACE),
                can_move_publicly(),
                fame_below("renowned"),
                has_location_class_destination(
                    "commerce", "entertainment", "meeting", "place_open"
                ),
            ),
            narrative_stub=(
                "{actor} chooses movement over more empty time and sets out "
                "toward a place where other people can be encountered without "
                "requiring the story to pre-name them."
            ),
            state_delta={
                "character.current_activity": "seeking public company",
                "travel.start": {
                    "destination_place_classes": [
                        "commerce",
                        "entertainment",
                        "meeting",
                        "place_open",
                    ],
                    "mode": "mixed",
                    "purpose": "socialize",
                    "purpose_need": "socialize",
                    "initial_progress": 0.05,
                },
            },
            event_type="social_travel_departed",
            changed_fields=(
                "character.current_activity",
                "character_travel_states.status",
                "character_travel_states.progress_ratio",
            ),
            magnitude=0.26,
        ),
        Branch(
            label="Go where people are",
            conditions=AND(SOCIAL_VENUE_PLACE, fame_below("renowned")),
            narrative_stub=(
                "{actor} goes to one of the places built around the fact "
                "that people gather there, and stays long enough to become "
                "part of the room's ordinary texture."
            ),
            state_delta={
                "character.current_activity": "passing time in a populated place",
                "need.fulfill": {
                    "type": "socialize",
                    "quality": "public_company",
                    "discharge_debt": 9999,
                },
            },
            event_type="socialized",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.20,
        ),
        Branch(
            label="Reach out to a contact for no urgent reason",
            conditions=has_contact_of_kind("social"),
            narrative_stub=(
                "{actor} thinks of someone they have not spoken with in too "
                "long and reaches out for no urgent reason, which is its "
                "own kind of reason."
            ),
            state_delta={
                "character.current_activity": "reconnecting with a contact",
                "need.fulfill": {
                    "type": "socialize",
                    "quality": "remote_contact",
                    "discharge_debt": 72,
                },
            },
            event_type="socialized",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.24,
        ),
        Branch(
            label="Practice parasocial company",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} spends an hour with the voice of a stranger — a "
                "book, a serial, a recording — which is not the same as "
                "company but is enough like company to take the worst edge "
                "off."
            ),
            state_delta={
                "character.current_activity": "spending time with a stranger's voice",
                "need.fulfill": {
                    "type": "socialize",
                    "quality": "parasocial",
                    "discharge_debt": 12,
                },
            },
            event_type="socialized_alone",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.16,
        ),
    ),
)


INTIMACY = Template(
    id="intimacy",
    priority=16,
    drive_band=DriveBand.AFFILIATION,
    priority_override_rationale=(
        "Intimacy pressure should beat generic work when gates and suppressors "
        "allow it, but remain below basic embodied maintenance."
    ),
    blurb="The body asks for the kind of connection that is not conversation.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_need_debt_at_or_above("intimacy", 72),
        NOT(has_any_intimacy_suppressor()),
        since_last_event_at_least("intimacy_fulfilled", minimum_ticks=8),
        since_last_event_at_least("intimacy_pursued", minimum_ticks=8),
        since_last_event_at_least("intimacy_partial", minimum_ticks=8),
        since_last_event_at_least("intimacy_deferred", minimum_ticks=8),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("wounded")),
        NOT(has_ephemeral("grieving")),
    ),
    branches=(
        Branch(
            label="Spend private time with an established partner",
            conditions=AND(
                HOME_PLACE,
                has_established_partner_co_located(),
            ),
            narrative_stub=(
                "{actor} closes the door on the day and lets private time "
                "with an established partner answer a need the public world "
                "has no claim on."
            ),
            state_delta={
                "character.current_activity": "spending private time with partner",
                "need.fulfill": {
                    "type": "intimacy",
                    "quality": "established_partner",
                    "discharge_debt": 9999,
                },
            },
            event_type="intimacy_fulfilled",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.32,
        ),
        Branch(
            label="Visit a place where compatible company gathers",
            conditions=AND(
                INTIMATE_SOCIAL_PLACE,
                has_need_debt_at_or_above("intimacy", 168),
                NOT(has_tag("partnered_exclusively")),
            ),
            narrative_stub=(
                "{actor} goes to the kind of place where someone like them "
                "might meet someone they would want to meet, alert to the "
                "possibility without presuming the outcome."
            ),
            state_delta={
                "character.current_activity": "seeking compatible company",
                "need.fulfill": {
                    "type": "intimacy",
                    "quality": "pursued_possibility",
                    "discharge_debt": 24,
                },
            },
            event_type="intimacy_pursued",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.48,
        ),
        Branch(
            label="Engage contracted intimate company",
            conditions=AND(
                INTIMATE_SERVICES_PLACE,
                has_contact_of_kind("intimate"),
                NOT(has_tag("partnered_exclusively")),
                NOT(
                    has_any_tag(
                        "vow_of_celibacy",
                        "religiously_abstinent",
                        "ethically_opposed_to_contracted_intimacy",
                    )
                ),
            ),
            narrative_stub=(
                "{actor} arranges what can be arranged, in one of the places "
                "where the transaction is understood by everyone involved "
                "and made ordinary by that clarity."
            ),
            state_delta={
                "character.current_activity": "engaging contracted intimate company",
                "need.fulfill": {
                    "type": "intimacy",
                    "quality": "contracted_companion",
                    "discharge_debt": 9999,
                },
            },
            event_type="intimacy_fulfilled",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.28,
        ),
        Branch(
            label="Attend to the need in private",
            conditions=AND(
                PRIVATE_PLACE,
                NOT(count_co_located(1)),
            ),
            narrative_stub=(
                "{actor} attends to the body's quieter demands in private — "
                "an unremarkable hour the rest of the world has no business "
                "knowing about."
            ),
            state_delta={
                "character.current_activity": "private personal time",
                "need.fulfill": {
                    "type": "intimacy",
                    "quality": "private_solo",
                    "discharge_debt": 48,
                },
            },
            event_type="intimacy_partial",
            changed_fields=(
                "character.current_activity",
                "character_need_states.debt_score",
            ),
            magnitude=0.06,
        ),
        Branch(
            label="Let the want stay where it is",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} does not pursue what the body is asking for — the "
                "wrong company, the wrong hour, the wrong life — and the "
                "want stays where it has been for a while now."
            ),
            state_delta={
                "character.current_activity": "carrying an unaddressed want",
            },
            event_type="intimacy_deferred",
            changed_fields=("character.current_activity",),
            magnitude=0.10,
        ),
    ),
)


# ----------------------------------------------------------------------------
# Section — The mundane band
#
# Genre-neutral things people do in the absence of more pressing concerns.
# Deliberately universal: unlike TEND_CRAFT's tag-restricted entry, these
# gates admit any hydrated actor (TRAIN excepted — training is identity-
# conditional), because the measured famine was actors with NO reachable
# package, not actors with too many. Displacing MAINTAIN_COVER (priority 0)
# for ordinary life is the intent.
#
# Anti-monoculture comes from cooldown staggering: every package carries a
# different since_last cooldown (5-9 ticks), so an unpressured actor cycles
# through varied mundane verbs — errands (13), stroll (12), upkeep (11),
# training (10), recreation (9) — rather than repeating one. The whole
# ladder sits strictly below WORK (14) and every need package: mundane
# texture never outranks an actionable pressure. Magnitudes stay below the
# [orrery.promote] floor: this band is ambient texture and event-ecology
# fuel, not storyteller-prompt pressure.
# ----------------------------------------------------------------------------


TRAIN = Template(
    id="train",
    priority=10,
    drive_band=DriveBand.ANCHORED_ROUTINE,
    blurb="Keeping the body and the trained skill from dulling.",
    required_slots=(Slot.ACTOR,),
    # Identity-conditional like TEND_CRAFT: training is upkeep of a
    # discipline the actor actually has. The wide tag OR is the entry;
    # branches pick which discipline gets the hour.
    package_gate=AND(
        has_minimal_context(),
        has_any_tag(
            # body
            "combat_trained",
            "soldier",
            "warrior",
            "fighter",
            "martial_artist",
            "athlete",
            "monk",
            "scout",
            "ranger",
            "hunter",
            "dancer",
            # skill
            "hacker",
            "arcane_caster",
            "medical_skill",
            "surgical_training",
            "first_aid_trained",
            "musician",
            "performer",
            "surveillance_capable",
        ),
        time_of_day_in("morning", "midday", "afternoon", "evening"),
        since_last_event_at_least("training_performed", minimum_ticks=8),
        NOT(is_constrained()),
        NOT(has_any_tag(*NON_CORPOREAL_TAGS)),
        NOT(is_in_transit()),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("wounded")),
    ),
    branches=(
        Branch(
            label="Drill the fighting forms",
            conditions=has_any_tag(
                "combat_trained",
                "soldier",
                "warrior",
                "fighter",
                "martial_artist",
                "monk",
            ),
            narrative_stub=(
                "{actor} runs the forms until the body stops asking why — "
                "footwork, repetition, the unglamorous maintenance that "
                "keeps a fighter's skill from becoming a fighter's memory."
            ),
            state_delta={
                "character.current_activity": "drilling fighting forms",
            },
            event_type="training_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.22,
        ),
        Branch(
            label="Condition the body",
            conditions=has_any_tag("athlete", "dancer", "scout", "ranger", "hunter"),
            narrative_stub=(
                "{actor} puts the body through its paces — distance, "
                "climbing, stretch and strain — paying the quiet daily tax "
                "that keeps it answering when called."
            ),
            state_delta={
                "character.current_activity": "conditioning the body",
            },
            event_type="training_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.18,
        ),
        Branch(
            label="Sharpen the finer skill",
            conditions=has_any_tag(
                "hacker",
                "arcane_caster",
                "medical_skill",
                "surgical_training",
                "first_aid_trained",
                "musician",
                "performer",
                "surveillance_capable",
            ),
            narrative_stub=(
                "{actor} practices the exacting part of what they do — "
                "scales, sutures, sigils, whatever their craft calls its "
                "fundamentals — because the difference between good and "
                "trusted is repetition nobody sees."
            ),
            state_delta={
                "character.current_activity": "sharpening a trained skill",
            },
            event_type="training_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.18,
        ),
        Branch(
            label="Keep the edge from dulling",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} gives an hour to basic upkeep of their discipline "
                "— nothing ambitious, just enough that tomorrow's version "
                "of them inherits a tool that still works."
            ),
            state_delta={
                "character.current_activity": "maintaining their training",
            },
            event_type="training_performed",
            changed_fields=("character.current_activity",),
            magnitude=0.12,
        ),
    ),
)


RUN_ERRANDS = Template(
    id="run_errands",
    priority=13,
    drive_band=DriveBand.ANCHORED_ROUTINE,
    blurb="The small acquisitions and obligations that keep a life stocked.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_minimal_context(),
        time_of_day_in("morning", "midday", "afternoon"),
        since_last_event_at_least("errands_run", minimum_ticks=9),
        NOT(is_constrained()),
        NOT(has_any_tag(*NON_CORPOREAL_TAGS)),
        NOT(is_in_transit()),
        NOT(is_hidden()),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("wounded")),
    ),
    branches=(
        Branch(
            label="Make the market run",
            conditions=in_location_class("commerce"),
            narrative_stub=(
                "{actor} works through the stalls and counters with a "
                "mental list — provisions, replacements, the one thing "
                "that ran out at the worst moment — trading small money "
                "for the continued smooth running of a life."
            ),
            state_delta={
                "character.current_activity": "making a market run",
            },
            event_type="errands_run",
            changed_fields=("character.current_activity",),
            magnitude=0.18,
        ),
        Branch(
            label="Scrounge for what the day needs",
            conditions=resources_below("poor"),
            narrative_stub=(
                "{actor} does the poor person's version of errands: "
                "finding, borrowing, bartering, stretching — acquiring by "
                "ingenuity what others acquire by purse."
            ),
            state_delta={
                "character.current_activity": "scrounging necessities",
            },
            event_type="errands_run",
            changed_fields=("character.current_activity",),
            magnitude=0.16,
        ),
        Branch(
            label="Provision the household",
            conditions=has_any_tag(
                "domestic_role", "cares_for_household", "matriarch", "patriarch"
            ),
            narrative_stub=(
                "{actor} runs the rounds a household quietly depends on — "
                "food in, worn things out, the standing orders renewed — "
                "the invisible supply chain of ordinary life."
            ),
            state_delta={
                "character.current_activity": "provisioning the household",
            },
            event_type="errands_run",
            changed_fields=("character.current_activity",),
            magnitude=0.16,
        ),
        Branch(
            label="Knock out the small obligations",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} spends the hour on the small errands that "
                "accumulate at the edges of any life — a thing to return, "
                "a message to leave, a small debt of logistics repaid."
            ),
            state_delta={
                "character.current_activity": "running small errands",
            },
            event_type="errands_run",
            changed_fields=("character.current_activity",),
            magnitude=0.10,
        ),
    ),
)


STROLL = Template(
    id="stroll",
    priority=12,
    drive_band=DriveBand.ANCHORED_ROUTINE,
    blurb="Taking air: an unhurried walk with no destination that matters.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_minimal_context(),
        since_last_event_at_least("stroll_taken", minimum_ticks=5),
        NOT(is_constrained()),
        NOT(has_any_tag(*NON_CORPOREAL_TAGS)),
        NOT(is_in_transit()),
        NOT(is_hidden()),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("wounded")),
    ),
    branches=(
        Branch(
            label="Walk under open sky",
            conditions=AND(
                weather_is("clear", "warm"),
                NOT(in_location_class("subterranean")),
            ),
            narrative_stub=(
                "{actor} walks for the sake of walking, under weather good "
                "enough to notice — the pace of someone whose next hour "
                "has, for once, no owner."
            ),
            state_delta={
                "character.current_activity": "walking under open sky",
            },
            event_type="stroll_taken",
            changed_fields=("character.current_activity",),
            magnitude=0.16,
        ),
        Branch(
            label="Walk the familiar streets",
            conditions=URBAN_PUBLIC_FLOW_PLACE,
            narrative_stub=(
                "{actor} takes the long way through streets they know by "
                "wear rather than by name, registering the small changes — "
                "a new face at a stall, a repaired door — that a "
                "neighborhood shows only to its regulars."
            ),
            state_delta={
                "character.current_activity": "walking the neighborhood",
            },
            event_type="stroll_taken",
            changed_fields=("character.current_activity",),
            magnitude=0.14,
        ),
        Branch(
            label="Take the night air",
            conditions=time_of_day_in("evening", "night"),
            narrative_stub=(
                "{actor} steps out into the dark hours, when the world "
                "runs quieter and thoughts get room to finish themselves."
            ),
            state_delta={
                "character.current_activity": "taking the night air",
            },
            event_type="stroll_taken",
            changed_fields=("character.current_activity",),
            magnitude=0.12,
        ),
        Branch(
            label="Pace the near ground",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} moves through whatever ground is nearest — "
                "corridors, courtyard, the length of a deck or a lane — "
                "walking off the restlessness that sitting still breeds."
            ),
            state_delta={
                "character.current_activity": "pacing the near ground",
            },
            event_type="stroll_taken",
            changed_fields=("character.current_activity",),
            magnitude=0.08,
        ),
    ),
)


UPKEEP = Template(
    id="upkeep",
    priority=11,
    drive_band=DriveBand.ANCHORED_ROUTINE,
    blurb="Tending one's own space, kit, and tools before they fail.",
    required_slots=(Slot.ACTOR,),
    # Distinct from WORK's household branch: that is labor performed as a
    # role obligation (domestic_role and kin); this is any actor tending
    # what is theirs — quarters, gear, tools.
    package_gate=AND(
        has_minimal_context(),
        since_last_event_at_least("upkeep_done", minimum_ticks=7),
        NOT(is_constrained()),
        NOT(has_any_tag(*NON_CORPOREAL_TAGS)),
        NOT(is_in_transit()),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Maintain the working tools",
            conditions=has_any_tag(
                "engineer",
                "mechanic",
                "tinkerer",
                "artificer",
                "artisan",
                "keeps_shop",
                "merchant",
                "hacker",
                "musician",
            ),
            narrative_stub=(
                "{actor} goes over the tools of their trade — cleaning, "
                "adjusting, replacing the part that was about to become a "
                "story — because the work is only ever as good as the kit."
            ),
            state_delta={
                "character.current_activity": "maintaining their tools",
            },
            event_type="upkeep_done",
            changed_fields=("character.current_activity",),
            magnitude=0.16,
        ),
        Branch(
            label="Mend and ready the kit",
            conditions=has_any_tag(
                "soldier",
                "scout",
                "ranger",
                "hunter",
                "combat_trained",
                "travel_ready",
            ),
            narrative_stub=(
                "{actor} strips, checks, and rights their gear with the "
                "economy of habit — edges, straps, seals, charges — so "
                "that when it matters, nothing surprises them."
            ),
            state_delta={
                "character.current_activity": "readying their kit",
            },
            event_type="upkeep_done",
            changed_fields=("character.current_activity",),
            magnitude=0.15,
        ),
        Branch(
            label="Set the home in order",
            conditions=at_routine_anchor("home"),
            narrative_stub=(
                "{actor} puts their own place back in order — the small "
                "repairs and resets that make a room somewhere to return "
                "to instead of somewhere to pass through."
            ),
            state_delta={
                "character.current_activity": "setting their home in order",
            },
            event_type="upkeep_done",
            changed_fields=("character.current_activity",),
            magnitude=0.14,
        ),
        Branch(
            label="Tidy what is theirs",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} tends whatever corner of the world is currently "
                "theirs — folding, sorting, wiping down, the small "
                "housekeeping that keeps a life from silting up."
            ),
            state_delta={
                "character.current_activity": "tidying their own space",
            },
            event_type="upkeep_done",
            changed_fields=("character.current_activity",),
            magnitude=0.08,
        ),
    ),
)


RECREATE = Template(
    id="recreate",
    priority=9,
    drive_band=DriveBand.ANCHORED_ROUTINE,
    blurb="Unproductive time taken on purpose: play, spectacle, small pleasure.",
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        has_minimal_context(),
        time_of_day_in("afternoon", "evening", "night"),
        since_last_event_at_least("recreation_taken", minimum_ticks=6),
        NOT(is_constrained()),
        NOT(is_in_transit()),
        NOT(has_inbound_pair_tag("hunting")),
        NOT(has_ephemeral("grieving")),
    ),
    branches=(
        Branch(
            label="Find games and company",
            conditions=AND(PUBLIC_MEETING_PLACE, NOT(is_hidden())),
            narrative_stub=(
                "{actor} joins whatever the room is playing at — dice, "
                "cards, darts, argument — for stakes small enough to laugh "
                "about and company good enough to stay for."
            ),
            state_delta={
                "character.current_activity": "at games in company",
            },
            event_type="recreation_taken",
            changed_fields=("character.current_activity",),
            magnitude=0.15,
            mood_affinities={"elated": 1.5},
        ),
        Branch(
            label="Lose an hour to the loved thing",
            conditions=has_any_tag(
                "musician",
                "artist",
                "writer",
                "scholar",
                "dancer",
                "performer",
                "loremaster",
            ),
            narrative_stub=(
                "{actor} returns to the thing they love with no audience "
                "and no deadline — playing, sketching, reading — the "
                "version of their craft that belongs to no one else."
            ),
            state_delta={
                "character.current_activity": "lost in a loved pastime",
            },
            event_type="recreation_taken",
            changed_fields=("character.current_activity",),
            magnitude=0.14,
        ),
        Branch(
            label="Watch the world go by",
            conditions=time_of_day_in("evening", "night"),
            narrative_stub=(
                "{actor} claims a seat with a view of other people's "
                "evenings and lets the spectacle of ordinary life be the "
                "entertainment."
            ),
            state_delta={
                "character.current_activity": "watching the world go by",
            },
            event_type="recreation_taken",
            changed_fields=("character.current_activity",),
            magnitude=0.10,
        ),
        Branch(
            label="Take a small private pleasure",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} gives themselves a modest hour — a familiar "
                "comfort, an idle game, a stretch of doing nothing in "
                "particular — and does not apologize for it."
            ),
            state_delta={
                "character.current_activity": "taking a small pleasure",
            },
            event_type="recreation_taken",
            changed_fields=("character.current_activity",),
            magnitude=0.08,
        ),
    ),
)


START_RELOCATION_PLAN = Template(
    id="start_relocation_plan",
    priority=17,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A relocation plan begins only after repeated local routine plus a "
        "recent negative signal; the narrow gate lets it interrupt the mundane "
        "floor without becoming ambient project noise."
    ),
    blurb=(
        "Repeated local maintenance and a fresh setback become an explicit "
        "decision to leave."
    ),
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        project_due("start"),
        has_minimal_context(),
        at_routine_anchor("home"),
        NOT(is_constrained()),
        NOT(is_in_transit()),
        OR(
            count_recent_events_at_least("upkeep_done", within_ticks=30, min_count=2),
            count_recent_events_at_least("errands_run", within_ticks=30, min_count=2),
            count_recent_events_at_least(
                "recreation_taken", within_ticks=30, min_count=2
            ),
            count_recent_events_at_least(
                "work_performed", within_ticks=30, min_count=2
            ),
        ),
        OR(
            recent_event("travel_delayed", within_ticks=12, actor_slot=Slot.ACTOR),
            recent_event("contact_deferred", within_ticks=12, actor_slot=Slot.ACTOR),
            recent_event("threat_issued", within_ticks=12, target_slot=Slot.ACTOR),
            recent_event(
                "retaliation_attempted", within_ticks=12, target_slot=Slot.ACTOR
            ),
        ),
    ),
    branches=(
        Branch(
            label="Begin putting something aside",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} stops treating departure as the thought that arrives "
                "after a bad day. They make a ledger, name what it would cost, "
                "and put the first real thing aside."
            ),
            state_delta={
                "project.start": {
                    "project_type": "plan_relocation",
                    "stage": "saving",
                    "milestone": True,
                }
            },
            event_type="relocation_plan_started",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stage",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.40,
        ),
    ),
)


ADVANCE_RELOCATION_PLAN = Template(
    id="advance_relocation_plan",
    priority=47,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A due relocation plan occupies SURVEIL's adjacent priority slot; "
        "SURVEIL yields while the project is due, so project work displaces "
        "surveillance idling while its cadence protects maintenance wins."
    ),
    blurb=(
        "A due relocation plan saves, scouts, commits, stalls, or reaches its "
        "travel handoff."
    ),
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        project_due("ready"),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        # A due project yields to the embodied floor. The need writer clears
        # debt when those packages fire, so this delays rather than starves the
        # project while keeping eating, drinking, and sleep intact.
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
    ),
    branches=(
        Branch(
            label="Commit to the road",
            conditions=project_due("completion"),
            narrative_stub=(
                "{actor} makes the final commitment. The chosen place stops "
                "being a possibility and becomes a destination; the project "
                "ends where the journey begins."
            ),
            state_delta={
                "project.complete": {
                    "mode": "mixed",
                    "initial_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="relocation_plan_completed",
            changed_fields=(
                "character_project_states.status",
                "character_travel_states.status",
                "character_travel_states.destination_place_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Let the plan go rather than live in limbo",
            conditions=project_due("abandon"),
            narrative_stub=(
                "{actor} opens the plan one last time and recognizes that it "
                "has become a ritual of not leaving. They close the ledger and "
                "release the future it had been holding hostage."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "stalled_or_overdue",
                    "milestone": True,
                }
            },
            event_type="relocation_plan_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Turn the savings into a search",
            conditions=project_due("saving_milestone"),
            narrative_stub=(
                "{actor} has enough margin now to stop counting and start "
                "looking. Prices become neighborhoods, routes, and actual "
                "doors they might one day close behind them."
            ),
            state_delta={
                "project.advance": {
                    "stage": "scouting",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="relocation_plan_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Choose the place and begin committing",
            conditions=project_due("scouting_milestone"),
            narrative_stub=(
                "{actor} stops comparing exits. One place has survived every "
                "practical objection, and choosing it turns research into a "
                "promise with consequences."
            ),
            state_delta={
                "project.advance": {
                    "stage": "committing",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="relocation_plan_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Put another share aside",
            conditions=project_due("saving"),
            narrative_stub=(
                "{actor} makes the unremarkable sacrifice the plan requires: "
                "one expense refused, one small reserve protected from the "
                "present."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="relocation_plan_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Scout a candidate place",
            conditions=AND(
                project_due("scouting_without_target"),
                has_location_class_destination(
                    "dwelling", "haven", "urban_sparse", "urban_dense"
                ),
            ),
            narrative_stub=(
                "{actor} follows one candidate past the fantasy of it: cost, "
                "distance, the shape of an ordinary morning there. For the "
                "first time, the plan has a place attached."
            ),
            state_delta={
                "project.advance": {
                    "progress_delta": 0.50,
                    "select_target": True,
                    "destination_place_classes": [
                        "dwelling",
                        "haven",
                        "urban_sparse",
                        "urban_dense",
                    ],
                }
            },
            event_type="relocation_plan_progressed",
            changed_fields=(
                "character_project_states.target_place_id",
                "character_project_states.progress",
            ),
            magnitude=0.20,
            promotable=False,
        ),
        Branch(
            label="Lose ground to a setback",
            conditions=project_due("neglected"),
            narrative_stub=(
                "The present takes its cut from {actor}'s future: an expense, "
                "a closed option, a promise that cannot yet be kept. The plan "
                "stalls, but it is not silently erased."
            ),
            state_delta={"project.stall": {"increment": 1}},
            event_type="relocation_plan_stalled",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stall_count",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.10,
            promotable=False,
        ),
        Branch(
            label="Press on with the next practical step",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} does the next small thing the move requires — a "
                "message, a form, a measured risk — work too ordinary to look "
                "like transformation until enough of it accumulates."
            ),
            state_delta={"project.advance": {"progress_delta": 0.25}},
            event_type="relocation_plan_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.16,
            promotable=False,
        ),
    ),
)


START_RECRUIT_ALLY = Template(
    id="start_recruit_ally",
    priority=17,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A recruitment begins only for a known, warm, or trusted candidate; "
        "the narrow pair gate lets explicit positive intent rise above routine."
    ),
    blurb="A plausible contact becomes the named target of a recruitment project.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    starts_from_social_contact=True,
    package_gate=AND(
        project_due("start", project_type="recruit_ally"),
        has_minimal_context(),
        at_routine_anchor("home"),
        NOT(is_constrained()),
        NOT(is_in_transit()),
        OR(
            AND(
                has_contact_of_kind("social"),
                has_pair_tag("contact:social"),
            ),
            has_relationship_of_type("friend", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("friend", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("companion", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("companion", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("comrade", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("comrade", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("chosen_kin", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("chosen_kin", Slot.TARGET, Slot.ACTOR),
            trust_at_least(1),
        ),
        lacks_pair_tag("ally", Slot.ACTOR, Slot.TARGET),
        NOT(
            has_any_pair_tag(
                "hostile_to",
                "hunting",
                subject_slot=Slot.ACTOR,
                object_slot=Slot.TARGET,
            )
        ),
        NOT(
            has_any_pair_tag(
                "hostile_to",
                "hunting",
                subject_slot=Slot.TARGET,
                object_slot=Slot.ACTOR,
            )
        ),
    ),
    branches=(
        Branch(
            label="Sound out a possible ally",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} stops treating {target} as merely useful company. "
                "A careful conversation tests whether shared concern might "
                "become a commitment both can name."
            ),
            state_delta={
                "project.start": {
                    "project_type": "recruit_ally",
                    "stage": "sounding_out",
                    "milestone": True,
                }
            },
            event_type="recruit_ally_started",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stage",
                "character_project_states.target_character_entity_id",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.40,
        ),
    ),
)


ADVANCE_RECRUIT_ALLY = Template(
    id="advance_recruit_ally",
    priority=47,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A due recruitment shares relocation's vigilance-adjacent slot; "
        "SURVEIL yields to either due project while cadence and embodied "
        "guards preserve routine stability."
    ),
    blurb=(
        "A due recruitment sounds out its chosen candidate, earns trust, "
        "seals commitment, stalls, or ends."
    ),
    required_slots=(Slot.ACTOR, Slot.TARGET),
    binds_project_target=True,
    package_gate=AND(
        project_due("ready", project_type="recruit_ally"),
        project_target_is(Slot.TARGET),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
    ),
    branches=(
        Branch(
            label="End a recruitment whose candidate is no longer available",
            conditions=NOT(project_target_is_active(Slot.TARGET)),
            narrative_stub=(
                "{actor}'s intended recruit is no longer someone an alliance "
                "can be made with. The project ends cleanly rather than "
                "holding open a promise that cannot be answered."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "target_inactive_or_non_character",
                    "milestone": True,
                }
            },
            event_type="recruit_ally_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Seal the alliance",
            conditions=AND(
                project_due("completion", project_type="recruit_ally"),
                NOT(
                    has_any_pair_tag(
                        "hostile_to",
                        "hunting",
                        subject_slot=Slot.TARGET,
                        object_slot=Slot.ACTOR,
                    )
                ),
                NOT(trust_below(-2, Slot.TARGET, Slot.ACTOR)),
            ),
            narrative_stub=(
                "{actor} and {target} stop speaking in contingencies. The "
                "understanding becomes a commitment: when the cost arrives, "
                "{actor} may call on {target} as an ally."
            ),
            state_delta={
                "project.complete": {"milestone": True},
                "entity_pair_tags.add_outbound": ["ally"],
            },
            event_type="recruit_ally_completed",
            changed_fields=(
                "character_project_states.status",
                "entity_pair_tags",
                "character_relationships.relationship_type",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Withdraw after a hostile turn",
            conditions=OR(
                has_any_pair_tag(
                    "hostile_to",
                    "hunting",
                    subject_slot=Slot.TARGET,
                    object_slot=Slot.ACTOR,
                ),
                trust_below(-2, Slot.TARGET, Slot.ACTOR),
            ),
            narrative_stub=(
                "Whatever possibility {actor} saw in {target} has hardened "
                "into danger or contempt. {actor} ends the recruitment before "
                "hope becomes leverage in hostile hands."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "target_hostile_or_trust_collapsed",
                    "milestone": True,
                }
            },
            event_type="recruit_ally_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Let the recruitment go rather than force it",
            conditions=project_due("abandon", project_type="recruit_ally"),
            narrative_stub=(
                "{actor} admits that the invitation has become a ritual of "
                "delay. They stop pressing {target} for a promise that is not "
                "coming and release the unfinished alliance."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "stalled_or_overdue",
                    "milestone": True,
                }
            },
            event_type="recruit_ally_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Turn interest into earned trust",
            conditions=project_due(
                "sounding_out_milestone", project_type="recruit_ally"
            ),
            narrative_stub=(
                "{target} has heard enough to take the possibility seriously. "
                "Now {actor} must prove that the offered alliance is reliable, "
                "not merely attractive."
            ),
            state_delta={
                "project.advance": {
                    "stage": "earning_trust",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="recruit_ally_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Ask for a real commitment",
            conditions=project_due(
                "earning_trust_milestone", project_type="recruit_ally"
            ),
            narrative_stub=(
                "The small proofs have accumulated. {actor} can finally ask "
                "{target} for the thing underneath them: a commitment that "
                "will still hold when cooperation becomes costly."
            ),
            state_delta={
                "project.advance": {
                    "stage": "sealing_commitment",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="recruit_ally_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Lose ground through neglect",
            conditions=project_due("neglected", project_type="recruit_ally"),
            narrative_stub=(
                "Silence does work of its own. A missed promise or unanswered "
                "opening leaves {target} less certain that {actor}'s proposed "
                "alliance deserves the risk."
            ),
            state_delta={"project.stall": {"increment": 1}},
            event_type="recruit_ally_stalled",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stall_count",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.10,
            promotable=False,
            preemptive=True,
        ),
        Branch(
            label="Learn what the candidate actually wants",
            conditions=project_due("sounding_out", project_type="recruit_ally"),
            narrative_stub=(
                "{actor} listens past {target}'s first answer and learns what "
                "would make an alliance matter to them, not merely to its "
                "would-be recruiter."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="recruit_ally_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Prove reliable in a small consequential way",
            conditions=project_due("earning_trust", project_type="recruit_ally"),
            narrative_stub=(
                "{actor} gives {target} evidence instead of assurances: one "
                "promise kept where breaking it would have been easier."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="recruit_ally_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Make the next commitment concrete",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} and {target} make one more expectation explicit — "
                "who answers, what each protects, and what neither will ask "
                "the other to pretend away."
            ),
            state_delta={"project.advance": {"progress_delta": 0.25}},
            event_type="recruit_ally_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.16,
            promotable=False,
        ),
    ),
)


START_PURSUE_ROMANCE = Template(
    id="start_pursue_romance",
    priority=17,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A courtship begins only around existing social plausibility and shares "
        "the established project-entry priority."
    ),
    blurb="An off-screen character makes a named person the focus of a courtship.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    starts_from_social_contact=True,
    package_gate=AND(
        project_due("start", project_type="pursue_romance"),
        has_minimal_context(),
        at_routine_anchor("home"),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
        OR(
            AND(
                has_contact_of_kind("social"),
                has_pair_tag("contact:social"),
            ),
            has_relationship_of_type("friend", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("friend", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("companion", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("companion", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("comrade", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("comrade", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("chosen_kin", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("chosen_kin", Slot.TARGET, Slot.ACTOR),
            trust_at_least(1),
            has_pair_tag("contact:intimate", Slot.ACTOR, Slot.TARGET),
        ),
        NOT(
            has_any_pair_tag(
                "hostile_to",
                "hunting",
                subject_slot=Slot.ACTOR,
                object_slot=Slot.TARGET,
            )
        ),
        NOT(
            has_any_pair_tag(
                "hostile_to",
                "hunting",
                subject_slot=Slot.TARGET,
                object_slot=Slot.ACTOR,
            )
        ),
        *(
            NOT(has_symmetric_relationship_of_type(relationship_type))
            for relationship_type in sorted(ESTABLISHED_PARTNER_RELATIONSHIP_TYPES)
        ),
        NOT(has_tag("partnered_exclusively")),
        NOT(has_tag("married")),
        # The canonical suppressor set (shared with the intimacy band) also
        # blocks grieving and libido_absent — courtship defers to the same
        # availability concept intimacy behavior does.
        NOT(has_any_intimacy_suppressor()),
    ),
    branches=(
        Branch(
            label="Begin testing the waters",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} lets {target} see that their attention is no longer "
                "merely friendly, offering one small opening without demanding "
                "an answer before either of them is ready."
            ),
            state_delta={
                "project.start": {
                    "project_type": "pursue_romance",
                    "stage": "testing_waters",
                    "milestone": True,
                }
            },
            event_type="pursue_romance_started",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stage",
                "character_project_states.target_character_entity_id",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.40,
        ),
    ),
)


ADVANCE_PURSUE_ROMANCE = Template(
    id="advance_pursue_romance",
    priority=47,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A due courtship shares the established project-continuation slot while "
        "cadence and embodied guards preserve routine stability."
    ),
    blurb=(
        "A due courtship tests the waters, grows closer, declares intention, "
        "stalls, is rebuffed, or becomes mutual."
    ),
    required_slots=(Slot.ACTOR, Slot.TARGET),
    binds_project_target=True,
    package_gate=AND(
        project_due("ready", project_type="pursue_romance"),
        project_target_is(Slot.TARGET),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
    ),
    branches=(
        Branch(
            label="End a courtship whose target is no longer available",
            conditions=NOT(project_target_is_active(Slot.TARGET)),
            narrative_stub=(
                "{target} is no longer someone this courtship can reach. "
                "{actor} releases the hope rather than preserving an impossible "
                "promise."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "target_inactive_or_non_character",
                    "milestone": True,
                }
            },
            event_type="pursue_romance_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Declare the feeling and be answered",
            conditions=AND(
                project_due("completion", project_type="pursue_romance"),
                relationship_is_mutual_warm(Slot.ACTOR, Slot.TARGET),
                # Trust is valence-derived while hostility is a pair tag, so
                # the two can coexist; without this exclusion the completion
                # arm outruns the rebuffed arm (recruit_ally's seal carries
                # the same guard).
                NOT(
                    has_any_pair_tag(
                        "hostile_to",
                        "hunting",
                        subject_slot=Slot.ACTOR,
                        object_slot=Slot.TARGET,
                    )
                ),
                NOT(
                    has_any_pair_tag(
                        "hostile_to",
                        "hunting",
                        subject_slot=Slot.TARGET,
                        object_slot=Slot.ACTOR,
                    )
                ),
            ),
            narrative_stub=(
                "{actor} finally names what has grown between them, and "
                "{target} answers with warmth of their own. The courtship "
                "becomes a relationship both can recognize."
            ),
            state_delta={
                "project.complete": {"milestone": True},
                "entity_pair_tags.add_outbound": ["contact:intimate"],
                "mood.set": {"mood": "elated"},
            },
            event_type="pursue_romance_completed",
            changed_fields=(
                "character_project_states.status",
                "entity_pair_tags",
                "character_relationships.relationship_type",
                "entity_tags",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Withdraw after being rebuffed",
            conditions=OR(
                has_any_pair_tag(
                    "hostile_to",
                    "hunting",
                    subject_slot=Slot.ACTOR,
                    object_slot=Slot.TARGET,
                ),
                has_any_pair_tag(
                    "hostile_to",
                    "hunting",
                    subject_slot=Slot.TARGET,
                    object_slot=Slot.ACTOR,
                ),
                trust_below(-1, Slot.TARGET, Slot.ACTOR),
            ),
            narrative_stub=(
                "{target}'s answer closes the possibility, whether through "
                "plain refusal, disapproval, or danger. {actor} stops pursuing "
                "what is not mutual."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "target_rebuffed_or_hostile",
                    "milestone": True,
                },
                "mood.set": {"mood": "sour"},
            },
            event_type="pursue_romance_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
                "entity_tags",
            ),
            magnitude=0.40,
            # Deliberately preemptive with NO affinity: a rebuff is a
            # deterministic guard (the family contract recruit_ally's
            # withdraw arm shares), never a stochastic lean — affinities
            # are inert on preemptive arms by design.
            preemptive=True,
        ),
        Branch(
            label="Let the courtship go rather than force it",
            conditions=project_due("abandon", project_type="pursue_romance"),
            narrative_stub=(
                "Delay has become its own answer. {actor} stops asking the "
                "unfinished courtship to become something it has not become."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "stalled_or_overdue",
                    "milestone": True,
                }
            },
            event_type="pursue_romance_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Let tentative interest become closeness",
            conditions=project_due(
                "testing_waters_milestone", project_type="pursue_romance"
            ),
            narrative_stub=(
                "The first openings have been met rather than ignored. {actor} "
                "and {target} begin making room for a closeness neither needs "
                "to disguise as accident."
            ),
            state_delta={
                "project.advance": {
                    "stage": "growing_closer",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="pursue_romance_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Move from closeness toward declared intention",
            conditions=project_due(
                "growing_closer_milestone", project_type="pursue_romance"
            ),
            narrative_stub=(
                "What has grown between them is too deliberate to leave "
                "unnamed. {actor} prepares to say plainly what they want and "
                "hear plainly what {target} wants in return."
            ),
            state_delta={
                "project.advance": {
                    "stage": "declaring_intentions",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="pursue_romance_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Lose romantic ground through neglect",
            conditions=project_due("neglected", project_type="pursue_romance"),
            narrative_stub=(
                "Unanswered openings and postponed honesty do their own work. "
                "The courtship stalls, still possible but less certain."
            ),
            state_delta={"project.stall": {"increment": 1}},
            event_type="pursue_romance_stalled",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stall_count",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.10,
            promotable=False,
            preemptive=True,
        ),
        Branch(
            label="Offer another honest opening",
            conditions=project_due("testing_waters", project_type="pursue_romance"),
            narrative_stub=(
                "{actor} offers {target} another unmistakably personal opening "
                "and pays attention to whether it is welcomed."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="pursue_romance_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Build closeness through chosen time",
            conditions=project_due("growing_closer", project_type="pursue_romance"),
            narrative_stub=(
                "{actor} and {target} choose time together that asks for more "
                "attention and trust than ordinary company."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="pursue_romance_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Make the next intention legible",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} makes one more part of their intention legible, "
                "leaving {target} room for an answer that is genuinely theirs."
            ),
            state_delta={"project.advance": {"progress_delta": 0.25}},
            event_type="pursue_romance_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.16,
            promotable=False,
            mood_affinities={"elated": 1.5},
        ),
    ),
)


START_COURT_PATRON = Template(
    id="start_court_patron",
    priority=17,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Courting a patron requires both a plausible social opening and a "
        "specific marker of the target's power."
    ),
    blurb="An off-screen character begins working to win a named power's favor.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    starts_from_social_contact=True,
    package_gate=AND(
        project_due("start", project_type="court_patron"),
        has_minimal_context(),
        at_routine_anchor("home"),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
        OR(
            AND(has_contact_of_kind("social"), has_pair_tag("contact:social")),
            has_relationship_of_type("friend", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("friend", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("companion", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("companion", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("comrade", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("comrade", Slot.TARGET, Slot.ACTOR),
            has_relationship_of_type("chosen_kin", Slot.ACTOR, Slot.TARGET),
            has_relationship_of_type("chosen_kin", Slot.TARGET, Slot.ACTOR),
            trust_at_least(1),
        ),
        OR(
            has_any_status_at_or_above("senior", Slot.TARGET),
            has_tag("leader", Slot.TARGET),
            has_pair_tag("authority_over", Slot.TARGET, Slot.ACTOR),
        ),
        lacks_pair_tag("sponsors", Slot.TARGET, Slot.ACTOR),
        NOT(has_relationship_of_type("patron", Slot.ACTOR, Slot.TARGET)),
        NOT(
            has_any_pair_tag(
                "hostile_to",
                "hunting",
                subject_slot=Slot.ACTOR,
                object_slot=Slot.TARGET,
            )
        ),
        NOT(
            has_any_pair_tag(
                "hostile_to",
                "hunting",
                subject_slot=Slot.TARGET,
                object_slot=Slot.ACTOR,
            )
        ),
    ),
    branches=(
        Branch(
            label="Begin seeking the patron's notice",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} stops hoping that {target} will notice them by accident. "
                "They choose a first gesture calculated to be useful, visible, "
                "and difficult to mistake for idle flattery."
            ),
            state_delta={
                "project.start": {
                    "project_type": "court_patron",
                    "stage": "gaining_notice",
                    "milestone": True,
                }
            },
            event_type="court_patron_started",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stage",
                "character_project_states.target_character_entity_id",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.40,
        ),
    ),
)


ADVANCE_COURT_PATRON = Template(
    id="advance_court_patron",
    priority=47,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A due patronage effort shares the established project-continuation "
        "slot while SURVEIL yields to its bound two-party work."
    ),
    blurb=(
        "A due patronage effort gains notice, proves worth, secures favor, "
        "stalls, is spurned, or ends."
    ),
    required_slots=(Slot.ACTOR, Slot.TARGET),
    binds_project_target=True,
    package_gate=AND(
        project_due("ready", project_type="court_patron"),
        project_target_is(Slot.TARGET),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
    ),
    branches=(
        Branch(
            label="End a patronage effort whose target is no longer available",
            conditions=NOT(project_target_is_active(Slot.TARGET)),
            narrative_stub=(
                "{target} is no longer someone whose favor can be won. {actor} "
                "closes the effort rather than courting a power that cannot answer."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "target_inactive_or_non_character",
                    "milestone": True,
                }
            },
            event_type="court_patron_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Secure the patron's favor",
            conditions=AND(
                project_due("completion", project_type="court_patron"),
                trust_at_least(2, Slot.TARGET, Slot.ACTOR),
                NOT(
                    has_any_pair_tag(
                        "hostile_to",
                        "hunting",
                        subject_slot=Slot.ACTOR,
                        object_slot=Slot.TARGET,
                    )
                ),
                NOT(
                    has_any_pair_tag(
                        "hostile_to",
                        "hunting",
                        subject_slot=Slot.TARGET,
                        object_slot=Slot.ACTOR,
                    )
                ),
            ),
            narrative_stub=(
                "{target} finally answers {actor}'s service with public favor. "
                "The protection is real, and so is the obligation attached to it."
            ),
            state_delta={
                "project.complete": {"milestone": True},
                "entity_pair_tags.add_inbound": ["sponsors"],
                "entity_pair_tags.add_outbound": ["obligation"],
            },
            event_type="court_patron_completed",
            changed_fields=(
                "character_project_states.status",
                "entity_pair_tags",
                "character_relationships.relationship_type",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Withdraw after being spurned",
            conditions=OR(
                has_any_pair_tag(
                    "hostile_to",
                    "hunting",
                    subject_slot=Slot.ACTOR,
                    object_slot=Slot.TARGET,
                ),
                has_any_pair_tag(
                    "hostile_to",
                    "hunting",
                    subject_slot=Slot.TARGET,
                    object_slot=Slot.ACTOR,
                ),
                trust_below(-1, Slot.TARGET, Slot.ACTOR),
            ),
            narrative_stub=(
                "{target}'s answer is rejection, contempt, or danger. {actor} "
                "abandons the bid for favor before deference becomes humiliation."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "target_spurned_or_hostile",
                    "milestone": True,
                },
                "mood.set": {"mood": "sour"},
            },
            event_type="court_patron_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
                "entity_tags",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Let the bid for patronage go",
            conditions=project_due("abandon", project_type="court_patron"),
            narrative_stub=(
                "Delay has become its own refusal. {actor} stops spending effort "
                "on favor that never comes within reach."
            ),
            state_delta={
                "project.abandon": {"reason": "stalled_or_overdue", "milestone": True}
            },
            event_type="court_patron_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Turn notice into a chance to prove worth",
            conditions=project_due(
                "gaining_notice_milestone", project_type="court_patron"
            ),
            narrative_stub=(
                "{target} has noticed {actor}. Attention now becomes a test: "
                "whether usefulness survives scrutiny and inconvenience."
            ),
            state_delta={
                "project.advance": {
                    "stage": "proving_worth",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="court_patron_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Ask proven worth to become favor",
            conditions=project_due(
                "proving_worth_milestone", project_type="court_patron"
            ),
            narrative_stub=(
                "{actor} has supplied proof instead of promises. The remaining "
                "question is whether {target} will convert approval into favor."
            ),
            state_delta={
                "project.advance": {
                    "stage": "securing_favor",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="court_patron_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Lose ground through neglect",
            conditions=project_due("neglected", project_type="court_patron"),
            narrative_stub=(
                "Inattention erodes the impression {actor} worked to create. "
                "The bid for patronage stalls and must recover its momentum."
            ),
            state_delta={"project.stall": {"increment": 1}},
            event_type="court_patron_stalled",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stall_count",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.10,
            promotable=False,
            preemptive=True,
        ),
        Branch(
            label="Make useful work visible",
            conditions=project_due("gaining_notice", project_type="court_patron"),
            narrative_stub=(
                "{actor} places one useful act where {target} can see both its "
                "value and the judgment behind it."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="court_patron_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Prove reliable under scrutiny",
            conditions=project_due("proving_worth", project_type="court_patron"),
            narrative_stub=(
                "{actor} accepts a consequential task and performs it cleanly, "
                "giving {target} evidence that usefulness is not a pose."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="court_patron_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Make the next claim on favor legible",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} makes one more service, request, or allegiance explicit, "
                "bringing {target}'s answer closer without pretending it is owed."
            ),
            state_delta={"project.advance": {"progress_delta": 0.25}},
            event_type="court_patron_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.16,
            promotable=False,
            mood_affinities={"elated": 1.5},
        ),
    ),
)


START_SEEK_REDEMPTION = Template(
    id="start_seek_redemption",
    priority=17,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "Seeking redemption requires durable evidence of a wrong and an actor "
        "who is no longer actively hostile toward the wronged party."
    ),
    blurb="An off-screen character begins making amends to someone they wronged.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    starts_from_social_contact=True,
    composes_from_hostility=True,
    package_gate=AND(
        project_due("start", project_type="seek_redemption"),
        has_minimal_context(),
        at_routine_anchor("home"),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
        OR(
            trust_below(0, Slot.TARGET, Slot.ACTOR),
            has_symmetric_relationship_of_type("enemy", Slot.ACTOR, Slot.TARGET),
            has_symmetric_relationship_of_type("rival", Slot.ACTOR, Slot.TARGET),
            # #530 reachability contour closed by the ruled hostile source:
            # this directed evidence can now source the pair even when no
            # relationship row or social-contact edge exists.
            has_any_pair_tag(
                "hostile_to",
                "hunting",
                subject_slot=Slot.TARGET,
                object_slot=Slot.ACTOR,
            ),
        ),
        NOT(
            has_any_pair_tag(
                "hostile_to",
                "hunting",
                subject_slot=Slot.ACTOR,
                object_slot=Slot.TARGET,
            )
        ),
    ),
    branches=(
        Branch(
            label="Own the wrong",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} stops arranging the past into excuses. What they did "
                "to {target} becomes a wrong they can name, and therefore one "
                "they can begin trying to repair."
            ),
            state_delta={
                "project.start": {
                    "project_type": "seek_redemption",
                    "stage": "owning_the_wrong",
                    "milestone": True,
                }
            },
            event_type="seek_redemption_started",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stage",
                "character_project_states.target_character_entity_id",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.40,
        ),
    ),
)


ADVANCE_SEEK_REDEMPTION = Template(
    id="advance_seek_redemption",
    priority=47,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A due reconciliation effort shares the established continuation slot "
        "while SURVEIL yields to its bound two-party work."
    ),
    blurb=(
        "A due attempt at redemption owns the wrong, makes amends, seeks "
        "forgiveness, stalls, is thrown back, or ends."
    ),
    required_slots=(Slot.ACTOR, Slot.TARGET),
    binds_project_target=True,
    package_gate=AND(
        project_due("ready", project_type="seek_redemption"),
        project_target_is(Slot.TARGET),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
    ),
    branches=(
        Branch(
            label="End amends whose wronged party is no longer available",
            conditions=NOT(project_target_is_active(Slot.TARGET)),
            narrative_stub=(
                "{target} is no longer someone who can receive an attempt at "
                "amends. {actor} closes the effort rather than preserving an "
                "unanswerable claim to forgiveness."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "target_inactive_or_non_character",
                    "milestone": True,
                }
            },
            event_type="seek_redemption_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Have the amends accepted",
            conditions=AND(
                project_due("completion", project_type="seek_redemption"),
                NOT(
                    has_any_pair_tag(
                        "hostile_to",
                        "hunting",
                        subject_slot=Slot.ACTOR,
                        object_slot=Slot.TARGET,
                    )
                ),
                NOT(
                    has_any_pair_tag(
                        "hostile_to",
                        "hunting",
                        subject_slot=Slot.TARGET,
                        object_slot=Slot.ACTOR,
                    )
                ),
            ),
            narrative_stub=(
                "{target} accepts what {actor} has done to make amends. The "
                "history remains complicated, but it no longer dictates only "
                "hostility between them."
            ),
            state_delta={
                "project.complete": {"milestone": True},
                "entity_tags_target.remove": ["grudge_active"],
                "mood.set": {"mood": "elated"},
            },
            event_type="seek_redemption_completed",
            changed_fields=(
                "character_project_states.status",
                "entity_tags",
                "character_relationships.relationship_type",
                "character_relationships.emotional_valence",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Abandon amends that are thrown back",
            conditions=OR(
                trust_below(-2, Slot.TARGET, Slot.ACTOR),
                has_any_pair_tag(
                    "hostile_to",
                    "hunting",
                    subject_slot=Slot.ACTOR,
                    object_slot=Slot.TARGET,
                ),
                has_any_pair_tag(
                    "hostile_to",
                    "hunting",
                    subject_slot=Slot.TARGET,
                    object_slot=Slot.ACTOR,
                ),
            ),
            narrative_stub=(
                "The amends are thrown back in {actor}'s face. Whether the "
                "answer is hardened resentment or fresh hostility, {target} "
                "will not accept reconciliation on these terms."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "amends_spurned_or_hostility_hardened",
                    "milestone": True,
                },
                "mood.set": {"mood": "grim"},
            },
            event_type="seek_redemption_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
                "entity_tags",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Let the attempt at redemption go",
            conditions=project_due("abandon", project_type="seek_redemption"),
            narrative_stub=(
                "Delay has made the attempt another promise without repair. "
                "{actor} stops claiming that unfinished amends are progress."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "stalled_or_overdue",
                    "milestone": True,
                }
            },
            event_type="seek_redemption_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Turn ownership into amends",
            conditions=project_due(
                "owning_the_wrong_milestone", project_type="seek_redemption"
            ),
            narrative_stub=(
                "{actor} has named the wrong without qualification. Words now "
                "have to become repair shaped by what {target} actually lost."
            ),
            state_delta={
                "project.advance": {
                    "stage": "making_amends",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="seek_redemption_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Let amends ask for forgiveness",
            conditions=project_due(
                "making_amends_milestone", project_type="seek_redemption"
            ),
            narrative_stub=(
                "The repair is no longer hypothetical. {actor} leaves the last "
                "judgment with {target}: whether these amends can be accepted."
            ),
            state_delta={
                "project.advance": {
                    "stage": "earning_forgiveness",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="seek_redemption_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Lose ground through neglected amends",
            conditions=project_due("neglected", project_type="seek_redemption"),
            narrative_stub=(
                "Neglect makes the apology look like another demand for easy "
                "absolution. The attempt at redemption loses ground."
            ),
            state_delta={"project.stall": {"increment": 1}},
            event_type="seek_redemption_stalled",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stall_count",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.10,
            promotable=False,
            preemptive=True,
        ),
        Branch(
            label="Name the wrong without self-exoneration",
            conditions=project_due("owning_the_wrong", project_type="seek_redemption"),
            narrative_stub=(
                "{actor} examines one consequence from {target}'s side of the "
                "harm and removes another comforting excuse from the account."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="seek_redemption_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Make one concrete repair",
            conditions=project_due("making_amends", project_type="seek_redemption"),
            narrative_stub=(
                "{actor} makes one repair that costs them something and returns "
                "something meaningful to {target}."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="seek_redemption_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Leave forgiveness in the wronged party's hands",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} continues the work without treating forgiveness as a "
                "debt {target} now owes them."
            ),
            state_delta={"project.advance": {"progress_delta": 0.25}},
            event_type="seek_redemption_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.16,
            promotable=False,
            mood_affinities={"elated": 1.5},
        ),
    ),
)


START_BUILD_VENTURE = Template(
    id="start_build_venture",
    priority=17,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A venture begins from a stable home anchor and shares the proven "
        "project-entry priority with relocation and recruitment."
    ),
    blurb=(
        "An off-screen character turns a business, workshop, or crew from an "
        "idea into deliberate groundwork."
    ),
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        project_due("start", project_type="build_venture"),
        has_minimal_context(),
        at_routine_anchor("home"),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
        NOT(has_inbound_pair_tag("hostile_to")),
        NOT(has_inbound_pair_tag("hunting")),
    ),
    branches=(
        Branch(
            label="Lay the first groundwork",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} stops leaving the venture in the realm of someday. "
                "They name what it will do, what it will need, and the first "
                "piece of groundwork they can finish now."
            ),
            state_delta={
                "project.start": {
                    "project_type": "build_venture",
                    "stage": "laying_groundwork",
                    "milestone": True,
                }
            },
            event_type="build_venture_started",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stage",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.40,
        ),
    ),
)


ADVANCE_BUILD_VENTURE = Template(
    id="advance_build_venture",
    priority=47,
    drive_band=DriveBand.PROJECT_IDENTITY,
    priority_override_rationale=(
        "A due venture shares the established project-advance priority; its "
        "cadence and embodied floor preserve routine stability."
    ),
    blurb=(
        "A due venture lays groundwork, secures backing, opens doors, stalls, "
        "or ends."
    ),
    required_slots=(Slot.ACTOR,),
    package_gate=AND(
        project_due("ready", project_type="build_venture"),
        NOT(is_in_transit()),
        NOT(is_constrained()),
        NOT(
            OR(
                has_need_debt_at_or_above("sleep", 8),
                has_need_debt_at_or_above("thirst", 2),
                has_need_debt_at_or_above("hunger", 4),
            )
        ),
    ),
    branches=(
        Branch(
            label="Open the doors",
            conditions=project_due("completion", project_type="build_venture"),
            narrative_stub=(
                "The preparations stop being preparations. {actor} opens the "
                "doors, takes responsibility for what happens beyond them, "
                "and becomes the proprietor of something now alive in the world."
            ),
            state_delta={
                "project.complete": {"milestone": True},
                "entity_tags.add": ["proprietor"],
                "mood.set": {"mood": "elated"},
            },
            event_type="build_venture_completed",
            changed_fields=(
                "character_project_states.status",
                "entity_tags",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Let the venture go",
            conditions=project_due("abandon", project_type="build_venture"),
            narrative_stub=(
                "{actor} admits that the venture has become an obligation to "
                "an unopened future. They release it rather than feed another "
                "season into delay."
            ),
            state_delta={
                "project.abandon": {
                    "reason": "stalled_or_overdue",
                    "milestone": True,
                },
                "mood.set": {"mood": "grim"},
            },
            event_type="build_venture_abandoned",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.source_chunk_id",
                "entity_tags",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Turn groundwork into backing",
            conditions=project_due(
                "laying_groundwork_milestone", project_type="build_venture"
            ),
            narrative_stub=(
                "The shape is credible enough to show another person. {actor} "
                "stops refining the idea in private and begins securing the "
                "money, materials, promises, and labor that can hold it up."
            ),
            state_delta={
                "project.advance": {
                    "stage": "securing_backing",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="build_venture_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Turn backing into an opening",
            conditions=project_due(
                "securing_backing_milestone", project_type="build_venture"
            ),
            narrative_stub=(
                "Enough commitments now hold. {actor} turns from winning "
                "support to the last concrete work: a place in the world, a "
                "way of operating, and doors ready to open."
            ),
            state_delta={
                "project.advance": {
                    "stage": "opening_doors",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            event_type="build_venture_milestone",
            changed_fields=(
                "character_project_states.stage",
                "character_project_states.progress",
                "character_project_states.stall_count",
            ),
            magnitude=0.40,
            preemptive=True,
        ),
        Branch(
            label="Lose ground through neglect",
            conditions=project_due("neglected", project_type="build_venture"),
            narrative_stub=(
                "Unanswered messages and unfinished arrangements begin undoing "
                "what {actor} assembled. The venture stalls, still possible but "
                "no longer moving on its own momentum."
            ),
            state_delta={"project.stall": {"increment": 1}},
            event_type="build_venture_stalled",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.stall_count",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.10,
            promotable=False,
            preemptive=True,
        ),
        Branch(
            label="Make the venture legible",
            conditions=project_due("laying_groundwork", project_type="build_venture"),
            narrative_stub=(
                "{actor} turns another vague requirement into a concrete one: "
                "a cost counted, a service defined, or a necessary piece of "
                "work finished."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="build_venture_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Secure one more commitment",
            conditions=project_due("securing_backing", project_type="build_venture"),
            narrative_stub=(
                "{actor} wins one more commitment the venture can rely on: "
                "capital, material, labor, permission, or a promise with weight."
            ),
            state_delta={"project.advance": {"progress_delta": 0.35}},
            event_type="build_venture_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.18,
            promotable=False,
        ),
        Branch(
            label="Finish the next opening task",
            conditions=ALWAYS,
            narrative_stub=(
                "{actor} finishes one of the unglamorous tasks between backing "
                "and opening: a roster, a schedule, a key, a supply line, or "
                "the first promise to a customer."
            ),
            state_delta={"project.advance": {"progress_delta": 0.25}},
            event_type="build_venture_progressed",
            changed_fields=(
                "character_project_states.status",
                "character_project_states.progress",
                "character_project_states.next_eligible_at_world_time",
            ),
            magnitude=0.16,
            promotable=False,
            mood_affinities={"elated": 1.5},
        ),
    ),
)


BUILTIN_TEMPLATES = (
    EVADE_PURSUERS,
    PROTECT_KIN,
    EXTRACT_VENGEANCE,
    TEND_WOUNDED,
    HIDE,
    HONOR_DEBT,
    WARN_ALLY,
    SURVEIL,
    ADVANCE_RELOCATION_PLAN,
    ADVANCE_RECRUIT_ALLY,
    ADVANCE_BUILD_VENTURE,
    ADVANCE_PURSUE_ROMANCE,
    ADVANCE_COURT_PATRON,
    ADVANCE_SEEK_REDEMPTION,
    ACT_ON_INTEL,
    UNCOVER_PAST,
    CHECK_ON_DEPENDENT,
    CULTIVATE_INFORMANT,
    KEEP_VIGIL,
    REACH_OUT,
    CONSULT_RIVAL,
    MOURN_LOSS,
    ROUTINE_COMMUTE,
    TRAVEL,
    WORK,
    TEND_CRAFT,
    TRAIN,
    SLEEP,
    DRINK,
    EAT,
    SOCIALIZE,
    INTIMACY,
    RUN_ERRANDS,
    STROLL,
    UPKEEP,
    RECREATE,
    START_RELOCATION_PLAN,
    START_RECRUIT_ALLY,
    START_BUILD_VENTURE,
    START_PURSUE_ROMANCE,
    START_COURT_PATRON,
    START_SEEK_REDEMPTION,
    MAINTAIN_COVER,
)

# Enforce the issue #282 stage contract at import time: fame predicates are
# stage-2/3 vocabulary and must never appear in stage-1 entry gating. A
# fame-gated template added to this catalog raises immediately rather than
# relying on test coverage.
validate_no_fame_in_entry_gates(BUILTIN_TEMPLATES)
validate_no_mood_in_entry_gates(BUILTIN_TEMPLATES)
validate_mood_affinities(BUILTIN_TEMPLATES)

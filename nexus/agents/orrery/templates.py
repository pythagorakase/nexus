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
    has_ephemeral,
    has_tag,
    in_location_class,
    lacks_tag,
    recent_event,
    time_of_day_in,
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


BUILTIN_TEMPLATES = (
    EVADE_PURSUERS,
    HONOR_DEBT,
    PURSUE_GHOST_LEAD,
    MAINTAIN_COVER,
)

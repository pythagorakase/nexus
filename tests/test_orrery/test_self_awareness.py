"""Tests for package self-awareness (issue #282): stage-2 self-property reads."""

from typing import Optional

import pytest

from nexus.agents.orrery.substrate import (
    ALWAYS,
    AND,
    NOT,
    Branch,
    DriveBand,
    Slot,
    Template,
    TravelState,
    WorldState,
    evaluate,
    fame_at_or_above,
    fame_below,
    has_any_status_at_or_above,
    resources_at_or_above,
    resources_below,
    validate_no_fame_in_entry_gates,
)
from nexus.agents.orrery.templates import (
    BUILTIN_TEMPLATES,
    EVADE_PURSUERS,
    HIDE,
    MAINTAIN_COVER,
    SOCIALIZE,
    TEND_CRAFT,
    TRAVEL,
    WORK,
)

ACTOR = 1
PURSUER = 2
CONTACT = 3
FACTION = 40
PLACE = 7

ACTOR_BINDINGS = {Slot.ACTOR: ACTOR}


def _state(
    *,
    actor_tags: frozenset[str] = frozenset(),
    pair_tags: Optional[dict] = None,
    locations: Optional[dict] = None,
    location_classes: Optional[dict] = None,
    need_debt_scores: Optional[dict] = None,
    travel_states: Optional[dict] = None,
) -> WorldState:
    return WorldState(
        tags={ACTOR: actor_tags},
        pair_tags=pair_tags or {},
        locations=locations or {},
        location_classes=location_classes or {},
        need_debt_scores=need_debt_scores or {},
        travel_states=travel_states or {},
    )


# ---------------------------------------------------------------------------
# Predicate semantics
# ---------------------------------------------------------------------------


def test_fame_tiers_order_and_default_absent_reads_as_obscure() -> None:
    """Absence of a role.fame tag IS the obscure tier (default-absent)."""

    untagged = _state(actor_tags=frozenset({"fixer"}))
    assert fame_at_or_above("obscure")(untagged, ACTOR_BINDINGS)
    assert not fame_at_or_above("known")(untagged, ACTOR_BINDINGS)
    assert fame_below("known")(untagged, ACTOR_BINDINGS)
    assert not fame_below("obscure")(untagged, ACTOR_BINDINGS)

    renowned = _state(actor_tags=frozenset({"renowned"}))
    assert fame_at_or_above("known")(renowned, ACTOR_BINDINGS)
    assert fame_at_or_above("renowned")(renowned, ACTOR_BINDINGS)
    assert not fame_at_or_above("legendary")(renowned, ACTOR_BINDINGS)
    assert fame_below("legendary")(renowned, ACTOR_BINDINGS)
    assert not fame_below("renowned")(renowned, ACTOR_BINDINGS)


def test_resources_tiers_order_and_default_absent_reads_as_comfortable() -> None:
    """Absence of a role.resources tag IS the comfortable tier."""

    untagged = _state(actor_tags=frozenset({"fixer"}))
    assert resources_at_or_above("comfortable")(untagged, ACTOR_BINDINGS)
    assert not resources_at_or_above("wealthy")(untagged, ACTOR_BINDINGS)
    assert resources_below("wealthy")(untagged, ACTOR_BINDINGS)
    assert not resources_below("poor")(untagged, ACTOR_BINDINGS)

    destitute = _state(actor_tags=frozenset({"destitute"}))
    assert resources_below("poor")(destitute, ACTOR_BINDINGS)
    assert not resources_at_or_above("poor")(destitute, ACTOR_BINDINGS)

    magnate = _state(actor_tags=frozenset({"magnate"}))
    assert resources_at_or_above("magnate")(magnate, ACTOR_BINDINGS)
    assert not resources_below("magnate")(magnate, ACTOR_BINDINGS)


def test_tier_predicates_reject_unknown_tiers() -> None:
    with pytest.raises(ValueError, match="Unknown fame tier"):
        fame_at_or_above("celebrity")
    with pytest.raises(ValueError, match="Unknown fame tier"):
        fame_below("famous")
    with pytest.raises(ValueError, match="Unknown resources tier"):
        resources_at_or_above("rich")
    with pytest.raises(ValueError, match="Unknown resources tier"):
        resources_below("broke")


def test_tier_predicates_require_bound_entity() -> None:
    state = _state(actor_tags=frozenset({"legendary", "magnate"}))
    empty: dict = {}
    assert not fame_at_or_above("obscure")(state, empty)
    assert not fame_below("legendary")(state, empty)
    assert not resources_at_or_above("destitute")(state, empty)
    assert not resources_below("magnate")(state, empty)


def test_self_scoped_status_reads_outbound_edges_in_any_scope() -> None:
    """Status is scope-bound; the self read is outbound-any-scope."""

    senior = _state(
        pair_tags={(ACTOR, FACTION): frozenset({"status:senior"})},
    )
    assert has_any_status_at_or_above("senior")(senior, ACTOR_BINDINGS)
    assert has_any_status_at_or_above("junior")(senior, ACTOR_BINDINGS)
    assert not has_any_status_at_or_above("elite")(senior, ACTOR_BINDINGS)

    inbound_only = _state(
        pair_tags={(FACTION, ACTOR): frozenset({"status:senior"})},
    )
    assert not has_any_status_at_or_above("junior")(inbound_only, ACTOR_BINDINGS)

    negative = _state(
        pair_tags={(ACTOR, FACTION): frozenset({"status:pariah"})},
    )
    assert not has_any_status_at_or_above("junior")(negative, ACTOR_BINDINGS)

    with pytest.raises(ValueError, match="Unknown status level"):
        has_any_status_at_or_above("vip")


# ---------------------------------------------------------------------------
# Stage-1 guardrail: fame never gates package entry
# ---------------------------------------------------------------------------


def test_builtin_package_gates_never_read_fame() -> None:
    """The locked #282 stage contract holds for the whole built-in catalog."""

    validate_no_fame_in_entry_gates(BUILTIN_TEMPLATES)


def test_fame_in_entry_gate_is_rejected_even_when_nested() -> None:
    offender = Template(
        id="fame_gated_offender",
        priority=1,
        drive_band=DriveBand.PROJECT_IDENTITY,
        blurb="Illegally gates entry on the actor's fame.",
        required_slots=(Slot.ACTOR,),
        package_gate=AND(NOT(fame_below("renowned"))),
        branches=(
            Branch(
                label="noop",
                conditions=ALWAYS,
                narrative_stub="{actor} does nothing.",
            ),
        ),
    )
    with pytest.raises(ValueError, match="stage-2/3 only"):
        validate_no_fame_in_entry_gates((offender,))


# ---------------------------------------------------------------------------
# HIDE: the issue #282 worked example
# ---------------------------------------------------------------------------

_HIDDEN_BASE = frozenset({"fugitive"})


@pytest.mark.parametrize(
    ("profile_tags", "expected_branch"),
    (
        # The worked-example table from issue #282. The lay_low row maps to
        # HIDE's existing low-drama maintenance fallback.
        (
            frozenset({"cautious"}),
            "Preserve the silence another day",
        ),
        (
            frozenset({"known"}),
            "Change the face they show the street",
        ),
        (
            frozenset({"renowned", "wealthy"}),
            "Relocate to safer ground",
        ),
        (
            frozenset({"legendary", "magnate"}),
            "Erase the identity and vanish completely",
        ),
    ),
)
def test_hide_branch_selection_matches_issue_282_worked_example(
    profile_tags: frozenset[str], expected_branch: str
) -> None:
    state = _state(actor_tags=_HIDDEN_BASE | profile_tags)
    resolution = evaluate(HIDE, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == expected_branch


def test_hide_escalation_requires_affordability() -> None:
    """A famous actor who cannot pay for their tier takes a cheaper measure."""

    legendary_destitute = _state(
        actor_tags=_HIDDEN_BASE | frozenset({"legendary", "destitute"})
    )
    resolution = evaluate(HIDE, legendary_destitute, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Preserve the silence another day"

    legendary_wealthy = _state(
        actor_tags=_HIDDEN_BASE | frozenset({"legendary", "wealthy"})
    )
    resolution = evaluate(HIDE, legendary_wealthy, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Relocate to safer ground"


def test_hide_entry_gate_ignores_fame() -> None:
    """Stage 1: a legendary actor qualifies for HIDE exactly like an obscure one."""

    for fame_tag in ((), ("legendary",)):
        state = _state(actor_tags=_HIDDEN_BASE | frozenset(fame_tag))
        assert evaluate(HIDE, state, ACTOR_BINDINGS).passes


# ---------------------------------------------------------------------------
# EVADE_PURSUERS: the famous fixer no longer strolls into a crowd
# ---------------------------------------------------------------------------


def _pursued_state(actor_tags: frozenset[str]) -> WorldState:
    return _state(
        actor_tags=actor_tags,
        pair_tags={(PURSUER, ACTOR): frozenset({"hunting"})},
    )


def test_obscure_actor_still_blends_into_public_flow() -> None:
    state = _pursued_state(frozenset({"fixer"}))
    resolution = evaluate(EVADE_PURSUERS, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Keep moving, blend into public flow"


def test_renowned_actor_cannot_blend_and_scrambles_without_funds() -> None:
    state = _pursued_state(frozenset({"fixer", "renowned"}))
    resolution = evaluate(EVADE_PURSUERS, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Break line of sight without a clean route"


def test_renowned_wealthy_actor_buys_a_discreet_extraction() -> None:
    state = _pursued_state(frozenset({"fixer", "renowned", "wealthy"}))
    resolution = evaluate(EVADE_PURSUERS, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Buy a discreet extraction"


# ---------------------------------------------------------------------------
# MAINTAIN_COVER: visibility as cover for recognizable actors
# ---------------------------------------------------------------------------


def _cover_state(actor_tags: frozenset[str]) -> WorldState:
    return _state(
        actor_tags=actor_tags,
        locations={ACTOR: PLACE},
        location_classes={PLACE: frozenset({"urban_dense"})},
    )


def test_obscure_operative_runs_anonymous_courier_cover() -> None:
    state = _cover_state(frozenset({"fixer"}))
    resolution = evaluate(MAINTAIN_COVER, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Run a low-level courier job"


def test_renowned_operative_performs_the_expected_public_pattern() -> None:
    state = _cover_state(frozenset({"fixer", "renowned"}))
    resolution = evaluate(MAINTAIN_COVER, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Be seen exactly where they are expected"


# ---------------------------------------------------------------------------
# SOCIALIZE: fame and disposition shape where company is sought
# ---------------------------------------------------------------------------


def _social_state(
    actor_tags: frozenset[str],
    *,
    with_contact: bool = False,
    at_venue: bool = False,
) -> WorldState:
    pair_tags = (
        {(ACTOR, CONTACT): frozenset({"contact:social"})} if with_contact else {}
    )
    return _state(
        actor_tags=actor_tags,
        pair_tags=pair_tags,
        locations={ACTOR: PLACE},
        location_classes={PLACE: frozenset({"meeting" if at_venue else "dwelling"})},
        need_debt_scores={(ACTOR, "socialize"): 200.0},
    )


def test_obscure_actor_at_a_venue_still_goes_where_people_are() -> None:
    state = _social_state(frozenset({"gregarious"}), at_venue=True)
    resolution = evaluate(SOCIALIZE, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Go where people are"


def test_renowned_actor_hosts_chosen_company_instead_of_a_crowd() -> None:
    state = _social_state(frozenset({"renowned"}), with_contact=True, at_venue=True)
    resolution = evaluate(SOCIALIZE, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Host chosen company on their own ground"


def test_renowned_actor_without_contacts_falls_to_parasocial_company() -> None:
    state = _social_state(frozenset({"renowned"}), at_venue=True)
    resolution = evaluate(SOCIALIZE, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Practice parasocial company"


def test_solitary_actor_with_a_contact_prefers_a_trusted_voice() -> None:
    state = _social_state(frozenset({"solitary"}), with_contact=True, at_venue=True)
    resolution = evaluate(SOCIALIZE, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Seek a trusted voice rather than a crowd"


# ---------------------------------------------------------------------------
# WORK / TEND_CRAFT: resource-gated branches
# ---------------------------------------------------------------------------


def _work_state(actor_tags: frozenset[str]) -> WorldState:
    return _state(
        actor_tags=actor_tags | frozenset({"work_obligation"}),
        locations={ACTOR: PLACE},
        location_classes={PLACE: frozenset({"commerce"})},
    )


def test_destitute_actor_takes_whatever_paying_work_exists() -> None:
    resolution = evaluate(WORK, _work_state(frozenset({"destitute"})), ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Take whatever paying work the day offers"


def test_wealthy_actor_directs_rather_than_performs() -> None:
    resolution = evaluate(WORK, _work_state(frozenset({"magnate"})), ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Direct the work rather than perform it"


def test_comfortable_default_actor_still_works_the_shift() -> None:
    resolution = evaluate(WORK, _work_state(frozenset()), ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Work a public-facing shift"


def test_senior_status_anywhere_routes_work_to_administration() -> None:
    state = _state(
        actor_tags=frozenset({"work_obligation"}),
        pair_tags={(ACTOR, FACTION): frozenset({"status:senior"})},
        locations={ACTOR: PLACE},
        location_classes={PLACE: frozenset({"dwelling"})},
    )
    resolution = evaluate(WORK, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Keep administrative obligations moving"


def test_wealthy_crafter_puts_money_into_the_craft() -> None:
    state = _state(actor_tags=frozenset({"soldier", "wealthy"}))
    resolution = evaluate(TEND_CRAFT, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Put real money into the craft"


def test_comfortable_crafter_keeps_existing_craft_branch() -> None:
    state = _state(actor_tags=frozenset({"soldier"}))
    resolution = evaluate(TEND_CRAFT, state, ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Make the weapon ready for what comes next"


# ---------------------------------------------------------------------------
# TRAVEL: route style follows the traveler's own wealth and fame
# ---------------------------------------------------------------------------


def _travel_state(actor_tags: frozenset[str]) -> WorldState:
    return _state(
        actor_tags=actor_tags,
        travel_states={
            ACTOR: TravelState(status="at_place", destination_place_id=PLACE)
        },
    )


def test_wealthy_traveler_charters_private_transport() -> None:
    resolution = evaluate(TRAVEL, _travel_state(frozenset({"wealthy"})), ACTOR_BINDINGS)
    assert resolution.passes
    assert resolution.branch_label == "Charter private transport"
    assert resolution.state_delta["travel.start"]["mode"] == "vehicle"


def test_renowned_prepared_traveler_takes_covert_routes() -> None:
    resolution = evaluate(
        TRAVEL,
        _travel_state(frozenset({"renowned", "travel_ready"})),
        ACTOR_BINDINGS,
    )
    assert resolution.passes
    assert resolution.branch_label == "Slip out along covert routes"
    assert resolution.state_delta["travel.start"]["mode"] == "covert"


def test_renowned_unprepared_traveler_prepares_before_going_covert() -> None:
    resolution = evaluate(
        TRAVEL, _travel_state(frozenset({"renowned"})), ACTOR_BINDINGS
    )
    assert resolution.passes
    assert resolution.branch_label == "Prepare the journey rather than starting badly"


def test_ordinary_prepared_traveler_departs_normally() -> None:
    resolution = evaluate(
        TRAVEL, _travel_state(frozenset({"travel_ready"})), ACTOR_BINDINGS
    )
    assert resolution.passes
    assert resolution.branch_label == "Depart toward the planned destination"

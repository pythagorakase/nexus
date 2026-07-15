"""Coverage and parity tests for the leaf-predicate evidence resolver.

Two layers of guarantee, no mocks:

1. **Total factory coverage** — a synthetic rich state exercises every one of
   the 53 predicate factories exactly as authored, asserting the evidence
   resolver's recomputed verdict matches the real closure's return value and
   that the sweep visits every registered resolver. A new factory landing in
   substrate without an evidence resolver fails here (and fails the explain
   path loudly at runtime).
2. **Builtin template coverage** — every leaf in every builtin template's
   gate and branch trees resolves against every demo preset, so the grammar
   actually emitted by production templates is covered end to end.

The per-leaf verdict cross-check also runs inside ``trace_condition`` on
every explain, so the whole explain test suite doubles as a drift tripwire.
"""

from __future__ import annotations

import json

import pytest

from nexus.agents.orrery.demo import _all_preset_names, _resolve_preset
from nexus.agents.orrery.evidence import (
    _RESOLVERS,
    EvidenceResolutionError,
    resolve_evidence,
)
from nexus.agents.orrery.explain import explain_stack
from nexus.agents.orrery.substrate import (
    ALWAYS,
    EventRecord,
    ProjectPolicy,
    RoutineAnchor,
    Slot,
    TravelState,
    WorldState,
    _condition_tree_leaves,
    at_routine_anchor,
    away_from_routine_anchor,
    can_move_publicly,
    co_located,
    count_co_located,
    count_recent_events_at_least,
    direct_contact_is_dramatic,
    faction_member,
    fame_at_or_above,
    fame_below,
    has_any_current_tag,
    has_any_intimacy_suppressor,
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
    has_routine_anchor,
    has_severity_tag,
    has_severity_tag_at_or_above,
    has_symmetric_relationship_of_type,
    has_tag,
    has_travel_destination,
    in_location,
    in_location_class,
    is_constrained,
    is_hidden,
    is_in_transit,
    knows_recent_event,
    lacks_pair_tag,
    lacks_tag,
    project_due,
    recent_event,
    relationship_is_asymmetric,
    relationship_is_mutual_warm,
    relative_orbit_distance,
    resources_at_or_above,
    resources_below,
    routine_anchor_due,
    routine_anchor_has_destination,
    since_last_event_at_least,
    time_of_day_in,
    travel_progress_at_or_above,
    travel_purpose_is,
    travel_risk_is,
    trust_at_least,
    trust_below,
    weather_is,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from datetime import datetime

ACTOR, TARGET, FACTION_ID = 1, 2, 9
PLACE_ENTITY = 501

RICH_STATE = WorldState(
    tags={
        ACTOR: frozenset({"off_grid", "known", "wealthy", "route_familiar"}),
        TARGET: frozenset({"seeking_identity"}),
        3: frozenset({"public_role"}),
    },
    ephemeral_tags={ACTOR: frozenset({"grieving", "wound_3_severe"})},
    locations={ACTOR: 101, TARGET: 101, 3: 101, 4: 102},
    activities={ACTOR: "keeping watch"},
    trust={(ACTOR, TARGET): 2, (TARGET, ACTOR): 1},
    relationship_types={(ACTOR, TARGET): frozenset({"romantic"})},
    pair_tags={
        (ACTOR, TARGET): frozenset({"contact:social"}),
        (TARGET, ACTOR): frozenset({"hunting"}),
        (ACTOR, PLACE_ENTITY): frozenset({"contact:lodging"}),
        (ACTOR, FACTION_ID): frozenset({"status:senior"}),
    },
    faction_memberships={ACTOR: frozenset({FACTION_ID})},
    location_class={102: "transit"},
    location_classes={
        101: frozenset({"commerce", "meeting"}),
        102: frozenset({"transit"}),
    },
    location_entity_ids={101: PLACE_ENTITY},
    location_zones={101: 7, 102: 8},
    orbit_distance={(ACTOR, TARGET): 1},
    need_debt_scores={(ACTOR, "sleep"): 12.5},
    travel_states={
        ACTOR: TravelState(
            status="at_place",
            destination_place_id=102,
            progress_ratio=0.6,
            route_purpose="socialize",
            risk="low",
        ),
        4: TravelState(status="in_transit"),
    },
    project_policy=ProjectPolicy(enabled=True),
    routine_anchors={
        (ACTOR, "work"): RoutineAnchor(
            anchor_type="work",
            place_id=102,
            mobility_policy="fixed_place",
            schedule={"weekdays": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"},
        ),
    },
    recent_events=(
        EventRecord(event_type="threat_issued", tick=99, target_entity_id=ACTOR),
        EventRecord(event_type="contact_made", tick=95, actor_entity_id=ACTOR),
    ),
    time_of_day="night",
    world_time=datetime(2073, 5, 3, 11, 30),
    weather="rain",
    current_tick=100,
)

BINDINGS = {Slot.ACTOR: ACTOR, Slot.TARGET: TARGET, Slot.FACTION: FACTION_ID}

# One authored predicate per factory — the sweep below asserts this table
# covers every registered resolver, so a new factory cannot land silently.
FACTORY_SWEEP = [
    has_tag("off_grid"),
    lacks_tag("captive"),
    has_any_tag("off_grid", "public_role"),
    has_any_current_tag("grieving", "nonexistent"),
    has_ephemeral("grieving"),
    is_constrained(),
    is_hidden(),
    has_any_intimacy_suppressor(),
    has_severity_tag("wound"),
    has_severity_tag_at_or_above("wound", 2),
    fame_at_or_above("known"),
    fame_below("renowned"),
    resources_at_or_above("comfortable"),
    resources_below("magnate"),
    has_pair_tag("contact:social"),
    lacks_pair_tag("hunting"),
    has_any_pair_tag("hunting", "contact:social"),
    has_pair_tag_to_current_location("contact:lodging"),
    has_inbound_pair_tag("hunting"),
    has_contact_of_kind("social"),
    has_any_status_at_or_above("respected"),
    has_minimal_context(),
    can_move_publicly(),
    has_need_debt_at_or_above("sleep", 8),
    in_location_class("commerce"),
    has_location_class_destination("transit"),
    in_location(101),
    co_located(),
    count_co_located(2, with_tag="public_role", with_ephemeral="grieving"),
    count_co_located(1),
    has_established_partner_co_located(),
    is_in_transit(),
    has_travel_destination(),
    travel_progress_at_or_above(0.5),
    travel_purpose_is("socialize"),
    travel_risk_is("low", "moderate"),
    has_routine_anchor("work"),
    routine_anchor_due("work"),
    at_routine_anchor("work"),
    away_from_routine_anchor("work"),
    routine_anchor_has_destination("work"),
    trust_at_least(2),
    trust_below(5),
    relationship_is_mutual_warm(),
    relationship_is_asymmetric(),
    direct_contact_is_dramatic(),
    has_relationship_of_type("romantic"),
    has_symmetric_relationship_of_type("romantic", Slot.TARGET, Slot.ACTOR),
    faction_member(),
    relative_orbit_distance(2),
    time_of_day_in("night", "evening"),
    weather_is("clear"),
    recent_event("threat_issued", within_ticks=5, target_slot=Slot.ACTOR),
    recent_event(within_ticks=3),
    knows_recent_event("threat_issued", within_ticks=8, target_slot=Slot.TARGET),
    since_last_event_at_least("contact_made", 3),
    since_last_event_at_least("contact_made", 3, target_slot=Slot.TARGET),
    project_due("start"),
    count_recent_events_at_least("mourning_act", within_ticks=30, min_count=4),
    count_recent_events_at_least(
        "surveillance_performed",
        within_ticks=12,
        min_count=3,
        target_slot=Slot.TARGET,
    ),
]


def test_factory_sweep_covers_every_registered_resolver() -> None:
    """The sweep table and the resolver registry must stay in lockstep."""

    swept_kinds = {predicate.__name__.split("(", 1)[0] for predicate in FACTORY_SWEEP}
    assert swept_kinds == set(_RESOLVERS), (
        "factory sweep and evidence resolver registry disagree; "
        f"missing from sweep: {sorted(set(_RESOLVERS) - swept_kinds)}, "
        f"unregistered kinds: {sorted(swept_kinds - set(_RESOLVERS))}"
    )


@pytest.mark.parametrize("predicate", FACTORY_SWEEP, ids=lambda p: p.__name__)
def test_evidence_verdict_matches_predicate(predicate) -> None:
    """Parse-and-recompute must agree with the real closure, value for value."""

    evidence = resolve_evidence(predicate.__name__, RICH_STATE, BINDINGS)
    assert evidence["result"] == predicate(RICH_STATE, BINDINGS)
    assert evidence["kind"] == predicate.__name__.split("(", 1)[0]
    # Payloads are for the dashboard: they must round-trip through JSON.
    json.dumps(evidence)


def test_unbound_slots_resolve_honestly() -> None:
    """With no TARGET bound, evidence records the missing entity, not a lie."""

    predicate = has_pair_tag("contact:social")
    evidence = resolve_evidence(predicate.__name__, RICH_STATE, {Slot.ACTOR: ACTOR})
    assert evidence["entities"]["target"] is None
    assert evidence["result"] is False
    assert evidence["result"] == predicate(RICH_STATE, {Slot.ACTOR: ACTOR})


@pytest.mark.parametrize("preset_name", _all_preset_names())
def test_every_builtin_leaf_resolves_on_preset(preset_name: str) -> None:
    """Every gate and branch leaf of every builtin template has evidence."""

    state, bindings = _resolve_preset(preset_name)
    for template in BUILTIN_TEMPLATES:
        conditions = [template.package_gate]
        conditions.extend(branch.conditions for branch in template.branches)
        for condition in conditions:
            for leaf in _condition_tree_leaves(condition):
                name = getattr(leaf, "__name__", repr(leaf))
                evidence = resolve_evidence(name, state, bindings)
                if evidence["result"] is not None:
                    assert evidence["result"] == bool(leaf(state, bindings)), name


def test_family_evidence_names_the_matching_member() -> None:
    evidence = resolve_evidence(is_hidden().__name__, RICH_STATE, BINDINGS)
    assert evidence["matched"] == ["off_grid"]
    assert "hidden_tags" == evidence["params"]["family"]

    suppressor = resolve_evidence(
        has_any_intimacy_suppressor().__name__, RICH_STATE, BINDINGS
    )
    assert suppressor["matched"] == ["grieving"]


def test_observed_values_surface_for_thresholds() -> None:
    debt = resolve_evidence(
        has_need_debt_at_or_above("sleep", 8).__name__, RICH_STATE, BINDINGS
    )
    assert debt["observed"]["debt_score"] == 12.5
    assert debt["params"]["threshold"] == 8.0
    assert debt["result"] is True

    trust = resolve_evidence(trust_at_least(2).__name__, RICH_STATE, BINDINGS)
    assert trust["observed"]["trust"] == 2

    cooldown = resolve_evidence(
        since_last_event_at_least("contact_made", 3).__name__,
        RICH_STATE,
        BINDINGS,
    )
    assert cooldown["observed"]["latest_matching_tick"] == 95
    assert cooldown["observed"]["elapsed_ticks"] == 5
    assert cooldown["result"] is True


def test_inbound_pair_tag_evidence_names_the_subjects() -> None:
    evidence = resolve_evidence(
        has_inbound_pair_tag("hunting").__name__, RICH_STATE, BINDINGS
    )
    assert evidence["matched"] == [TARGET]


def test_severity_evidence_parses_track_levels() -> None:
    evidence = resolve_evidence(
        has_severity_tag_at_or_above("wound", 2).__name__, RICH_STATE, BINDINGS
    )
    assert evidence["observed"]["severity_track"] == [
        {"tag": "wound_3_severe", "level": 3}
    ]
    assert evidence["matched"] == ["wound_3_severe"]


def test_tier_evidence_reports_default_when_untagged() -> None:
    evidence = resolve_evidence(
        fame_at_or_above("known").__name__,
        RICH_STATE,
        {Slot.ACTOR: TARGET},
    )
    assert evidence["observed"]["resolved_tier"] == "obscure"
    assert evidence["observed"]["defaulted"] is True
    assert evidence["result"] is False


def test_always_never_and_unknown_names() -> None:
    assert resolve_evidence("ALWAYS", RICH_STATE, BINDINGS)["result"] is True
    assert resolve_evidence("NEVER", RICH_STATE, BINDINGS)["result"] is False
    assert resolve_evidence(ALWAYS.__name__, RICH_STATE, BINDINGS)["result"] is True

    with pytest.raises(EvidenceResolutionError, match="No evidence resolver"):
        resolve_evidence("summon_dragon(@actor)", RICH_STATE, BINDINGS)


def test_explain_stack_traces_carry_evidence() -> None:
    """The inspector consumes evidence through the explain payload."""

    state, bindings = _resolve_preset("hunted")
    explanation = explain_stack(BUILTIN_TEMPLATES, state, bindings)
    payload = json.loads(json.dumps(explanation.to_dict()))

    def _leaves(node: dict):
        if "children" in node:
            for child in node["children"]:
                yield from _leaves(child)
        else:
            yield node

    leaf_count = 0
    for template in payload["templates"]:
        for leaf in _leaves(template["gate_trace"]):
            assert leaf["evidence"] is not None
            assert leaf["evidence"]["result"] == leaf["result"]
            leaf_count += 1
        assert (
            "evidence" not in template["gate_trace"]
            or template["gate_trace"].get("children") is None
        )
    assert leaf_count > 50, "expected a full stack of explained leaves"

    winner = next(t for t in payload["templates"] if t["is_winner"])
    hunting_leaves = [
        leaf
        for leaf in _leaves(winner["gate_trace"])
        if leaf["evidence"]["kind"] == "has_inbound_pair_tag"
    ]
    assert hunting_leaves, "evade_pursuers gate reads the hunting pair tag"
    assert hunting_leaves[0]["evidence"]["matched"] == [2]


@pytest.mark.requires_postgres
def test_slot_backed_explain_carries_evidence_end_to_end() -> None:
    """Evidence must survive the full audit payload path on a real slot."""

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from nexus.agents.orrery.audit import explain_dry_run
    from nexus.api.slot_utils import get_slot_db_url
    from nexus.config import load_settings_as_dict

    orrery = load_settings_as_dict()["orrery"]
    engine = create_engine(get_slot_db_url(slot=2))
    try:
        with Session(engine) as session:
            report = explain_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=None,
                window_chunks=int(orrery["binding"]["window_chunks"]),
                sunhelm_settings=orrery.get("sunhelm"),
            )
    finally:
        engine.dispose()

    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["actors"], "save_02 is expected to bind off-screen actors"

    def _leaves(node: dict):
        if "children" in node:
            for child in node["children"]:
                yield from _leaves(child)
        else:
            yield node

    checked = 0
    for group in payload["actors"]:
        for template in group["actor_stack"]["templates"]:
            for leaf in _leaves(template["gate_trace"]):
                assert leaf["evidence"] is not None
                assert leaf["evidence"]["result"] == leaf["result"]
                checked += 1
    assert checked > 100, "expected slot-wide leaf evidence coverage"

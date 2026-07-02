"""Real-engine tests for the what-if override layer.

These apply overrides to the deterministic demo presets and re-run the
production ``evaluate_stack`` — no mocks, no database. Each flip below was
chosen because the preset makes the outcome fully deterministic: the
``hiding`` preset's winner (``hide``) gates on the absence of an inbound
``hunting`` pair tag, on the ``off_grid`` hidden tag, and on three event
cooldowns, so each override category can kill or redirect it through a
different door. Slot-backed what-if behavior (validation against live
vocabularies, diff payloads) is covered in
tests/test_api/test_orrery_dev_endpoints.py.
"""

from __future__ import annotations

import pytest

from nexus.agents.orrery.demo import _resolve_preset
from nexus.agents.orrery.explain import explain_stack
from nexus.agents.orrery.overrides import (
    EventOverride,
    LocationOverride,
    NeedOverride,
    OverrideValidationError,
    PairTagOverride,
    TagOverride,
    WorldStateOverrides,
    apply_overrides,
)
from nexus.agents.orrery.substrate import evaluate_stack
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES

ACTOR_ID = 1
TARGET_ID = 2


def _winner(state, bindings):
    resolution = evaluate_stack(BUILTIN_TEMPLATES, state, bindings)
    return resolution.template_id if resolution is not None else None


def test_pair_tag_add_redirects_hide_to_evade() -> None:
    """Injecting an inbound `hunting` pair tag turns concealment into flight."""

    state, bindings = _resolve_preset("hiding")
    assert _winner(state, bindings) == "hide"

    hunted = apply_overrides(
        state,
        WorldStateOverrides(
            pair_tags=(
                PairTagOverride(
                    subject_entity_id=TARGET_ID,
                    object_entity_id=ACTOR_ID,
                    tag="hunting",
                    op="add",
                ),
            )
        ),
    )
    assert _winner(hunted, bindings) == "evade_pursuers"
    # The original state is untouched.
    assert _winner(state, bindings) == "hide"
    assert (TARGET_ID, ACTOR_ID) not in state.pair_tags


def test_event_injection_respects_tick_arithmetic() -> None:
    """ticks_ago maps onto the cooldown window exactly.

    ``hide`` requires >= 6 ticks since the last ``hideout_maintained``; an
    injection at ticks_ago=0 kills it, the same injection at ticks_ago=10
    leaves it standing.
    """

    state, bindings = _resolve_preset("hiding")

    fresh = apply_overrides(
        state,
        WorldStateOverrides(
            events=(
                EventOverride(
                    event_type="hideout_maintained",
                    actor_entity_id=ACTOR_ID,
                    ticks_ago=0,
                ),
            )
        ),
    )
    assert _winner(fresh, bindings) is None

    stale = apply_overrides(
        state,
        WorldStateOverrides(
            events=(
                EventOverride(
                    event_type="hideout_maintained",
                    actor_entity_id=ACTOR_ID,
                    ticks_ago=10,
                ),
            )
        ),
    )
    assert _winner(stale, bindings) == "hide"
    # Injected events append after the hydrated ones with the derived tick.
    assert stale.recent_events[-1].tick == state.current_tick - 10


def test_tag_removal_kills_hidden_state() -> None:
    state, bindings = _resolve_preset("hiding")

    exposed = apply_overrides(
        state,
        WorldStateOverrides(
            tags=(TagOverride(entity_id=ACTOR_ID, tag="off_grid", op="remove"),)
        ),
    )
    assert _winner(exposed, bindings) is None
    assert "off_grid" in state.tags[ACTOR_ID]


def test_need_override_fires_sleep_over_maintain_cover() -> None:
    state, bindings = _resolve_preset("quiet")
    assert _winner(state, bindings) == "maintain_cover"

    tired = apply_overrides(
        state,
        WorldStateOverrides(
            needs=(
                NeedOverride(entity_id=ACTOR_ID, need_type="sleep", debt_score=20.0),
            )
        ),
    )
    assert _winner(tired, bindings) == "sleep"
    assert (ACTOR_ID, "sleep") not in state.need_debt_scores


def test_location_override_moves_actor() -> None:
    state, _ = _resolve_preset("quiet")
    moved = apply_overrides(
        state,
        WorldStateOverrides(
            locations=(LocationOverride(entity_id=ACTOR_ID, place_id=104),)
        ),
    )
    assert moved.locations[ACTOR_ID] == 104
    assert state.locations[ACTOR_ID] != 104


def test_explain_cross_check_holds_on_overridden_state() -> None:
    """explain_stack's per-template evaluate() cross-check runs on the
    sandbox state too — sandbox parity is enforced by construction."""

    state, bindings = _resolve_preset("hiding")
    hunted = apply_overrides(
        state,
        WorldStateOverrides(
            pair_tags=(
                PairTagOverride(
                    subject_entity_id=TARGET_ID,
                    object_entity_id=ACTOR_ID,
                    tag="hunting",
                    op="add",
                ),
            )
        ),
    )
    explanation = explain_stack(BUILTIN_TEMPLATES, hunted, bindings)
    assert explanation.winner_id == "evade_pursuers"
    hide = next(item for item in explanation.templates if item.template_id == "hide")
    assert hide.gate_passed is False


def test_empty_override_set_returns_state_unchanged() -> None:
    state, _ = _resolve_preset("quiet")
    overrides = WorldStateOverrides()
    assert overrides.is_empty
    assert apply_overrides(state, overrides) is state


def test_no_op_tag_toggles_raise() -> None:
    state, _ = _resolve_preset("hiding")

    with pytest.raises(OverrideValidationError, match="already carries it"):
        apply_overrides(
            state,
            WorldStateOverrides(
                tags=(TagOverride(entity_id=ACTOR_ID, tag="off_grid", op="add"),)
            ),
        )
    with pytest.raises(OverrideValidationError, match="does not carry it"):
        apply_overrides(
            state,
            WorldStateOverrides(
                tags=(TagOverride(entity_id=ACTOR_ID, tag="public_role", op="remove"),)
            ),
        )
    # Layers are separate vocabularies: off_grid lives on the durable layer,
    # so an ephemeral-layer removal is a no-op and must refuse.
    with pytest.raises(OverrideValidationError, match="does not carry it"):
        apply_overrides(
            state,
            WorldStateOverrides(
                tags=(
                    TagOverride(
                        entity_id=ACTOR_ID,
                        tag="off_grid",
                        op="remove",
                        ephemeral=True,
                    ),
                )
            ),
        )


def test_unknown_inputs_raise() -> None:
    state, _ = _resolve_preset("quiet")

    with pytest.raises(OverrideValidationError, match="Unknown tag override op"):
        apply_overrides(
            state,
            WorldStateOverrides(
                tags=(TagOverride(entity_id=ACTOR_ID, tag="off_grid", op="toggle"),)
            ),
        )
    with pytest.raises(OverrideValidationError, match="Unknown need type"):
        apply_overrides(
            state,
            WorldStateOverrides(
                needs=(
                    NeedOverride(
                        entity_id=ACTOR_ID, need_type="caffeine", debt_score=1.0
                    ),
                )
            ),
        )
    with pytest.raises(OverrideValidationError, match="must be >= 0"):
        apply_overrides(
            state,
            WorldStateOverrides(
                needs=(
                    NeedOverride(
                        entity_id=ACTOR_ID, need_type="sleep", debt_score=-1.0
                    ),
                )
            ),
        )
    with pytest.raises(OverrideValidationError, match="ticks_ago must be >= 0"):
        apply_overrides(
            state,
            WorldStateOverrides(
                events=(EventOverride(event_type="contact_made", ticks_ago=-1),)
            ),
        )


def test_override_echo_round_trips_through_json() -> None:
    import json

    overrides = WorldStateOverrides(
        tags=(TagOverride(entity_id=1, tag="off_grid", op="remove"),),
        pair_tags=(
            PairTagOverride(
                subject_entity_id=2, object_entity_id=1, tag="hunting", op="add"
            ),
        ),
        needs=(NeedOverride(entity_id=1, need_type="sleep", debt_score=20.0),),
        locations=(LocationOverride(entity_id=1, place_id=104),),
        events=(
            EventOverride(
                event_type="hideout_maintained", actor_entity_id=1, ticks_ago=3
            ),
        ),
    )
    echo = json.loads(json.dumps(overrides.to_dict()))
    assert echo["scope"] == "world_state_only"
    assert {key for key in echo} == {
        "scope",
        "tags",
        "pair_tags",
        "needs",
        "locations",
        "events",
    }
    assert echo["events"][0]["ticks_ago"] == 3

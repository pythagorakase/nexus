"""World-hour gates use dated history independently of the tick window."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from pydantic import ValidationError

from nexus.agents.orrery.resolver import coerce_event_horizon_hours
from nexus.agents.orrery.substrate import (
    EventRecord,
    Slot,
    WorldState,
    _hours_text,
    count_recent_events_at_least,
    count_recent_events_within_hours_at_least,
    knows_recent_event,
    knows_recent_event_within_hours,
    recent_event,
    recent_event_within_hours,
    since_last_event_at_least,
    since_last_event_hours_at_least,
)
from nexus.config import load_settings
from nexus.config.settings_models import OrreryBindingSettings

NOW = datetime(2100, 1, 2, tzinfo=timezone.utc)
BINDINGS = {Slot.ACTOR: 1, Slot.TARGET: 2}


def _event(*, hours: float, tick: int = 99, event_id: int = 7) -> EventRecord:
    return EventRecord(
        "stroll_taken",
        tick,
        event_id=event_id,
        actor_entity_id=1,
        target_entity_id=2,
        world_time=NOW - timedelta(hours=hours),
    )


def _state(*events: EventRecord) -> WorldState:
    return WorldState(
        current_tick=100,
        world_time=NOW,
        event_horizon_hours=24.0,
        recent_events=events,
        horizon_events=events,
    )


def test_hour_forms_measure_world_time_not_ticks() -> None:
    """A one-tick-old occurrence can be three world hours old."""
    state = _state(_event(hours=3))
    assert recent_event(within_ticks=5)(state, BINDINGS)
    assert not recent_event_within_hours(within_hours=2)(state, BINDINGS)
    assert recent_event_within_hours(within_hours=3)(state, BINDINGS)


def test_since_last_hours_uses_latest_occurrence() -> None:
    """Occurrence order wins over tick order and the exact boundary passes."""
    state = _state(_event(hours=5, tick=99), _event(hours=1.5, tick=80, event_id=8))
    assert not since_last_event_hours_at_least("stroll_taken", 2)(state, BINDINGS)
    assert since_last_event_hours_at_least("stroll_taken", 1.5)(state, BINDINGS)
    assert since_last_event_hours_at_least("never_fired", 2)(state, BINDINGS)
    assert since_last_event_hours_at_least(
        "stroll_taken", 1.5, target_slot=Slot.TARGET
    )(state, BINDINGS)


def test_count_and_knows_hour_forms() -> None:
    """Floor inclusion, target binding and epistemic visibility are independent."""
    state = _state(_event(hours=2), _event(hours=1, event_id=8))
    assert count_recent_events_within_hours_at_least(
        "stroll_taken", within_hours=2, min_count=2, target_slot=Slot.TARGET
    )(state, BINDINGS)
    assert not count_recent_events_within_hours_at_least(
        "stroll_taken", within_hours=1, min_count=2
    )(state, BINDINGS)
    assert not count_recent_events_within_hours_at_least(
        "stroll_taken", within_hours=2, min_count=2, target_slot=Slot.TARGET
    )(state, {Slot.ACTOR: 1, Slot.TARGET: 3})
    hidden = replace(
        state,
        epistemics_enabled=True,
        claimed_event_scopes={7: "bounded", 8: "bounded"},
    )
    gate = knows_recent_event_within_hours("stroll_taken", within_hours=2)
    assert not gate(hidden, BINDINGS)
    assert gate(replace(hidden, awareness_by_entity={1: frozenset({7})}), BINDINGS)
    assert gate(state, BINDINGS) == recent_event_within_hours(within_hours=2)(
        state, BINDINGS
    )
    assert recent_event_within_hours(within_hours=2, actor_slot=Slot.ACTOR)(
        state, BINDINGS
    )
    assert not recent_event_within_hours(
        within_hours=2, changed_fields_any_of=("location",)
    )(state, BINDINGS)


def test_hour_forms_refuse_an_uncovered_window() -> None:
    """Even missing bindings or missing matches cannot bypass horizon admission."""
    gates = (
        recent_event_within_hours(within_hours=2),
        knows_recent_event_within_hours(within_hours=2),
        since_last_event_hours_at_least("missing", 2),
        count_recent_events_within_hours_at_least(
            "missing", within_hours=2, min_count=1
        ),
    )
    for gate in gates:
        for horizon in (1.0, None):
            with pytest.raises(ValueError, match="recent_event_horizon_hours"):
                gate(replace(_state(), event_horizon_hours=horizon), {})
        for clock in (None, NOW.replace(tzinfo=None)):
            with pytest.raises(ValueError, match="aware world_time"):
                gate(replace(_state(), world_time=clock), {})


def test_horizon_events_must_be_dated() -> None:
    """Undated history is legal only outside the hour horizon."""
    for clock in (None, NOW.replace(tzinfo=None)):
        event = replace(_event(hours=1, event_id=778), world_time=clock)
        with pytest.raises(ValueError, match="778.*aware world_time"):
            _state(event)
        assert WorldState(recent_events=(event,)).recent_events == (event,)


def test_tick_forms_ignore_horizon_events() -> None:
    """Adding occurrence-time history never changes existing tick predicates."""
    state = replace(_state(_event(hours=1)), recent_events=())
    empty = replace(state, horizon_events=())
    gates = (
        recent_event("stroll_taken"),
        knows_recent_event("stroll_taken"),
        since_last_event_at_least("stroll_taken", 5),
        count_recent_events_at_least("stroll_taken", within_ticks=5, min_count=1),
    )
    assert [gate(state, BINDINGS) for gate in gates] == [False, False, True, False]
    assert [gate(state, BINDINGS) for gate in gates] == [
        gate(empty, BINDINGS) for gate in gates
    ]


def test_hours_text_round_trips() -> None:
    """Predicate names cannot silently round or encode scientific notation."""
    assert _hours_text(1.5, "probe") == "1.5"
    assert _hours_text(24, "probe") == "24"
    for hours in (1 / 3, 1e-5, 0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="probe"):
            _hours_text(hours, "probe")
    for hours in (True, "2", None):
        with pytest.raises(TypeError, match="probe"):
            _hours_text(cast(Any, hours), "probe")


def test_horizon_setting_is_validated() -> None:
    """The shipped horizon and hydration coercer refuse unbounded intervals."""
    for hours in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            OrreryBindingSettings(recent_event_horizon_hours=hours)
        with pytest.raises(ValueError, match="recent_event_horizon_hours"):
            coerce_event_horizon_hours(hours)
    for hours in (True, "24"):
        with pytest.raises(TypeError, match="recent_event_horizon_hours"):
            coerce_event_horizon_hours(hours)
    orrery = load_settings().orrery
    assert orrery is not None
    assert orrery.binding.recent_event_horizon_hours == 24.0
    assert coerce_event_horizon_hours(None) == 24.0

"""Offline shape and schedule rules of the routine-anchor custody model (#783 S1a)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from nexus.agents.orrery.routine_anchors import (
    RoutineAnchorChange,
    RoutineAnchorDelta,
    RoutineSchedule,
)

SCHEDULE = {"weekdays": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"}

# Each case breaks exactly one shape rule, in the order the shared shape
# function applies them. Names are wire fields; ids replace them for the
# resolved model.
SHAPE_REFUSALS: list[tuple[str, dict[str, Any], str]] = [
    (
        "clear_with_policy",
        {"anchor_type": "home", "clear": True, "mobility_policy": "nomadic"},
        "a clear has no mobility_policy, place, zone or schedule",
    ),
    (
        "clear_with_place",
        {"anchor_type": "home", "clear": True, "place": "Flat 4"},
        "a clear has no mobility_policy, place, zone or schedule",
    ),
    (
        "clear_with_zone",
        {"anchor_type": "home", "clear": True, "zone": "Harbor"},
        "a clear has no mobility_policy, place, zone or schedule",
    ),
    (
        "clear_with_schedule",
        {"anchor_type": "home", "clear": True, "schedule": {"always": True}},
        "a clear has no mobility_policy, place, zone or schedule",
    ),
    (
        "upsert_without_policy",
        {"anchor_type": "home"},
        "an upsert needs a mobility_policy",
    ),
    (
        "fixed_place_without_place",
        {"anchor_type": "home", "mobility_policy": "fixed_place"},
        "fixed_place needs a place and no zone",
    ),
    (
        "fixed_place_with_zone",
        {
            "anchor_type": "home",
            "mobility_policy": "fixed_place",
            "place": "Flat 4",
            "zone": "Harbor",
        },
        "fixed_place needs a place and no zone",
    ),
    (
        "zone_resolved_without_zone",
        {"anchor_type": "work", "mobility_policy": "zone_resolved"},
        "zone_resolved needs a zone and no place",
    ),
    (
        "zone_resolved_with_place",
        {
            "anchor_type": "work",
            "mobility_policy": "zone_resolved",
            "zone": "Harbor",
            "place": "Dock 9",
        },
        "zone_resolved needs a zone and no place",
    ),
    (
        "works_from_home_on_home",
        {"anchor_type": "home", "mobility_policy": "works_from_home"},
        "works_from_home is a work anchor policy",
    ),
    (
        "works_from_home_with_place",
        {
            "anchor_type": "work",
            "mobility_policy": "works_from_home",
            "place": "Flat 4",
        },
        "works_from_home has no place or zone",
    ),
    (
        "works_from_home_with_zone",
        {
            "anchor_type": "work",
            "mobility_policy": "works_from_home",
            "zone": "Harbor",
        },
        "works_from_home has no place or zone",
    ),
    (
        "nomadic_with_place",
        {"anchor_type": "work", "mobility_policy": "nomadic", "place": "Dock 9"},
        "nomadic has no place or zone",
    ),
    (
        "nomadic_with_zone",
        {"anchor_type": "work", "mobility_policy": "nomadic", "zone": "Harbor"},
        "nomadic has no place or zone",
    ),
    (
        "none_with_place",
        {"anchor_type": "home", "mobility_policy": "none", "place": "Flat 4"},
        "none has no place or zone",
    ),
    (
        "none_with_zone",
        {"anchor_type": "home", "mobility_policy": "none", "zone": "Harbor"},
        "none has no place or zone",
    ),
    (
        "none_with_schedule",
        {"anchor_type": "home", "mobility_policy": "none", "schedule": SCHEDULE},
        "none records an authored absence and has no schedule",
    ),
]

SCHEDULE_REFUSALS: list[tuple[str, dict[str, Any], str]] = [
    (
        "always_with_weekdays",
        {"always": True, "weekdays": [1]},
        "an always-due schedule has no weekdays, start or end",
    ),
    (
        "always_with_start",
        {"always": True, "start": "09:00"},
        "an always-due schedule has no weekdays, start or end",
    ),
    (
        "always_with_end",
        {"always": True, "end": "17:00"},
        "an always-due schedule has no weekdays, start or end",
    ),
    (
        "empty_object",
        {},
        "an unknown schedule is null, not an empty object",
    ),
    (
        "explicit_false_only",
        {"always": False},
        "an unknown schedule is null, not an empty object",
    ),
    ("weekdays_empty", {"weekdays": []}, "weekdays is empty"),
    ("weekdays_bool", {"weekdays": [True, 2]}, "weekdays holds a bool"),
    ("weekdays_numeric_string", {"weekdays": ["2"]}, "Input should be a valid integer"),
    ("weekdays_other_string", {"weekdays": ["3"]}, "Input should be a valid integer"),
    ("weekdays_float", {"weekdays": [2.0]}, "Input should be a valid integer"),
    ("always_string_true", {"always": "true"}, "Input should be a valid boolean"),
    ("always_string_yes", {"always": "yes"}, "Input should be a valid boolean"),
    ("always_integer_one", {"always": 1}, "Input should be a valid boolean"),
    ("weekdays_above_six", {"weekdays": [7]}, "outside 0-6"),
    ("weekdays_negative", {"weekdays": [-1]}, "outside 0-6"),
    ("weekdays_duplicate", {"weekdays": [2, 2]}, "repeat a day"),
    ("start_unpadded", {"start": "9:00"}, "is not zero-padded HH:MM"),
    ("start_hour_24", {"start": "24:00"}, "is not zero-padded HH:MM"),
    ("start_trailing_newline", {"start": "09:00\n"}, "is not zero-padded HH:MM"),
    ("end_minute_60", {"end": "17:60"}, "is not zero-padded HH:MM"),
    ("end_non_ascii_digits", {"end": "１７:00"}, "is not zero-padded HH:MM"),
    (
        "start_equals_end",
        {"start": "09:00", "end": "09:00"},
        "start and end are both 09:00",
    ),
]


def _wire(fields: dict[str, Any]) -> dict[str, Any]:
    return {"character": "Mara Voss", **fields}


def _resolved(fields: dict[str, Any]) -> dict[str, Any]:
    """Map a wire case to the resolved model, a name becoming a fixed id."""

    resolved: dict[str, Any] = {
        "character_entity_id": 41,
        "mobility_policy": None,
        "place_id": None,
        "zone_id": None,
        "schedule": None,
        "clear": False,
    }
    for key, value in fields.items():
        if key == "place":
            resolved["place_id"] = 7
        elif key == "zone":
            resolved["zone_id"] = 3
        else:
            resolved[key] = value
    return resolved


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(fields, message, id=name)
        for name, fields, message in SHAPE_REFUSALS
    ],
)
def test_wire_delta_refuses_each_shape_rule(
    fields: dict[str, Any], message: str
) -> None:
    """Each shape rule refuses the wire model on its own."""

    with pytest.raises(ValidationError, match=message):
        RoutineAnchorDelta.model_validate(_wire(fields))


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(fields, message, id=name)
        for name, fields, message in SHAPE_REFUSALS
    ],
)
def test_resolved_change_refuses_each_shape_rule(
    fields: dict[str, Any], message: str
) -> None:
    """The resolved model applies the same shape rules to ids."""

    with pytest.raises(ValidationError, match=message):
        RoutineAnchorChange.model_validate(_resolved(fields))


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(fields, message, id=name)
        for name, fields, message in SCHEDULE_REFUSALS
    ],
)
def test_schedule_refuses_each_malformed_value(
    fields: dict[str, Any], message: str
) -> None:
    """Malformed schedule values fail; an unknown schedule is null, not {}."""

    with pytest.raises(ValidationError, match=message):
        RoutineSchedule.model_validate(fields)


def test_schedule_refuses_a_bool_in_a_weekday_set() -> None:
    """A non-list iterable holding a bool still fails; strict ints refuse it."""

    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        RoutineSchedule(weekdays={True, 2})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("character_entity_id", True, id="entity_bool"),
        pytest.param("character_entity_id", "41", id="entity_string"),
        pytest.param("place_id", True, id="place_bool"),
        pytest.param("place_id", 7.0, id="place_float"),
        pytest.param("zone_id", "3", id="zone_string"),
    ],
)
def test_resolved_change_refuses_wrong_typed_ids(field: str, value: Any) -> None:
    """A resolved id is a strict integer: a bool, string or float fails."""

    fields: dict[str, Any] = {
        "anchor_type": "home",
        "mobility_policy": "fixed_place",
        "place": "Flat 4",
    }
    if field == "zone_id":
        fields = {
            "anchor_type": "work",
            "mobility_policy": "zone_resolved",
            "zone": "H",
        }
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        RoutineAnchorChange.model_validate({**_resolved(fields), field: value})


@pytest.mark.parametrize(
    "value",
    [pytest.param("yes", id="string_yes"), pytest.param(1, id="integer_one")],
)
@pytest.mark.parametrize("model", ["wire", "resolved"])
def test_clear_is_a_strict_boolean(model: str, value: Any) -> None:
    """A clear deletes the anchor, so only a real boolean can ask for one."""

    fields: dict[str, Any] = {"anchor_type": "home", "clear": value}
    with pytest.raises(ValidationError, match="Input should be a valid boolean"):
        if model == "wire":
            RoutineAnchorDelta.model_validate(_wire(fields))
        else:
            RoutineAnchorChange.model_validate(_resolved(fields))


@pytest.mark.parametrize(
    ("fields", "stored"),
    [
        pytest.param({"weekdays": [5, 6]}, {"weekdays": [5, 6]}, id="weekdays_only"),
        pytest.param({"start": "09:00"}, {"start": "09:00"}, id="start_only"),
        pytest.param({"end": "17:00"}, {"end": "17:00"}, id="end_only"),
        pytest.param(
            {"weekdays": [4, 0], "start": "22:00"},
            {"weekdays": [0, 4], "start": "22:00"},
            id="weekdays_and_start",
        ),
        pytest.param(
            {"weekdays": [6], "end": "06:00"},
            {"weekdays": [6], "end": "06:00"},
            id="weekdays_and_end",
        ),
        pytest.param(
            {"start": "22:00", "end": "06:00"},
            {"start": "22:00", "end": "06:00"},
            id="overnight",
        ),
        pytest.param(
            {"always": False, "weekdays": [3, 1]},
            {"weekdays": [1, 3]},
            id="explicit_false_sorted",
        ),
        pytest.param({"always": True}, {"always": True}, id="always"),
    ],
)
def test_accepted_schedules_keep_their_known_fields(
    fields: dict[str, Any], stored: dict[str, Any]
) -> None:
    """Partial schedules keep their fields; weekdays sort; always stays alone."""

    schedule = RoutineSchedule.model_validate(fields)
    assert schedule.as_json() == stored
    if schedule.weekdays is not None:
        assert schedule.weekdays == sorted(schedule.weekdays)


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param(
            {
                "anchor_type": "home",
                "mobility_policy": "fixed_place",
                "place": "Flat 4",
            },
            id="fixed_place",
        ),
        pytest.param(
            {
                "anchor_type": "work",
                "mobility_policy": "zone_resolved",
                "zone": "Harbor",
            },
            id="zone_resolved",
        ),
        pytest.param(
            {
                "anchor_type": "work",
                "mobility_policy": "works_from_home",
                "schedule": SCHEDULE,
            },
            id="works_from_home",
        ),
        pytest.param(
            {"anchor_type": "work", "mobility_policy": "nomadic"}, id="nomadic"
        ),
        pytest.param({"anchor_type": "home", "mobility_policy": "none"}, id="none"),
        pytest.param({"anchor_type": "work", "clear": True}, id="clear"),
    ],
)
def test_well_formed_shapes_pass_both_models(fields: dict[str, Any]) -> None:
    """Every policy has an accepted shape on the wire and when resolved."""

    RoutineAnchorDelta.model_validate(_wire(fields))
    RoutineAnchorChange.model_validate(_resolved(fields))


def test_models_forbid_extra_fields_and_are_frozen() -> None:
    """An unknown key fails, and a validated model cannot be edited."""

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RoutineSchedule.model_validate({"always": True, "timezone": "UTC"})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RoutineAnchorDelta.model_validate(
            _wire({"anchor_type": "work", "clear": True, "reason": "fired"})
        )
    with pytest.raises(ValidationError, match="String should have at least 1"):
        RoutineAnchorDelta.model_validate(
            {"character": "", "anchor_type": "work", "clear": True}
        )
    delta = RoutineAnchorDelta.model_validate(
        _wire({"anchor_type": "work", "clear": True})
    )
    with pytest.raises(ValidationError, match="frozen"):
        delta.clear = False  # type: ignore[misc]


@pytest.mark.parametrize(
    ("fields", "ids"),
    [
        pytest.param(
            {
                "anchor_type": "home",
                "mobility_policy": "fixed_place",
                "place": "Flat 4",
            },
            {"place_id": None, "zone_id": None},
            id="named_place_without_id",
        ),
        pytest.param(
            {"anchor_type": "work", "mobility_policy": "nomadic"},
            {"place_id": 7, "zone_id": None},
            id="place_id_without_name",
        ),
        pytest.param(
            {
                "anchor_type": "work",
                "mobility_policy": "zone_resolved",
                "zone": "Harbor",
            },
            {"place_id": None, "zone_id": None},
            id="named_zone_without_id",
        ),
        pytest.param(
            {
                "anchor_type": "home",
                "mobility_policy": "fixed_place",
                "place": "Flat 4",
            },
            {"place_id": 7, "zone_id": 3},
            id="zone_id_without_name",
        ),
    ],
)
def test_from_delta_refuses_mismatched_ids(
    fields: dict[str, Any], ids: dict[str, Any]
) -> None:
    """A resolved id must match the presence of its name, as a plain ValueError."""

    delta = RoutineAnchorDelta.model_validate(_wire(fields))
    with pytest.raises(ValueError) as caught:
        RoutineAnchorChange.from_delta(delta, character_entity_id=41, **ids)
    assert type(caught.value) is ValueError


def test_from_delta_carries_the_delta_over() -> None:
    """Matching ids give the resolved change with the delta's fields."""

    delta = RoutineAnchorDelta.model_validate(
        _wire(
            {
                "anchor_type": "home",
                "mobility_policy": "fixed_place",
                "place": "Flat 4",
                "schedule": {"weekdays": [6, 5]},
            }
        )
    )
    change = RoutineAnchorChange.from_delta(
        delta, character_entity_id=41, place_id=7, zone_id=None
    )
    assert change.after_image() == {
        "mobility_policy": "fixed_place",
        "place_id": 7,
        "zone_id": None,
        "schedule": {"weekdays": [5, 6]},
    }
    assert (change.character_entity_id, change.anchor_type, change.clear) == (
        41,
        "home",
        False,
    )

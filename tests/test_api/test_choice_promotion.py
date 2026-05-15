"""Tests for narrative choice promotion helpers."""

from __future__ import annotations

from nexus.api.choice_handling import (
    normalize_choice_object,
    resolve_choice_response,
    selected_text_from_choice_object,
)
from nexus.api.lore_adapter import compute_raw_text


def test_resolve_choice_response_writes_canonical_selected_index() -> None:
    """Structured choices should persist selected as an integer."""
    choice_object = {
        "presented": ["Cross the street.", "Stay hidden."],
        "selected": None,
    }

    resolved = resolve_choice_response(choice_object, choice=2)

    assert resolved.choice_text == "Stay hidden."
    assert resolved.selected == 2
    assert resolved.choice_object == {
        "presented": ["Cross the street.", "Stay hidden."],
        "selected": 2,
    }


def test_resolve_choice_response_accept_fate_selects_first_choice() -> None:
    """Narrative accept-fate is auditable as the first presented choice."""
    choice_object = {
        "presented": ["Cross the street.", "Stay hidden."],
        "selected": None,
    }

    resolved = resolve_choice_response(choice_object, accept_fate=True)

    assert resolved.choice_text == "Cross the street."
    assert resolved.selected == 1
    assert resolved.choice_object["selected"] == 1


def test_resolve_choice_response_infers_flattened_choice_text() -> None:
    """Old callers that flatten --choice into text should still preserve selected."""
    choice_object = {
        "presented": ["Cross the street.", "Stay hidden."],
        "selected": None,
    }

    resolved = resolve_choice_response(choice_object, user_text="Cross the street.")

    assert resolved.choice_text == "Cross the street."
    assert resolved.selected == 1
    assert resolved.choice_object["selected"] == 1


def test_resolve_choice_response_freeform_keeps_selected_null() -> None:
    """Freeform responses keep choice_text without claiming a menu index."""
    choice_object = {
        "presented": ["Cross the street.", "Stay hidden."],
        "selected": None,
    }

    resolved = resolve_choice_response(choice_object, user_text="I call Jonas instead.")

    assert resolved.choice_text == "I call Jonas instead."
    assert resolved.selected is None
    assert resolved.choice_object["selected"] is None


def test_legacy_selected_object_normalizes_to_integer() -> None:
    """Readers tolerate the previous selected-object shape."""
    choice_object = {
        "presented": ["Cross the street.", "Stay hidden."],
        "selected": {"label": 2, "text": "Stay hidden.", "edited": False},
    }

    assert normalize_choice_object(choice_object)["selected"] == 2
    assert selected_text_from_choice_object(choice_object) == "Stay hidden."


def test_legacy_freeform_selection_preserves_text() -> None:
    """Readers should recover freeform text before canonical normalization."""
    choice_object = {
        "presented": ["Cross the street.", "Stay hidden."],
        "selected": {
            "label": "freeform",
            "text": "Circle around through the loading dock.",
            "edited": True,
        },
    }

    assert normalize_choice_object(choice_object)["selected"] is None
    assert (
        selected_text_from_choice_object(choice_object)
        == "Circle around through the loading dock."
    )
    assert compute_raw_text("Rain silvered the street.", choice_object) == (
        "Rain silvered the street.\n\nCircle around through the loading dock."
    )


def test_compute_raw_text_uses_choice_text_not_full_menu() -> None:
    """raw_text is storyteller prose plus the selected/freeform response only."""
    raw_text = compute_raw_text(
        "Rain silvered the street.",
        {"presented": ["Cross the street.", "Stay hidden."], "selected": 1},
        "Cross the street.",
    )

    assert raw_text == "Rain silvered the street.\n\nCross the street."

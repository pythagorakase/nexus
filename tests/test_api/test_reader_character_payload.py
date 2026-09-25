"""Character projection distinguishes setup provenance from story facts."""

from copy import deepcopy
from typing import Any

import pytest

from nexus.api.reader_endpoints import _character_payload


def _row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": 946,
        "name": "Nell Rourke",
        "summary": (
            "Retrograde-generated character stub for Nell Rourke. "
            "Created so Skald-selected setup history can resolve to canonical rows."
        ),
        "background": (
            "Retrograde-generated stub; details intentionally sparse until play."
        ),
        "current_activity": "latent in generated backstory",
        "appearance": None,
        "personality": None,
        "emotional_state": None,
        "current_location": 7,
        "extra_data": {
            "source": "retrograde",
            "stub_kind": "retrograde_expansion_ref",
            "sources": [{"plan": "event_plan", "event_ref": "harbor_rescue"}],
        },
        "created_at": None,
        "updated_at": None,
        "current_location_name": "Fish Quay",
        "portrait_path": None,
    }
    row.update(overrides)
    return row


def test_legacy_character_placeholders_are_projected_without_mutation() -> None:
    """Old saves need no rewrite to omit the generator's placeholder prose."""
    row = _row()
    original = deepcopy(row)

    payload = _character_payload(row)

    assert payload["summary"] is None
    assert payload["background"] is None
    assert payload["currentActivity"] is None
    assert payload["currentLocation"] == "7"
    assert payload["extraData"] == original["extra_data"]
    assert row == original


@pytest.mark.parametrize(
    "provenance",
    [None, {}, {"source": "retrograde"}, {"source": "authored"}, ["retrograde"]],
)
def test_placeholder_text_requires_matching_provenance(provenance: Any) -> None:
    """Similar prose alone is not sufficient evidence to hide character facts."""
    row = _row(extra_data=provenance)
    payload = _character_payload(row)

    assert payload["summary"] == row["summary"]
    assert payload["background"] == row["background"]
    assert payload["currentActivity"] == row["current_activity"]


def test_matured_character_facts_remain_visible_with_stub_provenance() -> None:
    """Keeping origin metadata must not hide facts learned later in play."""
    row = _row(
        summary="Nell keeps the rescue ledger at the Fish Quay.",
        background="Nell studied the Retrograde charts before becoming a navigator.",
        current_activity="Sorting repair slips.",
        appearance="A weathered yellow coat.",
    )

    payload = _character_payload(row)

    assert payload["summary"] == row["summary"]
    assert payload["background"] == row["background"]
    assert payload["currentActivity"] == row["current_activity"]
    assert payload["appearance"] == row["appearance"]


def test_each_legacy_placeholder_is_suppressed_independently() -> None:
    """A new summary must not make the old activity marker visible again."""
    row = _row(summary="Nell keeps the rescue ledger.")

    payload = _character_payload(row)

    assert payload["summary"] == row["summary"]
    assert payload["background"] is None
    assert payload["currentActivity"] is None

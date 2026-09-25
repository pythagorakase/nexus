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


def test_renamed_legacy_character_uses_only_recorded_prior_names() -> None:
    """A durable name reveal must not expose an older diagnostic summary."""
    row = _row(
        name="Anika Sayegh",
        identity_previous_names=["Nell Rourke", "The unnamed witness"],
    )
    original = deepcopy(row)

    payload = _character_payload(row)

    assert payload["name"] == "Anika Sayegh"
    assert payload["summary"] is None
    assert row == original
    assert "identity_previous_names" not in payload


@pytest.mark.parametrize("prior_names", [None, [], ["Another person"]])
def test_rename_does_not_guess_missing_placeholder_provenance(prior_names) -> None:
    """Only exact names from this character's rulings extend the legacy marker."""
    row = _row(name="Anika Sayegh", identity_previous_names=prior_names)

    assert _character_payload(row)["summary"] == row["summary"]


@pytest.mark.parametrize(
    "summary",
    [
        "Nell Rourke was the name Anika used while working at the quay.",
        "Retrograde-generated character stub for Nell Rourke. "
        "Created so Skald-selected setup history can resolve to canonical rows. "
        "Anika now keeps the rescue ledger.",
    ],
)
def test_recorded_prior_name_does_not_hide_real_character_facts(summary: str) -> None:
    row = _row(
        name="Anika Sayegh",
        summary=summary,
        identity_previous_names=["Nell Rourke"],
    )

    assert _character_payload(row)["summary"] == summary


def test_recorded_prior_name_still_requires_retrograde_provenance() -> None:
    row = _row(
        name="Anika Sayegh",
        identity_previous_names=["Nell Rourke"],
        extra_data={"source": "authored"},
    )

    assert _character_payload(row)["summary"] == row["summary"]

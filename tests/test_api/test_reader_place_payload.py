"""Place projection distinguishes setup provenance from genuine story prose."""

from copy import deepcopy
from typing import Any

import pytest

from nexus.api.reader_endpoints import _place_payload


def _row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": 950,
        "name": "Old Pump Annex",
        "type": "other",
        "zone": 3,
        "summary": (
            "Retrograde-generated place stub for Old Pump Annex. "
            "Created so Skald-selected setup history can resolve to canonical rows."
        ),
        "current_status": "latent in generated backstory",
        "history": None,
        "inhabitants": None,
        "secrets": None,
        "geometry": None,
        "extra_data": {
            "source": "retrograde",
            "stub_kind": "retrograde_expansion_ref",
            "sources": [{"plan": "event_plan", "event_ref": "annex_quarantine"}],
        },
        "created_at": None,
        "updated_at": None,
    }
    row.update(overrides)
    return row


def test_legacy_place_placeholders_are_projected_without_mutation() -> None:
    """The place API masks old diagnostics while preserving its stored row."""
    row = _row()
    original = deepcopy(row)

    payload = _place_payload(row)

    assert payload["summary"] is None
    assert payload["currentStatus"] is None
    assert payload["zone"] == 3
    assert payload["extraData"] == original["extra_data"]
    assert row == original


@pytest.mark.parametrize(
    "provenance",
    [
        None,
        {},
        {"source": "retrograde"},
        {"stub_kind": "retrograde_expansion_ref"},
        {"source": "authored", "stub_kind": "retrograde_expansion_ref"},
        ["retrograde"],
    ],
)
def test_place_placeholder_text_requires_matching_provenance(provenance: Any) -> None:
    """Text alone is not sufficient evidence to suppress place facts."""
    row = _row(extra_data=provenance)
    payload = _place_payload(row)

    assert payload["summary"] == row["summary"]
    assert payload["currentStatus"] == row["current_status"]


@pytest.mark.parametrize(
    "field,wire_name,value",
    [
        ("summary", "summary", "The annex once cooled the station's south ring."),
        ("current_status", "currentStatus", "Workers are repairing the intake."),
    ],
)
def test_place_facts_do_not_reveal_remaining_legacy_markers(
    field: str, wire_name: str, value: str
) -> None:
    """Partially enriched stubs expose new facts and still hide old markers."""
    row = _row(**{field: value})
    payload = _place_payload(row)

    assert payload[wire_name] == value
    assert payload["currentStatus" if field == "summary" else "summary"] is None


def test_place_genuine_and_near_matching_prose_stays_visible() -> None:
    """Exact legacy signatures cannot swallow authored or enriched prose."""
    row = _row(
        summary=_row()["summary"] + " It now houses the repair crew.",
        current_status="Previously latent in generated backstory; now occupied.",
        history="The Retrograde survey named the annex in 2180.",
        inhabitants=["Sana Pell"],
        secrets="A spare valve is hidden behind the north panel.",
        geometry={"type": "Point", "coordinates": [12.5, 42.0]},
    )
    payload = _place_payload(row)

    for field in ("summary", "history", "inhabitants", "secrets", "geometry"):
        assert payload[field] == row[field]
    assert payload["currentStatus"] == row["current_status"]


def test_place_signature_for_another_name_is_not_suppressed() -> None:
    """A quoted marker about another place is not this row's legacy signature."""
    row = _row(name="Council Office")
    assert _place_payload(row)["summary"] == row["summary"]

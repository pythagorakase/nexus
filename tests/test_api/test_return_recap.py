"""Deterministic return recap: composition, hiatus policy, settings, and route.

Composition runs on typed rows shaped like the committed reads the loader
makes (see ``test_return_recap_pg.py`` for those reads on a seeded slot).
The route checks run through the real gateway app and its player projection.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nexus.api import narrative
from nexus.api.return_recap import (
    ActionRow,
    FrontierRow,
    NamedRow,
    RecapEvidenceError,
    RecapItem,
    ReturnRecap,
    RosterRows,
    SettingRows,
    SourceHandle,
    compose_recap,
    is_recap_due,
    verify_recap_sources,
)
from nexus.api.route_capabilities import ROUTE_CAPABILITIES, build_player_app
from nexus.config import load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
RETURN = datetime(2026, 9, 27, 21, 30, tzinfo=timezone.utc)
MEMORIAL_CHOICES = [
    "Close your hand around the brass key and follow Rook into the rain.",
    "Show Ren the warrant is premature and ask for an hour.",
    "Take Ivo's call on the viaduct stairs.",
]
SETTING = SettingRows(
    chunk_id=41,
    places=(
        NamedRow(id=7, name="Lantern Quay Memorial Hall"),
        NamedRow(id=12, name="Transit Viaduct"),
    ),
)
ROSTER = RosterRows(
    chunk_id=42,
    characters=(
        NamedRow(id=1, name="Mara Vey"),
        NamedRow(id=4, name="Elian Rook"),
        NamedRow(id=5, name="Ren Vale"),
        NamedRow(id=9, name="Sister Calyx"),
    ),
)
LAST_ACTION = ActionRow(
    chunk_id=41, choice_text="  Offer Rook the thumb-to-temple greeting.  "
)
OPEN_FRONTIER = FrontierRow(
    chunk_id=42,
    choice_text=None,
    # The stored jsonb shape: the menu with no selection yet.
    choice_object={"presented": MEMORIAL_CHOICES, "selected": None},
)


def _compose(**overrides: Any) -> ReturnRecap:
    """Compose with a full memorial-hall return unless a row is overridden."""
    rows: dict[str, Any] = {
        "last_played": RETURN - timedelta(hours=30),
        "now": RETURN,
        "hiatus_hours": 12.0,
        "roster_limit": 6,
        "setting": SETTING,
        "roster": ROSTER,
        "last_action": LAST_ACTION,
        "frontier": OPEN_FRONTIER,
    }
    rows.update(overrides)
    return compose_recap(**rows)


def _handles(item: RecapItem) -> list[tuple[str, int]]:
    return [(source.kind, source.id) for source in item.sources]


def test_full_return_cites_each_fact_to_its_committed_rows() -> None:
    """Location, cast, last action and open decision each cite their rows."""
    recap = _compose()

    assert recap.due is True
    assert recap.last_played == RETURN - timedelta(hours=30)
    assert [item.kind for item in recap.items] == [
        "location",
        "roster",
        "last_action",
        "open_decision",
    ]
    location, roster, action, decision = recap.items
    assert location.text == "Lantern Quay Memorial Hall, Transit Viaduct"
    assert _handles(location) == [("chunk", 41), ("place", 7), ("place", 12)]
    # Names stay in their stored natural case.
    assert roster.text == "Mara Vey, Elian Rook, Ren Vale, Sister Calyx"
    assert _handles(roster) == [
        ("chunk", 42),
        ("character", 1),
        ("character", 4),
        ("character", 5),
        ("character", 9),
    ]
    assert action.text == "Offer Rook the thumb-to-temple greeting."
    assert _handles(action) == [("chunk", 41)]
    assert decision.text.split("\n") == MEMORIAL_CHOICES
    assert _handles(decision) == [("chunk", 42)]


def test_answered_frontier_is_the_last_action_and_leaves_no_open_decision() -> None:
    """A recorded response consumes the menu; the frontier is the last action."""
    edited = "Close your hand around the key, but let Rook leave alone."
    frontier = FrontierRow(
        chunk_id=42,
        choice_text=edited,
        choice_object={"presented": MEMORIAL_CHOICES, "selected": 1, "edited": True},
    )

    recap = _compose(
        frontier=frontier, last_action=ActionRow(chunk_id=42, choice_text=edited)
    )

    assert [item.kind for item in recap.items] == [
        "location",
        "roster",
        "last_action",
    ]
    assert recap.items[-1].text == edited
    assert _handles(recap.items[-1]) == [("chunk", 42)]


@pytest.mark.parametrize(
    ("overrides", "kinds"),
    [
        ({"setting": None}, ["roster", "last_action", "open_decision"]),
        (
            {"setting": SettingRows(chunk_id=41, places=())},
            ["roster", "last_action", "open_decision"],
        ),
        (
            {"roster": RosterRows(chunk_id=42, characters=())},
            ["location", "last_action", "open_decision"],
        ),
        ({"roster": None}, ["location", "last_action", "open_decision"]),
        ({"last_action": None}, ["location", "roster", "open_decision"]),
        (
            {"last_action": ActionRow(chunk_id=41, choice_text=" \n\t")},
            ["location", "roster", "open_decision"],
        ),
        (
            {"frontier": FrontierRow(chunk_id=42, choice_text="", choice_object=None)},
            ["location", "roster", "last_action"],
        ),
        (
            {
                "frontier": FrontierRow(
                    chunk_id=42,
                    choice_text=None,
                    choice_object={"presented": ["", "  "], "selected": None},
                )
            },
            ["location", "roster", "last_action"],
        ),
        ({"frontier": None}, ["location", "roster", "last_action"]),
    ],
    ids=[
        "no-setting",
        "setting-without-places",
        "empty-roster",
        "no-roster",
        "no-action",
        "blank-action",
        "freeform-frontier",
        "blank-options",
        "no-frontier",
    ],
)
def test_facts_without_a_source_are_omitted_not_invented(
    overrides: dict[str, Any], kinds: list[str]
) -> None:
    """Each missing source drops exactly its own item and nothing else."""
    assert [item.kind for item in _compose(**overrides).items] == kinds


def test_empty_story_has_no_items_and_is_never_due() -> None:
    """A slot with no committed chunks or recorded action has nothing to recap."""
    recap = _compose(
        last_played=None, setting=None, roster=None, last_action=None, frontier=None
    )

    assert recap == ReturnRecap(due=False, last_played=None, items=[])


def test_roster_cap_names_and_cites_only_the_first_characters() -> None:
    """The cap trims names and their handles together, in character-ID order."""
    roster = _compose(roster_limit=2).items[1]

    assert roster.text == "Mara Vey, Elian Rook"
    assert _handles(roster) == [("chunk", 42), ("character", 1), ("character", 4)]


def test_roster_limit_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="roster_limit must be at least 1"):
        _compose(roster_limit=0)


def test_stored_choice_object_text_normalizes() -> None:
    """A choice_object read back as JSON text yields the same open options."""
    frontier = FrontierRow(
        chunk_id=42,
        choice_text=None,
        choice_object=json.dumps({"presented": MEMORIAL_CHOICES, "selected": None}),
    )

    assert _compose(frontier=frontier).items[-1].text.split("\n") == MEMORIAL_CHOICES


def test_malformed_stored_choice_object_fails_loudly() -> None:
    frontier = FrontierRow(
        chunk_id=42,
        choice_text=None,
        choice_object={"presented": MEMORIAL_CHOICES, "selected": 9},
    )

    with pytest.raises(ValueError, match="out of range"):
        _compose(frontier=frontier)


@pytest.mark.parametrize(
    ("absence", "due"),
    [
        (timedelta(hours=12), True),
        (timedelta(hours=12) - timedelta(seconds=1), False),
        (timedelta(hours=12, seconds=1), True),
        (timedelta(0), False),
        (timedelta(hours=-1), False),
    ],
    ids=["exactly-hiatus", "one-second-short", "past-hiatus", "just-played", "skew"],
)
def test_hiatus_boundary_with_a_fixed_clock(absence: timedelta, due: bool) -> None:
    """Due exactly when now minus last_played reaches the configured hiatus."""
    assert is_recap_due(RETURN - absence, RETURN, 12.0) is due
    assert _compose(last_played=RETURN - absence).due is due


def test_fractional_hiatus_and_unplayed_story() -> None:
    assert is_recap_due(RETURN - timedelta(minutes=90), RETURN, 1.5) is True
    assert is_recap_due(RETURN - timedelta(minutes=89), RETURN, 1.5) is False
    assert is_recap_due(None, RETURN, 1.5) is False


def test_an_item_citing_other_than_one_chunk_is_refused_before_any_read() -> None:
    """Every item names the one chunk its evidence came from."""
    recap = ReturnRecap(
        due=False,
        last_played=None,
        items=[
            RecapItem(
                kind="location",
                text="Lantern Quay Memorial Hall",
                sources=[SourceHandle(kind="place", id=7)],
            )
        ],
    )

    with pytest.raises(RecapEvidenceError, match="exactly one chunk, got \\[\\]"):
        verify_recap_sources(None, recap)


# ---------------------------------------------------------------------------
# [ui.recap] settings
# ---------------------------------------------------------------------------

RECAP_TABLE = re.compile(r"^\[ui\.recap\]\n(?:(?!\[).*\n)*", re.MULTILINE)


def _config_with_recap(tmp_path: Path, body: str | None) -> Path:
    """Write nexus.toml with its [ui.recap] table replaced (None removes it)."""
    source = (REPO_ROOT / "nexus.toml").read_text()
    replacement = "" if body is None else f"[ui.recap]\n{body}\n"
    edited, count = RECAP_TABLE.subn(replacement, source)
    assert count == 1
    path = tmp_path / "nexus.toml"
    path.write_text(edited)
    return path


def test_shipped_recap_policy_loads() -> None:
    policy = load_settings().ui.recap

    assert isinstance(policy.hiatus_hours, float) and policy.hiatus_hours > 0
    assert isinstance(policy.roster_limit, int) and policy.roster_limit >= 1


@pytest.mark.parametrize(
    ("body", "field", "error_type"),
    [
        ("hiatus_hours = 0\nroster_limit = 6", "hiatus_hours", "greater_than"),
        ("hiatus_hours = -4.0\nroster_limit = 6", "hiatus_hours", "greater_than"),
        ("hiatus_hours = inf\nroster_limit = 6", "hiatus_hours", "finite_number"),
        ("hiatus_hours = nan\nroster_limit = 6", "hiatus_hours", "finite_number"),
        ("hiatus_hours = 12.0\nroster_limit = 0", "roster_limit", "greater_than_equal"),
        ("hiatus_hours = 12.0", "roster_limit", "missing"),
        ("roster_limit = 6", "hiatus_hours", "missing"),
        (
            "hiatus_hours = 12.0\nroster_limit = 6\ndismiss_hours = 1",
            "dismiss_hours",
            "extra_forbidden",
        ),
    ],
)
def test_recap_policy_rejects_invalid_values(
    tmp_path: Path, body: str, field: str, error_type: str
) -> None:
    with pytest.raises(ValidationError) as exc:
        load_settings(_config_with_recap(tmp_path, body))

    assert any(
        error["loc"] == ("ui", "recap", field) and error["type"] == error_type
        for error in exc.value.errors()
    )


def test_missing_recap_table_fails_load(tmp_path: Path) -> None:
    """No code default stands in for an absent [ui.recap] table."""
    with pytest.raises(ValidationError) as exc:
        load_settings(_config_with_recap(tmp_path, None))

    assert any(
        error["loc"] == ("ui", "recap") and error["type"] == "missing"
        for error in exc.value.errors()
    )


def test_integer_hiatus_is_accepted_as_hours(tmp_path: Path) -> None:
    config = _config_with_recap(tmp_path, "hiatus_hours = 36\nroster_limit = 3")

    policy = load_settings(config).ui.recap
    assert (policy.hiatus_hours, policy.roster_limit) == (36.0, 3)


# ---------------------------------------------------------------------------
# GET /api/narrative/recap on the real gateway
# ---------------------------------------------------------------------------


def test_recap_route_is_a_player_plane_narrative_read() -> None:
    capability = ROUTE_CAPABILITIES[("GET", "/api/narrative/recap")]

    assert capability.plane == "player"
    assert capability.capability == "narrative.read"
    assert capability.slot_mode == "read"
    assert not capability.provider_effect and not capability.destructive


@pytest.mark.parametrize("project", [False, True], ids=["gateway", "player-plane"])
def test_recap_route_validates_its_slot_in_the_handler(project: bool) -> None:
    """Slot validation inside the reader handler proves the route matched."""
    app = build_player_app(narrative.app) if project else narrative.app

    response = TestClient(app).get("/api/narrative/recap", params={"slot": 9})

    assert response.status_code == 400
    assert response.json() == {"detail": "slot_number must be between 1 and 5"}


def test_recap_wire_contract_is_the_typed_model() -> None:
    """The served schema carries the item kinds and handle kinds, nothing else."""
    schema = narrative.app.openapi()
    route = schema["paths"]["/api/narrative/recap"]["get"]
    ok = route["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/ReturnRecap"}

    components = schema["components"]["schemas"]
    assert set(components["ReturnRecap"]["properties"]) == {
        "due",
        "last_played",
        "items",
    }
    assert set(components["RecapItem"]["properties"]) == {"kind", "text", "sources"}
    assert components["RecapItem"]["properties"]["kind"]["enum"] == [
        "location",
        "roster",
        "last_action",
        "open_decision",
    ]
    assert components["SourceHandle"]["properties"]["kind"]["enum"] == [
        "chunk",
        "place",
        "character",
    ]

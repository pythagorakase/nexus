"""Tests for player-facing trait menu guidance."""

from pathlib import Path


def test_trait_menu_disambiguates_status_from_reputation() -> None:
    """Wizard trait reference must separate scoped standing from broad fame."""

    trait_menu = (
        Path(__file__).resolve().parents[1] / "docs" / "trait_menu.md"
    ).read_text()

    assert "standing within a specific institution, faction, community" in trait_menu
    assert "known within that group" in trait_menu
    assert "how broadly you're recognized beyond any one specific group" in trait_menu
    assert "use Status instead when the recognition is limited" in trait_menu

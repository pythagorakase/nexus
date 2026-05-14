"""Tests for the NEXUS CLI helpers."""

from nexus.cli import GENERATION_POLL_SECONDS, _is_terminal_generation_status


def test_terminal_generation_statuses_include_api_and_incubator_values() -> None:
    """CLI polling should accept both progress and incubator completion states."""

    assert _is_terminal_generation_status("complete")
    assert _is_terminal_generation_status("completed")
    assert _is_terminal_generation_status("provisional")
    assert _is_terminal_generation_status("approved")
    assert _is_terminal_generation_status("committed")
    assert not _is_terminal_generation_status("processing")
    assert not _is_terminal_generation_status("error")


def test_generation_poll_window_covers_live_reasoning_models() -> None:
    """CLI polling should outlast slow structured generation calls."""

    assert GENERATION_POLL_SECONDS >= 180

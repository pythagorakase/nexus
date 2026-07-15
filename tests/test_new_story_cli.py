"""Unit tests for the standalone new-story CLI."""

import sys

from scripts import new_story_cli


def test_start_omits_model_when_cli_flag_is_absent(monkeypatch, capsys) -> None:
    """The standalone client must leave setup-model resolution to the core."""
    calls: list[tuple[int, str | None]] = []

    def fake_start_setup(slot: int, model: str | None = None) -> str:
        calls.append((slot, model))
        return "thread-4"

    monkeypatch.setattr(
        new_story_cli,
        "start_setup",
        fake_start_setup,
    )
    monkeypatch.setattr(sys, "argv", ["new_story_cli.py", "start", "--slot", "4"])

    new_story_cli.main()

    assert calls == [(4, None)]
    assert "Started thread thread-4 for slot 4" in capsys.readouterr().out


def test_start_forwards_explicit_model(monkeypatch, capsys) -> None:
    """An explicit standalone CLI override remains authoritative."""
    calls: list[tuple[int, str | None]] = []

    def fake_start_setup(slot: int, model: str | None = None) -> str:
        calls.append((slot, model))
        return "thread-4"

    monkeypatch.setattr(
        new_story_cli,
        "start_setup",
        fake_start_setup,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["new_story_cli.py", "start", "--slot", "4", "--model", "operator"],
    )

    new_story_cli.main()

    assert calls == [(4, "operator")]
    assert "Started thread thread-4 for slot 4" in capsys.readouterr().out

"""Tests for the NEXUS CLI helpers."""

from argparse import Namespace
from typing import Any

from nexus import cli
from nexus.cli import GENERATION_POLL_SECONDS, _is_terminal_generation_status


class DummyResponse:
    """Minimal requests.Response double for CLI tests."""

    def __init__(
        self, payload: dict[str, Any], ok: bool = True, text: str = ""
    ) -> None:
        self.payload = payload
        self.ok = ok
        self.text = text

    def json(self) -> dict[str, Any]:
        """Return response JSON."""
        return self.payload

    def raise_for_status(self) -> None:
        """Mimic a successful HTTP response."""
        return None


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


def test_continue_posts_choice_to_backend_without_preapproving(
    monkeypatch,
) -> None:
    """The CLI should let /api/narrative/continue record and approve atomically."""
    posts: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        if url.endswith("/api/slot/5/state"):
            return DummyResponse(
                {
                    "is_empty": False,
                    "is_wizard_mode": False,
                    "has_pending": True,
                    "choices": ["Cross the street.", "Stay hidden."],
                    "model": None,
                }
            )
        if "/api/narrative/status/" in url:
            return DummyResponse({"status": "completed", "chunk_id": 2})
        raise AssertionError(f"Unexpected GET {url}")

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        posts.append((url, json))
        if url.endswith("/api/narrative/approve"):
            raise AssertionError("CLI should not pre-approve pending narrative")
        if url.endswith("/api/narrative/continue"):
            return DummyResponse({"session_id": "session-2"})
        raise AssertionError(f"Unexpected POST {url}")

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)
    monkeypatch.setattr(
        cli,
        "run_load",
        lambda args: {"message": "Next chunk", "choices": ["Continue."]},
    )

    result = cli.run_continue(
        Namespace(
            slot=5,
            model=None,
            user_text=None,
            choice=1,
            accept_fate=False,
            dev=False,
        )
    )

    assert result["success"] is True
    assert len(posts) == 1
    url, payload = posts[0]
    assert url.endswith("/api/narrative/continue")
    assert payload["choice"] == 1
    assert payload["accept_fate"] is False
    assert payload["user_text"] == ""

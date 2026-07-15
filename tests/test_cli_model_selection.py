"""CLI model-selection regression tests for new-story flows."""

from argparse import Namespace
from typing import Any

from nexus import cli


class DummyResponse:
    """Minimal successful requests response for CLI boundary tests."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.ok = True
        self.text = ""

    def json(self) -> dict[str, Any]:
        """Return response JSON."""
        return self.payload

    def raise_for_status(self) -> None:
        """Mirror a successful response."""


def test_continue_starts_empty_slot_without_implicit_model(monkeypatch) -> None:
    """An omitted CLI override must stay omitted at the setup API boundary."""
    posts: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/slot/4/state")
        return DummyResponse(
            {
                "is_empty": True,
                "is_wizard_mode": False,
                "model": "operator-model",
            }
        )

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        posts.append((url, json))
        return DummyResponse(
            {
                "thread_id": "thread-operator",
                "model": "operator-model",
                "welcome_message": "Welcome.",
                "welcome_choices": [],
            }
        )

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)

    result = cli.run_continue(
        Namespace(
            slot=4,
            model=None,
            user_text=None,
            choice=None,
            accept_fate=False,
            dev=False,
        )
    )

    assert result["success"] is True
    assert posts == [
        (
            f"{cli.get_api_url()}/api/story/new/setup/start",
            {"slot": 4},
        )
    ]


def test_continue_wizard_turn_forwards_only_explicit_model(monkeypatch) -> None:
    """The server-side slot lock resolves ordinary wizard turns."""
    posts: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/slot/4/state")
        return DummyResponse(
            {
                "is_empty": False,
                "is_wizard_mode": True,
                "phase": "setting",
                "model": "operator-model",
                "choices": [],
            }
        )

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        posts.append((url, json))
        return DummyResponse(
            {
                "message": "The city waits.",
                "choices": [],
                "phase": "setting",
                "phase_complete": False,
            }
        )

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)

    result = cli.run_continue(
        Namespace(
            slot=4,
            model=None,
            user_text="Begin.",
            choice=None,
            accept_fate=False,
            dev=False,
        )
    )

    assert result["success"] is True
    assert len(posts) == 1
    assert posts[0][0].endswith("/api/story/new/chat")
    assert posts[0][1]["message"] == "Begin."
    assert "model" not in posts[0][1]


def test_continue_narrative_turn_forwards_only_explicit_model(monkeypatch) -> None:
    """A persisted narrative model is resolved server-side too."""
    posts: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> DummyResponse:
        assert url.endswith("/api/slot/4/state")
        return DummyResponse(
            {
                "is_empty": False,
                "is_wizard_mode": False,
                "has_pending": False,
                "model": "operator-model",
            }
        )

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> DummyResponse:
        posts.append((url, json))
        return DummyResponse({"message": "The city answers.", "session_id": None})

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.requests, "post", fake_post)

    result = cli.run_continue(
        Namespace(
            slot=4,
            model=None,
            user_text="Continue.",
            choice=None,
            accept_fate=False,
            dev=False,
        )
    )

    assert result["success"] is True
    assert len(posts) == 1
    assert posts[0][0].endswith("/api/narrative/continue")
    assert posts[0][1]["user_text"] == "Continue."
    assert "model" not in posts[0][1]

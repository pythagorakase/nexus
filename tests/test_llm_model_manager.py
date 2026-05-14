"""Tests for LM Studio model lifecycle management."""

from __future__ import annotations

from typing import Any

from nexus.llm import model_manager
from nexus.llm.model_manager import ModelManager


class HandleThatMustNotVerify:
    """Model handle double that fails if chat verification is attempted."""

    def respond(self, *args: Any, **kwargs: Any) -> None:
        """Raise if the old verification path is invoked."""
        raise AssertionError("load_model should not run chat verification")


class StubLms:
    """Small stand-in for the lmstudio module."""

    def __init__(self) -> None:
        self.llm_calls: list[tuple[str | None, dict[str, Any] | None]] = []

    def llm(
        self, model_id: str | None = None, config: dict[str, Any] | None = None
    ) -> HandleThatMustNotVerify:
        """Capture load/attach calls and return a model handle."""
        self.llm_calls.append((model_id, config))
        return HandleThatMustNotVerify()


def _bare_manager() -> ModelManager:
    """Build a ModelManager without configuring the real LM Studio client."""
    manager = ModelManager.__new__(ModelManager)
    manager.settings = {
        "Agent Settings": {
            "global": {
                "llm": {"context_window": 2048},
            }
        }
    }
    manager.current_model = None
    manager.current_model_id = None
    manager.unload_on_exit = True
    manager.lmstudio_api_base = "http://localhost:1234"
    return manager


def test_load_model_skips_chat_verification(monkeypatch) -> None:
    """Loading should succeed once a handle is acquired without respond()."""
    manager = _bare_manager()
    loaded_sequences = iter([[], ["nexveridian/gpt-oss-120b"]])
    stub_lms = StubLms()

    monkeypatch.setattr(model_manager, "lms", stub_lms)
    monkeypatch.setattr(model_manager.time, "sleep", lambda seconds: None)
    manager.get_loaded_models = lambda: next(loaded_sequences)

    assert manager.load_model("nexveridian/gpt-oss-120b", context_window=4096) is True
    assert manager.current_model_id == "nexveridian/gpt-oss-120b"
    assert stub_lms.llm_calls == [("nexveridian/gpt-oss-120b", {"contextLength": 4096})]


def test_load_model_attaches_when_requested_model_is_already_loaded(
    monkeypatch,
) -> None:
    """load_model should share the ensure_default_model pre-loaded fast path."""
    manager = _bare_manager()
    stub_lms = StubLms()

    monkeypatch.setattr(model_manager, "lms", stub_lms)
    manager.get_loaded_models = lambda: ["nexveridian/gpt-oss-120b"]

    assert manager.load_model("nexveridian/gpt-oss-120b") is True
    assert manager.current_model_id == "nexveridian/gpt-oss-120b"
    assert stub_lms.llm_calls == [("nexveridian/gpt-oss-120b", None)]


def test_openai_compatible_models_endpoint_is_not_loaded_inventory(
    monkeypatch,
) -> None:
    """/v1/models is not a reliable loaded-model inventory endpoint."""
    manager = _bare_manager()
    requested_urls: list[str] = []

    class Response:
        """HTTP response double for unavailable loaded-model endpoints."""

        status_code = 404

        def raise_for_status(self) -> None:
            """Represent a response that should be skipped before raising."""
            return None

        def json(self) -> dict[str, Any]:
            """Return an empty payload."""
            return {"data": []}

    def fake_get(url: str, timeout: int) -> Response:
        requested_urls.append(url)
        return Response()

    monkeypatch.setattr(model_manager.requests, "get", fake_get)

    assert manager._get_loaded_models_via_http() is None
    assert requested_urls == [
        "http://localhost:1234/api/v0/models",
        "http://localhost:1234/api/v0/models/list",
        "http://localhost:1234/api/models",
        "http://localhost:1234/models",
    ]


def test_unflagged_model_entries_are_not_counted_as_loaded(monkeypatch) -> None:
    """Downloaded model entries without loaded state should not skip loading."""
    manager = _bare_manager()

    class Response:
        """HTTP response double with unflagged model entries."""

        status_code = 200

        def raise_for_status(self) -> None:
            """Represent a successful response."""
            return None

        def json(self) -> dict[str, Any]:
            """Return model IDs without loaded-state fields."""
            return {"data": [{"id": "nexveridian/gpt-oss-120b"}]}

    def fake_get(url: str, timeout: int) -> Response:
        return Response()

    monkeypatch.setattr(model_manager.requests, "get", fake_get)

    assert manager._get_loaded_models_via_http() == []

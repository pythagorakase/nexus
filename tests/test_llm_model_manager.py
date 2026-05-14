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
    assert stub_lms.llm_calls == [(None, None)]


def test_v1_models_endpoint_identifiers_count_as_loaded(monkeypatch) -> None:
    """The OpenAI-compatible LM Studio model list contains loaded model IDs."""
    manager = _bare_manager()
    requested_urls: list[str] = []

    class Response:
        """HTTP response double for the /v1/models probe."""

        status_code = 200

        def raise_for_status(self) -> None:
            """Represent a successful response."""
            return None

        def json(self) -> dict[str, Any]:
            """Return an OpenAI-compatible model list payload."""
            return {"data": [{"id": "nexveridian/gpt-oss-120b"}]}

    def fake_get(url: str, timeout: int) -> Response:
        requested_urls.append(url)
        return Response()

    monkeypatch.setattr(model_manager.requests, "get", fake_get)

    assert manager._get_loaded_models_via_http() == ["nexveridian/gpt-oss-120b"]
    assert requested_urls == ["http://localhost:1234/v1/models"]

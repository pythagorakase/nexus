"""Tests for lazy initialization of LOGON provider."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_utility import LogonUtility


class _DummyResponse:
    def __init__(self, prompt: str):
        self.content = f"dummy:{prompt[:20]}"
        self.input_tokens = 1
        self.output_tokens = 1
        self.model = "dummy-model"
        self.raw_response = {"prompt": prompt}


class _DummyProvider:
    def get_completion(self, prompt: str) -> _DummyResponse:
        return _DummyResponse(prompt)


@pytest.fixture()
def patched_provider(monkeypatch: pytest.MonkeyPatch) -> Dict[str, int]:
    """Patch provider initialization so tests never hit real services."""

    init_calls = {"count": 0}

    def _fake_initialize(self: LogonUtility) -> None:
        init_calls["count"] += 1
        self.provider = _DummyProvider()

    monkeypatch.setattr(LogonUtility, "_initialize_provider", _fake_initialize)
    return init_calls


def _minimal_payload() -> Dict[str, Any]:
    return {
        "user_input": "Test user input",
        "warm_slice": {"chunks": []},
        "entity_data": {},
        "retrieved_passages": {"results": []},
    }


@pytest.mark.requires_local_llm
@pytest.mark.requires_postgres
def test_lore_leaves_logon_lazy(patched_provider: Dict[str, int]) -> None:
    """LORE should not initialize LOGON on construction when lazy."""

    lore = LORE(debug=True, enable_logon=True)
    assert patched_provider["count"] == 0
    assert lore.logon is None


@pytest.mark.requires_local_llm
@pytest.mark.requires_postgres
def test_logon_initializes_on_first_use(patched_provider: Dict[str, int]) -> None:
    """LOGON provider should initialize when narrative generation is requested."""

    lore = LORE(debug=True, enable_logon=True)
    lore.ensure_logon()
    assert lore.logon is not None
    assert patched_provider["count"] == 0

    response = lore.logon.generate_narrative(_minimal_payload())

    assert patched_provider["count"] == 1
    assert response.content.startswith("dummy:")

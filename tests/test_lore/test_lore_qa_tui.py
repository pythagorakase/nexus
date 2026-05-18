"""Tests for LORE Q&A display helpers."""

from __future__ import annotations

from typing import Any, Dict

import pytest

pytest.importorskip("textual")

from nexus.agents.lore.lore_qa_tui import (  # noqa: E402
    collect_directive_field,
    format_retrieval_context,
)


def test_format_retrieval_context_uses_directive_payloads() -> None:
    """Direct retrieval payloads should render useful text without an answer."""

    result: Dict[str, Any] = {
        "directives": {
            "Where is Victor?": {
                "retrieved_context": "Retrieval directive: Where is Victor?\n\n[Source 1] ...",
            },
            "What does Emilia know?": {
                "retrieved_context": "Retrieval directive: What does Emilia know?\n\n[Source 2] ...",
            },
        }
    }

    rendered = format_retrieval_context(result)

    assert "Where is Victor?" in rendered
    assert "[Source 1]" in rendered
    assert "---" in rendered
    assert "What does Emilia know?" in rendered


def test_collect_directive_field_flattens_per_directive_metadata() -> None:
    """Telemetry tables consume direct retrieval metadata from each directive."""

    result: Dict[str, Any] = {
        "directives": {
            "a": {"search_progress": [{"query": "alpha", "result_count": 1}]},
            "b": {"search_progress": [{"query": "beta", "result_count": 2}]},
        }
    }

    assert collect_directive_field(result, "search_progress") == [
        {"query": "alpha", "result_count": 1},
        {"query": "beta", "result_count": 2},
    ]

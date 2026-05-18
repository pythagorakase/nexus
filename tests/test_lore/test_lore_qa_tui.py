"""Tests for LORE Q&A display helpers."""

from __future__ import annotations

from typing import Any, Dict

import pytest

pytest.importorskip("textual")

from nexus.agents.lore.lore_qa_tui import (  # noqa: E402
    collect_directive_field,
    format_reasoning_metadata,
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


def test_format_retrieval_context_preserves_answer_fast_path() -> None:
    """Legacy answer-shaped payloads should not duplicate directive context."""

    result: Dict[str, Any] = {
        "answer": "Victor is still hidden.",
        "directives": {
            "Where is Victor?": {"retrieved_context": "Duplicate context."},
        },
    }

    assert format_retrieval_context(result) == "Victor is still hidden."


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


def test_collect_directive_field_can_exclude_scalars_for_list_fields() -> None:
    """List-oriented table paths should not receive scalar metadata by accident."""

    result: Dict[str, Any] = {
        "directives": {
            "a": {"search_progress": "not-a-progress-row"},
            "b": {"search_progress": [{"query": "beta", "result_count": 2}]},
        }
    }

    assert collect_directive_field(
        result, "search_progress", include_scalars=False
    ) == [{"query": "beta", "result_count": 2}]


def test_format_reasoning_metadata_uses_directive_reasoning() -> None:
    """Markdown exports should include reasoning from directive payloads."""

    result: Dict[str, Any] = {
        "directives": {
            "a": {"reasoning": {"mode": "direct_memnon_retrieval", "query_count": 1}},
            "b": {"reasoning": {"mode": "direct_memnon_retrieval", "query_count": 2}},
        }
    }

    rendered = format_reasoning_metadata(result)

    assert '"query_count": 1' in rendered
    assert '"query_count": 2' in rendered

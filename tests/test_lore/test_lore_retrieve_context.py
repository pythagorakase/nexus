"""Tests for legacy LORE contextual retrieval."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from nexus.agents.lore.lore import LORE


class FakeMemnon:
    """Small MEMNON stand-in for direct retrieval tests."""

    def __init__(
        self, chunk_text: str = "Victor vanished below the transit concourse."
    ) -> None:
        self.queries: list[str] = []
        self.recent_chunk_calls = 0
        self.chunk_text = chunk_text

    def get_chunk_by_id(self, chunk_id: int) -> Dict[str, Any]:
        return {
            "id": chunk_id,
            "full_text": self.chunk_text,
        }

    def query_memory(
        self,
        query: str,
        filters: object | None = None,
        k: int = 8,
        use_hybrid: bool = True,
    ) -> Dict[str, Any]:
        self.queries.append(query)
        return {
            "metadata": {"result_count": 1},
            "results": [
                {
                    "id": len(self.queries),
                    "chunk_id": len(self.queries),
                    "text": f"Retrieved context for {query[:24]}",
                    "score": 0.9,
                }
            ],
        }

    def get_recent_chunks(self, limit: int) -> Dict[str, Any]:
        self.recent_chunk_calls += 1
        return {"results": []}


@pytest.mark.asyncio
async def test_retrieve_context_uses_direct_memnon_queries_without_local_llm() -> None:
    """The legacy retrieval helper should no longer initialize local inference."""

    lore = LORE.__new__(LORE)
    lore.memnon = FakeMemnon()
    lore.settings = {}

    result = await lore.retrieve_context(["Where did Victor go?"], chunk_id=42)

    assert not hasattr(lore, "llm_manager")
    assert lore.memnon.queries == [
        "Where did Victor go",
        "Victor vanished below the transit concourse.",
    ]
    directive = result["directives"]["Where did Victor go?"]
    assert directive["reasoning"]["mode"] == "direct_memnon_retrieval"
    assert directive["sql_attempts"] == []
    assert result["sources"] == [1, 2]
    assert result["memory_sources"] == [1, 2]
    assert directive["memory_sources"] == [1, 2]


@pytest.mark.asyncio
async def test_retrieve_context_caps_target_chunk_query_text() -> None:
    """Full chunk text should not be sent to MEMNON as an unbounded query."""

    lore = LORE.__new__(LORE)
    lore.memnon = FakeMemnon(chunk_text="A" * 750)
    lore.settings = {}

    await lore.retrieve_context(["Track the fallout"], chunk_id=42)

    assert lore.memnon.queries == [
        "Track the fallout",
        "A" * 500,
    ]


@pytest.mark.asyncio
async def test_retrieve_context_without_chunk_uses_only_directive_query() -> None:
    """The unanchored path should not build unused recent-chunk context."""

    lore = LORE.__new__(LORE)
    lore.memnon = FakeMemnon()
    lore.settings = {}

    result = await lore.retrieve_context(["Who is Victor hiding from?"], chunk_id=None)

    assert lore.memnon.queries == ["Who is Victor hiding from"]
    assert lore.memnon.recent_chunk_calls == 0
    directive = result["directives"]["Who is Victor hiding from?"]
    assert directive["reasoning"] == {
        "mode": "direct_memnon_retrieval",
        "query_count": 1,
        "target_chunk_id": None,
    }
    assert directive["sql_attempts"] == []

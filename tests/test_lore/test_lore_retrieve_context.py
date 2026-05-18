"""Tests for legacy LORE contextual retrieval."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from nexus.agents.lore.lore import LORE


class FakeMemnon:
    """Small MEMNON stand-in for direct retrieval tests."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def get_chunk_by_id(self, chunk_id: int) -> Dict[str, Any]:
        return {
            "id": chunk_id,
            "full_text": "Victor vanished below the transit concourse.",
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
        return {"results": []}


@pytest.mark.asyncio
async def test_retrieve_context_uses_direct_memnon_queries_without_local_llm() -> None:
    """The legacy retrieval helper should no longer initialize LM Studio."""

    lore = LORE.__new__(LORE)
    lore.memnon = FakeMemnon()
    lore.settings = {}
    lore.llm_manager = None

    result = await lore.retrieve_context(["Where did Victor go?"], chunk_id=42)

    assert lore.llm_manager is None
    assert lore.memnon.queries == [
        "Where did Victor go",
        "Victor vanished below the transit concourse.",
    ]
    directive = result["directives"]["Where did Victor go?"]
    assert directive["reasoning"]["mode"] == "direct_memnon_retrieval"
    assert directive["sql_attempts"] == []
    assert result["sources"] == [1, 2]

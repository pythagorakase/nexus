"""Typed-memory identity checks for narrative and Retrograde retrieval."""

from __future__ import annotations

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.lore import (
    _direct_retrieval_source_label,
    _retrieval_memory_sources,
)
from nexus.agents.lore.utils.turn_cycle import (
    _deduplicate_retrieval_results,
    _narrative_chunk_ids,
)
from nexus.memory import ContextMemoryManager
from nexus.memory.context_state import memory_identity
from nexus.memory.divergence import DivergenceResult
from nexus.memory.incremental import _normalize_retrieval_memory
from nexus.memory.manager import Pass2Update
from nexus.memory.retrieval_coverage import coerce_chunk_id


def _summary(summary_id: int, text: str = "A season-zero consequence.") -> dict:
    memory_id = f"retrograde_summary:{summary_id}"
    return {
        "id": memory_id,
        "memory_id": memory_id,
        "summary_id": summary_id,
        "world_event_id": summary_id + 100,
        "content_type": "retrograde_summary",
        "text": text,
        "score": 0.8,
        "metadata": {"recorded_at_chunk_id": 12},
    }


def test_typed_memory_identity_separates_summary_from_same_numbered_chunk() -> None:
    narrative = {"id": "7", "text": "The playable scene continues."}
    summary = _summary(7)

    assert memory_identity(narrative) == 7
    assert memory_identity(summary) == "retrograde_summary:7"
    assert coerce_chunk_id(narrative) == 7
    assert coerce_chunk_id(summary) is None
    assert "chunk_id" not in summary

    summary_identity, normalized_summary = _normalize_retrieval_memory(summary)
    assert summary_identity == "retrograde_summary:7"
    assert "chunk_id" not in normalized_summary


def test_retrieval_deduplication_uses_typed_memory_identity() -> None:
    lower_summary = _summary(7, "Lower-scoring summary.")
    lower_summary["score"] = 0.2
    higher_summary = _summary(7, "Higher-scoring summary.")
    higher_summary["score"] = 0.9
    narrative = {"id": "7", "text": "The playable scene.", "score": 0.7}

    deduplicated = _deduplicate_retrieval_results(
        [lower_summary, narrative, higher_summary]
    )

    assert [memory_identity(memory) for memory in deduplicated] == [
        "retrograde_summary:7",
        7,
    ]
    assert deduplicated[0]["text"] == "Higher-scoring summary."
    assert _narrative_chunk_ids(deduplicated) == [7]


def test_pass_state_keeps_and_deduplicates_typed_summary_memories() -> None:
    manager = ContextMemoryManager({"memory": {}})
    summary = _summary(7)

    package = manager.handle_storyteller_response(
        narrative="The playable scene continues.",
        warm_slice=[{"id": "7", "text": "The playable scene continues."}],
        retrieved_passages=[summary],
        token_usage={"total_available": 1000, "warm_slice": 10},
    )

    assert package.baseline_chunks == {7, "retrograde_summary:7"}
    assert package.structured_passages == []
    assert {
        memory_identity(memory) for memory in manager.context_state.get_all_chunks()
    } == {
        7,
        "retrograde_summary:7",
    }

    additions = manager.context_state.register_additional_chunks(
        [summary, _summary(8), {"id": "8", "text": "A later playable scene."}]
    )

    assert {memory_identity(memory) for memory in additions} == {
        8,
        "retrograde_summary:8",
    }
    assert manager.context_state.context is not None
    assert manager.context_state.context.additional_chunks == {
        8,
        "retrograde_summary:8",
    }


def test_chunk_id_status_excludes_retrograde_summaries() -> None:
    update = Pass2Update(
        divergence=DivergenceResult(False, 0.0, {}, set(), set()),
        retrieved_chunks=[
            _summary(9),
            {"id": "9", "text": "A narrative retrieval."},
        ],
        tokens_used=12,
    )

    status = update.to_dict()
    assert status["retrieved_memory_ids"] == ["retrograde_summary:9", 9]
    assert status["retrieved_chunk_ids"] == [9]


def test_prompts_label_each_retrieval_corpus_without_fake_chunk_ids() -> None:
    summary = _summary(9)
    narrative = {"id": "9", "text": "A narrative retrieval.", "score": 0.7}

    prompt = LogonUtility({})._format_context_prompt(
        {
            "user_input": "Continue.",
            "retrieved_passages": {"results": [summary, narrative]},
        }
    )

    assert "[Retrograde summary 9 | Score: 0.80]" in prompt
    assert "[Chunk 9 | Score: 0.70]" in prompt
    assert "Chunk retrograde_summary:9" not in prompt
    assert _direct_retrieval_source_label(summary) == "Retrograde summary 9"
    assert _direct_retrieval_source_label(narrative) == "Chunk 9"
    assert _direct_retrieval_source_label({"text": "Unidentified."}) == (
        "Retrieved passage"
    )
    assert _retrieval_memory_sources([summary, narrative, summary]) == [
        "retrograde_summary:9",
        9,
    ]

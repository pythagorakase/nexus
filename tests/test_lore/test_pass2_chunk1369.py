"""Integration test verifying Pass 2 retrieves karaoke context when baseline is naive."""

from __future__ import annotations

import logging
from typing import Dict, List

import pytest
from sqlalchemy import text

from nexus.agents.lore.lore import LORE

KARAOKE_CHUNK_ID = 1369
KARAOKE_DEEP_CUT_RANGE = range(743, 770)
AUTHORIAL_DIRECTIVES = [
    "Recent private outings between Alex and Emilia since leaving the Cradle",
    "Nyati's corporate campaign progress and current leverage",
    "Pete and Alina collaboration highlights aboard The Ghost",
]


def _strip_user_section(full_text: str) -> str:
    """Remove any trailing '## You' section so baseline stays naive."""
    marker = "\n## You"
    return full_text.split(marker, 1)[0]


@pytest.fixture(scope="module")
def lore_agent() -> LORE:
    """Instantiate LORE once with API calls disabled."""
    lore = LORE(debug=True, enable_logon=False)
    return lore


def _build_warm_slice(lore: LORE, chunk_id: int, span: int = 4) -> List[Dict[str, object]]:
    start_id = max(1, chunk_id - span)
    with lore.memnon.Session() as session:
        rows = session.execute(
            text(
                """
                SELECT id, raw_text
                FROM narrative_chunks
                WHERE id BETWEEN :start AND :end
                ORDER BY id
                """
            ),
            {"start": start_id, "end": chunk_id},
        ).fetchall()
    return [{"chunk_id": row.id, "text": row.raw_text} for row in rows]


def _gather_structured_data(lore: LORE) -> Dict[str, List[Dict[str, object]]]:
    characters: List[Dict[str, object]] = []
    locations: List[Dict[str, object]] = []
    for name in ["Alex", "Emilia", "Nyati", "Pete", "Alina"]:
        characters.extend(lore.memnon._query_structured_data(name, "characters", limit=2))
    for loc in ["The Ghost", "Boudreaux"]:
        locations.extend(lore.memnon._query_structured_data(loc, "places", limit=2))
    return {"characters": characters, "locations": locations}


def _execute_authorial_queries(lore: LORE) -> List[Dict[str, object]]:
    retrieved: List[Dict[str, object]] = []
    for directive in AUTHORIAL_DIRECTIVES:
        result = lore.memnon.query_memory(query=directive, k=6, use_hybrid=True)
        retrieved.extend(result.get("results", []))
    return retrieved


def test_pass2_handles_karaoke_divergence(lore_agent: LORE, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="nexus")

    chunk = lore_agent.memnon.get_chunk_by_id(KARAOKE_CHUNK_ID)
    assert chunk is not None, "Chunk 1369 missing from corpus"
    storyteller_only = _strip_user_section(chunk["full_text"])
    assert "karaoke" not in storyteller_only.lower()

    warm_slice = _build_warm_slice(lore_agent, KARAOKE_CHUNK_ID)
    authorial_passages = _execute_authorial_queries(lore_agent)
    structured = _gather_structured_data(lore_agent)

    token_counts = lore_agent.token_manager.calculate_budget("karaoke divergence probe")

    baseline = lore_agent.memory_manager.handle_storyteller_response(
        narrative=storyteller_only,
        warm_slice=warm_slice,
        retrieved_passages=authorial_passages,
        token_usage=token_counts,
        assembled_context={
            "user_input": "(storyteller output)",
            "warm_slice": {"chunks": warm_slice},
            "entity_data": structured,
            "retrieved_passages": {"results": authorial_passages},
        },
    )

    assert KARAOKE_CHUNK_ID in baseline.baseline_chunks

    divergence_prompt = (
        "Walk me back through the Virginia Beach karaoke ambush—the Driftlight cocktails, "
        "Pete's duet trap, and why Emilia swore off stage lights after that meltdown."
    )

    update = lore_agent.memory_manager.handle_user_input(
        user_input=divergence_prompt,
        token_counts=token_counts,
    )

    assert update.baseline_available is True
    assert update.divergence.detected is True
    assert update.retrieved_chunks

    additional_ids = {
        int(chunk.get("chunk_id") or chunk.get("id"))
        for chunk in lore_agent.memory_manager.context_state.get_additional_chunk_details()
    }
    additional_ids.discard(None)
    karaoke_hits = [cid for cid in additional_ids if cid in KARAOKE_DEEP_CUT_RANGE]
    assert karaoke_hits, f"Expected karaoke chunks in {KARAOKE_DEEP_CUT_RANGE}, got {sorted(additional_ids)}"

    summary = lore_agent.memory_manager.get_memory_summary()
    assert summary["pass2"]["divergence_detected"] is True
    assert summary["pass2"]["usage"]["remaining_budget"] >= 0

    assert structured["characters"], "Structured character summaries should be present"

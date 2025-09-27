"""Integration test verifying Pass 2 retrieves karaoke context when baseline is naive."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List

import pytest
from sqlalchemy import text

from nexus.agents.lore.lore import LORE
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager

KARAOKE_CHUNK_ID = 1369
KARAOKE_DEEP_CUT_RANGE = range(743, 770)
AUTHORIAL_DIRECTIVES = [
    "Recent private outings between Alex and Emilia since leaving the Cradle",
    "Nyati's corporate campaign progress and current leverage",
    "Pete and Alina collaboration highlights aboard The Ghost",
]


def _strip_user_section(full_text: str) -> str:
    marker = "\n## You"
    return full_text.split(marker, 1)[0]


@pytest.fixture(scope="module")
def lore_agent() -> LORE:
    return LORE(debug=True, enable_logon=False)


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
    return [{"id": row.id, "chunk_id": row.id, "text": row.raw_text} for row in rows]


def _execute_authorial_queries(lore: LORE) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    for directive in AUTHORIAL_DIRECTIVES:
        payload = lore.memnon.query_memory(query=directive, k=6, use_hybrid=True)
        results.extend(payload.get("results", []))
    return results


def _run_pass1_phases(
    lore: LORE,
    warm_slice: List[Dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> TurnContext:
    turn_manager = TurnCycleManager(lore)
    ctx = TurnContext(
        turn_id=f"turn_{int(time.time())}",
        user_input="Capture any dinner follow-up threads",
        start_time=time.time(),
    )

    monkeypatch.setattr(lore.memnon, "get_recent_chunks", lambda limit=5: {"results": warm_slice})

    async def _run() -> None:
        await turn_manager.process_user_input(ctx)
        await turn_manager.perform_warm_analysis(ctx)
        await turn_manager.query_entity_states(ctx)

    asyncio.run(_run())
    return ctx


def test_pass2_handles_karaoke_divergence(
    lore_agent: LORE,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.INFO, logger="nexus")

    chunk = lore_agent.memnon.get_chunk_by_id(KARAOKE_CHUNK_ID)
    assert chunk is not None, "Chunk 1369 missing from corpus"
    storyteller_only = _strip_user_section(chunk["full_text"])
    assert "karaoke" not in storyteller_only.lower()

    warm_slice = _build_warm_slice(lore_agent, KARAOKE_CHUNK_ID)
    token_counts = lore_agent.token_manager.calculate_budget("karaoke divergence probe")
    context = _run_pass1_phases(lore_agent, warm_slice, monkeypatch)
    authorial_passages = _execute_authorial_queries(lore_agent)

    analysis = context.phase_states.get("warm_analysis", {}).get("analysis", {})
    assert analysis.get("characters"), "Warm analysis should capture characters for notes"
    assert context.entity_data.get("characters"), "Structured character lookups should be populated"

    baseline = lore_agent.memory_manager.handle_storyteller_response(
        narrative=storyteller_only,
        warm_slice=context.warm_slice,
        retrieved_passages=authorial_passages,
        token_usage=token_counts,
        assembled_context={
            "user_input": context.user_input,
            "warm_slice": {"chunks": context.warm_slice},
            "entity_data": context.entity_data,
            "retrieved_passages": {"results": authorial_passages},
            "analysis": analysis,
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

    assert context.entity_data["characters"], "Structured character summaries should be present"


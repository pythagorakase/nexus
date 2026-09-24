"""Chronological rendering through the real shared TEST prompt path."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.agents.lore.utils.scene_order import recalled_clock_label
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.memory import ContextMemoryManager
from nexus.memory.context_state import ContextPackage, PassTransition
from tests.test_lore.window_helpers import window_logon


def scene_payload() -> dict[str, Any]:
    """Supply intentionally disordered warm, incremental, and summary memories."""
    return {
        "user_input": "Continue.",
        "warm_slice": {
            "chunks": [
                {"id": 49, "text": "Parent scene.", "is_target": True},
                {"id": "48", "text": "Earlier scene."},
                {
                    "id": 8,
                    "text": "Remembered scene.",
                    "is_recalled": True,
                    "metadata": {"world_time": "2189-10-17T15:27:00-04:00"},
                },
            ]
        },
        "retrieved_passages": {
            "results": [
                {"id": "retrograde_summary:3", "text": "Undated summary."},
                {
                    "id": "retrograde_summary:2",
                    "text": "Recorded summary.",
                    "metadata": {
                        "recorded_at_chunk_id": 46,
                        "recorded_at_world_time": "2189-10-17T18:23:00-04:00",
                    },
                },
                {"id": 1, "text": "Historical passage."},
            ]
        },
        "entity_data": {},
    }


def test_render_scene_order_and_recalled_clocks_match_both_seats() -> None:
    """The parent ends the warm scene and summaries use only recording clocks."""
    utility = window_logon()
    payload = scene_payload()
    original = deepcopy(payload)
    prompts = [
        utility._format_context_prompt(payload, seat=seat)
        for seat in ("writer", "gaia")
    ]
    assert prompts[0] == prompts[1]
    prompt = prompts[0]
    recent = prompt.split("=== RECENT NARRATIVE ===")[1].split("=== USER INPUT ===")[0]
    assert recent.strip() == "Earlier scene.\nParent scene."
    assert prompt.index("Historical passage.") < prompt.index("=== RECALLED SCENES ===")
    assert prompt.index("=== RECALLED SCENES ===") < prompt.index(
        "=== RECENT NARRATIVE ==="
    )
    recalled = prompt.split("=== RECALLED SCENES ===")[1]
    labels = [
        "[chunk 8 · 17 Oct 2189 · 19:27]",
        "[Retrograde summary 2 · recorded at chunk 46 · 17 Oct 2189 · 22:23 | Score: 0.00]",
        "[Retrograde summary 3 | Score: 0.00]",
    ]
    assert [recalled.index(label) for label in labels] == sorted(
        recalled.index(label) for label in labels
    )
    assert payload == original
    requests = utility.measure_turn_requests(payload, 75000)
    for request in requests:
        blocks = [value for kind, value in request.blocks if kind == "recalled scenes"]
        assert len(blocks) == 4
        assert all(label in "".join(blocks) for label in labels)


def test_render_recalled_missing_or_naive_clock_fails_loudly() -> None:
    """Neither missing time nor a storage timestamp becomes an event clock."""
    with pytest.raises(KeyError):
        recalled_clock_label(
            {"id": 8, "metadata": {"created_at": "2026-01-01T00:00:00Z"}}
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        recalled_clock_label(
            {"id": 8, "metadata": {"world_time": "2189-10-17T19:27:00"}}
        )
    with pytest.raises(KeyError):
        recalled_clock_label(
            {"id": "retrograde_summary:2", "metadata": {"recorded_at_chunk_id": 46}}
        )


def test_warm_additions_are_recalled_without_reclassifying_existing_scene() -> None:
    """The real memory-state path tags only additions, preserving deduplication."""
    utility = window_logon()
    manager = ContextMemoryManager(utility.settings)
    manager.context_state.store_baseline(
        ContextPackage(), PassTransition(storyteller_output="", remaining_budget=100)
    )
    additions = [{"id": 8, "text": "Recall."}, {"id": 48, "text": "Already warm."}]
    manager.context_state.register_additional_chunks(additions)
    chunks = manager.augment_warm_slice([{"id": 48, "text": "Already warm."}])
    assert len(chunks) == 2
    assert not chunks[0].get("is_recalled")
    assert chunks[1]["is_recalled"]
    assert not additions[0].get("is_recalled")


def test_window_trimming_removes_recalled_heading_and_counts_exactly() -> None:
    """Subtractive accounting equals fresh rendering after the lane disappears."""
    utility = window_logon()
    payload = scene_payload()
    payload["retrieved_passages"]["results"] = []
    payload["warm_slice"]["chunks"][-1]["text"] = " Remembered scene." * 40000
    context = TurnContext(
        turn_id="scene-order-trim", user_input="Continue.", start_time=0
    )
    context.context_payload = payload
    context.token_counts = {"total_available": 71000, "apex_window": 75000}
    cycle = TurnCycleManager(
        SimpleNamespace(
            settings=utility.settings,
            logon=utility,
            memory_manager=ContextMemoryManager(utility.settings),
        )
    )
    cycle._enforce_context_payload_budget(context)
    assert payload["window_trimming"]["dropped_chunk_ids"] == [8]
    assert payload["window_trimming"]["dropped_blocks"]["recalled scenes"] == 1
    fresh = utility.measure_turn_requests(payload, 75000)
    for trimmed, rerendered in zip(utility._assembly_window_requests, fresh):
        assert trimmed.tokens == rerendered.tokens
        assert not any(kind == "recalled scenes" for kind, _ in rerendered.blocks)


@pytest.mark.requires_postgres
def test_recalled_render_clocks_come_from_narrative_view() -> None:
    """Read chunk/recording clocks from a disposable PostgreSQL story.

    Requires narrative_chunks, chunk_metadata, and narrative_view; the fixture
    drops the database after the test, including failure paths.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from nexus.agents.lore.utils.scene_order import hydrate_recalled_clocks
    from tests.pg_fixtures import disposable_slot_database, sqlalchemy_url

    with disposable_slot_database("qa640_scene_clock") as dbname:
        engine = create_engine(sqlalchemy_url(dbname))
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO narrative_chunks (id, raw_text) VALUES (8, 'Recalled scene'), (46, 'Recording scene')"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO chunk_metadata (chunk_id, season, episode, scene) VALUES (8, 1, 1, 1), (46, 1, 1, 2)"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE chunk_metadata SET world_time = CASE chunk_id WHEN 8 THEN '2189-10-17T19:27:00Z'::timestamptz ELSE '2189-10-17T22:23:00Z'::timestamptz END"
                    )
                )
            memories = [
                {"id": 8, "is_recalled": True},
                {
                    "id": "retrograde_summary:2",
                    "metadata": {"recorded_at_chunk_id": 46},
                },
                {"id": "retrograde_summary:3"},
            ]
            with Session(engine) as session:
                hydrate_recalled_clocks(session, memories)
                assert (
                    recalled_clock_label(memories[0]) == "chunk 8 · 17 Oct 2189 · 19:27"
                )
                assert (
                    recalled_clock_label(memories[1])
                    == "Retrograde summary 2 · recorded at chunk 46 · 17 Oct 2189 · 22:23"
                )
                assert recalled_clock_label(memories[2]) == "Retrograde summary 3"
                with pytest.raises(ValueError, match="has no story clock"):
                    hydrate_recalled_clocks(
                        session,
                        [
                            {
                                "id": "retrograde_summary:4",
                                "metadata": {"recorded_at_chunk_id": 999},
                            }
                        ],
                    )
        finally:
            engine.dispose()

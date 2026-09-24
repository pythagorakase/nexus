"""Chronological rendering through the real shared TEST prompt path."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.agents.lore.utils.scene_order import recalled_clock_label
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.memory import ContextMemoryManager
from nexus.memory.context_state import ContextPackage, PassTransition, memory_identity
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
    assert (
        prompts[0].split("=== USER INPUT ===")[0]
        == prompts[1].split("=== USER INPUT ===")[0]
    )
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


def test_render_recalled_missing_clock_is_undated_but_naive_clock_fails() -> None:
    """Absent clocks stay undated; malformed clocks are still rejected."""
    assert (
        recalled_clock_label(
            {"id": 8, "metadata": {"created_at": "2026-01-01T00:00:00Z"}}
        )
        == "chunk 8"
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        recalled_clock_label(
            {"id": 8, "metadata": {"world_time": "2189-10-17T19:27:00"}}
        )
    assert (
        recalled_clock_label(
            {"id": "retrograde_summary:2", "metadata": {"recorded_at_chunk_id": 46}}
        )
        == "Retrograde summary 2"
    )


def test_render_deduplicates_all_sources_before_historical_cap() -> None:
    """Both seats pick one identity in its most specific lane and refill caps."""
    utility = window_logon()
    utility.settings["lore"]["render_limits"]["historical_passages"] = 2
    payload = scene_payload()
    summary = payload["retrieved_passages"]["results"][1]
    payload["warm_slice"]["chunks"].append(deepcopy(summary))
    payload["warm_slice"]["chunks"].append(
        {"id": 48, "is_recalled": True, "text": "Duplicate warm recall."}
    )
    payload["retrieved_passages"]["results"] = [
        {"id": 49, "text": "Duplicate parent."},
        {"id": 48, "text": "Duplicate recent."},
        {"id": "8", "text": "Duplicate recalled."},
        summary,
        {"id": 1, "text": "First distinct historical."},
        {"id": "1", "text": "Duplicate historical."},
        {"id": 2, "text": "Second distinct historical."},
        {"id": 3, "text": "Beyond cap."},
    ]
    original = deepcopy(payload)
    for request in utility.measure_turn_requests(payload, 75000):
        sources = {
            id(memory): memory_identity(memory)
            for memory in payload["warm_slice"]["chunks"]
            + payload["retrieved_passages"]["results"]
        }
        lanes = {}
        for index, source in request.sources.items():
            lanes.setdefault(request.blocks[index][0], []).append(sources[source])
        assert lanes == {
            "historical context": [1, 2],
            "recalled scenes": [8, "retrograde_summary:2"],
            "recent narrative": [48, 49],
        }
        prompt = "".join(content for _, content in request.blocks)
        assert prompt.count("Parent scene.") == 1
        assert prompt.count("Recorded summary.") == 1
        assert "Duplicate" not in prompt
        assert "Beyond cap." not in prompt
    assert payload == original


def test_render_recalled_lane_wins_over_earlier_historical_candidate() -> None:
    """Lane priority precedes rank when a deep result is also a recalled hit."""
    utility = window_logon()
    utility.settings["lore"]["render_limits"]["historical_passages"] = 1
    payload = scene_payload()
    payload["retrieved_passages"]["results"] = [
        {"id": 2, "text": "Duplicate historical."},
        {"id": 2, "text": "Preferred recalled.", "is_recalled": True},
        {"id": 3, "text": "Beyond cap."},
    ]
    for seat in ("writer", "gaia"):
        prompt = utility._format_context_prompt(payload, seat=seat)
        assert "Duplicate historical." not in prompt
        assert "Beyond cap." not in prompt
        assert "[chunk 2 | Score: 0.00] Preferred recalled." in prompt


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
    # Removing the winning copy must not resurrect a discarded deep duplicate.
    payload["retrieved_passages"]["results"] = [
        deepcopy(payload["warm_slice"]["chunks"][-1])
    ]
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
                missing = {
                    "id": "retrograde_summary:4",
                    "metadata": {"recorded_at_chunk_id": 999},
                }
                hydrate_recalled_clocks(session, [missing])
                assert recalled_clock_label(missing) == "Retrograde summary 4"
        finally:
            engine.dispose()


@pytest.mark.requires_postgres
def test_assembly_hydrates_only_selected_recalled_entries_with_null_clocks() -> None:
    """Real assembly skips a capped NULL anchor and renders selected NULLs undated.

    Uses narrative_chunks, chunk_metadata, and narrative_view in a fixture-owned
    disposable database. SQL observation proves excluded anchors are not hydrated.
    """
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import sessionmaker

    from tests.pg_fixtures import disposable_slot_database, sqlalchemy_url

    with disposable_slot_database("qa640_scene_null_clock") as dbname:
        engine = create_engine(sqlalchemy_url(dbname))
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO narrative_chunks (id, raw_text) VALUES "
                        "(8, 'Undated scene'), (46, 'Undated recording anchor')"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO chunk_metadata (chunk_id, season, episode, scene) "
                        "VALUES (8, 1, 1, 1), (46, 1, 1, 2)"
                    )
                )
                conn.execute(text("UPDATE chunk_metadata SET world_time = NULL"))

            hydrated_ids = []

            @event.listens_for(engine, "before_cursor_execute")
            def record_clock_query(
                conn: Any,
                cursor: Any,
                statement: str,
                parameters: Any,
                context: Any,
                executemany: bool,
            ) -> None:
                if "SELECT id, world_time FROM narrative_view" in statement:
                    hydrated_ids.append(parameters["ids"])

            utility = window_logon()
            utility.settings["orrery"]["enabled"] = False
            cycle = TurnCycleManager(
                SimpleNamespace(
                    settings=utility.settings,
                    enable_logon=False,
                    memnon=SimpleNamespace(Session=sessionmaker(bind=engine)),
                )
            )
            for limit in (1, 2):
                utility.settings["lore"]["render_limits"]["historical_passages"] = limit
                context = TurnContext(
                    turn_id=f"null-clock-{limit}", user_input="Continue.", start_time=0
                )
                context.warm_slice = [
                    {"id": 49, "text": "Parent scene.", "is_target": True},
                    {
                        "id": 8,
                        "text": "Undated recall.",
                        "is_recalled": True,
                        "metadata": {"world_time": "2189-10-17T19:27:00Z"},
                    },
                ]
                summary = {
                    "id": "retrograde_summary:2",
                    "text": "Undated summary.",
                    "metadata": {"recorded_at_chunk_id": 46},
                }
                context.retrieved_passages = [
                    {"id": 49, "text": "Duplicate parent."},
                    {"id": 1, "text": "Historical passage."},
                    summary,
                ]
                context.token_counts = {"total_available": 71000}
                asyncio.run(cycle.assemble_context_payload(context))
                assert hydrated_ids[-1] == ([8] if limit == 1 else [8, 46])
                for seat in ("writer", "gaia"):
                    prompt = utility._format_context_prompt(
                        context.context_payload, seat=seat
                    )
                    assert "[chunk 8] Undated recall." in prompt
                    assert "17 Oct 2189" not in prompt
                    assert "Duplicate parent." not in prompt
                    assert ("[Retrograde summary 2 | Score: 0.00]" in prompt) == (
                        limit == 2
                    )
                if limit == 1:
                    assert "recorded_at_world_time" not in summary["metadata"]
        finally:
            engine.dispose()


@pytest.mark.requires_postgres
def test_recent_warm_window_ends_at_historical_parent() -> None:
    """Read a parent ten scenes behind save_04's frontier on a disposable clone.

    Uses narrative_chunks and chunk_metadata through the real MEMNON query,
    warm analysis, and both TEST seat renderers; the source save is read only.
    """
    from sqlalchemy import text

    from nexus.agents.memnon.memnon import MEMNON
    from nexus.agents.orrery.reconstruction import playable_narrative_predicate
    from nexus.database import database_url
    from tests.pg_fixtures import disposable_slot_database

    with disposable_slot_database(
        "qa640_scene_parent", source_db="save_04", include_data=True
    ) as dbname:
        memnon = MEMNON(interface=None, db_url=database_url(dbname))
        try:
            utility = window_logon()
            count = utility.settings["lore"]["chunk_parameters"]["warm_slice_initial"]
            with memnon.Session() as session:
                ids = list(
                    session.execute(
                        text(
                            "SELECT nc.id FROM narrative_chunks nc WHERE "
                            f"{playable_narrative_predicate()} ORDER BY nc.id DESC"
                        )
                    ).scalars()
                )
            assert len(ids) >= 10 + count
            cycle = TurnCycleManager(
                SimpleNamespace(settings=utility.settings, memnon=memnon)
            )
            for offset in (10, 0):
                parent = ids[offset]
                expected = sorted(ids[offset : offset + count])
                context = TurnContext(
                    turn_id=f"parent-window-{parent}",
                    user_input="Continue.",
                    start_time=0,
                    target_chunk_id=parent,
                )
                asyncio.run(cycle.perform_warm_analysis(context))
                assert sorted(chunk["id"] for chunk in context.warm_slice) == expected
                assert (
                    sum(chunk.get("is_target", False) for chunk in context.warm_slice)
                    == 1
                )
                payload = {
                    "user_input": context.user_input,
                    "warm_slice": {"chunks": context.warm_slice},
                    "retrieved_passages": {"results": []},
                    "entity_data": {},
                }
                sources = {id(chunk): chunk["id"] for chunk in context.warm_slice}
                for request in utility.measure_turn_requests(payload, 75000):
                    rendered = [
                        sources[source]
                        for index, source in request.sources.items()
                        if request.blocks[index][0] == "recent narrative"
                    ]
                    assert rendered == expected
                    assert rendered[-1] == parent
                print(
                    f"WARM_WINDOW parent={parent} count={count} ids={expected}; both seats match"
                )
            assert [
                chunk["id"]
                for chunk in memnon.get_recent_chunks(limit=count)["results"]
            ] == ids[:count]
        finally:
            memnon.db_manager.engine.dispose()

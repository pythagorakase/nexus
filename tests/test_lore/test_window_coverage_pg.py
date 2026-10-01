"""PostgreSQL proof that post-render coverage excludes trimmed Pass-2 chunks."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from nexus.agents.lore.lore import LORE
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.memnon.memnon import MEMNON
from nexus.config import load_settings
from nexus.database import database_url
from nexus.memory import ContextMemoryManager
from nexus.memory.context_state import memory_identity
from nexus.memory.entity_detector import EntityMatch
from tests.pg_fixtures import (
    disposable_slot_database,
    route_slot_to_disposable,
    seed_protagonist,
)
from tests.test_lore.window_helpers import window_logon

pytestmark = pytest.mark.requires_postgres


def test_window_coverage_is_written_only_from_post_render_kept_chunks():
    with disposable_slot_database("qa640_window_coverage") as dbname:
        character_id, _ = seed_protagonist(
            dbname, name="Window Proof Player", summary="Window coverage fixture."
        )
        memnon = MEMNON(interface=None, db_url=database_url(dbname))
        try:
            settings = load_settings()
            manager = ContextMemoryManager(settings, memnon=memnon)
            with memnon.db_manager.engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO narrative_chunks (id, raw_text, storyteller_text) VALUES (42, 'Retained passage.', 'Retained passage.'), (43, 'Trimmed passage.', 'Trimmed passage.')"
                    )
                )
            with memnon.db_manager.engine.begin() as conn:
                conn.execute(
                    text("SELECT set_config('nexus.write_producer', 'manual', true)")
                )
                conn.execute(
                    text(
                        "INSERT INTO chunk_character_references (chunk_id, character_id, reference) VALUES (43, :character, 'mentioned')"
                    ),
                    {"character": character_id},
                )
            manager.handle_user_input("1", turn_id="pending-empty-coverage")
            with memnon.db_manager.engine.connect() as conn:
                assert (
                    conn.execute(
                        text(
                            "SELECT count(*) FROM retrieval_coverage_log WHERE turn_id = 'pending-empty-coverage'"
                        )
                    ).scalar_one()
                    == 0
                )
            chunks = [
                {"chunk_id": 42, "text": "Retained passage."},
                {"chunk_id": 43, "text": "Trimmed passage."},
            ]
            manager._stage_retrieval_coverage(
                incremental_retriever=manager.incremental,
                entity_match=EntityMatch(
                    characters=[{"id": character_id, "name": "Window Proof Player"}],
                    places=[],
                    factions=[],
                ),
                user_input="Recall the earlier passage.",
                raw_result_count=2,
                kept_chunks=chunks,
                kept_tokens=100,
                available_budget=1000,
                turn_id="post-render-coverage",
            )
            with memnon.db_manager.engine.connect() as conn:
                assert (
                    conn.execute(
                        text(
                            "SELECT count(*) FROM retrieval_coverage_log WHERE turn_id = 'post-render-coverage'"
                        )
                    ).scalar_one()
                    == 0
                )
            utility = window_logon(settings)
            payload = {
                "user_input": "Continue.",
                "warm_slice": {"chunks": chunks[:1]},
                "retrieved_passages": {"results": []},
                "entity_data": {},
            }
            request = utility.measure_turn_requests(payload, 75000)[0]
            rendered_tokens = sum(request.sizes[index] for index in request.sources)
            manager.record_rendered_coverage(chunks[:1], {42: rendered_tokens})
            manager.record_rendered_coverage(chunks[:1], {42: rendered_tokens})
            with memnon.db_manager.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT kept_chunk_ids, kept_tokens, raw_result_count, coverage, gap_entities FROM retrieval_coverage_log WHERE turn_id = 'post-render-coverage'"
                    )
                ).all()
            assert len(rows) == 1
            assert rows[0].kept_chunk_ids == [42]
            assert rows[0].kept_tokens == rendered_tokens
            assert rows[0].raw_result_count == 2
            assert rows[0].coverage == [
                {
                    "kind": "character",
                    "id": character_id,
                    "name": "Window Proof Player",
                    "covered": False,
                    "covering_chunk_ids": [],
                }
            ]
            assert rows[0].gap_entities == [
                {"kind": "character", "id": character_id, "name": "Window Proof Player"}
            ]
        finally:
            memnon.close()


@pytest.mark.parametrize("limit, repeats", [(5, 1), (15, 1), (15, 2500)])
def test_historical_coverage_matches_rendered_prefix(limit: int, repeats: int) -> None:
    """The real trim callback logs all and only printed historical passages."""
    from types import SimpleNamespace

    from nexus.agents.lore.utils.turn_context import TurnContext
    from nexus.agents.lore.utils.turn_cycle import TurnCycleManager

    with disposable_slot_database("qa640_historical_coverage") as dbname:
        seed_protagonist(
            dbname, name="Historical Proof Player", summary="Coverage proof."
        )
        memnon = MEMNON(interface=None, db_url=database_url(dbname))
        try:
            settings = load_settings()
            settings.lore.render_limits.historical_passages = limit
            manager = ContextMemoryManager(settings, memnon=memnon)
            passages = [
                {"chunk_id": i, "text": " Passage." * repeats} for i in range(1, 17)
            ]
            with memnon.db_manager.engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO narrative_chunks (id, raw_text, storyteller_text) "
                        "VALUES (:chunk_id, :text, :text)"
                    ),
                    passages,
                )
            manager._stage_retrieval_coverage(
                incremental_retriever=manager.incremental,
                entity_match=EntityMatch(characters=[], places=[], factions=[]),
                user_input="Recall.",
                raw_result_count=len(passages),
                kept_chunks=passages,
                kept_tokens=1,
                available_budget=71000,
                turn_id="historical-coverage",
            )
            utility = window_logon(settings)
            context = TurnContext(
                turn_id="historical-coverage", user_input="Recall.", start_time=0
            )
            context.context_payload = {
                "user_input": "Recall.",
                "warm_slice": {"chunks": []},
                "retrieved_passages": {"results": passages},
                "entity_data": {},
            }
            context.token_counts = {"total_available": 71000, "apex_window": 75000}
            cycle = TurnCycleManager(
                SimpleNamespace(
                    settings=settings, logon=utility, memory_manager=manager
                )
            )
            cycle._enforce_context_payload_budget(context)
            writer = utility._assembly_window_requests[0]
            printed = {
                source
                for index, source in writer.sources.items()
                if index not in writer.removed
            }
            expected = [p["chunk_id"] for p in passages if id(p) in printed]
            if repeats == 1:
                assert expected == list(range(1, limit + 1))
            else:
                assert 5 < len(expected) < limit
                assert expected == list(range(1, len(expected) + 1))
            utility.record_rendered_coverage()
            utility.record_rendered_coverage()
            with memnon.db_manager.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT kept_chunk_ids, kept_tokens FROM retrieval_coverage_log "
                        "WHERE turn_id = 'historical-coverage'"
                    )
                ).all()
            assert len(rows) == 1
            assert rows[0].kept_chunk_ids == expected
            assert rows[0].kept_tokens == sum(
                writer.sizes[index]
                for index in writer.sources
                if index not in writer.removed
            )
        finally:
            memnon.close()


@pytest.mark.requires_corpus
@pytest.mark.parametrize("k", [3, 15])
def test_configured_k_bounds_the_deep_query_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    k: int,
) -> None:
    """Real corpus retrieval from narrative_chunks honors configured breadth."""
    config = tmp_path / "nexus.toml"
    config.write_text(
        Path("nexus.toml")
        .read_text()
        .replace("deep_query_k = 15", f"deep_query_k = {k}")
    )
    with disposable_slot_database(
        "qa640_756_deep_query",
        source_db="save_01",
        include_data=True,
    ) as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        lore = LORE(
            settings_path=str(config),
            enable_logon=False,
            debug=False,
            dbname=dbname,
            model_override="TEST",
        )
        try:
            assert lore.memnon is not None
            assert lore.turn_manager is not None
            with lore.memnon.db_manager.engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT id, raw_text FROM narrative_chunks "
                        "WHERE raw_text IS NOT NULL AND btrim(raw_text) <> '' "
                        "ORDER BY id LIMIT 1"
                    )
                ).first()
            assert row is not None
            chunk_id, raw_text = row
            query = " ".join(raw_text.split()[:32])
            assert query
            broad = lore.memnon.query_memory(query=query, k=30, use_hybrid=True)
            broad_count = len(broad["results"])
            assert broad_count > 15
            context = TurnContext(
                turn_id="756-deep-query-count",
                user_input=query,
                start_time=0,
                warm_slice=[{"id": chunk_id, "is_target": True, "full_text": query}],
            )
            asyncio.run(lore.turn_manager.execute_deep_queries(context))
            state = context.phase_states["deep_queries"]
            with capsys.disabled():
                print(
                    f"756-S2: k={k}; chunk_id={chunk_id}; query={query!r}; "
                    f"broad_count={broad_count}; "
                    f"results_retrieved={state['results_retrieved']}; "
                    f"pool_count={len(context.retrieved_passages)}"
                )
            assert state["queries_executed"] == 1
            assert state["results_retrieved"] == k
            assert len(context.retrieved_passages) == k
            identities = [
                memory_identity(result) for result in context.retrieved_passages
            ]
            assert all(identity is not None for identity in identities)
            assert len(set(identities)) == k
        finally:
            lore.close()

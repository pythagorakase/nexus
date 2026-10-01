"""PostgreSQL proof that post-render coverage excludes trimmed Pass-2 chunks."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4
import asyncio

import pytest
from sqlalchemy import text

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.lore.lore import LORE
from nexus.agents.memnon.memnon import MEMNON
from nexus.config import load_settings
from nexus.database import database_url
from nexus.memory import ContextMemoryManager
from nexus.memory.context_state import memory_identity
from nexus.memory.entity_detector import EntityMatch
from nexus.telemetry.attempt_manifest import inspect_turn, manifest_scope
from nexus.telemetry.turn_observation import observe_turn
from nexus.telemetry.usage import read_prompt_windows
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_protagonist,
)
from tests.scheduler_helpers import run_cli, test_provider_config as configure_test
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401
from tests.test_lore.test_turn_cycle import _cached_removals, _distinct_removal_requests
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


def _seed_removal_session(dbname: str, session: str) -> None:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_generation_sessions "
            "(session_id, operation, status) "
            "VALUES (%s, 'continue', 'initiated')",
            (session,),
        )
        cur.execute(
            "INSERT INTO generation_session_phases (generation_session_id, phase) "
            "VALUES (%s, 'assembly')",
            (session,),
        )


@pytest.mark.parametrize("pipeline", ["two_pass", "single_pass"])
def test_removed_tokens_reach_real_attempt_manifest_and_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
    pipeline: Literal["two_pass", "single_pass"],
) -> None:
    """Real TEST generation preserves seat maps, actual input sums and kept coverage."""
    configure_test(tmp_path, "http://127.0.0.1:1", monkeypatch)
    endpoint = request.getfixturevalue("mock_openai_server")
    configure_test(tmp_path, endpoint, monkeypatch)
    with disposable_slot_database("qa640_756s1_generation") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        seed_protagonist(dbname, name="Removal Proof Player", summary="Removal proof.")
        session = str(uuid4())
        _seed_removal_session(dbname, session)
        memnon = MEMNON(interface=None, db_url=database_url(dbname))
        try:
            settings = load_settings()
            settings.apex.turn_pipeline = pipeline
            manager = ContextMemoryManager(settings, memnon=memnon)
            chunks = [
                {"chunk_id": 41, "text": "Old passage. " * 35000},
                {"chunk_id": 42, "text": "Retained passage.", "is_target": True},
            ]
            with memnon.db_manager.engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO narrative_chunks (id, raw_text, storyteller_text) "
                        "VALUES (:chunk_id, :text, :text)"
                    ),
                    chunks,
                )
            manager._stage_retrieval_coverage(
                incremental_retriever=manager.incremental,
                entity_match=EntityMatch(characters=[], places=[], factions=[]),
                user_input="Continue.",
                raw_result_count=2,
                kept_chunks=chunks,
                kept_tokens=1,
                available_budget=71000,
                turn_id=session,
            )
            utility = window_logon(settings)
            context = TurnContext(turn_id=session, user_input="Continue.", start_time=0)
            context.context_payload = {
                "metadata": {"turn_id": session},
                "user_input": "Continue.",
                "warm_slice": {"chunks": chunks},
                "retrieved_passages": {"results": []},
                "entity_data": {},
            }
            context.token_counts = {"total_available": 71000, "apex_window": 75000}
            cycle = TurnCycleManager(
                SimpleNamespace(
                    settings=settings, logon=utility, memory_manager=manager
                )
            )
            cycle._enforce_context_payload_budget(context)
            expected = {
                r.budget.seat: _cached_removals(r)
                for r in getattr(utility, "_assembly_window_requests")
            }
            assert all(sum(value.values()) > 0 for value in expected.values())
            with manifest_scope(lambda: connect(dbname)):
                response = utility.generate_narrative(
                    context.context_payload, effective_context_window=75000
                )
            assert response.narrative
            with closing(connect(dbname)) as conn:
                inspection = inspect_turn(conn, session=session)
            observation = observe_turn(inspection, slot=4)
            seats = (
                {"skald_writer", "gaia"}
                if pipeline == "two_pass"
                else {"skald_single_pass"}
            )
            assert {row["seat"] for row in inspection["manifests"]} == seats
            for row in inspection["manifests"]:
                assembly_seat = (
                    "skald_writer"
                    if row["seat"] == "skald_single_pass"
                    else row["seat"]
                )
                window = row["window_record"]
                assert window["removed_block_tokens"] == expected[assembly_seat]
                assert sum(window["block_tokens"].values()) == window["input_tokens"]
                assert window["input_tokens"] <= window["effective_ceiling"]
                assert "trimming" not in window and "dropped_chunk_ids" not in window
            for attempt in observation["attempts"]:
                seat = (
                    "skald_writer"
                    if attempt["seat"] == "skald_single_pass"
                    else attempt["seat"]
                )
                assert attempt["window"]["removed_block_tokens"] == expected[seat]
            public = json.loads(
                run_cli(
                    monkeypatch,
                    "inspect-turn",
                    "--slot",
                    "4",
                    "--session",
                    session,
                    "--json",
                )
            )
            assert public["observation"]["attempts"] == observation["attempts"]
            summary = run_cli(
                monkeypatch,
                "inspect-turn",
                "--slot",
                "4",
                "--session",
                session,
                "--summary",
            )
            assert "removed " in summary and "removed unknown" not in summary
            with memnon.db_manager.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT kept_chunk_ids FROM retrieval_coverage_log "
                        "WHERE turn_id=:turn"
                    ),
                    {"turn": session},
                ).all()
            assert [row.kept_chunk_ids for row in rows] == [[42]]
        finally:
            memnon.close()


def test_distinct_seat_removals_reach_attempt_records_and_manifests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actual bound guards route distinct tokenizer snapshots through both attempts."""
    requests = _distinct_removal_requests()
    expected = {r.budget.seat: _cached_removals(r) for r in requests}
    assert expected["skald_writer"] != expected["gaia"]
    with disposable_slot_database("qa640_756s1_distinct") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        for pipeline in ("two_pass", "single_pass"):
            session = str(uuid4())
            _seed_removal_session(dbname, session)
            settings = load_settings()
            settings.apex.turn_pipeline = pipeline
            utility = window_logon(settings)
            entries = {
                r.budget.seat: {
                    "tokens_before": r.counter.overhead + sum(r.sizes),
                    "input_tokens": r.tokens,
                    "tokens_recovered": sum(expected[r.budget.seat].values()),
                    "removed_block_tokens": expected[r.budget.seat],
                }
                for r in requests
                if pipeline == "two_pass" or r.budget.seat == "skald_writer"
            }
            payload: dict[str, Any] = {
                "metadata": {"turn_id": session},
                "user_input": "Continue.",
                "warm_slice": {"chunks": []},
                "retrieved_passages": {"results": []},
                "entity_data": {},
                "window_trimming": {
                    "removed_block_tokens": expected["skald_writer"],
                    "seats": entries,
                },
            }
            utility._ensure_provider(payload)
            utility._window_payload = payload
            provider: Any
            for seat in (
                ("skald_writer", "gaia")
                if pipeline == "two_pass"
                else ("skald_single_pass",)
            ):
                prompt = utility._format_context_prompt(
                    payload,
                    seat=(
                        "gaia"
                        if seat == "gaia"
                        else "single_pass" if seat == "skald_single_pass" else "writer"
                    ),
                )
                blocks = list(utility._last_rendered_blocks)
                if seat == "gaia":
                    utility._gaia_window_blocks = blocks
                    provider = utility._clone_provider_for_two_pass(
                        system_prompt=utility._gaia_system_prompt(
                            wire_type="local", anthropic_transport=None
                        ),
                        output_validator=None,
                        usage_seat="gaia",
                        anthropic_transport=None,
                    )
                else:
                    utility._writer_window_blocks = blocks
                    provider = utility.provider
                utility._attach_prompt_window_guard(
                    provider, prompt, seat=seat, window=75000
                )
                with manifest_scope(lambda: connect(dbname)):
                    provider.prompt_window_guard(prompt, 1)
                    provider.prompt_window_guard(
                        prompt + "\nRetry with valid structure.", 2
                    )
            records = read_prompt_windows(
                session, datetime.now(timezone.utc).date().isoformat()
            )
            assert len(records) == (4 if pipeline == "two_pass" else 2)
            with closing(connect(dbname)) as conn:
                manifests = inspect_turn(conn, session=session)["manifests"]
            assert len(manifests) == len(records)
            for record in records:
                seat = (
                    "skald_writer"
                    if record.seat == "skald_single_pass"
                    else record.seat
                )
                assert record.removed_block_tokens == expected[seat]
                assert sum(record.block_tokens.values()) == record.input_tokens
                assert record.input_tokens <= record.effective_ceiling
                manifest = next(
                    row
                    for row in manifests
                    if (row["seat"], row["attempt"]) == (record.seat, record.attempt)
                )
                assert (
                    manifest["window_record"]["removed_block_tokens"] == expected[seat]
                )
                if record.attempt == 2:
                    assert record.block_tokens["structured output retry"] > 0
            # New accounting must not silently borrow the writer's seat.
            payload["window_trimming"]["seats"] = {}
            with pytest.raises(KeyError):
                provider.prompt_window_guard(prompt, 3)
            # Old payloads keep unknown accounting through the same real guard.
            payload.pop("window_trimming")
            provider.prompt_window_guard(prompt, 4)
            assert (
                read_prompt_windows(
                    session, datetime.now(timezone.utc).date().isoformat()
                )[-1].removed_block_tokens
                == {}
            )


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

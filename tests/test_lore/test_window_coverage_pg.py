"""PostgreSQL proof that post-render coverage excludes trimmed Pass-2 chunks."""

import pytest
from sqlalchemy import text

from nexus.agents.memnon.memnon import MEMNON
from nexus.config import load_settings_as_dict
from nexus.database import database_url
from nexus.memory import ContextMemoryManager
from nexus.memory.entity_detector import EntityMatch
from tests.pg_fixtures import disposable_slot_database, seed_protagonist
from tests.test_lore.window_helpers import window_logon

pytestmark = pytest.mark.requires_postgres


def test_window_coverage_is_written_only_from_post_render_kept_chunks():
    with disposable_slot_database("qa640_window_coverage") as dbname:
        character_id, _ = seed_protagonist(
            dbname, name="Window Proof Player", summary="Window coverage fixture."
        )
        memnon = MEMNON(interface=None, db_url=database_url(dbname))
        try:
            settings = load_settings_as_dict()
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

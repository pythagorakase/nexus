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
        seed_protagonist(
            dbname, name="Window Proof Player", summary="Window coverage fixture."
        )
        memnon = MEMNON(interface=None, db_url=database_url(dbname))
        try:
            settings = load_settings_as_dict()
            manager = ContextMemoryManager(settings, memnon=memnon)
            chunks = [
                {"chunk_id": 42, "text": "Retained passage."},
                {"chunk_id": 43, "text": "Trimmed passage."},
            ]
            manager._stage_retrieval_coverage(
                incremental_retriever=manager.incremental,
                entity_match=EntityMatch(characters=[], places=[], factions=[]),
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
            _, _, _, count = utility.measure_writer_request(payload, 75000)
            manager.record_rendered_coverage(chunks[:1], count)
            manager.record_rendered_coverage(chunks[:1], count)
            with memnon.db_manager.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT kept_chunk_ids, kept_tokens, raw_result_count FROM retrieval_coverage_log WHERE turn_id = 'post-render-coverage'"
                    )
                ).all()
            assert len(rows) == 1
            assert rows[0].kept_chunk_ids == [42]
            assert rows[0].kept_tokens == count(chunks[0]["text"]) - count("")
            assert rows[0].raw_result_count == 2
        finally:
            memnon.close()

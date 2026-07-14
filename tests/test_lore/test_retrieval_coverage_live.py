"""Rolled-back save_02 proof for retrieval coverage instrumentation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from sqlalchemy import create_engine, text

from nexus.api.slot_utils import get_slot_db_url
from nexus.memory import ContextMemoryManager
from scripts.report_retrieval_coverage import format_retrieval_coverage_report

pytestmark = pytest.mark.requires_postgres


class LiveReferenceMemnon:
    """Return one controlled kept chunk while exposing the live DB connection."""

    def __init__(self, connection: Any, chunk_id: int) -> None:
        self.db_manager = SimpleNamespace(engine=connection)
        self.chunk_id = chunk_id

    def query_memory(
        self, query: str, k: int = 5, use_hybrid: bool = True
    ) -> Dict[str, object]:
        return {
            "results": [
                {
                    "chunk_id": self.chunk_id,
                    "text": "Controlled kept chunk for the rolled-back live audit.",
                }
            ]
        }


def test_handle_user_input_writes_exact_coverage_and_empty_detection() -> None:
    engine = create_engine(get_slot_db_url(slot=2))
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "075_retrieval_coverage_log.sql"
    )

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(migration_path.read_text())
            covered = connection.execute(
                text(
                    """
                    SELECT c.id, c.name, ccr.chunk_id
                    FROM characters c
                    JOIN chunk_character_references ccr
                      ON ccr.character_id = c.id
                    WHERE lower(c.name) = 'alex'
                    ORDER BY ccr.chunk_id DESC
                    LIMIT 1
                    """
                )
            ).one()
            gap = connection.execute(
                text(
                    """
                    SELECT c.id, c.name
                    FROM characters c
                    WHERE lower(c.name) = 'wren'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM chunk_character_references ccr
                          WHERE ccr.character_id = c.id
                            AND ccr.chunk_id = :chunk_id
                      )
                    """
                ),
                {"chunk_id": covered.chunk_id},
            ).one()

            manager = ContextMemoryManager(
                {"memory": {"skip_simple_choices": False}},
                memnon=LiveReferenceMemnon(connection, int(covered.chunk_id)),
            )
            manager.handle_storyteller_response(
                narrative="The prior scene closes.",
                warm_slice=[{"chunk_id": 1, "text": "Baseline."}],
                token_usage={"total_available": 1000, "warm_slice": 10},
            )

            first_update = manager.handle_user_input(
                f"Ask {covered.name} and {gap.name}.",
                turn_id="coverage-live-hit-gap",
            )
            assert [chunk["chunk_id"] for chunk in first_update.retrieved_chunks] == [
                covered.chunk_id
            ]

            manager.handle_user_input(
                "Proceed without named references.",
                turn_id="coverage-live-empty",
            )

            rows = (
                connection.execute(
                    text(
                        """
                    SELECT turn_id, user_input, detected_entities,
                           raw_result_count, kept_chunk_ids, kept_tokens,
                           available_budget, coverage, gap_entities
                    FROM retrieval_coverage_log
                    WHERE turn_id IN (
                        'coverage-live-hit-gap',
                        'coverage-live-empty'
                    )
                    ORDER BY id
                    """
                    )
                )
                .mappings()
                .all()
            )
            assert len(rows) == 2

            hit_gap_row = rows[0]
            expected_detected = sorted(
                [
                    {
                        "kind": "character",
                        "id": int(covered.id),
                        "name": str(covered.name),
                    },
                    {
                        "kind": "character",
                        "id": int(gap.id),
                        "name": str(gap.name),
                    },
                ],
                key=lambda entity: (entity["kind"], entity["id"]),
            )
            assert hit_gap_row["detected_entities"] == expected_detected
            assert hit_gap_row["kept_chunk_ids"] == [covered.chunk_id]
            assert hit_gap_row["coverage"] == [
                {
                    **entity,
                    "covered": entity["id"] == covered.id,
                    "covering_chunk_ids": (
                        [covered.chunk_id] if entity["id"] == covered.id else []
                    ),
                }
                for entity in expected_detected
            ]
            assert hit_gap_row["gap_entities"] == [
                entity for entity in expected_detected if entity["id"] == gap.id
            ]

            empty_row = rows[1]
            assert empty_row["detected_entities"] == []
            assert empty_row["coverage"] == []
            assert empty_row["gap_entities"] == []

            print()
            print(format_retrieval_coverage_report(2, rows))
        finally:
            transaction.rollback()
    engine.dispose()

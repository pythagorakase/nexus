"""Rolled-back PostgreSQL proof for retrieval coverage instrumentation.

The proof runs on a disposable template clone at the migration head (so
``retrieval_coverage_log`` exists), routed under ``ROUTED_SLOT`` and seeded
with a canonical player (the need-clock anchor for the probe characters), the
warm slice's chunk, and the head chunk for the covered reference. Since #903
``handle_user_input`` only stages a turn's coverage; the row is written by
``record_rendered_coverage`` once the rendered payload is known, so the test
records each turn the way the production turn cycle does and asserts the hit,
gap, and empty-detection rows. Everything the test writes rolls back.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from sqlalchemy import create_engine, text

from nexus.memory import ContextMemoryManager
from nexus.memory.context_state import MemoryIdentity
from scripts.report_retrieval_coverage import format_retrieval_coverage_report
from tests.pg_fixtures import (
    disposable_slot_database,
    route_slot_to_disposable,
    seed_committed_chunk,
    seed_protagonist,
    sqlalchemy_url,
)
from tests.settings_helpers import settings_with

pytestmark = pytest.mark.requires_postgres

# The slot label the clone is routed under; the coverage report names it.
ROUTED_SLOT = 5
WARM_SLICE = [{"chunk_id": 1, "text": "Baseline."}]


@pytest.fixture(scope="module")
def coverage_db() -> Iterator[str]:
    """A routed clone with a canonical player and two committed chunks.

    The first chunk is the warm slice's; the covered probe's reference lands
    on the second (the head), so the retrieved chunk is not already in the
    warm slice. Each test's own writes roll back in its transaction.
    """

    with disposable_slot_database("qa885_retrieval_coverage") as dbname:
        with pytest.MonkeyPatch.context() as mp:
            route_slot_to_disposable(mp.setattr, slot=ROUTED_SLOT, dbname=dbname)
            seed_protagonist(dbname, name="Coverage Player")
            warm_chunk_id = seed_committed_chunk(dbname, raw_text="Baseline.", scene=1)
            assert warm_chunk_id == WARM_SLICE[0]["chunk_id"]
            seed_committed_chunk(
                dbname, raw_text="Fixture chunk the covered probe is in.", scene=2
            )
            yield dbname


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


def _record_rendered_turn(
    manager: ContextMemoryManager, retrieved: List[Dict[str, Any]]
) -> int:
    """Record coverage as the turn cycle does once the payload is rendered.

    The rendered chunks are the warm slice plus the turn's retrieved
    passages; each identity carries the tokens it rendered at. Returns the
    tokens rendered for the retrieved passages.
    """

    rendered = WARM_SLICE + retrieved
    tokens: Dict[MemoryIdentity, int] = {}
    for chunk in rendered:
        identity = manager._memory_identity(chunk)
        assert identity is not None, f"rendered chunk {chunk!r} has no identity"
        tokens[identity] = manager._estimate_tokens(chunk["text"])
    manager.record_rendered_coverage(rendered, tokens)
    return sum(
        tokens[identity]
        for chunk in retrieved
        if (identity := manager._memory_identity(chunk)) is not None
    )


def _coverage_row_count(connection: Any, turn_id: str) -> int:
    return int(
        connection.execute(
            text("SELECT count(*) FROM retrieval_coverage_log WHERE turn_id = :turn"),
            {"turn": turn_id},
        ).scalar_one()
    )


def test_handle_user_input_writes_exact_coverage_and_empty_detection(
    coverage_db: str,
) -> None:
    engine = create_engine(sqlalchemy_url(coverage_db))

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            covered = connection.execute(
                text(
                    """
                    WITH entity_row AS (
                        INSERT INTO entities (kind, is_active)
                        VALUES ('character', true)
                        RETURNING id
                    ), character_row AS (
                        INSERT INTO characters (name, entity_id)
                        SELECT 'Coverage Hit Probe', id FROM entity_row
                        RETURNING id, name
                    ), reference_row AS (
                        INSERT INTO chunk_character_references (
                            chunk_id, character_id, reference
                        )
                        SELECT max(nc.id), cr.id, 'present'
                        FROM narrative_chunks nc
                        CROSS JOIN character_row cr
                        GROUP BY cr.id
                        RETURNING chunk_id
                    )
                    SELECT cr.id, cr.name, rr.chunk_id
                    FROM character_row cr
                    CROSS JOIN reference_row rr
                    """
                )
            ).one()
            gap = connection.execute(
                text(
                    """
                    WITH entity_row AS (
                        INSERT INTO entities (kind, is_active)
                        VALUES ('character', true)
                        RETURNING id
                    )
                    INSERT INTO characters (name, entity_id)
                    SELECT 'Coverage Gap Probe', id FROM entity_row
                    RETURNING id, name
                    """
                )
            ).one()

            manager = ContextMemoryManager(
                settings_with(
                    {
                        "lore.token_budget.apex_context_window": 75_000,
                        "memory.skip_simple_choices": False,
                    }
                ),
                memnon=LiveReferenceMemnon(connection, int(covered.chunk_id)),
                provider_wire_type="openai",
                provider_name="openai",
            )
            manager.handle_storyteller_response(
                narrative="The prior scene closes.",
                warm_slice=WARM_SLICE,
                token_usage={"total_available": 1000, "warm_slice": 10},
            )

            first_update = manager.handle_user_input(
                f"Ask {covered.name} and {gap.name}.",
                turn_id="coverage-live-hit-gap",
            )
            assert [chunk["chunk_id"] for chunk in first_update.retrieved_chunks] == [
                covered.chunk_id
            ]
            # Retrieval only stages coverage; the rendered turn writes it.
            assert _coverage_row_count(connection, "coverage-live-hit-gap") == 0
            hit_gap_tokens = _record_rendered_turn(
                manager, first_update.retrieved_chunks
            )

            empty_update = manager.handle_user_input(
                "Proceed without named references.",
                turn_id="coverage-live-empty",
            )
            assert _coverage_row_count(connection, "coverage-live-empty") == 0
            _record_rendered_turn(manager, empty_update.retrieved_chunks)

            rows = [
                dict(row)
                for row in connection.execute(
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
            ]
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
            assert hit_gap_row["kept_tokens"] == hit_gap_tokens > 0
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
            print(format_retrieval_coverage_report(ROUTED_SLOT, rows))
        finally:
            transaction.rollback()
    engine.dispose()

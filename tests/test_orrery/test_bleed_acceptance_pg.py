"""Acceptance bookkeeping on disposable PostgreSQL template clones."""

from collections.abc import Iterator

import pytest

from nexus.agents.orrery.bleed import record_bleed_offers
from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def bleed_acceptance_db() -> Iterator[tuple[str, int, int]]:
    """Create real chunks and resolutions without touching a native save."""
    with disposable_slot_database("qa640_bleed_acceptance") as dbname:
        _, actor = seed_protagonist(dbname)
        with connect(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
                    "VALUES ('Rain falls.', 'Rain falls.') RETURNING id"
                )
                parent = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO orrery_resolutions (
                        tick_chunk_id, template_id, binding_hash, actor_entity_id,
                        priority, magnitude, state_delta, brief, promotion_status
                    ) VALUES (%s, 'qa640_bleed', 'qa640_bleed', %s, 50, 0.5,
                              '{}'::jsonb, 'Rain falls.', 'promoted')
                    RETURNING id
                    """,
                    (parent, actor),
                )
                resolution = cur.fetchone()[0]
        yield dbname, parent, resolution


def test_bleed_offers_are_unique_and_owned_by_accepting_transaction(
    bleed_acceptance_db: tuple[str, int, int],
) -> None:
    """The counter helper neither double-counts ids nor commits its caller."""
    dbname, parent, resolution = bleed_acceptance_db
    conn = connect(dbname)
    try:
        record_bleed_offers(
            conn, resolution_ids=[resolution, resolution], anchor_chunk_id=parent
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT offer_count, last_offered_chunk_id FROM orrery_resolutions "
                "WHERE id = %s",
                (resolution,),
            )
            assert cur.fetchone() == (1, parent)
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT offer_count, last_offered_chunk_id FROM orrery_resolutions "
                "WHERE id = %s",
                (resolution,),
            )
            assert cur.fetchone() == (0, None)
    finally:
        conn.close()

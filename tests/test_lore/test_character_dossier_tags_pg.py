"""Real PostgreSQL proofs for attributed dossier tags and canonical rosters."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.lore.utils.entity_queries import (
    fetch_all_characters_with_references,
    fetch_all_factions_with_references,
)
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_protagonist,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def dossier_database() -> Iterator[tuple[str, int, int]]:
    """Seed subtype/canonical ID mismatch and both clocks in an owned database."""
    with disposable_slot_database("qa640_910_dossier") as dbname:
        # Offset the canonical sequence before inserting the player subtype.
        with connect(dbname) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO entities (kind, is_active) VALUES ('faction', true)"
            )
        character_id, entity_id = seed_protagonist(dbname)
        assert character_id != entity_id
        with connect(dbname) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO narrative_chunks (id, raw_text) VALUES (1, 'A quiet room.')"
            )
            cur.execute(
                "INSERT INTO chunk_metadata (chunk_id, time_delta) VALUES (1, interval '1 hour')"
            )
            cur.execute("SELECT set_config('nexus.write_producer', 'manual', true)")
            cur.execute(
                "INSERT INTO chunk_character_references (chunk_id, character_id, reference) VALUES (1, %s, 'present')",
                (character_id,),
            )
            cur.execute("INSERT INTO characters (name) VALUES ('Untagged Observer')")
            cur.execute(
                "INSERT INTO factions (id, name) VALUES (1, 'Dossier Guild') RETURNING id, entity_id"
            )
            faction_id, faction_entity_id = cur.fetchone()
            cur.execute(
                "INSERT INTO chunk_faction_references (chunk_id, faction_id) VALUES (1, %s)",
                (faction_id,),
            )
            for tag, category, expiry, cleared, deprecated in (
                ("dossier_zeta", "capacity", None, False, False),
                ("dossier_alpha", "capacity", None, False, False),
                ("dossier_live", "state", "interval '1 second'", False, False),
                ("dossier_expired", "state", "interval '-1 second'", False, False),
                ("dossier_boundary", "state", "interval '0 seconds'", False, False),
                ("dossier_cleared", "state", None, True, False),
                ("dossier_deprecated", "state", None, False, True),
            ):
                cur.execute(
                    "INSERT INTO tags (tag, category, deprecated) VALUES (%s, %s, %s) RETURNING id",
                    (tag, category, deprecated),
                )
                tag_id = cur.fetchone()[0]
                # applied_at is a wall-clock value (2099), independent of the
                # frontier world clock (2100); expiry must use world time.
                expiry_sql = (
                    f"(SELECT max(world_time) FROM chunk_metadata) + {expiry}"
                    if expiry
                    else "NULL"
                )
                cur.execute(
                    f"""INSERT INTO entity_tags
                    (entity_id, tag_id, source_kind, applied_at, applied_at_world_time, expires_at_world_time, cleared_at)
                    VALUES (%s, %s, 'authored', '2099-01-01', '2100-01-01', {expiry_sql}, CASE WHEN %s THEN now() ELSE NULL END)""",
                    (entity_id, tag_id, cleared),
                )
            cur.execute(
                "INSERT INTO tags (tag, category, synonym_for) SELECT 'dossier_synonym', 'capacity', id FROM tags WHERE tag = 'dossier_alpha' RETURNING id"
            )
            synonym_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO entity_tags (entity_id, tag_id, source_kind) VALUES (%s, %s, 'authored')",
                (entity_id, synonym_id),
            )
            cur.execute(
                "INSERT INTO tags (tag, category) VALUES ('dossier_agenda', 'agenda') RETURNING id"
            )
            tag_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO entity_tags (entity_id, tag_id, source_kind) VALUES (%s, %s, 'authored')",
                (faction_entity_id, tag_id),
            )
        yield dbname, character_id, faction_id


def test_dossier_character_tags_use_current_view_and_world_clock(
    dossier_database,
) -> None:
    """The real view excludes clear/expired/deprecated/synonym rows by holder."""
    dbname, character_id, faction_id = dossier_database
    engine = create_engine(sqlalchemy_url(dbname))
    try:
        with Session(engine) as session:
            characters = fetch_all_characters_with_references(
                session, [1], max_featured_characters=2
            )
            baseline = {row["id"]: row for row in characters["baseline"]}
            featured = {row["id"]: row for row in characters["featured"]}
            expected = (
                "capacity:dossier_alpha, capacity:dossier_zeta, state:dossier_live"
            )
            assert baseline[character_id]["orrery_tag_summary"] == expected
            assert featured[character_id]["orrery_tag_summary"] == expected
            assert featured[character_id]["reference_type"] == "user_character"
            assert (
                next(
                    row
                    for row in baseline.values()
                    if row["name"] == "Untagged Observer"
                )["orrery_tag_summary"]
                == ""
            )
            factions = fetch_all_factions_with_references(session, [1])
            for tier in ("baseline", "featured"):
                guild = next(row for row in factions[tier] if row["id"] == faction_id)
                assert guild["orrery_tag_summary"] == "agenda:dossier_agenda"
            # Expire the live tag exactly at the frontier, without wall time.
            session.execute(
                text(
                    "UPDATE entity_tags SET expires_at_world_time = (SELECT max(world_time) FROM chunk_metadata) WHERE tag_id = (SELECT id FROM tags WHERE tag = 'dossier_live')"
                )
            )
            result = fetch_all_characters_with_references(
                session, [1], max_featured_characters=2
            )
            assert (
                next(row for row in result["baseline"] if row["id"] == character_id)[
                    "orrery_tag_summary"
                ]
                == "capacity:dossier_alpha, capacity:dossier_zeta"
            )
    finally:
        engine.dispose()

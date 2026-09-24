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
                    VALUES (%s, %s, 'authored', '2099-01-01', (SELECT max(world_time) FROM chunk_metadata), {expiry_sql}, CASE WHEN %s THEN now() ELSE NULL END)""",
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


@pytest.mark.parametrize("start_seconds", [None, -1, 0, 1])
def test_dossier_tag_start_uses_world_clock(dossier_database, start_seconds) -> None:
    """NULL/past/boundary starts render; future starts do not, for both kinds."""
    dbname, character_id, faction_id = dossier_database
    engine = create_engine(sqlalchemy_url(dbname))
    try:
        with Session(engine) as session:
            session.execute(
                text(
                    """UPDATE entity_tags
                    SET applied_at = '2300-01-01',
                        applied_at_world_time = (
                            SELECT max(world_time) FROM chunk_metadata
                        ) + :seconds * interval '1 second'
                    WHERE tag_id IN (
                        SELECT id FROM tags
                        WHERE tag IN ('dossier_alpha', 'dossier_agenda')
                    )"""
                ),
                {"seconds": start_seconds},
            )
            characters = fetch_all_characters_with_references(
                session, [1], max_featured_characters=2
            )
            factions = fetch_all_factions_with_references(session, [1])
            visible = start_seconds is None or start_seconds <= 0
            for records, holder_id, tag in (
                (characters, character_id, "capacity:dossier_alpha"),
                (factions, faction_id, "agenda:dossier_agenda"),
            ):
                for tier in ("baseline", "featured"):
                    row = next(row for row in records[tier] if row["id"] == holder_id)
                    assert (tag in row["orrery_tag_summary"]) is visible
    finally:
        engine.dispose()


def test_dossier_database_tags_reach_real_renderer(dossier_database) -> None:
    """A seeded holder traverses the real query and LogonUtility renderer."""
    from tests.test_lore.window_helpers import window_logon

    dbname, character_id, _ = dossier_database
    engine = create_engine(sqlalchemy_url(dbname))
    try:
        with Session(engine) as session:
            session.execute(
                text(
                    """UPDATE characters SET name = 'Iona',
                    current_location = NULL, current_activity = 'Waiting.',
                    summary = 'A patient observer.', personality = 'Deliberate.',
                    emotional_state = 'Uneasy.' WHERE id = :character_id"""
                ),
                {"character_id": character_id},
            )
            characters = fetch_all_characters_with_references(
                session, [1], max_featured_characters=2
            )
            prompt = window_logon()._format_context_prompt(
                {"user_input": "Continue.", "entity_data": {"characters": characters}},
                seat="writer",
            )
            lines = prompt.splitlines()
            assert (
                "- Iona: Waiting. Tags: capacity:dossier_alpha, "
                "capacity:dossier_zeta, state:dossier_live"
            ) in lines
            assert (
                "- Iona [user_character]: A patient observer. Tags: "
                "capacity:dossier_alpha, capacity:dossier_zeta, state:dossier_live"
            ) in lines
            assert "  Personality: Deliberate.\n  Emotional State: Uneasy." in prompt
    finally:
        engine.dispose()


def test_dossier_place_and_relationship_names(dossier_database, caplog) -> None:
    """Real joins preserve subtype IDs and reject a corrupt endpoint once."""
    from nexus.agents.lore.utils.entity_queries import fetch_character_relationships
    from tests.test_lore.window_helpers import window_logon

    dbname, character_id, _ = dossier_database
    engine = create_engine(sqlalchemy_url(dbname))
    try:
        with Session(engine) as session:
            session.execute(
                text("SELECT set_config('nexus.write_producer', 'manual', true)")
            )
            place_id = session.execute(
                text(
                    "INSERT INTO places (name, type) VALUES ('Dossier Hall', 'fixed_location') RETURNING id"
                )
            ).scalar_one()
            session.execute(
                text(
                    "UPDATE characters SET current_location = :place, "
                    "current_activity = NULL WHERE id = :id"
                ),
                {"place": place_id, "id": character_id},
            )
            other_id = session.execute(
                text("SELECT id FROM characters WHERE name = 'Untagged Observer'")
            ).scalar_one()
            session.execute(
                text(
                    "UPDATE characters SET current_location = NULL, "
                    "current_activity = NULL WHERE id = :id"
                ),
                {"id": other_id},
            )
            session.execute(
                text(
                    """INSERT INTO character_relationships
                (character1_id, character2_id, relationship_type, valence_current,
                 dynamic, recent_events, history)
                VALUES (:first, :second, 'complex', -0.18181818181818181818,
                        'Fixture', 'Fixture', 'Fixture')"""
                ),
                {"first": character_id, "second": other_id},
            )
            characters = fetch_all_characters_with_references(
                session, [1], max_featured_characters=2
            )
            baseline = next(
                c for c in characters["baseline"] if c["id"] == character_id
            )
            featured = next(
                c for c in characters["featured"] if c["id"] == character_id
            )
            assert baseline["current_location_name"] == "Dossier Hall"
            assert featured["current_location"] == place_id
            relationships = fetch_character_relationships(
                session, [character_id, other_id]
            )
            assert len(relationships) == 1
            rel = relationships[0]
            assert rel["character1_name"] == baseline["name"]
            assert rel["character2_name"] == "Untagged Observer"
            for seat in ("writer", "gaia"):
                prompt = window_logon()._format_context_prompt(
                    {
                        "entity_data": {
                            "characters": characters,
                            "relationships": relationships,
                        }
                    },
                    seat=seat,
                )
                lines = prompt.splitlines()
                assert (
                    f"- {baseline['name']}: at Dossier Hall Tags: "
                    "capacity:dossier_alpha, capacity:dossier_zeta, state:dossier_live"
                ) in lines
                assert "- Untagged Observer" in lines
                assert (
                    f"- {baseline['name']} → Untagged Observer: complex (valence -0.18)"
                    in prompt
                )

            # Deliberately corrupt only this disposable transaction. The normal
            # FK prevents absent endpoints; dropping it exercises the defect guard.
            session.execute(
                text(
                    "ALTER TABLE character_relationships DROP CONSTRAINT character_relationships_character2_id_fkey"
                )
            )
            missing_id = 999999
            session.execute(
                text("UPDATE character_relationships SET character2_id = :missing"),
                {"missing": missing_id},
            )
            caplog.clear()
            relationships = fetch_character_relationships(
                session, [character_id, other_id]
            )
            assert relationships == []
            for seat in ("writer", "gaia"):
                prompt = window_logon()._format_context_prompt(
                    {"entity_data": {"relationships": relationships}}, seat=seat
                )
                assert "→" not in prompt
            defects = [
                r for r in caplog.records if "missing canonical endpoint" in r.message
            ]
            assert len(defects) == 1
            assert f"({character_id}, {missing_id})" in defects[0].message
    finally:
        engine.dispose()

"""The accepted-turn factory leaves the state production acceptance leaves.

``tests.pg_fixtures.seed_played_story``, ``seed_accepted_turn`` and
``seed_pending_turn`` stage turns through the gateway's lease and incubator
writers and accept them through ``commit_incubator_to_database_sync``. These
tests read back what that path must have written on a disposable template
clone, and prove the factory refuses a save missing its preconditions.
"""

from __future__ import annotations

import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from nexus.api.config_utils import get_generation_lease_timeout_seconds
from nexus.api.narrative_lease import acquire_generation_lease
from nexus.config import load_settings_as_dict
from nexus.config.story_model import read_story_settings, story_context_settings
from nexus.memory.manager import pass2_baseline_config_fingerprint
from tests.pg_fixtures import (
    FIXTURE_TURN_CHOICES,
    connect,
    disposable_slot_database,
    seed_accepted_turn,
    seed_pending_turn,
    seed_played_story,
    seed_story_clock,
)

pytestmark = pytest.mark.requires_postgres

BASE_TIMESTAMP = datetime(2100, 1, 1, tzinfo=timezone.utc)
TURN_GAP = timedelta(hours=6)
CAST = ("Mara Quill", "Oren Vale")


@pytest.fixture(autouse=True)
def _no_ambient_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep an exported ``NEXUS_SLOT`` from labelling the clone's jobs.

    These tests pass no ``slot`` and route none, so the factory's ambient-slot
    guard would refuse any exported owner slot before seeding.
    """

    monkeypatch.delenv("NEXUS_SLOT", raising=False)


def test_played_story_writes_every_accepted_turn_record() -> None:
    """Chunks, clock, baselines, sessions, presence, letters, IDF and Orrery."""

    with disposable_slot_database("qa640_816_factory") as dbname:
        chunk_ids = seed_played_story(
            dbname,
            turns=3,
            cast=CAST,
            time_delta=TURN_GAP,
            correspondence=True,
        )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT nc.id, nc.choice_text, cm.slug, cm.world_time "
                "FROM narrative_chunks nc "
                "JOIN chunk_metadata cm ON cm.chunk_id = nc.id "
                "WHERE nc.authorial_directives = '[]'::jsonb ORDER BY nc.id"
            )
            chunks = cur.fetchall()
            assert [row[0] for row in chunks] == chunk_ids
            assert {row[1] for row in chunks} == {FIXTURE_TURN_CHOICES[0]}
            assert [row[2] for row in chunks] == [
                "S01E01_001",
                "S01E01_002",
                "S01E01_003",
            ]
            # The chunk_metadata trigger stamps base_timestamp plus the deltas.
            assert [row[3] for row in chunks] == [
                BASE_TIMESTAMP,
                BASE_TIMESTAMP + TURN_GAP,
                BASE_TIMESTAMP + 2 * TURN_GAP,
            ]
            cur.execute(
                "SELECT chunk_id, (payload->>'parent_chunk_id')::int "
                "FROM lore_pass_baselines ORDER BY chunk_id"
            )
            assert cur.fetchall() == [(chunk, chunk) for chunk in chunk_ids]
            cur.execute(
                "SELECT chunk_id, operation, status, terminal_outcome "
                "FROM narrative_generation_sessions ORDER BY chunk_id"
            )
            assert cur.fetchall() == [
                (chunk, "continue", "complete", "accepted") for chunk in chunk_ids
            ]
            cur.execute(
                "SELECT (SELECT count(*) FROM incubator), "
                "(SELECT count(*) FROM narrative_generation_lease)"
            )
            assert cur.fetchone() == (0, 0)
            cur.execute(
                "SELECT document_id FROM memory_idf_documents "
                "WHERE corpus_kind = 'narrative' ORDER BY document_id"
            )
            assert [row[0] for row in cur.fetchall()] == chunk_ids
            cur.execute(
                "SELECT c.name, r.reference, count(*) "
                "FROM chunk_character_references r "
                "JOIN characters c ON c.id = r.character_id "
                "GROUP BY c.name, r.reference ORDER BY c.name"
            )
            assert cur.fetchall() == [
                ("Fixture Player", "present", 3),
                ("Mara Quill", "mentioned", 3),
                ("Oren Vale", "mentioned", 3),
            ]
            cur.execute(
                "SELECT count(*) FROM place_chunk_references "
                "WHERE reference_type = 'setting'"
            )
            assert cur.fetchone()[0] == 3
            cur.execute(
                "SELECT seat, count(*) FROM storyteller_correspondence_letters "
                "GROUP BY seat ORDER BY seat"
            )
            assert cur.fetchall() == [("gaia", 3), ("writer", 3)]
            # Continuations stage the resolver's proposal; acceptance writes it.
            cur.execute("SELECT count(*), min(tick_chunk_id) FROM orrery_resolutions")
            resolutions, first_tick = cur.fetchone()
            assert resolutions > 0 and first_tick == chunk_ids[1]
            cur.execute(
                "SELECT count(*) FROM character_experiences e "
                "JOIN characters c ON c.entity_id = e.character_entity_id "
                "WHERE c.name = ANY(%s)",
                (list(CAST),),
            )
            assert cur.fetchone()[0] > 0


def test_pending_turn_is_the_draft_continue_accepts() -> None:
    """The staged draft continues the frontier under the current fingerprint."""

    with disposable_slot_database("qa640_816_pending") as dbname:
        [frontier] = seed_played_story(dbname, turns=1)
        session_id = seed_pending_turn(
            dbname,
            user_text=FIXTURE_TURN_CHOICES[0],
            storyteller_text="The pending fixture turn.",
            choices=list(FIXTURE_TURN_CHOICES),
        )
        settings = story_context_settings(
            load_settings_as_dict(), read_story_settings(dbname)
        )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT i.session_id::text, i.parent_chunk_id, i.generation_model, "
                "i.choice_object->'presented', i.choice_text, "
                "i.lore_pass_baseline->>'config_fingerprint', "
                "i.lore_pass_baseline->'parent_chunk_id', "
                "s.status, s.terminal_outcome, s.parent_chunk_id "
                "FROM incubator i JOIN narrative_generation_sessions s "
                "ON s.session_id = i.session_id"
            )
            assert cur.fetchone() == (
                session_id,
                frontier,
                "TEST",
                list(FIXTURE_TURN_CHOICES),
                None,
                pass2_baseline_config_fingerprint(settings),
                None,
                "complete",
                None,
                frontier,
            )
            cur.execute("SELECT count(*) FROM narrative_generation_lease")
            assert cur.fetchone()[0] == 0
        with pytest.raises(ValueError, match="at least two choices"):
            seed_pending_turn(
                dbname,
                user_text="Again.",
                storyteller_text="A one-choice draft.",
                choices=[FIXTURE_TURN_CHOICES[0]],
            )
        with pytest.raises(RuntimeError, match="singleton is owned by session"):
            seed_pending_turn(
                dbname, user_text="Again.", storyteller_text="A second draft."
            )
        # The refusals took no lease and opened no session.
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_generation_lease")
            assert cur.fetchone()[0] == 0
            cur.execute(
                "SELECT session_id::text, terminal_outcome "
                "FROM narrative_generation_sessions ORDER BY created_at"
            )
            assert [(row[0] == session_id, row[1]) for row in cur.fetchall()] == [
                (False, "accepted"),
                (True, None),
            ]
            cur.execute("SELECT session_id::text FROM incubator")
            assert cur.fetchall() == [(session_id,)]


def test_turn_factory_records_free_text_and_refuses_a_foreign_lease() -> None:
    """Free text is the player's wording; a live foreign lease is loud."""

    with disposable_slot_database("qa640_816_free_text") as dbname:
        seed_played_story(dbname, turns=1)
        free_text = "I climb the fire escape instead."
        chunk_id = seed_accepted_turn(
            dbname,
            user_text=FIXTURE_TURN_CHOICES[0],
            storyteller_text="The fixture turn the player answers in their words.",
            choices=list(FIXTURE_TURN_CHOICES),
            choice_text=free_text,
        )
        with closing(connect(dbname)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT choice_text FROM narrative_chunks WHERE id = %s",
                    (chunk_id,),
                )
                assert cur.fetchone() == (free_text,)
            conn.rollback()
            foreign = str(uuid.uuid4())
            assert (
                acquire_generation_lease(
                    conn,
                    session_id=foreign,
                    operation="continue",
                    stale_timeout_seconds=get_generation_lease_timeout_seconds(),
                )
                is None
            )
        with pytest.raises(RuntimeError, match="seed_pending_turn lease conflict"):
            seed_pending_turn(
                dbname,
                user_text=free_text,
                storyteller_text="A draft the foreign lease blocks.",
            )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT (SELECT count(*) FROM incubator), "
                "(SELECT session_id::text FROM narrative_generation_lease), "
                "(SELECT count(*) FROM narrative_generation_sessions "
                "WHERE terminal_outcome IS NULL)"
            )
            assert cur.fetchone() == (0, foreign, 1)


def test_turn_factory_refuses_a_save_missing_its_preconditions() -> None:
    """No clock, then no player, then an already played save: each is loud."""

    with disposable_slot_database("qa640_816_preconditions") as dbname:
        with pytest.raises(AssertionError, match="needs a world clock"):
            seed_pending_turn(dbname, user_text="Go.", storyteller_text="Nothing.")
        seed_story_clock(dbname, world_time=BASE_TIMESTAMP)
        with pytest.raises(AssertionError, match="needs a canonical player"):
            seed_pending_turn(dbname, user_text="Go.", storyteller_text="Nothing.")
        with pytest.raises(AssertionError, match="needs an unplayed save"):
            seed_played_story(dbname, turns=1)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT (SELECT count(*) FROM incubator), "
                "(SELECT count(*) FROM narrative_generation_sessions)"
            )
            assert cur.fetchone() == (0, 0)

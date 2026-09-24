"""Real commit and prompt assembly proofs for the canonical scene roster."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PlaceRef,
    PresenceDelta,
    SceneReset,
    SkaldTurnWire,
    hydrate_skald_turn,
)
from nexus.agents.lore.logon_utility import LogonUtility, read_presence_baseline
from nexus.agents.orrery.bleed import load_bleed_anchor_entity_ids
from nexus.agents.orrery.knowledge_surfacing import build_knowledge_digest_sync
from nexus.agents.orrery.resolver import _present_actor_ids_at_anchor
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.lore_adapter import response_to_incubator
from nexus.api.presence_reconciliation import (
    read_character_roster_from_connection,
    reconcile_prose_mentions,
)
from nexus.api.slot_utils import VALID_DBNAMES
from nexus.config import load_settings
from nexus.memory.manager import empty_pass2_baseline
from nexus.presence.roster import read_roster, resolve_reference
from tests.test_orrery.test_knowledge_surfacing_live import (
    _insert_claim,
    _grant_awareness,
)
from tests.pg_fixtures import connect, disposable_slot_database, sqlalchemy_url
from tests.test_commit_choice_presence_pg import _insert_staged_turn, _reset_world

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def roster_database() -> Iterator[tuple[str, dict[str, int], int]]:
    """Seed characters and one place in a disposable template clone."""
    with disposable_slot_database("qa640_roster798") as dbname:
        VALID_DBNAMES.add(dbname)
        try:
            with connect(dbname) as conn:
                with conn.cursor() as cur:
                    ids = _reset_world(cur, ["Remote Friend"])
                    cur.execute(
                        "SELECT user_character FROM global_variables WHERE id = true"
                    )
                    ids["Test Protagonist"] = cur.fetchone()[0]
                    cur.execute(
                        "INSERT INTO places (name, type) VALUES ('Hall', 'fixed_location') RETURNING id"
                    )
                    place_id = cur.fetchone()[0]
            yield dbname, ids, place_id
        finally:
            VALID_DBNAMES.discard(dbname)


def commit_wire(dbname: str, parent_id: int, wire: SkaldTurnWire) -> int:
    """Hydrate and stage a wire, then drive the genuine commit transaction."""
    from nexus.agents.logon.skald_wire import PresenceBaseline

    if not parent_id and (wire.presence is None or wire.presence.scene_reset is None):
        with connect(dbname) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM places WHERE name = 'Hall'")
            hall = cur.fetchone()[0]
        presence = wire.presence or PresenceDelta()
        wire.presence = presence.model_copy(
            update={
                "scene_reset": SceneReset(
                    place=PlaceRef(kind="place", id=hall, name="Hall"),
                    present=presence.enter,
                )
            }
        )
    baseline = (
        read_presence_baseline(dbname, parent_id) if parent_id else PresenceBaseline()
    )
    with connect(dbname) as conn:
        reconcile_prose_mentions(
            wire,
            presence_baseline=baseline,
            roster_rows=read_character_roster_from_connection(conn),
        )
    response = hydrate_skald_turn(wire, presence_baseline=baseline)
    session_id = str(uuid4())
    data = response_to_incubator(
        response, parent_id, "Continue.", session_id, empty_pass2_baseline({})
    )
    with connect(dbname) as conn:
        with conn.cursor() as cur:
            _insert_staged_turn(
                cur,
                session_id=session_id,
                parent_chunk_id=parent_id,
                storyteller_text=data["storyteller_text"],
                choice_object=None,
                choice_text=None,
                reference_updates=data["reference_updates"],
                metadata_updates=data["metadata_updates"],
                entity_updates=data["entity_updates"],
                new_entities=data["new_entities"],
            )
    conn = connect(dbname)
    try:
        # Slot is job provenance only; every write uses this disposable connection.
        assert conn.info.dbname.startswith("qa640_")
        return commit_incubator_to_database_sync(conn, session_id, slot=5)
    finally:
        conn.close()


def wire(prose: str, **kwargs) -> SkaldTurnWire:
    """Use the real sparse wire without invoking a provider."""
    return SkaldTurnWire(
        narrative=prose,
        choices=["Stay.", "Go."],
        letter="Continue the scene.",
        **kwargs,
    )


def test_roster_real_commit_promotion_audience_and_writer_seat(roster_database) -> None:
    dbname, ids, place_id = roster_database
    first = commit_wire(
        dbname,
        0,
        wire(
            "Len Aster says, “Wait.” They discuss Remote Friend.",
            presence=PresenceDelta(
                scene_reset=SceneReset(
                    place=PlaceRef(kind="place", id=place_id, name="Hall"),
                    present=[
                        CharacterRef(
                            kind="character",
                            id=ids["Test Protagonist"],
                            name="Test Protagonist",
                        )
                    ],
                ),
                mentions=[
                    CharacterRef(
                        kind="character", id=ids["Remote Friend"], name="Remote Friend"
                    )
                ],
            ),
            new_entities=[
                {
                    "kind": "character",
                    "name": "Len Aster",
                    "summary": "A liaison who knows the hall.",
                }
            ],
        ),
    )
    with connect(dbname) as conn:
        roster = read_roster(conn, first)
        assert {entry.name for entry in roster.present.values()} == {
            "Test Protagonist",
            "Len Aster",
        }
        assert ("character", ids["Remote Friend"]) in roster.referenced
        with conn.cursor() as cur:
            cur.execute(
                "SELECT entity_id FROM characters WHERE id = %s",
                (ids["Remote Friend"],),
            )
            remote_entity_id = cur.fetchone()[0]
        assert remote_entity_id not in roster.present_entity_ids
    engine = create_engine(sqlalchemy_url(dbname))
    try:
        with Session(engine) as session:
            assert remote_entity_id not in load_bleed_anchor_entity_ids(
                session, anchor_chunk_id=first
            )
            assert (
                _present_actor_ids_at_anchor(session, anchor_chunk_id=first)
                == roster.present_entity_ids
            )
            anchor_time = session.execute(
                text("SELECT world_time FROM chunk_metadata WHERE chunk_id = :chunk"),
                {"chunk": first},
            ).scalar_one()
            owner = next(
                entry.entity_id
                for entry in roster.present.values()
                if entry.name == "Len Aster"
            )
            for entity_id in (owner, remote_entity_id):
                claim_id, _ = _insert_claim(
                    session,
                    anchor_chunk_id=first,
                    summary=f"An account held by {entity_id}.",
                )
                _grant_awareness(
                    session,
                    claim_id=claim_id,
                    knower_entity_id=entity_id,
                    source_tier="participant",
                    source_entity_id=None,
                    acquired_at=anchor_time,
                    source_chunk_id=first,
                )
            cfg = load_settings().orrery
            digest = build_knowledge_digest_sync(
                session,
                present_entity_ids=tuple(roster.present_entity_ids),
                anchor_chunk_id=first,
                settings=cfg.knowledge,
                include_player_character=True,
                recall_settings=cfg.recall,
                disclosure_settings=cfg.disclosure,
                turn_id="roster-proof",
            )
            assert digest
            traces = (
                session.execute(
                    text(
                        "SELECT character_entity_id, score_components FROM orrery_recall_trace WHERE turn_id = 'roster-proof'"
                    )
                )
                .mappings()
                .all()
            )
            assert traces and {row["character_entity_id"] for row in traces} == {owner}
            assert all(
                row["score_components"]["disclosure"]["audience_count"] == 1
                for row in traces
            )

    finally:
        engine.dispose()
    baseline = read_presence_baseline(dbname, first)
    utility = LogonUtility(load_settings().model_dump(mode="json"), dbname=dbname)
    context = {
        "metadata": {"target_chunk_id": first},
        "user_input": "Wait by the door.",
    }
    writer = utility._format_context_prompt(
        context, presence_baseline=baseline, seat="writer"
    )
    gaia = utility._format_context_prompt(
        context, presence_baseline=baseline, seat="gaia"
    )
    assert (
        "PRESENT: Test Protagonist (player), Len Aster · SETTING: Hall\n\n=== USER INPUT ===\nWait by the door."
        in writer
    )
    assert "PRESENT:" not in gaia


def test_roster_real_commit_carry_forward_and_reset(roster_database) -> None:
    dbname, ids, place_id = roster_database
    first = commit_wire(
        dbname,
        0,
        wire(
            "The hall is quiet.",
            presence=PresenceDelta(
                scene_reset=SceneReset(
                    place=PlaceRef(kind="place", id=place_id, name="Hall"),
                    present=[
                        CharacterRef(
                            kind="character",
                            id=ids["Test Protagonist"],
                            name="Test Protagonist",
                        ),
                        CharacterRef(
                            kind="character",
                            id=ids["Remote Friend"],
                            name="Remote Friend",
                        ),
                    ],
                )
            ),
        ),
    )
    second = commit_wire(dbname, first, wire("Rain taps the window."))
    third = commit_wire(
        dbname,
        second,
        wire(
            "The room empties.",
            presence=PresenceDelta(
                scene_reset=SceneReset(
                    place=PlaceRef(kind="place", id=place_id, name="Hall"),
                    present=[
                        CharacterRef(
                            kind="character",
                            id=ids["Test Protagonist"],
                            name="Test Protagonist",
                        )
                    ],
                )
            ),
        ),
    )
    with connect(dbname) as conn:
        assert read_roster(conn, first).present == read_roster(conn, second).present
        assert read_roster(conn, third).present_character_ids == {
            ids["Test Protagonist"]
        }

    with pytest.raises(ValueError, match="Cannot exit non-present"):
        commit_wire(
            dbname,
            third,
            wire(
                "The hall is still.",
                presence=PresenceDelta(
                    exit=[
                        CharacterRef(
                            kind="character",
                            id=ids["Remote Friend"],
                            name="Remote Friend",
                        )
                    ]
                ),
            ),
        )
    with connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_chunks")
            assert cur.fetchone()[0] == 3


def test_roster_real_alias_resolution_and_ambiguity(roster_database) -> None:
    dbname, ids, _ = roster_database
    with connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO character_aliases (character_id, alias) VALUES (%s, 'Fox')",
                (ids["Remote Friend"],),
            )
        assert (
            resolve_reference(conn, kind="character", id=None, name="Fox").id
            == ids["Remote Friend"]
        )
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO character_aliases (character_id, alias) VALUES (%s, 'Fox')",
                (ids["Test Protagonist"],),
            )
        with pytest.raises(ValueError, match="Ambiguous character"):
            resolve_reference(conn, kind="character", id=None, name="Fox")


@pytest.mark.parametrize("alias_collision", [False, True])
def test_roster_ambiguous_crossing_rejected_before_hydration(
    roster_database, alias_collision
) -> None:
    dbname, ids, _ = roster_database
    first_id, second_id = ids["Test Protagonist"], ids["Remote Friend"]
    with connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE characters SET name = 'Alex' WHERE id = %s", (first_id,)
            )
            cur.execute(
                "UPDATE characters SET name = %s WHERE id = %s",
                ("Fox" if alias_collision else "ALEX", second_id),
            )
            if alias_collision:
                cur.execute(
                    "INSERT INTO character_aliases (character_id, alias) VALUES (%s, 'Fox')",
                    (first_id,),
                )
    first = commit_wire(
        dbname,
        0,
        wire(
            "The room is quiet.",
            presence=PresenceDelta(
                enter=[
                    CharacterRef(
                        kind="character",
                        id=second_id,
                        name="Fox" if alias_collision else "Alex",
                    )
                ]
            ),
        ),
    )
    with pytest.raises(ValueError, match="Ambiguous character name"):
        commit_wire(
            dbname,
            first,
            wire(
                "Someone crosses the doorway.",
                presence=PresenceDelta(
                    enter=[CharacterRef(kind="character", id=first_id, name="Alex")],
                    exit=[
                        CharacterRef(
                            kind="character", name="Fox" if alias_collision else "Alex"
                        )
                    ],
                ),
            ),
        )
    with connect(dbname) as conn:
        assert second_id in read_roster(conn, first).present_character_ids
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_chunks")
            assert cur.fetchone()[0] == 1


def test_roster_same_turn_departure_survives_commit_reconciliation(
    roster_database,
) -> None:
    dbname, ids, _ = roster_database
    guest = ids["Remote Friend"]
    first = commit_wire(dbname, 0, wire("The room is quiet."))
    second = commit_wire(
        dbname,
        first,
        wire(
            "Remote Friend says goodbye. Remote Friend walks away.",
            presence=PresenceDelta(
                enter=[CharacterRef(kind="character", id=guest, name="Remote Friend")],
                exit=[CharacterRef(kind="character", name="Remote Friend")],
            ),
        ),
    )
    with connect(dbname) as conn:
        roster = read_roster(conn, second)
        assert guest not in roster.present_character_ids
        assert ("character", guest) in roster.referenced


def test_roster_operator_provenance_includes_historical_presence(
    roster_database,
) -> None:
    from nexus.agents.orrery.resolver import compose_actor_bindings
    from scripts.orrery_sample import fetch_actor_sources
    from nexus.agents.orrery.substrate import Slot

    dbname, ids, _ = roster_database
    guest = ids["Remote Friend"]
    first = commit_wire(
        dbname,
        0,
        wire(
            "The room is quiet.",
            presence=PresenceDelta(
                enter=[CharacterRef(kind="character", id=guest, name="Remote Friend")]
            ),
        ),
    )
    second = commit_wire(
        dbname,
        first,
        wire(
            "The room is empty.",
            presence=PresenceDelta(
                exit=[CharacterRef(kind="character", id=guest, name="Remote Friend")]
            ),
        ),
    )
    engine = create_engine(sqlalchemy_url(dbname))
    try:
        with Session(engine) as session:
            entity_id = session.execute(
                text("SELECT entity_id FROM characters WHERE id = :id"), {"id": guest}
            ).scalar_one()
            bindings = compose_actor_bindings(
                session, anchor_chunk_id=second, window_chunks=2
            )
            assert any(binding[Slot.ACTOR] == entity_id for binding in bindings)
            sources = fetch_actor_sources(
                session, anchor_chunk_id=second, window_chunks=2, actor_ids={entity_id}
            )
            assert "chunk-ref" in sources[entity_id]
    finally:
        engine.dispose()


def test_historical_settings_are_ordered_but_frontier_is_rejected(
    roster_database,
) -> None:
    """Historical reads retain every place; continuation names both conflicts."""
    from nexus.presence.roster import render_roster

    dbname, ids, hall = roster_database
    first = commit_wire(
        dbname,
        0,
        wire(
            "The hall is quiet.",
            presence=PresenceDelta(
                scene_reset=SceneReset(
                    place=PlaceRef(kind="place", id=hall, name="Hall"), present=[]
                )
            ),
        ),
    )
    with connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO places (name, type) VALUES ('Garden', 'fixed_location') RETURNING id"
            )
            garden = cur.fetchone()[0]
            cur.execute(
                "DELETE FROM place_chunk_references WHERE chunk_id = %s", (first,)
            )
            for place in (garden, hall):
                cur.execute(
                    "INSERT INTO place_chunk_references (chunk_id, place_id, reference_type) VALUES (%s, %s, 'setting')",
                    (first, place),
                )
        roster = read_roster(conn, first)
        assert [entry.name for entry in roster.setting.values()] == ["Hall", "Garden"]
        assert "SETTING: Hall, Garden" in render_roster(roster)
    with pytest.raises(ValueError, match=rf"Chunk {first}.*Hall.*Garden"):
        read_presence_baseline(dbname, first)

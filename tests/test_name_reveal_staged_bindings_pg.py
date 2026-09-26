"""Both acceptance paths reject conflicting reveal references before writes."""

import asyncio
from uuid import uuid4

import pytest

from nexus.api.commit_handler import commit_incubator_to_database
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.presence.name_reveals import CharacterNameRevealConflict
from tests.pg_fixtures import connect
from tests.test_character_name_reveals_pg import NEW, prepare_witness, reveal_wire
from tests.test_commit_choice_presence_pg import _connect_async, _insert_staged_turn
from tests.test_name_reveal_staged_bindings import SITES, staged_data
from tests.test_presence_roster_pg import roster_database as _roster_database


name_reveal_binding_database = _roster_database
pytestmark = pytest.mark.requires_postgres


def stage_binding(dbname, ids, parent, character_id, site, supplied_id, name):
    """Stage a raw accepted-wire shape without repairing its supplied identity."""
    data = staged_data(site, supplied_id, name)
    revelation = reveal_wire(character_id)
    data["storyteller_text"] = revelation.narrative
    data["new_entities"] = [item.model_dump() for item in revelation.new_entities]
    if site.startswith("relationship"):
        other = 3 - int(site[-1])
        relationship = data["entity_updates"]["relationships"][0]
        relationship[f"character{other}_id"] = ids["Test Protagonist"]
        relationship[f"character{other}_name"] = "Test Protagonist"
    if site == "state":
        data["entity_updates"]["characters"][0][
            "current_activity"
        ] = "Giving testimony."
    session_id = str(uuid4())
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM places WHERE name = 'Hall'")
        data["reference_updates"]["places"] = [
            {
                "place_id": cur.fetchone()[0],
                "place_name": "Hall",
                "reference_type": "setting",
            }
        ]
        _insert_staged_turn(
            cur,
            session_id=session_id,
            parent_chunk_id=parent,
            storyteller_text=data["storyteller_text"],
            choice_object=None,
            choice_text=None,
            reference_updates=data["reference_updates"],
            entity_updates=data["entity_updates"],
            new_entities=data["new_entities"],
        )
    return session_id


def accept(dbname, session_id, commit_async):
    """Exercise the real transaction using only the test's private database."""
    if commit_async:

        async def run():
            conn = await _connect_async(dbname)
            try:
                return await commit_incubator_to_database(conn, session_id, slot=5)
            finally:
                await conn.close()

        return asyncio.run(run())
    conn = connect(dbname)
    try:
        return commit_incubator_to_database_sync(conn, session_id, slot=5)
    finally:
        conn.close()


def snapshot(dbname, session_id):
    """Capture persistent state plus the nontransactional chunk-ID sequence."""
    queries = [
        "SELECT id, name, current_activity FROM characters ORDER BY id",
        "SELECT id FROM narrative_chunks ORDER BY id",
        "SELECT pg_sequence_last_value("
        "pg_get_serial_sequence('narrative_chunks', 'id')::regclass)",
        "SELECT character_id, alias, provenance FROM character_aliases "
        "ORDER BY character_id, alias",
        "SELECT * FROM character_identity_rulings ORDER BY id",
        "SELECT * FROM character_relationships ORDER BY character1_id, character2_id",
    ]
    with connect(dbname) as conn, conn.cursor() as cur:
        result = []
        for query in queries:
            cur.execute(query)
            result.append(cur.fetchall())
        cur.execute("SELECT * FROM incubator WHERE session_id = %s", (session_id,))
        result.append(cur.fetchall())
        return result


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("commit_async", [False, True])
def test_conflicting_reveal_id_is_rejected_before_any_acceptance_write(
    name_reveal_binding_database, site, commit_async
):
    dbname, ids, _ = name_reveal_binding_database
    character_id, _, _, parent = prepare_witness(dbname, ids)
    session_id = stage_binding(
        dbname,
        ids,
        parent,
        character_id,
        site,
        ids["Test Protagonist"],
        NEW,
    )
    before = snapshot(dbname, session_id)
    with pytest.raises(CharacterNameRevealConflict, match="supplied ID conflicts"):
        accept(dbname, session_id, commit_async)
    assert snapshot(dbname, session_id) == before


@pytest.mark.parametrize("commit_async", [False, True])
def test_new_unique_alias_state_update_binds_before_draft_validation(
    name_reveal_binding_database, commit_async
):
    dbname, ids, _ = name_reveal_binding_database
    character_id, _, _, parent = prepare_witness(dbname, ids)
    session_id = stage_binding(
        dbname, ids, parent, character_id, "state", None, "Anika"
    )
    accept(dbname, session_id, commit_async)
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT name, current_activity FROM characters WHERE id = %s",
            (character_id,),
        )
        assert cur.fetchone() == (NEW, "Giving testimony.")

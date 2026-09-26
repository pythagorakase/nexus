"""Real registry reads and commits retain active tags across a name revelation."""

import asyncio

import pytest

from nexus.agents.logon.orrery_tag_validation import (
    build_storyteller_tag_validator,
    name_reveal_update_validation,
)
from nexus.agents.logon.skald_wire import UpdatesBlock
from nexus.presence.identity import read_identity_index
from tests.pg_fixtures import connect
from tests.test_character_name_reveals_pg import NEW, prepare_witness, reveal_wire
from tests.test_presence_roster_pg import commit_wire
from tests.test_presence_roster_pg import roster_database as _roster_database


name_reveal_tag_database = _roster_database
pytestmark = pytest.mark.requires_postgres


@pytest.mark.parametrize("include_id", [False, True])
@pytest.mark.parametrize("commit_async", [False, True])
def test_reveal_registry_validation_and_acceptance_keep_active_tag_unchanged(
    name_reveal_tag_database, include_id, commit_async
):
    dbname, ids, _ = name_reveal_tag_database
    character_id, entity_id, _, parent = prepare_witness(dbname, ids)
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_tags (entity_id, tag_id, source_kind) "
            "SELECT %s, id, 'llm_generated' FROM tags WHERE tag = 'dying' "
            "RETURNING id, applied_at, expires_at_world_time, cleared_at",
            (entity_id,),
        )
        before = cur.fetchone()
        assert before is not None

    response = reveal_wire(character_id)
    response.updates = UpdatesBlock.model_validate(
        {
            "characters": [
                {
                    "id": character_id if include_id else None,
                    "name": NEW,
                    "activity": "Holding the timing sheet.",
                    "tags_add": ["dying"],
                }
            ],
            "places": [],
            "factions": [],
            "relationships": [],
        }
    )
    validator = build_storyteller_tag_validator(
        dbname,
        allow_same_turn_faction_declarations=True,
        anchor_chunk_id_provider=lambda: parent,
    )
    assert validator is not None
    with connect(dbname) as conn:
        index = read_identity_index(conn)
    with name_reveal_update_validation(
        response, index, narrative=response.narrative
    ) as accepted_names:
        accepted = asyncio.run(validator(None, response))
    accepted = accepted_names(accepted)
    update = accepted.updates.characters[0]
    assert (update.id, update.name, update.tags_add) == (character_id, NEW, None)

    commit_wire(dbname, parent, accepted, commit_async=commit_async)
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT name, current_activity FROM characters WHERE id = %s",
            (character_id,),
        )
        assert cur.fetchone() == (NEW, "Holding the timing sheet.")
        cur.execute(
            "SELECT et.id, et.applied_at, et.expires_at_world_time, et.cleared_at "
            "FROM entity_tags et JOIN tags t ON t.id = et.tag_id "
            "WHERE et.entity_id = %s AND t.tag = 'dying'",
            (entity_id,),
        )
        assert cur.fetchall() == [before]

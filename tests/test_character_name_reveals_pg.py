"""Actual sync/async acceptance keeps name revelations on the original row."""

import asyncio
import json

import asyncpg

import pytest

from nexus.agents.logon.apex_schema import NewEntityDeclaration
from nexus.agents.logon.skald_wire import CharacterRef, PresenceDelta
from nexus.presence.roster import read_roster, resolve_reference
from tests.pg_fixtures import asyncpg_kwargs, connect
from tests.test_presence_roster_pg import commit_wire, wire
from tests.test_presence_roster_pg import roster_database as _roster_database


name_reveal_database = _roster_database
pytestmark = pytest.mark.requires_postgres
OLD = "Unnamed former CP-9 crew member"
NEW = "Anika Sayegh"
QUOTE = "“Anika Sayegh. Test instrumentation. Retired, apparently.”"


def prepare_witness(dbname, ids):
    """Create the initial descriptor through an ordinary accepted scene."""
    character_id = ids["Remote Friend"]
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE characters SET name = %s, summary = 'Kept summary', "
            "background = 'Kept testimony', extra_data = %s::jsonb "
            "WHERE id = %s RETURNING entity_id",
            (OLD, json.dumps({"private_fixture": "preserve"}), character_id),
        )
        entity_id = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM characters")
        count = cur.fetchone()[0]
    parent = commit_wire(
        dbname,
        0,
        wire(
            f"{OLD} presents her timing sheet.",
            presence=PresenceDelta(
                enter=[CharacterRef(kind="character", id=character_id, name=OLD)]
            ),
        ),
    )
    return character_id, entity_id, count, parent


def reveal_wire(character_id):
    """Pair finished writer prose with Gaia's explicit same-person ruling."""
    return wire(
        f"The older witness looks up. {QUOTE}",
        new_entities=[
            NewEntityDeclaration(
                kind="character",
                name=NEW,
                summary="New declaration summary is not a rewrite.",
                same_as={
                    "character_id": character_id,
                    "previous_name": OLD,
                    "evidence": QUOTE,
                },
            )
        ],
        presence=PresenceDelta(mentions=[CharacterRef(kind="character", name=NEW)]),
    )


@pytest.mark.parametrize("commit_async", [False, True])
def test_accepted_reveal_preserves_id_history_and_one_presence_row(
    name_reveal_database, commit_async
):
    dbname, ids, _ = name_reveal_database
    character_id, entity_id, count, parent = prepare_witness(dbname, ids)
    child = commit_wire(
        dbname, parent, reveal_wire(character_id), commit_async=commit_async
    )
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM characters")
        assert cur.fetchone()[0] == count
        cur.execute(
            "SELECT name, entity_id, summary, background, extra_data "
            "FROM characters WHERE id = %s",
            (character_id,),
        )
        assert cur.fetchone() == (
            NEW,
            entity_id,
            "Kept summary",
            "Kept testimony",
            {"private_fixture": "preserve"},
        )
        for label in (OLD, NEW):
            assert (
                resolve_reference(conn, kind="character", id=None, name=label).id
                == character_id
            )
        assert character_id in read_roster(conn, parent).present_character_ids
        assert character_id in read_roster(conn, child).present_character_ids
        cur.execute(
            "SELECT alias, provenance FROM character_aliases WHERE character_id = %s",
            (character_id,),
        )
        aliases = cur.fetchall()
        assert (OLD, "authored") in aliases
        assert ("Anika", "generated") in aliases
        cur.execute(
            "SELECT source_chunk_id, entity_id, decision, previous_name, new_name, "
            "evidence, generation_session_id FROM character_identity_rulings "
            "WHERE character_id = %s",
            (character_id,),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][:6] == (child, entity_id, "same_as", OLD, NEW, QUOTE)
        assert rows[0][6]
        cur.execute(
            "SELECT old_value, new_value FROM state_delta_log WHERE "
            "source_chunk_id = %s AND entity_id = %s AND field = 'characters.name'",
            (child, entity_id),
        )
        assert cur.fetchall() == [(OLD, NEW)]
        cur.execute(
            "SELECT count(*) FROM orrery_maturation_jobs WHERE entity_id = %s",
            (entity_id,),
        )
        assert cur.fetchone()[0] == 0
    # A later accepted use of the old descriptor remains the same person.
    later = commit_wire(
        dbname,
        child,
        wire(
            f"{OLD} keeps the sheet.",
            presence=PresenceDelta(mentions=[CharacterRef(kind="character", name=OLD)]),
        ),
        commit_async=commit_async,
    )
    with connect(dbname) as conn:
        assert character_id in read_roster(conn, later).present_character_ids


@pytest.mark.parametrize("commit_async", [False, True])
def test_reveal_and_alias_rollback_with_acceptance_failure(
    name_reveal_database, monkeypatch, commit_async
):
    from nexus.presence import name_reveals

    dbname, ids, _ = name_reveal_database
    character_id, entity_id, count, parent = prepare_witness(dbname, ids)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic post-rename ledger failure")

    async def fail_async(*args, **kwargs):
        fail()

    monkeypatch.setattr(name_reveals, "log_state_delta_sync", fail)
    monkeypatch.setattr(name_reveals, "log_state_delta_async", fail_async)
    with pytest.raises(RuntimeError, match="synthetic post-rename"):
        commit_wire(
            dbname, parent, reveal_wire(character_id), commit_async=commit_async
        )
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT name, entity_id FROM characters WHERE id = %s", (character_id,)
        )
        assert cur.fetchone() == (OLD, entity_id)
        cur.execute("SELECT count(*) FROM characters")
        assert cur.fetchone()[0] == count
        cur.execute("SELECT count(*) FROM character_identity_rulings")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM character_aliases WHERE alias = %s", (OLD,))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT max(id) FROM narrative_chunks")
        assert cur.fetchone()[0] == parent


@pytest.mark.parametrize("custom_json_codec", [False, True])
def test_async_name_delta_has_identical_json_with_either_codec(
    name_reveal_database, custom_json_codec
):
    """The ledger must record the name value, not a JSON document in a string."""
    from nexus.agents.orrery.reconstruction import log_state_delta_async

    dbname, ids, _ = name_reveal_database
    _, entity_id, _, parent = prepare_witness(dbname, ids)

    async def record():
        conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
        try:
            if custom_json_codec:
                await conn.set_type_codec(
                    "jsonb",
                    schema="pg_catalog",
                    encoder=json.dumps,
                    decoder=json.loads,
                    format="text",
                )
            await log_state_delta_async(
                conn,
                source_chunk_id=parent,
                writer="skald_state_update",
                entity_id=entity_id,
                field="characters.name",
                old_value=OLD,
                new_value=NEW,
            )
        finally:
            await conn.close()

    asyncio.run(record())
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT old_value, new_value, jsonb_typeof(new_value) "
            "FROM state_delta_log WHERE field = 'characters.name'",
        )
        assert cur.fetchall() == [(OLD, NEW, "string")]

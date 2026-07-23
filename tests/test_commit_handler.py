"""Unit tests for asynchronous narrative commit helpers."""

from types import SimpleNamespace

import pytest

from nexus.agents.logon.apex_schema import FactionStateUpdate, StateUpdates
from nexus.api.commit_handler import (
    apply_state_updates,
    commit_incubator_to_database,
    insert_chunk_metadata,
)
import nexus.api.commit_handler as commit_handler


class RecordingAsyncConnection:
    """Async connection stand-in that records executed SQL."""

    def __init__(self):
        self.statements = []

    async def execute(self, sql, *args):
        self.statements.append((" ".join(sql.split()), args))


class AsyncTransaction:
    """No-op async transaction context."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class AsyncCommitConnection:
    """Stateful asyncpg-style connection for commit orchestration testing."""

    def __init__(self):
        self.chunk_id = 902
        self.characters = {}
        self.places = {}
        self.factions = {}
        self.character_junctions = []
        self.place_junctions = []
        self.statements = []
        self.parent_metadata = {
            "season": 1,
            "episode": 1,
            "scene": 8,
            "world_layer": "primary",
            "time_delta": None,
        }
        self.incubator = {
            "chunk_id": None,
            "parent_chunk_id": 88,
            "user_text": "Open the gate.",
            "storyteller_text": "Mara Venn opens the gate.",
            "choice_object": None,
            "choice_text": None,
            "orrery_proposal": None,
            "orrery_adjudications": [],
            "new_entities": [
                {
                    "kind": "character",
                    "name": "Mara Venn",
                    "summary": "A gatekeeper with a careful memory.",
                }
            ],
            "metadata_updates": {"chronology": {"episode_transition": "continue"}},
            "entity_updates": {},
            "reference_updates": {
                "characters": [
                    {
                        "character_name": "Mara Venn",
                        "reference_type": "present",
                    }
                ],
                "places": [],
                "factions": [],
            },
            "llm_response_id": "response-2",
            "generation_model": "test-model",
            "status": "provisional",
        }

    def transaction(self):
        return AsyncTransaction()

    async def fetchrow(self, sql, *_args):
        normalized = " ".join(sql.split())
        if "FROM incubator" in normalized:
            return self.incubator
        if "FROM chunk_metadata" in normalized:
            return self.parent_metadata
        if "SELECT entity_id FROM factions" in normalized:
            return {"entity_id": 303}
        raise AssertionError(f"Unexpected fetchrow SQL: {normalized}")

    async def fetch(self, sql, *args):
        normalized = " ".join(sql.split())
        if "SELECT id FROM characters WHERE name" in normalized:
            entity_id = self.characters.get(args[0])
            return [{"id": entity_id}] if entity_id is not None else []
        raise AssertionError(f"Unexpected fetch SQL: {normalized}")

    async def fetchval(self, sql, *args):
        normalized = " ".join(sql.split())
        if "INSERT INTO narrative_chunks" in normalized:
            return self.chunk_id
        if "SELECT id FROM characters WHERE name" in normalized:
            return self.characters.get(args[0])
        if "SELECT id FROM places WHERE name" in normalized:
            return self.places.get(args[0])
        if "SELECT id FROM factions WHERE name" in normalized:
            return self.factions.get(args[0])
        if "SELECT entity_id FROM characters WHERE id" in normalized:
            return 1000 + args[0]
        if "SELECT entity_id FROM places WHERE id" in normalized:
            return 2000 + args[0]
        raise AssertionError(f"Unexpected fetchval SQL: {normalized}")

    async def execute(self, sql, *args):
        normalized = " ".join(sql.split())
        self.statements.append((normalized, args))
        if "INSERT INTO characters" in normalized:
            self.characters[args[0]] = 72
        elif "INSERT INTO chunk_character_references" in normalized:
            self.character_junctions.append(args)
        elif "INSERT INTO place_chunk_references" in normalized:
            self.place_junctions.append(args)
        return "OK"


def _empty_orrery_result():
    return SimpleNamespace(
        resolution_count=0,
        event_count=0,
        tag_mutation_count=0,
        cleared_tag_count=0,
        skipped_existing_count=0,
        adjudication_count=0,
        deferred_count=0,
        voided_count=0,
        replaced_count=0,
        scene_pressure_count=0,
        prompt_exposure_count=0,
        propagation_count=0,
        reveal_count=0,
    )


@pytest.mark.asyncio
async def test_async_faction_state_updates_do_not_write_legacy_activity():
    """Faction state updates should not touch obsolete faction columns."""

    conn = RecordingAsyncConnection()

    await apply_state_updates(
        conn,
        StateUpdates(
            factions=[
                FactionStateUpdate(
                    faction_id=42,
                    recent_actions=["Shifted lookouts to the tram stop."],
                )
            ]
        ),
    )

    assert all("UPDATE factions" not in sql for sql, _args in conn.statements)


@pytest.mark.asyncio
async def test_async_chunk_metadata_insert_carries_generation_model():
    """The async commit helper writes the incubator's provenance value."""

    conn = RecordingAsyncConnection()

    await insert_chunk_metadata(
        conn,
        chunk_id=42,
        season=1,
        episode=2,
        scene=3,
        world_layer="primary",
        time_delta=60,
        generation_model="resolved-async-model",
    )

    sql, args = conn.statements[-1]
    assert "generation_model" in sql
    assert args[-1] == "resolved-async-model"


@pytest.mark.asyncio
async def test_async_commit_links_same_turn_character_declaration(monkeypatch):
    """The real async commit creates stubs before resolving name references."""

    conn = AsyncCommitConnection()

    async def no_op_attribution(*_args):
        return None

    async def empty_orrery_tick(*_args, **_kwargs):
        return _empty_orrery_result()

    monkeypatch.setattr(
        commit_handler, "set_commit_chunk_attribution_async", no_op_attribution
    )
    monkeypatch.setattr(commit_handler, "commit_orrery_tick_async", empty_orrery_tick)
    monkeypatch.setattr(commit_handler, "_orrery_checkpoint_interval", lambda: 0)

    chunk_id = await commit_incubator_to_database(conn, "session-2", slot=5)

    assert chunk_id == conn.chunk_id
    assert conn.character_junctions == [(conn.chunk_id, 72, "present")]


@pytest.mark.asyncio
async def test_async_commit_resolves_all_name_addressed_state_updates(monkeypatch):
    """The real async commit resolves every update identity before DB writes."""

    conn = AsyncCommitConnection()
    conn.characters.update({"Mara Venn": 72, "Odile": 73})
    conn.places["Fixture Station"] = 81
    conn.factions["Project Palimpsest"] = 91
    conn.incubator["new_entities"] = []
    conn.incubator["reference_updates"] = {
        "characters": [],
        "places": [],
        "factions": [],
    }
    conn.incubator["entity_updates"] = {
        "characters": [
            {
                "character_name": "Mara Venn",
                "current_activity": "opening the gate",
            }
        ],
        "locations": [
            {
                "place_name": "Fixture Station",
                "current_conditions": "The gate stands open.",
            }
        ],
        "factions": [
            {
                "faction_name": "Project Palimpsest",
                "orrery_tags": {"applied_tags": ["mobilized"]},
            }
        ],
        "relationships": [
            {
                "character1_name": "Mara Venn",
                "character2_name": "Odile",
                "dynamic": "Newly allied at the gate.",
            }
        ],
    }
    tag_writes = []

    async def no_op(*_args, **_kwargs):
        return None

    async def record_tag_write(*_args, **kwargs):
        tag_writes.append(kwargs)
        return {
            "applied": 1,
            "cleared": 0,
            "unknown": 0,
            "noop": 0,
        }

    async def empty_orrery_tick(*_args, **_kwargs):
        return _empty_orrery_result()

    monkeypatch.setattr(
        commit_handler, "set_commit_chunk_attribution_async", no_op
    )
    monkeypatch.setattr(commit_handler, "log_state_delta_async", no_op)
    monkeypatch.setattr(
        commit_handler, "apply_tag_bestowal_async", record_tag_write
    )
    monkeypatch.setattr(commit_handler, "commit_orrery_tick_async", empty_orrery_tick)
    monkeypatch.setattr(commit_handler, "_orrery_checkpoint_interval", lambda: 0)

    await commit_incubator_to_database(conn, "state-session", slot=5)

    sql_and_args = [
        (sql, args)
        for sql, args in conn.statements
        if sql.startswith("UPDATE ")
    ]
    assert any(
        sql.startswith("UPDATE characters") and args[-1] == 72
        for sql, args in sql_and_args
    )
    assert any(
        sql.startswith("UPDATE places") and args[-1] == 81
        for sql, args in sql_and_args
    )
    assert any(
        sql.startswith("UPDATE character_relationships")
        and args[-2:] == (72, 73)
        for sql, args in sql_and_args
    )
    assert tag_writes[0]["entity_id"] == 303


@pytest.mark.asyncio
async def test_async_commit_aborts_on_unresolvable_state_update_name(monkeypatch):
    """An unresolved update name fails before any state mutation is applied."""

    conn = AsyncCommitConnection()
    conn.incubator["new_entities"] = []
    conn.incubator["reference_updates"] = {
        "characters": [],
        "places": [],
        "factions": [],
    }
    conn.incubator["entity_updates"] = {
        "characters": [
            {
                "character_name": "Nobody By This Name",
                "current_activity": "vanishing",
            }
        ]
    }

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        commit_handler, "set_commit_chunk_attribution_async", no_op
    )

    with pytest.raises(
        ValueError,
        match="Unresolved character state update name 'Nobody By This Name'",
    ):
        await commit_incubator_to_database(conn, "missing-state", slot=5)

    assert not any(
        sql.startswith("UPDATE characters") for sql, _args in conn.statements
    )
    assert not any(
        sql.startswith("DELETE FROM incubator") for sql, _args in conn.statements
    )

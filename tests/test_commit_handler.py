"""Unit tests for asynchronous narrative commit helpers."""

import pytest

from nexus.agents.logon.apex_schema import FactionStateUpdate, StateUpdates
from nexus.api.commit_handler import apply_state_updates, insert_chunk_metadata


class RecordingAsyncConnection:
    """Async connection stand-in that records executed SQL."""

    def __init__(self):
        self.statements = []

    async def execute(self, sql, *args):
        self.statements.append((" ".join(sql.split()), args))


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

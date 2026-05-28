"""Unit tests for asynchronous narrative commit helpers."""

import pytest

from nexus.agents.logon.apex_schema import FactionStateUpdate, StateUpdates
from nexus.api.commit_handler import apply_state_updates


class RecordingAsyncConnection:
    """Async connection stand-in that records executed SQL."""

    def __init__(self):
        self.statements = []

    async def execute(self, sql, *args):
        self.statements.append(" ".join(sql.split()))


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

    assert all("UPDATE factions" not in sql for sql in conn.statements)

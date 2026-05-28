"""Unit tests for synchronous narrative commit helpers."""

from nexus.agents.logon.apex_schema import (
    CharacterReference,
    FactionStateUpdate,
    NewFaction,
    ReferenceType,
    StateUpdates,
)
from nexus.api.commit_handler_sync import (
    apply_state_updates_sync,
    create_new_faction_sync,
    resolve_character_references_sync,
)


class MissingLookupCursor:
    """Cursor stand-in whose name lookups find no rows."""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        return None


class MissingLookupConnection:
    """Connection stand-in for sync resolver tests."""

    def cursor(self):
        return MissingLookupCursor()


class RecordingFactionInsertCursor:
    """Cursor stand-in for the synchronous new-faction insert path."""

    def __init__(self):
        self.statements = []
        self.params = []
        self._fetches = [(77,), (77, 7700)]

    def execute(self, sql, params=None):
        self.statements.append(" ".join(sql.split()))
        self.params.append(params)

    def fetchone(self):
        return self._fetches.pop(0)


class RecordingStateUpdateCursor:
    """Cursor stand-in that records state-update SQL."""

    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.statements.append(" ".join(sql.split()))


class RecordingStateUpdateConnection:
    """Connection stand-in for state update tests."""

    def __init__(self):
        self.cursor_instance = RecordingStateUpdateCursor()

    def cursor(self):
        return self.cursor_instance


def test_sync_unresolved_character_reference_is_skipped(caplog):
    """Unresolved group labels should not block chunk commit."""
    refs = resolve_character_references_sync(
        [
            CharacterReference(
                character_name="Rectification officers",
                reference_type=ReferenceType.PRESENT,
            )
        ],
        MissingLookupConnection(),
    )

    assert refs == []
    assert "Skipping unresolved character reference" in caplog.text


def test_sync_create_new_faction_does_not_insert_obsolete_columns():
    """New faction inserts should write only retained faction columns."""

    cur = RecordingFactionInsertCursor()

    faction_id = create_new_faction_sync(
        cur,
        NewFaction(
            name="Project Palimpsest",
            summary="A covert continuity office.",
            extra_data={"leader": "unknown"},
        ),
    )

    insert_sql = next(sql for sql in cur.statements if sql.startswith("INSERT"))

    assert faction_id == 77
    assert "ideology" not in insert_sql
    assert "history" not in insert_sql
    assert "current_activity" not in insert_sql
    assert "hidden_agenda" not in insert_sql
    assert "territory" not in insert_sql
    assert "power_level" not in insert_sql
    assert "resources" not in insert_sql
    assert "id, name, summary, primary_location, extra_data" in insert_sql


def test_sync_faction_state_updates_do_not_write_legacy_activity():
    """Faction state updates should not write obsolete current_activity."""

    conn = RecordingStateUpdateConnection()

    apply_state_updates_sync(
        conn,
        StateUpdates(
            factions=[
                FactionStateUpdate(
                    faction_id=77,
                    recent_actions=["Moved lookouts to the rail station."],
                )
            ]
        ),
    )

    assert all("UPDATE factions" not in sql for sql in conn.cursor_instance.statements)

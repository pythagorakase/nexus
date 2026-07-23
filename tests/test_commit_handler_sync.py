"""Unit tests for synchronous narrative commit helpers."""

from types import SimpleNamespace

from nexus.agents.logon.apex_schema import (
    CharacterReference,
    FactionStateUpdate,
    ReferenceType,
    StateUpdates,
)
from nexus.api.commit_handler_sync import (
    apply_state_updates_sync,
    commit_incubator_to_database_sync,
    resolve_character_references_sync,
)
import nexus.api.commit_handler_sync as commit_handler_sync


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


class CommitCursor:
    """Cursor stand-in for the real synchronous commit entry point."""

    def __init__(self, connection):
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        if "FROM incubator" in normalized:
            self.result = self.connection.incubator
        elif "FROM chunk_metadata" in normalized:
            self.result = self.connection.parent_metadata
        elif "SELECT id FROM characters WHERE name" in normalized:
            entity_id = self.connection.characters.get(params[0])
            self.result = (entity_id,) if entity_id is not None else None
        elif "INSERT INTO narrative_chunks" in normalized:
            self.result = (self.connection.chunk_id,)
        elif "INSERT INTO chunk_character_references" in normalized:
            self.connection.character_junctions.append(params)
            self.result = None
        else:
            self.result = None

    def fetchone(self):
        return self.result


class CommitConnection:
    """Stateful psycopg-style connection for commit orchestration testing."""

    def __init__(self):
        self.chunk_id = 901
        self.characters = {}
        self.character_junctions = []
        self.parent_metadata = {
            "season": 1,
            "episode": 1,
            "scene": 4,
            "world_layer": "primary",
            "time_delta": None,
        }
        self.incubator = {
            "chunk_id": None,
            "parent_chunk_id": 44,
            "user_text": "Watch the door.",
            "storyteller_text": "Iria Vale steps through the door.",
            "choice_object": None,
            "choice_text": None,
            "orrery_proposal": None,
            "orrery_adjudications": [],
            "new_entities": [
                {
                    "kind": "character",
                    "name": "Iria Vale",
                    "summary": "A courier who knows the hidden routes.",
                }
            ],
            "metadata_updates": {"chronology": {"episode_transition": "continue"}},
            "entity_updates": {},
            "reference_updates": {
                "characters": [
                    {
                        "character_name": "Iria Vale",
                        "reference_type": "present",
                    }
                ],
                "places": [],
                "factions": [],
            },
            "llm_response_id": "response-1",
            "generation_model": "test-model",
            "status": "provisional",
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self, **_kwargs):
        return CommitCursor(self)

    def rollback(self):
        return None


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


def test_sync_commit_links_same_turn_character_declaration(monkeypatch):
    """The real sync commit resolves references after declaration stub creation."""

    conn = CommitConnection()

    def create_stub(connection, **_kwargs):
        connection.characters["Iria Vale"] = 71
        return SimpleNamespace(
            declared=1,
            stubs_created=1,
            jobs_enqueued=1,
            jobs_already_present=0,
            signal_absent=0,
            skipped_disabled=0,
        )

    monkeypatch.setattr(
        commit_handler_sync, "enqueue_declared_entity_maturations", create_stub
    )
    monkeypatch.setattr(
        commit_handler_sync,
        "commit_orrery_tick_sync",
        lambda *_args, **_kwargs: _empty_orrery_result(),
    )
    monkeypatch.setattr(
        commit_handler_sync, "set_commit_chunk_attribution_sync", lambda *_args: None
    )
    monkeypatch.setattr(commit_handler_sync, "_orrery_checkpoint_interval", lambda: 0)

    chunk_id = commit_incubator_to_database_sync(conn, "session-1", slot=5)

    assert chunk_id == conn.chunk_id
    assert conn.character_junctions == [(conn.chunk_id, 71, "present")]


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


def test_sync_location_state_updates_map_conditions_to_status_column():
    """LocationStateUpdate.current_conditions persists to places.current_status.

    M9 gate finding: the handler previously read a nonexistent
    ``current_status`` attribute and crashed every commit that carried a
    location state update.
    """

    from nexus.agents.logon.apex_schema import LocationStateUpdate

    conn = RecordingStateUpdateConnection()

    apply_state_updates_sync(
        conn,
        StateUpdates(
            locations=[
                LocationStateUpdate(
                    place_id=4,
                    current_conditions="Flooded to the second stair",
                )
            ]
        ),
    )

    statements = conn.cursor_instance.statements
    assert any("UPDATE places SET current_status" in sql for sql in statements)

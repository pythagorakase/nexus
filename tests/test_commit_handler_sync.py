"""Unit tests for synchronous narrative commit helpers."""

from types import SimpleNamespace

import pytest

from nexus.agents.logon.apex_schema import (
    CharacterReference,
    FactionStateUpdate,
    ReferenceType,
    StateUpdates,
)
from nexus.agents.lore import logon_utility
from nexus.agents.lore.logon_utility import read_presence_baseline
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
        self.connection.statements.append((normalized, params))
        if "FROM incubator" in normalized:
            self.result = self.connection.incubator
        elif "FROM chunk_metadata" in normalized:
            self.result = self.connection.parent_metadata
        elif "SELECT id FROM characters WHERE name" in normalized:
            entity_id = self.connection.characters.get(params[0])
            self.result = (entity_id,) if entity_id is not None else None
        elif "SELECT id FROM places WHERE name" in normalized:
            entity_id = self.connection.places.get(params[0])
            self.result = (entity_id,) if entity_id is not None else None
        elif "SELECT id FROM factions WHERE name" in normalized:
            entity_id = self.connection.factions.get(params[0])
            self.result = (entity_id,) if entity_id is not None else None
        elif "SELECT entity_id FROM characters WHERE id" in normalized:
            self.result = (1000 + params[0],)
        elif "SELECT entity_id FROM places WHERE id" in normalized:
            self.result = (2000 + params[0],)
        elif "SELECT entity_id FROM factions WHERE id" in normalized:
            self.result = (3000 + params[0],)
        elif "INSERT INTO narrative_chunks" in normalized:
            self.result = (self.connection.chunk_id,)
        elif "INSERT INTO place_chunk_references" in normalized:
            self.connection.place_junctions.append(params)
            self.result = None
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
        self.places = {}
        self.factions = {}
        self.character_junctions = []
        self.place_junctions = []
        self.statements = []
        self.rollback_called = False
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
        self.rollback_called = True


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


def _patch_sync_commit_runtime(monkeypatch) -> None:
    """Replace unrelated runtime integrations around the real sync commit."""

    monkeypatch.setattr(
        commit_handler_sync,
        "enqueue_declared_entity_maturations",
        lambda *_args, **_kwargs: SimpleNamespace(
            declared=0,
            stubs_created=0,
            jobs_enqueued=0,
            jobs_already_present=0,
            signal_absent=0,
            skipped_disabled=0,
        ),
    )
    monkeypatch.setattr(
        commit_handler_sync,
        "commit_orrery_tick_sync",
        lambda *_args, **_kwargs: _empty_orrery_result(),
    )
    monkeypatch.setattr(
        commit_handler_sync, "set_commit_chunk_attribution_sync", lambda *_args: None
    )
    monkeypatch.setattr(
        commit_handler_sync, "log_state_delta_sync", lambda *_a, **_k: None
    )
    monkeypatch.setattr(commit_handler_sync, "_orrery_checkpoint_interval", lambda: 0)


def test_sync_commit_resolves_all_name_addressed_state_updates(monkeypatch):
    """The real sync commit resolves every update identity before DB writes."""

    conn = CommitConnection()
    conn.characters.update({"Iria Vale": 71, "Odile": 72})
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
                "character_name": "Iria Vale",
                "current_activity": "watching the door",
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
                "character1_name": "Iria Vale",
                "character2_name": "Odile",
                "dynamic": "Newly allied at the gate.",
            }
        ],
    }
    tag_writes = []
    _patch_sync_commit_runtime(monkeypatch)
    monkeypatch.setattr(
        commit_handler_sync,
        "_apply_state_tags",
        lambda _cur, **kwargs: tag_writes.append(kwargs),
    )

    commit_incubator_to_database_sync(conn, "state-session", slot=5)

    update_statements = [
        (sql, params) for sql, params in conn.statements if sql.startswith("UPDATE ")
    ]
    assert any(
        sql.startswith("UPDATE characters") and params[-1] == 71
        for sql, params in update_statements
    )
    assert any(
        sql.startswith("UPDATE places") and params[-1] == 81
        for sql, params in update_statements
    )
    assert any(
        sql.startswith("UPDATE character_relationships") and params[-2:] == [71, 72]
        for sql, params in update_statements
    )
    assert tag_writes[0]["subtype_id"] == 91


def test_sync_commit_aborts_on_unresolvable_state_update_name(monkeypatch):
    """An unresolved update name rolls back before state application."""

    conn = CommitConnection()
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
    _patch_sync_commit_runtime(monkeypatch)

    with pytest.raises(
        ValueError,
        match="Unresolved character state update name 'Nobody By This Name'",
    ):
        commit_incubator_to_database_sync(conn, "missing-state", slot=5)

    assert conn.rollback_called is True
    assert not any(
        sql.startswith("UPDATE characters") for sql, _params in conn.statements
    )
    assert not any(
        sql.startswith("DELETE FROM incubator") for sql, _params in conn.statements
    )


def test_bootstrap_commit_seeds_setting_for_next_presence_baseline(
    monkeypatch,
) -> None:
    """Chunk one persists the known starting place as its SETTING junction."""

    conn = CommitConnection()
    conn.incubator["parent_chunk_id"] = 0
    conn.incubator["new_entities"] = []
    conn.incubator["entity_updates"] = {}
    conn.incubator["reference_updates"] = {
        "characters": [{"character_id": 71, "reference_type": "present"}],
        "places": [
            {
                "place_id": 81,
                "place_name": "Fixture Station",
                "reference_type": "setting",
            }
        ],
        "factions": [],
    }
    _patch_sync_commit_runtime(monkeypatch)

    chunk_id = commit_incubator_to_database_sync(conn, "bootstrap-session", slot=5)
    assert conn.place_junctions == [(81, chunk_id, "setting", None)]

    class BaselineCursor:
        def __init__(self):
            self.rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            normalized = " ".join(sql.split())
            assert params == (chunk_id,)
            if "FROM chunk_character_references" in normalized:
                self.rows = [(71, "Iria Vale")]
            elif "FROM place_chunk_references" in normalized:
                self.rows = [
                    (place_id, "Fixture Station")
                    for place_id, recorded_chunk_id, reference_type, _evidence in (
                        conn.place_junctions
                    )
                    if recorded_chunk_id == chunk_id and reference_type == "setting"
                ]
            else:
                raise AssertionError(f"Unexpected baseline SQL: {normalized}")

        def fetchall(self):
            return self.rows

    class BaselineConnection:
        def set_session(self, **_kwargs):
            return None

        def cursor(self):
            return BaselineCursor()

        def close(self):
            return None

    monkeypatch.setattr(
        logon_utility.psycopg2,
        "connect",
        lambda **_kwargs: BaselineConnection(),
    )

    baseline = read_presence_baseline("save_05", chunk_id)
    assert baseline.setting is not None
    assert baseline.setting.id == 81
    assert baseline.setting.name == "Fixture Station"


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

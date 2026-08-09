"""Unit tests for synchronous narrative commit helpers."""

import json
import logging
from types import SimpleNamespace

import pytest

from nexus.agents.logon.apex_schema import (
    CharacterReference,
    FactionStateUpdate,
    ReferenceType,
    StateUpdates,
)
from nexus.agents.logon.skald_wire import PresenceBaseline, SkaldTurnWire
from nexus.agents.lore import logon_utility
from nexus.agents.lore.logon_utility import LogonUtility, read_presence_baseline
from nexus.api.commit_handler_sync import (
    apply_state_updates_sync,
    commit_incubator_to_database_sync,
    resolve_character_references_sync,
)
import nexus.api.commit_handler_sync as commit_handler_sync
from nexus.api.lore_adapter import response_to_incubator
from nexus.api.presence_reconciliation import CharacterRosterRows
from nexus.memory.manager import empty_pass2_baseline


TEST_BASELINE = empty_pass2_baseline({})
TEST_BASELINE_PAYLOAD = TEST_BASELINE.model_dump(mode="json")


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
        self.rows = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.connection.statements.append((normalized, params))
        self.rows = []
        self.rowcount = 0
        if normalized.startswith("DELETE FROM incubator"):
            self.rowcount = 1
            self.result = None
        elif "FROM incubator" in normalized:
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
        elif "/* orrery:bleed_uptake_candidates */" in normalized:
            self.rows = [
                offer
                for offer in self.connection.bleed_offers
                if offer["id"] in params[0]
            ]
            self.result = None
        elif "/* orrery:stamp_bleed_uptake */" in normalized:
            chunk_id, resolution_id = params
            offer = next(
                offer
                for offer in self.connection.bleed_offers
                if offer["id"] == resolution_id
            )
            offer["used_chunk_id"] = chunk_id
            offer["use_count"] += 1
            self.result = None
        else:
            self.result = None

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.rows


class CommitConnection:
    """Stateful psycopg-style connection for commit orchestration testing."""

    def __init__(self):
        self.chunk_id = 901
        self.characters = {}
        self.places = {}
        self.factions = {}
        self.character_junctions = []
        self.place_junctions = []
        self.bleed_offers = []
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
            "lore_pass_baseline": TEST_BASELINE_PAYLOAD,
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
    monkeypatch.setattr(
        commit_handler_sync, "_orrery_checkpoint_interval", lambda _settings: 0
    )

    chunk_id = commit_incubator_to_database_sync(conn, "session-1", slot=5)

    assert chunk_id == conn.chunk_id
    assert conn.character_junctions == [(conn.chunk_id, 71, "present")]
    baseline_writes = [
        params
        for sql, params in conn.statements
        if sql.startswith("INSERT INTO lore_pass_baselines")
    ]
    assert baseline_writes[0][:2] == (conn.chunk_id, 1)
    assert json.loads(baseline_writes[0][2])["parent_chunk_id"] == conn.chunk_id
    assert any(
        "FROM incubator" in sql and "FOR UPDATE" in sql
        for sql, _params in conn.statements
    )


@pytest.mark.parametrize("name_present", (True, False))
def test_sync_commit_measures_seeded_bleed_offer_uptake(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    name_present: bool,
) -> None:
    """The genuine commit path stamps only exact-name Bleed uptake."""

    caplog.set_level(logging.INFO, logger="nexus.orrery.bleed")
    conn = CommitConnection()
    conn.incubator["new_entities"] = []
    conn.incubator["reference_updates"] = {
        "characters": [],
        "places": [],
        "factions": [],
    }
    conn.incubator["storyteller_text"] = (
        "Iria Vale slips through the rain-dark station."
        if name_present
        else "The courier slips through the rain-dark station."
    )
    conn.incubator["orrery_proposal"] = {"_bleed_offer_resolution_ids": [501]}
    conn.bleed_offers = [
        {
            "id": 501,
            "actor_name": "Iria Vale",
            "stub_text": "Iria Vale slips through the rain-dark station.",
            "last_offered_chunk_id": conn.incubator["parent_chunk_id"],
            "used_chunk_id": None,
            "use_count": 0,
        }
    ]
    _patch_sync_commit_runtime(monkeypatch)

    chunk_id = commit_incubator_to_database_sync(conn, "bleed-session", slot=5)

    offer = conn.bleed_offers[0]
    assert offer["used_chunk_id"] == (chunk_id if name_present else None)
    assert offer["use_count"] == (1 if name_present else 0)
    uptake_record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "orrery_bleed_uptake"
    )
    assert uptake_record.name_matched is name_present
    if name_present:
        assert uptake_record.four_gram_overlap_ratio == 1.0
    else:
        assert 0.0 < uptake_record.four_gram_overlap_ratio < 1.0


def test_sync_commit_does_not_stamp_offer_from_regenerated_away_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepting draft B cannot consume resolution R offered only to draft A."""

    conn = CommitConnection()
    conn.incubator["new_entities"] = []
    conn.incubator["reference_updates"] = {
        "characters": [],
        "places": [],
        "factions": [],
    }
    conn.bleed_offers = [
        {
            "id": 501,
            "actor_name": "Iria Vale",
            "stub_text": "Iria Vale slips through the station.",
            "last_offered_chunk_id": conn.incubator["parent_chunk_id"],
            "used_chunk_id": None,
            "use_count": 0,
        }
    ]
    draft_a_staging = {"_bleed_offer_resolution_ids": [501]}
    conn.incubator["orrery_proposal"] = draft_a_staging

    conn.incubator["session_id"] = "draft-b"
    conn.incubator["storyteller_text"] = "Iria Vale slips through the station."
    conn.incubator["orrery_proposal"] = {"_bleed_offer_resolution_ids": []}
    _patch_sync_commit_runtime(monkeypatch)

    commit_incubator_to_database_sync(conn, "draft-b", slot=5)

    assert draft_a_staging == {"_bleed_offer_resolution_ids": [501]}
    assert conn.bleed_offers[0]["used_chunk_id"] is None
    assert conn.bleed_offers[0]["use_count"] == 0
    assert not any(
        "orrery:bleed_uptake_candidates" in sql for sql, _params in conn.statements
    )


@pytest.mark.parametrize(
    ("storyteller_text", "expected_use_count"),
    (("Anna waits by the gate.", 0), ("Ann's coat is wet.", 1)),
)
def test_sync_commit_matches_actor_name_on_word_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    storyteller_text: str,
    expected_use_count: int,
) -> None:
    """Ann does not match Anna but does match before a possessive apostrophe."""

    conn = CommitConnection()
    conn.incubator["new_entities"] = []
    conn.incubator["reference_updates"] = {
        "characters": [],
        "places": [],
        "factions": [],
    }
    conn.incubator["storyteller_text"] = storyteller_text
    conn.incubator["orrery_proposal"] = {"_bleed_offer_resolution_ids": [503]}
    conn.bleed_offers = [
        {
            "id": 503,
            "actor_name": "Ann",
            "stub_text": "Ann waits by the gate.",
            "last_offered_chunk_id": conn.incubator["parent_chunk_id"],
            "used_chunk_id": None,
            "use_count": 0,
        }
    ]
    _patch_sync_commit_runtime(monkeypatch)

    chunk_id = commit_incubator_to_database_sync(conn, "boundary", slot=5)

    assert conn.bleed_offers[0]["use_count"] == expected_use_count
    assert conn.bleed_offers[0]["used_chunk_id"] == (
        chunk_id if expected_use_count else None
    )


def test_sync_reconciled_mentions_flow_through_adapter_and_commit(monkeypatch):
    """The validated wire boundary feeds normalized mentions to the real commit."""

    conn = CommitConnection()
    conn.characters.update({"Ressa Morn": 101, "Niko Rell": 102, "Ora Pell": 103})
    wire = SkaldTurnWire(
        narrative=(
            "Ressa Morn remains due before dawn. "
            "Niko Rell and Ora Pell have made no contact."
        ),
        choices=["Wait.", "Proceed."],
        letter="Keep the three debts unresolved.",
    )
    response = LogonUtility._hydrate_provider_response(
        wire,
        SkaldTurnWire,
        presence_baseline=PresenceBaseline(),
        character_roster=CharacterRosterRows(
            characters=[
                {"id": 101, "name": "Ressa Morn", "summary": None},
                {"id": 102, "name": "Niko Rell", "summary": None},
                {"id": 103, "name": "Ora Pell", "summary": None},
            ],
            aliases=[],
        ),
    )
    conn.incubator = response_to_incubator(
        response,
        parent_chunk_id=44,
        user_text="Continue.",
        session_id="sync-655",
        lore_pass_baseline=TEST_BASELINE,
    )
    _patch_sync_commit_runtime(monkeypatch)

    assert conn.incubator["reference_updates"]["characters"] == [
        {
            "character_id": 101,
            "character_name": "Ressa Morn",
            "reference_type": "mentioned",
        },
        {
            "character_id": 102,
            "character_name": "Niko Rell",
            "reference_type": "mentioned",
        },
        {
            "character_id": 103,
            "character_name": "Ora Pell",
            "reference_type": "mentioned",
        },
    ]

    chunk_id = commit_incubator_to_database_sync(conn, "sync-655", slot=5)

    assert conn.character_junctions == [
        (chunk_id, 101, "mentioned"),
        (chunk_id, 102, "mentioned"),
        (chunk_id, 103, "mentioned"),
    ]


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
    monkeypatch.setattr(
        commit_handler_sync, "_orrery_checkpoint_interval", lambda _settings: 0
    )


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


def test_post_commit_compaction_failure_preserves_success_and_retries(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Derived compaction cannot turn a durable acceptance into a false 500."""

    attempts = []

    def flaky_compaction(_conn, *, accepting_chunk_id):
        attempts.append(accepting_chunk_id)
        if len(attempts) == 1:
            raise RuntimeError("provider unavailable")
        return True

    monkeypatch.setattr(
        commit_handler_sync,
        "compact_accepted_correspondence_sync",
        flaky_compaction,
    )
    connection = object()

    assert (
        commit_handler_sync._compact_accepted_correspondence_best_effort(
            connection,
            accepting_chunk_id=11,
        )
        is False
    )
    assert (
        commit_handler_sync._compact_accepted_correspondence_best_effort(
            connection,
            accepting_chunk_id=12,
        )
        is True
    )
    assert attempts == [11, 12]
    assert "leaving the uncompacted journal intact for retry" in caplog.text


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

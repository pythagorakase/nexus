"""Real-PostgreSQL regressions for extend-expiry normalization (issue #649)."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, List, Optional

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.extras import Json
from pydantic import ValidationError
from pydantic_ai import ModelRetry

from nexus.agents.logon.gaia_registry_schema import (
    coerce_gaia_registry_wire,
    load_gaia_registry_wire_spec,
)
from nexus.agents.logon.orrery_tag_validation import (
    _SUBSTANTIVE_UPDATE_PREDICATES,
    _has_substantive_update,
    build_storyteller_tag_validator,
    collect_orrery_tag_issues,
    normalize_extend_expiry_reasserts,
    read_storyteller_vocabulary,
)
from nexus.agents.logon.skald_wire import (
    CharacterUpdateDelta,
    FactionUpdateDelta,
    hydrate_skald_turn,
    PlaceUpdateDelta,
    SkaldGaiaWire,
    SkaldTurnWire,
)
from nexus.api.commit_handler_sync import (
    apply_state_updates_sync,
    commit_incubator_to_database_sync,
    resolve_state_update_ids_sync,
)
from nexus.api.db_pool import close_all_pools
from nexus.api.lore_adapter import response_to_incubator
from nexus.api.slot_utils import VALID_DBNAMES
from nexus.memory.manager import empty_pass2_baseline


pytestmark = pytest.mark.requires_postgres

CHARACTER_TAG = "recently_protective"
EVENT_TAG = "dying"
FACTION_TAG = "schismatic_internal_threat"
PLACE_TAG = "qa649_place_watch"
TIME_TAG = "intoxicated:stimulant"
CHARACTER_REJECTION = (
    "updates.characters[0]: applied_tags: Tag 'recently_protective' uses "
    "reapplication_policy='extend_expiry', which requires duration_override; "
    "storyteller tags_add cannot express duration_override. If the tag is already "
    "active, leave it unchanged; otherwise omit it."
)


@dataclass(frozen=True)
class _EntityRef:
    """Subtype and canonical identifiers for one seeded test entity."""

    wire_id: int
    entity_id: int
    name: str


@dataclass(frozen=True)
class _Qa649Database:
    """Disposable database plus the entity rows seeded into it."""

    dbname: str
    anchor_chunk_id: int
    declaration_anchor_chunk_id: int
    source_chunk_id: int
    anchor_world_time: datetime
    active_character: _EntityRef
    inactive_character: _EntityRef
    time_character: _EntityRef
    rebased_time_character: _EntityRef
    mixed_time_character: _EntityRef
    semantic_character: _EntityRef
    expired_character: _EntityRef
    commit_character: _EntityRef
    place: _EntityRef
    no_default_place: _EntityRef
    faction: _EntityRef


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _insert_entity(cur: Any, kind: str, name: str) -> _EntityRef:
    cur.execute(
        "INSERT INTO entities (kind) VALUES (%s::entity_kind) RETURNING id",
        (kind,),
    )
    entity_id = int(cur.fetchone()[0])
    if kind == "character":
        cur.execute(
            "INSERT INTO characters (name, entity_id) VALUES (%s, %s) RETURNING id",
            (name, entity_id),
        )
    elif kind == "place":
        cur.execute(
            """
            INSERT INTO places (name, type, entity_id)
            VALUES (%s, 'fixed_location', %s)
            RETURNING id
            """,
            (name, entity_id),
        )
    elif kind == "faction":
        cur.execute("SELECT COALESCE(MAX(id), 0) + 649 FROM factions")
        faction_id = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO factions (id, name, entity_id)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (faction_id, name, entity_id),
        )
    else:
        raise AssertionError(f"Unsupported test entity kind: {kind}")
    return _EntityRef(
        wire_id=int(cur.fetchone()[0]),
        entity_id=entity_id,
        name=name,
    )


def _activate_tag(
    cur: Any,
    entity_id: int,
    tag: str,
    *,
    expires_at_world_time: Optional[datetime] = None,
) -> None:
    cur.execute(
        """
        INSERT INTO entity_tags (
            entity_id, tag_id, source_kind, expires_at_world_time
        )
        SELECT %s, id, 'llm_generated', %s
        FROM tags
        WHERE tag = %s
        """,
        (entity_id, expires_at_world_time, tag),
    )
    assert cur.rowcount == 1


def _insert_chunk_at(cur: Any, world_time: datetime, *, scene: int) -> int:
    """Create one real anchor chunk pinned to an exact world clock."""

    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES ('Issue 649 clock anchor.', 'Issue 649 clock anchor.')
        RETURNING id
        """
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, slug, world_time
        ) VALUES (%s, 64, 49, %s, 'primary', %s, %s)
        """,
        (chunk_id, scene, f"Q649{scene:03d}", world_time),
    )
    cur.execute(
        "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
        (world_time, chunk_id),
    )
    return chunk_id


@pytest.fixture(scope="module")
def qa649_db() -> Iterator[_Qa649Database]:
    """Yield a populated current-template clone and drop it after the module."""

    dbname = f"qa649_{uuid.uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        VALID_DBNAMES.add(dbname)
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
                for migration_name in (
                    "109_extend_expiry_default_durations.sql",
                    # The real commit route now runs the experience-formation
                    # sweep, which needs migration 110's formation stamps.
                    "110_experience_formation_sweep.sql",
                ):
                    migration_sql = (migrations_dir / migration_name).read_text()
                    cur.execute(migration_sql)
                    cur.execute(migration_sql)
                anchor_world_time = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
                cur.execute(
                    """
                    INSERT INTO global_variables (id, new_story, base_timestamp)
                    VALUES (true, true, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET base_timestamp = EXCLUDED.base_timestamp
                    """,
                    (anchor_world_time,),
                )
                # The real commit route now runs the experience-formation
                # sweep, whose player-identity lookup fails loudly on a save
                # without a protagonist. Model a complete save.
                protagonist = _insert_entity(cur, "character", "Fixture Protagonist")
                cur.execute(
                    "UPDATE global_variables SET user_character = %s WHERE id = true",
                    (protagonist.wire_id,),
                )
                cur.execute("INSERT INTO entities (kind) VALUES ('place')")
                anchor_chunk_id = _insert_chunk_at(cur, anchor_world_time, scene=1)
                source_chunk_id = _insert_chunk_at(
                    cur,
                    anchor_world_time + timedelta(days=1),
                    scene=900,
                )
                declaration_anchor_chunk_id = _insert_chunk_at(
                    cur,
                    anchor_world_time + timedelta(days=2),
                    scene=100,
                )
                # The legacy statement trigger recomputes earlier clocks when
                # the later row is inserted. Re-pin the exact target anchor;
                # a world_time-only update does not invoke that trigger.
                cur.execute(
                    "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
                    (anchor_world_time, anchor_chunk_id),
                )
                active_character = _insert_entity(
                    cur, "character", "QA649 Active Character"
                )
                inactive_character = _insert_entity(
                    cur, "character", "QA649 Inactive Character"
                )
                time_character = _insert_entity(
                    cur, "character", "QA649 Time Character"
                )
                rebased_time_character = _insert_entity(
                    cur, "character", "QA649 Rebased Time Character"
                )
                mixed_time_character = _insert_entity(
                    cur, "character", "QA649 Mixed Time Character"
                )
                semantic_character = _insert_entity(
                    cur, "character", "QA649 Semantic Character"
                )
                expired_character = _insert_entity(
                    cur, "character", "QA649 Expired Character"
                )
                commit_character = _insert_entity(
                    cur, "character", "QA649 Commit Character"
                )
                place = _insert_entity(cur, "place", "QA649 Place")
                no_default_place = _insert_entity(
                    cur, "place", "QA649 No Default Place"
                )
                faction = _insert_entity(cur, "faction", "QA649 Faction")
                cur.execute(
                    """
                    INSERT INTO tags (
                        tag,
                        category,
                        is_ephemeral,
                        clearance_kind,
                        reapplication_policy,
                        description
                    ) VALUES (
                        %s,
                        'place_threat',
                        true,
                        'time',
                        'extend_expiry',
                        'Issue 649 disposable place tag.'
                    )
                    """,
                    (PLACE_TAG,),
                )
                _activate_tag(cur, active_character.entity_id, CHARACTER_TAG)
                _activate_tag(cur, place.entity_id, PLACE_TAG)
                _activate_tag(cur, faction.entity_id, FACTION_TAG)
        yield _Qa649Database(
            dbname=dbname,
            anchor_chunk_id=anchor_chunk_id,
            declaration_anchor_chunk_id=declaration_anchor_chunk_id,
            source_chunk_id=source_chunk_id,
            anchor_world_time=anchor_world_time,
            active_character=active_character,
            inactive_character=inactive_character,
            time_character=time_character,
            rebased_time_character=rebased_time_character,
            mixed_time_character=mixed_time_character,
            semantic_character=semantic_character,
            expired_character=expired_character,
            commit_character=commit_character,
            place=place,
            no_default_place=no_default_place,
            faction=faction,
        )
    finally:
        close_all_pools()
        VALID_DBNAMES.discard(dbname)
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (dbname,),
            )
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
            )
        admin.close()


def _response(
    *,
    characters: Optional[List[dict[str, Any]]] = None,
    places: Optional[List[dict[str, Any]]] = None,
    factions: Optional[List[dict[str, Any]]] = None,
    orrery_adjudications: Optional[List[dict[str, Any]]] = None,
    scene: Optional[dict[str, Any]] = None,
    new_entities: Optional[List[dict[str, Any]]] = None,
    narrative: str = "The QA649 state changes without a model retry.",
) -> SkaldTurnWire:
    payload: dict[str, Any] = {
        "narrative": narrative,
        "choices": ["Continue.", "Observe."],
        "scene": scene,
        "letter": "Preserve the deterministic boundary behavior.",
        "new_entities": new_entities or [],
        "orrery_adjudications": orrery_adjudications or [],
        "updates": {
            "characters": characters or [],
            "places": places or [],
            "factions": factions or [],
            "relationships": [],
        },
    }
    return SkaldTurnWire.model_validate(payload)


def _gaia_registry_response(
    database: _Qa649Database,
    *,
    characters: Optional[List[dict[str, Any]]] = None,
) -> SkaldGaiaWire:
    schema_model = load_gaia_registry_wire_spec(database.dbname).model
    return schema_model.model_validate(
        {
            "letter": "Preserve the deterministic boundary behavior.",
            "new_entities": [],
            "orrery_adjudications": [],
            "updates": {
                "characters": characters or [],
                "places": [],
                "factions": [],
                "relationships": [],
            },
        }
    )


def _normalize(response: Any, database: _Qa649Database) -> int:
    vocabulary = read_storyteller_vocabulary(database.dbname)
    with _connect(database.dbname) as conn:
        with conn.cursor() as cur:
            return normalize_extend_expiry_reasserts(
                response,
                cur,
                vocabulary=vocabulary,
            )


def _normalize_and_collect(
    response: SkaldTurnWire,
    database: _Qa649Database,
    *,
    proposal_bindings: Optional[dict[str, dict[str, int]]] = None,
) -> tuple[int, List[str]]:
    vocabulary = read_storyteller_vocabulary(database.dbname)
    with _connect(database.dbname) as conn:
        with conn.cursor() as cur:
            normalized = normalize_extend_expiry_reasserts(
                response,
                cur,
                vocabulary=vocabulary,
            )
            issues = collect_orrery_tag_issues(
                response,
                cur,
                vocabulary=vocabulary,
                proposal_bindings=proposal_bindings,
            )
    return normalized, issues


async def _validate_and_apply(
    response: SkaldTurnWire,
    database: _Qa649Database,
) -> SkaldTurnWire:
    """Drive the real validation, hydration, identity resolution, and writer."""

    validator = build_storyteller_tag_validator(
        database.dbname,
        anchor_chunk_id_provider=lambda: database.anchor_chunk_id,
    )
    assert validator is not None
    validated = await validator(SimpleNamespace(retry=0), response)
    assert validated is response
    hydrated = hydrate_skald_turn(validated)
    assert hydrated.state_updates is not None
    with _connect(database.dbname) as conn:
        resolved = resolve_state_update_ids_sync(conn, hydrated.state_updates)
        apply_state_updates_sync(
            conn,
            resolved,
            source_chunk_id=database.source_chunk_id,
            anchor_world_time=database.anchor_world_time,
        )
    return validated


def _current_tag_row(
    database: _Qa649Database,
    *,
    entity_id: int,
    tag: str,
) -> Optional[tuple[Any, ...]]:
    """Return one entity's current durable tag row from the scratch database."""

    with _connect(database.dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    et.applied_at_world_time,
                    et.expires_at_world_time,
                    et.source_chunk_id
                FROM entity_tags et
                JOIN tags registry ON registry.id = et.tag_id
                WHERE et.entity_id = %s
                  AND registry.tag = %s
                  AND et.cleared_at IS NULL
                """,
                (entity_id, tag),
            )
            return cur.fetchone()


def _stage_incubator_response(
    cur: Any,
    *,
    database: _Qa649Database,
    response: SkaldTurnWire,
    session_id: str,
    parent_chunk_id: Optional[int] = None,
) -> None:
    """Hydrate and stage a validated response through the real draft adapter."""

    hydrated = hydrate_skald_turn(response)
    hydrated.generation_model = "TEST"
    staged = response_to_incubator(
        hydrated,
        parent_chunk_id=(
            database.anchor_chunk_id if parent_chunk_id is None else parent_chunk_id
        ),
        user_text="Continue.",
        session_id=session_id,
        lore_pass_baseline=empty_pass2_baseline({}),
    )
    staged["llm_response_id"] = f"response-{session_id}"
    cur.execute(
        """
        INSERT INTO incubator (
            id, chunk_id, parent_chunk_id, user_text, storyteller_text,
            generation_model, choice_object, choice_text,
            metadata_updates, entity_updates, reference_updates,
            orrery_proposal, orrery_adjudications, new_entities,
            correspondence_writer_letter, correspondence_gaia_letter,
            session_id, llm_response_id, status, lore_pass_baseline
        ) VALUES (
            TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, 'provisional', %s
        )
        """,
        (
            staged["chunk_id"],
            staged["parent_chunk_id"],
            staged["user_text"],
            staged["storyteller_text"],
            staged["generation_model"],
            Json(staged["choice_object"]),
            staged["choice_text"],
            Json(staged["metadata_updates"]),
            Json(staged["entity_updates"]),
            Json(staged["reference_updates"]),
            Json(staged["orrery_proposal"]),
            Json(staged["orrery_adjudications"]),
            Json(staged["new_entities"]),
            staged["correspondence_writer_letter"],
            staged["correspondence_gaia_letter"],
            staged["session_id"],
            staged["llm_response_id"],
            Json(staged["lore_pass_baseline"]),
        ),
    )


def _chunk_world_time(database: _Qa649Database, chunk_id: int) -> datetime:
    """Read the trigger-authoritative clock for one committed chunk."""

    with _connect(database.dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
                (chunk_id,),
            )
            row = cur.fetchone()
    if row is None or not isinstance(row[0], datetime):
        raise AssertionError(f"Chunk {chunk_id} has no world_time")
    return row[0]


def _commit_response(
    database: _Qa649Database,
    response: SkaldTurnWire,
    *,
    parent_chunk_id: Optional[int] = None,
    slot: Optional[int] = None,
) -> int:
    """Stage through the real draft adapter and synchronously accept it."""

    session_id = str(uuid.uuid4())
    with _connect(database.dbname) as conn:
        with conn.cursor() as cur:
            _stage_incubator_response(
                cur,
                database=database,
                response=response,
                session_id=session_id,
                parent_chunk_id=parent_chunk_id,
            )
    commit_conn = _connect(database.dbname)
    try:
        return commit_incubator_to_database_sync(commit_conn, session_id, slot=slot)
    finally:
        commit_conn.close()


def test_identity_only_active_character_update_is_removed_before_registry_coercion(
    qa649_db: _Qa649Database,
) -> None:
    response = _gaia_registry_response(
        qa649_db,
        characters=[
            {
                "name": qa649_db.active_character.name,
                "tags_add": [CHARACTER_TAG],
            }
        ],
    )
    assert response.__class__ is not SkaldGaiaWire
    assert response.updates is not None
    original_updates = response.updates.characters

    normalized = _normalize(response, qa649_db)
    coerced = coerce_gaia_registry_wire(response)

    assert normalized == 1
    assert response.updates.characters is original_updates
    assert original_updates == []
    assert coerced.updates is not None
    assert coerced.updates.characters == []


def test_active_character_update_with_activity_survives_registry_coercion(
    qa649_db: _Qa649Database,
) -> None:
    response = _gaia_registry_response(
        qa649_db,
        characters=[
            {
                "name": qa649_db.active_character.name,
                "activity": "Keeps watch over the QA boundary.",
                "tags_add": [CHARACTER_TAG],
            }
        ],
    )

    normalized = _normalize(response, qa649_db)
    coerced = coerce_gaia_registry_wire(response)

    assert normalized == 1
    assert response.updates is not None
    assert len(response.updates.characters) == 1
    assert response.updates.characters[0].tags_add is None
    assert coerced.updates is not None
    assert coerced.updates.characters[0].activity == "Keeps watch over the QA boundary."
    assert coerced.updates.characters[0].tags_add is None


def test_active_character_update_with_tags_clear_survives_registry_coercion(
    qa649_db: _Qa649Database,
) -> None:
    response = _gaia_registry_response(
        qa649_db,
        characters=[
            {
                "name": qa649_db.active_character.name,
                "tags_add": [CHARACTER_TAG],
                "tags_clear": [CHARACTER_TAG],
            }
        ],
    )

    normalized = _normalize(response, qa649_db)
    coerced = coerce_gaia_registry_wire(response)

    assert normalized == 1
    assert response.updates is not None
    assert len(response.updates.characters) == 1
    assert response.updates.characters[0].tags_add is None
    assert response.updates.characters[0].tags_clear == [CHARACTER_TAG]
    assert coerced.updates is not None
    assert coerced.updates.characters[0].tags_add is None
    assert coerced.updates.characters[0].tags_clear == [CHARACTER_TAG]


@pytest.mark.parametrize(
    ("entity_kind", "model", "error"),
    [
        (
            "character",
            CharacterUpdateDelta,
            "character update requires a substantive field",
        ),
        ("place", PlaceUpdateDelta, "place update requires a substantive field"),
        (
            "faction",
            FactionUpdateDelta,
            "faction update requires a substantive field",
        ),
    ],
)
def test_normalization_predicate_matches_identity_only_wire_rejection(
    entity_kind: str,
    model: Any,
    error: str,
) -> None:
    identity_only = model.model_construct(name=f"QA649 {entity_kind}")

    assert not _has_substantive_update(entity_kind, identity_only)
    with pytest.raises(ValidationError, match=error):
        model.model_validate(identity_only.model_dump(mode="python"))


@pytest.mark.parametrize(
    ("entity_kind", "model"),
    [
        ("character", CharacterUpdateDelta),
        ("place", PlaceUpdateDelta),
        ("faction", FactionUpdateDelta),
    ],
)
def test_normalization_predicate_fields_match_wire_model(
    entity_kind: str,
    model: Any,
) -> None:
    assert set(_SUBSTANTIVE_UPDATE_PREDICATES[entity_kind]) == set(
        model.model_fields
    ) - {"name", "id", "tags_add"}


@pytest.mark.asyncio
async def test_active_character_identity_only_reassert_arm_is_removed(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _response(
        characters=[
            {
                "name": qa649_db.active_character.name,
                "tags_add": [CHARACTER_TAG],
            }
        ]
    )
    assert response.updates is not None
    update = response.updates.characters[0]
    original_tags_add = update.tags_add
    assert original_tags_add == [CHARACTER_TAG]
    validator = build_storyteller_tag_validator(qa649_db.dbname)
    assert validator is not None

    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        validated = await validator(SimpleNamespace(retry=0), response)

    assert validated is response
    assert original_tags_add == []
    assert update.tags_add is None
    assert response.updates.characters == []
    assert [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("extend-expiry re-assert normalized")
    ] == [
        "extend-expiry re-assert normalized entity_kind=character "
        f"entity_name={qa649_db.active_character.name!r} tag={CHARACTER_TAG!r}"
    ]
    assert [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("extend-expiry no-op update removed")
    ] == [
        "extend-expiry no-op update removed entity_kind=character "
        f"entity_name={qa649_db.active_character.name!r}"
    ]
    vocabulary = read_storyteller_vocabulary(qa649_db.dbname)
    with _connect(qa649_db.dbname) as conn:
        with conn.cursor() as cur:
            assert (
                collect_orrery_tag_issues(
                    response,
                    cur,
                    vocabulary=vocabulary,
                )
                == []
            )


def test_inactive_extend_expiry_rejection_text_is_unchanged(
    qa649_db: _Qa649Database,
) -> None:
    response = _response(
        characters=[
            {
                "name": qa649_db.inactive_character.name,
                "tags_add": [CHARACTER_TAG],
            }
        ]
    )

    normalized, issues = _normalize_and_collect(response, qa649_db)

    assert normalized == 0
    assert response.updates is not None
    assert response.updates.characters[0].tags_add == [CHARACTER_TAG]
    assert issues == [CHARACTER_REJECTION]


def test_replacement_state_delta_extend_expiry_remains_rejected(
    qa649_db: _Qa649Database,
) -> None:
    response = _response(
        orrery_adjudications=[
            {
                "proposal_id": "qa649-proposal",
                "action": "replace",
                "replacement_state_delta": {
                    "entity_tags_add": [CHARACTER_TAG],
                },
            }
        ]
    )

    normalized, issues = _normalize_and_collect(
        response,
        qa649_db,
        proposal_bindings={
            "qa649-proposal": {
                "actor": qa649_db.active_character.entity_id,
            }
        },
    )

    assert normalized == 0
    assert issues == [
        "orrery_adjudications[0].replacement_state_delta.entity_tags_add: "
        "applied_tags: Tag 'recently_protective' uses "
        "reapplication_policy='extend_expiry', which requires duration_override; "
        "storyteller tags_add cannot express duration_override. If the tag is "
        "already active, leave it unchanged; otherwise omit it."
    ]


def test_non_extend_expiry_tags_survive_active_normalization(
    qa649_db: _Qa649Database,
) -> None:
    response = _response(
        characters=[
            {
                "name": qa649_db.active_character.name,
                "tags_add": [CHARACTER_TAG, "human"],
            }
        ]
    )

    normalized, issues = _normalize_and_collect(response, qa649_db)

    assert normalized == 1
    assert response.updates is not None
    assert response.updates.characters[0].tags_add == ["human"]
    assert issues == []


def test_unknown_name_preserves_extend_expiry_rejection(
    qa649_db: _Qa649Database,
) -> None:
    response = _response(
        characters=[
            {
                "name": "QA649 Missing Character",
                "tags_add": [CHARACTER_TAG],
            }
        ]
    )

    normalized, issues = _normalize_and_collect(response, qa649_db)

    assert normalized == 0
    assert response.updates is not None
    assert response.updates.characters[0].tags_add == [CHARACTER_TAG]
    assert issues == [CHARACTER_REJECTION]


@pytest.mark.parametrize(
    ("array_name", "entity_attribute", "tag"),
    [
        ("places", "place", PLACE_TAG),
        ("factions", "faction", FACTION_TAG),
    ],
)
def test_active_place_and_faction_identity_only_reassert_arms_are_removed_by_id(
    qa649_db: _Qa649Database,
    array_name: str,
    entity_attribute: str,
    tag: str,
) -> None:
    entity = getattr(qa649_db, entity_attribute)
    entity_updates: List[dict[str, Any]] = [
        {
            "id": entity.wire_id,
            "name": entity.name,
            "tags_add": [tag],
        }
    ]
    response = _response(
        places=entity_updates if array_name == "places" else None,
        factions=entity_updates if array_name == "factions" else None,
    )

    normalized, issues = _normalize_and_collect(response, qa649_db)

    assert normalized == 1
    assert response.updates is not None
    assert getattr(response.updates, array_name) == []
    assert issues == []


def test_migration_109_seeds_only_time_cleared_defaults(
    qa649_db: _Qa649Database,
) -> None:
    with _connect(qa649_db.dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tag, default_duration
                FROM tags
                WHERE default_duration IS NOT NULL
                ORDER BY tag
                """
            )
            assert cur.fetchall() == [
                ("intoxicated:depressant", timedelta(hours=8)),
                ("intoxicated:dissociative", timedelta(hours=6)),
                ("intoxicated:hallucinogen", timedelta(hours=8)),
                ("intoxicated:stimulant", timedelta(hours=6)),
            ]
            cur.execute(
                """
                SELECT col_description(
                    'tags'::regclass,
                    (
                        SELECT attnum
                        FROM pg_attribute
                        WHERE attrelid = 'tags'::regclass
                          AND attname = 'default_duration'
                    )
                )
                """
            )
            comment = cur.fetchone()[0]
            assert "time-cleared" in comment
            assert "semantic- and event-cleared" in comment


@pytest.mark.asyncio
async def test_time_first_application_lands_with_registry_default_expiry(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _response(
        characters=[
            {
                "id": qa649_db.time_character.wire_id,
                "name": qa649_db.time_character.name,
                "tags_add": [TIME_TAG],
            }
        ]
    )

    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        await _validate_and_apply(response, qa649_db)

    assert "reason=first-application-time-defaulted" in caplog.text
    row = _current_tag_row(
        qa649_db,
        entity_id=qa649_db.time_character.entity_id,
        tag=TIME_TAG,
    )
    assert row == (
        qa649_db.anchor_world_time,
        qa649_db.anchor_world_time + timedelta(hours=6),
        qa649_db.source_chunk_id,
    )


@pytest.mark.asyncio
async def test_removed_active_update_rebases_later_defaulted_application(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _response(
        characters=[
            {
                "id": qa649_db.active_character.wire_id,
                "name": qa649_db.active_character.name,
                "tags_add": [CHARACTER_TAG],
            },
            {
                "id": qa649_db.rebased_time_character.wire_id,
                "name": qa649_db.rebased_time_character.name,
                "tags_add": [TIME_TAG],
            },
        ]
    )

    caplog.clear()
    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        await _validate_and_apply(response, qa649_db)

    assert "reason=normalized-active" in caplog.text
    assert "reason=first-application-time-defaulted" in caplog.text
    assert response.updates is not None
    assert [update.name for update in response.updates.characters] == [
        qa649_db.rebased_time_character.name
    ]
    row = _current_tag_row(
        qa649_db,
        entity_id=qa649_db.rebased_time_character.entity_id,
        tag=TIME_TAG,
    )
    assert row == (
        qa649_db.anchor_world_time,
        qa649_db.anchor_world_time + timedelta(hours=6),
        qa649_db.source_chunk_id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tag", "clearance_kind"),
    [
        (CHARACTER_TAG, "semantic"),
        (EVENT_TAG, "event"),
    ],
)
async def test_semantic_and_event_first_applications_land_without_expiry(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
    tag: str,
    clearance_kind: str,
) -> None:
    response = _response(
        characters=[
            {
                "id": qa649_db.semantic_character.wire_id,
                "name": qa649_db.semantic_character.name,
                "tags_add": [tag],
            }
        ]
    )

    caplog.clear()
    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        await _validate_and_apply(response, qa649_db)

    assert "reason=first-application-landed-no-expiry" in caplog.text
    assert f"clearance_kind={clearance_kind}" in caplog.text
    row = _current_tag_row(
        qa649_db,
        entity_id=qa649_db.semantic_character.entity_id,
        tag=tag,
    )
    assert row == (
        qa649_db.anchor_world_time,
        None,
        qa649_db.source_chunk_id,
    )


@pytest.mark.asyncio
async def test_time_first_application_without_default_rejects_loudly(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _response(
        places=[
            {
                "id": qa649_db.no_default_place.wire_id,
                "name": qa649_db.no_default_place.name,
                "tags_add": [PLACE_TAG],
            }
        ]
    )
    validator = build_storyteller_tag_validator(
        qa649_db.dbname,
        anchor_chunk_id_provider=lambda: qa649_db.anchor_chunk_id,
    )
    assert validator is not None

    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        with pytest.raises(ModelRetry) as exc_info:
            await validator(SimpleNamespace(retry=0), response)

    assert "requires duration_override" in exc_info.value.message
    rejection_log = next(
        record.getMessage()
        for record in caplog.records
        if "reason=no-default-rejected" in record.getMessage()
    )
    assert "array=places" in rejection_log
    assert "index=0" in rejection_log
    assert f"supplied_id={qa649_db.no_default_place.wire_id}" in rejection_log
    assert f"supplied_name='{qa649_db.no_default_place.name}'" in rejection_log
    assert f"offending_tags=['{PLACE_TAG}']" in rejection_log


@pytest.mark.asyncio
async def test_expiry_at_anchor_is_inactive_and_defaulted_from_exact_anchor(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with _connect(qa649_db.dbname) as conn:
        with conn.cursor() as cur:
            _activate_tag(
                cur,
                qa649_db.expired_character.entity_id,
                TIME_TAG,
                expires_at_world_time=qa649_db.anchor_world_time,
            )
    response = _response(
        characters=[
            {
                "id": qa649_db.expired_character.wire_id,
                "name": qa649_db.expired_character.name,
                "tags_add": [TIME_TAG],
            }
        ]
    )

    caplog.clear()
    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        await _validate_and_apply(response, qa649_db)

    assert "reason=expiry-disagreement" in caplog.text
    assert "reason=first-application-time-defaulted" in caplog.text
    row = _current_tag_row(
        qa649_db,
        entity_id=qa649_db.expired_character.entity_id,
        tag=TIME_TAG,
    )
    assert row == (
        qa649_db.anchor_world_time,
        qa649_db.anchor_world_time + timedelta(hours=6),
        qa649_db.source_chunk_id,
    )


@pytest.mark.asyncio
async def test_expired_semantic_row_is_relanded_without_expiry(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with _connect(qa649_db.dbname) as conn:
        with conn.cursor() as cur:
            _activate_tag(
                cur,
                qa649_db.expired_character.entity_id,
                CHARACTER_TAG,
                expires_at_world_time=qa649_db.anchor_world_time,
            )
    response = _response(
        characters=[
            {
                "id": qa649_db.expired_character.wire_id,
                "name": qa649_db.expired_character.name,
                "tags_add": [CHARACTER_TAG],
            }
        ]
    )

    caplog.clear()
    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        await _validate_and_apply(response, qa649_db)

    assert "reason=expiry-disagreement" in caplog.text
    assert "reason=first-application-landed-no-expiry" in caplog.text
    row = _current_tag_row(
        qa649_db,
        entity_id=qa649_db.expired_character.entity_id,
        tag=CHARACTER_TAG,
    )
    assert row == (
        qa649_db.anchor_world_time,
        None,
        qa649_db.source_chunk_id,
    )


@pytest.mark.asyncio
async def test_id_name_disagreement_rejects_with_distinct_reason(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _response(
        characters=[
            {
                "id": qa649_db.time_character.wire_id,
                "name": qa649_db.semantic_character.name,
                "tags_add": [TIME_TAG],
            }
        ]
    )
    validator = build_storyteller_tag_validator(
        qa649_db.dbname,
        anchor_chunk_id_provider=lambda: qa649_db.anchor_chunk_id,
    )
    assert validator is not None

    caplog.clear()
    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        with pytest.raises(ModelRetry) as exc_info:
            await validator(SimpleNamespace(retry=0), response)

    assert "reason=id-name-conflict" in exc_info.value.message
    conflict_log = next(
        record.getMessage()
        for record in caplog.records
        if "reason=id-name-conflict" in record.getMessage()
    )
    assert "array=characters" in conflict_log
    assert "index=0" in conflict_log
    assert f"supplied_id={qa649_db.time_character.wire_id}" in conflict_log
    assert f"supplied_name='{qa649_db.semantic_character.name}'" in conflict_log
    assert f"offending_tags=['{TIME_TAG}']" in conflict_log


@pytest.mark.asyncio
async def test_model_controlled_name_cannot_inject_a_reason_token(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    hostile_name = "reason=normalized-active"
    with _connect(qa649_db.dbname) as conn:
        with conn.cursor() as cur:
            hostile_character = _insert_entity(cur, "character", hostile_name)
            _activate_tag(cur, hostile_character.entity_id, CHARACTER_TAG)
    response = _response(
        characters=[
            {
                "id": hostile_character.wire_id,
                "name": hostile_name,
                "tags_add": [CHARACTER_TAG, hostile_name],
            }
        ]
    )
    validator = build_storyteller_tag_validator(
        qa649_db.dbname,
        anchor_chunk_id_provider=lambda: qa649_db.anchor_chunk_id,
    )
    assert validator is not None

    caplog.clear()
    with caplog.at_level(
        logging.INFO,
        logger="nexus.logon.orrery_tag_validation",
    ):
        with pytest.raises(ModelRetry):
            await validator(SimpleNamespace(retry=0), response)

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "nexus.logon.orrery_tag_validation"
    ]
    classification_logs = [
        message
        for message in messages
        if message.startswith("extend-expiry boundary classified:")
    ]
    assert len(classification_logs) == 1
    classification_log = classification_logs[0]
    assert classification_log.count("reason=") == 1
    assert "reason=normalized-active" in classification_log
    assert "entity_name='reason\\x3dnormalized-active'" in classification_log
    assert sum(message.count("reason=normalized-active") for message in messages) == 1

    retry_logs = [
        message
        for message in messages
        if message.startswith("Storyteller output failed registry validation")
    ]
    assert len(retry_logs) == 1
    retry_log = retry_logs[0]
    assert "retry_issues=" in retry_log
    assert "reason=" not in retry_log
    assert "reason\\x3dnormalized-active" in retry_log


@pytest.mark.asyncio
async def test_mixed_payload_logs_active_defaulted_and_rejected_reasons(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _response(
        characters=[
            {
                "id": qa649_db.active_character.wire_id,
                "name": qa649_db.active_character.name,
                "tags_add": [CHARACTER_TAG],
            },
            {
                "id": qa649_db.mixed_time_character.wire_id,
                "name": qa649_db.mixed_time_character.name,
                "tags_add": [TIME_TAG],
            },
        ],
        places=[
            {
                "id": qa649_db.no_default_place.wire_id,
                "name": qa649_db.no_default_place.name,
                "tags_add": [PLACE_TAG],
            }
        ],
    )
    validator = build_storyteller_tag_validator(
        qa649_db.dbname,
        anchor_chunk_id_provider=lambda: qa649_db.anchor_chunk_id,
    )
    assert validator is not None

    caplog.clear()
    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        with pytest.raises(ModelRetry) as exc_info:
            await validator(SimpleNamespace(retry=0), response)

    assert "requires duration_override" in exc_info.value.message
    assert TIME_TAG not in exc_info.value.message
    messages = [record.getMessage() for record in caplog.records]
    assert sum("reason=normalized-active" in message for message in messages) == 1
    assert (
        sum(
            "reason=first-application-time-defaulted" in message for message in messages
        )
        == 1
    )
    assert sum("reason=no-default-rejected" in message for message in messages) == 1
    assert response.updates is not None
    assert [update.name for update in response.updates.characters] == [
        qa649_db.mixed_time_character.name
    ]


@pytest.mark.asyncio
async def test_time_default_survives_real_draft_and_commit_route(
    qa649_db: _Qa649Database,
) -> None:
    declared_character_name = "QA649 Child-Clock Declaration Character"
    response = _response(
        characters=[
            {
                "id": qa649_db.commit_character.wire_id,
                "name": qa649_db.commit_character.name,
                "tags_add": [TIME_TAG],
            }
        ],
        scene={"elapsed_minutes": 420},
        new_entities=[
            {
                "kind": "character",
                "name": declared_character_name,
                "summary": "A same-turn declaration with a clock-cleared tag hint.",
                "tag_hints": [TIME_TAG],
            }
        ],
    )
    validator = build_storyteller_tag_validator(
        qa649_db.dbname,
        anchor_chunk_id_provider=lambda: qa649_db.anchor_chunk_id,
    )
    assert validator is not None
    validated = await validator(SimpleNamespace(retry=0), response)
    assert validated is response
    accepted_chunk_id = _commit_response(qa649_db, response, slot=1)
    accepting_world_time = _chunk_world_time(qa649_db, accepted_chunk_id)
    assert accepting_world_time == qa649_db.anchor_world_time + timedelta(hours=7)

    row = _current_tag_row(
        qa649_db,
        entity_id=qa649_db.commit_character.entity_id,
        tag=TIME_TAG,
    )
    assert row == (
        accepting_world_time,
        accepting_world_time + timedelta(hours=6),
        accepted_chunk_id,
    )
    with _connect(qa649_db.dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT entity_id FROM characters WHERE name = %s",
                (declared_character_name,),
            )
            declared_row = cur.fetchone()
    assert declared_row is not None
    declared_entity_id = int(declared_row[0])
    declared_tag_row = _current_tag_row(
        qa649_db,
        entity_id=declared_entity_id,
        tag=TIME_TAG,
    )
    assert declared_tag_row == row

    before_expiry = _response(scene={"elapsed_minutes": 359})
    before_expiry_chunk_id = _commit_response(
        qa649_db,
        before_expiry,
        parent_chunk_id=accepted_chunk_id,
    )
    assert _chunk_world_time(qa649_db, before_expiry_chunk_id) == (
        accepting_world_time + timedelta(hours=5, minutes=59)
    )
    assert (
        _current_tag_row(
            qa649_db,
            entity_id=qa649_db.commit_character.entity_id,
            tag=TIME_TAG,
        )
        == row
    )
    assert (
        _current_tag_row(
            qa649_db,
            entity_id=declared_entity_id,
            tag=TIME_TAG,
        )
        == declared_tag_row
    )

    at_expiry = _response(scene={"elapsed_minutes": 1})
    at_expiry_chunk_id = _commit_response(
        qa649_db,
        at_expiry,
        parent_chunk_id=before_expiry_chunk_id,
    )
    assert _chunk_world_time(qa649_db, at_expiry_chunk_id) == (
        accepting_world_time + timedelta(hours=6)
    )
    assert (
        _current_tag_row(
            qa649_db,
            entity_id=qa649_db.commit_character.entity_id,
            tag=TIME_TAG,
        )
        is None
    )
    assert (
        _current_tag_row(
            qa649_db,
            entity_id=declared_entity_id,
            tag=TIME_TAG,
        )
        is None
    )


@pytest.mark.asyncio
async def test_same_turn_declared_faction_first_application_commits(
    qa649_db: _Qa649Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    faction_name = "QA649 Same-Turn Faction"
    response = _response(
        factions=[
            {
                "name": faction_name,
                "tags_add": [FACTION_TAG],
            }
        ],
        new_entities=[
            {
                "kind": "faction",
                "name": faction_name,
                "summary": "A newly declared faction used by issue 649 QA.",
            }
        ],
    )
    validator = build_storyteller_tag_validator(
        qa649_db.dbname,
        allow_same_turn_faction_declarations=True,
        anchor_chunk_id_provider=lambda: qa649_db.declaration_anchor_chunk_id,
    )
    assert validator is not None

    caplog.clear()
    with caplog.at_level(
        logging.WARNING,
        logger="nexus.logon.orrery_tag_validation",
    ):
        validated = await validator(SimpleNamespace(retry=0), response)
    assert validated is response
    deferral_logs = [
        record.getMessage()
        for record in caplog.records
        if "reason=first-application-deferred-declared-entity" in record.getMessage()
    ]
    assert len(deferral_logs) == 1
    assert deferral_logs[0].count("reason=") == 1
    assert f"entity_name={faction_name!r}" in deferral_logs[0]

    accepted_chunk_id = _commit_response(
        qa649_db,
        response,
        parent_chunk_id=qa649_db.declaration_anchor_chunk_id,
        slot=1,
    )
    accepting_world_time = _chunk_world_time(qa649_db, accepted_chunk_id)
    with _connect(qa649_db.dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, entity_id FROM factions WHERE name = %s",
                (faction_name,),
            )
            faction_row = cur.fetchone()
    assert faction_row is not None
    assert _current_tag_row(
        qa649_db,
        entity_id=int(faction_row[1]),
        tag=FACTION_TAG,
    ) == (accepting_world_time, None, accepted_chunk_id)

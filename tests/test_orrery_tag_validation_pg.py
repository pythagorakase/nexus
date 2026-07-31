"""Real-PostgreSQL regressions for extend-expiry normalization (issue #649)."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from types import SimpleNamespace
from typing import Any, Iterator, List, Optional
import uuid

import psycopg2
from psycopg2 import sql
from pydantic import ValidationError
import pytest

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
    PlaceUpdateDelta,
    SkaldGaiaWire,
    SkaldTurnWire,
)
from nexus.api.db_pool import close_all_pools
from nexus.api.slot_utils import VALID_DBNAMES


pytestmark = pytest.mark.requires_postgres

CHARACTER_TAG = "recently_protective"
FACTION_TAG = "schismatic_internal_threat"
PLACE_TAG = "qa649_place_watch"
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
    active_character: _EntityRef
    inactive_character: _EntityRef
    place: _EntityRef
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


def _activate_tag(cur: Any, entity_id: int, tag: str) -> None:
    cur.execute(
        """
        INSERT INTO entity_tags (entity_id, tag_id, source_kind)
        SELECT %s, id, 'llm_generated'
        FROM tags
        WHERE tag = %s
        """,
        (entity_id, tag),
    )
    assert cur.rowcount == 1


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
                cur.execute(
                    """
                    INSERT INTO global_variables (id, new_story, base_timestamp)
                    VALUES (true, true, '2026-07-31T12:00:00+00:00')
                    ON CONFLICT (id) DO UPDATE
                    SET base_timestamp = EXCLUDED.base_timestamp
                    """
                )
                cur.execute("INSERT INTO entities (kind) VALUES ('place')")
                active_character = _insert_entity(
                    cur, "character", "QA649 Active Character"
                )
                inactive_character = _insert_entity(
                    cur, "character", "QA649 Inactive Character"
                )
                place = _insert_entity(cur, "place", "QA649 Place")
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
                        'semantic',
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
            active_character=active_character,
            inactive_character=inactive_character,
            place=place,
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
) -> SkaldTurnWire:
    payload: dict[str, Any] = {
        "narrative": "The QA649 state changes without a model retry.",
        "choices": ["Continue.", "Observe."],
        "letter": "Preserve the deterministic boundary behavior.",
        "new_entities": [],
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
        f"entity={qa649_db.active_character.name} tag={CHARACTER_TAG}"
    ]
    assert [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("extend-expiry no-op update removed")
    ] == [
        "extend-expiry no-op update removed entity_kind=character "
        f"entity={qa649_db.active_character.name}"
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
    response = _response(
        **{
            array_name: [
                {
                    "id": entity.wire_id,
                    "name": entity.name,
                    "tags_add": [tag],
                }
            ]
        }
    )

    normalized, issues = _normalize_and_collect(response, qa649_db)

    assert normalized == 1
    assert response.updates is not None
    assert getattr(response.updates, array_name) == []
    assert issues == []

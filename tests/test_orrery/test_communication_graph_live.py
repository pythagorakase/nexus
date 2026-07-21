"""Rollback-only PostgreSQL coverage for Stage 2b communication assembly."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.audit import entity_context, explain_dry_run
from nexus.agents.orrery.communication import (
    CommunicationEdge,
    CommunicationGraph,
    _valence_tier,
    assemble_communication_graph,
)
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings
from nexus.config.settings_models import OrreryContagionSettings


pytestmark = pytest.mark.requires_postgres

LIVE_SLOT = 5
WORLD_TIME = datetime(2073, 8, 1, 12, 0, tzinfo=timezone.utc)


def _install_valence_shadow(cur: Any) -> None:
    """Shadow the pending-088 table shape in this connection's temp schema."""

    cur.execute(
        r"""
        CREATE TEMP TABLE character_relationships ON COMMIT DROP AS
        SELECT cr.* FROM public.character_relationships cr;

        ALTER TABLE pg_temp.character_relationships
            ADD COLUMN IF NOT EXISTS valence_current numeric;

        UPDATE pg_temp.character_relationships
        SET valence_current = substring(
            emotional_valence::text FROM '^([+-]?[0-9]+)\|'
        )::numeric / 5.5
        WHERE valence_current IS NULL
        """
    )


def _insert_character(
    session: Session, *, token: str, label: str, active: bool = True
) -> tuple[int, int]:
    entity_id = int(
        session.execute(
            text(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('character', :active)
                RETURNING id
                """
            ),
            {"active": active},
        ).scalar_one()
    )
    character_id = int(
        session.execute(
            text(
                """
                INSERT INTO characters (name, entity_id)
                VALUES (:name, :entity_id)
                RETURNING id
                """
            ),
            {"name": f"communication-{token}-{label}", "entity_id": entity_id},
        ).scalar_one()
    )
    return entity_id, character_id


def _insert_relationship(
    session: Session,
    *,
    source_character_id: int,
    target_character_id: int,
    relationship_type: str,
    emotional_valence: str,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, valence_current, dynamic,
                recent_events, history
            ) VALUES (
                :source_id, :target_id, :relationship_type,
                :emotional_valence, :valence_current,
                'Rollback-only communication fixture.',
                'No persistent events.', 'Created for issue 477 Stage 2b.'
            )
            """
        ),
        {
            "source_id": source_character_id,
            "target_id": target_character_id,
            "relationship_type": relationship_type,
            "emotional_valence": emotional_valence,
            "valence_current": Decimal(emotional_valence.split("|", maxsplit=1)[0])
            / Decimal("5.5"),
        },
    )


def _insert_pair_tag(
    session: Session,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tag: str,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO entity_pair_tags (
                subject_entity_id, object_entity_id, pair_tag_id,
                source_kind, template_id
            )
            SELECT :subject_id, :object_id, pt.id,
                   'template', 'test_communication_graph_live'
            FROM pair_tags pt
            WHERE pt.tag = :tag AND NOT pt.deprecated
            """
        ),
        {
            "subject_id": subject_entity_id,
            "object_id": object_entity_id,
            "tag": tag,
        },
    )


def _insert_culture_tag(session: Session, *, entity_id: int, tag: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO entity_tags (entity_id, tag_id, source_kind, template_id)
            SELECT :entity_id, t.id, 'template', 'test_communication_graph_live'
            FROM tags t
            WHERE t.tag = :tag AND NOT t.deprecated
            """
        ),
        {"entity_id": entity_id, "tag": tag},
    )


@pytest.fixture()
def communication_db() -> Iterator[dict[str, Any]]:
    """Build isolated character/channel fixtures in one slot-5 transaction."""

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        raw_connection = connection.connection.driver_connection
        with raw_connection.cursor() as cur:
            _install_valence_shadow(cur)
        token = uuid4().hex[:12]
        labels = (
            "lone_teller",
            "lone_listener",
            "neutral_teller",
            "neutral_listener",
            "debtor",
            "creditor",
            "authority",
            "subordinate",
            "handler",
            "asset",
            "junior_member",
            "outcast_member",
            "culture_listener",
            "reciprocal_low",
            "reciprocal_high",
            "plain_neutral_teller",
            "plain_neutral_listener",
            "hostile_teller",
            "hostile_listener",
        )
        entities: dict[str, int] = {}
        characters: dict[str, int] = {}
        for label in labels:
            entity_id, character_id = _insert_character(
                session, token=token, label=label
            )
            entities[label] = entity_id
            characters[label] = character_id

        _insert_relationship(
            session,
            source_character_id=characters["lone_teller"],
            target_character_id=characters["lone_listener"],
            relationship_type="associate",
            emotional_valence="+3|trusting",
        )
        _insert_relationship(
            session,
            source_character_id=characters["neutral_teller"],
            target_character_id=characters["neutral_listener"],
            relationship_type="handler",
            emotional_valence="0|neutral",
        )
        _insert_relationship(
            session,
            source_character_id=characters["plain_neutral_teller"],
            target_character_id=characters["plain_neutral_listener"],
            relationship_type="associate",
            emotional_valence="0|neutral",
        )
        _insert_relationship(
            session,
            source_character_id=characters["hostile_teller"],
            target_character_id=characters["hostile_listener"],
            relationship_type="associate",
            emotional_valence="-3|resentful",
        )
        _insert_relationship(
            session,
            source_character_id=characters["reciprocal_low"],
            target_character_id=characters["reciprocal_high"],
            relationship_type="captor",
            emotional_valence="-3|resentful",
        )
        _insert_relationship(
            session,
            source_character_id=characters["reciprocal_high"],
            target_character_id=characters["reciprocal_low"],
            relationship_type="captor",
            emotional_valence="-3|resentful",
        )

        inactive_entity, inactive_character = _insert_character(
            session, token=token, label="inactive", active=False
        )
        entities["inactive"] = inactive_entity
        characters["inactive"] = inactive_character
        _insert_relationship(
            session,
            source_character_id=inactive_character,
            target_character_id=characters["lone_listener"],
            relationship_type="associate",
            emotional_valence="+3|trusting",
        )

        _insert_pair_tag(
            session,
            subject_entity_id=entities["debtor"],
            object_entity_id=entities["creditor"],
            tag="obligation",
        )
        _insert_pair_tag(
            session,
            subject_entity_id=entities["authority"],
            object_entity_id=entities["subordinate"],
            tag="authority_over",
        )
        _insert_pair_tag(
            session,
            subject_entity_id=entities["handler"],
            object_entity_id=entities["asset"],
            tag="handles",
        )
        _insert_pair_tag(
            session,
            subject_entity_id=inactive_entity,
            object_entity_id=entities["asset"],
            tag="handles",
        )

        faction_entity_id = int(
            session.execute(
                text(
                    """
                    SELECT f.entity_id
                    FROM factions f
                    JOIN entities e ON e.id = f.entity_id
                    WHERE e.is_active = true
                      AND NOT EXISTS (
                          SELECT 1
                          FROM entity_tags_current etc
                          WHERE etc.entity_id = f.entity_id
                            AND etc.category IN (
                                'operational_secrecy', 'operational_mode'
                            )
                      )
                    ORDER BY f.entity_id
                    LIMIT 1
                    """
                )
            ).scalar_one()
        )
        _insert_pair_tag(
            session,
            subject_entity_id=entities["junior_member"],
            object_entity_id=faction_entity_id,
            tag="status:junior",
        )
        _insert_pair_tag(
            session,
            subject_entity_id=entities["outcast_member"],
            object_entity_id=faction_entity_id,
            tag="status:outcast",
        )
        _insert_pair_tag(
            session,
            subject_entity_id=faction_entity_id,
            object_entity_id=entities["culture_listener"],
            tag="authority_over",
        )

        yield {
            "session": session,
            "raw_connection": connection.connection.driver_connection,
            "entities": entities,
            "characters": characters,
            "faction_entity_id": faction_entity_id,
            "settings": load_settings("nexus.toml").orrery.contagion,
        }
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _assemble(db: dict[str, Any]) -> CommunicationGraph:
    return assemble_communication_graph(
        db["session"], settings=db["settings"], world_time=WORLD_TIME
    )


def _between(
    graph: CommunicationGraph, source: int, target: int, *, kind: str
) -> tuple[CommunicationEdge, ...]:
    return tuple(
        edge
        for edge in graph.edges
        if edge.teller_entity_id == source
        and edge.listener_entity_id == target
        and edge.kind == kind
    )


def test_conflicted_live_pair_licenses_only_each_tellers_own_direction(
    communication_db: dict[str, Any],
) -> None:
    """Tomi trusts Kosi; Kosi's captor stance is configured as never."""

    session = communication_db["session"]
    ids = {
        row["name"]: int(row["entity_id"])
        for row in session.execute(
            text(
                """
                SELECT name, entity_id
                FROM characters
                WHERE name IN ('Tomi', 'Kosi')
                ORDER BY name
                """
            )
        ).mappings()
    }
    if set(ids) != {"Tomi", "Kosi"}:
        pytest.skip("save_05 does not contain the frozen Tomi/Kosi pair")
    graph = assemble_communication_graph(
        session,
        settings=load_settings("nexus.toml").orrery.contagion,
        world_time=WORLD_TIME,
    )

    tomi_to_kosi = _between(graph, ids["Tomi"], ids["Kosi"], kind="dyad")
    assert [(edge.label, edge.latency) for edge in tomi_to_kosi] == [
        ("ward", timedelta(hours=24))
    ]
    assert _between(graph, ids["Kosi"], ids["Tomi"], kind="dyad") == ()


def test_lone_row_is_sparse_and_handler_override_beats_neutral(
    communication_db: dict[str, Any],
) -> None:
    """No reverse row is invented; handler's 12h override beats neutral 96h."""

    graph = _assemble(communication_db)
    entities = communication_db["entities"]
    lone = _between(
        graph,
        entities["lone_teller"],
        entities["lone_listener"],
        kind="dyad",
    )
    assert [(edge.label, edge.latency) for edge in lone] == [
        ("associate", timedelta(hours=24))
    ]
    assert (
        _between(
            graph,
            entities["lone_listener"],
            entities["lone_teller"],
            kind="dyad",
        )
        == ()
    )
    handler = _between(
        graph,
        entities["neutral_teller"],
        entities["neutral_listener"],
        kind="dyad",
    )
    assert [(edge.label, edge.latency) for edge in handler] == [
        ("handler", timedelta(hours=12))
    ]
    neutral = _between(
        graph,
        entities["plain_neutral_teller"],
        entities["plain_neutral_listener"],
        kind="dyad",
    )
    assert [(edge.label, edge.latency) for edge in neutral] == [
        ("associate", timedelta(hours=96))
    ]
    assert (
        _between(
            graph,
            entities["hostile_teller"],
            entities["hostile_listener"],
            kind="dyad",
        )
        == ()
    )
    reciprocal = _between(
        graph,
        entities["reciprocal_high"],
        entities["reciprocal_low"],
        kind="dyad",
    )
    assert [(edge.label, edge.latency) for edge in reciprocal] == [
        ("captor", timedelta(hours=24))
    ]
    assert (
        _between(
            graph,
            entities["reciprocal_low"],
            entities["reciprocal_high"],
            kind="dyad",
        )
        == ()
    )
    assert all(
        entities["inactive"] not in (edge.teller_entity_id, edge.listener_entity_id)
        for edge in graph.edges
    )


def test_channel_directionality_and_status_minimum(
    communication_db: dict[str, Any],
) -> None:
    """Obligation, authority, handles, and status follow their configured arrows."""

    graph = _assemble(communication_db)
    entities = communication_db["entities"]
    faction = communication_db["faction_entity_id"]

    assert (
        len(_between(graph, entities["creditor"], entities["debtor"], kind="channel"))
        == 1
    )
    assert (
        _between(graph, entities["debtor"], entities["creditor"], kind="channel") == ()
    )
    assert (
        len(
            _between(
                graph,
                entities["authority"],
                entities["subordinate"],
                kind="channel",
            )
        )
        == 1
    )
    assert (
        _between(
            graph,
            entities["subordinate"],
            entities["authority"],
            kind="channel",
        )
        == ()
    )
    assert (
        len(_between(graph, entities["handler"], entities["asset"], kind="channel"))
        == 1
    )
    assert (
        len(_between(graph, entities["asset"], entities["handler"], kind="channel"))
        == 1
    )
    assert len(_between(graph, faction, entities["junior_member"], kind="channel")) == 1
    assert _between(graph, faction, entities["outcast_member"], kind="channel") == ()


def test_faction_subject_status_yields_parent_to_member_faction_edge(
    communication_db: dict[str, Any],
) -> None:
    """PR #517 review: the registry allows faction-subject status standing.

    A member faction holding status toward a parent faction is a legal
    institutional conduit; faction_to_member must emit parent -> member.
    """

    session = communication_db["session"]
    parent_faction = communication_db["faction_entity_id"]
    member_entity_id = int(
        session.execute(
            text(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('faction', true)
                RETURNING id
                """
            )
        ).scalar_one()
    )
    session.execute(
        text(
            """
            INSERT INTO factions (id, name, entity_id)
            VALUES ((SELECT coalesce(max(id), 0) + 1 FROM factions), :name, :entity_id)
            """
        ),
        {
            "name": f"comm-graph-member-{uuid4().hex[:12]}",
            "entity_id": member_entity_id,
        },
    )
    _insert_pair_tag(
        session,
        subject_entity_id=member_entity_id,
        object_entity_id=parent_faction,
        tag="status:senior",
    )

    graph = _assemble(communication_db)
    edges = _between(graph, parent_faction, member_entity_id, kind="channel")
    assert len(edges) == 1
    assert edges[0].label == "status:senior"


def test_culture_profiles_multiply_and_record_provenance(
    communication_db: dict[str, Any],
) -> None:
    """Layered culture tags multiply channel latency and remain auditable."""

    session = communication_db["session"]
    faction = communication_db["faction_entity_id"]
    listener = communication_db["entities"]["culture_listener"]

    baseline = _between(_assemble(communication_db), faction, listener, kind="channel")
    assert [(edge.latency, edge.culture_multiplier) for edge in baseline] == [
        (timedelta(hours=24), 1.0)
    ]

    _insert_culture_tag(session, entity_id=faction, tag="cellular_clandestine")
    quadrupled = _between(
        _assemble(communication_db), faction, listener, kind="channel"
    )
    assert [(edge.latency, edge.culture_multiplier) for edge in quadrupled] == [
        (timedelta(hours=96), 4.0)
    ]

    _insert_culture_tag(session, entity_id=faction, tag="covert")
    composed = _between(_assemble(communication_db), faction, listener, kind="channel")
    assert [(edge.latency, edge.culture_multiplier) for edge in composed] == [
        (timedelta(hours=192), 8.0)
    ]
    assert composed[0].institution_entity_id == faction


def test_assembly_is_deterministic_and_unknown_configured_channel_is_loud(
    communication_db: dict[str, Any],
) -> None:
    """Stable state is equal byte-for-byte; registry drift raises."""

    first = _assemble(communication_db)
    assert first == _assemble(communication_db)
    with communication_db["raw_connection"].cursor() as cur:
        assert first == assemble_communication_graph(
            cur,
            settings=communication_db["settings"],
            world_time=WORLD_TIME,
        )

    payload = communication_db["settings"].model_dump()
    payload["channels"]["unregistered_conduit"] = {
        "direction": "both",
        "latency": "1h",
    }
    drifted = OrreryContagionSettings.model_validate(payload)
    with pytest.raises(ValueError, match="unregistered channel tags"):
        assemble_communication_graph(
            communication_db["session"],
            settings=drifted,
            world_time=WORLD_TIME,
        )


def test_unknown_dyad_override_key_is_loud(
    communication_db: dict[str, Any],
) -> None:
    """PR #517 review: a typo'd or retired override key raises, never falls back.

    Valid keys are the union of the apex RelationshipType enum, template-
    referenced relationship types, and types present in the live data — so
    the shipped captor/handler defaults validate while drift screams.
    """

    payload = communication_db["settings"].model_dump()
    payload["dyad_overrides"]["handeler"] = {
        "forward": "1h",
        "reverse": "1h",
    }
    drifted = OrreryContagionSettings.model_validate(payload)
    with pytest.raises(ValueError, match="unknown relationship types.*handeler"):
        assemble_communication_graph(
            communication_db["session"],
            settings=drifted,
            world_time=WORLD_TIME,
        )


def test_unparseable_relationship_valence_is_loud() -> None:
    """Non-numeric canonical values cannot silently lose an edge."""

    with pytest.raises(ValueError, match="Unparseable valence_current"):
        _valence_tier("friendly")


def test_production_explain_and_entity_audit_share_one_edge_list(
    communication_db: dict[str, Any],
) -> None:
    """Production hydration and both audit views expose identical outbound edges."""

    session = communication_db["session"]
    settings = communication_db["settings"]
    entity_id = communication_db["entities"]["lone_teller"]
    kwargs = {
        "anchor_chunk_id": None,
        "window_chunks": 30,
        "world_time_override": WORLD_TIME,
        "epistemics_settings": {"enabled": False},
        "contagion_settings": settings,
    }
    production = resolve_dry_run(session, (), **kwargs)
    explained = explain_dry_run(session, (), **kwargs)
    assert production.communication_graph == explained.communication_graph

    context = entity_context(
        session,
        [entity_id],
        anchor_chunk_id=None,
        contagion_settings=settings,
    )
    production_edges = [
        edge.to_dict() for edge in production.communication_graph.outbound(entity_id)
    ]
    assert context["entities"][0]["communication_edges"] == production_edges

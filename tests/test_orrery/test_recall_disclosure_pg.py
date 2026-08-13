"""Disposable-PostgreSQL proofs for entitlement-first recall and disclosure."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Mapping, cast
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.memnon.utils.embedding_tables import (
    ensure_character_experience_embedding_table,
    ensure_embedding_table,
)
from nexus.agents.orrery.audit import cognition_trace
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.knowledge_surfacing import build_knowledge_digest_sync
from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.agents.orrery.substrate import ALWAYS, Branch, DriveBand, Slot, Template
from nexus.api import narrative, orrery_dev_endpoints
from nexus.config import load_settings_as_dict


pytestmark = pytest.mark.requires_postgres
ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "migrations" / "106_recall_trace.sql"


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@pytest.fixture(scope="module")
def recall_database() -> Iterator[str]:
    """Clone the template, apply migration 106 twice, and drop the clone."""

    dbname = f"qa678_{uuid4().hex[:12]}"
    source = os.environ.get("NEXUS_TEST_TEMPLATE_DB", "NEXUS_template")
    assert source == "NEXUS_template" or source.startswith("qa678_")
    admin: Any = None
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname), sql.Identifier(source)
                )
            )
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                migration_sql = MIGRATION.read_text()
                cur.execute(migration_sql)
                cur.execute(migration_sql)
        yield dbname
    finally:
        if admin is not None:
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


@pytest.fixture()
def session(recall_database: str) -> Iterator[Session]:
    """Run each proof in a rollback-only transaction in the disposable clone."""

    engine = create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=os.environ.get("PGUSER", "pythagor"),
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5432")),
            database=recall_database,
        ),
        future=True,
    )
    connection = engine.connect()
    transaction = connection.begin()
    test_session = Session(bind=connection)
    try:
        yield test_session
    finally:
        test_session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _chunk(
    session: Session,
    *,
    label: str,
    world_time: datetime,
    scene: int,
) -> int:
    chunk_id = int(
        session.execute(
            text(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text)
                VALUES (:label, :label)
                RETURNING id
                """
            ),
            {"label": label},
        ).scalar_one()
    )
    session.execute(
        text(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer, world_time
            ) VALUES (:chunk_id, 1, 1, :scene, 'primary', :world_time)
            """
        ),
        {"chunk_id": chunk_id, "scene": scene, "world_time": world_time},
    )
    session.execute(
        text(
            "UPDATE chunk_metadata SET world_time = :world_time "
            "WHERE chunk_id = :chunk_id"
        ),
        {"chunk_id": chunk_id, "world_time": world_time},
    )
    return chunk_id


def _character(session: Session, label: str) -> tuple[int, int]:
    entity_id = int(
        session.execute(
            text(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('character', true) RETURNING id"
            )
        ).scalar_one()
    )
    character_id = int(
        session.execute(
            text(
                "INSERT INTO characters (entity_id, name) "
                "VALUES (:entity_id, :name) RETURNING id"
            ),
            {"entity_id": entity_id, "name": f"recall-{label}-{uuid4().hex[:6]}"},
        ).scalar_one()
    )
    return entity_id, character_id


def _place(session: Session, label: str) -> tuple[int, int]:
    entity_id = int(
        session.execute(
            text(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('place', true) RETURNING id"
            )
        ).scalar_one()
    )
    place_id = int(
        session.execute(
            text(
                "INSERT INTO places (entity_id, name, type) "
                "VALUES (:entity_id, :name, 'fixed_location') RETURNING id"
            ),
            {"entity_id": entity_id, "name": f"recall-{label}-{uuid4().hex[:6]}"},
        ).scalar_one()
    )
    return entity_id, place_id


def _faction(session: Session, label: str) -> int:
    entity_id = int(
        session.execute(
            text(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('faction', true) RETURNING id"
            )
        ).scalar_one()
    )
    faction_row_id = int(
        session.execute(
            text("SELECT COALESCE(max(id), 0) + 1 FROM factions")
        ).scalar_one()
    )
    session.execute(
        text(
            "INSERT INTO factions (id, entity_id, name) "
            "VALUES (:id, :entity_id, :name)"
        ),
        {
            "id": faction_row_id,
            "entity_id": entity_id,
            "name": f"recall-{label}-{uuid4().hex[:6]}",
        },
    )
    return entity_id


def _present(
    session: Session, *, chunk_id: int, characters: list[tuple[int, int]]
) -> None:
    for _entity_id, character_id in characters:
        session.execute(
            text(
                """
                INSERT INTO chunk_character_references (
                    chunk_id, character_id, reference
                ) VALUES (:chunk_id, :character_id, 'present')
                """
            ),
            {"chunk_id": chunk_id, "character_id": character_id},
        )


def _claim(
    session: Session,
    *,
    owner_entity_id: int | None,
    chunk_id: int,
    acquired_at: datetime,
    label: str,
    severity: str = "moderate",
    scope: str = "bounded",
    source_tier: str = "participant",
    world_event_id: int | None = None,
) -> tuple[int, int | None]:
    if world_event_id is None:
        event_type = f"qa678_{severity}_{uuid4().hex[:8]}"
        session.execute(
            text(
                """
                INSERT INTO event_types (type, category, severity, description)
                VALUES (
                    :event_type, 'social',
                    CAST(:severity AS event_severity_kind),
                    'Issue 678 rollback-only fixture'
                )
                """
            ),
            {"event_type": event_type, "severity": severity},
        )
        event_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, world_layer, source,
                        changed_fields, payload
                    ) VALUES (
                        :event_type, :chunk_id, 'primary', 'authored', '{}', '{}'
                    ) RETURNING id
                    """
                ),
                {"event_type": event_type, "chunk_id": chunk_id},
            ).scalar_one()
        )
    else:
        event_id = int(world_event_id)
    claim_id = int(
        session.execute(
            text(
                """
                INSERT INTO claims (
                    world_event_id, summary, scope, source_chunk_id,
                    account_label
                ) VALUES (
                    :event_id, :summary, :scope, :chunk_id, :account_label
                ) RETURNING id
                """
            ),
            {
                "event_id": event_id,
                "summary": f"Recall fixture {label}",
                "scope": scope,
                "chunk_id": chunk_id,
                "account_label": f"qa678-{uuid4().hex[:8]}",
            },
        ).scalar_one()
    )
    if owner_entity_id is None:
        return claim_id, None
    awareness_id = int(
        session.execute(
            text(
                """
                INSERT INTO claim_awareness (
                    claim_id, knower_entity_id, source_tier,
                    acquired_at_world_time, source_chunk_id
                ) VALUES (
                    :claim_id, :owner_id, :source_tier,
                    :acquired_at, :chunk_id
                ) RETURNING id
                """
            ),
            {
                "claim_id": claim_id,
                "owner_id": owner_entity_id,
                "source_tier": source_tier,
                "acquired_at": acquired_at,
                "chunk_id": chunk_id,
            },
        ).scalar_one()
    )
    return claim_id, awareness_id


def _experience(
    session: Session,
    *,
    owner_entity_id: int,
    chunk_id: int,
    world_time: datetime,
    label: str,
    invalidated: bool = False,
) -> int:
    event_type = f"qa678_experience_{uuid4().hex[:8]}"
    session.execute(
        text(
            """
            INSERT INTO event_types (type, category, severity, description)
            VALUES (:event_type, 'social', 'moderate', 'Issue 678 experience')
            """
        ),
        {"event_type": event_type},
    )
    event_id = int(
        session.execute(
            text(
                """
                INSERT INTO world_events (
                    event_type, tick_chunk_id, actor_entity_id, world_layer,
                    source, changed_fields, payload
                ) VALUES (
                    :event_type, :chunk_id, :owner_id, 'primary', 'authored',
                    '{}', '{}'
                ) RETURNING id
                """
            ),
            {
                "event_type": event_type,
                "chunk_id": chunk_id,
                "owner_id": owner_entity_id,
            },
        ).scalar_one()
    )
    return int(
        session.execute(
            text(
                """
                INSERT INTO character_experiences (
                    character_entity_id, anchor_chunk_id, world_event_ids,
                    basis, world_time, seed_summary, salience, source_digest,
                    world_layer, invalidation_status, invalidated_at
                ) VALUES (
                    :owner_id, :chunk_id, ARRAY[:event_id]::bigint[],
                    'participant', :world_time, :summary, 0.8, :digest,
                    'primary',
                    CAST(:status AS character_experience_invalidation_status),
                    :invalidated_at
                ) RETURNING id
                """
            ),
            {
                "owner_id": owner_entity_id,
                "chunk_id": chunk_id,
                "event_id": event_id,
                "world_time": world_time,
                "summary": f"Experience fixture {label}",
                "digest": uuid4().hex,
                "status": "invalidated" if invalidated else "valid",
                "invalidated_at": datetime.now(timezone.utc) if invalidated else None,
            },
        ).scalar_one()
    )


def _digest(
    session: Session,
    *,
    present: list[int],
    anchor: int,
    turn_id: str,
    max_entries: int = 12,
    recall: dict[str, Any] | None = None,
    query_embeddings: dict[str, list[float]] | None = None,
) -> list[dict[str, Any]]:
    return build_knowledge_digest_sync(
        session,
        present_entity_ids=present,
        anchor_chunk_id=anchor,
        settings={
            "enabled": True,
            "max_entries": max_entries,
            "recent_reveal_window_chunks": 3,
        },
        recall_settings=recall or {},
        disclosure_settings={},
        turn_id=turn_id,
        query_embeddings=query_embeddings,
    )


def test_cognition_trace_endpoint_rejects_invalid_identifiers(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The gateway returns field-specific 4xx errors for invalid trace ids."""

    base = datetime(2078, 1, 31, tzinfo=timezone.utc)
    anchor = _chunk(session, label="cognition boundary", world_time=base, scene=1)
    actor = _character(session, "cognition-boundary")
    inactive_actor = _character(session, "cognition-inactive")
    session.execute(
        text("UPDATE entities SET is_active = false WHERE id = :entity_id"),
        {"entity_id": inactive_actor[0]},
    )
    orphan_character_entity_id = int(
        session.execute(
            text(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('character', true)
                RETURNING id
                """
            )
        ).scalar_one()
    )
    faction_entity_id = _faction(session, "cognition-boundary")
    missing_metadata_anchor_id = int(
        session.execute(
            text(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text)
                VALUES ('cognition missing metadata', 'cognition missing metadata')
                RETURNING id
                """
            )
        ).scalar_one()
    )
    non_playable_anchor_id = _chunk(
        session,
        label="cognition non-playable",
        world_time=base + timedelta(hours=1),
        scene=2,
    )
    session.execute(
        text(
            """
            UPDATE narrative_chunks
            SET authorial_directives = :authorial_directives
            WHERE id = :chunk_id
            """
        ),
        {
            "authorial_directives": json.dumps([RETROGRADE_PROLOGUE_MARKER]),
            "chunk_id": non_playable_anchor_id,
        },
    )
    missing_entity_id = int(
        session.execute(
            text("SELECT COALESCE(max(id), 0) + 1 FROM entities")
        ).scalar_one()
    )
    missing_anchor_id = int(
        session.execute(
            text("SELECT COALESCE(max(id), 0) + 1 FROM narrative_chunks")
        ).scalar_one()
    )
    session.flush()

    @contextmanager
    def seeded_session(_slot: int | None) -> Iterator[Session]:
        yield session

    monkeypatch.setattr(orrery_dev_endpoints, "_slot_session", seeded_session)

    app = narrative.app
    original_route_count = len(app.router.routes)
    cognition_route_registered = any(
        getattr(route, "path", None) == "/api/dev/orrery/cognition/trace"
        and "POST" in (getattr(route, "methods", None) or set())
        for route in app.router.routes
    )
    if not cognition_route_registered:
        app.include_router(orrery_dev_endpoints.router)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            wrong_kind = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": faction_entity_id,
                    "anchor_chunk_id": anchor,
                },
            )
            unknown_actor = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": missing_entity_id,
                    "anchor_chunk_id": anchor,
                },
            )
            inactive = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": inactive_actor[0],
                    "anchor_chunk_id": anchor,
                },
            )
            orphan_character = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": orphan_character_entity_id,
                    "anchor_chunk_id": anchor,
                },
            )
            unknown_anchor = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": actor[0],
                    "anchor_chunk_id": missing_anchor_id,
                },
            )
            missing_metadata_anchor = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": actor[0],
                    "anchor_chunk_id": missing_metadata_anchor_id,
                },
            )
            non_playable_anchor = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": actor[0],
                    "anchor_chunk_id": non_playable_anchor_id,
                },
            )
            valid = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": actor[0],
                    "anchor_chunk_id": anchor,
                },
            )
            schema_invalid = client.post(
                "/api/dev/orrery/cognition/trace",
                json={
                    "slot": 1,
                    "entity_id": actor[0],
                    "anchor_chunk_id": anchor,
                    "unexpected": True,
                },
            )
    finally:
        if not cognition_route_registered:
            del app.router.routes[original_route_count:]

    assert wrong_kind.status_code == 422
    assert wrong_kind.json() == {
        "detail": (
            f"entity_id={faction_entity_id}: expected an active character, "
            "found entity kind 'faction'"
        )
    }
    assert unknown_actor.status_code == 404
    assert unknown_actor.json() == {
        "detail": f"entity_id={missing_entity_id}: entity does not exist"
    }
    assert inactive.status_code == 422
    assert inactive.json() == {
        "detail": f"entity_id={inactive_actor[0]}: character is inactive"
    }
    assert orphan_character.status_code == 422
    assert orphan_character.json() == {
        "detail": (
            f"entity_id={orphan_character_entity_id}: "
            "character entity has no character record"
        )
    }
    assert unknown_anchor.status_code == 404
    assert unknown_anchor.json() == {
        "detail": (
            f"anchor_chunk_id={missing_anchor_id}: narrative chunk does not exist"
        )
    }
    assert missing_metadata_anchor.status_code == 422
    assert missing_metadata_anchor.json() == {
        "detail": (
            f"anchor_chunk_id={missing_metadata_anchor_id}: "
            "narrative chunk has no timeline metadata"
        )
    }
    assert non_playable_anchor.status_code == 422
    assert non_playable_anchor.json() == {
        "detail": (
            f"anchor_chunk_id={non_playable_anchor_id}: "
            "narrative chunk is not a playable anchor"
        )
    }
    assert valid.status_code == 200, valid.text
    assert valid.json()["entity"]["entity_id"] == actor[0]
    assert valid.json()["anchor"]["chunk_id"] == anchor
    assert schema_invalid.status_code == 422
    assert schema_invalid.json() == {
        "detail": [
            {
                "type": "extra_forbidden",
                "loc": ["body", "unexpected"],
                "msg": "Extra inputs are not permitted",
            }
        ]
    }
    rejection_logs = [
        record
        for record in caplog.records
        if record.name == "nexus.api.orrery_dev_endpoints"
    ]
    assert [record.getMessage() for record in rejection_logs] == [
        (
            "Rejected cognition trace request: "
            f"entity_id={faction_entity_id}: expected an active character, "
            "found entity kind 'faction'"
        ),
        (
            "Rejected cognition trace request: "
            f"entity_id={missing_entity_id}: entity does not exist"
        ),
        (
            "Rejected cognition trace request: "
            f"entity_id={inactive_actor[0]}: character is inactive"
        ),
        (
            "Rejected cognition trace request: "
            f"entity_id={orphan_character_entity_id}: "
            "character entity has no character record"
        ),
        (
            "Rejected cognition trace request: "
            f"anchor_chunk_id={missing_anchor_id}: narrative chunk does not exist"
        ),
        (
            "Rejected cognition trace request: "
            f"anchor_chunk_id={missing_metadata_anchor_id}: "
            "narrative chunk has no timeline metadata"
        ),
        (
            "Rejected cognition trace request: "
            f"anchor_chunk_id={non_playable_anchor_id}: "
            "narrative chunk is not a playable anchor"
        ),
    ]
    assert all(record.exc_info is None for record in rejection_logs)


def test_cognition_trace_endpoint_keeps_canonical_truth_guarded(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dev endpoint links the durable chain without leaking canon."""

    base = datetime(2078, 2, 1, tzinfo=timezone.utc)
    source = _chunk(session, label="cognition source", world_time=base, scene=1)
    anchor = _chunk(
        session,
        label="cognition anchor",
        world_time=base + timedelta(hours=2),
        scene=2,
    )
    alpha = _character(session, "cognition-alpha")
    beta = _character(session, "cognition-beta")

    possessed_claim, awareness_id = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        acquired_at=base,
        label="possessed private account",
        scope="private",
    )
    assert awareness_id is not None
    session.execute(
        text(
            """
            UPDATE claim_awareness
            SET source_tier = 'told',
                immediate_source_entity_id = :source_entity_id,
                root_source_entity_id = :source_entity_id,
                channel = 'message'
            WHERE id = :awareness_id
            """
        ),
        {"source_entity_id": beta[0], "awareness_id": awareness_id},
    )
    world_event_id = int(
        session.execute(
            text("SELECT world_event_id FROM claims WHERE id = :claim_id"),
            {"claim_id": possessed_claim},
        ).scalar_one()
    )
    sibling_claim, _ = _claim(
        session,
        owner_entity_id=None,
        chunk_id=source,
        acquired_at=base,
        label="guarded sibling answer",
        scope="private",
        world_event_id=world_event_id,
    )
    latent_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        acquired_at=base,
        label="guarded latent secret",
        scope="private",
    )
    session.execute(
        text(
            """
            INSERT INTO backstory_secrets (
                claim_id, gate_template_id, holder_entity_id, source_chunk_id
            ) VALUES (
                :claim_id, 'qa680_gate', :holder_entity_id, :source_chunk_id
            )
            """
        ),
        {
            "claim_id": latent_claim,
            "holder_entity_id": alpha[0],
            "source_chunk_id": source,
        },
    )
    experience_id = _experience(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        world_time=base,
        label="actor-owned recollection",
    )

    digest = build_knowledge_digest_sync(
        session,
        present_entity_ids=[alpha[0], beta[0]],
        anchor_chunk_id=anchor,
        settings={
            "enabled": True,
            "max_entries": 12,
            "recent_reveal_window_chunks": 3,
        },
        recall_settings={},
        disclosure_settings={},
        turn_id="qa680-cognition-trace",
    )
    assert any(row.get("experience_id") == experience_id for row in digest)

    session.execute(
        text(
            """
            INSERT INTO character_experience_jobs (
                boundary_chunk_id, scene_end_chunk_id, world_layer,
                boundary_season, boundary_episode, boundary_scene,
                scene_end_season, scene_end_episode, scene_end_scene,
                batch_ordinal, experience_ids, slot, state, attempts,
                last_error, requested_model, source_digest
            ) VALUES (
                :anchor, :source, 'primary', 1, 1, 2, 1, 1, 1, 0,
                ARRAY[:experience_id]::bigint[], 'qa680', 'stale_rejected', 2,
                'boundary timeline is stale', 'qa680-model', 'qa680-job-digest'
            )
            """
        ),
        {"anchor": anchor, "source": source, "experience_id": experience_id},
    )
    session.flush()

    def actor_is_alpha(_state: Any, bindings: Mapping[Slot, Any]) -> bool:
        return bindings.get(Slot.ACTOR) == alpha[0]

    actor_is_alpha.__name__ = "qa680_actor_is_alpha"
    template = Template(
        id="qa680_cognition_probe",
        priority=50,
        drive_band=DriveBand.AFFILIATION,
        blurb="Exercise cognition exposure persistence.",
        required_slots=(Slot.ACTOR,),
        package_gate=actor_is_alpha,
        branches=(
            Branch(
                label="Inspect a private account",
                conditions=ALWAYS,
                narrative_stub="{actor} reviews what they believe happened.",
                magnitude=0.5,
            ),
        ),
    )
    proposal = resolve_dry_run(
        session,
        (template,),
        anchor_chunk_id=anchor,
        window_chunks=3,
        epistemics_settings={"enabled": False},
    )
    assert len(proposal.resolutions) == 1
    assert proposal.resolutions[0].bindings == {"actor": alpha[0]}
    raw_connection = session.connection().connection.driver_connection
    committed = commit_orrery_tick_sync(
        raw_connection,
        proposal,
        tick_chunk_id=anchor,
        prompt_settings={
            "max_rendered_proposals": 1,
            "max_rendered_pressures": 1,
        },
        epistemics_settings={"enabled": False},
    )
    assert committed.resolution_count == 1
    assert committed.prompt_exposure_count == 1
    session.expire_all()

    @contextmanager
    def seeded_session(_slot: int | None) -> Iterator[Session]:
        yield session

    monkeypatch.setattr(orrery_dev_endpoints, "_slot_session", seeded_session)
    app = FastAPI()
    app.include_router(orrery_dev_endpoints.router)
    response = TestClient(app).post(
        "/api/dev/orrery/cognition/trace",
        json={"slot": 1, "entity_id": alpha[0], "anchor_chunk_id": anchor},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    actor = payload["actor_facing"]
    assert (
        actor["possessed_accounts"][0]["possession"]["source_chain"][-1]["entity_id"]
        == alpha[0]
    )
    assert actor["experiences"][0]["source_event_ids"]
    assert {row["decision"] for row in actor["recall_candidates"]} >= {
        "included",
        "suppressed",
    }
    assert any(
        row["blocking_reasons"] == ["secrecy_threshold"]
        for row in actor["disclosure_results"]
    )
    assert actor["prompt_exposure"]["orrery_proposals"][0]["template_id"] == (
        "qa680_cognition_probe"
    )
    assert actor["prompt_exposure"]["knowledge_surfacing"]
    assert actor["experience_jobs"][0]["state"] == "stale_rejected"
    assert actor["experience_jobs"][0]["attempts"] == 2

    actor_json = json.dumps(actor, sort_keys=True)
    assert str(sibling_claim) not in {
        str(row["claim_id"]) for row in actor["possessed_accounts"]
    }
    assert "guarded sibling answer" not in actor_json
    assert "guarded latent secret" not in actor_json
    canonical = payload["canonical_truth"]
    assert canonical["guarded"] is True
    assert sibling_claim in {
        row["claim_id"] for row in canonical["unpossessed_sibling_accounts"]
    }
    assert latent_claim in {row["claim_id"] for row in canonical["latent_secrets"]}


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _nested_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _nested_keys(child)}
    return set()


def test_distorted_account_never_leaks_canonical_event_adjacency(
    session: Session,
) -> None:
    """Possession exposes account content, while event canon stays guarded."""

    base = datetime(2078, 3, 1, tzinfo=timezone.utc)
    source = _chunk(session, label="distorted source", world_time=base, scene=1)
    anchor = _chunk(
        session,
        label="distorted anchor",
        world_time=base + timedelta(hours=1),
        scene=2,
    )
    knower = _character(session, "distorted-knower")
    canonical_actor = _character(session, "distorted-canonical-actor")
    canonical_target = _character(session, "distorted-canonical-target")
    _place_entity_id, canonical_place = _place(session, "distorted-place")
    claim_id, awareness_id = _claim(
        session,
        owner_entity_id=knower[0],
        chunk_id=source,
        acquired_at=base,
        label="distorted account only",
        scope="private",
        source_tier="told",
    )
    assert awareness_id is not None
    event_id = int(
        session.execute(
            text("SELECT world_event_id FROM claims WHERE id = :claim_id"),
            {"claim_id": claim_id},
        ).scalar_one()
    )
    session.execute(
        text(
            """
            UPDATE world_events
            SET actor_entity_id = :actor_id,
                target_entity_id = :target_id,
                location_id = :location_id,
                payload = '{"canonical_detail": "unseen"}'::jsonb
            WHERE id = :event_id
            """
        ),
        {
            "actor_id": canonical_actor[0],
            "target_id": canonical_target[0],
            "location_id": canonical_place,
            "event_id": event_id,
        },
    )
    session.execute(
        text(
            """
            UPDATE claims
            SET summary = 'A masked figure crossed the square.',
                account_label = 'distorted',
                account_payload = '{"heard": "a masked figure crossed the square"}'
            WHERE id = :claim_id
            """
        ),
        {"claim_id": claim_id},
    )
    payload = cognition_trace(
        session,
        knower[0],
        anchor_chunk_id=anchor,
        orrery_settings=load_settings_as_dict()["orrery"],
    )

    actor_facing = payload["actor_facing"]
    forbidden = {"actor_entity_id", "target_entity_id", "location_id"}
    assert not (_nested_keys(actor_facing) & forbidden)
    assert actor_facing["possessed_accounts"][0]["account_label"] == "distorted"
    canonical_event = next(
        row
        for row in payload["canonical_truth"]["source_events"]
        if row["event_id"] == event_id
    )
    assert canonical_event["actor_entity_id"] == canonical_actor[0]
    assert canonical_event["target_entity_id"] == canonical_target[0]
    assert canonical_event["location_id"] == canonical_place


def test_cognition_trace_rolls_awareness_and_secret_status_back_to_anchor(
    session: Session,
) -> None:
    """A later reveal and acquisition do not rewrite a pre-reveal trace."""

    base = datetime(2078, 4, 1, tzinfo=timezone.utc)
    source = _chunk(session, label="rollback source 915", world_time=base, scene=1)
    pre_reveal = _chunk(
        session,
        label="rollback pre-reveal 916",
        world_time=base + timedelta(hours=1),
        scene=2,
    )
    reveal = _chunk(
        session,
        label="rollback reveal 917",
        world_time=base + timedelta(hours=2),
        scene=3,
    )
    knower = _character(session, "rollback-knower")
    secret_claim, _ = _claim(
        session,
        owner_entity_id=knower[0],
        chunk_id=source,
        acquired_at=base,
        label="later revealed secret",
        scope="private",
    )
    session.execute(
        text(
            """
            INSERT INTO backstory_secrets (
                claim_id, gate_template_id, holder_entity_id, source_chunk_id,
                status, revealed_at_world_time, revealed_by_chunk_id
            ) VALUES (
                :claim_id, 'qa680_rollback_gate', :holder_id, :source_chunk_id,
                'revealed', :revealed_at, :revealed_by_chunk_id
            )
            """
        ),
        {
            "claim_id": secret_claim,
            "holder_id": knower[0],
            "source_chunk_id": source,
            "revealed_at": base + timedelta(hours=2),
            "revealed_by_chunk_id": reveal,
        },
    )
    future_claim, _ = _claim(
        session,
        owner_entity_id=knower[0],
        chunk_id=reveal,
        acquired_at=base + timedelta(hours=2),
        label="future acquisition",
        scope="private",
    )
    settings = load_settings_as_dict()["orrery"]

    before = cognition_trace(
        session,
        knower[0],
        anchor_chunk_id=pre_reveal,
        orrery_settings=settings,
    )
    before_claims = {
        row["claim_id"] for row in before["actor_facing"]["possessed_accounts"]
    }
    assert secret_claim not in before_claims
    assert future_claim not in before_claims
    assert secret_claim in {
        row["claim_id"] for row in before["canonical_truth"]["latent_secrets"]
    }

    after = cognition_trace(
        session,
        knower[0],
        anchor_chunk_id=reveal,
        orrery_settings=settings,
    )
    after_claims = {
        row["claim_id"] for row in after["actor_facing"]["possessed_accounts"]
    }
    assert {secret_claim, future_claim} <= after_claims
    assert secret_claim not in {
        row["claim_id"] for row in after["canonical_truth"]["latent_secrets"]
    }


def test_ownership_and_anchor_validity_are_hard_boundaries(session: Session) -> None:
    base = datetime(2078, 1, 1, tzinfo=timezone.utc)
    source = _chunk(session, label="ownership source", world_time=base, scene=1)
    future = _chunk(
        session, label="future source", world_time=base + timedelta(hours=4), scene=3
    )
    anchor = _chunk(
        session, label="ownership anchor", world_time=base + timedelta(hours=2), scene=2
    )
    alpha = _character(session, "ownership-alpha")
    beta = _character(session, "ownership-beta")
    _present(session, chunk_id=anchor, characters=[alpha, beta])
    alpha_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        acquired_at=base,
        label="alpha owned claim",
    )
    unpossessed_claim, _ = _claim(
        session,
        owner_entity_id=None,
        chunk_id=source,
        acquired_at=base,
        label="unpossessed canonical answer",
    )
    sibling_event_id = int(
        session.execute(
            text("SELECT world_event_id FROM claims WHERE id = :claim_id"),
            {"claim_id": unpossessed_claim},
        ).scalar_one()
    )
    possessed_sibling, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        acquired_at=base,
        label="possessed sibling account",
        world_event_id=sibling_event_id,
    )
    latent_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        acquired_at=base,
        label="latent secret",
        scope="private",
    )
    session.execute(
        text(
            """
            INSERT INTO backstory_secrets (
                claim_id, gate_template_id, holder_entity_id,
                source_chunk_id
            ) VALUES (
                :claim_id, 'qa678-never-reveal', :holder_id, :chunk_id
            )
            """
        ),
        {
            "claim_id": latent_claim,
            "holder_id": alpha[0],
            "chunk_id": source,
        },
    )
    valid_experience = _experience(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        world_time=base,
        label="alpha owned",
    )
    invalid_experience = _experience(
        session,
        owner_entity_id=beta[0],
        chunk_id=source,
        world_time=base,
        label="invalidated",
        invalidated=True,
    )
    future_experience = _experience(
        session,
        owner_entity_id=alpha[0],
        chunk_id=future,
        world_time=base + timedelta(hours=4),
        label="future timeline",
    )

    digest = _digest(
        session,
        present=[alpha[0], beta[0]],
        anchor=anchor,
        turn_id="ownership-boundary",
    )
    assert {entry.get("claim_id") for entry in digest} == {
        alpha_claim,
        possessed_sibling,
        None,
    }
    assert {entry.get("experience_id") for entry in digest} == {
        valid_experience,
        None,
    }
    assert unpossessed_claim not in {entry.get("claim_id") for entry in digest}
    assert latent_claim not in {entry.get("claim_id") for entry in digest}
    assert invalid_experience not in {entry.get("experience_id") for entry in digest}
    assert future_experience not in {entry.get("experience_id") for entry in digest}
    assert {entry["character_entity_id"] for entry in digest} == {alpha[0]}
    semantic_status = session.execute(
        text(
            "SELECT score_components ->> 'semantic_status' "
            "FROM orrery_recall_trace "
            "WHERE turn_id = 'ownership-boundary' "
            "AND candidate_kind = 'experience' AND candidate_id = :experience_id"
        ),
        {"experience_id": valid_experience},
    ).scalar_one()
    assert semantic_status == "skipped_no_query_embedding"
    raw_connection = session.connection().connection.driver_connection
    assert raw_connection is not None
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor_digest = build_knowledge_digest_sync(
            cursor,
            present_entity_ids=[alpha[0], beta[0]],
            anchor_chunk_id=anchor,
            settings={
                "enabled": True,
                "max_entries": 12,
                "recent_reveal_window_chunks": 3,
            },
            recall_settings={},
            disclosure_settings={},
            turn_id="ownership-boundary-cursor",
        )
    assert cursor_digest == digest


def test_critical_current_scene_account_bypasses_ranking(session: Session) -> None:
    base = datetime(2078, 2, 1, tzinfo=timezone.utc)
    old = _chunk(session, label="mandatory old", world_time=base, scene=1)
    anchor = _chunk(
        session, label="mandatory anchor", world_time=base + timedelta(hours=1), scene=2
    )
    alpha = _character(session, "mandatory")
    _present(session, chunk_id=anchor, characters=[alpha])
    old_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=old,
        acquired_at=base,
        label="high involvement old",
        severity="major",
        source_tier="participant",
    )
    critical_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=anchor,
        acquired_at=base + timedelta(hours=1),
        label="critical granted now",
        severity="critical",
        source_tier="granted",
    )

    digest = _digest(
        session,
        present=[alpha[0]],
        anchor=anchor,
        turn_id="mandatory-bypass",
        max_entries=1,
        recall={
            "per_character_max_entries": 1,
            "mandatory_reserved_entries": 1,
            "semantic_fit_weight": 0.0,
            "event_severity_weight": 0.0,
            "actor_involvement_weight": 1.0,
            "emotional_salience_weight": 0.0,
            "recency_weight": 0.0,
            "place_match_weight": 0.0,
        },
    )

    assert [entry["claim_id"] for entry in digest] == [critical_claim]
    trace = session.execute(
        text(
            """
            SELECT claim_id, decision, reason, mandatory
            FROM orrery_recall_trace
            WHERE turn_id = 'mandatory-bypass'
            ORDER BY claim_id
            """
        )
    ).mappings()
    by_claim = {int(row["claim_id"]): dict(row) for row in trace}
    assert by_claim[critical_claim]["mandatory"] is True
    assert by_claim[critical_claim]["decision"] == "included"
    assert by_claim[old_claim]["decision"] == "excluded"


def test_world_clock_decay_lowers_rank_without_mutating_possession(
    session: Session,
) -> None:
    base = datetime(2078, 3, 1, tzinfo=timezone.utc)
    old = _chunk(session, label="decay old", world_time=base, scene=1)
    recent = _chunk(
        session, label="decay recent", world_time=base + timedelta(hours=90), scene=2
    )
    anchor = _chunk(
        session, label="decay anchor", world_time=base + timedelta(hours=100), scene=3
    )
    alpha = _character(session, "decay")
    _present(session, chunk_id=anchor, characters=[alpha])
    old_claim, old_awareness = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=old,
        acquired_at=base,
        label="old memory",
    )
    recent_claim, recent_awareness = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=recent,
        acquired_at=base + timedelta(hours=90),
        label="recent memory",
    )

    digest = _digest(
        session,
        present=[alpha[0]],
        anchor=anchor,
        turn_id="decay-rank",
        max_entries=1,
        recall={
            "per_character_max_entries": 1,
            "mandatory_reserved_entries": 0,
            "decay_half_life_hours": 10.0,
        },
    )

    assert [entry["claim_id"] for entry in digest] == [recent_claim]
    scores: dict[int, float] = {
        int(row[0]): float(row[1])
        for row in session.execute(
            text(
                "SELECT claim_id, score FROM orrery_recall_trace "
                "WHERE turn_id = 'decay-rank'"
            )
        ).all()
    }
    assert scores[recent_claim] > scores[old_claim]
    awareness_ids = set(
        session.execute(
            text("SELECT id FROM claim_awareness " "WHERE id = ANY(:awareness_ids)"),
            {"awareness_ids": [old_awareness, recent_awareness]},
        ).scalars()
    )
    assert awareness_ids == {old_awareness, recent_awareness}


def test_claim_rank_is_invariant_to_unpossessed_sibling_secret(
    session: Session,
) -> None:
    base = datetime(2078, 3, 15, tzinfo=timezone.utc)
    source = _chunk(session, label="distorted source", world_time=base, scene=1)
    anchor = _chunk(session, label="claim invariance anchor", world_time=base, scene=2)
    alpha = _character(session, "claim-invariance")
    _present(session, chunk_id=anchor, characters=[alpha])
    distorted_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        acquired_at=base,
        label="distorted possessed account",
    )
    world_event_id = int(
        session.execute(
            text("SELECT world_event_id FROM claims WHERE id = :claim_id"),
            {"claim_id": distorted_claim},
        ).scalar_one()
    )
    _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=source,
        acquired_at=base,
        label="possessed comparison account",
    )
    table_name = ensure_embedding_table(session.connection(), 2)
    session.execute(
        text(
            f"""
            INSERT INTO {table_name} (chunk_id, model, embedding)
            VALUES (:source, 'qa678', '[1,0]'::vector(2))
            """
        ),
        {"source": source},
    )

    before_digest = _digest(
        session,
        present=[alpha[0]],
        anchor=anchor,
        turn_id="claim-invariance-before",
        query_embeddings={"qa678": [1.0, 0.0]},
    )
    before_trace = (
        session.execute(
            text(
                "SELECT score, score_components FROM orrery_recall_trace "
                "WHERE turn_id = 'claim-invariance-before' AND claim_id = :claim_id"
            ),
            {"claim_id": distorted_claim},
        )
        .mappings()
        .one()
    )
    before_rank = [entry.get("claim_id") for entry in before_digest].index(
        distorted_claim
    )
    before_bytes = json.dumps(
        {
            "rank": before_rank,
            "score": str(before_trace["score"]),
            "components": before_trace["score_components"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    secret_claim, _ = _claim(
        session,
        owner_entity_id=None,
        chunk_id=source,
        acquired_at=base,
        label="unpossessed sibling secret",
        scope="private",
        world_event_id=world_event_id,
    )
    session.execute(
        text(
            f"UPDATE {table_name} SET embedding = '[0,1]'::vector(2) "
            "WHERE chunk_id = :source AND model = 'qa678'"
        ),
        {"source": source},
    )
    after_digest = _digest(
        session,
        present=[alpha[0]],
        anchor=anchor,
        turn_id="claim-invariance-after",
        query_embeddings={"qa678": [1.0, 0.0]},
    )
    after_trace = (
        session.execute(
            text(
                "SELECT score, score_components FROM orrery_recall_trace "
                "WHERE turn_id = 'claim-invariance-after' AND claim_id = :claim_id"
            ),
            {"claim_id": distorted_claim},
        )
        .mappings()
        .one()
    )
    after_rank = [entry.get("claim_id") for entry in after_digest].index(
        distorted_claim
    )
    after_bytes = json.dumps(
        {
            "rank": after_rank,
            "score": str(after_trace["score"]),
            "components": after_trace["score_components"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert secret_claim not in {entry.get("claim_id") for entry in after_digest}
    assert before_bytes == after_bytes
    assert after_trace["score_components"]["semantic_fit"] is None
    assert after_trace["score_components"]["semantic_status"] == "not_applicable_claim"


class _TurnMemnonHarness:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.query_embedding_ids: list[int] = []

    @contextmanager
    def Session(self) -> Iterator[Session]:
        yield self.session

    def query_memory(
        self,
        query: str,
        k: int,
        use_hybrid: bool,
        query_embeddings: dict[str, list[float]],
        **_kwargs: Any,
    ) -> dict[str, list[dict[str, Any]]]:
        assert k == 15
        assert use_hybrid is True
        self.query_embedding_ids.append(id(query_embeddings))
        query_embeddings["qa678"] = [1.0, 0.0] if "fire" in query else [0.0, 1.0]
        return {"results": []}


class _TurnLoreHarness:
    token_manager = None
    memory_manager = None
    enable_logon = False

    def __init__(self, session: Session) -> None:
        self.memnon = _TurnMemnonHarness(session)
        self.settings = {
            "Agent Settings": {
                "LORE": {
                    "token_budget": {
                        "apex_context_window": 75_000,
                        "prompt_overhead_tokens": 4_000,
                    }
                },
                "MEMNON": {
                    "retrieval": {"hybrid_search": {"presence_boost_enabled": False}}
                },
            },
            "orrery": {
                "enabled": True,
                "bleed": {"max_candidates": 0},
                "knowledge": {
                    "enabled": True,
                    "max_entries": 1,
                    "recent_reveal_window_chunks": 3,
                },
                "recall": {
                    "semantic_fit_weight": 1.0,
                    "event_severity_weight": 0.0,
                    "actor_involvement_weight": 0.0,
                    "emotional_salience_weight": 0.0,
                    "recency_weight": 0.0,
                    "place_match_weight": 0.0,
                    "per_character_max_entries": 1,
                    "mandatory_reserved_entries": 0,
                },
            },
        }


def test_turn_inputs_change_experience_ranking_via_shared_query_embedding(
    session: Session,
) -> None:
    base = datetime(2078, 3, 20, tzinfo=timezone.utc)
    fire_source = _chunk(session, label="fire experience", world_time=base, scene=1)
    harbor_source = _chunk(session, label="harbor experience", world_time=base, scene=2)
    anchor = _chunk(session, label="turn semantic anchor", world_time=base, scene=3)
    alpha = _character(session, "turn-semantic")
    _present(session, chunk_id=anchor, characters=[alpha])
    fire_experience = _experience(
        session,
        owner_entity_id=alpha[0],
        chunk_id=fire_source,
        world_time=base,
        label="fire memory",
    )
    harbor_experience = _experience(
        session,
        owner_entity_id=alpha[0],
        chunk_id=harbor_source,
        world_time=base,
        label="harbor memory",
    )
    table_name = ensure_character_experience_embedding_table(session.connection(), 2)
    session.execute(
        text(
            f"""
            INSERT INTO {table_name} (experience_id, model, embedding)
            VALUES
                (:fire, 'qa678', '[1,0]'::vector(2)),
                (:harbor, 'qa678', '[0,1]'::vector(2))
            """
        ),
        {"fire": fire_experience, "harbor": harbor_experience},
    )
    lore = _TurnLoreHarness(session)
    manager = TurnCycleManager(lore)

    selected: list[int] = []
    for turn_id, user_input in (
        ("turn-semantic-fire", "Recall the fire at the gate."),
        ("turn-semantic-harbor", "Recall the harbor at dawn."),
    ):
        context = TurnContext(
            turn_id=turn_id,
            user_input=user_input,
            start_time=0,
            warm_slice=[
                {
                    "id": anchor,
                    "is_target": True,
                    "full_text": "The same current scene anchor for both turns.",
                }
            ],
        )
        context.token_counts = {"total_available": 75_000}
        context.orrery_proposal = cast(
            Any,
            SimpleNamespace(
                anchor_chunk_id=anchor,
                pressure_count=0,
                resolution_count=0,
                joint_beats=(),
            ),
        )

        asyncio.run(manager.execute_deep_queries(context))
        shared_mapping_id = id(context.recall_query_embeddings)
        asyncio.run(manager.assemble_context_payload(context))

        assert shared_mapping_id == lore.memnon.query_embedding_ids[-1]
        entry = context.context_payload["world_knowledge"][0]
        selected.append(int(entry["experience_id"]))
        semantic_trace = session.execute(
            text(
                "SELECT score_components ->> 'semantic_status' "
                "FROM orrery_recall_trace "
                "WHERE turn_id = :turn_id AND candidate_kind = 'experience' "
                "AND candidate_id = :candidate_id"
            ),
            {"turn_id": turn_id, "candidate_id": entry["experience_id"]},
        ).scalar_one()
        assert semantic_trace == "scored"

    assert selected == [fire_experience, harbor_experience]


def test_disclosure_suppression_is_logged_and_not_surfaced(session: Session) -> None:
    base = datetime(2078, 4, 1, tzinfo=timezone.utc)
    anchor = _chunk(session, label="disclosure anchor", world_time=base, scene=1)
    alpha = _character(session, "secret-holder")
    beta = _character(session, "neutral-audience")
    _present(session, chunk_id=anchor, characters=[alpha, beta])
    private_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=anchor,
        acquired_at=base,
        label="private but possessed",
        scope="private",
    )

    digest = _digest(
        session,
        present=[alpha[0], beta[0]],
        anchor=anchor,
        turn_id="disclosure-suppression",
    )

    assert private_claim not in {entry.get("claim_id") for entry in digest}
    trace = (
        session.execute(
            text(
                """
            SELECT decision, reason, score_components
            FROM orrery_recall_trace
            WHERE turn_id = 'disclosure-suppression'
              AND claim_id = :claim_id
            """
            ),
            {"claim_id": private_claim},
        )
        .mappings()
        .one()
    )
    assert trace["decision"] == "suppressed"
    assert trace["reason"] == "secrecy_threshold"
    assert trace["score_components"]["disclosure"]["secrecy_marker"] == 1.0
    assert (
        session.execute(
            text("SELECT count(*) FROM claim_awareness WHERE claim_id = :claim_id"),
            {"claim_id": private_claim},
        ).scalar_one()
        == 1
    )


def test_role_obligation_suppresses_unauthorized_audience(session: Session) -> None:
    base = datetime(2078, 4, 15, tzinfo=timezone.utc)
    anchor = _chunk(session, label="obligation anchor", world_time=base, scene=1)
    alpha = _character(session, "obligated-holder")
    beta = _character(session, "outside-audience")
    faction_id = _faction(session, "protected-faction")
    _present(session, chunk_id=anchor, characters=[alpha, beta])
    bounded_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=anchor,
        acquired_at=base,
        label="faction-bound briefing",
    )
    obligation_tag_id = int(
        session.execute(
            text("SELECT id FROM pair_tags WHERE tag = 'obligation'")
        ).scalar_one()
    )
    session.execute(
        text(
            """
            INSERT INTO entity_pair_tags (
                subject_entity_id, object_entity_id, pair_tag_id,
                source_kind
            ) VALUES (
                :owner_id, :faction_id, :tag_id, 'authored'
            )
            """
        ),
        {
            "owner_id": alpha[0],
            "faction_id": faction_id,
            "tag_id": obligation_tag_id,
        },
    )

    digest = _digest(
        session,
        present=[alpha[0], beta[0]],
        anchor=anchor,
        turn_id="role-obligation-suppression",
    )

    assert bounded_claim not in {entry.get("claim_id") for entry in digest}
    trace = (
        session.execute(
            text(
                """
                SELECT decision, reason, score_components
                FROM orrery_recall_trace
                WHERE turn_id = 'role-obligation-suppression'
                  AND claim_id = :claim_id
                """
            ),
            {"claim_id": bounded_claim},
        )
        .mappings()
        .one()
    )
    assert trace["decision"] == "suppressed"
    assert trace["reason"] == "role_obligation_threshold"
    assert trace["score_components"]["disclosure"]["role_obligation_risk"] == 1.0


def test_trust_and_shared_status_can_disclose_private_claim(session: Session) -> None:
    base = datetime(2078, 4, 20, tzinfo=timezone.utc)
    anchor = _chunk(session, label="trusted anchor", world_time=base, scene=1)
    alpha = _character(session, "trusted-holder")
    beta = _character(session, "trusted-audience")
    faction_id = _faction(session, "shared-faction")
    _present(session, chunk_id=anchor, characters=[alpha, beta])
    private_claim, _ = _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=anchor,
        acquired_at=base,
        label="trusted private briefing",
        scope="private",
    )
    session.execute(
        text(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, valence_current, dynamic,
                recent_events, history
            ) VALUES (
                :alpha_id, :beta_id, 'confidant', '+5|devoted', 0.84,
                'Trusted disclosure fixture.', 'None.', 'Issue 678.'
            )
            """
        ),
        {"alpha_id": alpha[1], "beta_id": beta[1]},
    )
    for character in (alpha, beta):
        session.execute(
            text(
                """
                INSERT INTO entity_pair_tags (
                    subject_entity_id, object_entity_id, pair_tag_id,
                    source_kind
                )
                SELECT :character_id, :faction_id, pair_tag.id, 'authored'
                FROM pair_tags pair_tag
                WHERE pair_tag.tag = 'status:senior'
                  AND NOT pair_tag.deprecated
                """
            ),
            {"character_id": character[0], "faction_id": faction_id},
        )

    digest = _digest(
        session,
        present=[alpha[0], beta[0]],
        anchor=anchor,
        turn_id="trusted-private-disclosure",
    )

    assert private_claim in {entry.get("claim_id") for entry in digest}
    disclosure = session.execute(
        text(
            """
            SELECT score_components -> 'disclosure'
            FROM orrery_recall_trace
            WHERE turn_id = 'trusted-private-disclosure'
              AND claim_id = :claim_id
            """
        ),
        {"claim_id": private_claim},
    ).scalar_one()
    assert disclosure["relationship_valence"] == pytest.approx(0.84)
    assert disclosure["status_edge_match"] == pytest.approx(1.0)


def test_per_character_cap_preserves_shared_budget_for_other_actors(
    session: Session,
) -> None:
    base = datetime(2078, 5, 1, tzinfo=timezone.utc)
    anchor = _chunk(session, label="budget anchor", world_time=base, scene=1)
    alpha = _character(session, "budget-alpha")
    beta = _character(session, "budget-beta")
    _present(session, chunk_id=anchor, characters=[alpha, beta])
    for index in range(3):
        _claim(
            session,
            owner_entity_id=alpha[0],
            chunk_id=anchor,
            acquired_at=base,
            label=f"alpha-{index}",
        )
    beta_claim, _ = _claim(
        session,
        owner_entity_id=beta[0],
        chunk_id=anchor,
        acquired_at=base,
        label="beta-only",
    )

    digest = _digest(
        session,
        present=[alpha[0], beta[0]],
        anchor=anchor,
        turn_id="per-character-budget",
        max_entries=3,
        recall={
            "per_character_max_entries": 1,
            "mandatory_reserved_entries": 0,
        },
    )

    assert len(digest) == 2
    assert {entry["character_entity_id"] for entry in digest} == {
        alpha[0],
        beta[0],
    }
    assert beta_claim in {entry.get("claim_id") for entry in digest}
    excluded = session.execute(
        text(
            """
            SELECT count(*)
            FROM orrery_recall_trace
            WHERE turn_id = 'per-character-budget'
              AND character_entity_id = :alpha
              AND decision = 'excluded'
              AND reason = 'per_character_cap'
            """
        ),
        {"alpha": alpha[0]},
    ).scalar_one()
    assert excluded == 2


def test_trace_retention_prunes_oldest_rows_per_character(session: Session) -> None:
    base = datetime(2078, 6, 1, tzinfo=timezone.utc)
    anchor = _chunk(session, label="retention anchor", world_time=base, scene=1)
    alpha = _character(session, "retention")
    _present(session, chunk_id=anchor, characters=[alpha])
    _claim(
        session,
        owner_entity_id=alpha[0],
        chunk_id=anchor,
        acquired_at=base,
        label="retained knowledge",
    )

    for turn_id in ("retention-1", "retention-2", "retention-3"):
        _digest(
            session,
            present=[alpha[0]],
            anchor=anchor,
            turn_id=turn_id,
            recall={"trace_rows_per_character": 2},
        )

    retained_turns = list(
        session.execute(
            text(
                """
                SELECT turn_id
                FROM orrery_recall_trace
                WHERE character_entity_id = :alpha
                ORDER BY id
                """
            ),
            {"alpha": alpha[0]},
        ).scalars()
    )
    assert retained_turns == ["retention-2", "retention-3"]

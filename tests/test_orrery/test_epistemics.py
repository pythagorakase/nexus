"""Epistemics v1 claims, producers, and the first knower-gated package."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Iterator
import uuid

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.epistemics import (
    ClaimParticipant,
    coerce_epistemics_policy,
    mechanical_claim_summary,
    mint_claim_for_event,
    promote_claim_scope,
    record_revelation,
)
from nexus.agents.orrery.events import commit_orrery_tick_async, commit_orrery_tick_sync
from nexus.agents.orrery.explain import ConditionTrace, trace_condition
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
    hydrate_world_state,
)
from nexus.agents.orrery.retrograde_expansion import (
    RetrogradeExpansionEventPlan,
    RetrogradeExpansionParticipant,
)
from nexus.agents.orrery.retrograde_persistence import (
    _EntityRecord,
    _mint_retrograde_event_claim,
    _plan_event_row,
)
from nexus.agents.orrery.retrograde_vocabulary import normalize_entity_ref
from nexus.agents.orrery.substrate import (
    EventRecord,
    Slot,
    WorldState,
    knows_recent_event,
    recent_event,
)
from nexus.agents.orrery.templates import SURVEIL
from nexus.api.slot_utils import get_slot_db_url
from nexus.config.settings_models import OrreryEpistemicsSettings


EPISTEMICS = {
    "enabled": True,
    "claim_event_types": ["threat_issued"],
    "aware_roles": ["actor", "target", "observer", "witness"],
}
DISABLED = {**EPISTEMICS, "enabled": False}


@pytest.fixture
def save_02_conn() -> Iterator[Any]:
    """Real slot-2 transaction; every test rolls back all fixture writes."""

    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _anchor_and_characters(
    cur: Any, count: int = 4
) -> tuple[int, list[dict[str, Any]]]:
    cur.execute("SELECT max(id) AS id FROM narrative_chunks")
    anchor = int(cur.fetchone()["id"])
    cur.execute(
        """
        SELECT c.id AS character_id, c.entity_id, env.name
        FROM characters c
        JOIN entity_names_v env ON env.id = c.entity_id
        WHERE c.entity_id IS NOT NULL
        ORDER BY c.id
        LIMIT %s
        """,
        (count,),
    )
    characters = [dict(row) for row in cur.fetchall()]
    assert len(characters) == count, f"save_02 requires {count} character entities"
    return anchor, characters


def _insert_event(
    cur: Any,
    *,
    anchor: int,
    event_type: str,
    actor: int,
    target: int,
) -> int:
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload
        ) VALUES (%s, %s, %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb)
        RETURNING id
        """,
        (event_type, anchor, actor, target),
    )
    return int(cur.fetchone()["id"])


def _leaf_evidence(trace: ConditionTrace, kind: str) -> list[dict[str, Any]]:
    if trace.op is None:
        evidence = dict(trace.evidence or {})
        return [evidence] if evidence.get("kind") == kind else []
    return [
        evidence for child in trace.children for evidence in _leaf_evidence(child, kind)
    ]


@pytest.mark.requires_postgres
def test_two_similar_actors_are_separated_only_by_awareness(save_02_conn: Any) -> None:
    """A bounded threat opens SURVEIL only for the actor who knows it."""

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        anchor, characters = _anchor_and_characters(cur, 3)
        aware_actor, unaware_actor, target = [
            int(character["entity_id"]) for character in characters
        ]
        event_id = _insert_event(
            cur,
            anchor=anchor,
            event_type="threat_issued",
            actor=aware_actor,
            target=target,
        )
        participants = (
            ClaimParticipant(aware_actor, "actor", characters[0]["name"]),
            ClaimParticipant(target, "target", characters[2]["name"]),
        )
        minted = mint_claim_for_event(
            cur,
            world_event_id=event_id,
            event_type="threat_issued",
            summary=mechanical_claim_summary("threat_issued", participants),
            participants=participants,
            source_chunk_id=anchor,
            source_resolution_id=None,
            settings=EPISTEMICS,
        )
        assert minted is not None

    state = WorldState(
        locations={aware_actor: 1, unaware_actor: 1, target: 1},
        recent_events=(
            EventRecord(
                event_id=event_id,
                event_type="threat_issued",
                tick=anchor,
                actor_entity_id=aware_actor,
                target_entity_id=target,
            ),
        ),
        claimed_event_scopes={event_id: "bounded"},
        awareness_by_entity={aware_actor: frozenset({event_id})},
        epistemics_enabled=True,
        current_tick=anchor,
    )
    aware_bindings = {Slot.ACTOR: aware_actor, Slot.TARGET: target}
    unaware_bindings = {Slot.ACTOR: unaware_actor, Slot.TARGET: target}
    assert SURVEIL.package_gate(state, aware_bindings) is True
    assert SURVEIL.package_gate(state, unaware_bindings) is False

    aware_trace = trace_condition(SURVEIL.package_gate, state, aware_bindings)
    unaware_trace = trace_condition(SURVEIL.package_gate, state, unaware_bindings)
    aware_evidence = _leaf_evidence(aware_trace, "knows_recent_event")
    unaware_evidence = _leaf_evidence(unaware_trace, "knows_recent_event")
    assert aware_evidence[0]["observed"]["reason"] == (
        f"eligible because actor holds awareness of event {event_id}"
    )
    assert unaware_evidence[0]["observed"]["reason"] == (
        f"blocked: claim on event {event_id} not known to actor"
    )


@pytest.mark.requires_postgres
def test_retrograde_producer_mints_role_correct_awareness(save_02_conn: Any) -> None:
    """Configured Retrograde events mint; beneficiary and other types do not."""

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        anchor, characters = _anchor_and_characters(cur, 4)
        records = [
            _EntityRecord(
                entity_id=int(row["entity_id"]),
                entity_kind="character",
                name=str(row["name"]),
                character_id=int(row["character_id"]),
                faction_id=None,
                place_id=None,
            )
            for row in characters
        ]
        entity_index = {
            ("character", normalize_entity_ref(record.name)): [record]
            for record in records
        }

        def plan(event_type: str) -> dict[str, Any]:
            event = RetrogradeExpansionEventPlan(
                event_ref=f"epistemics_{event_type}_{uuid.uuid4().hex}",
                seed_ids=["seed_epistemics"],
                event_type=event_type,
                summary="Fixture prose is not used as the claim summary.",
                chronology="recent_past",
                participants=[
                    RetrogradeExpansionParticipant(
                        entity_ref=records[0].name,
                        entity_kind="character",
                        role="actor",
                    ),
                    RetrogradeExpansionParticipant(
                        entity_ref=records[1].name,
                        entity_kind="character",
                        role="target",
                    ),
                    RetrogradeExpansionParticipant(
                        entity_ref=records[2].name,
                        entity_kind="character",
                        role="witness",
                    ),
                    RetrogradeExpansionParticipant(
                        entity_ref=records[3].name,
                        entity_kind="character",
                        role="beneficiary",
                    ),
                ],
            )
            return _plan_event_row(
                cur,
                event,
                dry_run=False,
                prologue_chunk_id=anchor,
                entity_index=entity_index,
                event_types={"threat_issued", "surveillance_performed"},
                event_source_available=True,
                creatable_refs=frozenset(),
                epistemics_settings=EPISTEMICS,
            )

        configured = plan("threat_issued")
        assert configured["claim_id"] is not None
        cur.execute(
            """
            SELECT character_entity_id, source_tier
            FROM claim_awareness
            WHERE claim_id = %s
            ORDER BY character_entity_id
            """,
            (configured["claim_id"],),
        )
        awareness = {
            int(row["character_entity_id"]): row["source_tier"]
            for row in cur.fetchall()
        }
        assert awareness == {
            records[0].entity_id: "participant",
            records[1].entity_id: "participant",
            records[2].entity_id: "witness",
        }

        unconfigured = plan("surveillance_performed")
        assert unconfigured["claim_id"] is None
        cur.execute(
            "SELECT count(*) AS count FROM claims WHERE world_event_id = %s",
            (unconfigured["world_event_id"],),
        )
        assert cur.fetchone()["count"] == 0


@pytest.mark.requires_postgres
def test_retrograde_faction_actor_mints_without_faction_awareness(
    save_02_conn: Any,
) -> None:
    """A faction can act in claim prose but cannot hold awareness in v1."""

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        anchor, characters = _anchor_and_characters(cur, 2)
        cur.execute(
            """
            SELECT f.id AS faction_id, f.entity_id, env.name
            FROM factions f
            JOIN entity_names_v env ON env.id = f.entity_id
            WHERE f.entity_id IS NOT NULL
            ORDER BY f.id
            LIMIT 1
            """
        )
        faction = cur.fetchone()
        assert faction is not None, "save_02 requires one faction entity"
        records = [
            _EntityRecord(
                entity_id=int(faction["entity_id"]),
                entity_kind="faction",
                name=str(faction["name"]),
                character_id=None,
                faction_id=int(faction["faction_id"]),
                place_id=None,
            ),
            *[
                _EntityRecord(
                    entity_id=int(row["entity_id"]),
                    entity_kind="character",
                    name=str(row["name"]),
                    character_id=int(row["character_id"]),
                    faction_id=None,
                    place_id=None,
                )
                for row in characters
            ],
        ]
        entity_index = {
            (record.entity_kind, normalize_entity_ref(record.name)): [record]
            for record in records
        }
        result = _plan_event_row(
            cur,
            RetrogradeExpansionEventPlan(
                event_ref=f"epistemics_faction_threat_{uuid.uuid4().hex}",
                seed_ids=["seed_epistemics_faction"],
                event_type="threat_issued",
                summary="The faction threatens a character.",
                chronology="recent_past",
                participants=[
                    RetrogradeExpansionParticipant(
                        entity_ref=records[0].name,
                        entity_kind="faction",
                        role="actor",
                    ),
                    RetrogradeExpansionParticipant(
                        entity_ref=records[1].name,
                        entity_kind="character",
                        role="target",
                    ),
                    RetrogradeExpansionParticipant(
                        entity_ref=records[2].name,
                        entity_kind="character",
                        role="witness",
                    ),
                ],
            ),
            dry_run=False,
            prologue_chunk_id=anchor,
            entity_index=entity_index,
            event_types={"threat_issued"},
            event_source_available=True,
            creatable_refs=frozenset(),
            epistemics_settings=EPISTEMICS,
        )
        assert result["status"] == "inserted"
        assert result["claim_id"] is not None
        cur.execute(
            """
            SELECT c.summary, ca.character_entity_id, ca.source_tier
            FROM claims c
            LEFT JOIN claim_awareness ca ON ca.claim_id = c.id
            WHERE c.id = %s
            ORDER BY ca.character_entity_id
            """,
            (result["claim_id"],),
        )
        rows = cur.fetchall()
        assert rows[0]["summary"] == (
            f"Threat issued: actor {records[0].name}, target {records[1].name}, "
            f"witness {records[2].name}."
        )
        awareness = {
            int(row["character_entity_id"]): row["source_tier"] for row in rows
        }
        assert records[0].entity_id not in awareness
        assert awareness == {
            records[1].entity_id: "participant",
            records[2].entity_id: "witness",
        }


@pytest.mark.requires_postgres
def test_retrograde_claim_mint_skips_events_without_resolved_participants(
    save_02_conn: Any,
) -> None:
    """An otherwise configured event with no subject is a legitimate no-op."""

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT count(*) AS count FROM claims")
        before = int(cur.fetchone()["count"])
        assert (
            _mint_retrograde_event_claim(
                cur,
                world_event_id=7,
                event_type="threat_issued",
                participant_results=(),
                source_chunk_id=None,
                epistemics_settings=EPISTEMICS,
            )
            is None
        )
        cur.execute("SELECT count(*) AS count FROM claims")
        assert int(cur.fetchone()["count"]) == before


@pytest.mark.requires_postgres
def test_retrograde_already_present_event_backfills_claim(
    save_02_conn: Any,
) -> None:
    """Execute-time idempotency backfills a missing claim on an existing event."""

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        anchor, characters = _anchor_and_characters(cur, 2)
        records = [
            _EntityRecord(
                entity_id=int(row["entity_id"]),
                entity_kind="character",
                name=str(row["name"]),
                character_id=int(row["character_id"]),
                faction_id=None,
                place_id=None,
            )
            for row in characters
        ]
        entity_index = {
            ("character", normalize_entity_ref(record.name)): [record]
            for record in records
        }
        event = RetrogradeExpansionEventPlan(
            event_ref=f"epistemics_backfill_{uuid.uuid4().hex}",
            seed_ids=["seed_epistemics_backfill"],
            event_type="threat_issued",
            summary="Backfill fixture.",
            chronology="recent_past",
            participants=[
                RetrogradeExpansionParticipant(
                    entity_ref=record.name,
                    entity_kind="character",
                    role=role,
                )
                for record, role in zip(records, ("actor", "target"))
            ],
        )

        def apply(settings: Any) -> dict[str, Any]:
            return _plan_event_row(
                cur,
                event,
                dry_run=False,
                prologue_chunk_id=anchor,
                entity_index=entity_index,
                event_types={"threat_issued"},
                event_source_available=True,
                creatable_refs=frozenset(),
                epistemics_settings=settings,
            )

        inserted = apply(DISABLED)
        assert inserted["status"] == "inserted"
        assert inserted["claim_id"] is None
        backfilled = apply(EPISTEMICS)
        assert backfilled["status"] == "already_present"
        assert backfilled["world_event_id"] == inserted["world_event_id"]
        assert backfilled["claim_id"] is not None
        cur.execute(
            """
            SELECT character_entity_id, source_tier
            FROM claim_awareness WHERE claim_id = %s
            ORDER BY character_entity_id
            """,
            (backfilled["claim_id"],),
        )
        assert {
            int(row["character_entity_id"]): row["source_tier"]
            for row in cur.fetchall()
        } == {
            records[0].entity_id: "participant",
            records[1].entity_id: "participant",
        }


@pytest.mark.requires_postgres
def test_live_applier_mints_and_ledgers_epistemics_ids(save_02_conn: Any) -> None:
    """The sync live applier records claim and awareness ids in state_delta."""

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        anchor, characters = _anchor_and_characters(cur, 2)
        actor, target = [int(character["entity_id"]) for character in characters]
    binding_hash = f"epistemics-live-{uuid.uuid4().hex}"
    proposal = OrreryTickProposal(
        anchor_chunk_id=anchor,
        actor_count=1,
        epistemics_settings=EPISTEMICS,
        resolutions=(
            OrreryResolutionDraft(
                template_id="epistemics_live_probe",
                priority=48,
                binding_hash=binding_hash,
                bindings={"actor": actor, "target": target},
                branch_label="Issue a test threat",
                narrative_stub="{actor} threatens {target}.",
                event_type="threat_issued",
                magnitude=0.4,
            ),
        ),
    )
    result = commit_orrery_tick_sync(
        save_02_conn,
        proposal,
        tick_chunk_id=anchor,
        slot=2,
    )
    assert result.resolution_count == 1
    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, state_delta FROM orrery_resolutions
            WHERE binding_hash = %s
            """,
            (binding_hash,),
        )
        resolution = cur.fetchone()
        applied = resolution["state_delta"]["applied"]["epistemics"]
        assert applied["claim_id"] is not None
        assert len(applied["claim_awareness_ids"]) == 2
        cur.execute(
            """
            SELECT c.world_event_id, c.source_chunk_id, c.source_resolution_id,
                   count(ca.id) AS awareness_count
            FROM claims c
            JOIN claim_awareness ca ON ca.claim_id = c.id
            WHERE c.id = %s
            GROUP BY c.id
            """,
            (applied["claim_id"],),
        )
        claim = cur.fetchone()
        assert claim["source_chunk_id"] == anchor
        assert claim["source_resolution_id"] == resolution["id"]
        assert claim["awareness_count"] == 2


@pytest.mark.requires_postgres
def test_pydantic_epistemics_settings_coerce_and_drive_live_producer(
    save_02_conn: Any,
) -> None:
    """The config model and runtime policy drive the same producer behavior."""

    settings = OrreryEpistemicsSettings(
        enabled=True,
        claim_event_types=["threat_issued"],
        aware_roles=["actor", "target", "observer", "witness"],
    )
    policy = coerce_epistemics_policy(settings)
    assert policy.enabled is True
    assert policy.claim_event_types == frozenset({"threat_issued"})
    assert policy.aware_roles == frozenset({"actor", "target", "observer", "witness"})

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        anchor, characters = _anchor_and_characters(cur, 2)
        actor, target = [int(character["entity_id"]) for character in characters]
    binding_hash = f"epistemics-pydantic-{uuid.uuid4().hex}"
    result = commit_orrery_tick_sync(
        save_02_conn,
        OrreryTickProposal(
            anchor_chunk_id=anchor,
            actor_count=1,
            resolutions=(
                OrreryResolutionDraft(
                    template_id="epistemics_pydantic_probe",
                    priority=48,
                    binding_hash=binding_hash,
                    bindings={"actor": actor, "target": target},
                    branch_label="Issue a Pydantic-configured threat",
                    narrative_stub="{actor} threatens {target}.",
                    event_type="threat_issued",
                    magnitude=0.4,
                ),
            ),
        ),
        tick_chunk_id=anchor,
        slot=2,
        epistemics_settings=settings,
    )
    assert result.resolution_count == 1
    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT c.id
            FROM claims c
            JOIN world_events we ON we.id = c.world_event_id
            JOIN orrery_resolutions r ON r.id = we.resolution_id
            WHERE r.binding_hash = %s
            """,
            (binding_hash,),
        )
        assert cur.fetchone() is not None


@pytest.mark.requires_postgres
def test_async_live_applier_has_epistemics_parity() -> None:
    """The asyncpg applier mints and ledgers the same Epistemics rows."""

    import asyncio

    import asyncpg  # type: ignore[import-untyped]

    async def run() -> None:
        conn = await asyncpg.connect(
            host=os.environ.get("PGHOST", "localhost"),
            database="save_02",
            user=os.environ.get("PGUSER", "pythagor"),
            port=os.environ.get("PGPORT", "5432"),
        )
        transaction = conn.transaction()
        await transaction.start()
        try:
            anchor = int(await conn.fetchval("SELECT max(id) FROM narrative_chunks"))
            rows = await conn.fetch(
                """
                SELECT entity_id FROM characters
                WHERE entity_id IS NOT NULL ORDER BY id LIMIT 2
                """
            )
            actor, target = (int(row["entity_id"]) for row in rows)
            binding_hash = f"epistemics-async-{uuid.uuid4().hex}"
            result = await commit_orrery_tick_async(
                conn,
                OrreryTickProposal(
                    anchor_chunk_id=anchor,
                    actor_count=1,
                    resolutions=(
                        OrreryResolutionDraft(
                            template_id="epistemics_async_probe",
                            priority=48,
                            binding_hash=binding_hash,
                            bindings={"actor": actor, "target": target},
                            branch_label="Issue an async test threat",
                            narrative_stub="{actor} threatens {target}.",
                            event_type="threat_issued",
                            magnitude=0.4,
                        ),
                    ),
                ),
                tick_chunk_id=anchor,
                slot=2,
                epistemics_settings=EPISTEMICS,
            )
            assert result.resolution_count == 1
            resolution = await conn.fetchrow(
                """
                SELECT id, state_delta FROM orrery_resolutions
                WHERE binding_hash = $1
                """,
                binding_hash,
            )
            assert resolution is not None
            state_delta = resolution["state_delta"]
            if isinstance(state_delta, str):
                state_delta = json.loads(state_delta)
            applied = state_delta["applied"]["epistemics"]
            assert applied["claim_id"] is not None
            assert len(applied["claim_awareness_ids"]) == 2
            claim = await conn.fetchrow(
                """
                SELECT summary, scope, source_chunk_id, source_resolution_id
                FROM claims WHERE id = $1
                """,
                applied["claim_id"],
            )
            assert claim is not None
            assert claim["scope"] == "bounded"
            assert claim["source_chunk_id"] == anchor
            assert claim["source_resolution_id"] == resolution["id"]
            awareness_rows = await conn.fetch(
                """
                SELECT id, character_entity_id, source_tier, source_chunk_id,
                       immediate_source_entity_id, root_source_entity_id
                FROM claim_awareness
                WHERE claim_id = $1
                ORDER BY character_entity_id
                """,
                applied["claim_id"],
            )
            assert {
                int(row["character_entity_id"]): row["source_tier"]
                for row in awareness_rows
            } == {actor: "participant", target: "participant"}
            assert [int(row["id"]) for row in awareness_rows] == sorted(
                applied["claim_awareness_ids"]
            )
            assert all(row["source_chunk_id"] == anchor for row in awareness_rows)
            assert all(
                row["immediate_source_entity_id"] is None
                and row["root_source_entity_id"] is None
                for row in awareness_rows
            )
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(run())


@pytest.mark.requires_postgres
def test_resolver_hydrates_scopes_and_awareness_in_recent_window() -> None:
    """Resolver hydration exposes both Epistemics read-side indexes."""

    engine = create_engine(get_slot_db_url(slot=2))
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        anchor_value = session.execute(
            text("SELECT max(id) FROM narrative_chunks")
        ).scalar_one()
        assert anchor_value is not None
        anchor = int(anchor_value)
        rows = list(
            session.execute(
                text(
                    """
                    SELECT entity_id FROM characters
                    WHERE entity_id IS NOT NULL ORDER BY id LIMIT 2
                    """
                )
            ).scalars()
        )
        actor, target = (int(value) for value in rows)
        event_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, actor_entity_id,
                        target_entity_id, world_layer, source,
                        changed_fields, payload
                    ) VALUES (
                        'threat_issued', :anchor, :actor, :target,
                        'primary', 'resolver', '{}', '{}'::jsonb
                    ) RETURNING id
                    """
                ),
                {"anchor": anchor, "actor": actor, "target": target},
            ).scalar_one()
        )
        claim_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO claims (
                        world_event_id, summary, scope, source_chunk_id
                    ) VALUES (
                        :event_id, 'Hydration fixture', 'bounded', :anchor
                    ) RETURNING id
                    """
                ),
                {"event_id": event_id, "anchor": anchor},
            ).scalar_one()
        )
        session.execute(
            text(
                """
                INSERT INTO claim_awareness (
                    claim_id, character_entity_id, source_tier, source_chunk_id
                ) VALUES (:claim_id, :actor, 'participant', :anchor)
                """
            ),
            {"claim_id": claim_id, "actor": actor, "anchor": anchor},
        )
        state = hydrate_world_state(
            session,
            anchor_chunk_id=anchor,
            window_chunks=1,
            epistemics_settings=EPISTEMICS,
        )
        assert any(event.event_id == event_id for event in state.recent_events)
        assert state.claimed_event_scopes[event_id] == "bounded"
        assert event_id in state.awareness_by_entity[actor]
        assert state.epistemics_enabled is True
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.mark.requires_postgres
def test_unclaimed_event_is_implicitly_common_with_epistemics_enabled() -> None:
    """Unclaimed recent events remain visible to every actor under Epistemics."""

    engine = create_engine(get_slot_db_url(slot=2))
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        anchor_value = session.execute(
            text("SELECT max(id) FROM narrative_chunks")
        ).scalar_one()
        assert anchor_value is not None
        anchor = int(anchor_value)
        actor_ids = [
            int(value)
            for value in session.execute(
                text(
                    """
                    SELECT entity_id FROM characters
                    WHERE entity_id IS NOT NULL ORDER BY id LIMIT 4
                    """
                )
            ).scalars()
        ]
        assert len(actor_ids) == 4
        event_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, actor_entity_id,
                        target_entity_id, world_layer, source,
                        changed_fields, payload
                    ) VALUES (
                        'threat_issued', :anchor, :actor, :target,
                        'primary', 'resolver', '{}', '{}'::jsonb
                    ) RETURNING id
                    """
                ),
                {
                    "anchor": anchor,
                    "actor": actor_ids[0],
                    "target": actor_ids[1],
                },
            ).scalar_one()
        )
        state = hydrate_world_state(
            session,
            anchor_chunk_id=anchor,
            window_chunks=1,
            epistemics_settings=EPISTEMICS,
        )
        assert event_id not in state.claimed_event_scopes
        knows = knows_recent_event("threat_issued", within_ticks=1)
        legacy = recent_event("threat_issued", within_ticks=1)
        for actor_id in actor_ids:
            bindings = {Slot.ACTOR: actor_id}
            assert legacy(state, bindings) is True
            assert knows(state, bindings) is True
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.mark.requires_postgres
def test_revelation_scope_and_common_semantics(save_02_conn: Any) -> None:
    """Revelations deduplicate; common works row-free; illegal narrowing raises."""

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        anchor, characters = _anchor_and_characters(cur, 3)
        source, knower, target = [
            int(character["entity_id"]) for character in characters
        ]
        event_id = _insert_event(
            cur,
            anchor=anchor,
            event_type="threat_issued",
            actor=source,
            target=target,
        )
        cur.execute(
            """
            INSERT INTO claims (world_event_id, summary, scope, source_chunk_id)
            VALUES (%s, 'Common fixture claim', 'common', %s)
            RETURNING id
            """,
            (event_id, anchor),
        )
        claim_id = int(cur.fetchone()["id"])

        state = WorldState(
            recent_events=(
                EventRecord(
                    event_id=event_id,
                    event_type="threat_issued",
                    tick=anchor,
                    actor_entity_id=source,
                    target_entity_id=target,
                ),
            ),
            claimed_event_scopes={event_id: "common"},
            epistemics_enabled=True,
            current_tick=anchor,
        )
        condition = knows_recent_event("threat_issued", within_ticks=1)
        assert condition(state, {Slot.ACTOR: knower}) is True

        promote_claim_scope(cur, claim_id=claim_id, new_scope="common")
        cur.execute("SELECT scope FROM claims WHERE id = %s", (claim_id,))
        assert cur.fetchone()["scope"] == "common"
        promote_claim_scope(cur, claim_id=claim_id, new_scope="bounded")
        cur.execute("SELECT scope FROM claims WHERE id = %s", (claim_id,))
        assert cur.fetchone()["scope"] == "bounded"
        with pytest.raises(ValueError, match="Illegal claim scope transition"):
            promote_claim_scope(cur, claim_id=claim_id, new_scope="common")

        world_time = datetime(2099, 1, 2, 3, tzinfo=timezone.utc)
        first = record_revelation(
            cur,
            claim_id=claim_id,
            character_entity_id=knower,
            source_entity_id=source,
            channel="message",
            world_time=world_time,
            source_chunk_id=anchor,
        )
        duplicate = record_revelation(
            cur,
            claim_id=claim_id,
            character_entity_id=knower,
            source_entity_id=source,
            channel="message",
            world_time=world_time,
            source_chunk_id=anchor,
        )
        assert first.inserted is True
        assert duplicate.inserted is False
        assert duplicate.awareness_id == first.awareness_id
        assert duplicate.source_tier == first.source_tier == "told"
        cur.execute(
            """
            SELECT source_tier, immediate_source_entity_id,
                   root_source_entity_id, channel, acquired_at_world_time
            FROM claim_awareness WHERE id = %s
            """,
            (first.awareness_id,),
        )
        awareness = cur.fetchone()
        assert awareness["source_tier"] == "told"
        assert awareness["immediate_source_entity_id"] == source
        assert awareness["root_source_entity_id"] is None
        assert awareness["channel"] == "message"
        assert awareness["acquired_at_world_time"] == world_time


@pytest.mark.requires_postgres
def test_kill_switch_disables_real_retrograde_and_live_producers(
    save_02_conn: Any,
) -> None:
    """Disabled Epistemics writes nothing and preserves recent_event behavior."""

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT count(*) AS count FROM claims")
        claims_before = int(cur.fetchone()["count"])
        cur.execute("SELECT count(*) AS count FROM claim_awareness")
        awareness_before = int(cur.fetchone()["count"])
        anchor, characters = _anchor_and_characters(cur, 2)
        actor, target = [int(character["entity_id"]) for character in characters]
        records = [
            _EntityRecord(
                entity_id=int(row["entity_id"]),
                entity_kind="character",
                name=str(row["name"]),
                character_id=int(row["character_id"]),
                faction_id=None,
                place_id=None,
            )
            for row in characters
        ]
        retrograde = _plan_event_row(
            cur,
            RetrogradeExpansionEventPlan(
                event_ref=f"epistemics_disabled_retro_{uuid.uuid4().hex}",
                seed_ids=["seed_epistemics_disabled"],
                event_type="threat_issued",
                summary="Disabled Retrograde fixture.",
                chronology="recent_past",
                participants=[
                    RetrogradeExpansionParticipant(
                        entity_ref=record.name,
                        entity_kind="character",
                        role=role,
                    )
                    for record, role in zip(records, ("actor", "target"))
                ],
            ),
            dry_run=False,
            prologue_chunk_id=anchor,
            entity_index={
                ("character", normalize_entity_ref(record.name)): [record]
                for record in records
            },
            event_types={"threat_issued"},
            event_source_available=True,
            creatable_refs=frozenset(),
            epistemics_settings=DISABLED,
        )
        assert retrograde["status"] == "inserted"
        assert retrograde["claim_id"] is None

    binding_hash = f"epistemics-disabled-live-{uuid.uuid4().hex}"
    committed = commit_orrery_tick_sync(
        save_02_conn,
        OrreryTickProposal(
            anchor_chunk_id=anchor,
            actor_count=1,
            epistemics_settings=DISABLED,
            resolutions=(
                OrreryResolutionDraft(
                    template_id="epistemics_disabled_probe",
                    priority=48,
                    binding_hash=binding_hash,
                    bindings={"actor": actor, "target": target},
                    branch_label="Issue a disabled-policy threat",
                    narrative_stub="{actor} threatens {target}.",
                    event_type="threat_issued",
                    magnitude=0.4,
                ),
            ),
        ),
        tick_chunk_id=anchor,
        slot=2,
    )
    assert committed.resolution_count == 1

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT we.id
            FROM world_events we
            JOIN orrery_resolutions r ON r.id = we.resolution_id
            WHERE r.binding_hash = %s
            """,
            (binding_hash,),
        )
        live_event_id = int(cur.fetchone()["id"])
        cur.execute("SELECT count(*) AS count FROM claims")
        assert int(cur.fetchone()["count"]) == claims_before
        cur.execute("SELECT count(*) AS count FROM claim_awareness")
        assert int(cur.fetchone()["count"]) == awareness_before

    event_ids = (int(retrograde["world_event_id"]), live_event_id)
    state = WorldState(
        recent_events=tuple(
            EventRecord(
                event_id=event_id,
                event_type="threat_issued",
                tick=anchor,
                actor_entity_id=actor,
                target_entity_id=target,
            )
            for event_id in event_ids
        ),
        claimed_event_scopes={event_id: "private" for event_id in event_ids},
        epistemics_enabled=False,
        current_tick=anchor,
    )
    bindings = {Slot.ACTOR: actor, Slot.TARGET: target}
    knows = knows_recent_event("threat_issued", within_ticks=1, target_slot=Slot.TARGET)
    legacy = recent_event("threat_issued", within_ticks=1, target_slot=Slot.TARGET)
    assert knows(state, bindings) is True
    assert knows(state, bindings) == legacy(state, bindings)


@pytest.mark.requires_postgres
def test_record_revelation_cli_handler_reports_insert_and_dedupe(
    save_02_conn: Any,
) -> None:
    """The real CLI handler reports grants and unchanged dedupes honestly."""

    from nexus.cli import build_parser, run_record_revelation

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        anchor, characters = _anchor_and_characters(cur, 3)
        source, knower, target = [
            int(character["entity_id"]) for character in characters
        ]
        event_id = _insert_event(
            cur,
            anchor=anchor,
            event_type="threat_issued",
            actor=source,
            target=target,
        )
        cur.execute(
            """
            INSERT INTO claims (world_event_id, summary, scope, source_chunk_id)
            VALUES (%s, 'CLI revelation fixture', 'bounded', %s)
            RETURNING id
            """,
            (event_id, anchor),
        )
        claim_id = int(cur.fetchone()["id"])

    parser = build_parser()
    first_args = parser.parse_args(
        [
            "record-revelation",
            "--slot",
            "2",
            "--claim-id",
            str(claim_id),
            "--character-entity-id",
            str(knower),
            "--source-chunk-id",
            str(anchor),
        ]
    )
    first = run_record_revelation(first_args, connection=save_02_conn)
    assert first["inserted"] is True
    assert first["source_tier"] == "granted"
    assert first["message"] == (
        f"Granted awareness for claim {claim_id} (tier: granted)."
    )

    duplicate_args = parser.parse_args(
        [
            "record-revelation",
            "--slot",
            "2",
            "--claim-id",
            str(claim_id),
            "--character-entity-id",
            str(knower),
            "--source-entity-id",
            str(source),
            "--channel",
            "message",
        ]
    )
    duplicate = run_record_revelation(duplicate_args, connection=save_02_conn)
    assert duplicate["inserted"] is False
    assert duplicate["claim_awareness_id"] == first["claim_awareness_id"]
    assert duplicate["source_tier"] == "granted"
    assert duplicate["message"] == (
        f"Claim {claim_id} is already known by entity {knower}; unchanged."
    )
    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT source_tier, immediate_source_entity_id, root_source_entity_id
            FROM claim_awareness WHERE id = %s
            """,
            (first["claim_awareness_id"],),
        )
        row = cur.fetchone()
        assert row == {
            "source_tier": "granted",
            "immediate_source_entity_id": None,
            "root_source_entity_id": None,
        }


def test_migration_documents_every_new_table_and_column() -> None:
    migration = Path("migrations/076_claims_awareness.sql").read_text()
    for table, columns in {
        "claims": (
            "id",
            "world_event_id",
            "summary",
            "scope",
            "source_chunk_id",
            "source_resolution_id",
            "created_at",
        ),
        "claim_awareness": (
            "id",
            "claim_id",
            "character_entity_id",
            "source_tier",
            "immediate_source_entity_id",
            "root_source_entity_id",
            "channel",
            "acquired_at_world_time",
            "source_chunk_id",
            "created_at",
        ),
    }.items():
        assert f"COMMENT ON TABLE {table}" in migration
        for column in columns:
            assert f"COMMENT ON COLUMN {table}.{column}" in migration

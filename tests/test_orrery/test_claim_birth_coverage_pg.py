"""Ephemeral-Postgres coverage for tracked-at-birth claim producers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import timedelta
from itertools import count
import os
from typing import Any
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2 import sql
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery.epistemics import mint_account_variant_sync
from nexus.agents.orrery.events import (
    LIVE_EVENT_BIRTH_ROLES,
    commit_orrery_tick_sync,
)
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import canonicalize, reconstruct_state_at_sync
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    DriveBand,
    Slot,
    Template,
)


pytestmark = pytest.mark.requires_postgres

APPROVED_EVENT_TYPES = (
    "compliance_alert",
    "encoded_message",
    "hunt_called_off",
    "hunt_declared",
    "informant_contact",
    "intel_acquired",
    "intel_acted_on",
    "protective_intervention",
    "pursue_romance_completed",
    "recruit_ally_completed",
    "relationship_drift_milestone",
    "retaliation_attempted",
    "retaliation_executed",
    "rival_consulted",
    "seek_redemption_completed",
    "surveillance_performed",
    "threat_issued",
    "warning_delivered",
)
PRIVATE_RESOLVER_EVENT_TYPES = (
    "hunt_called_off",
    "hunt_declared",
    "intel_acted_on",
    "protective_intervention",
    "retaliation_attempted",
    "surveillance_performed",
)
BOUNDED_RESOLVER_EVENT_TYPES = (
    "informant_contact",
    "intel_acquired",
    "pursue_romance_completed",
    "recruit_ally_completed",
    "retaliation_executed",
    "rival_consulted",
    "seek_redemption_completed",
    "warning_delivered",
)
SIGNAL_EVENT_TYPES = (
    "compliance_alert",
    "encoded_message",
    "threat_issued",
)
EPISTEMICS = {
    "enabled": True,
    "claim_event_types": list(APPROVED_EVENT_TYPES),
    "aware_roles": ["actor", "target", "observer", "witness"],
}
_SCENES = count(1)


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        cursor_factory=RealDictCursor,
    )


@pytest.fixture(scope="module")
def claim_birth_db() -> Iterator[str]:
    """Clone the template into a disposable database and drop it afterward."""

    dbname = f"qa679_{uuid4().hex[:12]}"
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
        with _connect(dbname) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'claims'
                      AND column_name = 'account_label'
                ) AS claims_ready,
                EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'character_relationships'
                      AND column_name = 'valence_current'
                ) AS drift_ready
                """
            )
            readiness = cur.fetchone()
            assert readiness == {"claims_ready": True, "drift_ready": True}
        yield dbname
    finally:
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


def _insert_chunk(cur: Any, *, delta: timedelta) -> int:
    token = uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES (%s, 'Ephemeral issue-679 claim-birth fixture.')
        RETURNING id
        """,
        (f"Claim-birth fixture {token}.",),
    )
    chunk_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date, slug
        ) VALUES (
            %s, 79, 79, %s, 'primary', %s, now(), %s
        )
        """,
        (chunk_id, next(_SCENES), delta, token[:10]),
    )
    return chunk_id


def _seed_world(dbname: str) -> dict[str, Any]:
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("UPDATE entities SET is_active = false WHERE kind = 'character'")
        cur.execute(
            """
            INSERT INTO global_variables (id, new_story, base_timestamp)
            VALUES (true, true, '2200-01-01 00:00:00+00')
            ON CONFLICT (id) DO UPDATE
            SET base_timestamp = EXCLUDED.base_timestamp
            """
        )
        cur.execute(
            "INSERT INTO entities (kind, is_active) "
            "VALUES ('place', true) RETURNING id"
        )
        place_entity_id = int(cur.fetchone()["id"])
        cur.execute(
            """
            INSERT INTO places (name, type, summary, entity_id)
            VALUES (
                %s, 'fixed_location', 'Ephemeral issue-679 fixture.', %s
            )
            RETURNING id
            """,
            (f"qa679-place-{uuid4().hex[:10]}", place_entity_id),
        )
        place_id = int(cur.fetchone()["id"])
        entities: dict[str, int] = {}
        characters: dict[str, int] = {}
        names: dict[str, str] = {}
        token = uuid4().hex[:10]
        for label in ("actor", "target", "nearby"):
            cur.execute(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('character', true) RETURNING id"
            )
            entity_id = int(cur.fetchone()["id"])
            name = f"qa679-{token}-{label}"
            cur.execute(
                """
                INSERT INTO characters (name, entity_id, current_location)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (name, entity_id, place_id),
            )
            entities[label] = entity_id
            characters[label] = int(cur.fetchone()["id"])
            names[label] = name
        cur.execute(
            """
            INSERT INTO character_routine_anchors (
                character_entity_id, anchor_type, place_id,
                mobility_policy, source
            ) VALUES (%s, 'home', %s, 'fixed_place', 'test_claim_birth_coverage_pg')
            """,
            (entities["actor"], place_id),
        )
        cur.execute(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, valence_current, dynamic,
                recent_events, history
            ) VALUES (
                %s, %s, 'associate', '+1|favorable', 0.1,
                'Ephemeral claim-birth edge.', 'None.', 'Issue 679 fixture.'
            )
            """,
            (characters["actor"], characters["target"]),
        )
        base_chunk = _insert_chunk(cur, delta=timedelta(0))
    return {
        **entities,
        "actor_character": characters["actor"],
        "target_character": characters["target"],
        "actor_name": names["actor"],
        "target_name": names["target"],
        "base_chunk": base_chunk,
    }


def _template(event_type: str, *, signal_event_type: str | None = None) -> Template:
    return Template(
        id=f"qa679_{event_type}_{signal_event_type or 'primary'}",
        priority=100,
        drive_band=DriveBand.CRISIS_CONSTRAINT,
        blurb="Ephemeral tracked-at-birth producer fixture.",
        required_slots=(Slot.ACTOR, Slot.TARGET),
        package_gate=ALWAYS,
        branches=(
            Branch(
                label="Emit the approved event",
                conditions=ALWAYS,
                narrative_stub="{actor} acts in relation to {target}.",
                event_type=event_type,
                signal_event_type=signal_event_type,
                magnitude=0.5,
            ),
        ),
    )


def _resolve(dbname: str, *, template: Template, anchor_chunk_id: int) -> Any:
    engine = create_engine(
        "postgresql+psycopg2://"
        f"{os.environ.get('PGUSER', 'pythagor')}@"
        f"{os.environ.get('PGHOST', 'localhost')}:"
        f"{os.environ.get('PGPORT', '5432')}/{dbname}",
        future=True,
    )
    try:
        with Session(engine) as session:
            return resolve_dry_run(
                session,
                (template,),
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=1,
                epistemics_settings=EPISTEMICS,
            )
    finally:
        engine.dispose()


def _target_draft(proposal: Any, actor: int, target: int) -> Any:
    matches = [
        draft
        for draft in proposal.resolutions
        if draft.bindings == {"actor": actor, "target": target}
    ]
    assert len(matches) == 1
    return matches[0]


def _commit_proposal(
    dbname: str,
    *,
    proposal: Any,
    tick_chunk_id: int,
    drift_settings: Mapping[str, Any] | None = None,
) -> Any:
    with _connect(dbname) as conn:
        return commit_orrery_tick_sync(
            conn,
            proposal,
            tick_chunk_id=tick_chunk_id,
            epistemics_settings=EPISTEMICS,
            ecology_settings={"signal_detection_default": 100},
            drift_settings=drift_settings,
        )


def _claim_rows(cur: Any, *, tick_chunk_id: int, event_type: str) -> list[Any]:
    cur.execute(
        """
        SELECT event.id AS event_id, claim.id AS claim_id, claim.summary,
               claim.scope, claim.source_chunk_id, claim.source_resolution_id,
               event.actor_entity_id, event.target_entity_id
        FROM world_events event
        JOIN claims claim ON claim.world_event_id = event.id
        WHERE event.tick_chunk_id = %s
          AND event.event_type = %s
        ORDER BY event.id
        """,
        (tick_chunk_id, event_type),
    )
    return list(cur.fetchall())


def _awareness(cur: Any, claim_id: int) -> dict[int, str]:
    cur.execute(
        """
        SELECT knower_entity_id, source_tier
        FROM claim_awareness
        WHERE claim_id = %s
        ORDER BY knower_entity_id
        """,
        (claim_id,),
    )
    return {
        int(row["knower_entity_id"]): str(row["source_tier"]) for row in cur.fetchall()
    }


@pytest.mark.parametrize(
    ("event_type", "target_aware"),
    [
        *((event_type, False) for event_type in PRIVATE_RESOLVER_EVENT_TYPES),
        *((event_type, True) for event_type in BOUNDED_RESOLVER_EVENT_TYPES),
    ],
)
def test_primary_resolver_birth_roles_and_provenance(
    claim_birth_db: str,
    event_type: str,
    target_aware: bool,
) -> None:
    """Resolve -> draft -> commit assigns only the approved explicit knowers."""

    state = _seed_world(claim_birth_db)
    proposal = _resolve(
        claim_birth_db,
        template=_template(event_type),
        anchor_chunk_id=state["base_chunk"],
    )
    draft = _target_draft(proposal, state["actor"], state["target"])
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        tick_chunk_id = _insert_chunk(cur, delta=timedelta(hours=1))
    result = _commit_proposal(
        claim_birth_db,
        proposal=proposal,
        tick_chunk_id=tick_chunk_id,
    )
    assert result.resolution_count == 1

    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        rows = _claim_rows(cur, tick_chunk_id=tick_chunk_id, event_type=event_type)
        assert len(rows) == 1
        claim = rows[0]
        expected = {state["actor"]: "participant"}
        if target_aware:
            expected[state["target"]] = "participant"
        assert _awareness(cur, int(claim["claim_id"])) == expected
        assert state["nearby"] not in expected
        assert claim["source_chunk_id"] == tick_chunk_id
        assert claim["source_resolution_id"] is not None
        assert claim["scope"] == "bounded"
        assert draft.binding_names["actor"] in claim["summary"]
        assert draft.binding_names["target"] in claim["summary"]
        canonical_claim_id = int(claim["claim_id"])

    duplicate = _commit_proposal(
        claim_birth_db,
        proposal=proposal,
        tick_chunk_id=tick_chunk_id,
    )
    assert duplicate.skipped_existing_count == 1
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        rows = _claim_rows(cur, tick_chunk_id=tick_chunk_id, event_type=event_type)
        assert [int(row["claim_id"]) for row in rows] == [canonical_claim_id]


@pytest.mark.parametrize(
    ("primary_event_type", "signal_event_type", "primary_target_aware"),
    [
        ("surveillance_performed", "compliance_alert", False),
        ("informant_contact", "encoded_message", True),
        ("retaliation_attempted", "threat_issued", False),
    ],
)
def test_detected_signal_receipt_is_separate_from_private_deed(
    claim_birth_db: str,
    primary_event_type: str,
    signal_event_type: str,
    primary_target_aware: bool,
) -> None:
    """Detected signals inform their target without proximity-derived witnesses."""

    state = _seed_world(claim_birth_db)
    proposal = _resolve(
        claim_birth_db,
        template=_template(
            primary_event_type,
            signal_event_type=signal_event_type,
        ),
        anchor_chunk_id=state["base_chunk"],
    )
    _target_draft(proposal, state["actor"], state["target"])
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        tick_chunk_id = _insert_chunk(cur, delta=timedelta(hours=1))
    _commit_proposal(
        claim_birth_db,
        proposal=proposal,
        tick_chunk_id=tick_chunk_id,
    )

    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        primary = _claim_rows(
            cur,
            tick_chunk_id=tick_chunk_id,
            event_type=primary_event_type,
        )[0]
        signal = _claim_rows(
            cur,
            tick_chunk_id=tick_chunk_id,
            event_type=signal_event_type,
        )[0]
        primary_knowers = {state["actor"]: "participant"}
        if primary_target_aware:
            primary_knowers[state["target"]] = "participant"
        assert _awareness(cur, int(primary["claim_id"])) == primary_knowers
        assert _awareness(cur, int(signal["claim_id"])) == {
            state["actor"]: "participant",
            state["target"]: "participant",
        }
        assert state["nearby"] not in _awareness(cur, int(signal["claim_id"]))


def _canonical_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: canonicalize(value) for key, value in sorted(row.items())}
        for row in sorted(rows, key=lambda item: int(item["id"]))
    ]


def test_live_claim_replay_identity_and_sibling_account(
    claim_birth_db: str,
) -> None:
    """A live private mint replays exactly and keeps sibling accounts separate."""

    state = _seed_world(claim_birth_db)
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        base_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=state["base_chunk"],
            label="manual",
        )
        assert base_id is not None
    proposal = _resolve(
        claim_birth_db,
        template=_template("retaliation_attempted"),
        anchor_chunk_id=state["base_chunk"],
    )
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        tick_chunk_id = _insert_chunk(cur, delta=timedelta(hours=1))
    _commit_proposal(
        claim_birth_db,
        proposal=proposal,
        tick_chunk_id=tick_chunk_id,
    )

    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        claim = _claim_rows(
            cur,
            tick_chunk_id=tick_chunk_id,
            event_type="retaliation_attempted",
        )[0]
        claim_id = int(claim["claim_id"])
        sibling_id = mint_account_variant_sync(
            cur,
            source_claim_id=claim_id,
            account_label="qa679_sibling",
            summary="A deliberately separate account of the same incident.",
            source_chunk_id=tick_chunk_id,
        )
        cur.execute(
            "SELECT * FROM claim_awareness WHERE claim_id = %s ORDER BY id",
            (claim_id,),
        )
        live_awareness = list(cur.fetchall())
        target_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=tick_chunk_id,
            label="manual",
        )
        assert target_id is not None
        with conn.cursor(cursor_factory=psycopg2.extensions.cursor) as replay_cur:
            replayed = reconstruct_state_at_sync(
                replay_cur,
                tick_chunk_id,
                base_checkpoint_id=int(base_id),
                target_checkpoint_id=int(target_id),
            )
        cur.execute(
            """
            SELECT id, account_label, distorted_from_claim_id
            FROM claims
            WHERE world_event_id = %s
            ORDER BY id
            """,
            (claim["event_id"],),
        )
        accounts = list(cur.fetchall())

    replay_awareness = [
        row
        for row in replayed.state["claim_awareness"]
        if int(row["claim_id"]) == claim_id
    ]
    assert _canonical_rows(replay_awareness) == _canonical_rows(live_awareness)
    assert [(int(row["id"]), row["account_label"]) for row in accounts] == [
        (claim_id, "canonical"),
        (sibling_id, "qa679_sibling"),
    ]
    assert int(accounts[1]["distorted_from_claim_id"]) == claim_id


def test_relationship_drift_birth_is_actor_private_and_replays(
    claim_birth_db: str,
) -> None:
    """The drift producer keeps its target as subject, never as knower."""

    state = _seed_world(claim_birth_db)
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        base_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=state["base_chunk"],
            label="manual",
        )
        assert base_id is not None
    proposal = _resolve(
        claim_birth_db,
        template=_template(
            "retaliation_attempted",
            signal_event_type="threat_issued",
        ),
        anchor_chunk_id=state["base_chunk"],
    )
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        tick_chunk_id = _insert_chunk(cur, delta=timedelta(hours=1))
    _commit_proposal(
        claim_birth_db,
        proposal=proposal,
        tick_chunk_id=tick_chunk_id,
        drift_settings={
            "enabled": True,
            "copresence_rate_per_hour": "0.001",
            "copresence_max_hours_per_tick": "1",
            "project_milestone_delta": "0.03",
            "hostile_events": {"threat_issued": "-0.2"},
            "cooperative_events": {},
        },
    )

    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        drift_claim = _claim_rows(
            cur,
            tick_chunk_id=tick_chunk_id,
            event_type="relationship_drift_milestone",
        )[0]
        claim_id = int(drift_claim["claim_id"])
        assert _awareness(cur, claim_id) == {state["actor"]: "participant"}
        assert state["target"] not in _awareness(cur, claim_id)
        assert state["nearby"] not in _awareness(cur, claim_id)
        assert f"actor {state['actor_name']}" in drift_claim["summary"]
        assert f"target {state['target_name']}" in drift_claim["summary"]
        cur.execute(
            "SELECT * FROM claim_awareness WHERE claim_id = %s ORDER BY id",
            (claim_id,),
        )
        live_awareness = list(cur.fetchall())
        target_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=tick_chunk_id,
            label="manual",
        )
        assert target_id is not None
        with conn.cursor(cursor_factory=psycopg2.extensions.cursor) as replay_cur:
            replayed = reconstruct_state_at_sync(
                replay_cur,
                tick_chunk_id,
                base_checkpoint_id=int(base_id),
                target_checkpoint_id=int(target_id),
            )

    replay_awareness = [
        row
        for row in replayed.state["claim_awareness"]
        if int(row["claim_id"]) == claim_id
    ]
    assert _canonical_rows(replay_awareness) == _canonical_rows(live_awareness)


def test_resolution_free_commit_does_not_backfill_historical_event(
    claim_birth_db: str,
) -> None:
    """Enabling the expanded policy never scans and backfills old events."""

    state = _seed_world(claim_birth_db)
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, target_entity_id,
                world_layer, source, changed_fields, payload
            ) VALUES (
                'retaliation_attempted', %s, %s, %s,
                'primary', 'resolver', '{}', '{}'::jsonb
            )
            RETURNING id
            """,
            (state["base_chunk"], state["actor"], state["target"]),
        )
        historical_event_id = int(cur.fetchone()["id"])
        tick_chunk_id = _insert_chunk(cur, delta=timedelta(hours=1))

    with _connect(claim_birth_db) as conn:
        commit_orrery_tick_sync(
            conn,
            None,
            tick_chunk_id=tick_chunk_id,
            epistemics_settings=EPISTEMICS,
        )
    with _connect(claim_birth_db) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS count FROM claims WHERE world_event_id = %s",
            (historical_event_id,),
        )
        assert cur.fetchone()["count"] == 0


def test_matrix_partitions_the_exact_approved_set() -> None:
    """The test families cover every approved type and no excluded type."""

    assert set(APPROVED_EVENT_TYPES) == {
        *PRIVATE_RESOLVER_EVENT_TYPES,
        *BOUNDED_RESOLVER_EVENT_TYPES,
        *SIGNAL_EVENT_TYPES,
        "relationship_drift_milestone",
    }
    assert set(LIVE_EVENT_BIRTH_ROLES) | {"relationship_drift_milestone"} == set(
        APPROVED_EVENT_TYPES
    )

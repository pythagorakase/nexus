"""Rollback-only PostgreSQL coverage for Stage C hop distortion."""

from __future__ import annotations

from datetime import timedelta
import json
from typing import Any, Iterator

import asyncpg  # type: ignore[import-untyped]
import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.agents.orrery.epistemics import (
    mint_account_variant_async,
    mint_account_variant_sync,
    record_revelation,
)
from nexus.agents.orrery.propagation import drain_claim_propagation_sync
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import reconstruct_state_at_sync
from nexus.api.slot_utils import get_slot_db_url
from tests.test_orrery.claim_accounts_test_support import (
    install_claim_accounts_shadow_async,
    install_claim_accounts_shadow_sync,
)
from tests.test_orrery.test_claim_propagation_live import (
    LIVE_SLOT,
    _canonical_rows,
    _chain,
    _insert_character,
    _insert_chunk,
    _insert_claim,
    _insert_relationship,
    _install_valence_shadow,
    _settings,
)


pytestmark = pytest.mark.requires_postgres
DISTORTION_ENABLED = {"enabled": True}
DISTORTION_DISABLED = {"enabled": False}


@pytest.fixture()
def live_conn() -> Iterator[Any]:
    """Open one slot-5 transaction with post-092 shadow projections."""

    conn = psycopg2.connect(get_slot_db_url(slot=LIVE_SLOT))
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT EXISTS (
                           SELECT 1 FROM event_types
                           WHERE type = 'claim_propagated'
                       ) AS event_registered,
                       EXISTS (
                           SELECT 1
                           FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'world_events'
                             AND column_name = 'world_time'
                       ) AS world_time_column
                """
            )
            migration_state = cur.fetchone()
            if (
                not migration_state["event_registered"]
                or not migration_state["world_time_column"]
            ):
                pytest.skip("slot 5 must have migration 083 before Stage C tests")
            install_claim_accounts_shadow_sync(cur)
            _install_valence_shadow(cur)
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _mint_variant(
    cur: Any,
    *,
    canonical_claim_id: int,
    label: str,
    depth: int | None,
    source_chunk_id: int,
) -> int:
    return mint_account_variant_sync(
        cur,
        source_claim_id=canonical_claim_id,
        account_label=label,
        summary=f"Authored {label} account.",
        account_payload={"label": label},
        source_chunk_id=source_chunk_id,
        distortion_min_depth=depth,
    )


def _incident_id(cur: Any, claim_id: int) -> int:
    cur.execute("SELECT world_event_id FROM claims WHERE id = %s", (claim_id,))
    return int(cur.fetchone()["world_event_id"])


def _incident_awareness(cur: Any, incident_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT awareness.id, awareness.claim_id,
               awareness.knower_entity_id, awareness.source_tier,
               awareness.immediate_source_entity_id,
               awareness.root_source_entity_id, awareness.channel,
               awareness.acquired_at_world_time,
               awareness.source_chunk_id, awareness.created_at
        FROM claim_awareness awareness
        JOIN claims claim ON claim.id = awareness.claim_id
        WHERE claim.world_event_id = %s
        ORDER BY awareness.acquired_at_world_time,
                 awareness.knower_entity_id, awareness.id
        """,
        (incident_id,),
    )
    return [dict(row) for row in cur.fetchall()]


def _incident_events(cur: Any, incident_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, payload, world_time
        FROM world_events
        WHERE event_type = 'claim_propagated'
          AND (
              (payload ->> 'incident_world_event_id')::bigint = %s
              OR (
                  NOT (payload ? 'incident_world_event_id')
                  AND (payload ->> 'claim_id')::bigint IN (
                      SELECT id FROM claims WHERE world_event_id = %s
                  )
              )
          )
        ORDER BY world_time, id
        """,
        (incident_id, incident_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _assert_event_projection_pairs(
    awareness: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    awareness_keys = {
        (int(row["id"]), int(row["claim_id"]), int(row["knower_entity_id"]))
        for row in awareness
    }
    event_keys = {
        (
            int(event["payload"]["awareness_id"]),
            int(
                event["payload"].get(
                    "delivered_claim_id",
                    event["payload"]["claim_id"],
                )
            ),
            int(event["payload"]["knower_entity_id"]),
        )
        for event in events
    }
    assert event_keys <= awareness_keys
    assert len(event_keys) == len(events)


def test_depth_selection_tie_break_and_transitive_total_depth(
    live_conn: Any,
) -> None:
    """Each onward hop re-selects from one authored incident snapshot."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 6)
        birth_chunk, birth_world_time = _insert_chunk(cur)
        canonical = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        shallow = _mint_variant(
            cur,
            canonical_claim_id=canonical,
            label="shallow",
            depth=2,
            source_chunk_id=birth_chunk,
        )
        deepest_low_id = _mint_variant(
            cur,
            canonical_claim_id=canonical,
            label="deepest-low-id",
            depth=4,
            source_chunk_id=birth_chunk,
        )
        deepest_high_id = _mint_variant(
            cur,
            canonical_claim_id=canonical,
            label="deepest-high-id",
            depth=4,
            source_chunk_id=birth_chunk,
        )
        incident_id = _incident_id(cur, canonical)
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        drained = drain_claim_propagation_sync(
            cur,
            tick_chunk_id=drain_chunk,
            settings=_settings(depth_cap=5),
            distortion_settings=DISTORTION_ENABLED,
        )
        awareness = _incident_awareness(cur, incident_id)
        events = _incident_events(cur, incident_id)

    by_knower = {
        int(row["knower_entity_id"]): int(row["claim_id"]) for row in awareness
    }
    assert drained.minted_count == 5
    assert by_knower == {
        entities[0]: canonical,
        entities[1]: canonical,
        entities[2]: shallow,
        entities[3]: shallow,
        entities[4]: deepest_low_id,
        entities[5]: deepest_low_id,
    }
    assert deepest_high_id not in by_knower.values()
    assert [event["payload"]["depth"] for event in events] == [1, 2, 3, 4, 5]
    assert [event["payload"]["claim_id"] for event in events] == [
        canonical,
        canonical,
        shallow,
        shallow,
        deepest_low_id,
    ]
    assert [event["payload"]["delivered_claim_id"] for event in events] == [
        canonical,
        shallow,
        shallow,
        deepest_low_id,
        deepest_low_id,
    ]
    assert [event["payload"]["distortion_applied"] for event in events] == [
        False,
        True,
        False,
        True,
        False,
    ]
    assert {int(event["payload"]["incident_world_event_id"]) for event in events} == {
        incident_id
    }
    _assert_event_projection_pairs(awareness, events)


def test_incident_possession_suppresses_every_sibling_schedule(
    live_conn: Any,
) -> None:
    """A direct variant grant blocks canonical and variant propagation alike."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, source_character = _insert_character(cur, "suppression-source")
        listener, listener_character = _insert_character(cur, "suppression-listener")
        _insert_relationship(cur, source_character, listener_character)
        birth_chunk, birth_world_time = _insert_chunk(cur)
        canonical = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            birth_world_time=birth_world_time,
        )
        granted_variant = _mint_variant(
            cur,
            canonical_claim_id=canonical,
            label="manual-grant",
            depth=None,
            source_chunk_id=birth_chunk,
        )
        cur.execute(
            "UPDATE claims SET scope = 'private' WHERE id = %s",
            (granted_variant,),
        )
        _mint_variant(
            cur,
            canonical_claim_id=canonical,
            label="automatic-alternative",
            depth=1,
            source_chunk_id=birth_chunk,
        )
        record_revelation(
            cur,
            claim_id=granted_variant,
            knower_entity_id=listener,
            world_time=birth_world_time,
            source_chunk_id=birth_chunk,
        )
        incident_id = _incident_id(cur, canonical)
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        first = drain_claim_propagation_sync(
            cur,
            tick_chunk_id=drain_chunk,
            settings=_settings(),
            distortion_settings=DISTORTION_ENABLED,
        )
        second = drain_claim_propagation_sync(
            cur,
            tick_chunk_id=drain_chunk,
            settings=_settings(),
            distortion_settings=DISTORTION_ENABLED,
        )
        awareness = _incident_awareness(cur, incident_id)
        events = _incident_events(cur, incident_id)

    listener_rows = [
        row for row in awareness if int(row["knower_entity_id"]) == listener
    ]
    assert first.minted_count == second.minted_count == 0
    assert [int(row["claim_id"]) for row in listener_rows] == [granted_variant]
    assert listener_rows[0]["source_tier"] == "granted"
    assert events == []


def test_disabled_distortion_preserves_stage_b_delivery_but_not_rescheduling(
    live_conn: Any,
) -> None:
    """Feature-off delivery stays claim-identical; incident suppression remains."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 3)
        birth_chunk, birth_world_time = _insert_chunk(cur)
        canonical = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        _mint_variant(
            cur,
            canonical_claim_id=canonical,
            label="disabled-threshold",
            depth=1,
            source_chunk_id=birth_chunk,
        )
        propagated_incident = _incident_id(cur, canonical)

        suppress_source, suppress_source_character = _insert_character(
            cur, "disabled-suppress-source"
        )
        suppress_listener, suppress_listener_character = _insert_character(
            cur, "disabled-suppress-listener"
        )
        _insert_relationship(
            cur,
            suppress_source_character,
            suppress_listener_character,
        )
        suppressed_canonical = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=suppress_source,
            birth_world_time=birth_world_time,
        )
        suppressed_variant = _mint_variant(
            cur,
            canonical_claim_id=suppressed_canonical,
            label="already-heard",
            depth=1,
            source_chunk_id=birth_chunk,
        )
        record_revelation(
            cur,
            claim_id=suppressed_variant,
            knower_entity_id=suppress_listener,
            world_time=birth_world_time,
            source_chunk_id=birth_chunk,
        )
        suppressed_incident = _incident_id(cur, suppressed_canonical)

        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        drained = drain_claim_propagation_sync(
            cur,
            tick_chunk_id=drain_chunk,
            settings=_settings(),
            distortion_settings=DISTORTION_DISABLED,
        )
        propagated_rows = _incident_awareness(cur, propagated_incident)
        propagated_events = _incident_events(cur, propagated_incident)
        suppressed_rows = _incident_awareness(cur, suppressed_incident)
        suppressed_events = _incident_events(cur, suppressed_incident)

    assert drained.minted_count == 2
    assert {int(row["claim_id"]) for row in propagated_rows} == {canonical}
    assert all(
        event["payload"]["claim_id"] == event["payload"]["delivered_claim_id"]
        for event in propagated_events
    )
    assert all(
        event["payload"]["distortion_applied"] is False for event in propagated_events
    )
    suppressed_listener_rows = [
        row
        for row in suppressed_rows
        if int(row["knower_entity_id"]) == suppress_listener
    ]
    assert [int(row["claim_id"]) for row in suppressed_listener_rows] == [
        suppressed_variant
    ]
    assert suppressed_events == []


def test_distorted_drain_replays_identical_delivered_awareness(
    live_conn: Any,
) -> None:
    """Replay treats delivered claim ids as the passive projection authority."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 4)
        birth_chunk, birth_world_time = _insert_chunk(cur)
        canonical = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        variant = _mint_variant(
            cur,
            canonical_claim_id=canonical,
            label="replay-depth-two",
            depth=2,
            source_chunk_id=birth_chunk,
        )
        incident_id = _incident_id(cur, canonical)
        with live_conn.cursor() as checkpoint_cur:
            checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur,
                chunk_id=birth_chunk,
                label="manual",
            )
        assert checkpoint_id is not None
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        drained = drain_claim_propagation_sync(
            cur,
            tick_chunk_id=drain_chunk,
            settings=_settings(),
            distortion_settings=DISTORTION_ENABLED,
        )
        live_rows = _incident_awareness(cur, incident_id)
        with live_conn.cursor() as replay_cur:
            replay = reconstruct_state_at_sync(
                replay_cur,
                drain_chunk,
                base_checkpoint_id=checkpoint_id,
            )

    replayed_rows = [
        row
        for row in replay.state["claim_awareness"]
        if int(row["claim_id"]) in {canonical, variant}
    ]
    assert drained.minted_count == 3
    assert _canonical_rows(replayed_rows) == _canonical_rows(live_rows)


def test_pre_092_payload_fallback_drives_frontier_and_replay(
    live_conn: Any,
) -> None:
    """Historical claim_id-only events recover depth and replay unchanged."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 3)
        birth_chunk, birth_world_time = _insert_chunk(cur)
        canonical = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        incident_id = _incident_id(cur, canonical)
        with live_conn.cursor() as checkpoint_cur:
            checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur,
                chunk_id=birth_chunk,
                label="manual",
            )
        assert checkpoint_id is not None
        historical_chunk, historical_time = _insert_chunk(
            cur,
            time_delta=timedelta(hours=1),
        )
        cur.execute(
            """
            INSERT INTO claim_awareness (
                claim_id, knower_entity_id, source_tier,
                immediate_source_entity_id, root_source_entity_id, channel,
                acquired_at_world_time, source_chunk_id
            ) VALUES (%s, %s, 'told', %s, %s, 'dyad:associate', %s, %s)
            RETURNING id
            """,
            (
                canonical,
                entities[1],
                entities[0],
                entities[0],
                historical_time,
                historical_chunk,
            ),
        )
        historical_awareness_id = int(cur.fetchone()["id"])
        historical_payload = {
            "awareness_id": historical_awareness_id,
            "claim_id": canonical,
            "knower_entity_id": entities[1],
            "immediate_source_entity_id": entities[0],
            "root_source_entity_id": entities[0],
            "channel": "dyad:associate",
            "latency_seconds": 3600.0,
            "depth": 1,
            "policy_digest": "pre-092-fixture",
        }
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, world_layer, source,
                changed_fields, payload, world_time
            ) VALUES (
                'claim_propagated', %s, 'primary', 'resolver',
                ARRAY['claim_awareness']::text[], %s::jsonb, %s
            )
            """,
            (
                historical_chunk,
                json.dumps(historical_payload),
                historical_time,
            ),
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=2))
        drained = drain_claim_propagation_sync(
            cur,
            tick_chunk_id=drain_chunk,
            settings=_settings(),
            distortion_settings=DISTORTION_ENABLED,
        )
        live_rows = _incident_awareness(cur, incident_id)
        events = _incident_events(cur, incident_id)
        with live_conn.cursor() as replay_cur:
            replay = reconstruct_state_at_sync(
                replay_cur,
                drain_chunk,
                base_checkpoint_id=checkpoint_id,
            )

    replayed_rows = [
        row
        for row in replay.state["claim_awareness"]
        if int(row["claim_id"]) == canonical
    ]
    assert drained.minted_count == 1
    assert [event["payload"]["depth"] for event in events] == [1, 2]
    assert "delivered_claim_id" not in events[0]["payload"]
    assert events[1]["payload"]["delivered_claim_id"] == canonical
    assert _canonical_rows(replayed_rows) == _canonical_rows(live_rows)


def test_partial_stage_c_payload_fails_frontier_reconciliation(
    live_conn: Any,
) -> None:
    """Any Stage C identity key makes all three mandatory on new events."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, _ = _insert_character(cur, "partial-payload-source")
        birth_chunk, birth_world_time = _insert_chunk(cur)
        canonical = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            birth_world_time=birth_world_time,
        )
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, world_layer, source,
                changed_fields, payload, world_time
            ) VALUES (
                'claim_propagated', %s, 'primary', 'resolver',
                ARRAY['claim_awareness']::text[], %s::jsonb, %s
            )
            """,
            (
                birth_chunk,
                json.dumps(
                    {
                        "claim_id": canonical,
                        "delivered_claim_id": canonical,
                        "knower_entity_id": source,
                        "depth": 1,
                    }
                ),
                birth_world_time,
            ),
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=1))
        with pytest.raises(ValueError, match="lacks Stage C payload fields"):
            drain_claim_propagation_sync(
                cur,
                tick_chunk_id=drain_chunk,
                settings=_settings(),
                distortion_settings=DISTORTION_ENABLED,
            )


@pytest.mark.asyncio
async def test_async_variant_mint_persists_validated_depth() -> None:
    """The async authoring twin stores the same nullable-positive contract."""

    conn = await asyncpg.connect(get_slot_db_url(slot=LIVE_SLOT))
    transaction = conn.transaction()
    await transaction.start()
    try:
        await install_claim_accounts_shadow_async(conn)
        source_claim_id = int(
            await conn.fetchval(
                """
                INSERT INTO claims (
                    world_event_id, account_label, summary, scope
                ) VALUES (-92092, 'canonical', 'Async source.', 'bounded')
                RETURNING id
                """
            )
        )
        variant_id = await mint_account_variant_async(
            conn,
            source_claim_id=source_claim_id,
            account_label="async-depth-three",
            summary="Async authored variant.",
            source_chunk_id=None,
            distortion_min_depth=3,
        )
        assert (
            await conn.fetchval(
                "SELECT distortion_min_depth FROM claims WHERE id = $1",
                variant_id,
            )
            == 3
        )
        with pytest.raises(ValueError, match="integer >= 1"):
            await mint_account_variant_async(
                conn,
                source_claim_id=source_claim_id,
                account_label="async-invalid",
                summary="Invalid async variant.",
                source_chunk_id=None,
                distortion_min_depth=0,
            )
    finally:
        await transaction.rollback()
        await conn.close()

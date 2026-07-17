"""Rollback-only slot-5 coverage for Stage 2d claim consumption."""

from __future__ import annotations

from datetime import timedelta
import json
from typing import Any, Iterator

from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
import pytest
from sqlalchemy import create_engine, event

from nexus.agents.orrery.audit import entity_context, explain_dry_run
from nexus.agents.orrery.epistemics import (
    ClaimParticipant,
    load_epistemics_hydration,
    mechanical_claim_summary,
    mint_claim_for_event,
)
from nexus.agents.orrery.propagation import drain_claim_propagation_sync
from nexus.agents.orrery.resolver import hydrate_world_state, resolve_dry_run
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    DriveBand,
    Slot,
    Template,
    heard_secondhand,
    knows_claim_about,
)
from nexus.api.slot_utils import get_slot_db_url
from tests.test_orrery.test_claim_propagation_live import (
    EPISTEMICS,
    LIVE_SLOT,
    _chain,
    _insert_character,
    _insert_chunk,
    _insert_faction,
    _insert_pair_tag,
    _insert_relationship,
    _settings,
)


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def live_connection() -> Iterator[Any]:
    """Expose SQLAlchemy and raw-cursor reads inside one rolled-back tx."""

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
    connection = engine.connect()
    transaction = connection.begin()
    try:
        raw_connection = connection.connection.driver_connection
        with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT EXISTS (
                           SELECT 1 FROM event_types
                           WHERE type = 'claim_propagated'
                       ) AS registered,
                       EXISTS (
                           SELECT 1 FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'world_events'
                             AND column_name = 'world_time'
                       ) AS shaped
                """
            )
            migration_state = cur.fetchone()
            if not migration_state["registered"] or not migration_state["shaped"]:
                pytest.skip("slot 5 requires migrations 080-083 for Stage 2d")
        yield connection
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def _insert_claim_about(
    cur: Any,
    *,
    chunk_id: int,
    source_entity_id: int,
    about_entity_id: int,
    scope: str = "bounded",
) -> int:
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload
        ) VALUES (
            'threat_issued', %s, %s, %s, 'primary',
            'resolver', '{}', '{}'::jsonb
        )
        RETURNING id
        """,
        (chunk_id, source_entity_id, about_entity_id),
    )
    event_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO world_event_entities (event_id, role, entity_id)
        VALUES (%s, 'actor', %s), (%s, 'target', %s)
        """,
        (event_id, source_entity_id, event_id, about_entity_id),
    )
    participants = (
        ClaimParticipant(
            source_entity_id,
            "actor",
            f"Stage 2d source {source_entity_id}",
        ),
        ClaimParticipant(
            about_entity_id,
            "target",
            f"Stage 2d subject {about_entity_id}",
        ),
    )
    minted = mint_claim_for_event(
        cur,
        world_event_id=event_id,
        event_type="threat_issued",
        summary=mechanical_claim_summary("threat_issued", participants),
        participants=participants,
        source_chunk_id=chunk_id,
        source_resolution_id=None,
        settings=EPISTEMICS,
    )
    assert minted is not None
    if scope != "bounded":
        cur.execute(
            "UPDATE claims SET scope = %s WHERE id = %s", (scope, minted.claim_id)
        )
    return minted.claim_id


def _mark_actor_relevant(cur: Any, *, chunk_id: int, actor_entity_id: int) -> None:
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, world_layer,
            source, changed_fields, payload
        ) VALUES (
            'surveillance_performed', %s, %s, 'primary',
            'resolver', '{}', '{}'::jsonb
        )
        """,
        (chunk_id, actor_entity_id),
    )


def _consumption_template() -> Template:
    return Template(
        id="stage2d_knows_claim_about_probe",
        priority=100,
        drive_band=DriveBand.PROJECT_IDENTITY,
        blurb="Exercise Stage 2d hydrated package gating.",
        required_slots=(Slot.ACTOR, Slot.TARGET),
        package_gate=knows_claim_about(),
        branches=(
            Branch(
                label="Act on secondhand knowledge",
                conditions=ALWAYS,
                narrative_stub="{actor} acts on what they know about {target}.",
            ),
        ),
    )


def test_hydration_excludes_irrelevant_history_and_empty_universe_issues_no_sql(
    live_connection: Any,
) -> None:
    """Entity-scoped hydration ignores irrelevant claim volume entirely."""

    irrelevant_count = 32
    raw_connection = live_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        relevant_source, _ = _insert_character(cur, "hydrate-relevant-source")
        relevant_about, _ = _insert_character(cur, "hydrate-relevant-about")
        irrelevant_source, _ = _insert_character(cur, "hydrate-irrelevant-source")
        irrelevant_about, _ = _insert_character(cur, "hydrate-irrelevant-about")
        chunk_id, _ = _insert_chunk(cur)
        relevant_claim_id = _insert_claim_about(
            cur,
            chunk_id=chunk_id,
            source_entity_id=relevant_source,
            about_entity_id=relevant_about,
        )
        irrelevant_claim_ids = {
            _insert_claim_about(
                cur,
                chunk_id=chunk_id,
                source_entity_id=irrelevant_source,
                about_entity_id=irrelevant_about,
                scope="common" if index % 2 else "bounded",
            )
            for index in range(irrelevant_count)
        }
        cur.execute(
            "UPDATE entities SET is_active = false WHERE id IN (%s, %s)",
            (irrelevant_source, irrelevant_about),
        )

    state = hydrate_world_state(
        live_connection,
        anchor_chunk_id=chunk_id,
        window_chunks=1,
        epistemics_settings=EPISTEMICS,
    )
    hydrated_claim_ids = {record.claim_id for record in state.common_claim_knowledge}
    hydrated_claim_ids.update(
        record.claim_id
        for records in state.claim_knowledge_by_entity.values()
        for record in records
    )

    assert relevant_claim_id in hydrated_claim_ids
    assert irrelevant_claim_ids.isdisjoint(hydrated_claim_ids)

    claim_queries: list[str] = []

    def count_claim_queries(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if "orrery:epistemics_hydration" in statement:
            claim_queries.append(statement)

    event.listen(live_connection, "before_cursor_execute", count_claim_queries)
    try:
        hydration = load_epistemics_hydration(live_connection, entity_ids=())
    finally:
        event.remove(live_connection, "before_cursor_execute", count_claim_queries)

    assert hydration.claimed_event_scopes == {}
    assert claim_queries == []


def test_live_predicates_cover_participant_told_common_false_and_faction(
    live_connection: Any,
) -> None:
    """All possession paths hydrate for character and faction knowers."""

    settings = _settings(
        channels={
            "authority_over": {
                "direction": "subject_to_object",
                "latency": "1h",
            }
        }
    )
    raw_connection = live_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        source, source_character = _insert_character(cur, "consume-source")
        listener, listener_character = _insert_character(cur, "consume-listener")
        about, _ = _insert_character(cur, "consume-about")
        common_knower, _ = _insert_character(cur, "consume-common-knower")
        common_about, _ = _insert_character(cur, "consume-common-about")
        no_claim_about, _ = _insert_character(cur, "consume-no-claim")
        faction = _insert_faction(cur, "consume-faction")
        _insert_relationship(cur, source_character, listener_character)
        _insert_pair_tag(cur, source, faction, "authority_over")
        birth_chunk, birth_world_time = _insert_chunk(cur)
        bounded_claim = _insert_claim_about(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            about_entity_id=about,
        )
        _insert_claim_about(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            about_entity_id=common_about,
            scope="common",
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        drained = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=settings
        )
        cur.execute(
            """
            SELECT knower_entity_id, source_tier, acquired_at_world_time
            FROM claim_awareness
            WHERE claim_id = %s
              AND knower_entity_id IN (%s, %s)
            ORDER BY knower_entity_id
            """,
            (bounded_claim, listener, faction),
        )
        stamps = {int(row["knower_entity_id"]): dict(row) for row in cur.fetchall()}

    assert drained.minted_count >= 2
    assert stamps[listener]["source_tier"] == "told"
    assert stamps[faction]["source_tier"] == "told"
    assert stamps[listener]["acquired_at_world_time"] == birth_world_time + timedelta(
        hours=1
    )
    assert stamps[faction]["acquired_at_world_time"] == birth_world_time + timedelta(
        hours=1
    )

    state = hydrate_world_state(
        live_connection,
        anchor_chunk_id=drain_chunk,
        window_chunks=10,
        epistemics_settings=EPISTEMICS,
        contagion_settings=settings,
    )
    about_binding = {Slot.ACTOR: source, Slot.TARGET: about}
    assert knows_claim_about()(state, about_binding)
    assert not heard_secondhand()(state, {Slot.ACTOR: source})
    assert knows_claim_about()(state, {Slot.ACTOR: listener, Slot.TARGET: about})
    assert heard_secondhand()(state, {Slot.ACTOR: listener})
    assert knows_claim_about()(
        state, {Slot.ACTOR: common_knower, Slot.TARGET: common_about}
    )
    assert not knows_claim_about()(
        state, {Slot.ACTOR: common_knower, Slot.TARGET: no_claim_about}
    )
    assert knows_claim_about(Slot.FACTION, Slot.TARGET)(
        state, {Slot.FACTION: faction, Slot.TARGET: about}
    )
    assert heard_secondhand(Slot.FACTION)(state, {Slot.FACTION: faction})


def test_template_gate_flips_on_drain_with_production_explain_parity(
    live_connection: Any,
) -> None:
    """One hydrated template becomes proposable exactly at acquisition."""

    settings = _settings()
    template = _consumption_template()
    raw_connection = live_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        source, source_character = _insert_character(cur, "gate-source")
        listener, listener_character = _insert_character(cur, "gate-listener")
        about, about_character = _insert_character(cur, "gate-about")
        _insert_relationship(cur, source_character, listener_character)
        _insert_relationship(cur, listener_character, about_character)
        birth_chunk, _ = _insert_chunk(cur)
        _insert_claim_about(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            about_entity_id=about,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        _mark_actor_relevant(cur, chunk_id=drain_chunk, actor_entity_id=listener)

        before = resolve_dry_run(
            live_connection,
            [template],
            anchor_chunk_id=drain_chunk,
            window_chunks=10,
            epistemics_settings=EPISTEMICS,
            contagion_settings=settings,
        )
        before_explain = explain_dry_run(
            live_connection,
            [template],
            anchor_chunk_id=drain_chunk,
            window_chunks=10,
            epistemics_settings=EPISTEMICS,
            contagion_settings=settings,
        )
        drained = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=settings
        )
        after = resolve_dry_run(
            live_connection,
            [template],
            anchor_chunk_id=drain_chunk,
            window_chunks=10,
            epistemics_settings=EPISTEMICS,
            contagion_settings=settings,
        )
        after_explain = explain_dry_run(
            live_connection,
            [template],
            anchor_chunk_id=drain_chunk,
            window_chunks=10,
            epistemics_settings=EPISTEMICS,
            contagion_settings=settings,
        )

    def production_has_pair(report: Any) -> bool:
        return any(
            draft.template_id == template.id
            and draft.bindings == {"actor": listener, "target": about}
            for draft in report.resolutions
        )

    def explained_pair(report: Any) -> Any:
        actor = next(
            group for group in report.actors if group.actor_entity_id == listener
        )
        return next(
            stack
            for stack in actor.two_party_stacks
            if stack.bindings == {"actor": listener, "target": about}
        )

    assert drained.minted_count >= 1
    assert not production_has_pair(before)
    assert production_has_pair(after)
    before_stack = explained_pair(before_explain)
    after_stack = explained_pair(after_explain)
    assert before_stack.winner_id is None
    assert after_stack.winner_id == template.id
    evidence = after_stack.templates[0].gate_trace.evidence
    assert evidence is not None
    assert evidence["kind"] == "knows_claim_about"
    assert evidence["result"] is True
    assert {match["tier"] for match in evidence["matched"]} == {"told"}


def test_entity_audit_renders_two_hop_provenance_and_ledger_depth(
    live_connection: Any,
) -> None:
    """The entity knowledge panel resolves a two-hop acquisition end to end."""

    settings = _settings()
    raw_connection = live_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 3)
        source, relay, recipient = entities
        about, _ = _insert_character(cur, "audit-about")
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim_about(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            about_entity_id=about,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=12))
        drained = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=settings
        )

    assert drained.minted_count >= 2
    context = entity_context(
        live_connection,
        [recipient],
        anchor_chunk_id=drain_chunk,
        contagion_settings=settings,
    )
    # This is exactly the dev endpoint's return value, so JSON round-tripping
    # guards the direct audit/dev serialization parity.
    assert json.loads(json.dumps(context)) == context
    entity = context["entities"][0]
    row = next(item for item in entity["knowledge"] if item["claim_id"] == claim_id)
    assert row == {
        "claim_id": claim_id,
        "summary": (
            f"Threat issued: actor Stage 2d source {source}, "
            f"target Stage 2d subject {about}."
        ),
        "scope": "bounded",
        "tier": "told",
        "channel": "dyad:associate",
        "immediate_source": {
            "entity_id": relay,
            "name": row["immediate_source"]["name"],
        },
        "root_source": {
            "entity_id": source,
            "name": row["root_source"]["name"],
        },
        "acquired_at_world_time": (birth_world_time + timedelta(hours=2)).isoformat(),
        "depth": 2,
    }
    assert row["immediate_source"]["name"]
    assert row["root_source"]["name"]
    assert row["immediate_source"]["name"] != row["root_source"]["name"]
    assert [item["claim_id"] for item in entity["knowledge"]] == sorted(
        item["claim_id"] for item in entity["knowledge"]
    )

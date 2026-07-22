"""Live, rollback-only coverage for mechanical mood semantics."""

from datetime import datetime, timedelta, timezone
from dataclasses import replace
import json
from pathlib import Path
import uuid

import asyncpg
import psycopg2
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery.events import (
    MoodPolicy,
    _apply_state_delta_async,
    _apply_state_delta_sync,
    _sweep_expired_entity_tags_sync,
)
from nexus.agents.orrery.explain import explain_template
from nexus.agents.orrery.needs import coerce_need_tuning
from nexus.agents.orrery.replay import _Replayer
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    _load_current_entity_tags,
    compose_actor_bindings,
)
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    BranchSelection,
    ProjectPolicy,
    Slot,
    Template,
    WorldState,
    evaluate,
    mood_is,
    select_branch,
    validate_mood_affinities,
    validate_no_mood_in_entry_gates,
)
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres
NOW = datetime(2073, 5, 3, 12, tzinfo=timezone.utc)


def _migration_sql() -> str:
    return (
        Path(__file__).parents[2] / "migrations" / "095_mood_vocabulary.sql"
    ).read_text()


def _schema_sql() -> str:
    return """
        CREATE TABLE tag_category_registry (
            category text NOT NULL, entity_kind entity_kind NOT NULL,
            prompt_order integer NOT NULL, description text,
            deprecated boolean NOT NULL DEFAULT false,
            replacement_categories text[], PRIMARY KEY (category, entity_kind)
        );
        CREATE TABLE tags (
            id bigserial PRIMARY KEY, tag text UNIQUE NOT NULL,
            category text NOT NULL, is_ephemeral boolean NOT NULL DEFAULT false,
            clearance_kind entity_tag_clearance_kind,
            reapplication_policy entity_tag_reapplication_policy,
            clear_on jsonb, synonym_for bigint,
            deprecated boolean NOT NULL DEFAULT false, description text,
            CHECK (is_ephemeral = (clearance_kind IS NOT NULL))
        );
        CREATE TABLE entity_tags (
            id bigserial PRIMARY KEY, entity_id bigint NOT NULL,
            tag_id bigint NOT NULL REFERENCES tags(id),
            applied_at timestamptz NOT NULL DEFAULT now(),
            applied_at_world_time timestamptz,
            expires_at_world_time timestamptz,
            clear_on_override jsonb, cleared_at timestamptz,
            template_id text, source_kind entity_tag_source_kind NOT NULL,
            source_chunk_id bigint
        );
        CREATE UNIQUE INDEX ix_entity_tags_current
            ON entity_tags (entity_id, tag_id) WHERE cleared_at IS NULL;
        CREATE TABLE tag_clearance_log (
            id bigserial PRIMARY KEY, entity_tag_id bigint,
            mechanism text NOT NULL, cleared_at_world_time timestamptz,
            triggering_event_id bigint, justification jsonb,
            source_chunk_id bigint
        );
        CREATE TABLE chunk_metadata (
            chunk_id bigint PRIMARY KEY, world_time timestamptz
        );
        CREATE TABLE orrery_resolutions (
            id bigserial PRIMARY KEY, tick_chunk_id bigint NOT NULL,
            actor_entity_id bigint, state_delta jsonb NOT NULL
        );
    """


def _draft(mood: str, *, hours: float | None = None) -> OrreryResolutionDraft:
    payload: dict[str, object] = {"mood": mood}
    if hours is not None:
        payload["hours"] = hours
    return OrreryResolutionDraft(
        template_id="mood_test",
        priority=1,
        binding_hash=uuid.uuid4().hex,
        bindings={"actor": 11},
        branch_label="set mood",
        narrative_stub="The actor's disposition changes.",
        state_delta={"mood.set": payload},
        event_type=None,
        changed_fields=("entity_tags",),
        magnitude=0.4,
    )


def _apply_sync(cur: object, draft: OrreryResolutionDraft, chunk_id: int) -> int:
    cur.execute(
        """
        INSERT INTO orrery_resolutions (
            tick_chunk_id, actor_entity_id, state_delta
        ) VALUES (%s, 11, %s::jsonb) RETURNING id
        """,
        (chunk_id, json.dumps(dict(draft.state_delta))),
    )
    resolution_id = cur.fetchone()[0]
    return _apply_state_delta_sync(
        cur,
        draft,
        resolution_id=resolution_id,
        actor_entity_id=11,
        target_entity_id=None,
        source_chunk_id=chunk_id,
        need_tuning=coerce_need_tuning(None),
        project_policy=ProjectPolicy(),
        mood_policy=MoodPolicy(enabled=True, duration_hours=12),
    )


def test_set_displace_expire_snapshot_and_replay() -> None:
    conn = psycopg2.connect(get_slot_db_url(slot=5))
    schema = f"mood_live_{uuid.uuid4().hex}"
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(_schema_sql())
            cur.execute(_migration_sql())
            cur.execute(
                "INSERT INTO chunk_metadata VALUES (1, %s), (2, %s)",
                (NOW, NOW + timedelta(hours=1)),
            )
            assert _apply_sync(cur, _draft("sour", hours=2), 1) == 1
            assert _apply_sync(cur, _draft("elated"), 2) == 2
            cur.execute(
                """
                SELECT t.tag, et.applied_at_world_time,
                       et.expires_at_world_time, et.source_kind::text
                FROM entity_tags et JOIN tags t ON t.id = et.tag_id
                WHERE et.entity_id = 11 AND et.cleared_at IS NULL
                """
            )
            assert cur.fetchone() == (
                "elated",
                NOW + timedelta(hours=1),
                NOW + timedelta(hours=13),
                "template",
            )
            cur.execute(
                """
                SELECT state_delta -> 'mood.set' -> 'applied'
                FROM orrery_resolutions WHERE tick_chunk_id = 2
                """
            )
            applied = cur.fetchone()[0]
            assert applied["mood"] == "elated"
            assert applied["displaced_mood"] == "sour"
            assert (
                applied["expires_at_world_time"]
                == (NOW + timedelta(hours=13)).isoformat()
            )
            assert applied["entity_tag"]["source_chunk_id"] == 2
            cur.execute("SELECT count(*) FROM tag_clearance_log")
            assert cur.fetchone()[0] == 1

            replayer = _Replayer.__new__(_Replayer)
            replayer.cur = cur
            replayer.target_chunk_id = 2
            working: dict[int, dict[str, object]] = {}
            assert replayer._replay_mood_snapshots(working, base_chunk=0) == {11}
            assert len(working) == 1
            assert next(iter(working.values()))["id"] == applied["entity_tag"]["id"]
            cur.execute(
                "INSERT INTO chunk_metadata VALUES (3, %s)",
                (NOW + timedelta(hours=13),),
            )
            assert _sweep_expired_entity_tags_sync(cur, source_chunk_id=3) == 1
            replayer.target_chunk_id = 3
            working = {}
            assert replayer._replay_entity_tag_events(working, base_chunk=0) == {11}
            assert working == {}

            cur.execute(
                "INSERT INTO chunk_metadata VALUES (4, %s)",
                (NOW + timedelta(hours=14),),
            )
            cur.execute("SAVEPOINT before_unknown_mood")
            with pytest.raises(ValueError, match="Unknown mood"):
                _apply_sync(cur, _draft("wistful"), 4)
            cur.execute("ROLLBACK TO SAVEPOINT before_unknown_mood")
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.asyncio
async def test_async_writer_and_disabled_snapshot() -> None:
    conn = await asyncpg.connect(get_slot_db_url(slot=5))
    transaction = conn.transaction()
    await transaction.start()
    schema = f"mood_async_{uuid.uuid4().hex}"
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET LOCAL search_path = "{schema}", public')
        await conn.execute(_schema_sql())
        await conn.execute(_migration_sql())
        await conn.execute(
            "INSERT INTO chunk_metadata VALUES (1, $1), (2, $2)",
            NOW,
            NOW + timedelta(hours=1),
        )
        for chunk_id, enabled in ((1, True), (2, False)):
            draft = _draft("restless")
            resolution_id = await conn.fetchval(
                """
                INSERT INTO orrery_resolutions (
                    tick_chunk_id, actor_entity_id, state_delta
                ) VALUES ($1, 11, $2::jsonb) RETURNING id
                """,
                chunk_id,
                json.dumps(dict(draft.state_delta)),
            )
            await _apply_state_delta_async(
                conn,
                draft,
                resolution_id=resolution_id,
                actor_entity_id=11,
                target_entity_id=None,
                source_chunk_id=chunk_id,
                need_tuning=coerce_need_tuning(None),
                project_policy=ProjectPolicy(),
                mood_policy=MoodPolicy(enabled=enabled, duration_hours=12),
            )
        snapshot = await conn.fetchval(
            """
            SELECT state_delta -> 'mood.set' -> 'applied'
            FROM orrery_resolutions WHERE tick_chunk_id = 2
            """
        )
        assert json.loads(snapshot) == {"skipped": "mood_disabled"}
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM entity_tags WHERE cleared_at IS NULL"
            )
            == 1
        )
    finally:
        await transaction.rollback()
        await conn.close()


def test_expired_unswept_mood_does_not_hydrate_or_bias() -> None:
    engine = create_engine(get_slot_db_url(slot=5), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    schema = f"mood_hydration_{uuid.uuid4().hex}"
    try:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path = "{schema}", public')
        connection.exec_driver_sql(
            """
            CREATE TABLE entity_tags (
                id bigint PRIMARY KEY, expires_at_world_time timestamptz
            );
            INSERT INTO entity_tags VALUES (
                1, '2073-05-03 11:00:00+00'::timestamptz
            );
            CREATE VIEW entity_tags_current AS
            SELECT 1::bigint AS entity_tag_id, 11::bigint AS entity_id,
                   'grim'::text AS tag, true AS is_ephemeral
            """
        )
        with Session(connection) as session:
            tags, ephemeral = _load_current_entity_tags(session, current_world_time=NOW)
        assert tags == {}
        assert ephemeral == {}

        state = WorldState(
            ephemeral_tags={
                entity: frozenset(values) for entity, values in ephemeral.items()
            },
            mood_enabled=True,
            current_tick=7,
        )
        template = Template(
            id="mood_bias",
            priority=1,
            drive_band="anchored_routine",
            blurb="Bias test.",
            required_slots=(Slot.ACTOR,),
            package_gate=ALWAYS,
            branches=(
                Branch("first", ALWAYS, "First.", magnitude=0.4),
                Branch(
                    "second",
                    ALWAYS,
                    "Second.",
                    magnitude=0.4,
                    mood_affinities={"grim": 8.0},
                ),
            ),
        )
        chosen, _ = select_branch(
            template,
            state,
            {Slot.ACTOR: 11},
            digest="fixed",
            selection=BranchSelection(mode="stochastic", temperature=1.0),
        )
        unbiased = replace(
            template,
            branches=tuple(
                Branch(
                    branch.label,
                    branch.conditions,
                    branch.narrative_stub,
                    magnitude=branch.magnitude,
                )
                for branch in template.branches
            ),
        )
        control, _ = select_branch(
            unbiased,
            state,
            {Slot.ACTOR: 11},
            digest="fixed",
            selection=BranchSelection(mode="stochastic", temperature=1.0),
        )
        assert chosen.label == control.label
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_expired_unswept_tag_does_not_source_actor_binding() -> None:
    """An expired ephemeral tag cannot make an otherwise irrelevant actor run."""

    engine = create_engine(get_slot_db_url(slot=5), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    schema = f"mood_binding_{uuid.uuid4().hex}"
    try:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path = "{schema}", public')
        connection.exec_driver_sql(
            """
            CREATE TABLE entities (
                id bigint PRIMARY KEY, kind text NOT NULL, is_active boolean NOT NULL
            );
            INSERT INTO entities VALUES (11, 'character', true);
            CREATE TABLE chunk_metadata (
                chunk_id bigint PRIMARY KEY, world_time timestamptz
            );
            INSERT INTO chunk_metadata VALUES (1, '2073-05-03 12:00:00+00');
            CREATE TABLE chunk_entity_references_v (
                entity_id bigint, reference_type text, chunk_id bigint
            );
            CREATE TABLE world_events (
                actor_entity_id bigint, target_entity_id bigint,
                tick_chunk_id bigint, world_layer text,
                superseded_by_event_id bigint
            );
            CREATE TABLE entity_tags (
                id bigint PRIMARY KEY, entity_id bigint,
                expires_at_world_time timestamptz, cleared_at timestamptz
            );
            INSERT INTO entity_tags VALUES (
                1, 11, '2073-05-03 11:00:00+00', NULL
            );
            CREATE VIEW entity_tags_current AS
            SELECT id AS entity_tag_id, entity_id, true AS is_ephemeral
            FROM entity_tags WHERE cleared_at IS NULL;
            CREATE TABLE pair_tags (
                id bigint PRIMARY KEY, tag text, is_ephemeral boolean,
                deprecated boolean
            );
            CREATE TABLE entity_pair_tags (
                object_entity_id bigint, subject_entity_id bigint,
                pair_tag_id bigint, cleared_at timestamptz
            );
            CREATE TABLE character_routine_anchors (
                character_entity_id bigint, mobility_policy text
            );
            CREATE TABLE characters (id bigint PRIMARY KEY, entity_id bigint);
            CREATE TABLE chunk_character_references (
                chunk_id bigint, character_id bigint, reference text
            );
            """
        )
        with Session(connection) as session:
            bindings = compose_actor_bindings(
                session, anchor_chunk_id=1, window_chunks=1
            )
        assert bindings == ()
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_mood_gate_bias_purity_validation_and_no_magnitude_mutation() -> None:
    state = WorldState(
        ephemeral_tags={11: frozenset({"grim"})},
        mood_enabled=True,
        current_tick=3,
    )
    bindings = {Slot.ACTOR: 11}
    assert mood_is("grim")(state, bindings)
    assert not mood_is("grim")(
        WorldState(ephemeral_tags=state.ephemeral_tags, mood_enabled=False),
        bindings,
    )
    with pytest.raises(ValueError, match="Unknown mood"):
        mood_is("wistful")

    template = Template(
        id="mood_bias",
        priority=1,
        drive_band="anchored_routine",
        blurb="Bias test.",
        required_slots=(Slot.ACTOR,),
        package_gate=ALWAYS,
        branches=(
            Branch("plain", ALWAYS, "Plain.", magnitude=0.4),
            Branch(
                "favored",
                ALWAYS,
                "Favored.",
                magnitude=0.4,
                mood_affinities={"grim": 8.0},
            ),
        ),
    )
    before = tuple(branch.magnitude for branch in template.branches)
    outcomes = [
        select_branch(
            template,
            WorldState(
                ephemeral_tags=state.ephemeral_tags,
                mood_enabled=enabled,
                current_tick=tick,
            ),
            bindings,
            digest="fixed",
            selection=BranchSelection(mode="stochastic", temperature=1.0),
        )[0].label
        for enabled in (False, True)
        for tick in range(64)
    ]
    plain = outcomes[:64].count("favored")
    biased = outcomes[64:].count("favored")
    assert biased > plain
    assert tuple(branch.magnitude for branch in template.branches) == before
    explanation = explain_template(
        template,
        state,
        bindings,
        BranchSelection(mode="stochastic", temperature=1.0),
    )
    favored_trace = next(
        trace for trace in explanation.branches if trace.label == "favored"
    )
    assert favored_trace.applied_mood_affinity == {
        "mood": "grim",
        "multiplier": 8.0,
    }
    assert (
        evaluate(
            template,
            state,
            bindings,
            BranchSelection(mode="authored_order"),
        ).branch_label
        == "plain"
    )

    gated = Template(
        id="bad_gate",
        priority=1,
        drive_band="anchored_routine",
        blurb="Invalid gate.",
        required_slots=(Slot.ACTOR,),
        package_gate=mood_is("grim"),
        branches=(Branch("fallback", ALWAYS, "Fallback."),),
    )
    with pytest.raises(ValueError, match="stage-2/3"):
        validate_no_mood_in_entry_gates((gated,))
    invalid = Template(
        id="bad_affinity",
        priority=1,
        drive_band="anchored_routine",
        blurb="Invalid affinity.",
        required_slots=(Slot.ACTOR,),
        package_gate=ALWAYS,
        branches=(
            Branch(
                "bad",
                ALWAYS,
                "Bad.",
                mood_affinities={"grim": 9.0, "wistful": 1.0},
            ),
        ),
    )
    with pytest.raises(ValueError, match="Invalid mood affinities"):
        validate_mood_affinities((invalid,))

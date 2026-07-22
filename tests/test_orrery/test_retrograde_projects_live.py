"""Live rollback-only coverage for wizard-time Retrograde project seeding."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery.events import (
    _apply_state_delta_sync,
    commit_orrery_tick_sync,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import (
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
from nexus.agents.orrery.resolver import OrreryResolutionDraft, resolve_dry_run
from nexus.agents.orrery.retrograde_expansion import (
    RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
    RetrogradeExpansionPlanResponse,
    RetrogradeProjectPlan,
)
from nexus.agents.orrery.retrograde_orchestrator import (
    RetrogradeGenerationBundle,
    persist_retrograde_history,
)
from nexus.agents.orrery.retrograde_maturation import _persist_maturation_expansion
from nexus.agents.orrery.retrograde_persistence import (
    PROJECT_FIRST_STAGES,
    PROJECT_STARTED_EVENT_TYPES,
    _validate_project_start_dependencies,
    build_retrograde_persistence_plan,
    plan_retrograde_summaries,
)
from nexus.agents.orrery.retrograde_seed_candidates import (
    SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)
from nexus.agents.orrery.substrate import coerce_project_policy
from nexus.agents.orrery.templates import ADVANCE_BUILD_VENTURE
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings

pytestmark = pytest.mark.requires_postgres

PROJECT_TYPES = tuple(PROJECT_FIRST_STAGES)


@pytest.fixture()
def project_db() -> Iterator[dict[str, Any]]:
    """Open save_02 only inside an always-rolled-back transaction."""

    engine = create_engine(get_slot_db_url(slot=2))
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    conn = connection.connection.driver_connection
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.entity_id, c.name
                FROM characters c
                WHERE c.entity_id IS NOT NULL
                ORDER BY c.id
                LIMIT 12
                """
            )
            characters = [(int(row[0]), str(row[1])) for row in cur.fetchall()]
            assert len(characters) >= 12
            cur.execute("SELECT id, name FROM places ORDER BY id LIMIT 2")
            places = [(int(row[0]), str(row[1])) for row in cur.fetchall()]
            assert len(places) >= 2
            actor_ids = [entity_id for entity_id, _name in characters[:8]]
            character_ids = [entity_id for entity_id, _name in characters]
            cur.execute(
                """
                DELETE FROM character_project_states
                WHERE character_entity_id = ANY(%s)
                """,
                (actor_ids,),
            )
            cur.execute(
                """
                DELETE FROM character_relationships cr
                USING characters c1, characters c2
                WHERE cr.character1_id = c1.id
                  AND cr.character2_id = c2.id
                  AND c1.entity_id = ANY(%s)
                  AND c2.entity_id = ANY(%s)
                """,
                (character_ids, character_ids),
            )
        yield {
            "conn": conn,
            "session": session,
            "characters": characters,
            "places": places,
            "vocabulary": enumerate_seed_eligible_vocabulary(dbname="save_02"),
        }
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_writer_inserts_all_types_and_started_events(
    project_db: dict[str, Any],
) -> None:
    db = project_db
    specs = _all_type_specs(db)
    packet, seeds, expansion = _contracts(db["vocabulary"], specs)
    with db["conn"].cursor() as cur:
        manifest = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seeds,
            expansion_plan_payload=expansion,
            slot=2,
            dbname="save_02",
            dry_run=False,
            project_seeding_enabled=True,
            max_seeded_projects=6,
            project_settings=load_settings().orrery.projects,
        )
        assert manifest["counters"]["projects_inserted"] == 6
        assert all(row["status"] == "inserted" for row in manifest["project_rows"])

        project_ids = [row["project_id"] for row in manifest["project_rows"]]
        cur.execute(
            """
            SELECT cps.id, cps.project_type, cps.status, cps.stage,
                   cps.target_place_id, cps.target_character_entity_id,
                   cps.target_faction_entity_id, cps.progress, cps.stall_count,
                   cps.next_eligible_at_world_time, cps.source_chunk_id
            FROM character_project_states cps
            WHERE cps.id = ANY(%s)
            ORDER BY cps.id
            """,
            (project_ids,),
        )
        persisted = cur.fetchall()
        assert len(persisted) == 6
        cur.execute("SELECT base_timestamp FROM global_variables WHERE id = true")
        base_timestamp = cur.fetchone()[0]
        assert base_timestamp is not None
        for row in persisted:
            project_type = str(row[1])
            assert row[2] == "active"
            assert row[3] == PROJECT_FIRST_STAGES[project_type]
            assert row[6] is None
            assert float(row[7]) == 0.0
            assert row[8] == 0
            assert row[9] == base_timestamp + timedelta(hours=24)
            assert row[10] == manifest["prologue_anchor"]["chunk_id"]
            if project_type == "build_venture":
                assert row[4] is None and row[5] is None

        event_ids = [row["started_event_id"] for row in manifest["project_rows"]]
        cur.execute(
            """
            SELECT event_type, source::text, tick_chunk_id, payload
            FROM world_events
            WHERE id = ANY(%s)
            ORDER BY id
            """,
            (event_ids,),
        )
        events = cur.fetchall()
        assert {row[0] for row in events} == set(PROJECT_STARTED_EVENT_TYPES.values())
        assert all(row[1] == "retrograde" for row in events)
        assert all(row[2] == manifest["prologue_anchor"]["chunk_id"] for row in events)
        for _event_type, _source, _chunk, payload in events:
            assert set(payload) == {"seed_ids", "project_intent", "actor", "target"}
            assert payload["project_intent"] is True


def test_writer_dedup_cap_disabled_and_unresolvable_are_loud(
    project_db: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = project_db
    actor = db["characters"][0][1]
    target = db["characters"][8][1]
    specs = [
        ("seed_first", "build_venture", actor, None),
        ("seed_second", "recruit_ally", actor, target),
        ("seed_cap_1", "build_venture", db["characters"][1][1], None),
        ("seed_cap_2", "build_venture", db["characters"][2][1], None),
        ("seed_cap_3", "build_venture", db["characters"][3][1], None),
    ]
    packet, seeds, expansion = _contracts(db["vocabulary"], specs)
    caplog.set_level(logging.WARNING)
    with db["conn"].cursor() as cur:
        manifest = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seeds,
            expansion_plan_payload=expansion,
            slot=2,
            dbname="save_02",
            dry_run=True,
            project_seeding_enabled=True,
            max_seeded_projects=3,
            project_settings=load_settings().orrery.projects,
        )
        assert [row["status"] for row in manifest["project_rows"]] == [
            "would_insert",
            "dropped_duplicate_actor",
            "would_insert",
            "would_insert",
            "dropped_cap",
        ]
        assert "seed_second" in caplog.text and "seed_first" in caplog.text
        assert "cast-wide cap 3" in caplog.text

        caplog.clear()
        disabled = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seeds,
            expansion_plan_payload=expansion,
            slot=2,
            dbname="save_02",
            dry_run=True,
            project_seeding_enabled=False,
        )
        assert disabled["counters"]["projects_would_insert"] == 0
        assert disabled["counters"]["projects_dropped_disabled"] == len(specs)
        assert "project seeding is disabled" in caplog.text

    broken_specs = [("seed_broken", "recruit_ally", actor, "No Such Person")]
    packet, seeds, expansion = _contracts(db["vocabulary"], broken_specs)
    with db["conn"].cursor() as cur:
        with pytest.raises(ValueError, match="seed_broken.*unresolvable target"):
            build_retrograde_persistence_plan(
                cur,
                packet=packet,
                seed_candidate_response=seeds,
                expansion_plan_payload=expansion,
                slot=2,
                dbname="save_02",
                dry_run=True,
                project_seeding_enabled=True,
                project_settings=load_settings().orrery.projects,
            )


def test_cap_dropped_projects_do_not_claim_actor_keys(
    project_db: dict[str, Any],
) -> None:
    """Cap rejects never become false duplicate-actor winners."""

    db = project_db
    specs = [
        ("seed_a", "build_venture", db["characters"][0][1], None),
        ("seed_b1", "build_venture", db["characters"][1][1], None),
        ("seed_b2", "build_venture", db["characters"][1][1], None),
    ]
    packet, seeds, expansion = _contracts(db["vocabulary"], specs)
    with db["conn"].cursor() as cur:
        manifest = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seeds,
            expansion_plan_payload=expansion,
            slot=2,
            dbname="save_02",
            dry_run=False,
            project_seeding_enabled=True,
            max_seeded_projects=1,
            project_settings=load_settings().orrery.projects,
        )

    assert [row["status"] for row in manifest["project_rows"]] == [
        "inserted",
        "dropped_cap",
        "dropped_cap",
    ]
    assert manifest["counters"]["projects_inserted"] == 1
    assert manifest["counters"]["projects_dropped_cap"] == 2
    assert manifest["counters"]["projects_dropped_duplicate_actor"] == 0
    assert all(
        row.get("winning_seed_id") is None for row in manifest["project_rows"][1:]
    )


def test_dropped_project_targets_do_not_create_entity_stubs(
    project_db: dict[str, Any],
) -> None:
    """Only accepted project targets participate in entity stub planning."""

    db = project_db
    nonce = uuid4().hex[:10]
    accepted_target = f"Accepted Target {nonce}"
    dropped_target = f"Dropped Target {nonce}"
    specs = [
        (
            "seed_accepted_stub",
            "recruit_ally",
            db["characters"][0][1],
            accepted_target,
        ),
        (
            "seed_dropped_stub",
            "recruit_ally",
            db["characters"][1][1],
            dropped_target,
        ),
    ]
    packet, seeds, expansion = _contracts(db["vocabulary"], specs)
    with db["conn"].cursor() as cur:
        manifest = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seeds,
            expansion_plan_payload=expansion,
            slot=2,
            dbname="save_02",
            dry_run=False,
            create_missing_entities=True,
            project_seeding_enabled=True,
            max_seeded_projects=1,
            project_settings=load_settings().orrery.projects,
        )
        cur.execute(
            "SELECT name FROM characters WHERE name = ANY(%s) ORDER BY name",
            ([accepted_target, dropped_target],),
        )
        created_names = [str(row[0]) for row in cur.fetchall()]

    project_stub_rows = [
        row
        for row in manifest["entity_stub_rows"]
        if any(
            source["plan"] == "project_plan" and source["role"] == "target"
            for source in row["sources"]
        )
    ]
    assert [(row["entity_ref"], row["status"]) for row in project_stub_rows] == [
        (accepted_target, "inserted")
    ]
    assert dropped_target not in {
        row["entity_ref"] for row in manifest["entity_stub_rows"]
    }
    assert created_names == [accepted_target]


def test_seek_redemption_requires_target_to_actor_negative_valence(
    project_db: dict[str, Any],
) -> None:
    db = project_db
    actor_id, actor = db["characters"][0]
    target_id, target = db["characters"][8]
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            DELETE FROM character_relationships cr
            USING characters target_c, characters actor_c
            WHERE cr.character1_id = target_c.id
              AND cr.character2_id = actor_c.id
              AND target_c.entity_id = %s
              AND actor_c.entity_id = %s
            """,
            (target_id, actor_id),
        )
        specs = [("seed_redemption", "seek_redemption", actor, target)]
        packet, seeds, expansion = _contracts(
            db["vocabulary"],
            specs,
            include_redemption_wrong=False,
        )
        with pytest.raises(ValueError, match="wary-or-worse"):
            build_retrograde_persistence_plan(
                cur,
                packet=packet,
                seed_candidate_response=seeds,
                expansion_plan_payload=expansion,
                slot=2,
                dbname="save_02",
                dry_run=True,
                project_seeding_enabled=True,
                project_settings=load_settings().orrery.projects,
            )


def test_writer_rejects_project_participants_in_death_plan(
    project_db: dict[str, Any],
) -> None:
    db = project_db
    actor_id, actor_ref = db["characters"][0]
    target_id, target_ref = db["characters"][8]
    elsewhere_ref = db["characters"][9][1]
    project = RetrogradeProjectPlan.model_validate(
        {
            "seed_id": "seed_dead_participant",
            "project_type": "court_patron",
            "actor_ref": actor_ref,
            "target_ref": target_ref,
            "rationale": "The patronage arc starts at stage one.",
        }
    )
    actor = {
        "resolution": "resolved",
        "entity_id": actor_id,
        "entity_ref": actor_ref,
    }
    target = {
        "resolution": "resolved",
        "entity_id": target_id,
        "entity_ref": target_ref,
    }

    def expansion_with_death(entity_ref: str) -> RetrogradeExpansionPlanResponse:
        return RetrogradeExpansionPlanResponse.model_validate(
            {
                "selected_seed_ids": [project.seed_id],
                "death_plan": [
                    {
                        "entity_ref": entity_ref,
                        "entity_kind": "character",
                    }
                ],
                "project_plan": [project.model_dump(mode="json")],
            }
        )

    with db["conn"].cursor() as cur:
        with pytest.raises(
            ValueError,
            match="seed_dead_participant.*actor_ref.*death_plan",
        ):
            _validate_project_start_dependencies(
                cur,
                expansion=expansion_with_death(actor_ref.upper()),
                project=project,
                actor=actor,
                target=target,
            )
        with pytest.raises(
            ValueError,
            match="seed_dead_participant.*character target_ref.*death_plan",
        ):
            _validate_project_start_dependencies(
                cur,
                expansion=expansion_with_death(target_ref.upper()),
                project=project,
                actor=actor,
                target=target,
            )
        _validate_project_start_dependencies(
            cur,
            expansion=expansion_with_death(elsewhere_ref),
            project=project,
            actor=actor,
            target=target,
        )


def test_wizard_genesis_checkpoint_carries_seeded_project_through_replay(
    project_db: dict[str, Any],
) -> None:
    db = project_db
    actor_id, actor = db["characters"][0]
    specs = [("seed_replay", "build_venture", actor, None)]
    packet, seeds, expansion = _contracts(db["vocabulary"], specs)
    settings = load_settings()
    assert settings.orrery is not None
    bundle = RetrogradeGenerationBundle(
        slot=2,
        dbname="save_02",
        model="test",
        weird={"level": "medium"},
        packet=packet,
        seed_candidate_response=seeds,
        expansion_plan=expansion,
        timings=[],
    )
    with db["conn"].cursor() as cur:
        # Force this rollback-only run to create a fresh highest-id prologue,
        # so its genesis checkpoint is a truthful chronological replay base.
        cur.execute(
            """
            UPDATE narrative_chunks
            SET authorial_directives = '[]'::jsonb
            WHERE COALESCE(authorial_directives, '[]'::jsonb)
                  @> '["retrograde_prologue"]'::jsonb
            """
        )
        cur.execute("DELETE FROM state_checkpoints WHERE label = 'genesis'")
        manifest = persist_retrograde_history(
            cur,
            bundle=bundle,
            settings=settings,
        )
        base_id = manifest["genesis_checkpoint"]["id"]
        prologue_chunk = manifest["genesis_checkpoint"]["chunk_id"]
        with pytest.raises(
            RuntimeError,
            match=rf"checkpoint {base_id} already exists at prologue chunk "
            rf"{prologue_chunk}",
        ):
            persist_retrograde_history(
                cur,
                bundle=bundle,
                settings=settings,
            )
        cur.execute(
            """
            SELECT state -> 'character_project_states'
            FROM state_checkpoints WHERE id = %s
            """,
            (base_id,),
        )
        project_rows = cur.fetchone()[0]
        assert any(row["character_entity_id"] == actor_id for row in project_rows)

        cur.execute(
            """
            SELECT next_eligible_at_world_time
            FROM character_project_states
            WHERE character_entity_id = %s AND status = 'active'
            """,
            (actor_id,),
        )
        advance_time = cur.fetchone()[0]
        advance_chunk = _fabricate_chunk(cur, advance_time)
        _apply_project_advance(
            cur,
            chunk_id=advance_chunk,
            actor_entity_id=actor_id,
            project_settings=settings.orrery.projects,
        )
        target_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=advance_chunk,
            label="manual",
        )
        assert target_id is not None
        pair = [
            verdict
            for verdict in verify_checkpoints_sync(cur)
            if verdict.base_checkpoint_id == base_id
            and verdict.target_checkpoint_id == target_id
        ]
        assert len(pair) == 1
        assert pair[0].base_chunk_id == prologue_chunk
        assert pair[0].drifts == []


def test_maturation_seeds_only_target_actor_and_logs_advisory_drops(
    project_db: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Runtime arbitration admits one target-owned project and nothing else."""

    db = project_db
    actor_id, actor = db["characters"][0]
    foreign = db["characters"][1][1]
    specs = [
        ("seed_foreign", "build_venture", foreign, None),
        ("seed_target", "build_venture", actor, None),
        ("seed_second", "build_venture", actor, None),
    ]
    packet, seeds, expansion = _contracts(db["vocabulary"], specs)
    with db["conn"].cursor() as cur:
        request_chunk = _fabricate_chunk(cur, _next_world_time(cur))
        caplog.set_level(logging.WARNING)
        manifest = _persist_maturation_expansion(
            cur,
            packet=packet,
            seed_response=seeds,
            expansion_payload=expansion,
            row={
                "job_id": 531001,
                "entity_id": actor_id,
                "requesting_chunk_id": request_chunk,
            },
            slot=2,
            dbname="save_02",
            settings=load_settings(),
            summaries_enabled=False,
        )

        assert [row["status"] for row in manifest["project_rows"]] == [
            "dropped_foreign_actor",
            "inserted",
            "dropped_cap",
        ]
        assert manifest["counters"]["projects_inserted"] == 1
        assert "Maturation job 531001" in caplog.text
        assert "seed_foreign" in caplog.text
        assert "seed_second" in caplog.text

        inserted = manifest["project_rows"][1]
        cur.execute(
            """
            SELECT event_type, source::text, tick_chunk_id, payload
            FROM world_events WHERE id = %s
            """,
            (inserted["started_event_id"],),
        )
        event_type, source, tick_chunk_id, payload = cur.fetchone()
        assert event_type == "build_venture_started"
        # event_source_kind has no maturation label; payload provenance is the
        # bounded discriminator while canonical Retrograde storage stays valid.
        assert source == "retrograde"
        assert tick_chunk_id == request_chunk
        assert payload["source"] == "maturation"
        assert payload["retrograde_event_ref"].startswith("maturation_job_531001_")
        assert set(payload["applied"]) == {
            "project_type",
            "status",
            "stage",
            "target_place_id",
            "target_character_entity_id",
            "target_faction_entity_id",
            "progress",
            "stall_count",
            "next_eligible_at_world_time",
            "source_chunk_id",
        }
        assert payload["applied"]["source_chunk_id"] == request_chunk


def test_maturation_shared_writer_validation_raises(
    project_db: dict[str, Any],
) -> None:
    """Target shape, dead participant, and unresolved actor stay fail-fast."""

    db = project_db
    actor_id, actor = db["characters"][0]
    target = db["characters"][8][1]
    settings = load_settings()

    cases: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []

    packet, seeds, expansion = _contracts(
        db["vocabulary"], [("seed_bad_shape", "build_venture", actor, None)]
    )
    seeds["candidates"][0]["project_intent"]["target_ref"] = target
    expansion["project_plan"][0]["target_ref"] = target
    cases.append(("bad shape", seeds, expansion, "build_venture.*target"))

    packet_dead, seeds_dead, expansion_dead = _contracts(
        db["vocabulary"], [("seed_dead", "build_venture", actor, None)]
    )
    expansion_dead["death_plan"] = [
        {
            "entity_ref": actor,
            "entity_kind": "character",
            "cause_event_ref": expansion_dead["event_plan"][0]["event_ref"],
        }
    ]
    cases.append(("dead actor", seeds_dead, expansion_dead, "death_plan"))

    packet_missing, seeds_missing, expansion_missing = _contracts(
        db["vocabulary"],
        [("seed_missing_actor", "build_venture", "No Such Actor", None)],
    )
    cases.append(
        (
            "missing actor",
            seeds_missing,
            expansion_missing,
            "unresolvable actor",
        )
    )

    with db["conn"].cursor() as cur:
        request_chunk = _fabricate_chunk(cur, _next_world_time(cur))
        for label, case_seeds, case_expansion, match in cases:
            case_packet = {
                "bad shape": packet,
                "dead actor": packet_dead,
                "missing actor": packet_missing,
            }[label]
            with pytest.raises((ValueError, ValidationError), match=match):
                _persist_maturation_expansion(
                    cur,
                    packet=case_packet,
                    seed_response=case_seeds,
                    expansion_payload=case_expansion,
                    row={
                        "job_id": 531002,
                        "entity_id": actor_id,
                        "requesting_chunk_id": request_chunk,
                    },
                    slot=2,
                    dbname="save_02",
                    settings=settings,
                    summaries_enabled=False,
                )


def test_maturation_disabled_config_drops_intent_loudly(
    project_db: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = project_db
    actor_id, actor = db["characters"][0]
    packet, seeds, expansion = _contracts(
        db["vocabulary"], [("seed_disabled", "build_venture", actor, None)]
    )
    settings = load_settings()
    assert settings.orrery is not None
    disabled_retrograde = settings.orrery.retrograde.model_copy(
        update={
            "projects": settings.orrery.retrograde.projects.model_copy(
                update={"enabled": False}
            )
        }
    )
    disabled_settings = settings.model_copy(
        update={
            "orrery": settings.orrery.model_copy(
                update={"retrograde": disabled_retrograde}
            )
        }
    )
    with db["conn"].cursor() as cur:
        request_chunk = _fabricate_chunk(cur, _next_world_time(cur))
        caplog.set_level(logging.WARNING)
        manifest = _persist_maturation_expansion(
            cur,
            packet=packet,
            seed_response=seeds,
            expansion_payload=expansion,
            row={
                "job_id": 531003,
                "entity_id": actor_id,
                "requesting_chunk_id": request_chunk,
            },
            slot=2,
            dbname="save_02",
            settings=disabled_settings,
            summaries_enabled=False,
        )
    assert manifest["counters"]["projects_dropped_disabled"] == 1
    assert "Maturation job 531003" in caplog.text
    assert "seed_disabled" in caplog.text
    assert "project seeding is disabled" in caplog.text


def test_summary_backfill_excludes_wizard_and_maturation_project_starts(
    project_db: dict[str, Any],
) -> None:
    """Mechanical started events share one exclusion from prose summaries."""

    db = project_db
    settings = load_settings()
    assert settings.orrery is not None
    _wizard_id, wizard_actor = db["characters"][0]
    maturation_id, maturation_actor = db["characters"][1]
    wizard_packet, wizard_seeds, wizard_expansion = _contracts(
        db["vocabulary"],
        [("seed_wizard_summary", "build_venture", wizard_actor, None)],
    )
    maturation_packet, maturation_seeds, maturation_expansion = _contracts(
        db["vocabulary"],
        [("seed_maturation_summary", "build_venture", maturation_actor, None)],
    )

    with db["conn"].cursor() as cur:
        wizard_manifest = build_retrograde_persistence_plan(
            cur,
            packet=wizard_packet,
            seed_candidate_response=wizard_seeds,
            expansion_plan_payload=wizard_expansion,
            slot=2,
            dbname="save_02",
            dry_run=False,
            project_seeding_enabled=True,
            project_settings=settings.orrery.projects,
        )
        assert wizard_manifest["counters"]["projects_inserted"] == 1

        request_chunk = _fabricate_chunk(cur, _next_world_time(cur))
        maturation_manifest = _persist_maturation_expansion(
            cur,
            packet=maturation_packet,
            seed_response=maturation_seeds,
            expansion_payload=maturation_expansion,
            row={
                "job_id": 531008,
                "entity_id": maturation_id,
                "requesting_chunk_id": request_chunk,
            },
            slot=2,
            dbname="save_02",
            settings=settings,
            summaries_enabled=True,
        )
        assert maturation_manifest["counters"]["projects_inserted"] == 1

        started_event_ids = {
            int(wizard_manifest["project_rows"][0]["started_event_id"]),
            int(maturation_manifest["project_rows"][0]["started_event_id"]),
        }
        rows = plan_retrograde_summaries(cur, dry_run=False)
        assert started_event_ids.isdisjoint(
            int(row["world_event_id"])
            for row in rows
            if row["world_event_id"] is not None
        )
        cur.execute(
            """
            SELECT count(*) FROM retrograde_summaries
            WHERE world_event_id = ANY(%s)
            """,
            (list(started_event_ids),),
        )
        assert cur.fetchone()[0] == 0


def test_maturation_project_replays_exactly_and_hydrates_continuation(
    project_db: dict[str, Any],
) -> None:
    """A mid-arc start survives a later checkpoint with no project drift."""

    db = project_db
    actor_id, actor = db["characters"][0]
    packet, seeds, expansion = _contracts(
        db["vocabulary"], [("seed_mid_arc", "build_venture", actor, None)]
    )
    settings = load_settings()
    assert settings.orrery is not None
    with db["conn"].cursor() as cur:
        base_time = _next_world_time(cur)
        expected_due_time = base_time + timedelta(
            hours=1 + settings.orrery.projects.advance_interval_hours
        )
        cur.execute(
            "DELETE FROM character_travel_states WHERE character_entity_id = %s",
            (actor_id,),
        )
        cur.execute(
            """
            UPDATE character_need_states
            SET debt_score = 0, last_evaluated_at = %s
            WHERE character_entity_id = %s
            """,
            (expected_due_time, actor_id),
        )
        base_chunk = _fabricate_chunk(cur, base_time)
        base_id = capture_state_checkpoint_sync(
            cur, chunk_id=base_chunk, label="manual"
        )
        assert base_id is not None

        request_chunk = _fabricate_chunk(cur, base_time + timedelta(hours=1))
        manifest = _persist_maturation_expansion(
            cur,
            packet=packet,
            seed_response=seeds,
            expansion_payload=expansion,
            row={
                "job_id": 531004,
                "entity_id": actor_id,
                "requesting_chunk_id": request_chunk,
            },
            slot=2,
            dbname="save_02",
            settings=settings,
            summaries_enabled=False,
        )
        project_row = next(
            row for row in manifest["project_rows"] if row["status"] == "inserted"
        )
        due_time = project_row["next_eligible_at_world_time"]
        assert due_time == expected_due_time
        advance_chunk = _fabricate_chunk(cur, due_time)
        proposal = resolve_dry_run(
            db["session"],
            (ADVANCE_BUILD_VENTURE,),
            anchor_chunk_id=advance_chunk,
            window_chunks=30,
            project_settings=settings.orrery.projects,
        )
        continuation = next(
            draft
            for draft in proposal.resolutions
            if draft.template_id == ADVANCE_BUILD_VENTURE.id
            and draft.bindings.get("actor") == actor_id
        )
        assert continuation.branch_label == "Make the venture legible"
        assert "project.advance" in continuation.state_delta

        commit_orrery_tick_sync(
            db["conn"],
            proposal,
            tick_chunk_id=advance_chunk,
            project_settings=settings.orrery.projects,
            adjudications=[
                {
                    "proposal_id": draft.proposal_id,
                    "action": "defer",
                    "note": "isolate the maturation continuation seam",
                }
                for draft in proposal.resolutions
                if draft.proposal_id != continuation.proposal_id
            ],
        )
        target_id = capture_state_checkpoint_sync(
            cur, chunk_id=advance_chunk, label="manual"
        )
        assert target_id is not None

        replayed = reconstruct_state_at_sync(
            cur, advance_chunk, base_checkpoint_id=base_id
        )
        assert not any(
            section == "character_project_states"
            for section, _row_id in replayed.uncertain_rows
        )
        pair = [
            verdict
            for verdict in verify_checkpoints_sync(cur)
            if verdict.base_checkpoint_id == base_id
            and verdict.target_checkpoint_id == target_id
        ]
        assert len(pair) == 1
        assert pair[0].drifts == []


def test_maturation_start_at_base_chunk_replays_without_drift(
    project_db: dict[str, Any],
) -> None:
    """Step 8.6 base starts are newer than their Step 8.55 checkpoint."""

    db = project_db
    actor_id, actor = db["characters"][0]
    packet, seeds, expansion = _contracts(
        db["vocabulary"], [("seed_base_edge", "build_venture", actor, None)]
    )
    settings = load_settings()
    with db["conn"].cursor() as cur:
        base_time = _next_world_time(cur)
        base_chunk = _fabricate_chunk(cur, base_time)
        base_id = capture_state_checkpoint_sync(
            cur, chunk_id=base_chunk, label="manual"
        )
        assert base_id is not None

        manifest = _persist_maturation_expansion(
            cur,
            packet=packet,
            seed_response=seeds,
            expansion_payload=expansion,
            row={
                "job_id": 531006,
                "entity_id": actor_id,
                "requesting_chunk_id": base_chunk,
            },
            slot=2,
            dbname="save_02",
            settings=settings,
            summaries_enabled=False,
        )
        assert any(row["status"] == "inserted" for row in manifest["project_rows"])
        target_chunk = _fabricate_chunk(cur, base_time + timedelta(hours=1))
        target_id = capture_state_checkpoint_sync(
            cur, chunk_id=target_chunk, label="manual"
        )
        assert target_id is not None

        replayed = reconstruct_state_at_sync(
            cur, target_chunk, base_checkpoint_id=base_id
        )
        assert any(
            row["character_entity_id"] == actor_id
            and row["project_type"] == "build_venture"
            for row in replayed.state["character_project_states"]
        )
        pair = [
            verdict
            for verdict in verify_checkpoints_sync(cur)
            if verdict.base_checkpoint_id == base_id
            and verdict.target_checkpoint_id == target_id
        ]
        assert len(pair) == 1
        assert pair[0].drifts == []


def test_maturation_start_at_target_chunk_is_absent_without_drift(
    project_db: dict[str, Any],
) -> None:
    """Step 8.6 target starts are newer than their Step 8.55 checkpoint."""

    db = project_db
    actor_id, actor = db["characters"][0]
    packet, seeds, expansion = _contracts(
        db["vocabulary"], [("seed_target_edge", "build_venture", actor, None)]
    )
    settings = load_settings()
    with db["conn"].cursor() as cur:
        base_time = _next_world_time(cur)
        base_chunk = _fabricate_chunk(cur, base_time)
        base_id = capture_state_checkpoint_sync(
            cur, chunk_id=base_chunk, label="manual"
        )
        assert base_id is not None
        target_chunk = _fabricate_chunk(cur, base_time + timedelta(hours=1))
        target_id = capture_state_checkpoint_sync(
            cur, chunk_id=target_chunk, label="manual"
        )
        assert target_id is not None

        manifest = _persist_maturation_expansion(
            cur,
            packet=packet,
            seed_response=seeds,
            expansion_payload=expansion,
            row={
                "job_id": 531007,
                "entity_id": actor_id,
                "requesting_chunk_id": target_chunk,
            },
            slot=2,
            dbname="save_02",
            settings=settings,
            summaries_enabled=False,
        )
        assert any(row["status"] == "inserted" for row in manifest["project_rows"])

        replayed = reconstruct_state_at_sync(
            cur, target_chunk, base_checkpoint_id=base_id
        )
        assert not any(
            row["character_entity_id"] == actor_id
            and row["project_type"] == "build_venture"
            for row in replayed.state["character_project_states"]
        )
        pair = [
            verdict
            for verdict in verify_checkpoints_sync(cur)
            if verdict.base_checkpoint_id == base_id
            and verdict.target_checkpoint_id == target_id
        ]
        assert len(pair) == 1
        assert pair[0].drifts == []


def test_maturation_started_event_requires_applied_projection_in_replay(
    project_db: dict[str, Any],
) -> None:
    db = project_db
    actor_id, _actor = db["characters"][0]
    with db["conn"].cursor() as cur:
        base_time = _next_world_time(cur)
        base_chunk = _fabricate_chunk(cur, base_time)
        base_id = capture_state_checkpoint_sync(
            cur, chunk_id=base_chunk, label="manual"
        )
        assert base_id is not None
        event_chunk = _fabricate_chunk(cur, base_time + timedelta(hours=1))
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, world_layer,
                source, changed_fields, payload
            ) VALUES (
                'build_venture_started', %s, %s,
                'primary'::world_layer_type,
                'retrograde'::event_source_kind,
                ARRAY['character_project_states'],
                %s::jsonb
            )
            """,
            (
                event_chunk,
                actor_id,
                json.dumps(
                    {
                        "source": "maturation",
                        "retrograde_event_ref": (
                            "maturation_job_531005_project_missing_applied"
                        ),
                    }
                ),
            ),
        )
        target_chunk = _fabricate_chunk(cur, base_time + timedelta(hours=2))
        with pytest.raises(ValueError, match="missing its required applied"):
            reconstruct_state_at_sync(cur, target_chunk, base_checkpoint_id=base_id)


def _next_world_time(cur: Any) -> datetime:
    cur.execute("SELECT max(world_time) FROM chunk_metadata")
    value = cur.fetchone()[0]
    assert value is not None
    return value + timedelta(hours=24)


def _all_type_specs(db: Mapping[str, Any]) -> list[tuple[str, str, str, str | None]]:
    characters = db["characters"]
    places = db["places"]
    return [
        ("seed_relocation", "plan_relocation", characters[0][1], places[0][1]),
        ("seed_recruit", "recruit_ally", characters[1][1], characters[8][1]),
        ("seed_venture", "build_venture", characters[2][1], None),
        ("seed_romance", "pursue_romance", characters[3][1], characters[9][1]),
        ("seed_patron", "court_patron", characters[4][1], characters[10][1]),
        ("seed_redemption", "seek_redemption", characters[5][1], characters[11][1]),
    ]


def _contracts(
    vocabulary: SeedEligibleVocabulary,
    specs: Sequence[tuple[str, str, str, str | None]],
    *,
    include_redemption_wrong: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    nonce = uuid4().hex[:10]
    coverage = [
        {"id": "unresolved_ledger"},
        {"id": "trait_bound_hook"},
        {"id": "opening_pressure"},
    ]
    packet = {
        "seed_generation_request": {
            "budget": {
                "generate_candidates": max(12, len(specs)),
                "select_target": max(12, len(specs)),
            },
            "coverage_functions": coverage,
            "candidate_graph": {},
            "prompt_sections": [],
        },
        "seed_eligible_vocabulary": vocabulary,
    }
    candidates = []
    events = []
    threads = []
    projects = []
    selected = []
    event_type = str(vocabulary["event_types"][0])
    for index, (seed_id, project_type, actor_ref, target_ref) in enumerate(specs):
        seed_key = f"{seed_id}_{nonce}"
        event_ref = f"project_event_{nonce}_{index}"
        selected.append(seed_key)
        candidates.append(
            {
                "seed_id": seed_key,
                "summary": f"{actor_ref} carries an unfinished long-arc intent.",
                "origin_friction": "medium",
                "present_leaf_anchor": "The intent remains active at story start.",
                "coverage_functions": ["unresolved_ledger"],
                "mechanical_hints": {},
                "defer_or_reject_if": [],
                "claimed_edges": [],
                "project_intent": {
                    "project_type": project_type,
                    "target_ref": target_ref,
                    "rationale": "Generated history creates a live project.",
                },
            }
        )
        events.append(
            {
                "event_ref": event_ref,
                "seed_ids": [seed_key],
                "event_type": event_type,
                "summary": f"An old record left {actor_ref} with unfinished work.",
                "chronology": "recent_past",
                "participants": [
                    {
                        "entity_ref": actor_ref,
                        "entity_kind": "character",
                        "role": "actor",
                    }
                ],
                "changed_fields": [],
                "payload": [],
            }
        )
        threads.append(
            {
                "seed_id": seed_key,
                "status": "woven",
                "event_refs": [event_ref],
                "present_leaf_anchor": "The project is active at story start.",
            }
        )
        projects.append(
            {
                "seed_id": seed_key,
                "project_type": project_type,
                "actor_ref": actor_ref,
                "target_ref": target_ref,
                "rationale": "Begin at the first stage without skipped milestones.",
            }
        )

    relationships = []
    if include_redemption_wrong:
        negative_type = next(
            relationship_type
            for relationship_type in ("enemy", "rival", "captor")
            if relationship_type in vocabulary["relationship_types"]
        )
        for seed_id, project_type, actor_ref, target_ref in specs:
            if project_type != "seek_redemption":
                continue
            relationships.append(
                {
                    "subject_ref": target_ref,
                    "subject_kind": "character",
                    "relationship_type": negative_type,
                    "object_ref": actor_ref,
                    "object_kind": "character",
                    "rationale": f"{seed_id} names the wrong being amended.",
                }
            )
    seed_response = {
        "schema_version": SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
        "candidates": candidates,
        "selected_seed_ids": selected,
        "rejected_seed_ids": [],
    }
    expansion = {
        "schema_version": RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
        "selected_seed_ids": selected,
        "event_plan": events,
        "entity_tag_plan": [],
        "pair_tag_plan": [],
        "relationship_plan": relationships,
        "death_plan": [],
        "project_plan": projects,
        "thread_plan": threads,
        "coverage_notes": [],
        "commit_readiness": {
            "writes": "none",
            "planned_source": "retrograde",
            "blocked_by": [
                "pre_game_tick_chunk_id",
                "event_source_kind_retrograde",
            ],
            "explanation": "Dry-run plan only.",
        },
    }
    return packet, seed_response, expansion


def _fabricate_chunk(cur: Any, world_time: datetime) -> int:
    cur.execute(
        """
        INSERT INTO narrative_chunks (id, raw_text, created_at)
        SELECT max(id) + 1, 'retrograde project replay probe', now()
        FROM narrative_chunks
        RETURNING id
        """
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO chunk_metadata (chunk_id, world_time) VALUES (%s, %s)",
        (chunk_id, world_time),
    )
    cur.execute(
        "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
        (world_time, chunk_id),
    )
    return chunk_id


def _apply_project_advance(
    cur: Any,
    *,
    chunk_id: int,
    actor_entity_id: int,
    project_settings: Any,
) -> None:
    state_delta = {"project.advance": {"progress_delta": 0.25}}
    cur.execute(
        """
        INSERT INTO orrery_resolutions (
            tick_chunk_id, template_id, binding_hash, actor_entity_id,
            priority, magnitude, state_delta
        ) VALUES (%s, 'retrograde_replay_probe', %s, %s, 50, 0.4, %s::jsonb)
        RETURNING id
        """,
        (
            chunk_id,
            f"retrograde-project-{chunk_id}",
            actor_entity_id,
            json.dumps(state_delta),
        ),
    )
    resolution_id = int(cur.fetchone()[0])
    draft = OrreryResolutionDraft(
        template_id="retrograde_replay_probe",
        priority=50,
        binding_hash=f"retrograde-project-{chunk_id}",
        bindings={"actor": actor_entity_id},
        branch_label="project progress",
        narrative_stub="project progress",
        state_delta=state_delta,
        magnitude=0.4,
    )
    _apply_state_delta_sync(
        cur,
        draft,
        resolution_id=resolution_id,
        actor_entity_id=actor_entity_id,
        target_entity_id=None,
        source_chunk_id=chunk_id,
        need_tuning=load_need_tuning(),
        project_policy=coerce_project_policy(project_settings),
    )

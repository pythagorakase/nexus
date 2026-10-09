"""Real PostgreSQL coverage for the dev-gated Backstage endpoint."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests
from sqlalchemy import text
from sqlalchemy.orm import Session
import tomlkit

from nexus.agents.orrery.backstage import BackstagePayloadError, build_backstage_turn
from nexus.agents.orrery.relationship_provenance import relationship_producer
from nexus.agents.orrery.retrograde_persistence import (
    _ensure_prologue_metadata,
    _insert_prologue_chunk,
)
from nexus.agents.orrery.tag_writer import apply_pair_tag_bestowal
from nexus.api import backstage_endpoints, commit_handler_sync
from nexus.memory.correspondence import (
    CorrespondenceCompactionPlan,
    insert_digest_version,
)
from nexus.config import load_settings
from nexus.database import create_slot_engine, database_url
from nexus.memory.manager import empty_pass2_baseline
from tests.pg_fixtures import (
    assert_one_target,
    connect,
    disposable_slot_database,
    seed_played_story,
    seed_protagonist,
)
from tests.scheduler_helpers import (
    gateway_lane,
    route_slot,
    run_cli,
    test_provider_config as configure_test,
)
from tests.test_api.test_attempt_manifest_pg import (
    FIXTURE_CAST,
    FIXTURE_TURN_GAP,
    _stage_pending_turn,
)
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401


pytestmark = pytest.mark.requires_postgres


def _route_backstage_to(monkeypatch: pytest.MonkeyPatch, dbname: str) -> None:
    """Resolve the endpoint's slot-4 URL to ``dbname`` through the contract."""

    def fixture_slot_url(*, slot: int) -> str:
        if slot != 4:
            raise ValueError("slot_number must be between 1 and 5")
        return database_url(dbname)

    monkeypatch.setattr(backstage_endpoints, "get_slot_db_url", fixture_slot_url)


def _stage_incubator(
    cur: Any,
    *,
    chunk_id: int,
    parent_chunk_id: int,
    session_id: str,
    storyteller_text: str,
    entity_updates: dict[str, Any],
    writer_letter: str | None = None,
    gaia_letter: str | None = None,
) -> None:
    """Stage one fixture turn for the genuine synchronous commit handler."""

    cur.execute(
        """
        INSERT INTO incubator (
            id, chunk_id, parent_chunk_id, user_text,
            storyteller_text, metadata_updates, entity_updates,
            reference_updates, correspondence_writer_letter,
            correspondence_gaia_letter, session_id, llm_response_id,
            status, generation_model, lore_pass_baseline,
            orrery_adjudications, new_entities
        ) VALUES (
            TRUE, %s, %s, 'continue', %s, %s::jsonb, %s::jsonb,
            %s::jsonb, %s, %s, %s, %s, 'provisional', 'TEST', %s::jsonb,
            '[]'::jsonb, '[]'::jsonb
        )
        """,
        (
            chunk_id,
            parent_chunk_id,
            storyteller_text,
            json.dumps(
                {
                    "chronology": {
                        "episode_transition": "continue",
                        "time_delta_hours": 1,
                    },
                    "world_layer": "primary",
                }
            ),
            json.dumps(entity_updates),
            json.dumps({"characters": [], "places": [], "factions": []}),
            writer_letter,
            gaia_letter,
            session_id,
            f"backstage-response-{chunk_id}",
            json.dumps(empty_pass2_baseline(load_settings()).model_dump(mode="json")),
        ),
    )


@pytest.fixture(scope="module")
def disposable_db() -> Iterator[str]:
    """Yield a template clone that seeding and the endpoint both resolve."""

    with disposable_slot_database("qa640_778s6a_backstage") as dbname:
        assert_one_target(dbname)
        yield dbname


@pytest.fixture(scope="module")
def empty_disposable_db() -> Iterator[str]:
    """Yield a second template clone with no committed chunks."""

    with disposable_slot_database("qa640_778s6a_empty") as dbname:
        assert_one_target(dbname)
        yield dbname


@pytest.fixture(scope="module")
def backstage_case(disposable_db: str) -> dict[str, Any]:
    """Persist every Backstage stream through real writer/query paths."""

    seed_protagonist(disposable_db, base_timestamp="2189-10-17T18:00:00+00:00")
    conn = connect(disposable_db)
    try:
        with conn:
            with conn.cursor() as cur:
                prologue_id = _insert_prologue_chunk(cur)
                assert prologue_id == 1
                _ensure_prologue_metadata(cur, prologue_chunk_id=prologue_id)

                chunk_ids: list[int] = []
                for number in range(1, 3):
                    cur.execute(
                        "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
                        "VALUES (%s, %s) "
                        "RETURNING id",
                        (
                            f"Backstage committed turn {number}",
                            f"Backstage committed turn {number}",
                        ),
                    )
                    chunk_id = int(cur.fetchone()[0])
                    chunk_ids.append(chunk_id)
                    cur.execute(
                        """
                        INSERT INTO chunk_metadata (
                            chunk_id, season, episode, scene, world_layer,
                            time_delta, generation_date, slug
                        ) VALUES (
                            %s, 1, 1, %s, 'primary', interval '1 minute',
                            now(), %s
                        )
                        """,
                        (chunk_id, number, f"S01E01_{number:03d}"),
                    )

                cur.execute("INSERT INTO entities (kind) VALUES ('place') RETURNING id")
                place_entity = int(cur.fetchone()[0])
                cur.execute(
                    "INSERT INTO places (name, type, entity_id) "
                    "VALUES ('Rootline', 'fixed_location', %s) RETURNING id",
                    (place_entity,),
                )
                place_id = int(cur.fetchone()[0])
                cur.execute(
                    "INSERT INTO entities (kind) VALUES "
                    "('character'), ('character') RETURNING id"
                )
                first_entity, second_entity = [int(row[0]) for row in cur.fetchall()]
                cur.execute(
                    """
                    INSERT INTO characters (name, entity_id, current_location)
                    VALUES ('Celia', %s, %s), ('Victor', %s, %s)
                    RETURNING id
                    """,
                    (first_entity, place_id, second_entity, place_id),
                )
                first_character, second_character = [
                    int(row[0]) for row in cur.fetchall()
                ]
                with relationship_producer(cur, "manual"):
                    cur.execute(
                        """
                        INSERT INTO character_relationships (
                            character1_id, character2_id, relationship_type,
                            emotional_valence, valence_current, dynamic,
                            recent_events, history
                        ) VALUES
                            (%s, %s, 'acquaintance', '0|neutral', 0,
                             'quiet', 'none', 'fixture'),
                            (%s, %s, 'acquaintance', '0|neutral', 0,
                             'quiet', 'none', 'fixture')
                        """,
                        (
                            first_character,
                            second_character,
                            second_character,
                            first_character,
                        ),
                    )
                cur.execute(
                    """
                    UPDATE global_variables SET user_character = %s WHERE id = TRUE
                    """,
                    (first_character,),
                )
                prior_session_id = str(uuid.uuid4())
                parent_chunk_id = chunk_ids[-1]
                _stage_incubator(
                    cur,
                    chunk_id=parent_chunk_id + 1,
                    parent_chunk_id=parent_chunk_id,
                    session_id=prior_session_id,
                    storyteller_text="Victor answers Celia's signal.",
                    entity_updates={
                        "characters": [],
                        "relationships": [
                            {
                                "character1_id": second_character,
                                "character1_name": "Victor",
                                "character2_id": first_character,
                                "character2_name": "Celia",
                                "dynamic": "watchfulness becomes a shared habit",
                                "recent_events": "Celia answered Victor's signal",
                            }
                        ],
                        "locations": [],
                        "factions": [],
                    },
                )

        prior_relationship_chunk = (
            commit_handler_sync.commit_incubator_to_database_sync(
                conn,
                prior_session_id,
                slot=None,
            )
        )
        chunk_ids.append(prior_relationship_chunk)
        assert chunk_ids == [2, 3, 4]

        session_id = str(uuid.uuid4())
        with conn:
            with conn.cursor() as cur:
                _stage_incubator(
                    cur,
                    chunk_id=prior_relationship_chunk + 1,
                    parent_chunk_id=prior_relationship_chunk,
                    session_id=session_id,
                    storyteller_text="Celia watches the Rootline.",
                    entity_updates={
                        "characters": [
                            {
                                "character_id": first_character,
                                "character_name": "Celia",
                                "current_activity": "watching the Rootline",
                                "orrery_tags": {
                                    "applied_tags": ["grieving"],
                                    "tags_to_clear": ["grieving"],
                                },
                            }
                        ],
                        "relationships": [
                            {
                                "character1_id": first_character,
                                "character1_name": "Celia",
                                "character2_id": second_character,
                                "character2_name": "Victor",
                                "relationship_type": "friend",
                                "emotional_valence": "+2|friendly",
                                "dynamic": "trust sharpened by shared danger",
                                "recent_events": "Victor kept watch",
                            }
                        ],
                        "locations": [],
                        "factions": [],
                    },
                    writer_letter="Keep Celia's suspicion beneath the prose.",
                    gaia_letter=("Acknowledged; the durable state remains quiet."),
                )

        latest = commit_handler_sync.commit_incubator_to_database_sync(
            conn,
            session_id,
            slot=None,
        )
        chunk_ids.append(latest)
        assert chunk_ids == [2, 3, 4, 5]

        with conn:
            with conn.cursor() as cur:
                assert apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=second_entity,
                    object_entity_id=first_entity,
                    subject_kind="character",
                    object_kind="character",
                    tag="hunting",
                    source_chunk_id=latest,
                )
                plan = CorrespondenceCompactionPlan(
                    accepting_chunk_id=latest,
                    compacted_through_chunk_id=chunk_ids[1],
                    previous_digest=None,
                    aging_exchanges=(),
                    recent_exchanges=(),
                )
                insert_digest_version(
                    cur,
                    plan=plan,
                    digest="Victor is cultivating Celia as an informant.",
                )

                cur.execute(
                    """
                    INSERT INTO orrery_adjudication_log (
                        tick_chunk_id, proposal_id, template_id, binding_hash,
                        action, actor_entity_id, bindings
                    ) VALUES (
                        %s, 'open-proposal', 'evade_pursuers', 'held-binding',
                        'defer', %s, %s::jsonb
                    )
                    """,
                    (latest, first_entity, f'{{"actor": {first_entity}}}'),
                )
                cur.execute(
                    """
                    INSERT INTO orrery_resolutions (
                        tick_chunk_id, template_id, binding_hash,
                        actor_entity_id, priority, magnitude, state_delta, brief
                    ) VALUES (
                        %s, 'evade_pursuers', 'resolution-binding', %s,
                        100, 0.75, '{}'::jsonb, 'Celia moves toward safety.'
                    ) RETURNING id
                    """,
                    (latest, first_entity),
                )
                resolution_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO orrery_scene_pressures (
                        tick_chunk_id, template_id, binding_hash,
                        actor_entity_id, target_entity_id, priority, magnitude,
                        branch_label, pressure_stub, prompt_text, bindings
                    ) VALUES (
                        %s, 'evade_pursuers', 'resolution-binding', %s, %s,
                        100, 0.75, 'danger closes in', 'pressure', 'prompt',
                        '{}'::jsonb
                    )
                    """,
                    (latest, first_entity, second_entity),
                )
                cur.execute(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, actor_entity_id,
                        target_entity_id, world_layer, source, changed_fields,
                        magnitude, resolution_id, payload
                    ) VALUES (
                        'threat_issued', %s, %s, %s, 'primary', 'resolver',
                        '{}', 0.75, %s, '{}'::jsonb
                    ) RETURNING id
                    """,
                    (latest, first_entity, second_entity, resolution_id),
                )
                event_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO world_event_entities (event_id, role, entity_id)
                    VALUES (%s, 'target', %s)
                    """,
                    (event_id, second_entity),
                )

                provisional_id = latest + 1000
                provisional_session = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO incubator (
                        id, chunk_id, parent_chunk_id, user_text,
                        storyteller_text, metadata_updates, entity_updates,
                        reference_updates, session_id, llm_response_id, status,
                        generation_model, lore_pass_baseline
                    ) VALUES (
                        TRUE, %s, %s, 'continue', 'provisional secret',
                        '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, %s, 'response',
                        'pending', 'TEST', '{}'::jsonb
                    )
                    """,
                    (provisional_id, latest, provisional_session),
                )
    finally:
        conn.close()

    return {
        "chunks": chunk_ids,
        "latest": chunk_ids[-1],
        "prior_relationship_chunk": prior_relationship_chunk,
        "prologue": prologue_id,
        "provisional": provisional_id,
        "provisional_session": provisional_session,
    }


@pytest.fixture()
def client(
    disposable_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Route the genuine Backstage endpoint to the disposable slot."""

    _route_backstage_to(monkeypatch, disposable_db)
    app = FastAPI()
    app.include_router(backstage_endpoints.router)
    return TestClient(app)


def test_payload_assembles_every_committed_stream(
    client: TestClient,
    backstage_case: dict[str, Any],
    disposable_db: str,
) -> None:
    response = client.get("/api/dev/backstage/4/turn")
    assert response.status_code == 200
    payload = response.json()

    with closing(connect(disposable_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
            (backstage_case["latest"],),
        )
        expected_clock = cur.fetchone()[0]
    assert datetime.fromisoformat(payload["header"]["world_time"]) == expected_clock
    assert payload["header"] == {
        "slot": 4,
        "chunk_id": backstage_case["latest"],
        "chunk_label": "S01E01_004",
        "turn_label": "t.4",
        "world_time": expected_clock.isoformat().replace("+00:00", "Z"),
        "elapsed_seconds": 3600,
        "skald_status": "idle",
    }
    correspondence = payload["correspondence"]
    assert correspondence["digest"] == "Victor is cultivating Celia as an informant."
    assert correspondence["digest_fresh"] is True
    assert correspondence["exchanges"][0]["turn_label"] == "t.4"
    assert [letter["seat"] for letter in correspondence["exchanges"][0]["letters"]] == [
        "writer",
        "gaia",
    ]
    assert correspondence["held_threads"] == [
        {
            "template_id": "evade_pursuers",
            "actor_name": "Celia",
            "streak_length": 1,
            "start_tick": backstage_case["latest"],
            "start_turn_label": "t.4",
        }
    ]

    writes = payload["state_writes"]["rows"]
    relationship_writes = [
        row
        for row in writes
        if row["kind"] == "relation"
        and row["operation"] == "set"
        and row["field"] == "valence"
    ]
    # #888 removed passive co-presence drift; only the authored valence changes.
    assert [row["held"] for row in relationship_writes] == [False]
    changed_relationship_fields = {
        row["field"]
        for row in writes
        if row["kind"] == "relation" and row["operation"] == "set"
    }
    assert changed_relationship_fields == {
        "valence",
        "relationship_type",
        "dynamic",
        "recent_events",
    }
    relationship_rows = {
        row["field"]: row
        for row in writes
        if row["kind"] == "relation"
        and row["operation"] == "set"
        and row["field"] != "valence"
    }
    assert relationship_rows["relationship_type"]["old_value"] == "acquaintance"
    assert relationship_rows["relationship_type"]["new_value"] == "friend"
    assert relationship_rows["dynamic"]["old_value"] == "quiet"
    assert (
        relationship_rows["dynamic"]["new_value"] == "trust sharpened by shared danger"
    )
    assert relationship_rows["recent_events"]["old_value"] == "none"
    assert relationship_rows["recent_events"]["new_value"] == "Victor kept watch"
    assert any(row["field"] == "characters.current_activity" for row in writes)
    assert any(
        row["operation"] == "bestow" and row["field"] == "grieving" for row in writes
    )
    assert any(
        row["operation"] == "clear" and row["mechanism"] == "authored" for row in writes
    )
    assert any(
        row["operation"] == "bestow" and row["field"] == "hunting" for row in writes
    )
    assert payload["state_writes"]["history"] == [
        {
            "chunk_id": backstage_case["prior_relationship_chunk"],
            "turn_label": "t.3",
            "writes": 2,
            "fired": None,
            "pressures": None,
            "events": None,
        },
        {
            "chunk_id": backstage_case["chunks"][1],
            "turn_label": "t.2",
            "writes": 0,
            "fired": None,
            "pressures": None,
            "events": None,
        },
    ]

    orrery = payload["orrery"]
    assert orrery["counts"] == {"fired": 1, "pressures": 1, "events": 2}
    assert orrery["rows"] == [
        {
            "template_id": "evade_pursuers",
            "actor_name": "Celia",
            "target_name": "Victor",
            "magnitude": 0.75,
            "brief": "Celia moves toward safety.",
            "branch_label": "danger closes in",
            "event_type": "threat_issued",
            "drive_band": "crisis_constraint",
            "attention": None,
            "proposal_id": "evade_pursuers:resolution-binding",
            "position": None,
            "binding_names": {},
            "evaluated_at": None,
        }
    ]
    assert [entry["turn_label"] for entry in orrery["history"]] == ["t.3", "t.2"]


def test_payload_reports_known_branch_attention(
    client: TestClient,
    backstage_case: dict[str, Any],
    disposable_db: str,
) -> None:
    """Real endpoint assembly resolves both classes on a template-only clone."""

    chunk_id = backstage_case["chunks"][0]
    expected = {
        ("stroll", "Pace the near ground"): "background",
        ("evade_pursuers", "Go to ground in flooded tunnels"): "meaningful",
    }
    resolution_ids: list[int] = []
    pressure_ids: list[int] = []
    try:
        with closing(connect(disposable_db)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "SELECT orrery_proposal FROM narrative_chunks WHERE id = %s",
                (chunk_id,),
            )
            assert cur.fetchone()[0] is None
            cur.execute("SELECT entity_id FROM characters WHERE name = 'Celia'")
            actor_id = int(cur.fetchone()[0])
            for template_id, branch_label in expected:
                binding_hash = f"attention-proof-{template_id}"
                cur.execute(
                    """
                    INSERT INTO orrery_resolutions (
                        tick_chunk_id, template_id, binding_hash,
                        actor_entity_id, priority, magnitude, state_delta, brief
                    ) VALUES (%s, %s, %s, %s, 1, 0.25, '{}'::jsonb, %s)
                    RETURNING id
                    """,
                    (chunk_id, template_id, binding_hash, actor_id, branch_label),
                )
                resolution_ids.append(int(cur.fetchone()[0]))
                cur.execute(
                    """
                    INSERT INTO orrery_scene_pressures (
                        tick_chunk_id, template_id, binding_hash,
                        actor_entity_id, priority, magnitude, branch_label,
                        pressure_stub, prompt_text, bindings
                    ) VALUES (%s, %s, %s, %s, 1, 0.25, %s,
                              'attention proof', 'attention proof', '{}'::jsonb)
                    RETURNING id
                    """,
                    (chunk_id, template_id, binding_hash, actor_id, branch_label),
                )
                pressure_ids.append(int(cur.fetchone()[0]))

        response = client.get(
            "/api/dev/backstage/4/turn", params={"chunk_id": chunk_id}
        )
        assert response.status_code == 200
        orrery = response.json()["orrery"]
        for key in ("rows", "inventory"):
            rows = orrery[key]
            assert len(rows) == len(expected) == 2
            assert {
                (row["template_id"], row["branch_label"]): row["attention"]
                for row in rows
            } == expected
    finally:
        with closing(connect(disposable_db)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM orrery_scene_pressures WHERE id = ANY(%s)",
                (pressure_ids,),
            )
            cur.execute(
                "DELETE FROM orrery_resolutions WHERE id = ANY(%s)",
                (resolution_ids,),
            )


def test_history_counts_field_level_relationship_writes(
    client: TestClient,
    backstage_case: dict[str, Any],
) -> None:
    latest = client.get("/api/dev/backstage/4/turn").json()
    prior_chunk_id = backstage_case["prior_relationship_chunk"]
    prior = client.get(
        "/api/dev/backstage/4/turn",
        params={"chunk_id": prior_chunk_id},
    )
    assert prior.status_code == 200
    prior_writes = prior.json()["state_writes"]["rows"]

    assert {
        (row["field"], row["old_value"], row["new_value"]) for row in prior_writes
    } == {
        ("dynamic", "quiet", "watchfulness becomes a shared habit"),
        ("recent_events", "none", "Celia answered Victor's signal"),
    }
    history_line = next(
        line
        for line in latest["state_writes"]["history"]
        if line["chunk_id"] == prior_chunk_id
    )
    assert history_line["writes"] == len(prior_writes) == 2


def test_requested_chunk_is_historically_bounded(
    client: TestClient,
    backstage_case: dict[str, Any],
) -> None:
    response = client.get(
        "/api/dev/backstage/4/turn",
        params={"chunk_id": backstage_case["chunks"][1]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["header"]["chunk_id"] == backstage_case["chunks"][1]
    assert payload["header"]["turn_label"] == "t.2"
    assert payload["correspondence"]["digest"] is None
    assert payload["correspondence"]["digest_fresh"] is False
    assert payload["correspondence"]["exchanges"] == []


def test_empty_and_provisional_chunks_are_404(
    client: TestClient,
    backstage_case: dict[str, Any],
) -> None:
    missing = client.get(
        "/api/dev/backstage/4/turn",
        params={"chunk_id": backstage_case["provisional"]},
    )
    assert missing.status_code == 404
    assert "Committed chunk" in missing.json()["detail"]

    retrograde = client.get(
        "/api/dev/backstage/4/turn",
        params={"chunk_id": backstage_case["prologue"]},
    )
    assert retrograde.status_code == 404
    assert "Committed chunk" in retrograde.json()["detail"]


def test_empty_slot_is_404(
    empty_disposable_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _route_backstage_to(monkeypatch, empty_disposable_db)
    app = FastAPI()
    app.include_router(backstage_endpoints.router)
    response = TestClient(app).get("/api/dev/backstage/4/turn")
    assert response.status_code == 404
    assert response.json() == {"detail": "The slot has no committed story turns"}


def test_bad_slot_is_structured_400() -> None:
    app = FastAPI()
    app.include_router(backstage_endpoints.router)
    response = TestClient(app).get("/api/dev/backstage/9/turn")
    assert response.status_code == 400
    assert response.json() == {"detail": "slot_number must be between 1 and 5"}


def test_backstage_gate_both_arms(
    tmp_path: Path,
    disposable_db: str,
    backstage_case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tomlkit

    import nexus.api.narrative as narrative

    document = tomlkit.parse(Path("nexus.toml").read_text())
    document["orrery"]["dashboard"]["enabled"] = False  # type: ignore[index]
    off_path = tmp_path / "backstage_off.toml"
    off_path.write_text(tomlkit.dumps(document))
    original_routes = list(narrative.app.router.routes)
    try:
        narrative.app.router.routes[:] = [
            route
            for route in original_routes
            if not str(getattr(route, "path", "")).startswith("/api/dev/backstage")
        ]
        narrative._include_backstage_router(
            narrative.app,
            load_settings(str(off_path)),
        )
        gateway = TestClient(narrative.app)
        assert not [
            route
            for route in narrative.app.router.routes
            if str(getattr(route, "path", "")).startswith("/api/dev/backstage")
        ]
        # Which catch-all answers a gated-off path depends on the checkout:
        # a built ui/dist mounts the SPA (real 404 for api/ paths), while a
        # dist-less checkout registers the missing-build 503 route.
        off_health = gateway.get("/api/dev/backstage/health")
        assert off_health.status_code in (404, 503)
        off_turn = gateway.get("/api/dev/backstage/4/turn")
        assert off_turn.status_code in (404, 503)
        assert "correspondence" not in off_turn.text

        catch_all = [
            route
            for route in narrative.app.router.routes
            if str(getattr(route, "path", "")) == "/{full_path:path}"
            or (
                str(getattr(route, "path", "")) in ("", "/")
                and getattr(route, "name", "") == "ui"
            )
        ]
        assert len(catch_all) == 1
        narrative.app.router.routes[:] = [
            route for route in narrative.app.router.routes if route not in catch_all
        ]

        document["orrery"]["dashboard"]["enabled"] = True  # type: ignore[index]
        on_path = tmp_path / "backstage_on.toml"
        on_path.write_text(tomlkit.dumps(document))
        _route_backstage_to(monkeypatch, disposable_db)
        enabled_settings = load_settings(str(on_path))
        narrative._include_backstage_router(narrative.app, enabled_settings)
        narrative.app.router.routes.extend(catch_all)

        on_health = gateway.get("/api/dev/backstage/health")
        assert on_health.status_code == 200
        assert on_health.json() == {"ok": True}
        on_response = gateway.get("/api/dev/backstage/4/turn")
        assert on_response.status_code == 200
        assert "correspondence" in on_response.json()

        route_count = len(
            [
                route
                for route in narrative.app.routes
                if str(getattr(route, "path", "")).startswith("/api/dev/backstage")
            ]
        )
        assert route_count == 2
        narrative._include_backstage_router(narrative.app, enabled_settings)
        assert (
            len(
                [
                    route
                    for route in narrative.app.routes
                    if str(getattr(route, "path", "")).startswith("/api/dev/backstage")
                ]
            )
            == route_count
        )
    finally:
        narrative.app.router.routes[:] = original_routes


def test_incubator_view_never_exposes_staged_correspondence(
    disposable_db: str,
    backstage_case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nexus.api.narrative as narrative

    del backstage_case
    monkeypatch.setattr(
        narrative,
        "get_db_connection",
        lambda slot=None: connect(disposable_db),
    )
    response = TestClient(narrative.app).get(
        "/api/narrative/incubator", params={"slot": 4}
    )
    assert response.status_code == 200
    payload = response.json()
    assert "correspondence_writer_letter" not in payload
    assert "correspondence_gaia_letter" not in payload


def test_backstage_clock_equals_selected_chunk(
    client: TestClient,
    backstage_case: dict[str, Any],
    disposable_db: str,
) -> None:
    """Latest and explicitly selected earlier turns expose their own SQL clocks."""
    clocks = []
    for chunk_id, params in (
        (backstage_case["latest"], {}),
        (backstage_case["chunks"][1], {"chunk_id": backstage_case["chunks"][1]}),
    ):
        response = client.get("/api/dev/backstage/4/turn", params=params)
        assert response.status_code == 200
        with closing(connect(disposable_db)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s", (chunk_id,)
            )
            expected = cur.fetchone()[0]
        header = response.json()["header"]
        assert header["chunk_id"] == chunk_id
        assert datetime.fromisoformat(header["world_time"]) == expected
        clocks.append(expected)
    assert clocks[0] > clocks[1]


def test_backstage_header_elapsed_world_time(
    client: TestClient,
    backstage_case: dict[str, Any],
    disposable_db: str,
) -> None:
    """Fails if elapsed time is absent or counts the non-playable prologue."""
    chunks = backstage_case["chunks"]
    assert chunks == [2, 3, 4, 5]
    elapsed = []
    for index, chunk_id in enumerate(chunks):
        response = client.get(
            "/api/dev/backstage/4/turn", params={"chunk_id": chunk_id}
        )
        assert response.status_code == 200, response.text
        seconds = response.json()["header"]["elapsed_seconds"]
        elapsed.append(seconds)
        if index:
            with closing(connect(disposable_db)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT extract(epoch FROM "
                    "(selected.world_time - previous.world_time)) "
                    "FROM chunk_metadata selected CROSS JOIN chunk_metadata previous "
                    "WHERE selected.chunk_id = %s AND previous.chunk_id = %s",
                    (chunk_id, chunks[index - 1]),
                )
                assert seconds == int(cur.fetchone()[0])
    assert elapsed == [None, 60, 3600, 3600]


def test_backstage_header_missing_world_time_is_500(
    client: TestClient,
    backstage_case: dict[str, Any],
    disposable_db: str,
) -> None:
    """Fails if a missing prior clock silently becomes null or a zero delta."""
    previous, selected = backstage_case["chunks"][-2:]
    assert (previous, selected) == (4, 5)
    engine = create_slot_engine(database_url(disposable_db))
    try:
        with Session(engine) as session:
            try:
                session.execute(text("SET LOCAL session_replication_role = replica"))
                session.execute(
                    text(
                        "UPDATE chunk_metadata SET world_time = NULL "
                        "WHERE chunk_id = :chunk_id"
                    ),
                    {"chunk_id": previous},
                )
                with pytest.raises(BackstagePayloadError) as error:
                    build_backstage_turn(session, slot=4, chunk_id=selected)
                assert error.value.status_code == 500
                assert error.value.detail == (
                    f"Committed chunk {selected} or its previous turn {previous} "
                    "has no world_time"
                )
            finally:
                session.rollback()
    finally:
        engine.dispose()
    response = client.get("/api/dev/backstage/4/turn", params={"chunk_id": selected})
    assert response.status_code == 200, response.text
    assert response.json()["header"]["elapsed_seconds"] == 3600


def test_economics_legacy_and_unbound_pending_are_unavailable(
    client: TestClient, backstage_case: dict[str, Any]
) -> None:
    """Fails if legacy reads escape, the pending parent is ignored, or data vanishes."""
    response = client.get("/api/dev/backstage/4/turn")
    assert response.status_code == 200, response.text
    payload = response.json()
    latest = backstage_case["latest"]
    provisional = backstage_case["provisional_session"]
    assert payload["economics"]["accepted"] == {
        "status": "unavailable",
        "generation_session": None,
        "detail": (
            f"chunk {latest}: no generation session "
            "(accepted before session binding)"
        ),
        "observation": None,
    }
    assert payload["economics"]["pending"] == {
        "status": "unavailable",
        "generation_session": provisional,
        "detail": (
            f"session {provisional}: no generation session "
            "(staged before session binding)"
        ),
        "observation": None,
    }
    assert payload["correspondence"]["exchanges"]
    assert payload["state_writes"]["rows"]
    assert payload["orrery"]["rows"]
    earlier = client.get(
        "/api/dev/backstage/4/turn",
        params={"chunk_id": backstage_case["chunks"][1]},
    )
    assert earlier.status_code == 200, earlier.text
    assert earlier.json()["economics"]["pending"] is None


def _without_read_at(observation: dict[str, Any]) -> dict[str, Any]:
    """Remove only the read instant; every schema-3 value remains an oracle."""
    return {key: value for key, value in observation.items() if key != "read_at"}


def test_economics_matches_inspect_turn_for_a_test_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """Fails on another session, changed observation data or post-acceptance pending."""
    # The provider fixture must first see private runtime state and TEST-only use.
    config = configure_test(tmp_path, "http://127.0.0.1:1", monkeypatch)
    provider = request.getfixturevalue("mock_openai_server")
    configure_test(tmp_path, provider, monkeypatch)
    doc = tomlkit.parse(config.read_text())
    doc["storyteller"]["correspondence"]["floor_turns"] = 1
    config.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "0")
    with disposable_slot_database("qa640_uib_turn") as dbname:
        route_slot(monkeypatch, dbname)
        _route_backstage_to(monkeypatch, dbname)
        seed_played_story(
            dbname,
            turns=3,
            cast=FIXTURE_CAST,
            time_delta=FIXTURE_TURN_GAP,
            correspondence=True,
            slot=4,
        )
        prior_session = _stage_pending_turn(dbname)
        app = FastAPI()
        app.include_router(backstage_endpoints.router)
        with TestClient(app) as backstage:
            with gateway_lane(monkeypatch):
                output = run_cli(
                    monkeypatch, "continue", "--slot", "4", "--choice", "1", "--json"
                )
                assert json.loads(output)["success"], output
                with closing(connect(dbname)) as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT session_id::text, parent_chunk_id FROM incubator"
                    )
                    pending_session, parent_chunk = cur.fetchone()
                response = backstage.get("/api/dev/backstage/4/turn")
                assert response.status_code == 200, response.text
                payload = response.json()
                pending = payload["economics"]["pending"]
                assert pending["status"] == "observed"
                assert pending["generation_session"] == pending_session
                assert pending["detail"] is None
                observation = pending["observation"]
                assert observation["schema_version"] == 3
                assert {item["seat"] for item in observation["attempts"]} >= {
                    "skald_writer",
                    "gaia",
                }
                cli_observation = json.loads(
                    run_cli(
                        monkeypatch,
                        "inspect-turn",
                        "--slot",
                        "4",
                        "--session",
                        pending_session,
                        "--json",
                    )
                )["observation"]
                assert _without_read_at(observation) == _without_read_at(
                    cli_observation
                )
                with closing(connect(dbname)) as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT session_id::text FROM narrative_generation_sessions "
                        "WHERE chunk_id = %s AND terminal_outcome = 'accepted'",
                        (payload["header"]["chunk_id"],),
                    )
                    assert cur.fetchall() == [(prior_session,)]
                assert payload["header"]["chunk_id"] == parent_chunk
                assert payload["economics"]["accepted"]["status"] == "observed"
                assert (
                    payload["economics"]["accepted"]["generation_session"]
                    == prior_session
                )
                approved = requests.post(
                    f"{os.environ['NEXUS_API_URL']}/api/narrative/approve/"
                    f"{pending_session}?slot=4&commit=true",
                    timeout=120,
                )
                assert approved.status_code == 200, approved.text
            # The fixture stopped and joined its workers, so job states now hold.
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT chunk_id FROM narrative_generation_sessions "
                    "WHERE session_id = %s AND terminal_outcome = 'accepted'",
                    (pending_session,),
                )
                (accepted_chunk,) = cur.fetchone()
                cur.execute(
                    "SELECT extract(epoch FROM "
                    "(selected.world_time - parent.world_time)) "
                    "FROM chunk_metadata selected CROSS JOIN chunk_metadata parent "
                    "WHERE selected.chunk_id = %s AND parent.chunk_id = %s",
                    (accepted_chunk, parent_chunk),
                )
                elapsed_seconds = int(cur.fetchone()[0])
            response = backstage.get("/api/dev/backstage/4/turn")
            assert response.status_code == 200, response.text
            payload = response.json()
            accepted = payload["economics"]["accepted"]
            assert payload["header"]["chunk_id"] == accepted_chunk
            assert payload["header"]["elapsed_seconds"] == elapsed_seconds
            assert accepted["status"] == "observed"
            assert accepted["generation_session"] == pending_session
            assert accepted["detail"] is None
            assert payload["economics"]["pending"] is None
            cli_observation = json.loads(
                run_cli(
                    monkeypatch,
                    "inspect-turn",
                    "--slot",
                    "4",
                    "--chunk",
                    str(accepted_chunk),
                    "--json",
                )
            )["observation"]
            assert _without_read_at(accepted["observation"]) == _without_read_at(
                cli_observation
            )

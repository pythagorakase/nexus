"""Real PostgreSQL coverage for the dev-gated Backstage endpoint."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import psycopg2  # type: ignore[import-untyped]
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2 import sql
import pytest

from nexus.agents.orrery.retrograde_persistence import (
    _ensure_prologue_metadata,
    _insert_prologue_chunk,
)
from nexus.agents.orrery.tag_writer import apply_pair_tag_bestowal
from nexus.api import backstage_endpoints, commit_handler_sync, db_pool
from nexus.memory.correspondence import (
    CorrespondenceCompactionPlan,
    insert_digest_version,
)
from nexus.config import load_settings
from nexus.memory.manager import empty_pass2_baseline
from scripts import new_story_setup


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


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
            json.dumps(empty_pass2_baseline({}).model_dump(mode="json")),
        ),
    )


@pytest.fixture(scope="module")
def disposable_db() -> Iterator[str]:
    """Yield a dump-initialized disposable slot and drop it afterward."""

    dbname = f"qa_wt625_{uuid.uuid4().hex[:12]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
        pool = db_pool._pools.pop(dbname, None)
        if pool is not None:
            pool.closeall()
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


@pytest.fixture(scope="module")
def empty_disposable_db() -> Iterator[str]:
    """Yield a second dump-initialized slot with no committed chunks."""

    dbname = f"qa_wt625_empty_{uuid.uuid4().hex[:8]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
        pool = db_pool._pools.pop(dbname, None)
        if pool is not None:
            pool.closeall()
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


@pytest.fixture(scope="module")
def backstage_case(disposable_db: str) -> dict[str, Any]:
    """Persist every Backstage stream through real writer/query paths."""

    conn = _connect(disposable_db)
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
                    INSERT INTO global_variables (id, user_character, base_timestamp)
                    VALUES (TRUE, %s, '2189-10-17T18:00:00+00:00')
                    ON CONFLICT (id) DO UPDATE SET
                        user_character = EXCLUDED.user_character,
                        base_timestamp = EXCLUDED.base_timestamp
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
                    (provisional_id, latest, str(uuid.uuid4())),
                )
    finally:
        conn.close()

    return {
        "chunks": chunk_ids,
        "latest": chunk_ids[-1],
        "prior_relationship_chunk": prior_relationship_chunk,
        "prologue": prologue_id,
        "provisional": provisional_id,
    }


@pytest.fixture()
def client(
    disposable_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Route the genuine Backstage endpoint to the disposable slot."""

    def disposable_url(*, slot: int) -> str:
        if slot != 4:
            raise ValueError("slot_number must be between 1 and 5")
        return f"postgresql://pythagor@localhost:5432/{disposable_db}"

    monkeypatch.setattr(backstage_endpoints, "get_slot_db_url", disposable_url)
    app = FastAPI()
    app.include_router(backstage_endpoints.router)
    return TestClient(app)


def test_payload_assembles_every_committed_stream(
    client: TestClient,
    backstage_case: dict[str, Any],
) -> None:
    response = client.get("/api/dev/backstage/4/turn")
    assert response.status_code == 200
    payload = response.json()

    assert payload["header"] == {
        "slot": 4,
        "chunk_id": backstage_case["latest"],
        "chunk_label": "S01E01_004",
        "turn_label": "t.4",
        "world_time": payload["header"]["world_time"],
        "skald_status": "idle",
    }
    assert payload["header"]["world_time"] is not None
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
    assert sorted(row["held"] for row in relationship_writes) == [False, True]
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
        }
    ]
    assert [entry["turn_label"] for entry in orrery["history"]] == ["t.3", "t.2"]


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
    monkeypatch.setattr(
        backstage_endpoints,
        "get_slot_db_url",
        lambda *, slot: (f"postgresql://pythagor@localhost:5432/{empty_disposable_db}"),
    )
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
        monkeypatch.setattr(
            backstage_endpoints,
            "get_slot_db_url",
            lambda *, slot: f"postgresql://pythagor@localhost:5432/{disposable_db}",
        )
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
        lambda slot=None: _connect(disposable_db),
    )
    response = TestClient(narrative.app).get(
        "/api/narrative/incubator", params={"slot": 4}
    )
    assert response.status_code == 200
    payload = response.json()
    assert "correspondence_writer_letter" not in payload
    assert "correspondence_gaia_letter" not in payload

"""Real PostgreSQL coverage for the dev-gated Backstage endpoint."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import psycopg2  # type: ignore[import-untyped]
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2 import sql
import pytest

from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import (
    apply_pair_tag_bestowal,
    apply_tag_bestowal,
    clear_entity_tag,
)
from nexus.api import backstage_endpoints, db_pool
from nexus.api.commit_handler_sync import log_state_delta_sync
from nexus.agents.orrery.reconstruction import set_commit_chunk_attribution_sync
from nexus.memory.correspondence import (
    CorrespondenceCompactionPlan,
    insert_digest_version,
    persist_staged_correspondence,
)
from nexus.config import load_settings
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
                chunk_ids: list[int] = []
                for number in range(1, 4):
                    cur.execute(
                        "INSERT INTO narrative_chunks (raw_text) VALUES (%s) "
                        "RETURNING id",
                        (f"Backstage committed turn {number}",),
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

                cur.execute(
                    "INSERT INTO entities (kind) VALUES "
                    "('character'), ('character') RETURNING id"
                )
                first_entity, second_entity = [int(row[0]) for row in cur.fetchall()]
                cur.execute(
                    """
                    INSERT INTO characters (name, entity_id)
                    VALUES ('Celia', %s), ('Victor', %s)
                    RETURNING id
                    """,
                    (first_entity, second_entity),
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

                latest = chunk_ids[-1]
                set_commit_chunk_attribution_sync(cur, latest)
                cur.execute(
                    """
                    UPDATE character_relationships
                    SET valence_current = 0.05
                    WHERE character1_id = %s AND character2_id = %s
                    """,
                    (first_character, second_character),
                )
                cur.execute(
                    """
                    UPDATE character_relationships
                    SET valence_current = 0.20
                    WHERE character1_id = %s AND character2_id = %s
                    """,
                    (second_character, first_character),
                )
                log_state_delta_sync(
                    cur,
                    source_chunk_id=latest,
                    writer="skald_state_update",
                    entity_id=first_entity,
                    field="characters.current_activity",
                    new_value="watching the Rootline",
                )

                apply_tag_bestowal(
                    cur,
                    entity_id=first_entity,
                    entity_kind="character",
                    bestowal=OrreryTagBestowal(applied_tags=["grieving"]),
                    source_chunk_id=latest,
                )
                assert clear_entity_tag(
                    cur,
                    entity_id=first_entity,
                    tag="grieving",
                    source_chunk_id=latest,
                )
                assert apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=second_entity,
                    object_entity_id=first_entity,
                    subject_kind="character",
                    object_kind="character",
                    tag="hunting",
                    source_chunk_id=latest,
                )

                persist_staged_correspondence(
                    cur,
                    chunk_id=latest,
                    writer_letter="Keep Celia's suspicion beneath the prose.",
                    gaia_letter="Acknowledged; the durable state remains quiet.",
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
        "chunk_label": "S01E01_003",
        "turn_label": "t.3",
        "world_time": payload["header"]["world_time"],
        "skald_status": "idle",
    }
    assert payload["header"]["world_time"] is not None
    correspondence = payload["correspondence"]
    assert correspondence["digest"] == "Victor is cultivating Celia as an informant."
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
        }
    ]

    writes = payload["state_writes"]["rows"]
    relationship_writes = [
        row for row in writes if row["kind"] == "relation" and row["field"] == "valence"
    ]
    assert sorted(row["held"] for row in relationship_writes) == [False, True]
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
    assert len(payload["state_writes"]["history"]) == 2

    orrery = payload["orrery"]
    assert orrery["counts"] == {"fired": 1, "pressures": 1, "events": 1}
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
    assert len(orrery["history"]) == 2


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
    assert payload["correspondence"]["digest"] is None
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

    del backstage_case

    document = tomlkit.parse(Path("nexus.toml").read_text())
    document["orrery"]["dashboard"]["enabled"] = False  # type: ignore[index]
    off_path = tmp_path / "backstage_off.toml"
    off_path.write_text(tomlkit.dumps(document))
    app_off = FastAPI()
    narrative._include_backstage_router(app_off, load_settings(str(off_path)))
    off_response = TestClient(app_off).get("/api/dev/backstage/4/turn")
    assert off_response.status_code == 404
    assert "correspondence" not in off_response.text

    document["orrery"]["dashboard"]["enabled"] = True  # type: ignore[index]
    on_path = tmp_path / "backstage_on.toml"
    on_path.write_text(tomlkit.dumps(document))
    monkeypatch.setattr(
        backstage_endpoints,
        "get_slot_db_url",
        lambda *, slot: f"postgresql://pythagor@localhost:5432/{disposable_db}",
    )
    app_on = FastAPI()
    narrative._include_backstage_router(app_on, load_settings(str(on_path)))
    on_response = TestClient(app_on).get("/api/dev/backstage/4/turn")
    assert on_response.status_code == 200
    assert "correspondence" in on_response.json()


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

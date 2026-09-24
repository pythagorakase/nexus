"""Real acceptance, staging, undo, and recovery on disposable slot clones.

Requires template narrative_chunks, chunk_metadata, incubator, generation lease,
Orrery, and baseline tables. Fixtures own all writes; no provider is called.
"""

from collections.abc import Iterator
from contextlib import closing
import json
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
import pytest

from nexus.api import (
    narrative,
    save_slots,
    slot_endpoints,
    slot_mutations,
    slot_state,
    slot_utils,
)
from nexus.api.choice_recovery import recover_orphaned_choice
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.narrative_generation import write_to_incubator
from nexus.api.narrative_lease import (
    acquire_generation_lease,
    bind_generation_parent,
    finish_generation,
)
from nexus.api.narrative_schemas import RegenerateNarrativeRequest
from nexus.memory.manager import empty_pass2_baseline
from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def acceptance_slot(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, int, int]]:
    """Route slot entry points to the fixture's database, retaining real SQL."""
    with disposable_slot_database("qa640_acceptance") as dbname:
        slot_utils.VALID_DBNAMES.add(dbname)
        for module in (
            slot_utils,
            slot_endpoints,
            slot_mutations,
            slot_state,
            save_slots,
        ):
            monkeypatch.setattr(module, "slot_dbname", lambda _slot: dbname)
        try:
            _, actor = seed_protagonist(dbname)
            with connect(dbname) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO narrative_chunks (storyteller_text, raw_text, "
                        "choice_text, choice_object) VALUES (%s, %s, %s, %s) RETURNING id",
                        (
                            "Rain falls.",
                            "Rain falls.\n\nTake shelter.",
                            "Take shelter.",
                            json.dumps(
                                {
                                    "presented": ["Take shelter.", "Walk on."],
                                    "selected": 1,
                                }
                            ),
                        ),
                    )
                    parent = cur.fetchone()[0]
                    cur.execute(
                        "INSERT INTO chunk_metadata (chunk_id, season, episode, scene, "
                        "world_layer) VALUES (%s, 1, 1, 1, 'primary')",
                        (parent,),
                    )
                    cur.execute(
                        """
                        INSERT INTO orrery_resolutions (
                            tick_chunk_id, template_id, binding_hash, actor_entity_id,
                            priority, magnitude, state_delta, brief, promotion_status
                        ) VALUES (%s, 'qa640_acceptance', 'qa640_acceptance', %s,
                                  50, 0.5, '{}'::jsonb, 'Rain falls.', 'promoted')
                        RETURNING id
                        """,
                        (parent, actor),
                    )
                    resolution = cur.fetchone()[0]
            yield dbname, parent, resolution
        finally:
            slot_utils.VALID_DBNAMES.discard(dbname)


def draft(parent: int, resolution: int, session: str) -> dict:
    """Return typed draft data suitable for the production staging writer."""
    return {
        "chunk_id": None,
        "parent_chunk_id": parent,
        "user_text": "Take shelter.",
        "storyteller_text": "The station roof keeps the rain out.",
        "generation_model": "acceptance-fixture",
        "choice_object": None,
        "choice_text": None,
        "metadata_updates": {
            "chronology": {"episode_transition": "continue", "time_delta_minutes": 1},
            "world_layer": "primary",
        },
        "entity_updates": {},
        "reference_updates": {"characters": [], "places": [], "factions": []},
        "orrery_proposal": {"_bleed_offer_resolution_ids": [resolution]},
        "orrery_adjudications": [],
        "new_entities": [],
        "lore_pass_baseline": empty_pass2_baseline({}).model_dump(mode="json"),
        "session_id": session,
        "llm_response_id": None,
        "status": "provisional",
    }


def own_draft(conn, parent: int) -> str:
    """Acquire and bind a real generation lease without running inference."""
    session = str(uuid4())
    assert (
        acquire_generation_lease(
            conn, session_id=session, operation="continue", stale_timeout_seconds=60
        )
        is None
    )
    bind_generation_parent(conn, session_id=session, parent_chunk_id=parent)
    return session


def parent_choice(conn, parent: int) -> tuple:
    """Read the canonical parent choice and searchable text."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT choice_text, raw_text, storyteller_text, choice_object FROM narrative_chunks WHERE id = %s",
            (parent,),
        )
        return cur.fetchone()


@pytest.mark.asyncio
async def test_staging_bleed_regenerate_and_acceptance(acceptance_slot) -> None:
    """Real regeneration scheduling/replacement preserves input and spends no offers."""
    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        await write_to_incubator(conn, draft(parent, resolution, session))
        finish_generation(conn, session_id=session, status="complete")
        before = parent_choice(conn, parent)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT offer_count FROM orrery_resolutions WHERE id = %s",
                (resolution,),
            )
            assert cur.fetchone() == (0,)
            cur.execute("SELECT chunk_id FROM incubator")
            assert cur.fetchone() == (None,)
        conn.commit()
        tasks = BackgroundTasks()
        regenerated = await narrative.regenerate_narrative(
            RegenerateNarrativeRequest(slot=5), tasks
        )
        assert len(tasks.tasks) == 1
        assert tasks.tasks[0].kwargs["expected_incubator_session"] == session
        assert parent_choice(conn, parent) == before
        await write_to_incubator(
            conn,
            draft(parent, resolution, regenerated.session_id),
            expected_incubator_session=session,
        )
        finish_generation(conn, session_id=regenerated.session_id, status="complete")
        assert parent_choice(conn, parent) == before
        with conn.cursor() as cur:
            cur.execute(
                "SELECT offer_count FROM orrery_resolutions WHERE id = %s",
                (resolution,),
            )
            assert cur.fetchone() == (0,)
        status = await narrative.get_narrative_status(regenerated.session_id, slot=5)
        assert status.status == "complete" and status.chunk_id is None
        assert status.phase == "complete" and status.terminal_outcome is None
        replaced = await narrative.get_narrative_status(session, slot=5)
        assert replaced.terminal_outcome == "superseded"
        assert replaced.replaced_by_session_id == regenerated.session_id
        selected = narrative._record_player_response_for_chunk(
            slot=5,
            chunk_id=None,
            user_text="Keep watching.",
            choice=None,
            accept_fate=False,
            require_response=True,
            connection=conn,
            incubator_session_id=regenerated.session_id,
        )
        assert selected == "Keep watching."
        assert parent_choice(conn, parent) == before
        accepted = commit_incubator_to_database_sync(
            conn, regenerated.session_id, slot=5
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT offer_count FROM orrery_resolutions WHERE id = %s",
                (resolution,),
            )
            assert cur.fetchone() == (1,)
            cur.execute(
                "SELECT chunk_id FROM narrative_generation_sessions WHERE session_id = %s",
                (regenerated.session_id,),
            )
            assert cur.fetchone() == (accepted,)
        terminal = await narrative.get_narrative_status(regenerated.session_id, slot=5)
        assert terminal.terminal_outcome == "accepted"
        assert terminal.chunk_id == accepted
        with pytest.raises(ValueError, match="No incubator data"):
            commit_incubator_to_database_sync(conn, regenerated.session_id, slot=5)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT offer_count FROM orrery_resolutions WHERE id = %s",
                (resolution,),
            )
            assert cur.fetchone() == (1,)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        (
            "entity_updates",
            {
                "characters": [
                    {
                        "character_id": 2147483647,
                        "character_name": "Missing",
                        "current_activity": "waiting",
                    }
                ]
            },
        ),
        ("reference_updates", {"characters": [{"character_id": 2147483647}]}),
        ("metadata_updates", {"chronology": {"episode_transition": "impossible"}}),
        ("lore_pass_baseline", {"schema_version": -1}),
        (
            "entity_updates",
            {
                "characters": [
                    {
                        "character_name": "Fixture Player",
                        "orrery_tags": {"applied_tags": ["qa640_unknown_tag"]},
                    }
                ]
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_staging_rejects_invalid_state_without_allocating_id(
    acceptance_slot,
    field: str,
    invalid: dict,
) -> None:
    """Invalid typed data and identities fail before storage or id allocation."""
    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        data = draft(parent, resolution, session)
        data[field] = invalid
        with conn.cursor() as cur:
            cur.execute("SELECT last_value, is_called FROM narrative_chunks_id_seq")
            sequence = cur.fetchone()
        with pytest.raises(ValueError):
            await write_to_incubator(conn, data)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (0,)
            cur.execute("SELECT last_value, is_called FROM narrative_chunks_id_seq")
            assert cur.fetchone() == sequence


@pytest.mark.asyncio
async def test_undo_discards_session_and_clears_parent_choice_via_endpoint(
    acceptance_slot,
) -> None:
    """Undo clears both response representations while retaining offered choices."""
    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        await write_to_incubator(conn, draft(parent, resolution, session))
        finish_generation(conn, session_id=session, status="complete")
    app = FastAPI()
    app.include_router(slot_endpoints.router)
    with TestClient(app) as client:
        response = client.post("/api/slot/5/undo")
    assert response.status_code == 200, response.text
    assert response.json()["success"]
    with TestClient(narrative.app) as fresh_client:
        status = fresh_client.get(
            f"/api/narrative/status/{session}", params={"slot": 5}
        )
        assert status.status_code == 200, status.text
        assert status.json()["terminal_outcome"] == "discarded"
        assert status.json()["status"] == "complete"
        assert status.json()["error"] is None
        assert status.json()["error_class"] is None
        active = fresh_client.get("/api/narrative/active", params={"slot": 5})
        assert active.status_code == 200, active.text
        assert active.json() is None
    with closing(connect(dbname)) as conn:
        choice, raw, storyteller, menu = parent_choice(conn, parent)
        assert choice is None
        assert raw == storyteller == "Rain falls."
        assert menu == {"presented": ["Take shelter.", "Walk on."], "selected": None}
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (0,)


@pytest.mark.asyncio
async def test_startup_recovery_preserves_incubator_and_clears_orphan(
    acceptance_slot, caplog, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery preserves a live draft and clears/logs an orphan exactly once."""
    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        await write_to_incubator(conn, draft(parent, resolution, session))
        finish_generation(conn, session_id=session, status="complete")
        before = parent_choice(conn, parent)
        assert recover_orphaned_choice(conn) is None
        assert parent_choice(conn, parent) == before
        with conn.cursor() as cur:
            cur.execute("DELETE FROM incubator")
        conn.commit()
        monkeypatch.setenv("NEXUS_SLOT", "5")
        await narrative.recover_active_choice_on_startup()
        assert recover_orphaned_choice(conn) is None
        choice, raw, storyteller, menu = parent_choice(conn, parent)
        assert choice is None
        assert raw == storyteller
        assert menu["selected"] is None
        assert caplog.text.count("Startup recovery cleared orphaned player choice") == 1


@pytest.mark.asyncio
async def test_incubator_cli_load_and_undo_with_no_predicted_id(
    acceptance_slot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public CLI reads and undoes a real draft through a gateway on an ephemeral port."""
    import os
    import socket
    import subprocess
    import sys
    import threading
    import time

    import uvicorn

    from nexus import cli

    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        await write_to_incubator(conn, draft(parent, resolution, session))
        finish_generation(conn, session_id=session, status="complete")
    monkeypatch.setenv("NEXUS_SLOT", "5")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        monkeypatch.setenv("NEXUS_GATEWAY_PORT", str(port))
        monkeypatch.setenv("NEXUS_API_URL", f"http://127.0.0.1:{port}")
        server = uvicorn.Server(
            uvicorn.Config(
                narrative.app, host="127.0.0.1", port=port, log_level="warning"
            )
        )
        listener.listen()
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while (
                not server.started and thread.is_alive() and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert server.started, "Gateway 8014 failed to start"
            completed = cli._wait_for_narrative_result(5, session)
            assert completed["success"], completed
            assert completed["chunk_id"] is None
            for command in ("load", "undo", "load"):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "nexus.cli",
                        command,
                        "--slot",
                        "5",
                        "--json",
                    ],
                    env={**os.environ, "PYTHONPATH": os.getcwd()},
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                assert result.returncode == 0, result.stdout + result.stderr
                payload = json.loads(result.stdout)
                assert payload["success"], payload
            with closing(connect(dbname)) as conn:
                choice, raw, storyteller, menu = parent_choice(conn, parent)
                assert choice is None and raw == storyteller
                assert menu["selected"] is None
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "Gateway 8014 did not shut down"
            stopped = subprocess.run(
                [sys.executable, "-m", "nexus.cli", "down", "--json"],
                env={**os.environ, "PYTHONPATH": os.getcwd()},
                text=True,
                capture_output=True,
                timeout=30,
            )
            assert stopped.returncode == 0, stopped.stdout + stopped.stderr


@pytest.mark.asyncio
async def test_acceptance_revalidates_staged_state_before_allocating_id(
    acceptance_slot,
) -> None:
    """A draft invalidated after staging remains pending without spending an id."""
    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        await write_to_incubator(conn, draft(parent, resolution, session))
        finish_generation(conn, session_id=session, status="complete")
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE incubator SET entity_updates = %s",
                (json.dumps({"factions": [{"faction_id": 2147483647}]}),),
            )
            cur.execute("SELECT last_value, is_called FROM narrative_chunks_id_seq")
            sequence = cur.fetchone()
        conn.commit()
        with pytest.raises(ValueError, match="Unresolved faction state update id"):
            commit_incubator_to_database_sync(conn, session, slot=5)
        with conn.cursor() as cur:
            cur.execute("SELECT last_value, is_called FROM narrative_chunks_id_seq")
            assert cur.fetchone() == sequence
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (1,)


@pytest.mark.asyncio
async def test_staging_resolves_same_turn_declarations_only_on_acceptance(
    acceptance_slot,
) -> None:
    """Dry-run identity checks admit declared names without creating stubs early."""
    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        data = draft(parent, resolution, session)
        data["storyteller_text"] = "Courier Vale enters the station."
        data["new_entities"] = [
            {"kind": "character", "name": "Courier Vale", "summary": "A courier."}
        ]
        data["reference_updates"]["characters"] = [
            {"character_name": "Courier Vale", "reference_type": "present"}
        ]
        data["entity_updates"] = {
            "characters": [
                {
                    "character_name": "Courier Vale",
                    "current_activity": "watching the door",
                }
            ]
        }
        await write_to_incubator(conn, data)
        finish_generation(conn, session_id=session, status="complete")
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM characters WHERE name = 'Courier Vale'")
            assert cur.fetchone() == (0,)
        child = commit_incubator_to_database_sync(conn, session, slot=5)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.current_activity, r.reference FROM characters c JOIN chunk_character_references r ON r.character_id = c.id WHERE c.name = 'Courier Vale' AND r.chunk_id = %s",
                (child,),
            )
            assert cur.fetchone() == ("watching the door", "present")


def test_recovery_respects_live_lease_without_incubator(acceptance_slot) -> None:
    """A generating owner preserves its input until the lease actually expires."""
    dbname, parent, _ = acceptance_slot
    with closing(connect(dbname)) as conn:
        own_draft(conn, parent)
        before = parent_choice(conn, parent)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (0,)
        assert recover_orphaned_choice(conn) is None
        assert parent_choice(conn, parent) == before
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE narrative_generation_lease "
                "SET expires_at = clock_timestamp() - interval '1 second'"
            )
        conn.commit()
        assert recover_orphaned_choice(conn) == parent
        choice, raw, storyteller, menu = parent_choice(conn, parent)
        assert choice is None and raw == storyteller
        assert menu["selected"] is None
        assert recover_orphaned_choice(conn) is None


@pytest.mark.parametrize("violation", ["embedded", "null_menu"])
def test_recovery_refuses_ironman_and_lifecycle_violations(
    acceptance_slot, violation: str
) -> None:
    """Recovery raises and preserves every source field on an invalid parent."""
    dbname, parent, _ = acceptance_slot
    with closing(connect(dbname)) as conn:
        with conn.cursor() as cur:
            if violation == "embedded":
                cur.execute(
                    "UPDATE narrative_chunks SET embedding_generated_at = NOW() WHERE id = %s",
                    (parent,),
                )
                message = "already embedded.*ironman"
            else:
                cur.execute(
                    "UPDATE narrative_chunks SET choice_object = NULL WHERE id = %s",
                    (parent,),
                )
                message = "NULL choice_object.*lifecycle violation"
        conn.commit()
        before = parent_choice(conn, parent)
        with pytest.raises(ValueError, match=message):
            recover_orphaned_choice(conn)
        assert parent_choice(conn, parent) == before


@pytest.mark.parametrize("managed", [True, False])
def test_up_refuses_running_gateway_before_recovery(
    acceptance_slot, tmp_path, monkeypatch: pytest.MonkeyPatch, managed: bool
) -> None:
    """Real PID/port refusals cannot clear an orphan before refusing startup."""
    import os
    from pathlib import Path
    import socket

    import tomlkit

    from nexus.runtime import RuntimeError_, Supervisor

    dbname, parent, _ = acceptance_slot
    document = tomlkit.parse(Path("nexus.toml").read_text())
    document["runtime"]["state_dir"] = str(tmp_path / "state")
    # Isolate the refusal from other managed services and machine-local listeners.
    for name, service in document["runtime"]["services"].items():
        service["enabled"] = "always" if name == "gateway" else "never"
    config = tmp_path / "runtime.toml"
    config.write_text(tomlkit.dumps(document))
    with closing(connect(dbname)) as conn, socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        monkeypatch.setenv("NEXUS_GATEWAY_PORT", str(port))
        supervisor = Supervisor.from_config(config)
        supervisor.state_dir.mkdir(parents=True)
        before = parent_choice(conn, parent)
        if managed:
            supervisor._write_pidfile("gateway", {"pid": os.getpid()})
            message = "already running"
        else:
            message = f"Port {port} is already in use"
        with pytest.raises(RuntimeError_, match=message):
            supervisor.up(slot=5, echo=False)
        assert parent_choice(conn, parent) == before


@pytest.mark.asyncio
async def test_incubator_select_by_session_and_approve_via_http(
    acceptance_slot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A NULL-id draft is selectable by attempt and gets its id only on approval."""
    import threading

    dbname, parent, resolution = acceptance_slot
    monkeypatch.setenv("NEXUS_SLOT", "5")
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        data = draft(parent, resolution, session)
        data["choice_object"] = {"presented": ["Wait.", "Go."], "selected": None}
        await write_to_incubator(conn, data)
        finish_generation(conn, session_id=session, status="complete")
        with conn.cursor() as cur:
            cur.execute("SELECT last_value, is_called FROM narrative_chunks_id_seq")
            sequence = cur.fetchone()
        with TestClient(narrative.app) as client:
            pending = client.get(
                "/api/narrative/incubator", params={"slot": 5, "session_id": session}
            )
            assert pending.status_code == 200, pending.text
            assert pending.json()["chunk_id"] is None
            selection = {"label": 2, "text": "Go.", "edited": False}
            selected = client.post(
                "/api/narrative/select-choice",
                json={"slot": 5, "session_id": session, "selection": selection},
            )
            assert selected.status_code == 200, selected.text
            assert selected.json()["chunk_id"] is None
            assert selected.json()["session_id"] == session
            assert selected.json()["status"] == "pending"
            assert selected.json()["raw_text"].endswith("Go.")
            stale = str(uuid4())
            for path, body in (
                ("select-choice", {"selection": selection}),
                ("approve", {"commit": True}),
                ("regenerate", {}),
                ("continue", {"choice": 1}),
            ):
                refused = client.post(
                    f"/api/narrative/{path}",
                    json={"slot": 5, "session_id": stale, **body},
                )
                assert refused.status_code in (404, 409), refused.text
            refused = client.delete(
                "/api/narrative/incubator", params={"slot": 5, "session_id": stale}
            )
            assert refused.status_code == 404, refused.text
            with conn.cursor() as cur:
                cur.execute("SELECT last_value, is_called FROM narrative_chunks_id_seq")
                assert cur.fetchone() == sequence
                cur.execute("SELECT chunk_id, choice_text FROM incubator")
                assert cur.fetchone() == (None, "Go.")
            conn.commit()
            approved = client.post(
                "/api/narrative/approve", json={"slot": 5, "session_id": session}
            )
            assert approved.status_code == 200, approved.text
            accepted = approved.json()["chunk_id"]
            assert isinstance(accepted, int) and accepted > parent
            status = client.get(f"/api/narrative/status/{session}?slot=5")
            assert status.status_code == 200, status.text
            assert status.json()["chunk_id"] == accepted
            assert status.json()["status"] == "complete"
        # Empty real outbox drains finish before the fixture releases its routing.
        for prefix in ("orrery-post-commit-", "retrograde-maturation-"):
            for thread in threading.enumerate():
                if thread.name.startswith(prefix):
                    thread.join(timeout=10)
                    assert not thread.is_alive()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT choice_text FROM narrative_chunks WHERE id = %s", (accepted,)
            )
            assert cur.fetchone() == ("Go.",)
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (0,)


@pytest.mark.asyncio
async def test_staging_rejects_duplicate_defer_without_allocating_id(
    acceptance_slot,
) -> None:
    """Individually valid decisions still must form a valid adjudication set."""
    from nexus.agents.orrery.resolver import OrreryResolutionDraft, OrreryTickProposal

    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        data = draft(parent, resolution, session)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT actor_entity_id FROM orrery_resolutions WHERE id = %s",
                (resolution,),
            )
            actor = cur.fetchone()[0]
        proposal = OrreryResolutionDraft(
            template_id="sleep",
            priority=25,
            binding_hash="qa640_duplicate_defer",
            bindings={"actor": actor},
            branch_label="deferred",
            narrative_stub="{actor} rests.",
            magnitude=0.2,
        )
        data["orrery_proposal"] = OrreryTickProposal(
            anchor_chunk_id=parent, actor_count=1, resolutions=(proposal,)
        ).to_dict()
        decision = {"proposal_id": proposal.proposal_id, "action": "defer"}
        data["orrery_adjudications"] = [decision, dict(decision)]
        with conn.cursor() as cur:
            cur.execute("SELECT last_value, is_called FROM narrative_chunks_id_seq")
            sequence = cur.fetchone()
        with pytest.raises(ValueError, match="Duplicate Orrery adjudication"):
            await write_to_incubator(conn, data)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (0,)
            cur.execute("SELECT last_value, is_called FROM narrative_chunks_id_seq")
            assert cur.fetchone() == sequence
        # A single defer is valid under that same validator.
        data["orrery_adjudications"] = [decision]
        await write_to_incubator(conn, data)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id FROM incubator WHERE session_id = %s", (session,)
            )
            assert cur.fetchone() == (None,)

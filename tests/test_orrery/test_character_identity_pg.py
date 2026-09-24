"""Real Retrograde and asynchronous pre-insert identity proofs."""

import asyncio

import asyncpg
import pytest

from nexus.agents.orrery.retrograde_persistence import _insert_missing_entity_stubs
from nexus.api.db_converters import create_declared_entity_stubs
from nexus.presence.identity import CharacterIdentityAmbiguity
from tests.pg_fixtures import asyncpg_kwargs, connect
from tests.test_presence_roster_pg import roster_database

pytestmark = pytest.mark.requires_postgres


@pytest.mark.parametrize("name", ["Remote Friend", "Fox", "Juniper Moss"])
def test_retrograde_identity_seed_binds_and_is_idempotent(roster_database, name):
    dbname, ids, _ = roster_database
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO character_aliases (character_id, alias) VALUES (%s, 'Fox')",
            (ids["Remote Friend"],),
        )
        cur.execute("SELECT count(*) FROM characters")
        before = cur.fetchone()[0]
        for _ in range(2):
            _insert_missing_entity_stubs(
                cur,
                entity_stub_rows=[
                    {
                        "status": "would_insert",
                        "entity_kind": "character",
                        "entity_ref": name,
                        "sources": [],
                    }
                ],
                create_missing_entities=True,
            )
        cur.execute("SELECT count(*) FROM characters")
        assert cur.fetchone()[0] == before + int(name == "Juniper Moss")


def test_retrograde_identity_seed_surname_is_terminal(roster_database):
    dbname, ids, _ = roster_database
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE characters SET name = 'Silas Wren' WHERE id = %s",
            (ids["Remote Friend"],),
        )
        cur.execute("INSERT INTO characters (name) VALUES ('Ada Wren')")
        with pytest.raises(CharacterIdentityAmbiguity):
            _insert_missing_entity_stubs(
                cur,
                entity_stub_rows=[
                    {
                        "status": "would_insert",
                        "entity_kind": "character",
                        "entity_ref": "Wren",
                        "sources": [],
                    }
                ],
                create_missing_entities=True,
            )
        cur.execute("SELECT count(*) FROM characters WHERE name = 'Wren'")
        assert cur.fetchone()[0] == 0


def test_async_identity_declaration_alias_and_novel(roster_database):
    dbname, ids, _ = roster_database
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO character_aliases (character_id, alias) VALUES (%s, 'Fox')",
            (ids["Remote Friend"],),
        )

    async def exercise():
        conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
        try:
            async with conn.transaction():
                assert (
                    await create_declared_entity_stubs(
                        [
                            {
                                "kind": "character",
                                "name": "Fox",
                                "summary": "A known visitor.",
                            }
                        ],
                        conn,
                    )
                    == 0
                )
                declaration = [
                    {
                        "kind": "character",
                        "name": "Juniper Moss",
                        "summary": "A new visitor.",
                    }
                ]
                assert await create_declared_entity_stubs(declaration, conn) == 1
                assert await create_declared_entity_stubs(declaration, conn) == 0
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM characters WHERE name = 'Fox'"
                    )
                    == 0
                )
        finally:
            await conn.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("case", ["surname", "title", "location", "batch"])
def test_identity_ambiguity_never_retries_test_provider(
    roster_database, monkeypatch, capsys, case
):
    """Real SDK, loopback TEST response, PG resolver, and durable attempt ledger."""
    import json
    from datetime import datetime, timezone
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from uuid import uuid4

    from nexus.agents.logon.skald_wire import SkaldGaiaWire
    from nexus.telemetry.usage import read_prompt_windows
    from scripts.api_openai import OpenAIProvider
    from tests.test_lore.window_helpers import window_logon

    dbname, ids, _ = roster_database
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE characters SET name = 'Silas Wren' WHERE id = %s",
            (ids["Remote Friend"],),
        )
        cur.execute("INSERT INTO characters (name) VALUES ('Ada Wren')")
    from tests.test_presence_roster_pg import commit_wire, wire

    parent = commit_wire(dbname, 0, wire("The hall is quiet."))
    names = ["Wren"]
    if case == "title":
        names = ["Lady Ada"]
        with connect(dbname) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO characters (name) VALUES ('Ada')")
    elif case == "location":
        names = ["Silas Wren"]
        with connect(dbname) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO places (name, type) VALUES ('Garden', 'fixed_location') RETURNING id"
            )
            cur.execute(
                "UPDATE characters SET current_location = %s WHERE id = %s",
                (cur.fetchone()[0], ids["Remote Friend"]),
            )
    elif case == "batch":
        names = ["Juniper Moss", "Juniper Mosss"]
    requests = []
    body = {
        "letter": "Keep the scene quiet.",
        "new_entities": [
            {"kind": "character", "name": name, "summary": "A visitor."}
            for name in names
        ],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(self.rfile.read(int(self.headers["Content-Length"])))
            response = {
                "id": "identity-799",
                "object": "chat.completion",
                "created": 0,
                "model": "TEST",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(body)},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
            encoded = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        provider = OpenAIProvider(
            api_key="fixture-only",
            model="TEST",
            base_url=f"http://127.0.0.1:{server.server_port}",
            structured_transport="chat_completions",
            structured_output_retries=3,
            usage_provider_name="test",
            usage_seat="gaia",
        )
        try:
            utility = window_logon()
            utility._validation_dbname = dbname
            utility._active_anchor_chunk_id = parent
            utility._gaia_window_blocks = [("user input", "Wait.")]
            session = str(uuid4())
            utility._window_payload = {"metadata": {"turn_id": session}}
            utility._attach_prompt_window_guard(
                provider, "Wait.", seat="gaia", window=75000
            )
            with pytest.raises(CharacterIdentityAmbiguity):
                provider.get_structured_completion("Wait.", SkaldGaiaWire)
            assert len(requests) == 1
            attempts = read_prompt_windows(
                session, datetime.now(timezone.utc).date().isoformat()
            )
            assert len(attempts) == 1
            assert (
                "Ambiguous character declaration"
                in attempts[0].validation_notes[0]["error"]
            )
            import sys
            from nexus import cli

            monkeypatch.setattr(
                sys, "argv", ["nexus", "usage", "--run", session, "--json"]
            )
            capsys.readouterr()
            assert cli.main() == 0
            ledger = json.loads(capsys.readouterr().out)
            assert len(ledger["windows"]) == 1
            assert (
                "Ambiguous character declaration"
                in ledger["windows"][0]["validation_notes"][0]["error"]
            )
        finally:
            provider.client.close()
            server.shutdown()
            thread.join(timeout=5)


def test_identity_generated_family_alias_is_revoked_before_ambiguous_mint(
    roster_database,
):
    dbname, _, _ = roster_database
    with connect(dbname) as conn, conn.cursor() as cur:
        for name in ("Silas Wren", "Ada Wren"):
            inserted = _insert_missing_entity_stubs(
                cur,
                entity_stub_rows=[
                    {
                        "status": "would_insert",
                        "entity_kind": "character",
                        "entity_ref": name,
                        "sources": [],
                    }
                ],
                create_missing_entities=True,
            )
            assert len(inserted) == 1
        cur.execute("SELECT count(*) FROM character_aliases WHERE alias = 'Wren'")
        assert cur.fetchone()[0] == 0
        inserted = _insert_missing_entity_stubs(
            cur,
            entity_stub_rows=[
                {
                    "status": "would_insert",
                    "entity_kind": "character",
                    "entity_ref": "Silas Wren",
                    "sources": [],
                }
            ],
            create_missing_entities=True,
        )
        assert not inserted


def test_identity_declared_character_colliding_with_place_needs_review(roster_database):
    from nexus.presence.identity import require_character_identity

    dbname, _, _ = roster_database
    with connect(dbname) as conn:
        with pytest.raises(CharacterIdentityAmbiguity, match="Hall.*place"):
            require_character_identity(conn, "Hall")


def test_identity_maturation_failure_class_is_durable_and_terminal(roster_database):
    from uuid import uuid4

    from nexus.agents.logon.apex_schema import NewEntityDeclaration
    from nexus.agents.orrery.retrograde_maturation import _mark_maturation_failed
    from tests.test_presence_roster_pg import commit_wire, wire

    dbname, _, _ = roster_database
    commit_wire(
        dbname,
        0,
        wire(
            "Juniper Moss waits.",
            new_entities=[
                NewEntityDeclaration(
                    kind="character", name="Juniper Moss", summary="A visitor."
                )
            ],
        ),
    )
    nonce = str(uuid4())
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE orrery_maturation_jobs SET state='leased', locked_by='identity-proof',
                    lease_nonce=%s, lease_until=now() + interval '1 hour'
                    WHERE entity_name='Juniper Moss' RETURNING id""",
            (nonce,),
        )
        job = cur.fetchone()[0]
        _mark_maturation_failed(
            cur,
            row={
                "job_id": job,
                "locked_by": "identity-proof",
                "lease_nonce": nonce,
                "attempts": 0,
            },
            error="Ambiguous character declaration",
            failure_class=CharacterIdentityAmbiguity.__name__,
            max_attempts=3,
            retry_delay_seconds=1,
        )
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state, result_manifest->>'failure_class', lease_nonce FROM orrery_maturation_jobs WHERE id=%s",
            (job,),
        )
        assert cur.fetchone() == ("failed", "CharacterIdentityAmbiguity", None)

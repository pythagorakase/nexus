"""Real CLI acceptance preserves the draft's parent and commits no new choice.

Requires PostgreSQL narrative_chunks, chunk_metadata, incubator and generation
sessions. All state belongs to qa640_815_review clones. The fixture gateway
uses a private runtime config and an OS-assigned port; no provider call is
needed to accept an already staged draft.
"""

from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.pg_fixtures import (
    FIXTURE_TURN_CHOICES,
    connect,
    disposable_slot_database,
    seed_pending_turn,
    seed_played_story,
)
from tests.scheduler_helpers import (
    gateway_lane,
    private_runtime_config,
    route_slot,
    routed_child_environment,
)

pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).resolve().parents[1]
PENDING_TEXT = "The pending fixture turn waits for review."


def _cli(*argv: str) -> subprocess.CompletedProcess[str]:
    """Run the real child CLI routed only to the fixture's disposable slot."""
    completed = subprocess.run(
        [sys.executable, "-m", "tests.slot_routed_cli", *argv],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT), **routed_child_environment()},
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(f"$ nexus {' '.join(argv)}\n{completed.stdout}{completed.stderr}", flush=True)
    return completed


def test_accept_commits_the_draft_and_keeps_the_parent_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance retains the parent's selection and leaves the new menu unanswered."""
    private_runtime_config(tmp_path, monkeypatch)
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "0")
    with disposable_slot_database("qa640_815_review") as dbname:
        route_slot(monkeypatch, dbname)
        parent = seed_played_story(dbname, turns=2, slot=4)[-1]
        # Stage before startup: recovery must see the draft and keep its parent choice.
        session = seed_pending_turn(
            dbname,
            user_text=FIXTURE_TURN_CHOICES[0],
            storyteller_text=PENDING_TEXT,
            choices=list(FIXTURE_TURN_CHOICES),
        )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT choice_text, choice_object, raw_text "
                "FROM narrative_chunks WHERE id = %s",
                (parent,),
            )
            parent_before = cur.fetchone()
        assert parent_before[0] == FIXTURE_TURN_CHOICES[0]

        with gateway_lane(monkeypatch) as scheduler:
            scheduler.stop()
            accepted = _cli("accept", "--slot", "4", "--json")
            assert accepted.returncode == 0, accepted.stdout + accepted.stderr
            assert accepted.stderr == ""
            payload = json.loads(accepted.stdout)
            assert payload["success"] is True
            chunk_id = payload["chunk_id"]
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM incubator")
                assert cur.fetchone() == (0,)
                cur.execute("SELECT max(id) FROM narrative_chunks")
                assert cur.fetchone() == (chunk_id,)
                assert chunk_id > parent
                cur.execute(
                    "SELECT storyteller_text, choice_text, choice_object "
                    "FROM narrative_chunks WHERE id = %s",
                    (chunk_id,),
                )
                storyteller, choice, menu = cur.fetchone()
                assert storyteller == PENDING_TEXT
                assert choice is None
                assert menu["presented"] == list(FIXTURE_TURN_CHOICES)
                assert menu.get("selected") is None
                cur.execute(
                    "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
                    (chunk_id,),
                )
                assert cur.fetchone()[0] is not None
                cur.execute(
                    "SELECT terminal_outcome, chunk_id "
                    "FROM narrative_generation_sessions WHERE session_id = %s",
                    (session,),
                )
                assert cur.fetchone() == ("accepted", chunk_id)
                cur.execute(
                    "SELECT choice_text, choice_object, raw_text "
                    "FROM narrative_chunks WHERE id = %s",
                    (parent,),
                )
                assert cur.fetchone() == parent_before
                cur.execute("SELECT * FROM narrative_chunks ORDER BY id")
                accepted_rows = cur.fetchall()

            undone = _cli("undo", "--slot", "4", "--json")
            assert undone.returncode == 1
            assert undone.stdout == ""
            failure = json.loads(undone.stderr)
            assert failure["code"] == "domain_failure"
            assert failure["error"].startswith("Cannot undo: no live turn")
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM narrative_chunks ORDER BY id")
                assert cur.fetchall() == accepted_rows
                cur.execute(
                    "SELECT choice_text, choice_object, raw_text "
                    "FROM narrative_chunks WHERE id = %s",
                    (parent,),
                )
                assert cur.fetchone() == parent_before


def test_accept_without_a_draft_is_an_api_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing drafts report the existing route's 404 without adding a chunk."""
    private_runtime_config(tmp_path, monkeypatch)
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "0")
    with disposable_slot_database("qa640_815_review") as dbname:
        route_slot(monkeypatch, dbname)
        seed_played_story(dbname, turns=2, slot=4)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_chunks")
            before = cur.fetchone()[0]

        with gateway_lane(monkeypatch) as scheduler:
            scheduler.stop()
            accepted = _cli("accept", "--slot", "4", "--json")
            assert accepted.returncode == 1
            assert accepted.stdout == ""
            failure = json.loads(accepted.stderr)
            assert failure["code"] == "api_error"
            assert "No pending session to approve in incubator" in failure["error"]
            assert failure["partial"] == {"status_code": 404}
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM narrative_chunks")
                assert cur.fetchone() == (before,)

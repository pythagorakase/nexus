"""The inspect family and the shared session waiter on a factory-played clone.

A disposable clone holds a story played by ``seed_played_story``. The real
gateway serves it on ``gateway_lane``'s lane with every provider routed to
TEST, and the public CLI runs in subprocesses: ``inspect incubator`` reads the
empty incubator as null, the next turn is staged as pending, ``continue
--choice 1`` accepts it and waits on the new session through
``wait_for_session``, then the inspect verbs read the result back through the
player-plane routes.
"""

from __future__ import annotations

from contextlib import closing
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest
import requests

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from tests.pg_fixtures import (
    FIXTURE_TURN_CHOICES,
    connect,
    disposable_slot_database,
    seed_faction,
    seed_pending_turn,
    seed_played_story,
)
from tests.scheduler_helpers import gateway_lane, route_slot, routed_child_environment
from tests.scheduler_helpers import test_provider_config as configure_test
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401

pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).resolve().parents[1]
PENDING_TEXT = "The pending fixture turn waits for the player's choice."
CAST = ("Mara Quill", "Oren Vale")
CREDENTIAL = "sk-815s5-sentinel-credential-WXYZ"


def _nexus(*argv: str) -> tuple[subprocess.CompletedProcess[str], Any]:
    """Run the public CLI against the lane and parse its JSON stdout.

    The child runs through ``tests.slot_routed_cli`` with the active route, so
    it resolves slot 4 to the clone as this process does.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "tests.slot_routed_cli", *argv],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT), **routed_child_environment()},
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(f"$ nexus {' '.join(argv)}\n{completed.stdout}{completed.stderr}", flush=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stderr == ""
    return completed, json.loads(completed.stdout)


def _envelope(*argv: str) -> Any:
    """Run one ``nexus inspect`` verb on slot 4 and return its envelope data."""
    _completed, envelope = _nexus("inspect", *argv, "--slot", "4", "--json")
    assert set(envelope) == {"ok", "data"}
    assert envelope["ok"] is True
    return envelope["data"]


def _operator_envelope(*argv: str) -> tuple[subprocess.CompletedProcess[str], Any]:
    """Run an operator inspection without forcing the optional story-pin slot."""
    completed, envelope = _nexus("inspect", *argv, "--json")
    assert set(envelope) == {"ok", "data"}
    assert envelope["ok"] is True
    return completed, envelope["data"]


def _nexus_text(*argv: str) -> str:
    """Run an operator inspection through the routed child with text output."""
    completed = subprocess.run(
        [sys.executable, "-m", "tests.slot_routed_cli", "inspect", *argv],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT), **routed_child_environment()},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stderr == ""
    assert CREDENTIAL not in completed.stdout
    assert CREDENTIAL not in completed.stderr
    return completed.stdout


def test_continue_waits_then_inspect_reads_the_played_clone(
    monkeypatch, tmp_path, mock_openai_server  # noqa: F811
) -> None:
    """``continue`` waits through the helper; inspect reads what it produced."""
    configure_test(tmp_path, mock_openai_server, monkeypatch)
    with disposable_slot_database("qa640_815_inspect") as dbname:
        route_slot(monkeypatch, dbname)
        committed = seed_played_story(
            dbname,
            turns=3,
            cast=CAST,
            time_delta=timedelta(hours=2),
            slot=4,
        )
        faction_id, _entity = seed_faction(dbname, name="The Lamplighters")

        with gateway_lane(monkeypatch) as scheduler:
            scheduler.stop()
            # The real incubator route's empty answer is an explicit null.
            assert _envelope("incubator") is None
            seed_pending_turn(
                dbname,
                user_text=FIXTURE_TURN_CHOICES[0],
                storyteller_text=PENDING_TEXT,
                choices=list(FIXTURE_TURN_CHOICES),
            )
            _completed, turn = _nexus(
                "continue", "--slot", "4", "--choice", "1", "--json"
            )
            assert turn["success"] is True, turn
            assert isinstance(turn["session_id"], str) and turn["session_id"]
            assert turn["message"].strip()
            assert turn["choices"]

            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT nc.id, nc.storyteller_text FROM narrative_chunks nc "
                    "JOIN chunk_metadata cm ON cm.chunk_id = nc.id "
                    f"WHERE {playable_narrative_predicate()} ORDER BY nc.id"
                )
                playable = cur.fetchall()
                cur.execute("SELECT session_id::text, storyteller_text FROM incubator")
                incubator = cur.fetchone()
                cur.execute("SELECT id, name FROM characters ORDER BY id")
                characters = cur.fetchall()
                cur.execute("SELECT id, name FROM places ORDER BY id")
                places = cur.fetchall()
                cur.execute("SELECT id, name FROM factions ORDER BY id")
                factions = cur.fetchall()
            # Continuing accepted the pending turn and staged the next one.
            assert [row[0] for row in playable[:-1]] == committed
            assert playable[-1][1] == PENDING_TEXT
            assert incubator == (turn["session_id"], turn["message"])

            last_two = _envelope("chunks", "--last", "2")
            assert [chunk["id"] for chunk in last_two] == [
                row[0] for row in playable[-2:]
            ]
            assert last_two[-1]["storytellerText"] == PENDING_TEXT
            assert all(
                chunk["metadata"]["chunkId"] == chunk["id"] for chunk in last_two
            )

            first, second = playable[0][0], playable[1][0]
            ranged = _envelope("chunks", "--from", str(first), "--to", str(second))
            assert [chunk["id"] for chunk in ranged] == [first, second]
            assert _envelope("chunk", str(second)) == ranged[1]

            draft = _envelope("incubator")
            assert draft["session_id"] == turn["session_id"]
            assert draft["storyteller_text"] == turn["message"]

            cast = _envelope("characters")
            assert [(row["id"], row["name"]) for row in cast] == characters
            assert set(CAST) <= {row["name"] for row in cast}
            mara = next(row for row in cast if row["name"] == "Mara Quill")
            assert _envelope("characters", str(mara["id"])) == mara

            listed_places = _envelope("places")
            assert [(row["id"], row["name"]) for row in listed_places] == places
            assert _envelope("places", str(places[-1][0])) == listed_places[-1]
            listed_factions = _envelope("factions")
            assert [(row["id"], row["name"]) for row in listed_factions] == factions
            assert factions == [(faction_id, "The Lamplighters")]
            assert _envelope("factions", str(faction_id)) == listed_factions[0]


def test_operator_inspect_reads_the_live_gateway_masked(
    monkeypatch, tmp_path, mock_openai_server, in_memory_secret_store  # noqa: F811
) -> None:
    """The real gateway serves private settings and only in-memory masked keys."""
    configure_test(tmp_path, mock_openai_server, monkeypatch)
    with disposable_slot_database("qa640_815s5_operator") as dbname:
        route_slot(monkeypatch, dbname)
        in_memory_secret_store.write("openai", CREDENTIAL)
        with gateway_lane(monkeypatch) as scheduler:
            scheduler.stop()
            base_url = os.environ["NEXUS_API_URL"]
            settings_run, settings = _operator_envelope("settings")
            assert (
                settings == requests.get(f"{base_url}/api/settings", timeout=30).json()
            )
            assert "secrets" not in settings
            assert (
                settings["global"]["model"]["api_models"]["test"]["base_url"]
                == mock_openai_server
            )
            secrets_run, statuses = _operator_envelope("secrets")
            assert (
                statuses
                == requests.get(f"{base_url}/api/secrets/status", timeout=30).json()
            )
            openai = next(row for row in statuses if row["provider"] == "openai")
            assert openai["present"] is True
            assert openai["last4"] == "WXYZ"
            slot_run, slot_statuses = _operator_envelope("secrets", "--slot", "4")
            assert (
                slot_statuses
                == requests.get(
                    f"{base_url}/api/secrets/status", params={"slot": 4}, timeout=30
                ).json()
            )
            for completed in (settings_run, secrets_run, slot_run):
                assert CREDENTIAL not in completed.stdout
                assert CREDENTIAL not in completed.stderr
            for argv in (("settings",), ("secrets",), ("secrets", "--slot", "4")):
                assert CREDENTIAL not in _nexus_text(*argv)

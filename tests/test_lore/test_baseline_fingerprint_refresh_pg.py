"""Real continuation and CLI refresh against a seeded disposable clone.

The clone holds accepted turns whose commits bound their Pass-2 baselines
(``seed_played_story``) and a pending draft staged by ``seed_pending_turn``,
whose incubator row the refresh must leave untouched.
"""

import asyncio
from contextlib import closing
import subprocess
import sys
from uuid import uuid4

import pytest

from nexus.agents.lore.lore import LORE
from nexus.config import load_settings
from nexus.config.story_model import read_story_settings, story_context_settings
from nexus.memory.baseline_compat import config_hash, fingerprinted_config
from nexus.memory.manager import pass2_baseline_config_fingerprint
from scripts.stamp_lore_pass_baseline import refresh_tail_fingerprint
from tests.pg_fixtures import (
    FIXTURE_TURN_CHOICES,
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_pending_turn,
    seed_played_story,
)

pytestmark = pytest.mark.requires_postgres

# Accepted turns seeded ahead of the pending draft.
STORY_TURNS = 3


def test_divergence_fingerprint_refresh_preserves_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recreate the pre-removal stamp so this stays valid after fleet refresh."""
    with disposable_slot_database("qa640_908_fingerprint") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        seed_played_story(dbname, turns=STORY_TURNS, slot=4)
        seed_pending_turn(
            dbname,
            user_text=FIXTURE_TURN_CHOICES[0],
            storyteller_text="The plaza lamps flicker on as the square empties.",
            choices=list(FIXTURE_TURN_CHOICES),
        )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT max(id) FROM narrative_chunks")
            tail_id = cur.fetchone()[0]
            cur.execute(
                "SELECT chunk_id, schema_version, payload FROM lore_pass_baselines ORDER BY chunk_id"
            )
            before = cur.fetchall()
            cur.execute("SELECT * FROM incubator ORDER BY id")
            incubator_before = cur.fetchall()
        assert len(before) == STORY_TURNS and before[-1][0] == tail_id
        assert len(incubator_before) == 1
        settings = story_context_settings(load_settings(), read_story_settings(dbname))
        expected = pass2_baseline_config_fingerprint(settings)
        # A retired [memory] key the typed settings can no longer carry.
        historical = fingerprinted_config(settings)
        historical["memory"]["divergence_threshold"] = 0.7
        old = config_hash(historical)
        assert old != expected
        # Seed the historical config shape only in the disposable clone. This
        # remains a regression after the coordinator refreshes the source save.
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE lore_pass_baselines SET payload = jsonb_set(payload, "
                "'{config_fingerprint}', to_jsonb(%s::text)) WHERE chunk_id = %s",
                (old, tail_id),
            )
            assert cur.rowcount == 1
        first = LORE(enable_logon=False, dbname=dbname)
        try:
            result = asyncio.run(
                first.process_turn(
                    "Continue.", parent_chunk_id=tail_id, attempt_id=str(uuid4())
                )
            )
            assert "config fingerprint is incompatible" in result, result
            print(f"Before refresh: {result}")
        finally:
            first.close()
        command = [
            sys.executable,
            "scripts/stamp_lore_pass_baseline.py",
            "--refresh-fingerprint",
            "--dbname",
            dbname,
        ]
        refreshed = subprocess.run(command, capture_output=True, text=True, check=True)
        assert f"{old} -> {expected}" in refreshed.stdout
        print(refreshed.stdout.strip())
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id, schema_version, payload FROM lore_pass_baselines ORDER BY chunk_id"
            )
            after = cur.fetchall()
            cur.execute("SELECT * FROM incubator ORDER BY id")
            assert cur.fetchall() == incubator_before
        for row in before:
            if row[0] == tail_id:
                row[2]["config_fingerprint"] = expected
        assert after == before
        print(
            "Only the tail config_fingerprint changed; all other baseline content and incubator rows are identical."
        )
        second = LORE(enable_logon=False, dbname=dbname)
        try:
            result = asyncio.run(
                second.process_turn(
                    "Continue.", parent_chunk_id=tail_id, attempt_id=str(uuid4())
                )
            )
            assert result == "LOGON disabled", result
            assert second.turn_context.memory_state["pass2"]["baseline_available"]
            print(f"After refresh: {result}; baseline_available=True")
        finally:
            second.close()
        # A story pin must also participate in the current projection.
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE global_variables SET apex_context_window = 100000 WHERE id"
            )
        pinned = pass2_baseline_config_fingerprint(
            story_context_settings(load_settings(), read_story_settings(dbname))
        )
        assert pinned != expected
        assert refresh_tail_fingerprint(dbname=dbname) == (tail_id, expected, pinned)
        assert refresh_tail_fingerprint(dbname=dbname) == (tail_id, pinned, pinned)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM lore_pass_baselines WHERE chunk_id = %s", (tail_id,)
            )
        with pytest.raises(RuntimeError, match="has no Pass-2 baseline"):
            refresh_tail_fingerprint(dbname=dbname)
        print(
            "Story pin projection, repeat refresh, and missing-baseline refusal passed."
        )

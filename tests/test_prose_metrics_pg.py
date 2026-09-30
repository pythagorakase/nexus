"""Real SELECT-only metrics on a seeded, disposable template clone.

The clone holds what the metrics join reads: a Retrograde prologue anchor
written by the production prologue writers before play (non-playable, so the
database holds more chunks than the metrics measure), then turns accepted
through the production commit with structured choice menus, a setting place
reference, and world-time deltas. tests.pg_fixtures owns creation, seeding,
and drop; no live slot is mutated.
"""

from contextlib import closing
from datetime import timedelta
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
    seed_accepted_turn,
    seed_place,
    seed_protagonist,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres

# Accepted turns seeded after the prologue anchor.
PLAYED_TURNS = 4


def _seed_story_after_prologue(dbname: str) -> None:
    """Seed the wizard's leavings, the prologue anchor, then played turns.

    The order is production's: the wizard transition leaves a located player
    and Retrograde's prologue anchor (``_insert_prologue_chunk`` and
    ``_ensure_prologue_metadata``) before the bootstrap turn, and every turn
    after it is accepted through ``seed_accepted_turn``.
    """
    from nexus.agents.orrery.retrograde_persistence import (
        _ensure_prologue_metadata,
        _insert_prologue_chunk,
    )

    seed_zone(
        dbname,
        name="Fixture Zone",
        min_longitude=-74.1,
        min_latitude=40.6,
        max_longitude=-73.8,
        max_latitude=40.9,
    )
    place_id, _ = seed_place(dbname, name="Fixture Plaza")
    player_id, _ = seed_protagonist(dbname, current_location=place_id)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        prologue = _insert_prologue_chunk(cur)
        _ensure_prologue_metadata(cur, prologue_chunk_id=prologue)
    references = {
        "characters": [
            {
                "character_id": player_id,
                "character_name": "Fixture Player",
                "reference_type": "present",
            }
        ],
        "places": [{"place_id": place_id, "reference_type": "setting"}],
        "factions": [],
    }
    user_text = "Begin the story."
    for turn in range(1, PLAYED_TURNS + 1):
        seed_accepted_turn(
            dbname,
            user_text=user_text,
            storyteller_text=(
                f"Fixture turn {turn}: the player crosses Fixture Plaza as the "
                "evening crowd thins and the tram bells fade."
            ),
            choices=list(FIXTURE_TURN_CHOICES),
            choice_text=FIXTURE_TURN_CHOICES[0],
            time_delta=timedelta(0) if turn == 1 else timedelta(minutes=20),
            reference_updates=references,
        )
        user_text = FIXTURE_TURN_CHOICES[0]


def test_metrics_cli_on_disposable_corpus(tmp_path: Path) -> None:
    """Exercise the real CLI, join, serialization and modern menu adapter."""
    with disposable_slot_database("qa640_prose_metrics") as dbname:
        _seed_story_after_prologue(dbname)
        target = tmp_path / "metrics.json"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/qa_shift/prose_metrics.py",
                "--dbname",
                dbname,
                "--output",
                str(target),
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(Path.cwd())},
        )
        report = json.loads(target.read_text())
        assert report["schema_version"] == 1
        assert report["corpus"] == dbname
        assert report["provenance"]["read_only"] is True
        assert report["provenance"]["text_source"] == "columns"
        scope = report["provenance"]["measurement_scope"]
        assert "rhythm" in scope["comparable_metrics"]
        assert "recovered menus only" in scope["legacy_heuristics"]
        assert (
            report["provenance"]["database_chunk_count"]
            > report["metrics"]["chunks"]
            > 0
        )
        assert report["metrics"]["chunks"] == PLAYED_TURNS
        assert len(report["provenance"]["snapshot_sha256"]) == 64
        assert report["metrics"]["choices"]["sources"] == {
            "choice_object.presented": report["metrics"]["choices"]["menus"]
        }
        assert report["metrics"]["choices"]["mean_count"] > 0
        assert report["metrics"]["words_per_chunk"]["mean"] > 0
        assert "world_minutes_per_turn.mean" in result.stderr
        assert not result.stdout

        # Both new mutation CLI targets operate only on this fixture-owned clone.
        migrated = subprocess.run(
            [sys.executable, "scripts/migrate.py", "--dbname", dbname],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "0 skipped/failed" in migrated.stderr
        assert "migration stamps; level" in migrated.stderr
        with connect(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT max(id) FROM narrative_chunks")
                tail = cur.fetchone()[0]
                cur.execute(
                    "DELETE FROM lore_pass_baselines WHERE chunk_id = %s", (tail,)
                )
        stamped = subprocess.run(
            [sys.executable, "scripts/stamp_lore_pass_baseline.py", "--dbname", dbname],
            check=True,
            capture_output=True,
            text=True,
        )
        assert f"tail chunk {tail}" in stamped.stdout
        with connect(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM lore_pass_baselines WHERE chunk_id = %s",
                    (tail,),
                )
                assert cur.fetchone()[0] == 1

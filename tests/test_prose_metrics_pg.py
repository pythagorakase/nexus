"""Real SELECT-only metrics on a migrated, disposable clone of save_04.

Requires narrative_chunks, chunk_metadata, place_chunk_references and migration
stamps. tests.pg_fixtures owns creation/migration/drop; no live slot is mutated.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres


def test_metrics_cli_on_disposable_corpus(tmp_path: Path) -> None:
    """Exercise the real CLI, join, serialization and modern menu adapter."""
    with disposable_slot_database(
        "qa640_prose_metrics", source_db="save_04", include_data=True
    ) as dbname:
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
        assert (
            report["provenance"]["database_chunk_count"]
            > report["metrics"]["chunks"]
            > 0
        )
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

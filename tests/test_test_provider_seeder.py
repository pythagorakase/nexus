"""Real operator-CLI checks for TEST seeding and optimized Python guards."""

from contextlib import closing
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.pg_fixtures import connect, disposable_slot_database


ROOT = Path(__file__).resolve().parents[1]
SEEDER = ROOT / "migrations/008_populate_mock_database.py"


def _run_seeder(
    *args: str, config: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the actual operator under optimized Python with inherited guards."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    if config is not None:
        env["NEXUS_RUNTIME_CONFIG"] = str(config)
    return subprocess.run(
        [sys.executable, "-O", str(SEEDER), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_seeder_help_does_not_require_valid_settings(tmp_path: Path) -> None:
    """An operator can discover CLI syntax while repairing malformed config."""
    config = tmp_path / "invalid.toml"
    config.write_text("[api\n")

    result = _run_seeder("--help", config=config)

    assert result.returncode == 0, result.stderr
    assert "--dbname" in result.stdout
    assert "Seeding TEST provider database" not in result.stdout


def test_explicit_seeder_target_still_requires_connection_settings(
    tmp_path: Path,
) -> None:
    """Naming a target must not bypass the shared validated DB configuration."""
    config = tmp_path / "invalid.toml"
    config.write_text("[api\n")

    result = _run_seeder("--dbname", "qa640_816_never_created", config=config)

    assert result.returncode != 0
    assert "TOMLDecodeError" in result.stderr
    assert "populated successfully" not in result.stdout


@pytest.mark.requires_postgres
@pytest.mark.parametrize("stage", ["post_transition", "save_slot"])
def test_optimized_seeder_refuses_a_suppressed_singleton_update(stage: str) -> None:
    """A real zero-row UPDATE refuses and rolls back even with asserts removed."""
    # A BEFORE trigger suppresses exactly the operator's selected UPDATE.
    # Everything else is real production SQL on a fixture-owned database.
    condition = (
        "NEW.user_character = 1"
        if stage == "post_transition"
        else "NEW.new_story IS FALSE"
    )
    with disposable_slot_database("qa640_816_singleton") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT row_to_json(g) FROM global_variables AS g")
            before = cur.fetchall()
            cur.execute("SELECT count(*) FROM assets.new_story_creator")
            before_cache = cur.fetchone()
            cur.execute(
                f"""
                CREATE FUNCTION qa640_suppress_singleton_update()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF {condition} THEN
                        RETURN NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$;
                CREATE TRIGGER qa640_suppress_singleton_update
                BEFORE UPDATE ON global_variables
                FOR EACH ROW EXECUTE FUNCTION qa640_suppress_singleton_update();
                """
            )

        result = _run_seeder("--dbname", dbname)

        assert result.returncode != 0, result.stdout
        assert (
            "RuntimeError: global_variables singleton row is missing" in result.stderr
        )
        assert "populated successfully" not in result.stdout
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT row_to_json(g) FROM global_variables AS g")
            assert cur.fetchall() == before
            cur.execute("SELECT count(*) FROM assets.new_story_creator")
            assert cur.fetchone() == before_cache

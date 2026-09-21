"""Slot reset prerequisites must work without an interactive shell PATH."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus import config
from scripts import new_story_setup


@pytest.mark.parametrize("available", [(), ("dropdb", "createdb", "pg_dump")])
def test_missing_tools_abort_before_database_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, available: tuple[str, ...]
) -> None:
    """Never terminate connections or drop data if any reset tool is absent."""
    for name in available:
        executable = tmp_path / name
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(
        config,
        "load_settings",
        lambda: SimpleNamespace(
            api=SimpleNamespace(database=SimpleNamespace(tool_search_paths=[]))
        ),
    )

    def unexpected_side_effect(*args: object, **kwargs: object) -> None:
        pytest.fail("Database reset started before checking its tools")

    monkeypatch.setattr(new_story_setup.psycopg2, "connect", unexpected_side_effect)
    monkeypatch.setattr(new_story_setup.subprocess, "run", unexpected_side_effect)

    with pytest.raises(RuntimeError, match="PostgreSQL tools unavailable:.*psql"):
        new_story_setup.initialize_slot_database("test_missing_tools", force=True)


def test_path_tools_keep_precedence_over_additional_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An operator's existing PostgreSQL installation remains authoritative."""
    executable = tmp_path / "pg_dump"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    def unexpected_config_load() -> None:
        pytest.fail("Tools already available in PATH do not need extra paths")

    monkeypatch.setattr(config, "load_settings", unexpected_config_load)

    assert new_story_setup._postgres_tools("pg_dump") == {"pg_dump": str(executable)}

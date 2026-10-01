"""Orrery per-mode travel tables validated through the real nexus.toml path."""

from pathlib import Path
import re

import pytest
from pydantic import ValidationError

from nexus.config import load_settings

SPEED_TABLE = re.compile(
    r"^\[orrery\.travel\.speed_kmh\]\n(?:[a-z_]+ = .*\n)+", re.MULTILINE
)
DETOUR_TABLE = re.compile(
    r"^\[orrery\.travel\.detour_factor\]\n(?:[a-z_]+ = .*\n)+", re.MULTILINE
)


def _write_config(tmp_path: Path, source: str) -> Path:
    config = tmp_path / "nexus.toml"
    config.write_text(source)
    return config


def _table(pattern: re.Pattern[str], source: str) -> re.Match[str]:
    match = pattern.search(source)
    assert match is not None
    return match


def test_shipped_travel_tables_match_the_retired_literals() -> None:
    """The shipped tables carry the values the module literals held, unchanged."""
    orrery = load_settings().orrery
    assert orrery is not None
    travel = orrery.travel

    assert travel.speed_kmh.model_dump() == {
        "walking": 5.0,
        "vehicle": 45.0,
        "rail": 75.0,
        "water": 25.0,
        "air": 450.0,
        "covert": 3.5,
        "mixed": 25.0,
    }
    assert travel.detour_factor.model_dump() == {
        "walking": 1.35,
        "vehicle": 1.25,
        "rail": 1.15,
        "water": 1.40,
        "air": 1.05,
        "covert": 1.80,
        "mixed": 1.40,
    }


def test_missing_travel_table_fails_load(tmp_path: Path) -> None:
    """No code default stands in for an absent [orrery.travel] table."""
    source = Path("nexus.toml").read_text()
    source, removed_speed = SPEED_TABLE.subn("", source)
    source, removed_detour = DETOUR_TABLE.subn("", source)
    assert (removed_speed, removed_detour) == (1, 1)
    assert "[orrery.travel" not in source

    with pytest.raises(ValidationError) as exc:
        load_settings(_write_config(tmp_path, source))

    assert any(
        error["loc"] == ("orrery", "travel") and error["type"] == "missing"
        for error in exc.value.errors()
    )


def test_missing_mode_fails_load(tmp_path: Path) -> None:
    """Every travel mode needs a speed; a missing one fails at settings load."""
    source = Path("nexus.toml").read_text()
    table = _table(SPEED_TABLE, source)
    trimmed, removed = re.subn(
        r"^covert = .*\n", "", table.group(0), count=1, flags=re.MULTILINE
    )
    assert removed == 1
    source = source[: table.start()] + trimmed + source[table.end() :]

    with pytest.raises(ValidationError) as exc:
        load_settings(_write_config(tmp_path, source))

    assert any(
        error["loc"] == ("orrery", "travel", "speed_kmh", "covert")
        and error["type"] == "missing"
        for error in exc.value.errors()
    )


def test_unknown_mode_fails_load(tmp_path: Path) -> None:
    """A mode the travel enum does not name fails at settings load."""
    source = Path("nexus.toml").read_text()
    table = _table(SPEED_TABLE, source)
    source = source[: table.end()] + "teleport = 9.0\n" + source[table.end() :]

    with pytest.raises(ValidationError) as exc:
        load_settings(_write_config(tmp_path, source))

    assert any(
        error["loc"] == ("orrery", "travel", "speed_kmh", "teleport")
        and error["type"] == "extra_forbidden"
        for error in exc.value.errors()
    )


@pytest.mark.parametrize(
    ("toml_value", "error_type"),
    [
        ("0", "greater_than"),
        ("-1.0", "greater_than"),
        ("inf", "finite_number"),
        ("nan", "finite_number"),
    ],
)
def test_travel_value_rejects_non_positive_or_non_finite(
    tmp_path: Path, toml_value: str, error_type: str
) -> None:
    """A detour factor the route estimate cannot use fails at settings load."""
    source = Path("nexus.toml").read_text()
    table = _table(DETOUR_TABLE, source)
    edited, replaced = re.subn(
        r"^walking = .*$",
        f"walking = {toml_value}",
        table.group(0),
        count=1,
        flags=re.MULTILINE,
    )
    assert replaced == 1
    source = source[: table.start()] + edited + source[table.end() :]

    with pytest.raises(ValidationError) as exc:
        load_settings(_write_config(tmp_path, source))

    assert any(
        error["loc"] == ("orrery", "travel", "detour_factor", "walking")
        and error["type"] == error_type
        for error in exc.value.errors()
    )

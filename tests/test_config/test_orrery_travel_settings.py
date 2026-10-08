"""Orrery per-mode travel tables validated through the real nexus.toml path."""

from pathlib import Path
import re

import pytest
from pydantic import ValidationError

from nexus.agents.orrery.events import _route_estimate_from_distance
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


def test_shipped_travel_tables_match_the_calibrated_values() -> None:
    """The shipped tables pin sourced values and explicitly retained estimates."""
    orrery = load_settings().orrery
    assert orrery is not None
    travel = orrery.travel

    assert travel.speed_kmh.model_dump() == {
        "walking": 5.0,
        "vehicle": 45.0,
        "rail": 47.8,
        "water": 25.0,
        "air": 450.0,
        "covert": 2.4,
        "mixed": 25.0,
    }
    assert travel.detour_factor.model_dump() == {
        "walking": 1.35,
        "vehicle": 1.20,
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


@pytest.mark.parametrize(
    ("mode", "geodesic_m", "minutes"),
    [
        ("walking", 2148.2, 34.80),
        ("covert", 2148.2, 96.67),
        ("vehicle", 20885.6, 33.42),
        ("rail", 134099.8, 193.58),
        ("water", 8184.9, 27.50),
        ("air", 3983079.7, 557.63),
        ("mixed", 7251.7, 24.37),
    ],
)
def test_sample_route_estimates(mode: str, geodesic_m: float, minutes: float) -> None:
    """Shipped calibration yields the pinned real-Earth route estimates."""
    # Distances from read-only PostGIS on NEXUS_template:
    # ST_Distance(ST_SetSRID(ST_MakePoint(lon1,lat1),4326)::geography,
    #             ST_SetSRID(ST_MakePoint(lon2,lat2),4326)::geography).
    # Walking/covert: Times Square (-73.9855,40.7580) to Bethesda Terrace
    # (-73.9712,40.7740); vehicle: Grand Central (-73.9772,40.7527) to JFK
    # (-73.7781,40.6413); rail: Penn Station (-73.9935,40.7506) to Philadelphia
    # 30th Street (-75.1819,39.9557); water: Whitehall (-74.0131,40.7013) to
    # St. George (-74.0735,40.6437); air: JFK to LAX (-118.4085,33.9416);
    # mixed: Brooklyn Borough Hall (-73.9903,40.6928) to Times Square.
    route = _route_estimate_from_distance(
        geodesic_m,
        origin_place_id=1,
        destination_place_id=2,
        mode=mode,
        risk="low",
    )
    assert route["duration_minutes"] == pytest.approx(minutes, abs=0.01)

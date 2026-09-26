"""Genesis zone-boundary policy validated through the real nexus.toml path."""

from pathlib import Path
import re

import pytest
from pydantic import ValidationError

from nexus.config import load_settings

RADIUS_LINE = re.compile(r"^default_zone_radius_m = .*$", re.MULTILINE)


def _write_config(tmp_path: Path, source: str) -> Path:
    config = tmp_path / "nexus.toml"
    config.write_text(source)
    return config


def test_shipped_zone_radius_is_positive() -> None:
    """The committed genesis zone radius loads as a positive meter distance."""
    radius = load_settings().wizard.geo.default_zone_radius_m

    assert isinstance(radius, float)
    assert radius > 0


@pytest.mark.parametrize(
    ("toml_value", "error_type"),
    [
        ("0", "greater_than"),
        ("-80467", "greater_than"),
        ("inf", "finite_number"),
        ("nan", "finite_number"),
    ],
)
def test_zone_radius_rejects_non_positive_or_non_finite(
    tmp_path: Path, toml_value: str, error_type: str
) -> None:
    """A radius PostGIS cannot buffer by fails at settings load, not genesis."""
    source, replaced = RADIUS_LINE.subn(
        f"default_zone_radius_m = {toml_value}", Path("nexus.toml").read_text()
    )
    assert replaced == 1

    with pytest.raises(ValidationError) as exc:
        load_settings(_write_config(tmp_path, source))

    assert any(
        error["loc"] == ("wizard", "geo", "default_zone_radius_m")
        and error["type"] == error_type
        for error in exc.value.errors()
    )


def test_missing_wizard_geo_table_fails_load(tmp_path: Path) -> None:
    """No code default stands in for an absent [wizard.geo] table."""
    source = Path("nexus.toml").read_text()
    radius_line = RADIUS_LINE.search(source)
    assert radius_line is not None
    start = source.index("[wizard.geo]")
    assert start < radius_line.start()

    with pytest.raises(ValidationError) as exc:
        load_settings(
            _write_config(tmp_path, source[:start] + source[radius_line.end() :])
        )

    assert any(
        error["loc"] == ("wizard", "geo") and error["type"] == "missing"
        for error in exc.value.errors()
    )

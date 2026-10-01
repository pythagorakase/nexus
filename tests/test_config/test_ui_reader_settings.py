"""Feed bounds are required and validated through real TOML loading."""

from pathlib import Path
from typing import Any

import pytest
import tomlkit
from pydantic import ValidationError

from nexus.config import load_settings


def test_ui_reader_requires_closed_positive_ordered_bounds(tmp_path: Path) -> None:
    """No missing bounds, coercion, unknown keys or inverted pair can load."""
    shipped = load_settings().ui.reader
    assert (shipped.default_page_size, shipped.max_page_size) == (50, 200)
    path = tmp_path / "nexus.toml"
    source = Path("nexus.toml").read_text()
    document: Any = tomlkit.parse(source)
    document["ui"]["reader"] = {"default_page_size": 7, "max_page_size": 73}
    path.write_text(tomlkit.dumps(document))
    changed = load_settings(path).ui.reader
    assert (changed.default_page_size, changed.max_page_size) == (7, 73)
    invalid: list[Any] = [
        None,
        {},
        {"default_page_size": 1},
        {"max_page_size": 2},
        {"default_page_size": 2, "max_page_size": 1},
        {"default_page_size": 1, "max_page_size": 2, "unknown": 1},
    ]
    for field in ("default_page_size", "max_page_size"):
        for value in (True, 1.5, 0, -1):
            invalid.append({"default_page_size": 1, "max_page_size": 2, field: value})
    for bounds in invalid:
        document = tomlkit.parse(source)
        if bounds is None:
            del document["ui"]["reader"]
        else:
            document["ui"]["reader"] = bounds
        path.write_text(tomlkit.dumps(document))
        with pytest.raises(ValidationError):
            load_settings(path)

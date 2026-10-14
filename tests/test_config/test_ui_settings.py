"""Player display tunables are required and validated through real TOML loading."""

from pathlib import Path
from typing import Any

import pytest
import tomlkit
from pydantic import ValidationError

from nexus.config import load_settings


def test_ui_announcer_hold_is_required_and_bounded(tmp_path: Path) -> None:
    """No missing hold, coercion, unknown key, or out-of-range value can load."""
    assert load_settings().ui.announcer.hold_ms == 5000
    source = Path("nexus.toml").read_text()
    path = tmp_path / "nexus.toml"
    document: Any = tomlkit.parse(source)
    document["ui"]["announcer"] = {"hold_ms": 7300}
    path.write_text(tomlkit.dumps(document))
    assert load_settings(path).ui.announcer.hold_ms == 7300
    invalid: list[Any] = [None, {}, {"hold_ms": 5000, "unknown": 1}]
    invalid.extend({"hold_ms": value} for value in (True, 1.5, "5000", 999, 60001))
    for announcer in invalid:
        document = tomlkit.parse(source)
        if announcer is None:
            del document["ui"]["announcer"]
        else:
            document["ui"]["announcer"] = announcer
        path.write_text(tomlkit.dumps(document))
        with pytest.raises(ValidationError):
            load_settings(path)

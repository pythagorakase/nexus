"""Offline: the setup script's default slot model states its own contract.

``tests/test_new_story_setup.py`` is PostgreSQL-marked at module level; this
file needs no database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError
import pytest
import tomlkit

from nexus.runtime.home import resolve_config_path
from scripts import new_story_setup


def test_default_slot_model_raises_when_the_configuration_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid configuration raises; no placeholder model stands in for it."""
    doc: Any = tomlkit.parse(resolve_config_path().read_text())
    # An explicit key wins over the roster `uses`, which only fills an absent key.
    doc["global"]["model"]["default_slot_model"] = "NO_SUCH_MODEL"
    config = tmp_path / "invalid_default_slot_model.toml"
    config.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))

    with pytest.raises(ValidationError) as excinfo:
        new_story_setup._get_default_slot_model()

    message = str(excinfo.value)
    assert "default_slot_model" in message
    assert "NO_SUCH_MODEL" in message

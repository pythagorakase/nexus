"""Roster upgrades must be one edit, including every configured consumer."""

from copy import deepcopy
from pathlib import Path
import tomllib

import pytest
from pydantic import ValidationError

from nexus.config.settings_models import Settings

CONFIG = Path(__file__).resolve().parents[2] / "nexus.toml"


def _raw() -> dict:
    return tomllib.loads(CONFIG.read_text())


def _entries(raw: dict) -> list[dict]:
    return [
        entry
        for provider in raw["global"]["model"]["api_models"].values()
        for entry in provider["models"]
    ]


@pytest.mark.parametrize(
    "model_id", [e["id"] for e in _entries(_raw()) if e.get("uses")]
)
def test_one_roster_id_edit_upgrades_every_assigned_component(model_id: str) -> None:
    raw = _raw()
    entry = next(e for e in _entries(raw) if e["id"] == model_id)
    entry["id"] = model_id + "-next"
    before = deepcopy(raw)
    settings = Settings(**raw).model_dump()
    for path in entry["uses"]:
        current = settings
        for key in path.split("."):
            current = current[key]
        assert current == entry["id"], path
    assert raw == before, "Loading settings must not bake IDs back into the input"


def test_roster_rejects_ambiguous_component_assignments() -> None:
    raw = _raw()
    entries = _entries(raw)
    source = next(e for e in entries if e.get("uses"))
    target = next(e for e in entries if not e.get("uses"))
    target["uses"] = [source["uses"][0]]
    with pytest.raises(ValidationError, match="assigned more than once"):
        Settings(**raw)


def test_roster_rejects_unknown_component_paths() -> None:
    raw = _raw()
    _entries(raw)[0]["uses"] = ["apex.modle"]
    with pytest.raises(ValidationError, match="Unknown model use"):
        Settings(**raw)


def test_roster_rejects_duplicate_model_ids() -> None:
    raw = _raw()
    entries = _entries(raw)
    entries[1]["id"] = entries[0]["id"]
    with pytest.raises(ValidationError, match="Duplicate model ID"):
        Settings(**raw)


def test_required_selection_cannot_silently_disappear() -> None:
    raw = _raw()
    for entry in _entries(raw):
        if "apex.model" in entry.get("uses", []):
            entry["uses"].remove("apex.model")
    with pytest.raises(ValidationError, match="apex.model"):
        Settings(**raw)


def test_explicit_runtime_override_is_validated_and_leaves_roster_intact() -> None:
    raw = _raw()
    raw["apex"]["model"] = "TEST"
    before = deepcopy(raw)
    assert Settings(**raw).apex.model == "TEST"
    assert raw == before
    raw["apex"]["model"] = "@openai.default"
    with pytest.raises(ValidationError, match="not declared"):
        Settings(**raw)

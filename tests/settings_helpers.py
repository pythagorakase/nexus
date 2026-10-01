"""Typed settings for tests that vary a few configured values."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel
import tomlkit

from nexus.config import load_settings
from nexus.config.settings_models import Settings
from nexus.runtime.home import resolve_config_path


def settings_with(
    overrides: Mapping[str, Any] | None = None,
    *,
    path: str | Path | None = None,
) -> Settings:
    """Return validated ``nexus.toml`` settings with dotted-path overrides.

    Keys name the TOML path (``"apex.turn_pipeline"``,
    ``"global.model.api_models"``), so an override is validated exactly as a
    configuration edit would be: an unknown key or an invalid value raises.
    """

    data = load_settings(path).model_dump()
    for dotted, value in (overrides or {}).items():
        *parents, leaf = dotted.split(".")
        node = data
        for key in parents:
            if not isinstance(node.get(key), dict):
                raise KeyError(f"{dotted}: {key!r} is not a settings table")
            node = node[key]
        node[leaf] = value
    return Settings.model_validate(data)


def table(model: type[BaseModel], values: Mapping[str, Any] | None = None) -> Any:
    """Return one whole settings table: ``values`` over the model's defaults.

    Replacing a table this way keeps every unnamed key at its model default,
    which is what a partial table in a hand-built settings dict used to mean.
    """

    return model.model_validate(dict(values or {})).model_dump(by_alias=True)


def renamed_test_model_config(
    tmp_path: Path, model_id: str, port: int | None = None
) -> Path:
    """Write the active configuration with the TEST provider's model renamed.

    The copy is the file ``load_settings()`` would read, with the single
    ``[global.model.api_models.test]`` model's ``id`` set to ``model_id``; its
    ``uses`` list carries ``default_slot_model`` to the new id. When ``port`` is
    given, the test ``base_url`` and ``[runtime.services.mock_openai].port``
    move to that port together. No other key changes. Call this before setting
    ``NEXUS_RUNTIME_CONFIG``.
    """

    doc: Any = tomlkit.parse(resolve_config_path().read_text())
    test_provider = doc["global"]["model"]["api_models"]["test"]
    models = test_provider["models"]
    assert len(models) == 1, f"expected one TEST model, found {len(models)}"
    models[0]["id"] = model_id
    if port is not None:
        test_provider["base_url"] = f"http://127.0.0.1:{port}/v1"
        doc["runtime"]["services"]["mock_openai"]["port"] = port
    path = tmp_path / "renamed_test.toml"
    path.write_text(tomlkit.dumps(doc))
    return path

"""Typed settings for tests that vary a few configured values."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel

from nexus.config import load_settings
from nexus.config.settings_models import Settings


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

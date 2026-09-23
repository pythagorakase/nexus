"""Player preferences persisted under the configured runtime state directory."""

from __future__ import annotations

import os
import tempfile
import threading
import tomllib
from pathlib import Path
from typing import Any

import tomlkit

from nexus.config.loader import load_settings
from nexus.config.settings_models import PreferencesSettings, Settings

_write_lock = threading.Lock()


def preferences_path(settings: Settings) -> Path:
    """Resolve the player file using the runtime supervisor's state-dir rule."""
    if settings.runtime is None:
        raise RuntimeError("Player preferences require [runtime].state_dir")
    state_dir = Path(settings.runtime.state_dir).expanduser()
    if not state_dir.is_absolute():
        state_dir = Path(__file__).resolve().parents[2] / state_dir
    return state_dir / "preferences.toml"


def load_preferences(settings: Settings | None = None) -> PreferencesSettings:
    """Read validated preferences, using repository defaults before first write."""
    settings = settings or load_settings()
    path = preferences_path(settings)
    if path.exists():
        with path.open("rb") as stream:
            return PreferencesSettings.model_validate(tomllib.load(stream))
    return PreferencesSettings(
        theme=settings.ui.theme,
        fonts=settings.ui.fonts,
        wizard_model=settings.wizard.default_model,
    )


def save_preferences(
    updates: dict[str, Any], settings: Settings | None = None
) -> PreferencesSettings:
    """Validate and atomically persist a partial preference update."""
    settings = settings or load_settings()
    with _write_lock:
        data = load_preferences(settings).model_dump()
        for key, value in updates.items():
            if key == "fonts":
                for theme, slots in value.items():
                    data["fonts"][theme].update(slots)
            else:
                data[key] = value
        preferences = PreferencesSettings.model_validate(data)
        settings.resolve_model_ref(preferences.wizard_model)
        path = preferences_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, delete=False, encoding="utf-8"
            ) as stream:
                temporary = stream.name
                stream.write(tomlkit.dumps(preferences.model_dump()))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        return preferences

"""Integration coverage for LORE's managed-runtime configuration boundary."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, NamedTuple, cast

import pytest
import tomlkit

from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.config import load_settings
from nexus.config.loader import RUNTIME_CONFIG_ENV
from nexus.config.settings_models import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG = REPO_ROOT / "nexus.toml"

pytestmark = pytest.mark.requires_postgres


class AlternateConfig(NamedTuple):
    """Registry-derived alternate config and its resolved storyteller seats."""

    path: Path
    writer_value: str
    writer_model: str
    gaia_value: str
    gaia_model: str


def _role_refs_by_target(settings: Settings) -> Dict[str, str]:
    """Return real registry role references keyed by their resolved model IDs."""
    refs: Dict[str, str] = {}
    for provider_name, provider in settings.global_.model.api_models.items():
        for role_name, model_id in provider.roles.items():
            refs.setdefault(model_id, f"@{provider_name}.{role_name}")
    return refs


def _write_alternate_config(tmp_path: Path) -> AlternateConfig:
    """Write a real config using any two distinct registry models."""
    repository_settings = load_settings(REPO_CONFIG)
    role_refs = _role_refs_by_target(repository_settings)
    distinct_models: list[str] = []
    seen_models: set[str] = set()
    for provider in repository_settings.global_.model.api_models.values():
        for model in provider.models:
            if model.id not in seen_models:
                seen_models.add(model.id)
                distinct_models.append(model.id)
    if len(distinct_models) < 2:
        pytest.skip("runtime-config precedence needs two distinct registry models")
    config_values = [
        (model_id, role_refs.get(model_id, model_id)) for model_id in distinct_models
    ]
    # Exercise role resolution when roles exist, while remaining valid for a
    # future registry whose model entries do not all have named roles.
    config_values.sort(key=lambda item: (not item[1].startswith("@"), item[0]))
    (writer_model, writer_value), (gaia_model, gaia_value) = config_values[:2]

    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    apex = cast(Any, document["apex"])
    apex["model"] = writer_value
    apex["gaia_model"] = gaia_value
    alternate_path = tmp_path / "alternate-nexus.toml"
    alternate_path.write_text(tomlkit.dumps(document), encoding="utf-8")

    alternate_settings = load_settings(alternate_path)
    assert alternate_settings.apex.model == writer_model
    assert alternate_settings.apex.gaia_model == gaia_model
    return AlternateConfig(
        path=alternate_path,
        writer_value=writer_value,
        writer_model=writer_model,
        gaia_value=gaia_value,
        gaia_model=gaia_model,
    )


def test_lore_honors_runtime_config_for_both_storyteller_seats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The managed-runtime config reaches LORE and LOGON without a paid turn."""
    alternate = _write_alternate_config(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(alternate.path))
    caplog.set_level(logging.INFO, logger="nexus.lore")

    lore = LORE(enable_logon=False, slot=1)
    try:
        apex = lore.settings["API Settings"]["apex"]
        assert lore.settings_path == alternate.path.resolve()
        assert apex["model"] == alternate.writer_model
        assert apex["gaia_model"] == alternate.gaia_model

        routing = LogonUtility(
            lore.settings,
            dbname="save_01",
            model_override=alternate.writer_value,
            settings_path=lore.settings_path,
        )
        assert (
            routing.settings["API Settings"]["apex"]["gaia_model"]
            == alternate.gaia_model
        )
        assert routing.resolve_storyteller_route()[0] == alternate.writer_model
        assert any(
            f"effective config path {alternate.path.resolve()}" in message
            for message in caplog.messages
        )
    finally:
        lore.close()


def test_explicit_lore_settings_path_beats_runtime_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit caller path remains authoritative over the runtime env var."""
    alternate = _write_alternate_config(tmp_path)
    missing_runtime_config = tmp_path / "missing-runtime.toml"
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(missing_runtime_config))

    lore = LORE(settings_path=str(alternate.path), enable_logon=True, slot=1)
    try:
        apex = lore.settings["API Settings"]["apex"]
        assert lore.settings_path == alternate.path.resolve()
        assert apex["model"] == alternate.writer_model
        assert apex["gaia_model"] == alternate.gaia_model

        lore.ensure_logon()
        assert lore.logon is not None
        assert lore.logon.settings_path == alternate.path.resolve()
        lore.logon.model_override = alternate.writer_value
        assert lore.logon.resolve_storyteller_route()[0] == alternate.writer_model
    finally:
        lore.close()


def test_lore_without_runtime_environment_falls_back_to_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The no-env fallback is repository-root nexus.toml, independent of cwd."""
    monkeypatch.delenv(RUNTIME_CONFIG_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    repository_settings = load_settings(REPO_CONFIG)

    lore = LORE(enable_logon=False, slot=1)
    try:
        apex = lore.settings["API Settings"]["apex"]
        assert lore.settings_path == REPO_CONFIG.resolve()
        assert apex["model"] == repository_settings.apex.model
        assert apex["gaia_model"] == repository_settings.apex.gaia_model
    finally:
        lore.close()

"""Integration coverage for LORE's managed-runtime configuration boundary."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Tuple

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


def _role_refs_by_target(settings: Settings) -> Dict[str, str]:
    """Return real registry role references keyed by their resolved model IDs."""
    refs: Dict[str, str] = {}
    for provider_name, provider in settings.global_.model.api_models.items():
        for role_name, model_id in provider.roles.items():
            refs.setdefault(model_id, f"@{provider_name}.{role_name}")
    return refs


def _write_alternate_config(tmp_path: Path) -> Tuple[Path, str, str]:
    """Write a real config whose writer and Gaia swap registry-backed roles."""
    repository_settings = load_settings(REPO_CONFIG)
    repository_writer = repository_settings.apex.model
    repository_gaia = repository_settings.apex.gaia_model
    assert repository_gaia is not None
    assert repository_writer != repository_gaia

    role_refs = _role_refs_by_target(repository_settings)
    alternate_writer_ref = role_refs[repository_gaia]
    alternate_gaia_ref = role_refs[repository_writer]

    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    document["apex"]["model"] = alternate_writer_ref
    document["apex"]["gaia_model"] = alternate_gaia_ref
    alternate_path = tmp_path / "alternate-nexus.toml"
    alternate_path.write_text(tomlkit.dumps(document), encoding="utf-8")

    alternate_settings = load_settings(alternate_path)
    assert alternate_settings.apex.model != repository_writer
    assert alternate_settings.apex.gaia_model != repository_gaia
    return (
        alternate_path,
        alternate_settings.apex.model,
        alternate_settings.apex.gaia_model,
    )


def test_lore_honors_runtime_config_for_both_storyteller_seats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The managed-runtime config reaches LORE and LOGON without a paid turn."""
    alternate_path, alternate_writer, alternate_gaia = _write_alternate_config(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(alternate_path))
    caplog.set_level(logging.INFO, logger="nexus.lore")

    lore = LORE(enable_logon=False, slot=1)
    try:
        apex = lore.settings["API Settings"]["apex"]
        assert lore.settings_path == alternate_path.resolve()
        assert apex["model"] == alternate_writer
        assert apex["gaia_model"] == alternate_gaia

        routing = LogonUtility(
            lore.settings,
            dbname="save_01",
            model_override=alternate_writer,
        )
        assert routing.settings["API Settings"]["apex"]["gaia_model"] == alternate_gaia
        assert routing.resolve_storyteller_route()[0] == alternate_writer
        assert any(
            f"effective config path {alternate_path.resolve()}" in message
            for message in caplog.messages
        )
    finally:
        lore.close()


def test_explicit_lore_settings_path_beats_runtime_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit caller path remains authoritative over the runtime env var."""
    alternate_path, _, _ = _write_alternate_config(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(alternate_path))
    repository_settings = load_settings(REPO_CONFIG)

    lore = LORE(settings_path=str(REPO_CONFIG), enable_logon=False, slot=1)
    try:
        apex = lore.settings["API Settings"]["apex"]
        assert lore.settings_path == REPO_CONFIG.resolve()
        assert apex["model"] == repository_settings.apex.model
        assert apex["gaia_model"] == repository_settings.apex.gaia_model
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

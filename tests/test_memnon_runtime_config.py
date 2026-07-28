"""Integration coverage for MEMNON's import-time runtime configuration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, cast

import tomlkit

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG = REPO_ROOT / "nexus.toml"


def _write_config(tmp_path: Path, name: str, *, memnon_debug: bool) -> Path:
    """Write a real temporary config with an observable MEMNON value."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    memnon = cast(Any, document["memnon"])
    memnon["debug"] = memnon_debug
    path = tmp_path / name
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _import_memnon(
    tmp_path: Path, environment: Dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Import MEMNON in a fresh interpreter under the supplied config paths."""
    process_environment = dict(os.environ)
    process_environment.update(environment)
    process_environment["PYTHONPATH"] = str(REPO_ROOT)
    code = (
        "import json\n"
        "from nexus.agents.memnon import memnon\n"
        "print(json.dumps({'debug': memnon.MEMNON_SETTINGS['debug']}))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env=process_environment,
        cwd=tmp_path,
    )


def test_memnon_uses_runtime_config_instead_of_legacy_settings_path(
    tmp_path: Path,
) -> None:
    """The managed runtime path is the sole default-path authority."""
    runtime_config = _write_config(tmp_path, "runtime.toml", memnon_debug=False)
    legacy_config = _write_config(tmp_path, "legacy.toml", memnon_debug=True)

    result = _import_memnon(
        tmp_path,
        {
            "NEXUS_RUNTIME_CONFIG": str(runtime_config),
            "NEXUS_SETTINGS_PATH": str(legacy_config),
        },
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {"debug": False}


def test_memnon_import_fails_loudly_for_missing_runtime_config(
    tmp_path: Path,
) -> None:
    """A bad managed-runtime path must abort import instead of yielding {}."""
    missing_runtime_config = tmp_path / "missing-runtime.toml"
    legacy_config = _write_config(tmp_path, "legacy.toml", memnon_debug=True)

    result = _import_memnon(
        tmp_path,
        {
            "NEXUS_RUNTIME_CONFIG": str(missing_runtime_config),
            "NEXUS_SETTINGS_PATH": str(legacy_config),
        },
    )

    assert result.returncode != 0
    assert "FileNotFoundError" in result.stderr
    assert str(missing_runtime_config) in result.stderr

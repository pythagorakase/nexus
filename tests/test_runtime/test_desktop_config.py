"""The Python desktop diagnostic reads real files using the shell's contract."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pytest

from nexus.runtime.desktop_config import (
    DesktopConfig,
    DesktopConfigError,
    load_effective_desktop_config,
    resolve_runtime_program,
)

ROOT = Path(__file__).resolve().parents[2]
RELATIVE_CONFIG = Path("ui/src-tauri/nexus.desktop.json")


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No inherited desktop selection can point these cases at an owner's file."""
    monkeypatch.delenv("NEXUS_DESKTOP_CONFIG", raising=False)
    monkeypatch.delenv("NEXUS_DESKTOP_RUNTIME_ORIGIN", raising=False)
    monkeypatch.chdir(tmp_path)


def _write(path: Path, **fields: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def test_lookup_follows_the_shell_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit bad file never falls through to a healthy checkout or bundle."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "pyproject.toml").touch()
    (checkout / "nexus.toml").touch()
    checkout_config = _write(checkout / RELATIVE_CONFIG)
    inside = checkout / "inside"
    inside.mkdir()
    monkeypatch.chdir(inside)
    package_root = tmp_path / "package"
    bundled = _write(package_root / RELATIVE_CONFIG)
    explicit = _write(tmp_path / "chosen.json", runtimeOrigin="http://localhost:8031")
    monkeypatch.setenv("NEXUS_DESKTOP_CONFIG", str(explicit))
    effective = load_effective_desktop_config(package_root)
    assert (effective.source, effective.path) == ("NEXUS_DESKTOP_CONFIG", explicit)
    assert effective.runtime_origin == "http://localhost:8031"

    explicit.write_text("not json", encoding="utf-8")
    with pytest.raises(DesktopConfigError, match="chosen.json is invalid"):
        load_effective_desktop_config(package_root)
    explicit.unlink()
    with pytest.raises(DesktopConfigError, match="failed to read.*chosen.json"):
        load_effective_desktop_config(package_root)
    monkeypatch.setenv("NEXUS_DESKTOP_CONFIG", "")
    with pytest.raises(DesktopConfigError, match="failed to read"):
        load_effective_desktop_config(package_root)

    monkeypatch.delenv("NEXUS_DESKTOP_CONFIG")
    effective = load_effective_desktop_config(package_root)
    assert (effective.source, effective.path) == ("checkout", checkout_config)
    assert effective.working_directory == checkout
    monkeypatch.chdir(tmp_path)
    effective = load_effective_desktop_config(package_root)
    assert (effective.source, effective.path) == ("bundled", bundled)
    assert effective.working_directory == tmp_path
    bundled.unlink()
    with pytest.raises(DesktopConfigError, match="NEXUS_DESKTOP_CONFIG.*missing"):
        load_effective_desktop_config(package_root)


def test_defaults_strictness_and_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defaults mirror serde and origins/relative paths resolve without coercion."""
    path = _write(tmp_path / "config" / "desktop.json", runtimeOrigin="http://x")
    monkeypatch.setenv("NEXUS_DESKTOP_CONFIG", str(path))
    effective = load_effective_desktop_config(tmp_path)
    assert effective.config.model_dump(by_alias=True) == {
        "runtimeOrigin": "http://x",
        "statusPath": "/runtime/status",
        "authHeader": "X-Nexus-Auth",
        "authTokenEnv": "NEXUS_AUTH",
        "runtimeCommand": ["nexus"],
        "startArgs": ["--json", "up"],
        "restartArgs": ["--json", "restart"],
        "stopArgs": ["--json", "down"],
        "workingDirectory": None,
        "startupTimeoutSeconds": 90,
        "pollIntervalMilliseconds": 500,
        "commandTimeoutSeconds": 120,
    }
    _write(path, runtimeOrigin="http://127.0.0.1:8002/x?y#z", unknown="ignored")
    assert load_effective_desktop_config(tmp_path).runtime_origin == (
        "http://127.0.0.1:8002"
    )
    monkeypatch.setenv("NEXUS_DESKTOP_RUNTIME_ORIGIN", "https://example.com:443/x")
    assert (
        load_effective_desktop_config(tmp_path).runtime_origin == "https://example.com"
    )
    monkeypatch.setenv("NEXUS_DESKTOP_RUNTIME_ORIGIN", "  ")
    assert load_effective_desktop_config(tmp_path).runtime_origin == (
        "http://127.0.0.1:8002"
    )
    _write(path, workingDirectory="relative")
    assert load_effective_desktop_config(tmp_path).working_directory == (
        path.parent / "relative"
    )
    _write(path, runtimeOrigin="ftp://x")
    with pytest.raises(DesktopConfigError, match="http or https"):
        load_effective_desktop_config(tmp_path)
    _write(path, runtimeOrigin="http://")
    with pytest.raises(DesktopConfigError, match="host"):
        load_effective_desktop_config(tmp_path)
    _write(path, authHeader=None)
    with pytest.raises(DesktopConfigError, match="authHeader"):
        load_effective_desktop_config(tmp_path)


@pytest.mark.parametrize(
    "field",
    ["startupTimeoutSeconds", "pollIntervalMilliseconds", "commandTimeoutSeconds"],
)
def test_timeout_fields_match_strict_rust_u64(
    field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All three serde u64 fields reject coercion, negatives and overflow."""
    path = tmp_path / "desktop.json"
    monkeypatch.setenv("NEXUS_DESKTOP_CONFIG", str(path))
    for value in (0, 2**64 - 1):
        _write(path, **{field: value})
        assert (
            load_effective_desktop_config(tmp_path).config.model_dump(by_alias=True)[
                field
            ]
            == value
        )
    for value in (-1, 2**64, "90", 90.0, True, None):
        _write(path, **{field: value})
        with pytest.raises(DesktopConfigError, match=field):
            load_effective_desktop_config(tmp_path)


def test_fields_match_the_shell_struct() -> None:
    """A Rust field addition requires an explicit Python mirror update."""
    source = (ROOT / "ui/src-tauri/src/lib.rs").read_text(encoding="utf-8")
    match = re.search(r"pub struct DesktopConfig \{(.*?)\n\}", source, re.S)
    assert match is not None
    rust_fields = re.findall(r"pub (\w+):", match.group(1))
    aliases = {
        name.split("_")[0] + "".join(word.title() for word in name.split("_")[1:])
        for name in rust_fields
    }
    assert aliases == {field.alias for field in DesktopConfig.model_fields.values()}
    assert len(aliases) == len(rust_fields)
    DesktopConfig.model_validate_json((ROOT / RELATIVE_CONFIG).read_text())


def test_runtime_program_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real files prove PATH precedence, fixed directories and explicit paths."""
    program = "qa803-runtime-tool"
    path_dir = tmp_path / "path-bin"
    path_dir.mkdir()
    on_path = path_dir / program
    on_path.write_text("#!/bin/sh\nexit 0\n")
    on_path.chmod(0o755)
    home = tmp_path / "home"
    fixed = home / ".local/bin" / program
    fixed.parent.mkdir(parents=True)
    fixed.write_text("#!/bin/sh\nexit 0\n")
    fixed.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(path_dir))
    assert resolve_runtime_program(program, tmp_path) == (on_path, "PATH")
    monkeypatch.setenv("PATH", "")
    assert resolve_runtime_program(program, tmp_path) == (
        fixed,
        "the shell's fixed directories",
    )
    assert resolve_runtime_program(str(on_path), tmp_path) == (on_path, "path")
    assert resolve_runtime_program("bin/tool", tmp_path) == (
        tmp_path / "bin/tool",
        "path",
    )
    assert resolve_runtime_program("qa803-no-such-program", tmp_path) == (None, "")

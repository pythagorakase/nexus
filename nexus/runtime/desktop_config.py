"""Mirror the desktop format owned by ``ui/src-tauri/src/lib.rs``.

Change both readers together: defaults, discovery order, origins and command
lookup are a shared contract. Python cannot discover the running shell's
executable or its build checkout; the bundled copy is beside this package.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Literal, Optional
from urllib.parse import urlsplit, urlunsplit

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter

_U64_MAX = 2**64 - 1
_CONFIG_PATH = Path("ui/src-tauri/nexus.desktop.json")


class DesktopConfig(BaseModel):
    """The shell's strict serde fields, camelCase aliases and defaults."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)

    runtime_origin: str = Field(default="http://127.0.0.1:8002", alias="runtimeOrigin")
    status_path: str = Field(default="/runtime/status", alias="statusPath")
    auth_header: str = Field(default="X-Nexus-Auth", alias="authHeader")
    auth_token_env: str = Field(default="NEXUS_AUTH", alias="authTokenEnv")
    runtime_command: list[str] = Field(
        default_factory=lambda: ["nexus"], alias="runtimeCommand"
    )
    start_args: list[str] = Field(
        default_factory=lambda: ["--json", "up"], alias="startArgs"
    )
    restart_args: list[str] = Field(
        default_factory=lambda: ["--json", "restart"], alias="restartArgs"
    )
    stop_args: list[str] = Field(
        default_factory=lambda: ["--json", "down"], alias="stopArgs"
    )
    working_directory: Optional[str] = Field(default=None, alias="workingDirectory")
    startup_timeout_seconds: int = Field(
        default=90, alias="startupTimeoutSeconds", ge=0, le=_U64_MAX
    )
    poll_interval_milliseconds: int = Field(
        default=500, alias="pollIntervalMilliseconds", ge=0, le=_U64_MAX
    )
    command_timeout_seconds: int = Field(
        default=120, alias="commandTimeoutSeconds", ge=0, le=_U64_MAX
    )


class DesktopConfigError(ValueError):
    """The shell's effective configuration cannot be read or resolved."""


@dataclass(frozen=True)
class EffectiveDesktopConfig:
    """Configuration together with its source and resolved launch context."""

    config: DesktopConfig
    source: Literal["NEXUS_DESKTOP_CONFIG", "checkout", "bundled"]
    path: Path
    runtime_origin: str
    working_directory: Path


def discover_checkout(start: Path) -> Optional[Path]:
    """Find the first checkout above start; Python cannot seed from the shell exe."""
    return next(
        (
            path
            for path in (start, *start.parents)
            if (path / "pyproject.toml").exists() and (path / "nexus.toml").exists()
        ),
        None,
    )


def normalize_runtime_origin(origin: str) -> str:
    """Validate an HTTP(S) origin and discard its path, query and fragment."""
    try:
        scheme = urlsplit(origin).scheme
        if scheme not in {"http", "https"}:
            raise DesktopConfigError(
                f"runtimeOrigin must use http or https, got {scheme!r}"
            )
        normalized = TypeAdapter(AnyHttpUrl).validate_python(origin)
        parts = urlsplit(str(normalized))
    except ValueError as exc:
        raise DesktopConfigError(
            f"invalid runtime origin {origin}: {' '.join(str(exc).split())}"
        ) from exc
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _read_config(path: Path) -> DesktopConfig:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DesktopConfigError(f"failed to read {path}: {exc}") from exc
    try:
        return DesktopConfig.model_validate_json(raw)
    except ValueError as exc:
        raise DesktopConfigError(
            f"{path} is invalid: {' '.join(str(exc).split())}"
        ) from exc


def load_effective_desktop_config(package_root: Path) -> EffectiveDesktopConfig:
    """Read the explicit, discovered-checkout or packaged config without fallback."""
    cwd = Path.cwd()
    checkout = discover_checkout(cwd)
    bundled = package_root / _CONFIG_PATH
    source: Literal["NEXUS_DESKTOP_CONFIG", "checkout", "bundled"]
    if "NEXUS_DESKTOP_CONFIG" in os.environ:
        path = Path(os.environ["NEXUS_DESKTOP_CONFIG"])
        source = "NEXUS_DESKTOP_CONFIG"
    elif checkout is not None and (checkout / _CONFIG_PATH).exists():
        path = checkout / _CONFIG_PATH
        source = "checkout"
    elif bundled.exists():
        path = bundled
        source = "bundled"
    else:
        raise DesktopConfigError(
            "no desktop config: NEXUS_DESKTOP_CONFIG is unset, no checkout above "
            f"{cwd} holds {_CONFIG_PATH}, and {bundled} is missing"
        )
    config = _read_config(path)
    override = os.environ.get("NEXUS_DESKTOP_RUNTIME_ORIGIN", "")
    origin = normalize_runtime_origin(
        override if override.strip() else config.runtime_origin
    )
    if config.working_directory is None:
        working_directory = checkout or cwd
    else:
        working_directory = Path(config.working_directory)
        if not working_directory.is_absolute():
            working_directory = path.absolute().parent / working_directory
    return EffectiveDesktopConfig(config, source, path, origin, working_directory)


def shell_bin_dirs() -> list[Path]:
    """Return the shell's fixed search directories in its declared order."""
    directories = [
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/bin"),
        Path.home() / ".local/bin",
        Path.home() / ".cargo/bin",
    ]
    if sys.platform == "win32":
        if "APPDATA" in os.environ:
            directories.append(Path(os.environ["APPDATA"]) / "Python/Scripts")
        if "LOCALAPPDATA" in os.environ:
            local = Path(os.environ["LOCALAPPDATA"])
            directories.extend(
                local / suffix
                for suffix in (
                    "Programs/Python/Python311/Scripts",
                    "Programs/Python/Python312/Scripts",
                    "Programs/Python/Python313/Scripts",
                    "pypoetry/Cache/virtualenvs",
                )
            )
        if "ProgramFiles" in os.environ:
            directories.append(Path(os.environ["ProgramFiles"]) / "NEXUS/bin")
    return directories


def resolve_runtime_program(
    program: str, working_directory: Path
) -> tuple[Optional[Path], str]:
    """Resolve a program through path syntax, PATH, then the shell's directories."""
    path = Path(program)
    if path.is_absolute() or "/" in program or os.sep in program:
        return (
            path if path.is_absolute() else working_directory / path,
            "path",
        )
    if "PATH" in os.environ:
        for entry in os.environ["PATH"].split(os.pathsep):
            candidate = Path(entry) / program
            if candidate.is_file():
                return candidate, "PATH"
    for directory in shell_bin_dirs():
        candidate = directory / program
        if candidate.is_file():
            return candidate, "the shell's fixed directories"
    return None, ""

"""The runtime home: where the active config and mutable runtime data live.

One resolver owns two questions every runtime reader used to answer on its own
(issue #820): which ``nexus.toml`` is active, and what a relative directory in
it is relative to.

Locator rule
------------
- ``NEXUS_HOME`` set: the home root is that directory (an absolute path), the
  active configuration is ``$NEXUS_HOME/nexus.toml``, and relative layout paths
  resolve under the home.
- ``NEXUS_RUNTIME_CONFIG`` remains the supervisor's spawn seam: it names the
  config a supervised service was launched from. Set alone, it selects the
  configuration and the root stays the checkout.
- Both set: they must name the same file, or :class:`RuntimeHomeError` is
  raised, so two active configurations cannot exist. An explicit config
  (``nexus up --config``) outranks ``NEXUS_RUNTIME_CONFIG`` as before and is
  held to the same agreement with ``NEXUS_HOME``.
- Neither set (developer mode): the root is the checkout and the configuration
  is its ``nexus.toml``, the behavior before the runtime home existed.

``NEXUS_HOME`` locates the home; it is not another configuration system.
Everything inside the home is still configured by that home's ``nexus.toml``.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePath
from typing import Literal, Optional, Union

from nexus.config.loader import load_settings
from nexus.config.settings_models import Settings
from nexus.runtime.contract import HOME_ENV, RUNTIME_CONFIG_ENV

CONFIG_FILENAME = "nexus.toml"

# Home-layout directories that no runtime reader locates yet. Each becomes a
# nexus.toml key in the #820 slice that gives it a runtime owner; until then
# the resolver names them so `nexus home plan` and later slices share one
# layout. UPLOADS_DIR mirrors the upload root the asset endpoints and static
# mounts use today (tests pin the agreement).
UPLOADS_DIR = PurePath("ui", "client", "public")
UPLOAD_SUBDIRS = ("character_portraits", "place_images")
MODELS_DIR = PurePath("models")
CACHE_DIR = PurePath(".nexus", "cache")
BACKUPS_DIR = PurePath(".nexus", "backups")

Locator = Literal["NEXUS_HOME", "explicit", "NEXUS_RUNTIME_CONFIG", "checkout"]


class RuntimeHomeError(RuntimeError):
    """The runtime-home locators are malformed or name two configurations."""


def repo_root() -> Path:
    """The checkout root, derived from the nexus package location."""
    return Path(__file__).resolve().parents[2]


def anchor_path(root: Path, configured: Union[str, PurePath]) -> Path:
    """Expand ``~`` and anchor a relative configured path under ``root``.

    This is the one implementation of relative-path anchoring for runtime
    directories: absolute paths (after ``~`` expansion) are returned as
    configured, relative ones are joined to the home root.
    """
    path = Path(configured).expanduser()
    return path if path.is_absolute() else root / path


@dataclass(frozen=True)
class HomeLocation:
    """The home root and active configuration named by the locators."""

    root: Path
    config_path: Path
    locator: Locator


def _environment_path(name: str) -> Optional[Path]:
    """Return a path-valued environment variable, treating empty as unset."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return Path(raw).expanduser()


def locate_runtime_home(config_path: Union[str, Path, None] = None) -> HomeLocation:
    """Apply the locator rule and return the home root and active config.

    ``config_path`` is an explicit configuration (``nexus up --config``). It
    outranks ``NEXUS_RUNTIME_CONFIG`` and, like it, must agree with
    ``NEXUS_HOME`` when that is set. Nothing is created or read here.

    Raises:
        RuntimeHomeError: ``NEXUS_HOME`` is relative, or a set config locator
            names a different file than ``$NEXUS_HOME/nexus.toml``.
    """
    home = _environment_path(HOME_ENV)
    runtime_config = _environment_path(RUNTIME_CONFIG_ENV)
    explicit = Path(config_path).expanduser() if config_path is not None else None

    if home is None:
        checkout = repo_root()
        if explicit is not None:
            return HomeLocation(checkout, explicit.resolve(), "explicit")
        if runtime_config is not None:
            return HomeLocation(
                checkout, runtime_config.resolve(), "NEXUS_RUNTIME_CONFIG"
            )
        return HomeLocation(
            checkout, (checkout / CONFIG_FILENAME).resolve(), "checkout"
        )

    if not home.is_absolute():
        raise RuntimeHomeError(
            f"{HOME_ENV} must be an absolute path, got {str(home)!r}: a relative "
            "home would change with each process's working directory."
        )
    root = home.resolve()
    derived = (root / CONFIG_FILENAME).resolve()
    for label, candidate in (
        ("the explicit --config path", explicit),
        (RUNTIME_CONFIG_ENV, runtime_config),
    ):
        if candidate is not None and candidate.resolve() != derived:
            raise RuntimeHomeError(
                f"{HOME_ENV}={root} makes {derived} the active configuration, "
                f"but {label} names {candidate.resolve()}. Two active "
                f"configurations are not allowed: unset one locator or point "
                f"it at {derived}."
            )
    return HomeLocation(root, derived, "NEXUS_HOME")


def resolve_config_path(config_path: Union[str, Path, None] = None) -> Path:
    """Return the active ``nexus.toml`` path under the locator rule."""
    return locate_runtime_home(config_path).config_path


@dataclass(frozen=True)
class RuntimeHome:
    """Absolute locations of the active configuration and runtime data.

    ``logs_dir`` equals ``state_dir``: the supervisor captures each service's
    log beside its pidfile (issue #842). ``cache_dir``, ``backups_dir``,
    ``models_dir`` and ``uploads_dir`` name the home layout that later #820
    slices move data into; in this slice the upload endpoints still serve the
    checkout's ``ui/client/public`` and model paths stay as configured.
    """

    root: Path
    config_path: Path
    locator: Locator
    state_dir: Path
    logs_dir: Path
    usage_dir: Path
    cache_dir: Path
    backups_dir: Path
    models_dir: Path
    uploads_dir: Path

    def as_dict(self) -> dict[str, str]:
        """Return the layout as strings for JSON output."""
        return {
            "root": str(self.root),
            "config_path": str(self.config_path),
            "locator": self.locator,
            "state_dir": str(self.state_dir),
            "logs_dir": str(self.logs_dir),
            "usage_dir": str(self.usage_dir),
            "cache_dir": str(self.cache_dir),
            "backups_dir": str(self.backups_dir),
            "models_dir": str(self.models_dir),
            "uploads_dir": str(self.uploads_dir),
        }


def build_runtime_home(location: HomeLocation, settings: Settings) -> RuntimeHome:
    """Lay out a runtime home at ``location`` from a validated settings tree.

    Raises:
        RuntimeHomeError: the settings have no ``[runtime]`` section.
    """
    if settings.runtime is None:
        raise RuntimeHomeError(
            f"{location.config_path} has no [runtime] section; the runtime home "
            "needs [runtime].state_dir."
        )
    root = location.root
    state_dir = anchor_path(root, settings.runtime.state_dir)
    return RuntimeHome(
        root=root,
        config_path=location.config_path,
        locator=location.locator,
        state_dir=state_dir,
        logs_dir=state_dir,
        usage_dir=anchor_path(root, settings.usage.usage_dir),
        cache_dir=anchor_path(root, CACHE_DIR),
        backups_dir=anchor_path(root, BACKUPS_DIR),
        models_dir=anchor_path(root, MODELS_DIR),
        uploads_dir=anchor_path(root, UPLOADS_DIR),
    )


def resolve_runtime_home(
    settings: Optional[Settings] = None,
    *,
    config_path: Union[str, Path, None] = None,
) -> RuntimeHome:
    """Resolve the active runtime home under the locator rule.

    Args:
        settings: The validated settings whose relative directories are
            anchored. When omitted, the active configuration is loaded.
        config_path: An explicit configuration (``nexus up --config``); see
            :func:`locate_runtime_home`.
    """
    location = locate_runtime_home(config_path)
    if settings is None:
        settings = load_settings(location.config_path)
    return build_runtime_home(location, settings)

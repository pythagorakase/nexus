"""The runtime home (issue #820): one locator rule, one anchoring rule, one plan.

Every test uses real temporary directories and real copies of the checkout's
nexus.toml; nothing is faked. The locator variables are cleared per test so
the rule is exercised from a known starting point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import pytest
import tomlkit

from nexus import cli
from nexus.agents.lore.lore import LORE
from nexus.api import asset_endpoints, local_inference, static_ui
from nexus.api.route_capabilities import ROUTE_CAPABILITIES
from nexus.api.settings_endpoints import _read_raw_settings
from nexus.config import load_settings
from nexus.config.preferences import preferences_path
from nexus.runtime import RuntimeError_, Supervisor
from nexus.runtime.contract import GATEWAY_PORT_ENV, HOME_ENV, RUNTIME_CONFIG_ENV
from nexus.runtime.home import (
    UPLOAD_SUBDIRS,
    UPLOADS_DIR,
    RuntimeHomeError,
    locate_runtime_home,
    repo_root,
    resolve_runtime_home,
)
from nexus.telemetry import usage

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG = REPO_ROOT / "nexus.toml"
DISAGREEMENT = "Two active configurations are not allowed"


@pytest.fixture(autouse=True)
def _clear_locators(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test in developer mode with no instance-port override."""
    for name in (HOME_ENV, RUNTIME_CONFIG_ENV, GATEWAY_PORT_ENV):
        monkeypatch.delenv(name, raising=False)


def _write_config(
    path: Path,
    *,
    state_dir: Optional[str] = None,
    usage_dir: Optional[str] = None,
    edit: Optional[Callable[[Any], None]] = None,
) -> Path:
    """Write a real copy of the checkout's nexus.toml with runtime edits."""
    document: Any = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    if state_dir is not None:
        document["runtime"]["state_dir"] = state_dir
    if usage_dir is not None:
        document["usage"]["usage_dir"] = usage_dir
    if edit is not None:
        edit(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The locator rule
# ---------------------------------------------------------------------------


def test_developer_mode_is_the_checkout_whatever_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both locators unset: the checkout is the home, even from elsewhere."""
    monkeypatch.chdir(tmp_path)

    home = resolve_runtime_home()
    settings = load_settings()

    assert home.locator == "checkout"
    assert home.root == REPO_ROOT == repo_root()
    assert home.config_path == REPO_CONFIG.resolve()
    assert settings.runtime is not None
    assert str(home.state_dir) == str(REPO_ROOT / settings.runtime.state_dir)
    assert home.logs_dir == home.state_dir
    assert str(home.usage_dir) == str(REPO_ROOT / settings.usage.usage_dir)
    assert home.uploads_dir == REPO_ROOT / "ui" / "client" / "public"
    assert home.models_dir == REPO_ROOT / "models"
    assert home.cache_dir == REPO_ROOT / ".nexus" / "cache"
    assert home.backups_dir == REPO_ROOT / ".nexus" / "backups"


def test_working_directory_config_never_becomes_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A decoy nexus.toml in the cwd is ignored by every config reader."""
    _write_config(tmp_path / "nexus.toml", state_dir="decoy-state")
    monkeypatch.chdir(tmp_path)
    expected = load_settings(REPO_CONFIG)
    assert expected.runtime is not None

    loaded = load_settings()
    cli_settings = cli._load_cli_settings()

    assert loaded.runtime is not None
    assert loaded.runtime.state_dir == expected.runtime.state_dir
    assert _read_raw_settings()["runtime"]["state_dir"] == expected.runtime.state_dir
    assert cli_settings is not None and cli_settings.runtime is not None
    assert cli_settings.runtime.state_dir == expected.runtime.state_dir


def test_nexus_home_derives_the_config_and_anchors_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEXUS_HOME alone: $NEXUS_HOME/nexus.toml, relative dirs under the home."""
    home_root = tmp_path / "home"
    config = _write_config(
        home_root / "nexus.toml", state_dir="state", usage_dir="ledger/usage"
    )
    monkeypatch.setenv(HOME_ENV, str(home_root))
    monkeypatch.chdir(tmp_path)

    home = resolve_runtime_home()

    root = home_root.resolve()
    assert home.locator == "NEXUS_HOME"
    assert home.root == root
    assert home.config_path == config.resolve()
    assert home.state_dir == root / "state"
    assert home.logs_dir == root / "state"
    assert home.usage_dir == root / "ledger" / "usage"
    assert home.uploads_dir == root / UPLOADS_DIR
    assert home.models_dir == root / "models"
    assert home.cache_dir == root / ".nexus" / "cache"
    assert home.backups_dir == root / ".nexus" / "backups"
    loaded = load_settings()
    assert loaded.runtime is not None and loaded.runtime.state_dir == "state"
    # Resolution reads; it never lays the directories down.
    assert sorted(path.name for path in home_root.iterdir()) == ["nexus.toml"]


def test_absolute_and_home_relative_directories_under_nexus_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absolute paths stay as configured and ~ expands before anchoring."""
    home_root = tmp_path / "home"
    fake_user_home = tmp_path / "user"
    monkeypatch.setenv("HOME", str(fake_user_home))
    _write_config(
        home_root / "nexus.toml",
        state_dir=str(tmp_path / "elsewhere" / "state"),
        usage_dir="~/usage",
    )
    monkeypatch.setenv(HOME_ENV, str(home_root))

    home = resolve_runtime_home()

    assert home.state_dir == tmp_path / "elsewhere" / "state"
    assert home.usage_dir == fake_user_home / "usage"


def test_runtime_config_alone_selects_the_file_and_keeps_the_checkout_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEXUS_RUNTIME_CONFIG alone: that config, relative dirs in the checkout."""
    config = _write_config(tmp_path / "lane" / "nexus.toml", state_dir="lane-state")
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    home = resolve_runtime_home()

    assert home.locator == "NEXUS_RUNTIME_CONFIG"
    assert home.root == REPO_ROOT
    assert home.config_path == config.resolve()
    assert str(home.state_dir) == str(REPO_ROOT / "lane-state")


@pytest.mark.parametrize("through_alias", (False, True), ids=("same", "symlink"))
def test_agreeing_locators_name_one_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, through_alias: bool
) -> None:
    """Both set and naming the same file (directly or via a symlink) is fine."""
    home_root = tmp_path / "home"
    config = _write_config(home_root / "nexus.toml", state_dir="state")
    named_home = home_root
    if through_alias:
        named_home = tmp_path / "alias"
        named_home.symlink_to(home_root, target_is_directory=True)
    monkeypatch.setenv(HOME_ENV, str(home_root))
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(named_home / "nexus.toml"))

    location = locate_runtime_home()

    assert location.locator == "NEXUS_HOME"
    assert location.config_path == config.resolve()
    assert Supervisor.from_config().home.state_dir == home_root.resolve() / "state"


def test_disagreeing_locators_are_refused_by_every_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEXUS_HOME and NEXUS_RUNTIME_CONFIG naming two files is a loud error."""
    home_root = tmp_path / "home"
    _write_config(home_root / "nexus.toml")
    other = _write_config(tmp_path / "other" / "nexus.toml")
    monkeypatch.setenv(HOME_ENV, str(home_root))
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(other))

    with pytest.raises(RuntimeHomeError, match=DISAGREEMENT) as raised:
        locate_runtime_home()
    assert isinstance(raised.value, RuntimeError)
    assert str(other.resolve()) in str(raised.value)
    for reader in (load_settings, _read_raw_settings, cli._load_cli_settings):
        with pytest.raises(RuntimeHomeError, match=DISAGREEMENT):
            reader()
    with pytest.raises(RuntimeError_, match=DISAGREEMENT):
        Supervisor.from_config()


def test_explicit_config_must_agree_with_nexus_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``nexus up --config`` is held to the same agreement as the env seam."""
    home_root = tmp_path / "home"
    config = _write_config(home_root / "nexus.toml", state_dir="state")
    other = _write_config(tmp_path / "other" / "nexus.toml")
    monkeypatch.setenv(HOME_ENV, str(home_root))

    with pytest.raises(RuntimeError_, match="explicit --config"):
        Supervisor.from_config(other)
    supervisor = Supervisor.from_config(config)
    assert supervisor.config_path == config.resolve()
    assert supervisor.state_dir == home_root.resolve() / "state"


def test_explicit_config_still_outranks_runtime_config_without_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without NEXUS_HOME an explicit path wins over NEXUS_RUNTIME_CONFIG."""
    explicit = _write_config(tmp_path / "explicit.toml", state_dir="x")
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(tmp_path / "missing.toml"))

    location = locate_runtime_home(explicit)

    assert location.locator == "explicit"
    assert location.config_path == explicit.resolve()
    assert location.root == REPO_ROOT


def test_relative_nexus_home_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative home would move with each process's working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(HOME_ENV, "relative/home")

    with pytest.raises(RuntimeHomeError, match="must be an absolute path"):
        locate_runtime_home()


@pytest.mark.parametrize("value", ("", "   "))
def test_empty_nexus_home_counts_as_unset(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """An empty NEXUS_HOME is developer mode, like an empty runtime config."""
    monkeypatch.setenv(HOME_ENV, value)

    assert locate_runtime_home().locator == "checkout"


def test_nexus_home_without_its_config_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A home with no nexus.toml never falls back to the checkout's."""
    monkeypatch.setenv(HOME_ENV, str(tmp_path / "empty-home"))

    with pytest.raises(FileNotFoundError, match="empty-home"):
        load_settings()
    with pytest.raises(FileNotFoundError, match="empty-home"):
        cli._load_cli_settings()


# ---------------------------------------------------------------------------
# The former resolvers now answer from the runtime home
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ("checkout", "home"))
def test_former_resolvers_agree_with_the_runtime_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """Supervisor, preferences, local inference and usage share one answer."""
    if mode == "home":
        home_root = tmp_path / "home"
        config = _write_config(
            home_root / "nexus.toml", state_dir="state", usage_dir="usage"
        )
        monkeypatch.setenv(HOME_ENV, str(home_root))
    else:
        config = REPO_CONFIG
    settings = load_settings()
    home = resolve_runtime_home(settings)

    supervisor = Supervisor(settings, config)

    state = str(home.state_dir)
    assert str(supervisor.state_dir) == state
    assert str(supervisor.log_path("gateway")) == str(home.logs_dir / "gateway.log")
    assert str(supervisor.log_config_path()) == str(home.state_dir / "logging.json")
    assert str(preferences_path(settings)) == str(home.state_dir / "preferences.toml")
    assert str(local_inference._state_dir(settings)) == state
    assert str(local_inference._state_path(settings)) == str(
        home.state_dir / local_inference.STATE_FILENAME
    )
    assert str(local_inference._logs_dir(settings)) == str(home.logs_dir)
    assert str(usage._load_recorder_config().usage_dir) == str(home.usage_dir)
    assert settings.runtime is not None
    if mode == "checkout":
        # The pre-#820 formula every resolver duplicated, byte for byte.
        assert state == str(REPO_ROOT / settings.runtime.state_dir)
        assert str(home.usage_dir) == str(REPO_ROOT / settings.usage.usage_dir)
    else:
        assert home.state_dir == home_root.resolve() / "state"
        assert home.usage_dir == home_root.resolve() / "usage"


def test_gateway_port_override_isolates_state_and_logs_inside_the_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEXUS_GATEWAY_PORT's per-port instance directory nests in the home."""
    home_root = tmp_path / "home"
    config = _write_config(home_root / "nexus.toml", state_dir="state")
    monkeypatch.setenv(HOME_ENV, str(home_root))
    monkeypatch.setenv(GATEWAY_PORT_ENV, "8931")

    supervisor = Supervisor(load_settings(), config)

    instance = home_root.resolve() / "state" / "gateway-8931"
    assert supervisor.state_dir == instance
    assert supervisor.log_path("gateway") == instance / "gateway.log"


def test_every_config_reader_uses_the_home_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Loader, settings endpoint, CLI, supervisor and LORE read one file."""
    home_root = tmp_path / "home"
    config = _write_config(home_root / "nexus.toml", state_dir="home-state")
    _write_config(tmp_path / "nexus.toml", state_dir="decoy-state")
    monkeypatch.setenv(HOME_ENV, str(home_root))
    monkeypatch.chdir(tmp_path)

    loaded = load_settings()
    cli_settings = cli._load_cli_settings()
    lore = LORE.__new__(LORE)
    lore_settings = lore._load_settings(None)

    assert loaded.runtime is not None and loaded.runtime.state_dir == "home-state"
    assert _read_raw_settings()["runtime"]["state_dir"] == "home-state"
    assert cli_settings is not None and cli_settings.runtime is not None
    assert cli_settings.runtime.state_dir == "home-state"
    assert Supervisor.from_config().config_path == config.resolve()
    assert lore.settings_path == config.resolve()
    assert lore_settings["runtime"]["state_dir"] == "home-state"


def test_upload_layout_matches_the_upload_endpoints_and_mounts() -> None:
    """The layout's upload root is where uploads are written and served today."""
    mounts = {
        path for method, path in ROUTE_CAPABILITIES if method == "MOUNT" and path != "/"
    }

    assert asset_endpoints.UPLOAD_ROOT == REPO_ROOT / UPLOADS_DIR
    assert static_ui.UI_PUBLIC_DIR == REPO_ROOT / UPLOADS_DIR
    assert resolve_runtime_home().uploads_dir == asset_endpoints.UPLOAD_ROOT
    assert mounts == {f"/{name}" for name in UPLOAD_SUBDIRS}

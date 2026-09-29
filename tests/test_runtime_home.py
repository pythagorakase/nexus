"""The runtime home (issue #820): one locator rule, one anchoring rule, one plan.

Every test uses real temporary directories and real copies of the checkout's
nexus.toml; nothing is faked. The locator variables are cleared per test so
the rule is exercised from a known starting point.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict, Optional, Tuple, cast

import pytest
import tomlkit

from nexus import cli
from nexus.agents.lore.lore import LORE
from nexus.agents.memnon.utils.artifact_manifest import run_models_command
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
from nexus.runtime.home_plan import HomePlan, HomePlanError, plan_home_move
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


def _tree_snapshot(root: Path) -> Dict[str, Tuple[bool, int, int]]:
    """Record every path under ``root`` with its type, size and mtime."""
    snapshot: Dict[str, Tuple[bool, int, int]] = {}
    for directory, subdirectories, files in os.walk(root):
        for name in subdirectories + files:
            path = Path(directory) / name
            info = path.lstat()
            snapshot[str(path.relative_to(root))] = (
                path.is_dir(),
                info.st_size,
                info.st_mtime_ns,
            )
    return snapshot


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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    models = run_models_command("verify", None)
    assert models["success"] is False and DISAGREEMENT in models["error"]

    monkeypatch.setattr(
        sys, "argv", ["nexus", "--json", "home", "plan", "--to", str(tmp_path / "t")]
    )
    assert cli.main() == 1
    assert DISAGREEMENT in json.loads(capsys.readouterr().err)["error"]


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
    assert lore_settings.runtime is not None
    assert lore_settings.runtime.state_dir == "home-state"


def test_upload_layout_matches_the_upload_endpoints_and_mounts() -> None:
    """The layout's upload root is where uploads are written and served today."""
    mounts = {
        path for method, path in ROUTE_CAPABILITIES if method == "MOUNT" and path != "/"
    }

    assert asset_endpoints.UPLOAD_ROOT == REPO_ROOT / UPLOADS_DIR
    assert static_ui.UI_PUBLIC_DIR == REPO_ROOT / UPLOADS_DIR
    assert resolve_runtime_home().uploads_dir == asset_endpoints.UPLOAD_ROOT
    assert mounts == {f"/{name}" for name in UPLOAD_SUBDIRS}


# ---------------------------------------------------------------------------
# nexus home plan
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _point_models(models_source: Path) -> Callable[[Any], None]:
    """Point every model key in a config copy at a directory under a tmp root."""

    def edit(document: Any) -> None:
        for name, model in document["memnon"]["models"].items():
            model["local_path"] = str(models_source / f"{name}-dir")
        reranking = document["memnon"]["retrieval"]["cross_encoder_reranking"]
        reranking["model_path"] = str(models_source / "reranker")
        for name, candidate in reranking["candidates"].items():
            candidate["local_path"] = str(models_source / f"{name}-dir")
        reranking["candidates"]["deberta-v3-trecdl22"]["local_path"] = str(
            models_source / "reranker"
        )

    return edit


def _fake_checkout(tmp_path: Path) -> Tuple[Path, Path, Path]:
    """Lay out a real checkout-shaped tree with runtime data and models.

    Model keys hold absolute paths into the checkout's models/ directory, as
    the shipped nexus.toml does.
    """
    checkout = tmp_path / "checkout"
    models_source = checkout / "models"
    config = _write_config(
        checkout / "nexus.toml",
        state_dir=".nexus/runtime",
        usage_dir=".nexus/runtime/usage",
        edit=_point_models(models_source),
    )
    state = checkout / ".nexus" / "runtime"
    _write(state / "gateway.pid.json", b'{"pid": 1}\n')
    _write(state / "gateway.log", b"line one\nline two\n")
    _write(state / "gateway.log.1", b"older\n")
    _write(state / "preferences.toml", b'theme = "vector"\n')
    _write(state / "gateway-8931" / "gateway.log", b"isolated\n")
    _write(state / "usage" / "usage-2026-09-26.jsonl", b'{"tokens": 3}\n')
    (state / "current.log").symlink_to("gateway.log")
    _write(checkout / ".nexus" / "cache" / "derived.bin", bytes(range(256)))
    public = checkout / UPLOADS_DIR
    _write(public / "character_portraits" / "7" / "a.png", b"\x89PNG portrait")
    _write(public / "place_images" / "3" / "b.jpg", b"\xff\xd8 place")
    _write(public / "favicon.ico", b"checked-in asset, not an upload")
    _write(models_source / "bge-large-dir" / "config.json", b"{}")
    _write(models_source / "bge-large-dir" / "weights.bin", b"\x00" * 4096)
    _write(models_source / "reranker" / "model.safetensors", b"\x01" * 2048)
    return checkout, config, models_source


def test_home_plan_inventories_checksums_and_maps_every_runtime_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each current file gets its checksum, size, category and proposed path."""
    checkout, config, models_source = _fake_checkout(tmp_path)
    target = tmp_path / "target-home"
    conflict = _write(target / ".nexus" / "runtime" / "preferences.toml", b"theirs")
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    plan = plan_home_move(target, checkout=checkout)

    entries = {entry.current: entry for entry in plan.entries}
    state = checkout / ".nexus" / "runtime"
    public = checkout / UPLOADS_DIR
    expected = {
        config: ("config", "move", target / "nexus.toml"),
        state
        / "usage"
        / "usage-2026-09-26.jsonl": (
            "usage",
            "move",
            target / ".nexus/runtime/usage/usage-2026-09-26.jsonl",
        ),
        state
        / "gateway.pid.json": (
            "state",
            "move",
            target / ".nexus/runtime/gateway.pid.json",
        ),
        state / "gateway.log": ("state", "move", target / ".nexus/runtime/gateway.log"),
        state
        / "gateway.log.1": (
            "state",
            "move",
            target / ".nexus/runtime/gateway.log.1",
        ),
        state
        / "gateway-8931"
        / "gateway.log": (
            "state",
            "move",
            target / ".nexus/runtime/gateway-8931/gateway.log",
        ),
        state / "preferences.toml": ("state", "conflict", conflict),
        state / "current.log": ("state", "move", target / ".nexus/runtime/current.log"),
        checkout
        / ".nexus/cache/derived.bin": (
            "cache",
            "move",
            target / ".nexus/cache/derived.bin",
        ),
        public
        / "character_portraits/7/a.png": (
            "uploads",
            "move",
            target / UPLOADS_DIR / "character_portraits/7/a.png",
        ),
        public
        / "place_images/3/b.jpg": (
            "uploads",
            "move",
            target / UPLOADS_DIR / "place_images/3/b.jpg",
        ),
        models_source
        / "bge-large-dir"
        / "config.json": (
            "models",
            "move",
            target / "models/bge-large-dir/config.json",
        ),
        models_source
        / "bge-large-dir"
        / "weights.bin": (
            "models",
            "move",
            target / "models/bge-large-dir/weights.bin",
        ),
        models_source
        / "reranker"
        / "model.safetensors": (
            "models",
            "move",
            target / "models/reranker/model.safetensors",
        ),
    }
    for current, (category, status, proposed) in expected.items():
        entry = entries[current]
        assert (entry.category, entry.status, entry.proposed) == (
            category,
            status,
            proposed,
        ), current
        if entry.kind == "file":
            assert entry.sha256 == _sha256(current)
            assert entry.size == current.stat().st_size
    link = entries[state / "current.log"]
    assert (link.kind, link.link_target, link.sha256) == (
        "symlink",
        "gateway.log",
        None,
    )
    assert public / "favicon.ico" not in entries

    missing = {entry.current for entry in plan.entries if entry.status == "missing"}
    assert models_source / "e5-large-dir" in missing
    assert models_source / "bge-large-dir" not in missing
    assert all(
        entry.kind == "missing" and entry.sha256 is None
        for entry in plan.entries
        if entry.status == "missing"
    )
    rewrites = {rewrite.key: rewrite for rewrite in plan.rewrites}
    reranker_target = str(target / "models" / "reranker")
    assert rewrites["memnon.retrieval.cross_encoder_reranking.model_path"].proposed == (
        reranker_target
    )
    assert (
        rewrites[
            "memnon.retrieval.cross_encoder_reranking.candidates."
            "deberta-v3-trecdl22.local_path"
        ].proposed
        == reranker_target
    )
    assert rewrites["memnon.models.bge-large.local_path"].current == str(
        models_source / "bge-large-dir"
    )
    assert "memnon.models.e5-large.local_path" not in rewrites
    assert plan.total_bytes() == sum(entry.size or 0 for entry in plan.entries)
    assert plan.source.root == checkout.resolve()
    assert plan.target.root == target.resolve()


def test_home_plan_orders_entries_by_category_then_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report order is a pure function of the inventory."""
    checkout, config, _ = _fake_checkout(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    plan = plan_home_move(tmp_path / "target", checkout=checkout)

    order = (
        "config",
        "usage",
        "state",
        "logs",
        "cache",
        "backups",
        "uploads",
        "models",
    )
    keys = [(order.index(entry.category), str(entry.current)) for entry in plan.entries]
    assert keys == sorted(keys)


def test_home_plan_cli_is_read_only_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two runs print identical JSON and leave every file and mtime untouched."""
    state = tmp_path / "state"
    _write(state / "gateway.log", b"captured\n")
    _write(state / "preferences.toml", b'theme = "vector"\n')
    _write(tmp_path / "ledger" / "usage-2026-09-26.jsonl", b'{"tokens": 1}\n')
    models_source = tmp_path / "model-store"
    _write(models_source / "bge-large-dir" / "weights.bin", b"\x02" * 1024)
    config = _write_config(
        tmp_path / "config" / "nexus.toml",
        state_dir=str(state),
        usage_dir=str(tmp_path / "ledger"),
        edit=_point_models(models_source),
    )
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))
    target = tmp_path / "home-target"
    # The checkout directories the plan walks: it must never create one.
    checkout_layout = [
        REPO_ROOT / ".nexus" / "cache",
        REPO_ROOT / ".nexus" / "backups",
        *(REPO_ROOT / UPLOADS_DIR / name for name in UPLOAD_SUBDIRS),
    ]
    layout_before = [path.exists() for path in checkout_layout]
    before = _tree_snapshot(tmp_path)

    outputs = []
    for _ in range(2):
        monkeypatch.setattr(
            sys, "argv", ["nexus", "home", "plan", "--to", str(target), "--json"]
        )
        assert cli.main() == 0
        outputs.append(capsys.readouterr().out)

    assert outputs[0] == outputs[1]
    assert _tree_snapshot(tmp_path) == before
    assert not target.exists()
    assert [path.exists() for path in checkout_layout] == layout_before
    plan = cast(Dict[str, Any], json.loads(outputs[0])["home_plan"])
    by_current = {entry["current"]: entry for entry in plan["entries"]}
    # Absolute configured directories outside the checkout stay put: the
    # model store as well as the state directory.
    weights = models_source / "bge-large-dir" / "weights.bin"
    assert by_current[str(weights)]["sha256"] == _sha256(weights)
    assert (
        by_current[str(weights)]["status"],
        by_current[str(weights)]["proposed"],
    ) == ("in-place", str(weights))
    assert plan["rewrites"] == []
    captured = by_current[str(state / "gateway.log")]
    assert (captured["status"], captured["proposed"]) == (
        "in-place",
        str(state / "gateway.log"),
    )
    assert captured["sha256"] == _sha256(state / "gateway.log")
    assert by_current[str(config.resolve())]["proposed"] == str(target / "nexus.toml")
    assert plan["target"]["root"] == str(target)
    assert plan["source"]["root"] == str(REPO_ROOT)
    assert plan["config_locator"] == "NEXUS_RUNTIME_CONFIG"

    monkeypatch.setattr(sys, "argv", ["nexus", "home", "plan", "--to", str(target)])
    assert cli.main() == 0
    human = capsys.readouterr().out.splitlines()
    assert human[0].startswith(f"source  {REPO_ROOT} ")
    assert human[1] == f"target  {target}"
    assert human[-1].endswith("Dry run: nothing was moved.")
    assert _tree_snapshot(tmp_path) == before


def test_home_plan_defaults_to_nexus_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With NEXUS_HOME set the plan targets it; its own config stays in place."""
    checkout, _, models_source = _fake_checkout(tmp_path)
    home_root = tmp_path / "home"
    config = _write_config(
        home_root / "nexus.toml",
        edit=_point_models(models_source),
    )
    monkeypatch.setenv(HOME_ENV, str(home_root))

    plan = plan_home_move(checkout=checkout)

    assert isinstance(plan, HomePlan)
    assert plan.target.root == home_root.resolve()
    assert plan.config_locator == "NEXUS_HOME"
    config_entry = plan.entries[0]
    assert (config_entry.category, config_entry.status) == ("config", "in-place")
    assert config_entry.current == config.resolve()


def test_home_plan_refuses_ill_posed_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No target, the checkout itself, or a home inside or around it."""
    checkout, config, _ = _fake_checkout(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    with pytest.raises(HomePlanError, match="No target home"):
        plan_home_move(checkout=checkout)
    with pytest.raises(HomePlanError, match="inside it"):
        plan_home_move(checkout, checkout=checkout)
    with pytest.raises(HomePlanError, match="inside it"):
        plan_home_move(checkout / "home", checkout=checkout)
    with pytest.raises(HomePlanError, match="contains the checkout"):
        plan_home_move(tmp_path, checkout=checkout)
    occupied = _write(tmp_path / "a-file", b"not a directory")
    with pytest.raises(HomePlanError, match="not a directory"):
        plan_home_move(occupied, checkout=checkout)


def test_home_plan_refuses_two_models_landing_on_one_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two model directories with one name would overwrite each other."""
    checkout, _, models_source = _fake_checkout(tmp_path)

    def edit(document: Any) -> None:
        _point_models(models_source)(document)
        document["memnon"]["models"]["e5-large"]["local_path"] = str(
            checkout / "second-store" / "bge-large-dir"
        )

    config = _write_config(tmp_path / "collide" / "nexus.toml", edit=edit)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    with pytest.raises(HomePlanError, match="would both move"):
        plan_home_move(tmp_path / "target", checkout=checkout)


def test_home_plan_leaves_models_outside_the_checkout_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model on an external store is already separate and is not moved.

    It keeps its key, and sharing a directory name with a checkout model that
    moves is no collision.
    """
    checkout, _, models_source = _fake_checkout(tmp_path)
    external = tmp_path / "external-drive" / "bge-large-dir"
    weights = _write(external / "weights.bin", b"\x03" * 512)

    def edit(document: Any) -> None:
        _point_models(models_source)(document)
        document["memnon"]["models"]["e5-large"]["local_path"] = str(external)

    config = _write_config(tmp_path / "external" / "nexus.toml", edit=edit)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))
    target = tmp_path / "target"

    plan = plan_home_move(target, checkout=checkout)

    entries = {entry.current: entry for entry in plan.entries}
    outside = entries[weights]
    assert (outside.category, outside.status, outside.proposed) == (
        "models",
        "in-place",
        weights,
    )
    assert outside.sha256 == _sha256(weights)
    inside = entries[models_source / "bge-large-dir" / "weights.bin"]
    assert (inside.status, inside.proposed) == (
        "move",
        target / "models" / "bge-large-dir" / "weights.bin",
    )
    rewrites = {rewrite.key for rewrite in plan.rewrites}
    assert "memnon.models.e5-large.local_path" not in rewrites
    assert "memnon.models.bge-large.local_path" in rewrites


@pytest.mark.parametrize(
    "blocker_kind", ("file", "symlink-to-directory", "symlink-to-file")
)
def test_home_plan_reports_a_blocked_destination_ancestor_as_a_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocker_kind: str
) -> None:
    """A file or symlink on the way to a destination blocks it, unfollowed.

    Every entry beneath the blocker is a conflict naming it, while
    destinations elsewhere in the target stay free.
    """
    checkout, config, _ = _fake_checkout(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))
    target = tmp_path / "target-home"
    blocker = target / ".nexus"
    if blocker_kind == "file":
        _write(blocker, b"not a directory")
    else:
        blocker.parent.mkdir(parents=True)
        if blocker_kind == "symlink-to-directory":
            elsewhere = tmp_path / "elsewhere"
            (elsewhere / "runtime").mkdir(parents=True)
            blocker.symlink_to(elsewhere, target_is_directory=True)
        else:
            blocker.symlink_to(_write(tmp_path / "loose-file", b"a file"))
    occupied = _write(target / UPLOADS_DIR / "place_images" / "3" / "b.jpg", b"x")
    before = _tree_snapshot(tmp_path)

    plan = plan_home_move(target, checkout=checkout)

    entries = {entry.current: entry for entry in plan.entries}
    beneath = [entry for entry in plan.entries if blocker in entry.proposed.parents]
    assert {entry.category for entry in beneath} == {"usage", "state", "cache"}
    assert {entry.status for entry in beneath} == {"conflict"}
    assert {entry.conflict_with for entry in beneath} == {blocker}
    direct = entries[checkout / UPLOADS_DIR / "place_images" / "3" / "b.jpg"]
    assert (direct.status, direct.conflict_with) == ("conflict", occupied)
    free = entries[config]
    assert (free.status, free.conflict_with) == ("move", None)
    portrait = entries[checkout / UPLOADS_DIR / "character_portraits" / "7" / "a.png"]
    assert portrait.status == "move"
    gateway_log = entries[checkout / ".nexus" / "runtime" / "gateway.log"]
    assert gateway_log.as_dict()["conflict_with"] == str(blocker)
    rendered = plan.render()
    assert any(
        line.startswith("conflict") and line.endswith(f"(blocked by {blocker})")
        for line in rendered
    )
    assert not any(f"(blocked by {occupied})" in line for line in rendered)
    assert plan_home_move(target, checkout=checkout).as_dict() == plan.as_dict()
    assert _tree_snapshot(tmp_path) == before


@pytest.mark.parametrize("through", ("file", "symlink-to-file"))
def test_home_plan_refuses_a_target_under_a_non_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, through: str
) -> None:
    """A home beneath a file can never be created, so the plan is refused."""
    checkout, config, _ = _fake_checkout(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))
    loose = _write(tmp_path / "loose-file", b"a file")
    parent = loose
    if through == "symlink-to-file":
        parent = tmp_path / "link-to-file"
        parent.symlink_to(loose)

    with pytest.raises(HomePlanError, match="is blocked") as raised:
        plan_home_move(parent / "home", checkout=checkout)
    assert f"{loose} exists and is not a directory" in str(raised.value)


def _set_models(models_source: Path, paths: Dict[str, Path]) -> Callable[[Any], None]:
    """Point the model keys at the fake store, then override named models."""

    def edit(document: Any) -> None:
        _point_models(models_source)(document)
        for name, path in paths.items():
            document["memnon"]["models"][name]["local_path"] = str(path)

    return edit


@pytest.mark.parametrize(
    "layout", ("nested", "symlinked-parent", "symlinked-root", "external-alias")
)
def test_home_plan_refuses_overlapping_model_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    """Nested or aliased model paths would give one set of files two keys.

    Before the refusal the parent claimed the child's files and the child's
    key was still rewritten to a destination that received nothing.
    """
    checkout, _, models_source = _fake_checkout(tmp_path)
    first = models_source / "parent"
    _write(first / "sub" / "weights.bin", b"\x04" * 64)
    _write(first / "config.json", b"{}")
    if layout == "nested":
        second = first / "sub"
    elif layout == "symlinked-parent":
        (models_source / "alias").symlink_to(first, target_is_directory=True)
        second = models_source / "alias" / "sub"
    elif layout == "symlinked-root":
        second = models_source / "alias"
        second.symlink_to(first, target_is_directory=True)
    else:
        store = tmp_path / "external" / "store"
        first = store / "shared"
        _write(first / "weights.bin", b"\x05" * 64)
        (tmp_path / "external" / "link").symlink_to(store, target_is_directory=True)
        second = tmp_path / "external" / "link" / "shared"
    config = _write_config(
        tmp_path / "overlap" / "nexus.toml",
        edit=_set_models(models_source, {"bge-large": first, "e5-large": second}),
    )
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    with pytest.raises(HomePlanError, match="overlap") as raised:
        plan_home_move(tmp_path / "target", checkout=checkout)
    message = str(raised.value)
    for named in (
        "memnon.models.bge-large.local_path",
        "memnon.models.e5-large.local_path",
        str(first),
        str(second),
    ):
        assert named in message


@pytest.mark.parametrize("model_path", ("checkout", "ancestor"))
def test_home_plan_refuses_a_model_path_that_is_or_contains_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_path: str
) -> None:
    """The checkout holds code and runtime data; it is never a model."""
    checkout, _, models_source = _fake_checkout(tmp_path)
    named = checkout if model_path == "checkout" else tmp_path
    config = _write_config(
        tmp_path / "wide" / "nexus.toml",
        edit=_set_models(models_source, {"e5-large": named}),
    )
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    with pytest.raises(HomePlanError, match="is or contains the checkout") as raised:
        plan_home_move(tmp_path / "target", checkout=checkout)
    assert f"memnon.models.e5-large.local_path ({named})" in str(raised.value)


@pytest.mark.parametrize("layout", ("inside-state", "holds-state", "holds-config"))
def test_home_plan_refuses_a_model_path_overlapping_runtime_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    """A path is a model or runtime data, never both.

    A model inside the state directory used to have its files claimed (and
    moved) as state while its key was rewritten to an empty models path.
    """
    checkout, _, models_source = _fake_checkout(tmp_path)
    state = checkout / ".nexus" / "runtime"
    config_dir = tmp_path / "config-dir"
    if layout == "inside-state":
        named = state / "models" / "tiny"
        _write(named / "weights.bin", b"\x06" * 32)
        owner = f"the state directory {state}"
    elif layout == "holds-state":
        named = checkout / ".nexus"
        owner = f"the usage directory {state / 'usage'}"
    else:
        named = config_dir
        owner = f"the active configuration {config_dir / 'nexus.toml'}"
    config = _write_config(
        config_dir / "nexus.toml",
        state_dir=".nexus/runtime",
        usage_dir=".nexus/runtime/usage",
        edit=_set_models(models_source, {"e5-large": named}),
    )
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    with pytest.raises(HomePlanError, match="overlaps the") as raised:
        plan_home_move(tmp_path / "target", checkout=checkout)
    message = str(raised.value)
    assert f"memnon.models.e5-large.local_path ({named}) overlaps {owner}" in message


def test_home_plan_refuses_a_model_moving_onto_one_that_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A moving model may not land in a model directory that stays in place."""
    checkout, _, models_source = _fake_checkout(tmp_path)
    target = tmp_path / "target"
    staying = target / "models" / "bge-large-dir"
    _write(staying / "weights.bin", b"\x07" * 16)
    config = _write_config(
        tmp_path / "landing" / "nexus.toml",
        edit=_set_models(models_source, {"e5-large": staying}),
    )
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))

    with pytest.raises(HomePlanError, match="stays in place") as raised:
        plan_home_move(target, checkout=checkout)
    message = str(raised.value)
    moving = models_source / "bge-large-dir"
    assert f"memnon.models.bge-large.local_path ({moving})" in message
    assert f"would move to {staying}" in message
    assert f"memnon.models.e5-large.local_path ({staying})" in message


@pytest.mark.parametrize("locator", ("NEXUS_RUNTIME_CONFIG", "NEXUS_HOME"))
def test_home_plan_reports_a_symlinked_active_config_as_the_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, locator: str
) -> None:
    """The config entry is the link the locator selected, never its target.

    Locator agreement and loading still use the resolved file.
    """
    checkout, checkout_config, models_source = _fake_checkout(tmp_path)
    real = _write_config(
        tmp_path / "configs" / "real.toml", edit=_point_models(models_source)
    )
    if locator == "NEXUS_RUNTIME_CONFIG":
        checkout_config.unlink()
        link = checkout_config
        link.symlink_to(real)
        monkeypatch.chdir(checkout)
        monkeypatch.setenv(RUNTIME_CONFIG_ENV, "nexus.toml")
        target = tmp_path / "target"
        expected = ("move", target / "nexus.toml")
    else:
        target = tmp_path / "home"
        target.mkdir()
        link = target / "nexus.toml"
        link.symlink_to(real)
        monkeypatch.setenv(HOME_ENV, str(target))
        expected = ("in-place", link)

    plan = plan_home_move(target, checkout=checkout)

    config_entry = plan.entries[0]
    assert config_entry.category == "config"
    assert config_entry.current == link
    assert (config_entry.kind, config_entry.link_target) == ("symlink", str(real))
    assert (config_entry.status, config_entry.proposed) == expected
    assert (config_entry.size, config_entry.sha256) == (None, None)
    assert real not in {entry.current for entry in plan.entries}
    assert plan.source.config_path == real.resolve()
    location = locate_runtime_home()
    assert location.config_path == real.resolve()
    assert location.selected_config_path == link


def test_selected_config_path_is_the_config_in_developer_mode() -> None:
    """Without symlinks the selected path is the resolved checkout config."""
    location = locate_runtime_home()

    assert location.selected_config_path == location.config_path == REPO_CONFIG

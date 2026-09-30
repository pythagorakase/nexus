"""The scheduler helpers route through the shared slot contract (issue #885).

``tests.scheduler_helpers.route_slot`` is the slot-4 case of
``tests.pg_fixtures.route_slots_to_disposable``: it reaches the modules that
bind ``slot_dbname`` at import, refuses owner names and every other slot,
and restores all of it at teardown. ``run_cli`` hands its child the active
route, and ``gateway_lane`` refuses to start or to close with ``nexus down``
unless ``NEXUS_RUNTIME_CONFIG`` names a private config. Only the close-time
refusal opens a database: it serves a lane on a routed disposable clone.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
import tomlkit

from nexus.api import (
    narrative,
    save_slots,
    secrets_endpoints,
    slot_endpoints,
    slot_utils,
    wizard_agent,
    wizard_chat,
)
from nexus.runtime.home import anchor_path
from scripts import new_story_setup
from tests import scheduler_helpers
from tests.pg_fixtures import (
    ROUTED_SLOT_DATABASE_ENV,
    ROUTED_SLOT_ENV,
    active_slot_routes,
    disposable_slot_database,
    route_slots_to_disposable,
)
from tests.scheduler_helpers import (
    RUNTIME_CONFIG_ENV,
    gateway_lane,
    private_runtime_config,
    require_private_runtime_config,
    route_slot,
    routed_child_environment,
    run_cli,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# Modules that bind ``slot_dbname`` at import; the old six-module route_slot
# missed all but ``narrative``.
IMPORT_BOUND = (
    narrative,
    slot_endpoints,
    save_slots,
    wizard_chat,
    wizard_agent,
    secrets_endpoints,
    new_story_setup,
)

OWNER_DATABASES = (
    "NEXUS_template",
    *(slot_utils.slot_dbname(slot) for slot in slot_utils.all_slots()),
)


def test_route_slot_reaches_import_bound_resolvers_and_restores_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every import-bound resolver sees slot 4 routed and slot 5 refused."""

    modules = list(IMPORT_BOUND)
    originals = [module.slot_dbname for module in modules]
    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    with pytest.MonkeyPatch.context() as patch:
        route_slot(patch, "qa640_route_probe")
        for module in modules:
            assert module.slot_dbname(4) == "qa640_route_probe", module.__name__
            with pytest.raises(RuntimeError, match="Slot 5 is not routed"):
                module.slot_dbname(5)
        assert slot_utils.VALID_DBNAMES == {"qa640_route_probe"}
        assert dict(active_slot_routes() or {}) == {4: "qa640_route_probe"}
        assert slot_utils.get_active_slot() == 4
    assert [module.slot_dbname for module in modules] == originals
    assert active_slot_routes() is None
    assert slot_utils.slot_dbname(4) == "save_04"


@pytest.mark.parametrize(
    ("dbname", "message"),
    [
        *((owner, "Refusing to seed owner database") for owner in OWNER_DATABASES),
        ("qa885_other_prefix", "routes only qa640_ clones"),
    ],
)
def test_route_slot_refuses_before_patching(dbname: str, message: str) -> None:
    """An owner name or a clone outside the convention patches nothing."""

    resolver = slot_utils.slot_dbname
    with pytest.MonkeyPatch.context() as patch:
        with pytest.raises(RuntimeError, match=message):
            route_slot(patch, dbname)
        assert slot_utils.slot_dbname is resolver
        assert active_slot_routes() is None


def test_child_environment_requires_exactly_one_active_route() -> None:
    """A child carries the one active route, and refuses none or several."""

    with pytest.raises(RuntimeError, match="No slot is routed"):
        routed_child_environment()
    with pytest.MonkeyPatch.context() as patch:
        route_slots_to_disposable(patch.setattr, {4: "qa640_a", 5: "qa640_b"})
        with pytest.raises(RuntimeError, match="carries one routed slot"):
            routed_child_environment()
    with pytest.MonkeyPatch.context() as patch:
        route_slot(patch, "qa640_child")
        assert routed_child_environment() == {
            ROUTED_SLOT_ENV: "4",
            ROUTED_SLOT_DATABASE_ENV: "qa640_child",
        }


def test_unrouted_child_cli_is_refused_before_it_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``run_cli``'s child verbs raise when no slot is routed."""

    private_runtime_config(tmp_path, monkeypatch)
    for verb in ("continue", "status", "down"):
        with pytest.raises(RuntimeError, match="No slot is routed"):
            run_cli(monkeypatch, verb)


def test_routed_child_down_reads_the_private_state_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A routed ``down`` child runs through ``tests.slot_routed_cli``.

    The private state directory holds no pidfile, so the real command stops
    nothing and says so.
    """

    private_runtime_config(tmp_path, monkeypatch)
    route_slot(monkeypatch, "qa640_down_probe")
    assert run_cli(monkeypatch, "down").strip() == "nothing running"


def test_private_runtime_config_is_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unset, the checkout's file, any checkout's state_dir, or one outside tmp raise.

    The absolute case names the main checkout's state_dir (the first tree
    ``git worktree list`` prints): from a builder's worktree that is another
    checkout's directory, which an inequality with this checkout alone let
    through.
    """

    monkeypatch.delenv(RUNTIME_CONFIG_ENV, raising=False)
    with pytest.raises(RuntimeError, match="is unset"):
        require_private_runtime_config()

    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(REPO_ROOT / "nexus.toml"))
    with pytest.raises(RuntimeError, match="is the checkout's nexus.toml"):
        require_private_runtime_config()

    copy = tmp_path / "copy.toml"
    copy.write_text((REPO_ROOT / "nexus.toml").read_text())
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(copy))
    with pytest.raises(RuntimeError, match="keeps the state_dir of checkout"):
        require_private_runtime_config()

    main_root = scheduler_helpers._checkout_roots()[0]
    default_state = tomllib.loads((REPO_ROOT / "nexus.toml").read_text())["runtime"][
        "state_dir"
    ]
    for label, state_dir in (
        ("main", anchor_path(main_root, default_state)),
        ("outside", Path.home() / ".nexus-guard-probe-never-created"),
    ):
        probe: Any = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
        probe["runtime"]["state_dir"] = str(state_dir)
        other = tmp_path / f"{label}.toml"
        other.write_text(tomlkit.dumps(probe))
        monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(other))
        expected = (
            "keeps the state_dir of checkout"
            if label == "main"
            else "outside the pytest temporary root"
        )
        with pytest.raises(RuntimeError, match=expected):
            require_private_runtime_config()

    # tomlkit's item types do not index statically; the document is plain TOML.
    doc: Any
    doc, path = private_runtime_config(tmp_path, monkeypatch)
    assert require_private_runtime_config() == path.resolve()
    assert doc["runtime"]["state_dir"] == str(tmp_path / "runtime")
    written = tomllib.loads(path.read_text())
    assert written["runtime"]["state_dir"] == str(tmp_path / "runtime")


def test_gateway_lane_refuses_to_start_without_a_private_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No lane binds when ``nexus down`` would reach the checkout's services."""

    monkeypatch.delenv(RUNTIME_CONFIG_ENV, raising=False)
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "0")
    with pytest.raises(RuntimeError, match="is unset"):
        with gateway_lane(monkeypatch):
            pytest.fail("gateway_lane started without a private runtime config")


@pytest.mark.requires_postgres
def test_gateway_lane_refuses_to_close_without_a_private_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A lane whose private config is gone at close raises and runs no ``down``.

    The lane starts on an OS-assigned port for a routed clone. Inside the block
    ``NEXUS_RUNTIME_CONFIG`` is removed, so the closing ``nexus down`` would
    act on the checkout's state_dir; the lane raises before it starts that
    child. The test then restores the private config and runs the ``down``
    the lane skipped.
    """

    _, config = private_runtime_config(tmp_path, monkeypatch)
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "0")
    real_run_cli = scheduler_helpers.run_cli
    cli_calls: list[tuple[str, ...]] = []

    def recording_run_cli(patch: pytest.MonkeyPatch, *args: str) -> str:
        cli_calls.append(args)
        return real_run_cli(patch, *args)

    monkeypatch.setattr(scheduler_helpers, "run_cli", recording_run_cli)
    with disposable_slot_database("qa640_lane_close") as dbname:
        route_slot(monkeypatch, dbname)
        with pytest.raises(RuntimeError, match="is unset"):
            with gateway_lane(monkeypatch):
                monkeypatch.delenv(RUNTIME_CONFIG_ENV)
        assert cli_calls == []
        monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))
        real_run_cli(monkeypatch, "down")

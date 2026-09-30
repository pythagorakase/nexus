"""Real scheduler proof configuration using the registered TEST provider.

Every helper here routes through the shared contract in ``tests.pg_fixtures``:
``route_slot`` is the slot-4 case of ``route_slots_to_disposable``,
``run_cli`` starts its child CLI through ``tests.slot_routed_cli`` with the
active route, and ``gateway_lane`` refuses to run its closing ``nexus down``
unless ``NEXUS_RUNTIME_CONFIG`` names a private config.
"""

import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import tomlkit

from tests.pg_fixtures import (
    active_slot_routes,
    require_disposable_target,
    route_slot_to_disposable,
    routed_slot_environment,
)

# The lane ``gateway_lane`` binds when ``NEXUS_GATEWAY_PORT`` is unset.
DEFAULT_GATEWAY_LANE = 8018

ROUTED_SLOT = 4

RUNTIME_CONFIG_ENV = "NEXUS_RUNTIME_CONFIG"

_CHECKOUT = Path(__file__).resolve().parents[1]


def private_runtime_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str = "runtime.toml"
) -> tuple[tomlkit.TOMLDocument, Path]:
    """Write a copy of nexus.toml whose state_dir is private; export it.

    ``nexus down`` stops every service whose pidfile sits in the configured
    ``[runtime].state_dir``. A test that starts a gateway or runs the CLI
    points that directory into ``tmp_path`` first, so it can never stop the
    owner's managed services. Returns the parsed document and its path; the
    caller may edit the document and rewrite the file.
    """
    doc = tomlkit.parse((_CHECKOUT / "nexus.toml").read_text())
    runtime: Any = doc["runtime"]
    runtime["state_dir"] = str(tmp_path / "runtime")
    path = tmp_path / name
    path.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(path))
    return doc, path


def test_provider_config(
    tmp_path: Path, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Route every provider consumer to TEST in a private config file."""
    # tomlkit's item types do not index statically; the document is plain TOML.
    doc: Any
    doc, path = private_runtime_config(tmp_path, monkeypatch, "scheduler.toml")
    providers = doc["global"]["model"]["api_models"]
    uses: list[str] = []
    for provider in providers.values():
        for model in provider["models"]:
            model_uses = model.pop("uses", [])
            uses.extend(use for use in model_uses if use != "local_models.model")
            if "local_models.model" in model_uses:
                model["uses"] = ["local_models.model"]
    providers["test"]["models"][0]["uses"] = uses
    providers["test"]["base_url"] = base_url
    doc["runtime"]["services"]["mock_openai"]["port"] = urlsplit(base_url).port
    doc["wizard"]["max_retries"] = 0
    doc["runtime"]["scheduler"].update(
        poll_interval_seconds=0.05,
        generation_wait_seconds=0.01,
        heartbeat_interval_seconds=0.1,
        lease_duration_seconds=3,
        compaction_retry_delay_seconds=0.1,
        error_backoff_seconds=0.1,
    )
    path.write_text(tomlkit.dumps(doc))
    return path


def _pytest_temp_root() -> Path:
    """Return the directory pytest creates every ``tmp_path`` under.

    Pytest roots its temporary directories at ``PYTEST_DEBUG_TEMPROOT`` when
    set, else at ``tempfile.gettempdir()``; this mirrors that choice.
    """
    raw = os.environ.get("PYTEST_DEBUG_TEMPROOT") or tempfile.gettempdir()
    return Path(raw).resolve()


def _checkout_roots() -> list[Path]:
    """Return every working tree of this repository, the main checkout first.

    ``git worktree list`` names the owner's main checkout as well as every
    builder's worktree, so a guard that compares against all of them refuses
    the owner's state_dir from whichever tree the gate runs in.
    """
    listed = subprocess.run(
        ["git", "-C", str(_CHECKOUT), "worktree", "list", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    roots = [
        Path(line.removeprefix("worktree ")).resolve()
        for line in listed.splitlines()
        if line.startswith("worktree ")
    ]
    if not roots:
        raise RuntimeError(f"`git worktree list` named no tree for {_CHECKOUT}")
    return roots


def require_private_runtime_config() -> Path:
    """Return the exported private runtime config, or raise.

    A config is private when ``NEXUS_RUNTIME_CONFIG`` names a file other than
    the checkout's ``nexus.toml`` whose ``[runtime].state_dir`` lies under the
    pytest temporary root and is no working tree's own state_dir (the
    checkout's default ``state_dir`` anchored at every ``git worktree list``
    root, the owner's main checkout included). Anything else could let
    ``nexus down`` stop the services the owner started.
    """
    from nexus.runtime.home import anchor_path

    raw = os.environ.get(RUNTIME_CONFIG_ENV)
    if not raw:
        raise RuntimeError(
            f"{RUNTIME_CONFIG_ENV} is unset, so `nexus down` would stop the "
            "services in the checkout's state_dir; export a private config "
            "(test_provider_config or private_runtime_config) first"
        )
    path = Path(raw).resolve()
    checkout_config = (_CHECKOUT / "nexus.toml").resolve()
    if path == checkout_config:
        raise RuntimeError(
            f"{RUNTIME_CONFIG_ENV}={raw!r} is the checkout's nexus.toml, not a "
            "private config"
        )

    def configured_state_dir(config: Path) -> str:
        doc: Any = tomlkit.parse(config.read_text())
        return str(doc["runtime"]["state_dir"])

    private_state = anchor_path(_CHECKOUT, configured_state_dir(path)).resolve()
    default_state = configured_state_dir(checkout_config)
    for root in _checkout_roots():
        if private_state == anchor_path(root, default_state).resolve():
            raise RuntimeError(
                f"{RUNTIME_CONFIG_ENV}={raw!r} keeps the state_dir of checkout "
                f"{str(root)!r} ({str(private_state)!r}); point it into the "
                "test's tmp_path"
            )
    temp_root = _pytest_temp_root()
    if not private_state.is_relative_to(temp_root):
        raise RuntimeError(
            f"{RUNTIME_CONFIG_ENV}={raw!r} puts state_dir at "
            f"{str(private_state)!r}, outside the pytest temporary root "
            f"{str(temp_root)!r}; point it into the test's tmp_path"
        )
    return path


def route_slot(monkeypatch: pytest.MonkeyPatch, dbname: str) -> None:
    """Route slot 4, and only slot 4, to a disposable clone for this test.

    The slot-4 case of ``tests.pg_fixtures.route_slot_to_disposable``: every
    loaded module's resolver (including names bound at import, and modules
    first imported while routed) returns ``dbname`` for slot 4 and raises
    ``RuntimeError`` for any other slot, ``VALID_DBNAMES`` holds only the
    clone, and ``NEXUS_SLOT`` is 4. The ``monkeypatch`` restores all of it at
    teardown. ``require_disposable_target`` refuses an owner name first; the
    ``qa640_`` prefix check after it is this helper's naming convention.
    """
    require_disposable_target(dbname)
    if not dbname.startswith("qa640_"):
        raise RuntimeError(f"route_slot routes only qa640_ clones, got {dbname!r}")
    route_slot_to_disposable(monkeypatch.setattr, slot=ROUTED_SLOT, dbname=dbname)
    monkeypatch.setenv("NEXUS_SLOT", str(ROUTED_SLOT))


def routed_child_environment() -> dict[str, str]:
    """Return the variables that route a child process like this one.

    A child runs ``tests.slot_routed_cli`` (or another routed entry point)
    with the one active route. It raises when no route is active, or when
    more than one slot is routed, because the child carries one route.
    """
    routes = active_slot_routes()
    if routes is None:
        raise RuntimeError(
            "No slot is routed; a child process would reach the owner's slot. "
            "Route the slot to a disposable clone first"
        )
    if len(routes) != 1:
        raise RuntimeError(
            f"A child process carries one routed slot; {dict(routes)} are routed"
        )
    ((slot, dbname),) = routes.items()
    return routed_slot_environment(slot, dbname)


def run_cli(monkeypatch: pytest.MonkeyPatch, *args: str) -> str:
    """Run the actual parser and command with fixture-owned database routing.

    ``continue``, ``status`` and ``down`` run in a child process through
    ``tests.slot_routed_cli``, which routes the child's slot exactly as the
    active route routes this process; every other verb runs in-process
    under that route.
    """
    import io
    import sys
    from contextlib import redirect_stdout
    from nexus import cli

    if args[0] in {"continue", "status", "down"}:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "tests.slot_routed_cli", *args],
            env={
                **os.environ,
                "PYTHONPATH": os.getcwd(),
                **routed_child_environment(),
            },
            capture_output=True,
            text=True,
            timeout=180,
        )
        code, output = result.returncode, result.stdout
        assert code == 0, output + result.stderr
    else:
        stream = io.StringIO()
        with monkeypatch.context() as patch, redirect_stdout(stream):
            patch.setattr(sys, "argv", ["nexus", *args])
            code = cli.main()
        output = stream.getvalue()
    print(f"$ nexus {' '.join(args)}\n{output}", flush=True)
    assert code == 0, output
    return output


@contextmanager
def gateway_lane(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Serve the real lifespan on the order's port and tear down only our server.

    The lane is ``NEXUS_GATEWAY_PORT``, else ``DEFAULT_GATEWAY_LANE``; ``0``
    binds an OS-assigned port, which the helper exports. It closes with
    ``nexus down``, so it requires a private ``NEXUS_RUNTIME_CONFIG`` before
    it starts and again before that ``down``, and raises otherwise.
    """
    import socket
    import subprocess
    import threading
    import time
    import uvicorn
    from nexus.api import narrative

    require_private_runtime_config()
    port = int(os.environ.get("NEXUS_GATEWAY_PORT", str(DEFAULT_GATEWAY_LANE)))
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", str(port))
    monkeypatch.setenv("NEXUS_API_URL", f"http://127.0.0.1:{port}")
    check = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True
    )
    assert check.returncode == 1, check.stdout + check.stderr
    server = uvicorn.Server(
        uvicorn.Config(narrative.app, host="127.0.0.1", port=port, log_level="warning")
    )
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        port = listener.getsockname()[1]
        monkeypatch.setenv("NEXUS_GATEWAY_PORT", str(port))
        monkeypatch.setenv("NEXUS_API_URL", f"http://127.0.0.1:{port}")
        listener.listen()
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while (
                not server.started and thread.is_alive() and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert server.started, f"Gateway {port} failed to start"
            yield narrative.app.state.scheduler
        finally:
            server.should_exit = True
            thread.join(timeout=30)
            assert not thread.is_alive(), f"Gateway {port} did not shut down"
            require_private_runtime_config()
            run_cli(monkeypatch, "down")

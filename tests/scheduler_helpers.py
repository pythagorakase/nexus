"""Real scheduler proof configuration using the registered TEST provider."""

from pathlib import Path
from urllib.parse import urlsplit

import tomlkit


def test_provider_config(tmp_path, base_url, monkeypatch):
    """Route every provider consumer to TEST in a private config file."""
    doc = tomlkit.parse(Path("nexus.toml").read_text())
    providers = doc["global"]["model"]["api_models"]
    uses = []
    for provider in providers.values():
        for model in provider["models"]:
            model_uses = model.pop("uses", [])
            uses.extend(use for use in model_uses if use != "local_models.model")
            if "local_models.model" in model_uses:
                model["uses"] = ["local_models.model"]
    providers["test"]["models"][0]["uses"] = uses
    providers["test"]["base_url"] = base_url
    doc["runtime"]["services"]["mock_openai"]["port"] = urlsplit(base_url).port
    doc["runtime"]["state_dir"] = str(tmp_path / "runtime")
    doc["wizard"]["max_retries"] = 0
    doc["runtime"]["scheduler"].update(
        poll_interval_seconds=0.05,
        generation_wait_seconds=0.01,
        heartbeat_interval_seconds=0.1,
        lease_duration_seconds=3,
        compaction_retry_delay_seconds=0.1,
        error_backoff_seconds=0.1,
    )
    path = tmp_path / "scheduler.toml"
    path.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
    return path


def route_slot(monkeypatch, dbname):
    """Route the real slot entry points exclusively to a disposable database."""
    from nexus.api import (
        narrative,
        new_story_flow,
        setup_endpoints,
        slot_mutations,
        slot_state,
        slot_utils,
    )

    assert dbname.startswith("qa640_")

    def slot_database(slot):
        assert slot == 4, f"Unexpected slot access: {slot}"
        return dbname

    monkeypatch.setattr(slot_utils, "VALID_DBNAMES", {dbname})
    for module in (
        narrative,
        new_story_flow,
        setup_endpoints,
        slot_mutations,
        slot_state,
        slot_utils,
    ):
        monkeypatch.setattr(module, "slot_dbname", slot_database)
    monkeypatch.setenv("NEXUS_SLOT", "4")


def run_cli(monkeypatch, *args):
    """Run the actual parser and command with fixture-owned database routing."""
    import io
    import sys
    from contextlib import redirect_stdout
    from nexus import cli

    if args[0] in {"continue", "status", "down"}:
        import os
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "nexus.cli", *args],
            env={**os.environ, "PYTHONPATH": os.getcwd()},
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


from contextlib import contextmanager


@contextmanager
def gateway_lane(monkeypatch):
    """Serve the real lifespan on the order's port and tear down only our server."""
    import socket
    import subprocess
    import threading
    import time
    import uvicorn
    from nexus.api import narrative

    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8018")
    monkeypatch.setenv("NEXUS_API_URL", "http://127.0.0.1:8018")
    check = subprocess.run(
        ["lsof", "-nP", "-iTCP:8018", "-sTCP:LISTEN"], capture_output=True, text=True
    )
    assert check.returncode == 1, check.stdout + check.stderr
    server = uvicorn.Server(
        uvicorn.Config(narrative.app, host="127.0.0.1", port=8018, log_level="warning")
    )
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 8018))
        listener.listen()
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while (
                not server.started and thread.is_alive() and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert server.started, "Gateway 8018 failed to start"
            yield narrative.app.state.scheduler
        finally:
            server.should_exit = True
            thread.join(timeout=30)
            assert not thread.is_alive(), "Gateway 8018 did not shut down"
            run_cli(monkeypatch, "down")

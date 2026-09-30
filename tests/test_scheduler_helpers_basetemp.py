"""The private-runtime guard honors pytest's ``--basetemp`` (issue #885).

``require_private_runtime_config`` admits a config whose state_dir lies under
pytest's actual base temp directory, which ``--basetemp`` can put outside the
system temp directory. The child run below points ``TMPDIR`` at one directory
and ``--basetemp`` at a sibling, so every ``tmp_path`` the child creates lies
outside its ``tempfile.gettempdir()``. The routing-contract module must still
pass there: the private config is admitted, the owner's state_dir and a
directory outside both roots are refused, and a gateway lane starts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ROUTING_MODULE = "tests/test_scheduler_helpers_routing.py"


def test_routing_contract_passes_under_a_basetemp_outside_the_system_temp(
    tmp_path: Path,
) -> None:
    """A child pytest run with ``--basetemp`` outside its temp dir passes."""

    child_tmp = tmp_path / "child-system-temp"
    child_tmp.mkdir()
    basetemp = tmp_path / "child-basetemp"
    assert not basetemp.resolve().is_relative_to(child_tmp.resolve())
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTEST_DEBUG_TEMPROOT",
            "PYTEST_ADDOPTS",
            "NEXUS_GATEWAY_PORT",
            "NEXUS_API_URL",
        }
    }
    env.update(TMPDIR=str(child_tmp), PYTHONPATH=str(REPO_ROOT))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-v",
            "-p",
            "no:cacheprovider",
            f"--basetemp={basetemp}",
            ROUTING_MODULE,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    required = [
        "test_private_runtime_config_is_required",
        "test_gateway_lane_refuses_to_start_without_a_private_config",
    ]
    if os.environ.get("NEXUS_RUN_POSTGRES") == "1":
        # The one case that serves a lane on a routed clone needs PostgreSQL.
        required.append("test_gateway_lane_refuses_to_close_without_a_private_config")
    for test in required:
        assert f"{ROUTING_MODULE}::{test} PASSED" in output, output
    # The child made its tmp_path directories under the basetemp, not TMPDIR.
    assert any(basetemp.glob("test_private_runtime_config_is*")), output
    assert not any(child_tmp.glob("pytest-of-*")), output

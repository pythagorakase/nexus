"""An exported ``NEXUS_SLOT`` never reaches a test (issue #885).

The owner's shell may export ``NEXUS_SLOT=1``. The root conftest removes it
before collection and again for every test, so a gateway lifespan inside a
routed test recovers and schedules only the slot that test routes and sets
itself. Each case runs a nested pytest session over a generated test file
under ``tmp_path`` with ``NEXUS_SLOT=1`` exported, the repository conftest
loaded with ``-p tests.conftest``, and the connection audit loaded with
``-p tests.dbname_audit``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTED_SLOT = 3
CLONE_PREFIX = "qa885_inherited_slot"

# Everything the nested session inherits besides the exported slot; libpq
# variables and gateway lanes never reach it.
CHILD_ENVIRONMENT_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "NEXUS_KEYRING_DISABLE",
    "NEXUS_TEST_PROVIDER_ONLY",
)

ROUTED_GATEWAY_SESSION = f"""
import os

import pytest
from fastapi.testclient import TestClient

from nexus.api import choice_recovery, narrative
from tests.pg_fixtures import disposable_slot_database, route_slot_to_disposable

ROUTED_SLOT = {ROUTED_SLOT}
# Read while pytest imports this module, during collection.
SLOT_AT_COLLECTION = os.environ.get("NEXUS_SLOT")


@pytest.fixture
def recovered(monkeypatch):
    slots = []
    recover = choice_recovery.recover_active_slot_choice

    def record(slot, *args, **kwargs):
        slots.append(slot)
        return recover(slot, *args, **kwargs)

    monkeypatch.setattr(choice_recovery, "recover_active_slot_choice", record)
    return slots


@pytest.fixture
def routed_clone(monkeypatch):
    with disposable_slot_database("{CLONE_PREFIX}") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=ROUTED_SLOT, dbname=dbname)
        yield dbname


def test_the_exported_slot_never_reaches_collection_or_a_test():
    assert SLOT_AT_COLLECTION is None
    assert "NEXUS_SLOT" not in os.environ


def test_a_routed_test_without_a_slot_starts_no_scheduler(routed_clone, recovered):
    with TestClient(narrative.app):
        assert narrative.app.state.scheduler is None
    assert recovered == []


def test_a_routed_lifespan_recovers_and_schedules_only_the_clone(
    routed_clone, recovered, monkeypatch
):
    monkeypatch.setenv("NEXUS_SLOT", str(ROUTED_SLOT))
    with TestClient(narrative.app) as client:
        scheduler = narrative.app.state.scheduler
        assert scheduler is not None
        assert (scheduler.slot, scheduler.dbname) == (ROUTED_SLOT, routed_clone)
        status = client.get("/runtime/status").json()
    assert recovered == [ROUTED_SLOT]
    assert status["slot"] == ROUTED_SLOT
    assert status["database"]["ok"] is True, status["database"]
    assert status["database"]["dbname"] == routed_clone
"""


def _nested_session(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the routed-gateway session with ``NEXUS_SLOT=1`` exported."""

    test_file = tmp_path / "test_nested_session.py"
    test_file.write_text(ROUTED_GATEWAY_SESSION)
    env = {
        name: os.environ[name]
        for name in CHILD_ENVIRONMENT_ALLOWLIST
        if name in os.environ
    }
    env.update(
        {
            "NEXUS_SLOT": "1",
            "NEXUS_RUN_POSTGRES": "1",
            "PYTHONPATH": os.pathsep.join([str(tmp_path), str(REPO_ROOT)]),
        }
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "tests.conftest",
            "-p",
            "tests.dbname_audit",
            "--rootdir",
            str(tmp_path),
            str(test_file),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.mark.requires_postgres
def test_exported_slot_never_reaches_a_routed_gateway_lifespan(
    tmp_path: Path,
) -> None:
    """With ``NEXUS_SLOT=1`` exported, only the routed clone is recovered.

    The nested session sees no slot at collection or in any test; a routed
    test that sets no slot starts no scheduler and recovers nothing; a routed
    test that sets slot 3 recovers and schedules slot 3 in its clone, and the
    runtime status names the clone. The audit records the clone and no owner
    target.
    """

    result = _nested_session(tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "3 passed" in output, output
    assert "dbname audit: owner targets: none" in output, output
    assert f"{CLONE_PREFIX}_*" in output, output

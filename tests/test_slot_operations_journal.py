"""Real journal files and process locks; no database is opened by these tests."""

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from typing import Iterator

import pytest

from nexus.api import db_pool, slot_utils
from nexus.runtime.slot_operations import (
    MaintenanceTargetError,
    OperationHandle,
    SlotOperationError,
    open_operation,
    read_operation,
    require_authorized,
    staging_dbname,
)
from scripts import new_story_setup
from tests.pg_fixtures import route_slot_to_disposable


@pytest.fixture
def handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[OperationHandle]:
    """Route the journal's destination without creating or connecting to a DB."""
    route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname="qa640_823s1_offline")
    operation = open_operation(
        "stage_clone",
        slot=5,
        source_db="qa640_823s1_source",
        journal_dir=tmp_path / "journal",
    )
    try:
        yield operation
    finally:
        operation.close()


def test_record_round_trips_without_temporary_file(handle: OperationHandle) -> None:
    """Every legal move remains readable with a complete UTC history."""
    assert read_operation(handle.path) == handle.record
    handle.advance("building", detail="begin copy")
    handle.advance("built")
    handle.advance("validated")
    record = read_operation(handle.path)
    assert record == handle.record
    assert [entry.phase for entry in record.history] == [
        "created",
        "building",
        "built",
        "validated",
    ]
    assert record.history[1].detail == "begin copy"
    assert not list(handle.path.parent.glob("*.tmp"))
    assert require_authorized(handle.target) == record


def test_illegal_move_keeps_record_bytes(handle: OperationHandle) -> None:
    before = handle.path.read_bytes()
    with pytest.raises(SlotOperationError, match="created -> validated"):
        handle.advance("validated")
    assert handle.path.read_bytes() == before


def test_staging_name_is_exact_and_never_truncated() -> None:
    operation_id = "0123456789abcdef0123456789abcdef"
    assert (
        staging_dbname("qa640_dest", operation_id) == "qa640_dest_staging_0123456789ab"
    )
    assert len(staging_dbname("x" * 42, operation_id).encode()) == 63
    with pytest.raises(ValueError, match="63-byte"):
        staging_dbname("x" * 43, operation_id)
    with pytest.raises(ValueError, match="63-byte"):
        staging_dbname("é" * 22, operation_id)


@pytest.mark.parametrize(
    "defect",
    ["dbname", "operation_id", "filename", "hand_edit", "missing", "invalid_json"],
)
def test_target_requires_exact_durable_authorization(
    handle: OperationHandle, defect: str
) -> None:
    handle.advance("building")
    target = handle.target
    if defect == "dbname":
        target = replace(target, dbname="qa640_victim")
    elif defect == "operation_id":
        target = replace(target, operation_id="f" * 32)
    elif defect == "filename":
        other = handle.path.with_name("other.json")
        other.write_bytes(handle.path.read_bytes())
        target = replace(target, journal_path=other)
    elif defect == "hand_edit":
        payload = json.loads(handle.path.read_text())
        payload["staging_db"] = "qa640_victim"
        handle.path.write_text(json.dumps(payload))
        target = replace(target, dbname="qa640_victim")
    elif defect == "missing":
        handle.path.unlink()
    else:
        handle.path.write_text("not json")
    with pytest.raises(MaintenanceTargetError):
        require_authorized(target)
    with pytest.raises(MaintenanceTargetError):
        with db_pool.get_maintenance_connection(target):
            pytest.fail("Invalid journal reached a connection")


@pytest.mark.parametrize("phase", ["created", "refused", "failed", "swept"])
def test_terminal_or_unstarted_operation_cannot_connect(
    handle: OperationHandle, phase: str
) -> None:
    if phase == "refused":
        handle.advance("building")
        handle.advance("built")
        handle.advance("refused", refusals=["probe: deliberate refusal"])
    elif phase == "failed":
        handle.advance("failed", error="fixture")
    elif phase == "swept":
        handle.advance("swept")
    with pytest.raises(MaintenanceTargetError):
        require_authorized(handle.target)
    with pytest.raises(MaintenanceTargetError):
        with db_pool.get_maintenance_connection(handle.target):
            pytest.fail("Forbidden phase reached a connection")


def test_read_rejects_a_naive_history_timestamp(handle: OperationHandle) -> None:
    payload = json.loads(handle.path.read_text())
    payload["history"][0]["at"] = "2100-01-01T00:00:00"
    handle.path.write_text(json.dumps(payload))
    with pytest.raises(SlotOperationError, match="aware UTC"):
        read_operation(handle.path)


def test_child_cannot_hold_a_live_operation_lock(handle: OperationHandle) -> None:
    script = """
import fcntl, sys
with open(sys.argv[1], 'r+') as stream:
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('held')
    else:
        print('free')
"""

    def probe() -> str:
        return subprocess.check_output(
            [sys.executable, "-c", script, str(handle.path.with_suffix(".lock"))],
            text=True,
            timeout=20,
        ).strip()

    assert probe() == "held"
    handle.close()
    assert probe() == "free"


def test_gameplay_pool_refuses_staging_names() -> None:
    assert slot_utils.VALID_DBNAMES == {f"save_{n:02d}" for n in range(1, 6)}
    with pytest.raises(ValueError):
        with db_pool.get_connection("save_05_staging_0123456789ab"):
            pytest.fail("Gameplay admission allowed a staging name")


@pytest.mark.parametrize(
    "argv, message",
    [
        (
            ["--slot", "5", "--stage", "--force"],
            "--stage cannot be combined with --force or --create-assets",
        ),
        (["--stage"], "--stage requires --slot"),
        (["--sweep-staging", "--slot", "5"], "--sweep-staging takes no other option"),
        (
            ["--stage", "--create-assets"],
            "--stage cannot be combined with --force or --create-assets",
        ),
        (
            ["--sweep-staging", "--mode", "clone"],
            "--sweep-staging takes no other option",
        ),
    ],
)
def test_cli_refuses_before_any_tool_or_operation(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The amended order uses actual early refusals, without entrypoint tripwires."""
    with pytest.raises(SystemExit) as caught:
        new_story_setup.main(argv)
    assert caught.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1].endswith(f"error: {message}")

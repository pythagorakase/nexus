"""Failure receipts (issue #806): sanitized, append-only, grouped on read.

Every test runs the real loaders against real files. Each sets the receipt
seam to its own temporary directory unless it says otherwise; the planted
strings stand in for a secret and a prompt that a broken configuration can
hold, and must never reach a receipt file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tomllib
from typing import Any, Optional

from pydantic import ValidationError
import pytest

from nexus.config.loader import load_settings
from nexus.config.preferences import load_preferences, preferences_path
from nexus.runtime.contract import (
    FALLBACK_RECEIPTS_DIR,
    HOME_ENV,
    RUNTIME_CONFIG_ENV,
    TEST_RECEIPTS_ENV,
)
from nexus.runtime.home import (
    RECEIPTS_DIR,
    HomeLocation,
    RuntimeHomeError,
    build_runtime_home,
    locate_runtime_home,
    repo_root,
)
from nexus.runtime.receipts import (
    FailureReceipt,
    home_receipts_dir,
    read_failure_groups,
)

ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG = ROOT / "nexus.toml"

PLANTED_SECRET = "sk-planted-806-0123456789abcdef"
PLANTED_PROMPT = "You are the storyteller. PLANTED-806 prompt text."

BROKEN_TOML = (
    f"[runtime]\ndefault_slot = 1\nplanted = {PLANTED_SECRET} {PLANTED_PROMPT}\n"
)

# Locators and API settings the CLI must not inherit from the developer shell.
_ISOLATED_ENV = ("NEXUS_API_URL", "NEXUS_GATEWAY_PORT", RUNTIME_CONFIG_ENV)


@pytest.fixture
def seam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Route this test's receipts to ``tmp_path / "receipts"``."""
    root = tmp_path / "receipts"
    monkeypatch.setenv(TEST_RECEIPTS_ENV, str(root))
    monkeypatch.delenv(HOME_ENV, raising=False)
    monkeypatch.delenv(RUNTIME_CONFIG_ENV, raising=False)
    return root


def _receipt_lines(directory: Path) -> list[bytes]:
    """Every receipt line under ``directory``, in day-file order."""
    if not directory.exists():
        return []
    lines: list[bytes] = []
    for path in sorted(directory.glob("failures-*.jsonl")):
        lines.extend(path.read_bytes().splitlines())
    return lines


def _records(directory: Path) -> list[dict[str, Any]]:
    """The receipt lines under ``directory`` as JSON objects."""
    return [json.loads(line) for line in _receipt_lines(directory)]


def _assert_clean(raw: bytes) -> None:
    """Neither planted string reaches a receipt."""
    assert PLANTED_SECRET.encode() not in raw
    assert PLANTED_PROMPT.encode() not in raw
    assert b"PLANTED-806" not in raw


def _broken_config(tmp_path: Path, name: str = "broken.toml") -> Path:
    """A nexus.toml that fails to parse, holding both planted strings."""
    path = tmp_path / name
    path.write_text(BROKEN_TOML, encoding="utf-8")
    return path


def _invalid_config(tmp_path: Path) -> Path:
    """The checkout config with planted values that fail validation.

    ``default_slot`` holds both planted strings, and ``[runtime]`` gains an
    unknown key whose value is the secret and a bare key named the secret.
    """
    text = REPO_CONFIG.read_text(encoding="utf-8")
    assert text.count("\ndefault_slot = 1 ") == 1
    text = text.replace(
        "\ndefault_slot = 1 ",
        f'\ndefault_slot = "{PLANTED_SECRET} {PLANTED_PROMPT}" ',
    )
    assert text.count("\n[runtime]\n") == 1
    text = text.replace(
        "\n[runtime]\n",
        f'\n[runtime]\nplanted_value = "{PLANTED_SECRET}"\n{PLANTED_SECRET} = 1\n',
    )
    path = tmp_path / "invalid.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _snapshot(directory: Path) -> Optional[list[tuple[str, int]]]:
    """Sorted relative paths and sizes of every file below ``directory``."""
    if not directory.exists():
        return None
    return sorted(
        (path.relative_to(directory).as_posix(), path.stat().st_size)
        for path in directory.rglob("*")
        if path.is_file()
    )


def _run_cli(
    *argv: str, env: Optional[dict[str, str]] = None
) -> subprocess.CompletedProcess[str]:
    """Run the real CLI entry point with the inherited environment."""
    base = {key: value for key, value in os.environ.items() if key not in _ISOLATED_ENV}
    return subprocess.run(
        [sys.executable, "-m", "nexus.cli", *argv],
        cwd=ROOT,
        env={
            **base,
            "NEXUS_KEYRING_DISABLE": "1",
            "PYTHONPATH": str(ROOT),
            **(env or {}),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )


def _failure(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """The one JSON failure envelope a failed ``--json`` command printed."""
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr, completed.stderr
    envelope = json.loads(completed.stderr)
    assert set(envelope) == {"ok", "code", "error", "partial"}
    assert envelope["ok"] is False
    return dict(envelope)


def test_malformed_toml_writes_one_sanitized_receipt(
    seam: Path, tmp_path: Path
) -> None:
    """A parse failure records its position, never its message or the text."""
    path = _broken_config(tmp_path)
    with pytest.raises(tomllib.TOMLDecodeError) as raised:
        load_settings(path)
    with pytest.raises(tomllib.TOMLDecodeError) as direct:
        tomllib.loads(BROKEN_TOML)
    assert str(raised.value) == str(direct.value)

    lines = _receipt_lines(seam / "home")
    assert len(lines) == 1
    raw = lines[0]
    _assert_clean(raw)
    assert str(direct.value).encode() not in raw
    assert b"Invalid value" not in raw
    record = json.loads(raw)
    assert record["surface"] == "config.load_settings"
    assert record["config_path"] == str(path)
    assert record["exception_module"] == "tomllib"
    assert record["exception_type"] == "TOMLDecodeError"
    assert record["details"] == {"kind": "toml", "line": 3, "column": 11}
    assert record["frames"]
    assert all(set(frame) == {"file", "line", "function"} for frame in record["frames"])
    assert record["frames"][0] == {
        "file": "nexus/config/loader.py",
        "line": record["frames"][0]["line"],
        "function": "load_settings",
    }
    assert _receipt_lines(seam / "fallback") == []


def test_validation_receipt_keeps_loc_and_type_only(seam: Path, tmp_path: Path) -> None:
    """Validation errors keep their location and type; unknown keys are ``?``."""
    path = _invalid_config(tmp_path)
    with pytest.raises(ValidationError):
        load_settings(path)

    lines = _receipt_lines(seam / "home")
    assert len(lines) == 1
    raw = lines[0]
    _assert_clean(raw)
    for key in (b'"msg"', b'"input"', b'"ctx"', b'"url"'):
        assert key not in raw
    assert b"planted_value" not in raw
    details = json.loads(raw)["details"]
    assert details["kind"] == "validation"
    assert details["model"] == "Settings"
    assert details["error_count"] == len(details["errors"])
    locs = [entry["loc"] for entry in details["errors"]]
    assert ["runtime", "default_slot"] in locs
    assert {"loc": ["runtime", "?"], "type": "extra_forbidden"} in details["errors"]
    assert all(set(entry) == {"loc", "type"} for entry in details["errors"])


def test_preferences_failure_writes_a_receipt(seam: Path, tmp_path: Path) -> None:
    """A malformed preferences.toml records a ``config.preferences`` receipt."""
    settings = load_settings()
    assert settings.runtime is not None
    runtime = settings.runtime.model_copy(update={"state_dir": str(tmp_path / "state")})
    settings = settings.model_copy(update={"runtime": runtime})
    path = preferences_path(settings)
    assert path == tmp_path / "state" / "preferences.toml"
    path.parent.mkdir(parents=True)
    path.write_text(
        f"theme = {PLANTED_SECRET}\nwizard_model = {PLANTED_PROMPT}\n",
        encoding="utf-8",
    )

    with pytest.raises(tomllib.TOMLDecodeError):
        load_preferences(settings)

    lines = _receipt_lines(seam / "home")
    assert len(lines) == 1
    _assert_clean(lines[0])
    record = json.loads(lines[0])
    assert record["surface"] == "config.preferences"
    assert record["config_path"] == str(path)
    assert record["details"]["kind"] == "toml"


def test_runtime_home_error_goes_to_the_fallback_root(
    seam: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A home that cannot be located records to the fallback root only."""
    settings = load_settings(REPO_CONFIG)
    monkeypatch.setenv(HOME_ENV, "relative/home")

    with pytest.raises(RuntimeHomeError) as raised:
        locate_runtime_home()
    records = _records(seam / "fallback")
    assert len(records) == 1
    assert records[0]["surface"] == "runtime.home"
    assert records[0]["config_path"] is None
    assert records[0]["details"] == {
        "kind": "runtime_home",
        "message": " ".join(str(raised.value).split()),
    }
    assert _receipt_lines(seam / "home") == []

    location = HomeLocation(
        tmp_path, tmp_path / "nexus.toml", "checkout", tmp_path / "nexus.toml"
    )
    with pytest.raises(RuntimeHomeError):
        build_runtime_home(location, settings.model_copy(update={"runtime": None}))
    assert [r["surface"] for r in _records(seam / "fallback")] == ["runtime.home"] * 2

    broken = _broken_config(tmp_path)
    with pytest.raises(tomllib.TOMLDecodeError) as load_error:
        load_settings(broken)
    with pytest.raises(tomllib.TOMLDecodeError) as direct:
        tomllib.loads(BROKEN_TOML)
    assert str(load_error.value) == str(direct.value)
    records = _records(seam / "fallback")
    assert [r["surface"] for r in records] == [
        "runtime.home",
        "runtime.home",
        "runtime.home",
        "config.load_settings",
    ]
    assert records[-1]["config_path"] == str(broken)
    assert _receipt_lines(seam / "home") == []


def test_production_roots_without_the_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without the seam, receipts land in the home and in ``~/.nexus/receipts``."""
    monkeypatch.delenv(TEST_RECEIPTS_ENV, raising=False)
    monkeypatch.delenv(RUNTIME_CONFIG_ENV, raising=False)
    home = tmp_path / "home"
    user = tmp_path / "user"
    monkeypatch.setenv(HOME_ENV, str(home))
    monkeypatch.setenv("HOME", str(user))
    receipts = home.resolve() / RECEIPTS_DIR

    with pytest.raises(tomllib.TOMLDecodeError):
        load_settings(_broken_config(tmp_path))
    records = _records(receipts)
    assert len(records) == 1
    day = records[0]["recorded_at"][:10]
    day_file = receipts / f"failures-{day}.jsonl"
    assert day_file.is_file()
    assert stat.S_IMODE(day_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipts.stat().st_mode) == 0o700
    capsys.readouterr()

    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "absent.toml")
    records = _records(receipts)
    assert len(records) == 2
    assert records[1]["surface"] == "config.load_settings"
    assert records[1]["details"] == {"kind": "os", "errno": None}
    assert capsys.readouterr().err == ""

    monkeypatch.setenv(HOME_ENV, "relative")
    with pytest.raises(RuntimeHomeError):
        locate_runtime_home()
    fallback = user / FALLBACK_RECEIPTS_DIR
    assert [r["surface"] for r in _records(fallback)] == ["runtime.home"]
    assert len(_records(receipts)) == 2

    monkeypatch.setenv(HOME_ENV, str(home))
    built = build_runtime_home(locate_runtime_home(), load_settings(REPO_CONFIG))
    assert built.receipts_dir == home_receipts_dir() == receipts


def test_repeats_compact_to_one_group(seam: Path, tmp_path: Path) -> None:
    """Five identical failures and one other read back as two groups."""
    broken = _broken_config(tmp_path)
    for _ in range(5):
        with pytest.raises(tomllib.TOMLDecodeError):
            load_settings(broken)
    with pytest.raises(ValidationError):
        load_settings(_invalid_config(tmp_path))

    lines = _receipt_lines(seam / "home")
    assert len(lines) == 6
    assert len(list((seam / "home").glob("failures-*.jsonl"))) == 1
    roots = {"home": seam / "home", "fallback": seam / "fallback"}
    groups = read_failure_groups(roots)
    assert sorted(group.count for group in groups) == [1, 5]
    repeated = next(group for group in groups if group.count == 5)
    assert repeated.first == FailureReceipt.model_validate_json(lines[0])
    assert repeated.roots == ["home"]
    assert _receipt_lines(seam / "home") == lines

    completed = _run_cli("receipts", "--json")
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    assert document == {
        "home_dir": str(seam / "home"),
        "fallback_dir": str(seam / "fallback"),
        "groups": [group.model_dump(mode="json") for group in groups],
    }

    text = _run_cli("receipts")
    assert text.returncode == 0, text.stderr
    headers = [line for line in text.stdout.splitlines() if not line.startswith(" ")]
    assert len(headers) == 2
    assert headers[0].startswith(f"{groups[0].count}x {groups[0].fingerprint[:12]} ")
    assert _receipt_lines(seam / "home") == lines


def test_unwritable_root_does_not_mask_the_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A receipt that cannot be written leaves the original error unchanged."""
    blocker = tmp_path / "blocker"
    blocker.write_text("a regular file", encoding="utf-8")
    monkeypatch.setenv(TEST_RECEIPTS_ENV, str(blocker / "receipts"))
    monkeypatch.delenv(HOME_ENV, raising=False)
    monkeypatch.delenv(RUNTIME_CONFIG_ENV, raising=False)

    with pytest.raises(tomllib.TOMLDecodeError) as raised:
        load_settings(_broken_config(tmp_path))
    with pytest.raises(tomllib.TOMLDecodeError) as direct:
        tomllib.loads(BROKEN_TOML)
    assert type(raised.value) is type(direct.value)
    assert str(raised.value) == str(direct.value)
    assert "receipt not written for config.load_settings" in capsys.readouterr().err


def test_child_receipts_land_in_the_session_root(tmp_path: Path) -> None:
    """A child CLI inherits the session seam; real receipt roots stay untouched."""
    session_root = Path(os.environ[TEST_RECEIPTS_ENV])
    checkout = repo_root() / RECEIPTS_DIR
    user = Path.home() / FALLBACK_RECEIPTS_DIR
    before = (_snapshot(checkout), _snapshot(user))
    broken = _broken_config(tmp_path)

    completed = _run_cli("--json", "status", "--config", str(broken))

    assert completed.returncode == 1
    assert _failure(completed)["code"] == "config_error"
    mine = [
        record
        for record in _records(session_root / "home")
        if record["config_path"] == str(broken)
    ]
    assert [record["surface"] for record in mine] == ["config.load_settings"]
    assert (_snapshot(checkout), _snapshot(user)) == before


def test_receipts_command_reports_a_broken_home(
    seam: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``nexus receipts`` reads the fallback root when no home is located."""
    monkeypatch.setenv(HOME_ENV, "relative/home")
    with pytest.raises(RuntimeHomeError):
        locate_runtime_home()

    completed = _run_cli("receipts", "--json")

    assert completed.returncode == 1
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert envelope["error"].startswith("home receipts unavailable: ")
    partial = envelope["partial"]
    assert partial["home_dir"] is None
    assert partial["fallback_dir"] == str(seam / "fallback")
    assert len(partial["groups"]) == 1
    count = len(_receipt_lines(seam / "fallback"))
    assert partial["groups"][0]["count"] == count
    assert count >= 2

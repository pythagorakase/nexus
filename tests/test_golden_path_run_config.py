"""The golden-path run config pins its own absolute usage ledger (802-D9).

Offline and database-free: the golden-path gate writes a temporary runtime
config on every run, with or without a golden model override, whose
``usage.usage_dir`` is an absolute directory of the run. The gateway child
inherits that config through ``NEXUS_RUNTIME_CONFIG`` and the in-process stage 9
reads the same recorder config, so both sides of the turn observation read one
ledger and no clone event reaches the owner's account ledger.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import tomlkit

import nexus.telemetry.usage as usage_telemetry
from nexus.config import load_settings
from tests.test_golden_path_live import MODEL_OVERRIDE_ENV, _configure_run_config

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("override", [False, True], ids=["no_override", "override"])
def test_golden_run_config_pins_an_absolute_usage_dir(
    override: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Every run config, override or not, carries the run's absolute ledger."""

    # Set through monkeypatch so teardown restores the variable the helper sets.
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(REPO_ROOT / "nexus.toml"))
    checkout_model = load_settings().apex.model
    if override:
        monkeypatch.setenv(MODEL_OVERRIDE_ENV, checkout_model)
    else:
        monkeypatch.delenv(MODEL_OVERRIDE_ENV, raising=False)

    usage_dir = _configure_run_config(tmp_path_factory)

    assert usage_dir.is_absolute(), usage_dir
    written = Path(os.environ["NEXUS_RUNTIME_CONFIG"])
    assert written != REPO_ROOT / "nexus.toml", written
    document: Any = tomlkit.parse(written.read_text())
    assert document["usage"]["usage_dir"] == str(usage_dir)
    # The gateway child's loader resolves the same directory.
    assert usage_telemetry._load_recorder_config().usage_dir == usage_dir
    assert load_settings().apex.model == checkout_model

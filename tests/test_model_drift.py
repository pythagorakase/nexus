"""Keep model upgrades from leaving hardcoded IDs outside the roster."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_model_drift import find_violations


@pytest.mark.parametrize(
    "model_id",
    [
        "gpt-5",
        "gpt-5.6-terra",
        "gpt-6-astra",
        "gpt-7-next",
        "gpt-10-next",
        "claude-sonnet-5-0",
        "claude-opus-5",
        "claude-fable-5-1",
        "claude-next-6",
    ],
)
def test_runtime_model_literals_fail_the_drift_gate(
    tmp_path: Path, model_id: str
) -> None:
    """Current and future model families must not bypass the commit gate."""
    source = tmp_path / "consumer.py"
    source.write_text(f'MODEL = "{model_id}"\n', encoding="utf-8")

    checker = Path(__file__).resolve().parents[1] / "scripts/check_model_drift.py"
    result = subprocess.run(
        [sys.executable, str(checker), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert f'consumer.py:1: MODEL = "{model_id}"' in result.stderr


@pytest.mark.parametrize("model_id", ["gpt-6-astra", "claude-fable-5-1"])
def test_registered_and_intentionally_pinned_models_remain_allowed(
    tmp_path: Path, model_id: str
) -> None:
    """Expanded detection preserves the registry and documented pin exemptions."""
    (tmp_path / "nexus.toml").write_text(f'id = "{model_id}"\n', encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        f'MODEL = "{model_id}"  # pin: provider compatibility fixture\n',
        encoding="utf-8",
    )

    assert find_violations(tmp_path) == []


def test_legacy_gpt_models_remain_outside_the_managed_families(tmp_path: Path) -> None:
    """Legacy utility IDs keep the checker's existing exemption."""
    (tmp_path / "legacy.py").write_text(
        'MODELS = ["gpt-3.5-turbo", "gpt-4.1"]\n', encoding="utf-8"
    )

    assert find_violations(tmp_path) == []

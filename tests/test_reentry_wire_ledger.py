"""Real TEST-route validation, ledger, and CLI proofs without inference calls."""

import json
import sys
from copy import copy

import pytest
from pydantic_ai import ModelRetry

from nexus import cli
from nexus.agents.logon.skald_wire import SkaldWriterWire
from nexus.telemetry.usage import read_prompt_windows
from tests.test_lore.window_helpers import window_logon


@pytest.mark.asyncio
async def test_wire_repair_guard_records_attempt_and_cli_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Use the actual TEST provider, guard, validator, file ledger, and CLI."""
    from datetime import datetime, timezone

    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    utility = window_logon()
    utility._ensure_provider()
    provider = copy(utility.provider)
    utility._writer_window_blocks = [("user input", "Return.")]
    utility._window_payload = {"metadata": {"turn_id": "918-ledger"}}
    for attempt in (1, 2):
        # Rebinding must unwrap the previous validator, avoiding stale-attempt notes.
        utility._attach_prompt_window_guard(
            provider, "Return.", seat="skald_writer", window=75000
        )
        provider.prompt_window_guard("Return.", attempt)
        wire = SkaldWriterWire.model_validate(
            {
                "narrative": "The player returns.",
                "choices": ["Wait.", "Continue."],
                "letter": "Continue the return scene.",
                "presence": {
                    "scene_reset": {
                        "place": {"kind": "place", "name": "Hall"},
                        "present": [{"kind": "character", "name": "Player"}],
                    },
                    "enter": [{"kind": "character", "name": "Player"}],
                    "exit": [{"kind": "character", "name": "Old Friend"}],
                },
            }
        )
        if attempt == 1:
            wire.letter = "An overlong private letter. " * 10000
            with pytest.raises(ModelRetry, match="letter"):
                await provider.output_validator(None, wire)
        else:
            await provider.output_validator(None, wire)
        assert len(wire.presence.scene_reset.present) == 1
    rows = read_prompt_windows(
        "918-ledger", datetime.now(timezone.utc).date().isoformat()
    )
    assert [row.attempt for row in rows] == [1, 2]
    assert [len(row.validation_notes) for row in rows] == [1, 1]
    monkeypatch.setattr(
        sys, "argv", ["nexus", "usage", "--run", "918-ledger", "--json"]
    )
    capsys.readouterr()
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["windows"][1]["validation_notes"] == [
        {
            "repair": "scene-reset-crossings",
            "moved": ["Player"],
            "dropped": ["Old Friend"],
        }
    ]

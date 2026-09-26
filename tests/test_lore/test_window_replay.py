"""Provider-free replay of recorded prompt windows under candidate settings."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, cast

import pytest
import tomlkit

from nexus import cli
from nexus.config import load_settings
from nexus.config.local_window import local_context_window
from nexus.config.seat_window import SeatWindow, resolve_seat_window
from nexus.config.settings_models import Settings
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.usage import record_prompt_window
from nexus.telemetry.window_replay import (
    NoPromptWindowsError,
    ReplayRow,
    replay_record,
    replay_run,
)

REPO_CONFIG = Path(__file__).resolve().parents[2] / "nexus.toml"
SESSION = "window-replay-proof"
# Memory blocks the trimming pass may drop, then blocks it never touches.
TRIMMABLE = {
    "recent narrative": 20_000,
    "historical context": 10_000,
    "recalled scenes": 4_000,
}
FIXED = {"system": 3_000, "entity dossier": 6_000}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _candidate(tmp_path: Path, name: str, **apex: int) -> Path:
    """Write a copy of the real nexus.toml with changed writer seat policy."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    for key, value in apex.items():
        cast(Any, document["apex"])[key] = value
    path = tmp_path / f"{name}.toml"
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _record(
    budget: SeatWindow, *, input_tokens: int, session: str = SESSION, attempt: int = 1
) -> PromptWindowRecord:
    """Append one attempt exactly as the final guard records it."""
    fixed = input_tokens - sum(TRIMMABLE.values()) - sum(FIXED.values())
    assert fixed > 0
    record = PromptWindowRecord(
        generation_session=session,
        seat=budget.seat,
        attempt=attempt,
        model=budget.model,
        block_tokens={**FIXED, **TRIMMABLE, "user input": fixed},
        input_tokens=input_tokens,
        effective_ceiling=budget.input_ceiling,
        policy_headroom=budget.policy_headroom,
        headroom=budget.input_ceiling - input_tokens,
    )
    record_prompt_window(record)
    return record


def _local_model(settings: Settings) -> str:
    """Return the configured local model, which these proofs require."""
    model = settings.local_models.model
    assert model is not None, "nexus.toml must configure local_models.model"
    return model


def _local_budget(settings: Settings, seat: str) -> SeatWindow:
    """Resolve a local seat at the largest spend its serving window allows."""
    dumped = settings.model_dump()
    return resolve_seat_window(
        dumped,
        _local_model(settings),
        seat=seat,
        window=local_context_window(dumped),
    )


def test_replay_under_recorded_settings_changes_nothing() -> None:
    """The recorded spend round-trips through the shared seat arithmetic."""
    settings = load_settings(REPO_CONFIG)
    window = settings.lore.token_budget.apex_context_window
    for model in (settings.apex.model, _local_model(settings)):
        budget = resolve_seat_window(
            settings.model_dump(), model, seat="skald_writer", window=window
        )
        record = _record(budget, input_tokens=budget.input_ceiling - 700)
        row = replay_record(record, settings.model_dump())
        assert row.candidate_ceiling == record.effective_ceiling
        assert row.headroom_delta == row.overflow_tokens == 0
        assert row.freed_tokens == record.headroom == 700
        assert row.trimmable_tokens == sum(TRIMMABLE.values())
        assert row.feasible


def test_raised_output_allowance_tightens_a_model_limited_writer(
    tmp_path: Path,
) -> None:
    """A larger writer output allowance costs exactly that much input.

    Gaia keeps its own seat policy, so its replay does not move.
    """
    settings = load_settings(REPO_CONFIG)
    writer_budget = _local_budget(settings, "skald_writer")
    gaia_budget = _local_budget(settings, "gaia")
    writer = _record(writer_budget, input_tokens=writer_budget.input_ceiling - 500)
    _record(gaia_budget, input_tokens=gaia_budget.input_ceiling - 500)
    raised = settings.apex.max_output_tokens + 15_000
    candidate = load_settings(
        _candidate(tmp_path, "raised", max_output_tokens=raised)
    ).model_dump()

    rows = replay_run(SESSION, _today(), candidate)

    by_seat = {row.seat: row for row in rows}
    assert by_seat["gaia"].headroom_delta == 0
    assert by_seat["gaia"].feasible
    row = by_seat["skald_writer"]
    assert row.window == writer.effective_ceiling + writer.policy_headroom
    assert row.headroom_delta == settings.apex.max_output_tokens - raised
    assert row.overflow_tokens == 15_000 - 500
    assert row.overflow_tokens <= row.trimmable_tokens
    assert row.feasible and row.freed_tokens == 0


def test_overflow_beyond_trimmable_memory_is_infeasible(tmp_path: Path) -> None:
    """Overflow the memory blocks cannot absorb is reported as infeasible."""
    settings = load_settings(REPO_CONFIG)
    budget = _local_budget(settings, "skald_writer")
    record = _record(budget, input_tokens=budget.input_ceiling - 500)
    trimmable = sum(TRIMMABLE.values())
    # One token more output than the memory blocks can pay for in input.
    raised = settings.apex.max_output_tokens + trimmable + 500 + 1
    candidate = load_settings(
        _candidate(tmp_path, "harsh", max_output_tokens=raised)
    ).model_dump()

    row = replay_record(record, candidate)

    assert row.overflow_tokens == trimmable + 1
    assert row.trimmable_tokens == trimmable
    assert not row.feasible


def test_smaller_response_reserve_frees_frontier_input(tmp_path: Path) -> None:
    """Policy headroom is carved from the same spend, so shrinking it frees input."""
    settings = load_settings(REPO_CONFIG)
    budget = resolve_seat_window(
        settings.model_dump(),
        settings.apex.model,
        seat="skald_writer",
        window=settings.lore.token_budget.apex_context_window,
    )
    record = _record(budget, input_tokens=budget.input_ceiling - 2_000)
    reserve = settings.apex.response_reserve_tokens - 3_000
    candidate = load_settings(
        _candidate(tmp_path, "reserve", response_reserve_tokens=reserve)
    ).model_dump()

    row = replay_record(record, candidate)

    assert row.candidate_policy_headroom == reserve
    assert row.headroom_delta == 3_000
    assert row.freed_tokens == 5_000
    assert row.overflow_tokens == 0


def test_explicit_window_replaces_the_recorded_spend() -> None:
    """An explicit spend is resolved against the candidate model's limits."""
    settings = load_settings(REPO_CONFIG)
    dumped = settings.model_dump()
    budget = resolve_seat_window(
        dumped,
        settings.apex.model,
        seat="skald_writer",
        window=settings.lore.token_budget.apex_context_window,
    )
    record = _record(budget, input_tokens=budget.input_ceiling - 100)
    smaller = record.effective_ceiling + record.policy_headroom - 10_000

    row = replay_record(record, dumped, window=smaller)

    assert row.window == smaller
    assert row.headroom_delta == -10_000
    assert row.overflow_tokens == 10_000 - 100


def test_candidate_resolution_errors_propagate() -> None:
    """An unregistered model or an impossible allowance is never replayed."""
    settings = load_settings(REPO_CONFIG)
    dumped = settings.model_dump()
    budget = _local_budget(settings, "skald_writer")
    record = _record(budget, input_tokens=budget.input_ceiling - 100)
    with pytest.raises(ValueError, match="must have one registry entry"):
        replay_record(record, dumped, model="unregistered/replay-candidate")
    maximum = settings.model_entry(_local_model(settings)).max_output_tokens
    assert maximum is not None
    dumped["apex"]["max_output_tokens"] = maximum + 1
    with pytest.raises(ValueError, match="exceeds model maximum"):
        replay_record(record, dumped)


def test_replay_run_reads_one_session_and_rejects_empty_or_bad_days() -> None:
    """Only the requested run is replayed; a missing run is an error."""
    settings = load_settings(REPO_CONFIG)
    dumped = settings.model_dump()
    budget = _local_budget(settings, "skald_writer")
    _record(budget, input_tokens=budget.input_ceiling - 100)
    _record(budget, input_tokens=budget.input_ceiling - 200, attempt=2)
    _record(budget, input_tokens=budget.input_ceiling - 300, session="unrelated")

    rows = replay_run(SESSION, _today(), dumped)

    assert [(row.attempt, row.freed_tokens) for row in rows] == [(1, 100), (2, 200)]
    assert all(isinstance(row, ReplayRow) for row in rows)
    with pytest.raises(NoPromptWindowsError, match="'missing-run'"):
        replay_run("missing-run", _today(), dumped)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        replay_run(SESSION, "2026-2-3", dumped)


def test_cli_window_replay_json_and_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The real CLI validates the candidate TOML and reports each attempt."""
    settings = load_settings(REPO_CONFIG)
    budget = _local_budget(settings, "skald_writer")
    _record(budget, input_tokens=budget.input_ceiling - 500)
    raised = settings.apex.max_output_tokens + 15_000
    config = _candidate(tmp_path, "cli", max_output_tokens=raised)
    argv = ["nexus", "window-replay", "--run", SESSION, "--config", str(config)]

    monkeypatch.setattr(sys, "argv", [*argv, "--json"])
    assert cli.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["window_replay"]["day"] == _today()
    [row] = payload["window_replay"]["rows"]
    assert row["headroom_delta"] == -15_000
    assert row["overflow_tokens"] == 14_500
    assert row["feasible"] is True

    monkeypatch.setattr(sys, "argv", argv)
    assert cli.main() == 0
    table = capsys.readouterr().out.splitlines()
    assert table[0] == f"Run {SESSION} (UTC day {_today()})"
    assert table[1].split() == [
        "SEAT",
        "ATTEMPT",
        "MODEL",
        "INPUT",
        "CEILING",
        "CANDIDATE",
        "DELTA",
        "OVERFLOW",
        "TRIMMABLE",
        "FEASIBLE",
        "FREED",
    ]
    assert table[2].split()[:2] == ["skald_writer", "1"]
    assert table[2].split()[6:] == ["-15000", "14500", "34000", "yes", "0"]


@pytest.mark.parametrize(
    ("extra", "message"),
    (
        (["--run", "missing-run"], "No prompt window records for run 'missing-run'"),
        (["--run", SESSION, "--day", "2026-2-3"], "Usage day must be YYYY-MM-DD"),
    ),
)
def test_cli_window_replay_input_errors_are_concise(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
    message: str,
) -> None:
    """A wrong run or day exits 1 with one line, not a traceback."""
    argv = ["nexus", "--json", "window-replay", "--config", str(REPO_CONFIG)]
    monkeypatch.setattr(sys, "argv", [*argv, *extra])
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"].startswith(message)
    assert "Traceback" not in captured.err

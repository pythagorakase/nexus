"""Real configuration, rendering, and tokenizer proofs for seat window truth."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from nexus.config import load_settings, load_settings_as_dict
from nexus.config.seat_window import resolve_seat_window
from nexus.config.settings_models import APIModelEntry
from nexus.config.story_model import StorySettings, resolve_story_model
from nexus.memory.manager import pass2_baseline_config_fingerprint
from nexus.telemetry.prompt_window import measure_blocks
from tests.test_lore.window_helpers import window_logon


def test_registry_requires_complete_capabilities_and_explicit_overlap():
    declaration = dict(
        id="declared",
        label="Declared",
        context_window=100,
        max_input_tokens=80,
        max_output_tokens=30,
        reasoning_accounting="inside_output",
    )
    with pytest.raises(ValidationError, match="exceeds context_window"):
        APIModelEntry.model_validate(declaration)
    assert APIModelEntry.model_validate(
        dict(declaration, allows_overlapping_limits=True)
    )
    declaration.pop("reasoning_accounting")
    with pytest.raises(ValidationError, match="complete window"):
        APIModelEntry.model_validate(declaration)
    with pytest.raises(ValueError, match="without complete"):
        APIModelEntry(id="missing", label="Missing").require_window_capabilities()


def test_inside_output_reasoning_does_not_shrink_input_twice():
    settings = load_settings_as_dict()
    model = settings["apex"]["model"]
    before = resolve_seat_window(settings, model, seat="skald_writer", window=75000)
    settings["apex"]["reasoning_reserve_tokens"] = 0
    after = resolve_seat_window(settings, model, seat="skald_writer", window=75000)
    assert before.input_ceiling == after.input_ceiling == 71000
    assert before.max_output_tokens == 25000


def test_story_window_above_declared_input_ceiling_names_both_limits():
    settings = load_settings()
    model = settings.apex.model
    maximum = settings.model_entry(model).max_input_tokens
    with pytest.raises(ValueError, match=f"{maximum + 1}.*{maximum}"):
        resolve_story_model(
            "skald",
            settings=settings,
            story=StorySettings(skald_model=model, apex_context_window=maximum + 1),
        )


def test_model_and_seat_policy_do_not_change_stamped_memory_fingerprint():
    settings = load_settings_as_dict()
    original = pass2_baseline_config_fingerprint(settings)
    changed = deepcopy(settings)
    changed["apex"]["response_reserve_tokens"] += 1
    changed["global"]["model"]["api_models"]["openai"]["models"][0][
        "context_window"
    ] += 1
    assert pass2_baseline_config_fingerprint(changed) == original


def test_rendered_blocks_sum_to_exact_request_and_ignore_payload_metadata():
    utility = window_logon()
    payload = {
        "user_input": "Continue.",
        "warm_slice": {
            "chunks": [{"chunk_id": 1, "text": "The door opens.", "is_target": True}]
        },
        "retrieved_passages": {"results": []},
        "entity_data": {},
    }
    first, window, blocks, count = utility.measure_writer_request(payload, 75000)
    counts, total = measure_blocks(blocks, count)
    assert total == first == sum(counts.values())
    assert "system" in counts and "recent narrative" in counts
    payload["memory_state"] = {"diagnostic_only": "irrelevant " * 100000}
    assert utility.measure_writer_request(payload, 75000)[0] == first
    utility._enforce_final_prompt_window(
        "unused", effective_context_window=first, rendered_tokens=first
    )
    with pytest.raises(ValueError, match="exceeds the effective"):
        utility._enforce_final_prompt_window(
            "unused", effective_context_window=first - 1, rendered_tokens=first
        )


def test_usage_window_ledger_preserves_attempts_and_cli_blocks(tmp_path, capsys):
    """Real append/read and CLI rendering retain per-attempt block truth."""
    from argparse import Namespace
    from datetime import datetime, timezone
    from nexus import cli
    from nexus.telemetry.prompt_window import PromptWindowRecord
    from nexus.telemetry.usage import record_prompt_window, read_prompt_windows

    record = PromptWindowRecord(
        generation_session="window-cli-proof",
        seat="skald_writer",
        attempt=1,
        model="TEST",
        block_tokens={"system": 20, "user input": 5},
        input_tokens=25,
        effective_ceiling=100,
        policy_headroom=4,
        headroom=75,
        trimming={"dropped_chunk_ids": [7], "tokens_recovered": 10},
    )
    record_prompt_window(record)
    record_prompt_window(record.model_copy(update={"attempt": 2}))
    day = datetime.now(timezone.utc).date().isoformat()
    assert [row.attempt for row in read_prompt_windows("window-cli-proof", day)] == [
        1,
        2,
    ]
    assert read_prompt_windows("unrelated", day) == []
    result = cli.run_usage(Namespace(day=day, run="window-cli-proof"))
    cli._print_usage(result)
    output = capsys.readouterr().out
    assert "skald_writer attempt 2: 25 / 100 (headroom 75)" in output
    assert "BLOCK" in output and "user input" in output

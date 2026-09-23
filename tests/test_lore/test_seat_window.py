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
    policy = resolve_seat_window(
        settings.model_dump(),
        model,
        seat="skald_writer",
        window=settings.model_entry(model).context_window,
    )
    maximum = policy.input_ceiling + policy.policy_headroom
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


def test_total_only_models_reserve_seat_output_not_provider_maximum():
    """Every OpenRouter model can use the owner's normal 75K input spend."""
    settings = load_settings_as_dict()
    for entry in settings["global"]["model"]["api_models"]["openrouter"]["models"]:
        assert entry["max_input_tokens"] is None
        window = resolve_seat_window(
            settings, entry["id"], seat="skald_writer", window=75000
        )
        assert window.input_ceiling == 71000
        window = resolve_seat_window(
            settings, entry["id"], seat="skald_writer", window=entry["context_window"]
        )
        assert (
            window.input_ceiling + window.policy_headroom
            == entry["context_window"] - settings["apex"]["max_output_tokens"]
        )


def test_documented_input_limit_and_total_only_declarations():
    """Both supported capability forms validate without inventing an input cap."""
    total_only = dict(
        id="fixture",
        label="Fixture",
        context_window=100,
        max_output_tokens=90,
        reasoning_accounting="none",
    )
    assert APIModelEntry.model_validate(total_only).max_input_tokens is None
    assert APIModelEntry.model_validate(dict(total_only, max_input_tokens=10))
    with pytest.raises(ValidationError, match="exceeds context_window"):
        APIModelEntry.model_validate(dict(total_only, max_input_tokens=20))
    with pytest.raises(ValidationError, match="complete window"):
        APIModelEntry.model_validate(
            dict(id="partial", label="Partial", max_input_tokens=50)
        )


def test_local_serving_window_is_the_supervisor_window():
    """A 32K deployment cannot admit 28K input plus a 25K completion."""
    from nexus.config.local_window import (
        serving_context_window,
        validate_reported_context,
    )
    from nexus.config.settings_models import Settings

    settings = load_settings().model_dump()
    command = settings["runtime"]["services"]["llama_server"]["command"]
    command[command.index("--ctx-size") + 1] = "32768"
    validated = Settings.model_validate(settings)
    model = validated.local_models.model
    window = resolve_seat_window(
        validated.model_dump(), model, seat="skald_writer", window=32000
    )
    assert window.input_ceiling == 3768
    assert (
        window.input_ceiling + window.policy_headroom + window.max_output_tokens
        == 32768
    )
    validate_reported_context({"default_generation_settings": {"n_ctx": 32768}}, 32768)
    with pytest.raises(ValueError, match="98304.*32768"):
        validate_reported_context(
            {"default_generation_settings": {"n_ctx": 98304}}, 32768
        )
    with pytest.raises(ValueError, match="n_ctx=None"):
        validate_reported_context({}, 32768)
    with pytest.raises(ValueError, match="explicit positive"):
        serving_context_window(["llama-server", "--ctx-size", "0"])
    command[command.index("--ctx-size") + 1] = str(
        validated.model_entry(model).context_window + 1
    )
    with pytest.raises(ValidationError, match="architectural window"):
        Settings.model_validate(settings)


def test_local_block_accounting_reuses_counts_and_subtracts_without_rendering():
    """The actual tokenizer runs once per distinct block, even after trimming."""
    from nexus.telemetry.prompt_window import (
        AssemblyRequest,
        LocalRequestCounter,
        local_text_counter,
    )

    settings = load_settings()
    count = local_text_counter(settings.model_entry(settings.apex.model))
    chunk = {"chunk_id": 42}
    budget = resolve_seat_window(
        settings.model_dump(), settings.apex.model, seat="skald_writer", window=75000
    )
    request = AssemblyRequest(
        budget,
        [("recent narrative", " A passage."), ("instructions", " Continue.")],
        {0: id(chunk)},
        LocalRequestCounter(count, 100),
    )
    before = request.tokens
    misses = count.cache_info().misses
    counts, _ = measure_blocks(request.blocks, request.counter)
    assert count.cache_info().misses == misses
    request.drop(chunk, "recent narrative")
    assert request.tokens == before - counts["recent narrative"]
    assert count.cache_info().misses == misses


def test_shared_trim_reserves_maximal_writer_response_for_gaia():
    """Real seat renderers fit a full-sized writer response at the shared boundary."""
    from types import SimpleNamespace
    from nexus.agents.logon.skald_wire import SkaldWriterWire
    from nexus.agents.lore.utils.turn_context import TurnContext
    from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
    from nexus.memory import ContextMemoryManager
    from nexus.telemetry.prompt_window import rendered_request_counter

    settings = load_settings_as_dict()
    logon = window_logon(settings)
    payload = {
        "user_input": "Continue.",
        "warm_slice": {
            "chunks": [
                {"chunk_id": 1, "text": " Earlier." * 60000},
                {"chunk_id": 2, "text": " Now.", "is_target": True},
            ]
        },
        "retrieved_passages": {"results": []},
        "entity_data": {},
    }
    ctx = TurnContext(turn_id="both-seats", user_input="Continue.", start_time=0)
    ctx.context_payload = payload
    ctx.token_counts = {"total_available": 71000, "apex_window": 75000}
    manager = TurnCycleManager(
        SimpleNamespace(
            settings=settings,
            logon=logon,
            memory_manager=ContextMemoryManager(settings),
            memnon=None,
            token_manager=None,
        )
    )
    manager._enforce_context_payload_budget(ctx)
    writer, gaia = logon._assembly_window_requests
    assert gaia.reserved_output == settings["apex"]["max_output_tokens"]
    assert writer.tokens <= writer.target and gaia.tokens <= gaia.target
    # Fill the remaining shared capacity using a one-token-per-repeat string.
    count = writer.counter.text_count
    parent = payload["warm_slice"]["chunks"][0]
    parent["text"] += " X" * (gaia.target - gaia.tokens)
    writer, gaia = logon.measure_turn_requests(payload, 75000)
    assert gaia.tokens == gaia.target
    output = SkaldWriterWire(
        narrative="X", choices=["Go.", "Wait."], letter="Continue."
    )
    cost = count(output.model_dump_json())
    output.narrative += " X" * (writer.budget.max_output_tokens - cost)
    assert count(output.model_dump_json()) == writer.budget.max_output_tokens
    turn_prompt = logon._format_context_prompt(
        payload, seat="gaia", include_ambient_scene_seeds=False
    )
    gaia_prompt = logon._format_gaia_user_prompt(turn_prompt, output)
    provider = logon._clone_provider_for_two_pass(
        system_prompt=logon._gaia_system_prompt(),
        output_validator=None,
        usage_seat="gaia",
        anthropic_transport=None,
    )
    exact = rendered_request_counter(provider)(gaia_prompt)
    logon._enforce_final_prompt_window(
        gaia_prompt,
        effective_context_window=gaia.budget.input_ceiling,
        rendered_tokens=exact,
    )
    assert exact <= gaia.budget.input_ceiling


def test_exact_ledger_separates_system_text_from_schema_estimates():
    """The ledger reconciles against measured system text, not estimated schema."""
    from nexus.telemetry.prompt_window import LocalRequestCounter, local_text_counter

    settings = load_settings()
    count = local_text_counter(settings.model_entry(settings.apex.model))
    system = count("System instructions.")
    blocks = [("user input", "Continue.")]
    counter = LocalRequestCounter(count, system + 1000, system_tokens=system)
    exact = system + count("Continue.") + 200
    counts, total = measure_blocks(blocks, counter, exact_total=exact)
    assert counts == {
        "system": system,
        "user input": count("Continue."),
        "request framing": 200,
    }
    assert total == exact == sum(counts.values())


def test_trim_subtracts_only_the_removed_appearance_of_a_shared_chunk():
    """A passage reused in two sections must retain its other rendered cost."""
    from nexus.telemetry.prompt_window import (
        AssemblyRequest,
        LocalRequestCounter,
        local_text_counter,
    )

    settings = load_settings()
    count = local_text_counter(settings.model_entry(settings.apex.model))
    chunk = {"chunk_id": 42}
    budget = resolve_seat_window(
        settings.model_dump(), settings.apex.model, seat="skald_writer", window=75000
    )
    request = AssemblyRequest(
        budget,
        [
            ("recent narrative", " A passage."),
            ("historical context", " Again: a passage."),
        ],
        {0: id(chunk), 1: id(chunk)},
        LocalRequestCounter(count, 100),
    )
    request.drop(chunk, "recent narrative")
    assert request.removed == {0}
    assert request.tokens == 100 + count(" Again: a passage.")
    request.drop(chunk, "historical context")
    assert request.tokens == 100

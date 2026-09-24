"""Historical caps and ranked trimming through the real TEST renderer."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.config import load_settings_as_dict
from nexus.config.settings_models import RenderLimits
from nexus.memory import ContextMemoryManager
from tests.test_lore.window_helpers import window_logon


@pytest.mark.parametrize("seat", ["writer", "gaia"])
@pytest.mark.parametrize("limit", [1, 5, 15])
def test_historical_render_limit_preserves_passages(seat: str, limit: int) -> None:
    """Only the configured prefix prints, with unchanged passage formatting."""
    settings = load_settings_as_dict()
    settings["lore"]["render_limits"]["historical_passages"] = limit
    utility = window_logon(settings)
    passages = [
        {"chunk_id": i, "text": f"Passage {i}.", "score": 1 - i / 100}
        for i in range(1, 17)
    ]
    prompt = utility._format_context_prompt(
        {"retrieved_passages": {"results": passages}}, seat=seat
    )
    for passage in passages:
        expected = (
            f"[Chunk {passage['chunk_id']} | Score: {passage['score']:.2f}] "
            f"{passage['text']}"
        )
        assert (expected in prompt) is (passage["chunk_id"] <= limit)


def test_historical_render_limit_validation() -> None:
    """The typed default matches retrieval k and rejects nonpositive caps."""
    settings = load_settings_as_dict()
    limits = settings["lore"]["render_limits"]
    assert RenderLimits.model_validate(limits).historical_passages == 15
    limits.pop("historical_passages")
    assert RenderLimits.model_validate(limits).historical_passages == 15
    for value in (0, -1):
        with pytest.raises(ValidationError, match="historical_passages"):
            RenderLimits.model_validate(dict(limits, historical_passages=value))


def test_historical_window_trims_lowest_ranked_first() -> None:
    """Subtractive costs agree with rerendering after removing the ranked tail."""
    settings = load_settings_as_dict()
    utility = window_logon(settings)
    passages = [
        {"chunk_id": i, "text": " Passage." * 2500, "score": 1 - i / 100}
        for i in range(1, 16)
    ]
    payload = {
        "user_input": "Recall.",
        "warm_slice": {"chunks": []},
        "retrieved_passages": {"results": passages},
        "entity_data": {},
    }
    context = TurnContext(turn_id="historical-trim", user_input="Recall.", start_time=0)
    context.context_payload = payload
    context.token_counts = {"total_available": 71000, "apex_window": 75000}
    cycle = TurnCycleManager(
        SimpleNamespace(
            settings=settings,
            logon=utility,
            memory_manager=ContextMemoryManager(settings),
        )
    )
    cycle._enforce_context_payload_budget(context)
    kept = payload["retrieved_passages"]["results"]
    assert 5 < len(kept) < 15
    assert kept == passages[: len(kept)]
    assert payload["window_trimming"]["dropped_chunk_ids"] == list(
        range(15, len(kept), -1)
    )
    fresh = utility.measure_turn_requests(payload, 75000)
    for request, rerendered in zip(utility._assembly_window_requests, fresh):
        assert request.tokens == rerendered.tokens
        assert request.tokens <= request.target

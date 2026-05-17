"""Tests for Orrery Bleed selector."""

from __future__ import annotations

from decimal import Decimal
import time

import pytest

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.bleed import (
    BleedSelection,
    load_bleed_candidates,
    select_bleed_menu_async,
)


class FakeResult:
    """Tiny SQLAlchemy result stand-in."""

    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """Session stand-in keyed by Bleed selector SQL markers."""

    def __init__(self, candidate_rows=None, max_chunk_id=100):
        self.candidate_rows = candidate_rows or []
        self.max_chunk_id = max_chunk_id
        self.executed = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append((sql, params))
        if "/* orrery:bleed_candidates */" in sql:
            assert "r.tick_chunk_id <= :anchor_chunk_id" in sql
            assert "r.offer_count < 3" in sql
            return FakeResult(self.candidate_rows)
        if "/* orrery:record_bleed_offers */" in sql:
            return FakeResult([])
        if "SELECT max(id) AS max_id" in sql:
            return FakeResult([{"max_id": self.max_chunk_id}])
        raise AssertionError(f"Unexpected Bleed query: {sql}")

    def commit(self):
        self.commits += 1


class FakeLLM:
    """Local LLM stand-in returning one Bleed selection."""

    def __init__(self, selection):
        self.selection = selection
        self.prompts = []

    def structured_query(self, prompt, response_model, **_kwargs):
        self.prompts.append((prompt, response_model))
        return self.selection


class SlowLLM(FakeLLM):
    """Local LLM stand-in that exceeds the latency budget."""

    def structured_query(self, prompt, response_model, **kwargs):
        time.sleep(0.05)
        return super().structured_query(prompt, response_model, **kwargs)


class FakeMemnon:
    """Minimal MEMNON stand-in exposing the Session factory."""

    def __init__(self, session):
        self.session = session

    def Session(self):
        return self.session


class FakeLore:
    """Minimal LORE stand-in for TurnCycleManager tests."""

    token_manager = None

    def __init__(self, settings, session, llm_manager):
        self.settings = settings
        self.memnon = FakeMemnon(session)
        self.llm_manager = llm_manager


def _candidate_row():
    return {
        "resolution_id": 10,
        "narration_id": 501,
        "tick_chunk_id": 99,
        "template_id": "evade_pursuers",
        "event_type": "evade_pursuit",
        "actor_name": "Mara",
        "target_name": None,
        "perceptual_descriptor": {
            "channel": "digital",
            "summary": "street cameras briefly lose Mara",
            "brief": "Mara vanishes into a maintenance corridor.",
        },
        "brief": "Mara vanishes into a maintenance corridor.",
        "text": "Mara drops below the platform and vanishes from the cameras.",
        "magnitude": Decimal("0.720"),
    }


def _settings():
    return {
        "orrery": {
            "enabled": True,
            "bleed": {
                "latency_budget_ms": 2000,
                "max_candidates": 3,
            },
        }
    }


def test_load_bleed_candidates_coerces_descriptor() -> None:
    """Candidate loading keeps the Storyteller-facing descriptor separate."""

    candidates = load_bleed_candidates(
        FakeSession(candidate_rows=[_candidate_row()]),
        anchor_chunk_id=100,
        limit=3,
    )

    assert len(candidates) == 1
    assert candidates[0].resolution_id == 10
    assert candidates[0].channel == "digital"
    assert candidates[0].summary == "street cameras briefly lose Mara"
    assert candidates[0].magnitude == 0.72


@pytest.mark.asyncio
async def test_select_bleed_menu_records_selected_offers() -> None:
    """Selected ambient candidates update surfacing bookkeeping."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    llm = FakeLLM(BleedSelection(selected_resolution_ids=[10], reasoning="apt"))

    result = await select_bleed_menu_async(
        session,
        llm_manager=llm,
        anchor_chunk_id=100,
        user_input="Continue.",
        warm_slice=[{"text": "Rain ticks against the transit glass."}],
        max_candidates=3,
        latency_budget_ms=2000,
    )

    update_params = next(
        params
        for sql, params in session.executed
        if "/* orrery:record_bleed_offers */" in sql
    )

    assert result.candidates_considered == 1
    assert result.selected[0].resolution_id == 10
    assert session.commits == 1
    assert update_params["resolution_ids"] == [10]


@pytest.mark.asyncio
async def test_select_bleed_menu_returns_empty_without_candidates() -> None:
    """No candidates means no local LLM call and no bookkeeping writes."""

    session = FakeSession(candidate_rows=[])
    llm = FakeLLM(BleedSelection(selected_resolution_ids=[10], reasoning="unused"))

    result = await select_bleed_menu_async(
        session,
        llm_manager=llm,
        anchor_chunk_id=100,
        user_input="Continue.",
        warm_slice=[],
        max_candidates=3,
        latency_budget_ms=2000,
    )

    assert result.candidates_considered == 0
    assert result.selected == []
    assert llm.prompts == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_select_bleed_menu_timeout_returns_empty() -> None:
    """Latency overruns produce an empty menu and no offer bookkeeping."""

    session = FakeSession(candidate_rows=[_candidate_row()])

    result = await select_bleed_menu_async(
        session,
        llm_manager=SlowLLM(BleedSelection(selected_resolution_ids=[10])),
        anchor_chunk_id=100,
        user_input="Continue.",
        warm_slice=[],
        max_candidates=3,
        latency_budget_ms=1,
    )

    assert result.timed_out is True
    assert result.selected == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_assemble_context_payload_includes_bleed_menu() -> None:
    """LORE payload assembly injects selected ambient Orrery peripherals."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    manager = TurnCycleManager(
        FakeLore(
            _settings(),
            session,
            FakeLLM(BleedSelection(selected_resolution_ids=[10], reasoning="apt")),
        )
    )
    context = TurnContext(
        turn_id="t1",
        user_input="Continue.",
        start_time=0,
        warm_slice=[{"id": 100, "text": "Rain ticks against the glass."}],
    )

    await manager.assemble_context_payload(context)

    assert context.phase_states["orrery_bleed"]["selected_count"] == 1
    assert context.context_payload["orrery_bleed_menu"][0]["summary"] == (
        "street cameras briefly lose Mara"
    )

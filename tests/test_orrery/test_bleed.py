"""Tests for Orrery Bleed selector."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.bleed import (
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


class FakeMemnon:
    """Minimal MEMNON stand-in exposing the Session factory."""

    def __init__(self, session):
        self.session = session

    def Session(self):
        return self.session


class FakeStoryResponse:
    """Minimal structured response stand-in for LOGON."""

    narrative = "Rain ticks against the glass."
    chunk_metadata = None
    referenced_entities = None
    state_updates = None


class FakeLogon:
    """LOGON stand-in returning a successful structured narrative."""

    async def generate_narrative_async(self, _payload):
        return FakeStoryResponse()


class FailingLogon:
    """LOGON stand-in that raises before a response is surfaced."""

    async def generate_narrative_async(self, _payload):
        raise RuntimeError("generation failed")


class FakeLore:
    """Minimal LORE stand-in for TurnCycleManager tests."""

    token_manager = None
    enable_logon = True

    def __init__(self, settings, session, logon=None):
        self.settings = settings
        self.memnon = FakeMemnon(session)
        self.llm_manager = None
        self.logon = logon or FakeLogon()

    def ensure_logon(self):
        return None

    def _ensure_local_llm_manager(self):
        raise AssertionError("Orrery Bleed must not initialize a local LLM")


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


def _candidate_row_with_id(resolution_id: int):
    row = dict(_candidate_row())
    row["resolution_id"] = resolution_id
    row["narration_id"] = 500 + resolution_id
    return row


def _settings():
    return {
        "orrery": {
            "enabled": True,
            "bleed": {
                "max_candidates": 3,
                "candidate_pool_multiplier": 4,
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
async def test_select_bleed_menu_returns_top_candidate_without_recording_offers() -> (
    None
):
    """Selection is pure; offer bookkeeping waits until generation succeeds."""

    session = FakeSession(candidate_rows=[_candidate_row()])

    result = await select_bleed_menu_async(
        session,
        anchor_chunk_id=100,
        max_candidates=3,
        candidate_pool_multiplier=4,
    )

    assert result.candidates_considered == 1
    assert result.selected[0].resolution_id == 10
    assert session.commits == 0
    assert not any(
        "/* orrery:record_bleed_offers */" in sql for sql, _ in session.executed
    )


@pytest.mark.asyncio
async def test_select_bleed_menu_returns_empty_without_candidates() -> None:
    """No candidates means no bookkeeping writes."""

    session = FakeSession(candidate_rows=[])

    result = await select_bleed_menu_async(
        session,
        anchor_chunk_id=100,
        max_candidates=3,
        candidate_pool_multiplier=4,
    )

    assert result.candidates_considered == 0
    assert result.selected == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_select_bleed_menu_caps_deterministic_selection() -> None:
    """Deterministic Bleed preserves SQL ordering and max-candidate caps."""

    session = FakeSession(
        candidate_rows=[
            _candidate_row_with_id(10),
            _candidate_row_with_id(11),
        ]
    )

    result = await select_bleed_menu_async(
        session,
        anchor_chunk_id=100,
        max_candidates=1,
        candidate_pool_multiplier=4,
    )

    assert result.timed_out is False
    assert result.candidates_considered == 2
    assert [candidate.resolution_id for candidate in result.selected] == [10]
    assert session.commits == 0


@pytest.mark.asyncio
async def test_assemble_context_payload_includes_bleed_menu() -> None:
    """LORE payload assembly injects selected ambient Orrery peripherals."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    manager = TurnCycleManager(FakeLore(_settings(), session))
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


@pytest.mark.asyncio
async def test_assemble_context_payload_does_not_initialize_bleed_llm() -> None:
    """Orrery Bleed should not summon local inference during turn assembly."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    lore = FakeLore(_settings(), session)
    manager = TurnCycleManager(lore)
    context = TurnContext(
        turn_id="t1",
        user_input="Continue.",
        start_time=0,
        warm_slice=[{"id": 100, "text": "Rain ticks against the glass."}],
    )

    await manager.assemble_context_payload(context)

    assert lore.llm_manager is None
    assert context.phase_states["orrery_bleed"]["selected_count"] == 1


@pytest.mark.asyncio
async def test_assemble_context_payload_reuses_orrery_proposal_anchor() -> None:
    """Bleed uses the existing resolve anchor instead of recomputing max chunk."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    manager = TurnCycleManager(FakeLore(_settings(), session))
    context = TurnContext(
        turn_id="t1",
        user_input="Continue.",
        start_time=0,
        warm_slice=[],
    )
    context.orrery_proposal = SimpleNamespace(anchor_chunk_id=77, pressure_count=0)

    await manager.assemble_context_payload(context)

    candidate_params = next(
        params
        for sql, params in session.executed
        if "/* orrery:bleed_candidates */" in sql
    )
    assert candidate_params["anchor_chunk_id"] == 77
    assert not any("SELECT max(id) AS max_id" in sql for sql, _ in session.executed)


@pytest.mark.asyncio
async def test_call_apex_ai_records_bleed_offers_after_generation_success() -> None:
    """Surfacing bookkeeping is written only after LOGON returns a response."""

    session = FakeSession()
    manager = TurnCycleManager(FakeLore(_settings(), session, logon=FakeLogon()))
    context = TurnContext(turn_id="t1", user_input="Continue.", start_time=0)
    context.context_payload = {"user_input": "Continue."}
    context.bleed_menu = load_bleed_candidates(
        FakeSession(candidate_rows=[_candidate_row()]),
        anchor_chunk_id=100,
        limit=1,
    )
    context.phase_states["orrery_bleed"] = {
        "anchor_chunk_id": 100,
        "offers_recorded": 0,
    }

    response = await manager.call_apex_ai(context)
    update_params = next(
        params
        for sql, params in session.executed
        if "/* orrery:record_bleed_offers */" in sql
    )

    assert response.narrative == "Rain ticks against the glass."
    assert session.commits == 1
    assert update_params["resolution_ids"] == [10]
    assert context.phase_states["orrery_bleed"]["offers_recorded"] == 1


@pytest.mark.asyncio
async def test_call_apex_ai_does_not_record_bleed_offers_on_generation_failure() -> (
    None
):
    """Failed LOGON generation does not consume a Bleed opportunity."""

    session = FakeSession()
    manager = TurnCycleManager(FakeLore(_settings(), session, logon=FailingLogon()))
    context = TurnContext(turn_id="t1", user_input="Continue.", start_time=0)
    context.context_payload = {"user_input": "Continue."}
    context.bleed_menu = load_bleed_candidates(
        FakeSession(candidate_rows=[_candidate_row()]),
        anchor_chunk_id=100,
        limit=1,
    )
    context.phase_states["orrery_bleed"] = {
        "anchor_chunk_id": 100,
        "offers_recorded": 0,
    }

    with pytest.raises(RuntimeError, match="generation failed"):
        await manager.call_apex_ai(context)

    assert session.commits == 0
    assert not any(
        "/* orrery:record_bleed_offers */" in sql for sql, _ in session.executed
    )

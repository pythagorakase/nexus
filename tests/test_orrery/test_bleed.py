"""Tests for Orrery Bleed selector."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.bleed import (
    assemble_bleed_proximity_graph,
    load_bleed_candidates,
    select_bleed_menu,
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

    def __init__(
        self,
        candidate_rows=None,
        max_chunk_id=100,
        anchor_entity_rows=None,
        graph_nodes=None,
        graph_edges=None,
    ):
        self.candidate_rows = candidate_rows or []
        self.max_chunk_id = max_chunk_id
        self.anchor_entity_rows = anchor_entity_rows or []
        self.graph_nodes = graph_nodes or []
        self.graph_edges = graph_edges or []
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
            limit = params.get("limit")
            rows = self.candidate_rows if limit is None else self.candidate_rows[:limit]
            return FakeResult(rows)
        if "/* orrery:bleed_anchor_entities */" in sql:
            return FakeResult(self.anchor_entity_rows)
        if "/* orrery:bleed_proximity_nodes */" in sql:
            return FakeResult(self.graph_nodes)
        if "/* orrery:bleed_proximity_edges */" in sql:
            assert "cr.relationship_type" in sql
            assert "ept.cleared_at IS NULL" in sql
            assert "pt.tag LIKE 'status:%'" in sql
            assert "'hunting'" in sql
            return FakeResult(self.graph_edges)
        if "/* orrery:record_bleed_offers */" in sql:
            return FakeResult([])
        if "SELECT max(nc.id) AS max_id" in sql:
            assert "orrery:retrograde_prologue_anchor" in sql
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
    generation_model = "resolved-bleed-test-model"
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
        self.logon = logon or FakeLogon()

    def ensure_logon(self):
        return None


def _candidate_row():
    return {
        "resolution_id": 10,
        "narration_id": 501,
        "tick_chunk_id": 99,
        "template_id": "evade_pursuers",
        "actor_entity_id": 2,
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


def _select(
    session: FakeSession,
    *,
    anchor_entity_ids=(1,),
    max_candidates=3,
    near_distance_max=2,
    reserved_remote_slots=1,
    scan_limit=24,
):
    return select_bleed_menu(
        session,
        anchor_chunk_id=100,
        anchor_entity_ids=anchor_entity_ids,
        max_candidates=max_candidates,
        near_distance_max=near_distance_max,
        reserved_remote_slots=reserved_remote_slots,
        scan_limit=scan_limit,
    )


def _settings():
    return {
        "orrery": {
            "enabled": True,
            "bleed": {
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


def test_select_bleed_menu_returns_top_candidate_without_recording_offers() -> None:
    """Selection is pure; offer bookkeeping waits until generation succeeds."""

    session = FakeSession(candidate_rows=[_candidate_row()])

    result = _select(session, anchor_entity_ids=())

    assert result.candidates_considered == 1
    assert result.selected[0].resolution_id == 10
    assert session.commits == 0
    assert not any(
        "/* orrery:record_bleed_offers */" in sql for sql, _ in session.executed
    )


def test_select_bleed_menu_returns_empty_without_candidates() -> None:
    """No candidates means no bookkeeping writes."""

    session = FakeSession(candidate_rows=[])

    result = _select(session, anchor_entity_ids=())

    assert result.candidates_considered == 0
    assert result.selected == []
    assert session.commits == 0


def test_select_bleed_menu_caps_deterministic_selection() -> None:
    """Deterministic Bleed preserves SQL ordering and max-candidate caps."""

    session = FakeSession(
        candidate_rows=[
            _candidate_row_with_id(10),
            _candidate_row_with_id(11),
        ]
    )

    result = _select(
        session,
        anchor_entity_ids=(),
        max_candidates=1,
        reserved_remote_slots=0,
    )

    # Empty-anchor fallback fetches capped (limit = max_candidates), restoring
    # the pre-Stage-3 contract: candidates_considered reports the capped fetch.
    assert result.candidates_considered == 1
    assert [candidate.resolution_id for candidate in result.selected] == [10]
    assert session.commits == 0


def test_bleed_proximity_graph_is_undirected_and_deterministic() -> None:
    """Relationship and permitted pair-tag rows become stable neutral hops."""

    session = FakeSession(
        graph_nodes=[{"entity_id": 3}, {"entity_id": 1}, {"entity_id": 2}],
        graph_edges=[
            {
                "source_entity_id": 2,
                "target_entity_id": 3,
                "edge_kind": "pair_tag",
                "edge_label": "hunting",
            },
            {
                "source_entity_id": 2,
                "target_entity_id": 1,
                "edge_kind": "relationship",
                "edge_label": "enemy",
            },
        ],
    )

    graph = assemble_bleed_proximity_graph(session)

    assert graph.nodes == (1, 2, 3)
    assert graph.adjacency == {1: (2,), 2: (1, 3), 3: (2,)}
    assert graph.distances_from((3, 1)) == {1: 0, 3: 0, 2: 1}


def test_select_bleed_menu_reserves_remote_slot_after_near_candidates() -> None:
    """A lower-magnitude near candidate leads while remote keeps its slot."""

    remote = _candidate_row_with_id(30)
    remote["actor_entity_id"] = 30
    near = _candidate_row_with_id(20)
    near["actor_entity_id"] = 2
    near["magnitude"] = Decimal("0.100")
    session = FakeSession(
        candidate_rows=[remote, near],
        graph_nodes=[{"entity_id": 1}, {"entity_id": 2}, {"entity_id": 30}],
        graph_edges=[
            {
                "source_entity_id": 1,
                "target_entity_id": 2,
                "edge_kind": "relationship",
                "edge_label": "associate",
            }
        ],
    )

    result = _select(session, max_candidates=2)

    assert [candidate.resolution_id for candidate in result.selected] == [20, 30]
    assert [candidate.distance for candidate in result.selected] == [1, None]
    assert result.near_count == 1
    assert result.remote_count == 1


def test_reserved_remote_zero_makes_starvation_a_config_choice() -> None:
    """With enough near rows, a zero reservation excludes the remote leader."""

    rows = []
    for resolution_id, actor_id in ((30, 30), (20, 2), (10, 3)):
        row = _candidate_row_with_id(resolution_id)
        row["actor_entity_id"] = actor_id
        rows.append(row)
    session = FakeSession(
        candidate_rows=rows,
        graph_nodes=[{"entity_id": entity_id} for entity_id in (1, 2, 3, 30)],
        graph_edges=[
            {
                "source_entity_id": 1,
                "target_entity_id": actor_id,
                "edge_kind": "relationship",
                "edge_label": "associate",
            }
            for actor_id in (2, 3)
        ],
    )

    result = _select(
        session,
        max_candidates=2,
        reserved_remote_slots=0,
    )

    assert [candidate.resolution_id for candidate in result.selected] == [20, 10]
    assert result.near_count == 2
    assert result.remote_count == 0


def test_faction_anchor_reaches_candidate_over_hunting_edge() -> None:
    """A permitted character-faction pair tag makes the actor near."""

    row = _candidate_row()
    row["actor_entity_id"] = 2
    session = FakeSession(
        candidate_rows=[row],
        graph_nodes=[{"entity_id": 2}, {"entity_id": 9}],
        graph_edges=[
            {
                "source_entity_id": 2,
                "target_entity_id": 9,
                "edge_kind": "pair_tag",
                "edge_label": "hunting",
            }
        ],
    )

    result = _select(session, anchor_entity_ids=(9,))

    assert result.selected[0].distance == 1
    assert result.near_count == 1


def test_empty_anchor_preserves_existing_order_without_graph_queries() -> None:
    """No on-screen references keeps the pre-proximity menu byte ordering."""

    rows = [_candidate_row_with_id(value) for value in (30, 20, 10)]
    session = FakeSession(candidate_rows=rows)

    before = [
        candidate.model_dump_json()
        for candidate in load_bleed_candidates(
            session,
            anchor_chunk_id=100,
            limit=2,
        )
    ]
    result = _select(session, anchor_entity_ids=(), max_candidates=2)

    assert [candidate.model_dump_json() for candidate in result.selected] == before
    assert not any("orrery:bleed_proximity" in sql for sql, _ in session.executed)


@pytest.mark.parametrize(
    ("anchor_entity_ids", "near_distance_max", "expected_ids", "counts"),
    [
        ((1,), 0, [30, 20, 10], (1, 2)),
        ((1, 2, 3), 2, [30, 20, 10], (3, 0)),
    ],
)
def test_select_bleed_menu_backfills_short_partition(
    anchor_entity_ids,
    near_distance_max,
    expected_ids,
    counts,
) -> None:
    """A short near or remote partition backfills without shrinking the menu."""

    rows = []
    for resolution_id, actor_id in ((30, 1), (20, 2), (10, 3)):
        row = _candidate_row_with_id(resolution_id)
        row["actor_entity_id"] = actor_id
        rows.append(row)
    session = FakeSession(
        candidate_rows=rows,
        graph_nodes=[{"entity_id": entity_id} for entity_id in (1, 2, 3)],
        graph_edges=[],
    )

    result = _select(
        session,
        anchor_entity_ids=anchor_entity_ids,
        max_candidates=3,
        near_distance_max=near_distance_max,
    )

    assert [candidate.resolution_id for candidate in result.selected] == expected_ids
    assert (result.near_count, result.remote_count) == counts


def test_select_bleed_menu_is_deterministic_with_tie_order() -> None:
    """Identical rows retain the SQL id tie-break across repeated selection."""

    rows = [_candidate_row_with_id(value) for value in (30, 20, 10)]
    for row, actor_id in zip(rows, (3, 2, 1), strict=True):
        row["actor_entity_id"] = actor_id
    session = FakeSession(
        candidate_rows=rows,
        graph_nodes=[{"entity_id": entity_id} for entity_id in (1, 2, 3)],
        graph_edges=[],
    )

    first = _select(session, max_candidates=2)
    second = _select(session, max_candidates=2)

    assert first == second
    candidate_sql = next(
        sql for sql, _ in session.executed if "orrery:bleed_candidates" in sql
    )
    assert "r.id DESC" in candidate_sql


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
    assert context.phase_states["orrery_bleed"]["near_count"] == 0
    assert context.phase_states["orrery_bleed"]["remote_count"] == 1
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

    assert not hasattr(lore, "llm_manager")
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
    assert not any("SELECT max(nc.id) AS max_id" in sql for sql, _ in session.executed)


@pytest.mark.asyncio
async def test_assemble_context_payload_attaches_scene_conditions() -> None:
    """The resolved anchor weather and time reach the Storyteller payload."""

    session = FakeSession()
    manager = TurnCycleManager(FakeLore(_settings(), session))
    context = TurnContext(
        turn_id="t1",
        user_input="Continue.",
        start_time=0,
        warm_slice=[],
    )
    context.orrery_proposal = SimpleNamespace(
        anchor_chunk_id=77,
        pressure_count=0,
        scene_conditions={"weather": "warm", "time_of_day": "afternoon"},
    )

    await manager.assemble_context_payload(context)

    assert context.context_payload["scene_conditions"] == {
        "weather": "warm",
        "time_of_day": "afternoon",
    }


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
    assert response.generation_model == "resolved-bleed-test-model"
    assert context.apex_response is response
    assert (
        context.phase_states["apex_generation"]["generation_model"]
        == "resolved-bleed-test-model"
    )
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

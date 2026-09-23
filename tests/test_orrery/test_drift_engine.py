"""Pure-planner coverage for deterministic relationship drift."""

from decimal import Decimal

import pytest

from nexus.agents.orrery.drift import (
    DriftEvent,
    ProjectMilestone,
    _require_migration_115_async,
    _require_migration_115_sync,
    plan_relationship_drift,
    soft_clamp_step,
)
from nexus.config.settings_models import OrreryDriftSettings


def _settings(**overrides: object) -> OrreryDriftSettings:
    payload: dict[str, object] = {
        "project_milestone_delta": "0.03",
        "hostile_events": {"hostile": "-0.2"},
        "cooperative_events": {"cooperative": "0.1"},
    }
    payload.update(overrides)
    return OrreryDriftSettings.model_validate(payload)


def test_each_discrete_producer_moves_both_existing_directions() -> None:
    relationships = {(1, 2): Decimal("0.2"), (2, 1): Decimal("-0.2")}

    milestone = plan_relationship_drift(
        relationships=relationships,
        project_milestones=[ProjectMilestone(4, 1, 2)],
        events=[],
        settings=_settings(),
    )
    hostile = plan_relationship_drift(
        relationships=relationships,
        project_milestones=[],
        events=[DriftEvent(8, "hostile", 1, 2)],
        settings=_settings(),
    )
    cooperative = plan_relationship_drift(
        relationships=relationships,
        project_milestones=[],
        events=[DriftEvent(9, "cooperative", 1, 2)],
        settings=_settings(),
    )

    assert [edge.new_valence for edge in milestone.edges] == [
        Decimal("0.224"),
        Decimal("-0.176"),
    ]
    assert [edge.new_valence for edge in hostile.edges] == [
        Decimal("0.04"),
        Decimal("-0.36"),
    ]
    assert [edge.new_valence for edge in cooperative.edges] == [
        Decimal("0.28"),
        Decimal("-0.12"),
    ]


def test_producers_apply_sequentially_in_frozen_order() -> None:
    settings = _settings()
    plan = plan_relationship_drift(
        relationships={(1, 2): Decimal("0.2")},
        project_milestones=[ProjectMilestone(20, 1, 2)],
        events=[
            DriftEvent(40, "cooperative", 1, 2),
            DriftEvent(30, "hostile", 1, 2),
        ],
        settings=settings,
    )
    value = Decimal("0.2")
    expected_deltas = []
    for delta in (
        Decimal("0.03"),
        Decimal("-0.2"),
        Decimal("0.1"),
    ):
        value, effective = soft_clamp_step(value, delta)
        expected_deltas.append(effective)

    edge = plan.edges[0]
    assert edge.new_valence == value
    assert [delta for _label, delta in edge.producer_deltas] == expected_deltas
    assert [label.split(":", 1)[0] for label, _delta in edge.producer_deltas] == [
        "project_milestone",
        "hostile",
        "cooperative",
    ]


def test_repeated_hostility_approaches_negative_one_without_reaching_it() -> None:
    events = [DriftEvent(event_id, "hostile", 1, 2) for event_id in range(1000)]
    plan = plan_relationship_drift(
        relationships={(1, 2): Decimal("0")},
        project_milestones=[],
        events=events,
        settings=_settings(),
    )

    value = plan.edges[0].new_valence
    assert value == Decimal("-0.999999999999")


def test_missing_reverse_edge_is_not_created() -> None:
    plan = plan_relationship_drift(
        relationships={(1, 2): Decimal("0.1")},
        project_milestones=[],
        events=[DriftEvent(1, "cooperative", 1, 2)],
        settings=_settings(),
    )

    assert [(edge.source_entity_id, edge.target_entity_id) for edge in plan.edges] == [
        (1, 2)
    ]


def test_decimal_plan_is_bit_exact_across_identical_runs() -> None:
    inputs = {
        "relationships": {(1, 2): Decimal("0.123456789")},
        "project_milestones": [ProjectMilestone(2, 1, 2)],
        "events": [
            DriftEvent(4, "hostile", 1, 2),
            DriftEvent(5, "cooperative", 1, 2),
        ],
        "settings": _settings(),
    }

    assert plan_relationship_drift(**inputs) == plan_relationship_drift(**inputs)


def test_written_valence_is_quantized_to_twelve_decimal_places() -> None:
    plan = plan_relationship_drift(
        relationships={(1, 2): Decimal("0.12345678901234567890")},
        project_milestones=[],
        events=[DriftEvent(1, "cooperative", 1, 2)],
        settings=_settings(),
    )

    edge = plan.edges[0]
    assert edge.old_valence == Decimal("0.123456789012")
    assert edge.new_valence == Decimal("0.211111110111")
    assert edge.new_valence.as_tuple().exponent == -12


class _MigrationGateCursor:
    def execute(self, _sql: str, _params: object) -> None:
        return None

    def fetchone(self) -> dict[str, int]:
        return {"registered_count": 1}


class _MigrationGateAsyncConnection:
    async def fetchval(self, _sql: str, _event_types: object) -> int:
        return 1


def test_sync_migration_gate_requires_both_drift_event_types() -> None:
    with pytest.raises(RuntimeError, match="migration 115"):
        _require_migration_115_sync(_MigrationGateCursor())


@pytest.mark.asyncio
async def test_async_migration_gate_requires_both_drift_event_types() -> None:
    with pytest.raises(RuntimeError, match="migration 115"):
        await _require_migration_115_async(_MigrationGateAsyncConnection())

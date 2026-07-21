"""Fast contract tests for the Stage 2c propagation drain."""

from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from nexus.agents.orrery.propagation import (
    _propagation_claim_identity,
    drain_claim_propagation_sync,
)
from nexus.agents.orrery.replay import _propagated_claim_identity
from nexus.config.settings_models import OrreryContagionSettings


class _Pre083Cursor:
    def execute(self, _sql: str, _params: Any = None) -> None:
        pass

    def fetchone(self) -> dict[str, bool]:
        return {"event_registered": False, "world_time_column": False}


def test_enabled_drain_requires_migration_083_before_any_write() -> None:
    """A pre-083 slot fails with the rollout instruction, not SQL fallout."""

    with pytest.raises(RuntimeError, match="apply migration 083"):
        drain_claim_propagation_sync(
            _Pre083Cursor(),
            tick_chunk_id=1,
            settings=OrreryContagionSettings(),
        )


def test_migration_083_indexes_depth_recovery_expression() -> None:
    migration = Path("migrations/083_claim_propagation_ledger.sql").read_text()

    assert "ix_world_events_claim_propagated_claim_id" in migration
    assert "((payload ->> 'claim_id')::bigint)" in migration
    assert "WHERE event_type = 'claim_propagated'" in migration
    assert "COMMENT ON INDEX ix_world_events_claim_propagated_claim_id" in migration


_STAGE_C_FIELDS = {
    "delivered_claim_id": 1,
    "incident_world_event_id": 2,
    "distortion_applied": False,
}
_PARTIAL_STAGE_C_FIELD_SETS = [
    subset
    for subset_size in (1, 2)
    for subset in combinations(_STAGE_C_FIELDS, subset_size)
]


@pytest.mark.parametrize(
    "validator",
    [_propagation_claim_identity, _propagated_claim_identity],
    ids=["frontier", "replay"],
)
@pytest.mark.parametrize(
    "present_fields",
    _PARTIAL_STAGE_C_FIELD_SETS,
    ids=lambda fields: "+".join(fields),
)
def test_partial_stage_c_identity_is_rejected_exhaustively(
    validator: Any,
    present_fields: tuple[str, ...],
) -> None:
    """Every non-empty proper Stage C subset fails in both read paths."""

    payload = {"claim_id": 1}
    payload.update({field: _STAGE_C_FIELDS[field] for field in present_fields})

    with pytest.raises(ValueError, match="lacks .*payload fields"):
        validator(payload, event_id=479)

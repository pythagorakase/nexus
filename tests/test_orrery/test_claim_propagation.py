"""Fast contract tests for the Stage 2c propagation drain."""

from pathlib import Path
from typing import Any

import pytest

from nexus.agents.orrery.propagation import drain_claim_propagation_sync
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

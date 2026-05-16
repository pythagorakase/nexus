"""Tests for narrative generation orchestration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from nexus.api import narrative_generation


class DummyProgressManager:
    """Capture progress events sent by narrative generation."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any] | None]] = []

    async def send_progress(
        self, session_id: str, status: str, data: dict[str, Any] | None = None
    ) -> None:
        """Record a progress event."""
        self.events.append((session_id, status, data))


class DummyConnection:
    """Minimal connection object for orchestration tests."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        """Record connection closure."""
        self.closed = True


@pytest.mark.asyncio
async def test_lore_phase_failure_is_reported_before_adapter_coercion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed LORE phase should not become a generic no-narrative error."""

    class FailingLore:
        """LORE double that mimics a warm-analysis failure return."""

        instances: list["FailingLore"] = []

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.turn_context = SimpleNamespace(
                error_log=[
                    "TurnPhase.WARM_ANALYSIS: FATAL: No warm slice chunks retrieved."
                ]
            )
            self.instances.append(self)

        async def process_turn(
            self,
            user_text: str,
            parent_chunk_id: int,
            note: str | None = None,
        ) -> str:
            """Return the legacy failure string from LORE.process_turn."""
            return "Error processing turn: FATAL: No warm slice chunks retrieved."

    async def fake_get_chunk_info(
        conn: DummyConnection, chunk_id: int
    ) -> dict[str, Any]:
        """Return enough parent metadata to reach LORE orchestration."""
        return {"season": 1, "episode": 1, "place_name": "Halcyon Row"}

    async def fail_write(*args: Any, **kwargs: Any) -> None:
        pytest.fail("write_to_incubator should not run after a LORE phase failure")

    monkeypatch.setattr(narrative_generation, "LORE", FailingLore)
    monkeypatch.setattr(narrative_generation, "get_chunk_info", fake_get_chunk_info)
    monkeypatch.setattr(narrative_generation, "write_to_incubator", fail_write)

    manager = DummyProgressManager()
    conn = DummyConnection()

    await narrative_generation.generate_narrative_async(
        session_id="session-1",
        parent_chunk_id=1,
        user_text="continue",
        slot=5,
        get_db_connection=lambda slot: conn,
        load_settings=lambda: {},
        manager=manager,
    )

    error_events = [event for event in manager.events if event[1] == "error"]
    assert len(error_events) == 1
    error_message = error_events[0][2]["error"]
    assert "TurnPhase.WARM_ANALYSIS" in error_message
    assert "FATAL: No warm slice chunks retrieved." in error_message
    assert "No narrative text in LORE response" not in error_message
    assert FailingLore.instances[0].kwargs["slot"] == 5
    assert conn.closed is True

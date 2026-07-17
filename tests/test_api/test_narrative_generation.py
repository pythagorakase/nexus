"""Tests for narrative generation orchestration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
    StorytellerResponseMinimal,
)
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

        def close(self) -> None:
            """Match LORE's per-turn teardown contract (issue #401)."""
            self.closed = True

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


@pytest.mark.asyncio
async def test_continuation_threads_logon_model_into_incubator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Continuation keeps the model stamped at the successful LOGON call."""

    class SuccessfulLore:
        """LORE double returning a provider-enriched storyteller response."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.turn_context = SimpleNamespace(error_log=[], orrery_proposal=None)

        async def process_turn(
            self,
            user_text: str,
            parent_chunk_id: int,
            note: str | None = None,
        ) -> StorytellerResponseMinimal:
            return StorytellerResponseMinimal(
                generation_model="resolved-provider-model",
                narrative="A train exhales beyond the wall.",
                choices=["Follow the sound.", "Stay hidden."],
            )

        def close(self) -> None:
            pass

    async def fake_get_chunk_info(
        conn: DummyConnection, chunk_id: int
    ) -> dict[str, Any]:
        return {"season": 1, "episode": 1, "place_name": "Halcyon Row"}

    written: list[dict[str, Any]] = []

    async def capture_write(conn: DummyConnection, data: dict[str, Any]) -> None:
        written.append(data)

    monkeypatch.setattr(narrative_generation, "LORE", SuccessfulLore)
    monkeypatch.setattr(narrative_generation, "get_chunk_info", fake_get_chunk_info)
    monkeypatch.setattr(narrative_generation, "write_to_incubator", capture_write)

    manager = DummyProgressManager()
    conn = DummyConnection()
    await narrative_generation.generate_narrative_async(
        session_id="session-provenance",
        parent_chunk_id=7,
        user_text="Continue.",
        slot=5,
        get_db_connection=lambda slot: conn,
        load_settings=lambda: {},
        manager=manager,
    )

    assert written[0]["generation_model"] == "resolved-provider-model"
    assert [status for _session, status, _data in manager.events][-1] == "complete"


@pytest.mark.asyncio
async def test_write_to_incubator_rejects_missing_generation_model() -> None:
    """The generation writer fails before touching the database without a stamp."""

    with pytest.raises(ValueError, match="missing its model id"):
        await narrative_generation.write_to_incubator(
            DummyConnection(), {"generation_model": None}
        )


@pytest.mark.asyncio
async def test_bootstrap_threads_logon_model_into_incubator_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap uses the model carried by LOGON's successful response."""

    class BootstrapCursor:
        def __init__(self) -> None:
            self.result: dict[str, Any] | None = None

        def __enter__(self) -> "BootstrapCursor":
            return self

        def __exit__(self, *_args: Any) -> bool:
            return False

        def execute(self, query: str, params: Any = None) -> None:
            if "SELECT setting, user_character" in query:
                self.result = {
                    "setting": {
                        "world_name": "Fixture World",
                        "story_seed": {"title": "Fixture Opening"},
                    },
                    "user_character": 11,
                }
            elif "FROM characters" in query:
                self.result = {
                    "name": "Fixture Protagonist",
                    "summary": "A test-only protagonist.",
                    "appearance": "",
                    "background": "",
                    "personality": "",
                    "emotional_state": "",
                    "current_activity": "",
                    "extra_data": {},
                }
            elif "JOIN characters c" in query:
                self.result = {
                    "name": "Fixture Station",
                    "summary": "A test-only location.",
                    "history": "",
                    "current_status": "",
                    "secrets": "",
                    "inhabitants": [],
                    "atmosphere": "",
                    "extra_data": {},
                }
            else:
                raise AssertionError(f"Unexpected bootstrap query: {query}")

        def fetchone(self) -> dict[str, Any] | None:
            return self.result

    class BootstrapConnection(DummyConnection):
        def cursor(self, **_kwargs: Any) -> BootstrapCursor:
            return BootstrapCursor()

    class FakeLogonUtility:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def generate_narrative_async(
            self, context: dict[str, Any]
        ) -> StorytellerResponseBootstrap:
            assert context["is_bootstrap"] is True
            return StorytellerResponseBootstrap(
                generation_model="resolved-bootstrap-model",
                narrative="The station clock strikes thirteen.",
                choices=["Board the train.", "Leave the station."],
            )

    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.LogonUtility", FakeLogonUtility
    )

    payload = await narrative_generation.generate_bootstrap_narrative(
        BootstrapConnection(),
        "bootstrap-session",
        "Begin.",
        slot=5,
        load_settings=lambda: {},
    )

    assert payload["generation_model"] == "resolved-bootstrap-model"

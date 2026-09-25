"""Offline route and recovery precondition regressions for terminal failures."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from nexus.api import narrative, narrative_lease, slot_state
from nexus.api.narrative_schemas import RetryNarrativeRequest


class RetryCursor:
    """Return durable rows without a database or provider."""

    def __init__(self, failed, pending=None, parent=None):
        self.results = iter([failed, pending, parent])
        self.queries = []

    def execute(self, query):
        self.queries.append(query)

    def fetchone(self):
        return next(self.results)


def failed_row(**overrides):
    """Build a terminal attempt at the committed frontier."""
    return (
        dict(
            session_id="reviewed-failure",
            status="error",
            terminal_outcome="error",
            parent_chunk_id=9,
            replaced_by_session_id=None,
        )
        | overrides
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"session_id": "newer-failure"},
        {"status": "complete"},
        {"terminal_outcome": "accepted"},
        {"parent_chunk_id": None},
        {"replaced_by_session_id": "replacement"},
    ],
)
def test_retry_rejects_stale_or_ineligible_failure(overrides):
    """A historical or incomplete failure cannot authorize paid retry work."""
    with pytest.raises(narrative_lease.GenerationRetryConflict):
        narrative_lease._retry_context(
            RetryCursor(failed_row(**overrides)), "reviewed-failure"
        )


@pytest.mark.parametrize(
    "pending,parent",
    [
        (True, None),
        (None, None),
        (None, {"id": 10, "choice_text": "New action"}),
        (None, {"id": 9, "choice_text": "   "}),
    ],
)
def test_retry_rejects_changed_frontier_or_missing_recorded_action(pending, parent):
    """Retry neither consumes a draft nor invents a lost action."""
    with pytest.raises(narrative_lease.GenerationRetryConflict):
        narrative_lease._retry_context(
            RetryCursor(failed_row(), pending, parent), "reviewed-failure"
        )


def test_retry_preserves_exact_committed_action():
    """Free text survives without consulting now-consumed choice labels."""
    text = "Keep their terms—don't agree.\nAsk why."
    cur = RetryCursor(failed_row(), parent={"id": 9, "choice_text": text})
    result = narrative_lease._retry_context(cur, "reviewed-failure")
    assert result == narrative_lease.GenerationRetryContext(9, text)
    assert all(query.startswith("SELECT") for query in cur.queries)


def test_bootstrap_retry_requires_no_playable_frontier():
    """Only the same empty frontier can restart a failed bootstrap."""
    row = failed_row(parent_chunk_id=0)
    assert narrative_lease._retry_context(
        RetryCursor(row), "reviewed-failure"
    ) == narrative_lease.GenerationRetryContext(0, "")
    with pytest.raises(narrative_lease.GenerationRetryConflict):
        narrative_lease._retry_context(
            RetryCursor(row, parent={"id": 1, "choice_text": "x"}), "reviewed-failure"
        )


@pytest.mark.parametrize(
    "extra",
    [{"user_text": "new action"}, {"choice": 2}, {"chunk_id": 8}, {"model": "other"}],
)
def test_retry_cannot_override_action_frontier_or_model(extra):
    """A retry request only identifies the explicitly reviewed failure."""
    with pytest.raises(ValidationError):
        RetryNarrativeRequest(slot=4, expected_session_id="failed", **extra)


@pytest.fixture
def route(monkeypatch):
    """Capture scheduling; no background provider or database can run."""
    monkeypatch.setattr(narrative, "require_writable_slot", Mock())
    monkeypatch.setattr(
        slot_state, "get_slot_state", lambda slot: SimpleNamespace(is_wizard_mode=False)
    )
    connection = Mock()
    monkeypatch.setattr(narrative, "get_db_connection", lambda slot: connection)
    monkeypatch.setattr(narrative, "_bind_generation_owner", Mock())
    monkeypatch.setattr(narrative, "_abandon_unscheduled_generation_owner", Mock())
    monkeypatch.setattr(narrative.manager, "send_progress", AsyncMock())
    return connection


@pytest.mark.asyncio
async def test_retry_schedules_recorded_action_once_without_acceptance(
    route, monkeypatch
):
    """The retry schedules generation directly, never commits an input again."""
    acquire = Mock(
        return_value=narrative_lease.GenerationRetryContext(9, "Recorded\naction")
    )
    monkeypatch.setattr(narrative, "acquire_generation_lease", acquire)
    monkeypatch.setattr(
        narrative,
        "_record_player_response_for_chunk",
        Mock(side_effect=AssertionError("No response rewrite")),
    )
    monkeypatch.setattr(
        narrative,
        "_resolve_and_approve_pending",
        AsyncMock(side_effect=AssertionError("No acceptance")),
    )
    tasks = BackgroundTasks()
    result = await narrative.retry_narrative(
        RetryNarrativeRequest(slot=4, expected_session_id="failed"), tasks
    )
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args == (result.session_id, 9, "Recorded\naction", 4)
    assert tasks.tasks[0].kwargs["manage_generation_lease"] is True
    assert acquire.call_args.kwargs["expected_failed_session_id"] == "failed"
    route.close.assert_called_once()


@pytest.mark.asyncio
async def test_retry_precondition_failure_never_schedules(route, monkeypatch):
    """The server fences stale UI state before scheduling any work."""
    monkeypatch.setattr(
        narrative,
        "acquire_generation_lease",
        Mock(side_effect=narrative_lease.GenerationRetryConflict("changed")),
    )
    tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as error:
        await narrative.retry_narrative(
            RetryNarrativeRequest(slot=4, expected_session_id="failed"), tasks
        )
    assert error.value.status_code == 409
    assert tasks.tasks == []
    narrative._bind_generation_owner.assert_not_called()
    narrative._abandon_unscheduled_generation_owner.assert_not_called()


@pytest.mark.asyncio
async def test_retry_scheduling_failure_releases_its_new_owner(route, monkeypatch):
    """A broken notification cannot strand the new retry lease."""
    monkeypatch.setattr(
        narrative,
        "acquire_generation_lease",
        Mock(return_value=narrative_lease.GenerationRetryContext(9, "Recorded")),
    )
    narrative.manager.send_progress.side_effect = RuntimeError("offline notification")
    tasks = BackgroundTasks()
    with pytest.raises(RuntimeError, match="offline notification"):
        await narrative.retry_narrative(
            RetryNarrativeRequest(slot=4, expected_session_id="failed"), tasks
        )
    assert tasks.tasks == []
    narrative._abandon_unscheduled_generation_owner.assert_called_once()


def _committed_state(*, has_pending: bool = False, choices=("Open.", "Wait.")):
    """Slot state whose frontier chunk is 17, pending session when requested."""
    return SimpleNamespace(
        is_wizard_mode=False,
        narrative_state=SimpleNamespace(
            has_pending=has_pending,
            session_id="pending-17" if has_pending else None,
            current_chunk_id=17,
            choices=list(choices),
        ),
    )


@pytest.fixture
def continue_route(monkeypatch):
    """Drive continue_narrative to the bind boundary without a database."""
    from nexus.api.narrative_schemas import ContinueNarrativeRequest

    monkeypatch.setattr(narrative, "require_writable_slot", Mock())
    monkeypatch.setattr(narrative, "_acquire_generation_owner", Mock())
    monkeypatch.setattr(
        narrative,
        "_bind_generation_owner",
        Mock(side_effect=RuntimeError("bind connection lost")),
    )
    abandon = Mock()
    monkeypatch.setattr(narrative, "_abandon_unscheduled_generation_owner", abandon)
    monkeypatch.setattr(narrative.manager, "send_progress", AsyncMock())

    async def run(state, **request):
        monkeypatch.setattr(slot_state, "get_slot_state", lambda slot: state)
        tasks = BackgroundTasks()
        with pytest.raises(RuntimeError, match="bind connection lost"):
            await narrative.continue_narrative(
                ContinueNarrativeRequest(slot=4, **request), tasks
            )
        assert tasks.tasks == []
        abandon.assert_called_once()
        return abandon.call_args.kwargs["accepted_parent_candidate"]

    return run


@pytest.mark.asyncio
async def test_bind_failure_after_committed_frontier_action_names_that_chunk(
    continue_route, monkeypatch
):
    """The accepted action's chunk reaches the abandon path for durable binding."""
    monkeypatch.setattr(
        narrative, "_record_player_response_for_chunk", Mock(return_value="Open.")
    )
    assert await continue_route(_committed_state(), choice=1) == 17


@pytest.mark.asyncio
async def test_bind_failure_after_auto_approval_names_the_approved_chunk(
    continue_route, monkeypatch
):
    """Auto-approval commits a new chunk; that chunk is the retry frontier."""
    monkeypatch.setattr(
        narrative,
        "_resolve_and_approve_pending",
        AsyncMock(return_value=("Open.", 18, [])),
    )
    assert await continue_route(_committed_state(has_pending=True), choice=1) == 18


@pytest.mark.asyncio
async def test_bootstrap_bind_failure_has_no_accepted_action(continue_route):
    """No player action exists before the first chunk; nothing is bound."""
    state = SimpleNamespace(is_wizard_mode=False, narrative_state=None)
    assert await continue_route(state) is None

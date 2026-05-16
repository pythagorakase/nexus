"""Tests for Orrery post-commit promotion and narration worker."""

from __future__ import annotations

import pytest

from nexus.agents.orrery.worker import (
    PromotionVerdict,
    drain_narration_outbox_sync,
    promote_pending_resolutions_sync,
)


class WorkerCursor:
    """Recording cursor for worker SQL branches."""

    def __init__(self, *, promotion_rows=None, job_rows=None):
        self.promotion_rows = promotion_rows or []
        self.job_rows = job_rows or []
        self.executed = []
        self._fetchall = []
        self._fetchone = None

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._fetchall = []
        self._fetchone = None
        normalized = " ".join(str(sql).split())
        if "FROM orrery_resolutions r" in normalized:
            self._fetchall = self.promotion_rows
        elif "FROM orrery_narration_jobs j" in normalized:
            self._fetchall = self.job_rows
        elif "INSERT INTO offscreen_narrations" in normalized:
            self._fetchone = {"id": 501}

    def fetchall(self):
        return self._fetchall

    def fetchone(self):
        return self._fetchone


class WorkerConn:
    """Connection stand-in with transaction/context-manager behavior."""

    def __init__(self, cursor: WorkerCursor):
        self.cursor_obj = cursor
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def cursor(self, *args, **kwargs):
        return self.cursor_obj

    def close(self):
        self.closed = True


class FakeLLM:
    """Local LLM stand-in returning one structured verdict."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.prompts = []

    def structured_query(self, prompt, response_model, **_kwargs):
        self.prompts.append((prompt, response_model))
        return self.verdict


class FakeProviderResponse:
    """Provider response stand-in."""

    content = "Mara disappears below the platform, leaving only static behind."


class FakeNarrationProvider:
    """Frontier provider stand-in."""

    def __init__(self):
        self.prompts = []

    def get_completion(self, prompt):
        self.prompts.append(prompt)
        return FakeProviderResponse()


class FailingNarrationProvider:
    """Provider stand-in that raises while generating narration."""

    def get_completion(self, _prompt):
        raise TimeoutError("temporary provider failure")


def _settings():
    return {
        "orrery": {
            "narration": {
                "provider": "anthropic",
                "model_ref": "claude-sonnet-4-6",
            }
        }
    }


def _promotion_row():
    return {
        "id": 10,
        "tick_chunk_id": 100,
        "template_id": "evade_pursuers",
        "actor_entity_id": 1,
        "actor_name": "Mara",
        "priority": 100,
        "magnitude": 0.72,
        "state_delta": {"character.current_activity": "hiding"},
        "brief": "Mara vanishes into a maintenance corridor.",
        "event_ids": [20],
    }


def _job_row():
    return {
        "job_id": 90,
        "resolution_id": 10,
        "slot": "5",
        "tick_chunk_id": 100,
        "template_id": "evade_pursuers",
        "actor_entity_id": 1,
        "actor_name": "Mara",
        "magnitude": 0.72,
        "state_delta": {"character.current_activity": "hiding"},
        "brief": "Mara vanishes into a maintenance corridor.",
        "promotion_verdict": {
            "promote": True,
            "reason": "It creates a future off-screen consequence.",
            "perceptual_channel": "digital",
            "perceptual_summary": "street cameras briefly lose Mara",
        },
        "event_ids": [20],
        "attempts": 0,
        "world_layer": "primary",
    }


def test_promote_pending_resolutions_queues_narration_job() -> None:
    """Promoted resolutions are marked and placed into the durable outbox."""

    cursor = WorkerCursor(promotion_rows=[_promotion_row()])
    verdict = PromotionVerdict(
        promote=True,
        reason="It creates future retrieval value.",
        perceptual_channel="digital",
        perceptual_summary="street cameras briefly lose Mara",
    )

    promoted, skipped = promote_pending_resolutions_sync(
        slot=5,
        settings=_settings(),
        llm_manager=FakeLLM(verdict),
        conn=WorkerConn(cursor),
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert promoted == 1
    assert skipped == 0
    assert "FOR UPDATE OF r SKIP LOCKED" in statements
    assert "promotion_status = 'promoted'" in statements
    assert "INSERT INTO orrery_narration_jobs" in statements


def test_promote_pending_resolutions_rejects_malformed_llm_output() -> None:
    """Malformed local-LLM promotion data fails visibly."""

    cursor = WorkerCursor(promotion_rows=[_promotion_row()])

    with pytest.raises(ValueError, match="Malformed Orrery promotion verdict"):
        promote_pending_resolutions_sync(
            slot=5,
            settings=_settings(),
            llm_manager=FakeLLM({"answer": "sure"}),
            conn=WorkerConn(cursor),
        )


def test_drain_narration_outbox_persists_offscreen_narration() -> None:
    """Queued narration jobs persist into offscreen_narrations."""

    cursor = WorkerCursor(job_rows=[_job_row()])
    provider = FakeNarrationProvider()

    narrated, failed = drain_narration_outbox_sync(
        slot=5,
        settings=_settings(),
        narration_provider=provider,
        conn=WorkerConn(cursor),
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert narrated == 1
    assert failed == 0
    assert provider.prompts
    assert "FOR UPDATE OF j SKIP LOCKED" in statements
    assert "INSERT INTO offscreen_narrations" in statements
    assert "narration_status = 'succeeded'" in statements
    assert "state = 'succeeded'" in statements


def test_drain_narration_outbox_does_not_lease_before_provider_ready() -> None:
    """Provider setup failures leave queued jobs available for a later drain."""

    cursor = WorkerCursor(job_rows=[_job_row()])

    with pytest.raises(ValueError, match="Unsupported Orrery narration provider"):
        drain_narration_outbox_sync(
            slot=5,
            settings={"orrery": {"narration": {"provider": "missing"}}},
            conn=WorkerConn(cursor),
        )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert "state = 'leased'" not in statements


def test_drain_narration_outbox_requeues_transient_failures() -> None:
    """Narration attempts retry with backoff before becoming terminal."""

    cursor = WorkerCursor(job_rows=[_job_row()])

    narrated, failed = drain_narration_outbox_sync(
        slot=5,
        settings=_settings(),
        narration_provider=FailingNarrationProvider(),
        conn=WorkerConn(cursor),
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert narrated == 0
    assert failed == 1
    assert "state = 'queued'" in statements
    assert "available_at = now() + (%s * interval '1 second')" in statements
    assert "narration_status = 'queued'" in statements
    assert "narration_status = 'failed'" not in statements


def test_drain_narration_outbox_marks_terminal_after_max_attempts() -> None:
    """Retries stop once the configured max attempts is reached."""

    job = dict(_job_row(), attempts=2)
    cursor = WorkerCursor(job_rows=[job])

    narrated, failed = drain_narration_outbox_sync(
        slot=5,
        settings=_settings(),
        narration_provider=FailingNarrationProvider(),
        conn=WorkerConn(cursor),
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert narrated == 0
    assert failed == 1
    assert "state = 'failed'" in statements
    assert "narration_status = 'failed'" in statements

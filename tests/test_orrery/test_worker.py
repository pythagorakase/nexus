"""Tests for Orrery post-commit promotion and narration worker."""

from __future__ import annotations

import json

import pytest

from nexus.agents.orrery.worker import (
    clear_semantic_tags_sync,
    drain_narration_outbox_sync,
    load_orrery_status_sync,
    promote_pending_resolutions_sync,
    process_orrery_outbox_sync,
)


class WorkerCursor:
    """Recording cursor for worker SQL branches."""

    def __init__(
        self,
        *,
        promotion_rows=None,
        job_rows=None,
        count_rows=None,
    ):
        self.promotion_rows = promotion_rows or []
        self.job_rows = job_rows or []
        self.count_rows = list(count_rows or [])
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
        if "SELECT count(*) AS count" in normalized:
            self._fetchone = {"count": self.count_rows.pop(0)}
        elif "FROM orrery_resolutions r" in normalized:
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
            },
            "promote": {
                "priority_threshold": 50.0,
                "magnitude_threshold": 0.5,
                "perceptual_summary_max_chars": 240,
            },
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

    promoted, skipped = promote_pending_resolutions_sync(
        slot=5,
        settings=_settings(),
        conn=WorkerConn(cursor),
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert promoted == 1
    assert skipped == 0
    assert "FOR UPDATE OF r SKIP LOCKED" in statements
    assert "promotion_status = 'promoted'" in statements
    assert "INSERT INTO orrery_narration_jobs" in statements


def test_promote_pending_resolutions_skips_low_signal_rows() -> None:
    """Low-salience rows stay skipped without asking a local model."""

    row = dict(
        _promotion_row(),
        priority=10,
        magnitude=0.1,
        state_delta={},
        event_ids=[],
    )
    cursor = WorkerCursor(promotion_rows=[row])

    promoted, skipped = promote_pending_resolutions_sync(
        slot=5,
        settings=_settings(),
        conn=WorkerConn(cursor),
    )

    verdict = json.loads(cursor.executed[-1][1][0])
    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert promoted == 0
    assert skipped == 1
    assert verdict["promote"] is False
    assert "Deterministic skip" in verdict["reason"]
    assert "INSERT INTO orrery_narration_jobs" not in statements


def test_promote_pending_resolutions_uses_state_signal_without_brief() -> None:
    """A salient state/event resolution should not require a generated brief."""

    row = dict(
        _promotion_row(),
        priority=80,
        magnitude=0.1,
        brief="",
        state_delta={"character.current_activity": "recovering"},
        event_ids=[],
    )
    cursor = WorkerCursor(promotion_rows=[row])

    promoted, skipped = promote_pending_resolutions_sync(
        slot=5,
        settings=_settings(),
        conn=WorkerConn(cursor),
    )

    verdict = json.loads(cursor.executed[1][1][0])

    assert promoted == 1
    assert skipped == 0
    assert verdict["promote"] is True
    assert verdict["perceptual_summary"] is None


def test_promote_default_thresholds_match_calibrated_seams() -> None:
    """Default thresholds promote eventful templates and dramatic outcomes only.

    Calibrated against the save_05 corpus (2026-06): the template catalog's
    mundane-needs band tops out at priority 26 / routine magnitude 0.22, while
    relational and dramatic templates start at priority 35 and noteworthy
    branch magnitudes start near 0.34.
    """

    rows = [
        # (template-like row, expected_promote)
        (dict(_promotion_row(), id=1, priority=14, magnitude=0.18), False),  # work
        (dict(_promotion_row(), id=2, priority=25, magnitude=0.28), False),  # mourn
        (dict(_promotion_row(), id=3, priority=35, magnitude=0.34), True),  # rival
        (dict(_promotion_row(), id=4, priority=84, magnitude=0.36), True),  # hide
        (dict(_promotion_row(), id=5, priority=25, magnitude=0.74), True),  # sleep!
    ]
    settings = _settings()
    del settings["orrery"]["promote"]  # exercise OrreryPromoteSettings defaults
    cursor = WorkerCursor(promotion_rows=[row for row, _expected in rows])

    promoted, skipped = promote_pending_resolutions_sync(
        slot=5,
        settings=settings,
        conn=WorkerConn(cursor),
    )

    verdicts = [
        json.loads(params[0])
        for sql, params in cursor.executed
        if "promotion_verdict" in str(sql)
    ]

    assert promoted == 3
    assert skipped == 2
    assert [verdict["promote"] for verdict in verdicts] == [
        expected for _row, expected in rows
    ]


def test_promote_pending_resolutions_uses_configured_thresholds() -> None:
    """Promotion salience should be tuned through Orrery promote config."""

    row = dict(_promotion_row(), priority=80, magnitude=0.7)
    settings = _settings()
    settings["orrery"]["promote"] = {
        "priority_threshold": 90.0,
        "magnitude_threshold": 0.9,
        "perceptual_summary_max_chars": 16,
    }
    cursor = WorkerCursor(promotion_rows=[row])

    promoted, skipped = promote_pending_resolutions_sync(
        slot=5,
        settings=settings,
        conn=WorkerConn(cursor),
    )

    verdict = json.loads(cursor.executed[-1][1][0])

    assert promoted == 0
    assert skipped == 1
    assert verdict["promote"] is False
    assert "80/90" in verdict["reason"]


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


def test_clear_semantic_tags_is_conservative_noop_without_local_inference() -> None:
    """Semantic clearance performs no writes without a non-local clearance signal."""

    cursor = WorkerCursor()

    cleared = clear_semantic_tags_sync(
        slot=5,
        settings=_settings(),
        conn=WorkerConn(cursor),
    )

    assert cleared == 0
    assert cursor.executed == []


def test_process_orrery_outbox_includes_semantic_clearance(monkeypatch) -> None:
    """The background entry point keeps the semantic-clearance compatibility call."""

    calls = []

    def fake_promote(*_args, **kwargs):
        calls.append(("promote", kwargs["limit"]))
        return (1, 2)

    def fake_drain(*_args, **kwargs):
        calls.append(("drain", kwargs["limit"]))
        return (3, 4)

    def fake_clear(*_args, **kwargs):
        calls.append(
            (
                "clear",
                kwargs["limit"],
                kwargs["recent_chunk_window"],
                kwargs["evidence_chunk_limit"],
                kwargs["evidence_event_limit"],
            )
        )
        return 5

    monkeypatch.setattr(
        "nexus.agents.orrery.worker.promote_pending_resolutions_sync",
        fake_promote,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.worker.drain_narration_outbox_sync",
        fake_drain,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.worker.clear_semantic_tags_sync",
        fake_clear,
    )

    def fake_maturation(*_args, **kwargs):
        calls.append(("mature", kwargs["limit"]))
        return (6, 7)

    monkeypatch.setattr(
        "nexus.agents.orrery.worker.drain_maturation_jobs_sync",
        fake_maturation,
    )

    result = process_orrery_outbox_sync(
        slot=5,
        promotion_limit=6,
        narration_limit=7,
        semantic_clearance_limit=8,
        semantic_clearance_recent_chunks=9,
        semantic_clearance_evidence_chunks=10,
        semantic_clearance_evidence_events=11,
        maturation_limit=12,
    )

    assert result.promoted == 1
    assert result.skipped == 2
    assert result.narrated == 3
    assert result.failed == 4
    assert result.semantically_cleared == 5
    assert result.matured == 6
    assert result.maturation_failed == 7
    assert calls == [
        ("promote", 6),
        ("drain", 7),
        ("clear", 8, 9, 10, 11),
        ("mature", 12),
    ]


def test_load_orrery_status_sync_counts_background_work() -> None:
    """Status snapshots expose the background-work backlog."""

    cursor = WorkerCursor(count_rows=[1, 2, 3, 4, 5, 6, 7, 8, 9])

    status = load_orrery_status_sync(conn=WorkerConn(cursor))

    assert status.pending_promotions == 1
    assert status.queued_narration_jobs == 2
    assert status.leased_narration_jobs == 3
    assert status.failed_narration_jobs == 4
    assert status.pending_offscreen_embeddings == 5
    assert status.failed_offscreen_embeddings == 6
    assert status.active_semantic_tags == 7
    assert status.recent_resolutions == 8
    assert status.recent_narrations == 9

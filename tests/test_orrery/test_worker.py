"""Tests for Orrery post-commit promotion and narration worker."""

from __future__ import annotations

import pytest

from nexus.agents.orrery.worker import (
    PromotionVerdict,
    SemanticClearanceVerdict,
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
        semantic_rows=None,
        semantic_chunk_rows=None,
        semantic_event_rows=None,
        count_rows=None,
    ):
        self.promotion_rows = promotion_rows or []
        self.job_rows = job_rows or []
        self.semantic_rows = semantic_rows or []
        self.semantic_chunk_rows = semantic_chunk_rows or []
        self.semantic_event_rows = semantic_event_rows or []
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
        elif (
            "WITH recent_ticks AS" in normalized and "FROM entity_tags et" in normalized
        ):
            self._fetchall = self.semantic_rows
        elif "FROM chunk_entity_references_v cer" in normalized:
            self._fetchall = self.semantic_chunk_rows
        elif "FROM world_events we" in normalized:
            self._fetchall = self.semantic_event_rows
        elif "INSERT INTO offscreen_narrations" in normalized:
            self._fetchone = {"id": 501}
        elif "UPDATE entity_tags et SET cleared_at = now()" in normalized:
            self._fetchone = {"id": params[0]}

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
        self.verdicts = list(verdict) if isinstance(verdict, list) else [verdict]
        self.prompts = []

    def structured_query(self, prompt, response_model, **_kwargs):
        self.prompts.append((prompt, response_model))
        return self.verdicts.pop(0)


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


def _semantic_tag_row():
    return {
        "entity_tag_id": 700,
        "entity_id": 1,
        "entity_name": "Mara",
        "applied_at": "2073-10-31T18:00:00+00:00",
        "applied_at_world_time": None,
        "template_id": "evade_pursuers",
        "tag": "wounded",
        "category": "state",
        "description": "Entity has a recent physical injury.",
    }


def _semantic_tag_row_2():
    row = dict(_semantic_tag_row())
    row.update(
        {
            "entity_tag_id": 701,
            "entity_id": 2,
            "entity_name": "Toma",
            "tag": "recently_violent",
            "description": "Actor has executed violence in the recent past.",
        }
    )
    return row


def _semantic_chunk_row():
    return {
        "id": 105,
        "text": "Mara limps at first, then steadies herself and keeps moving.",
    }


def _semantic_event_row():
    return {
        "id": 20,
        "tick_chunk_id": 104,
        "event_type": "evade_pursuit",
        "changed_fields": ["character.current_activity"],
        "magnitude": 0.72,
        "payload": {"branch_label": "Go to ground"},
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


def test_clear_semantic_tags_clears_when_verdict_true() -> None:
    """Semantic ephemeral tags clear only after a structured positive verdict."""

    cursor = WorkerCursor(
        semantic_rows=[_semantic_tag_row()],
        semantic_chunk_rows=[_semantic_chunk_row()],
        semantic_event_rows=[_semantic_event_row()],
    )
    verdict = SemanticClearanceVerdict(clear=True, reason="Mara recovered.")
    llm = FakeLLM(verdict)

    cleared = clear_semantic_tags_sync(
        slot=5,
        settings=_settings(),
        llm_manager=llm,
        conn=WorkerConn(cursor),
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert cleared == 1
    assert "WITH recent_ticks AS" in statements
    assert "FOR UPDATE OF et SKIP LOCKED" not in statements
    assert "UPDATE entity_tags et" in statements
    assert "SET cleared_at = now()" in statements
    assert "INSERT INTO tag_clearance_log" in statements
    assert "VALUES (%s, 'semantic', %s::jsonb, %s)" in statements
    assert cursor.executed[-1][1][2] == 105
    assert llm.prompts[0][1] is SemanticClearanceVerdict
    assert "Tag: wounded" in llm.prompts[0][0]
    assert "Mara limps at first" in llm.prompts[0][0]


def test_clear_semantic_tags_keeps_when_verdict_false() -> None:
    """A negative semantic verdict leaves the current tag untouched."""

    cursor = WorkerCursor(
        semantic_rows=[_semantic_tag_row()],
        semantic_chunk_rows=[_semantic_chunk_row()],
        semantic_event_rows=[_semantic_event_row()],
    )
    verdict = SemanticClearanceVerdict(clear=False, reason="Recovery is ambiguous.")

    cleared = clear_semantic_tags_sync(
        slot=5,
        settings=_settings(),
        llm_manager=FakeLLM(verdict),
        conn=WorkerConn(cursor),
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert cleared == 0
    assert "UPDATE entity_tags SET cleared_at" not in statements
    assert "INSERT INTO tag_clearance_log" not in statements


def test_clear_semantic_tags_rejects_malformed_llm_output() -> None:
    """Malformed semantic-clearance data fails after prior row commits survive."""

    cursor = WorkerCursor(
        semantic_rows=[_semantic_tag_row(), _semantic_tag_row_2()],
        semantic_chunk_rows=[_semantic_chunk_row()],
        semantic_event_rows=[_semantic_event_row()],
    )
    llm = FakeLLM(
        [
            SemanticClearanceVerdict(clear=True, reason="Mara recovered."),
            {"answer": "maybe"},
        ]
    )

    with pytest.raises(ValueError, match="Malformed Orrery semantic clearance verdict"):
        clear_semantic_tags_sync(
            slot=5,
            settings=_settings(),
            llm_manager=llm,
            conn=WorkerConn(cursor),
        )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert statements.count("UPDATE entity_tags et") == 1
    assert statements.count("INSERT INTO tag_clearance_log") == 1


def test_process_orrery_outbox_includes_semantic_clearance(monkeypatch) -> None:
    """The background entry point drains semantic clearance with other work."""

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

    result = process_orrery_outbox_sync(
        slot=5,
        promotion_limit=6,
        narration_limit=7,
        semantic_clearance_limit=8,
        semantic_clearance_recent_chunks=9,
        semantic_clearance_evidence_chunks=10,
        semantic_clearance_evidence_events=11,
    )

    assert result.promoted == 1
    assert result.skipped == 2
    assert result.narrated == 3
    assert result.failed == 4
    assert result.semantically_cleared == 5
    assert calls == [("promote", 6), ("drain", 7), ("clear", 8, 9, 10, 11)]


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

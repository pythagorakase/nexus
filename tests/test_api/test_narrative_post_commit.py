"""Tests for post-commit Orrery work scheduling in the narrative API.

FastAPI background tasks run sequentially in add order, and the
auto-approve path schedules post-commit Orrery work BEFORE the next
chunk's generation task. The Retrograde maturation drain makes
multi-minute frontier calls, so it must detach from that chain
(fire-and-forget, spec decision 10) while quick outbox work stays inline.
"""

from __future__ import annotations

from typing import Any

from nexus.api import narrative


def test_post_commit_orrery_work_detaches_maturation(monkeypatch) -> None:
    """Quick outbox work runs inline with maturation excluded; the
    maturation drain starts on a detached daemon thread instead."""

    outbox_calls: list[dict[str, Any]] = []

    def fake_outbox(slot: Any, *args: Any, **kwargs: Any) -> None:
        outbox_calls.append({"slot": slot, **kwargs})

    def fake_drain(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("drain must not run inline")

    started: dict[str, Any] = {}

    class FakeThread:
        def __init__(
            self,
            *,
            target: Any,
            args: tuple[Any, ...] = (),
            name: str | None = None,
            daemon: bool | None = None,
        ) -> None:
            started["target"] = target
            started["args"] = args
            started["name"] = name
            started["daemon"] = daemon

        def start(self) -> None:
            started["started"] = True

    monkeypatch.setattr(
        "nexus.agents.orrery.worker.process_orrery_outbox_sync",
        fake_outbox,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_maturation.drain_maturation_jobs_sync",
        fake_drain,
    )
    monkeypatch.setattr(narrative.threading, "Thread", FakeThread)

    narrative._run_post_commit_orrery_work(2)

    assert outbox_calls == [{"slot": 2, "maturation_limit": 0}]
    assert started["started"] is True
    assert started["target"] is fake_drain
    assert started["args"] == (2,)
    assert started["daemon"] is True

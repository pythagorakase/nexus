from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

from nexus.api.summary_triggers import (
    SummaryTask,
    plan_summary_tasks,
    schedule_summary_generation,
)


def test_plan_summary_tasks():
    assert plan_summary_tasks("continue", 5, 1) == []

    new_ep = plan_summary_tasks("new_episode", 5, 1)
    assert new_ep == [SummaryTask(kind="episode", season=5, episode=1)]

    new_season = plan_summary_tasks("new_season", 5, 13)
    assert new_season == [
        SummaryTask(kind="episode", season=5, episode=13),
        SummaryTask(kind="season", season=5),
    ]


@dataclass
class _FakeDB:
    episode_summaries: Dict[str, object]
    season_summaries: Dict[int, object]
    empty_episodes: Optional[List[str]] = None
    failure_records: Optional[List[dict]] = None

    def episode_summary_exists(self, season: int, episode: int) -> bool:
        value = self.episode_summaries.get(f"{season}-{episode}", False)
        return bool(value) and not (
            isinstance(value, dict) and value.get("status") == "error"
        )

    def season_summary_exists(self, season: int) -> bool:
        value = self.season_summaries.get(season, False)
        return bool(value) and not (
            isinstance(value, dict) and value.get("status") == "error"
        )

    def get_episode_chunk_span(self, season: int, episode: int):
        if self.empty_episodes and f"{season}-{episode}" in self.empty_episodes:
            return None
        return (1, 2)

    def record_summary_failure(self, **record) -> bool:
        marker = {"status": "error", **record}
        if self.failure_records is None:
            self.failure_records = []
        self.failure_records.append(marker)
        if record["kind"] == "episode":
            self.episode_summaries[f"{record['season']}-{record['episode']}"] = marker
        else:
            self.season_summaries[record["season"]] = marker
        return True


@dataclass
class _RecorderGenerator:
    model: str
    db_manager: _FakeDB
    overwrite: bool
    verbose: bool
    save_prompt: bool
    prompt_on_conflict: bool
    calls: List[str]

    def generate_episode_summary(self, season: int, episode: int) -> Dict[str, str]:
        self.calls.append(f"episode-{season}-{episode}-{self.model}")
        return {"summary": "ok"}

    def generate_season_summary(self, season: int) -> Dict[str, str]:
        self.calls.append(f"season-{season}-{self.model}")
        return {"summary": "ok"}


class _FailingGenerator:
    def __init__(self, **kwargs):
        self.model = kwargs["model"]
        self.last_error = "mock Responses failure"

    def generate_episode_summary(self, season: int, episode: int):
        return None

    def generate_season_summary(self, season: int):
        return None


@pytest.mark.parametrize(
    "existing_episode,existing_season,expected_calls",
    [
        (False, False, ["episode-5-1-TEST", "season-5-TEST"]),
        (True, False, ["season-5-TEST"]),  # skip episode summary if present
        (False, True, ["episode-5-1-TEST"]),  # skip season summary if present
    ],
)
def test_schedule_summary_generation_skips_existing(
    existing_episode, existing_season, expected_calls
):
    recorder_calls: List[str] = []

    def db_factory() -> _FakeDB:
        return _FakeDB(
            episode_summaries={"5-1": existing_episode},
            season_summaries={5: existing_season},
        )

    def generator_factory(**kwargs):
        return _RecorderGenerator(calls=recorder_calls, **kwargs)

    tasks = [
        SummaryTask(kind="episode", season=5, episode=1),
        SummaryTask(kind="season", season=5),
    ]

    schedule_summary_generation(
        tasks,
        overwrite=False,
        model_candidates=["TEST"],
        run_in_thread=False,
        db_manager_factory=db_factory,
        generator_cls=generator_factory,
    )

    assert recorder_calls == expected_calls


def test_coalesce_models_prefers_summaries_default_over_apex(monkeypatch):
    """Empty candidates resolve to summaries.model, not the storyteller model.

    M9 gate finding: scripts/summarize_narrative resolves its module
    constants at argparse time (both None on import), so API-triggered
    episode summaries ran with zero model candidates and always failed.
    """

    from types import SimpleNamespace

    import nexus.config
    from nexus.api.summary_triggers import _coalesce_models

    monkeypatch.setattr(
        nexus.config,
        "load_settings",
        lambda: SimpleNamespace(
            summaries=SimpleNamespace(model="summary-model"),
            apex=SimpleNamespace(model="storyteller-model"),
        ),
    )

    models = _coalesce_models(None)
    assert models == ["summary-model"]


def test_schedule_summary_generation_skips_chunkless_episodes():
    """Episodes with no chunks are skipped instead of erroring.

    M9 gate finding: the Storyteller opened play at S01E02, the bootstrap
    commit scheduled a summary for S01E01, and the summarizer errored on an
    episode that holds zero chunks.
    """

    recorder_calls: List[str] = []

    def generator_factory(**kwargs):
        return _RecorderGenerator(calls=recorder_calls, **kwargs)

    schedule_summary_generation(
        [SummaryTask(kind="episode", season=1, episode=1)],
        model_candidates=["TEST"],
        run_in_thread=False,
        db_manager_factory=lambda: _FakeDB({}, {}, empty_episodes=["1-1"]),
        generator_cls=generator_factory,
    )

    assert recorder_calls == []


def test_unroutable_storyteller_records_durable_marker_without_api_call(caplog):
    """A followed non-OpenAI storyteller (the local-Skald path) must not
    reach any provider: the scheduler records the instructive gap durably."""
    recorder_calls: List[str] = []

    def generator_factory(**kwargs):
        return _RecorderGenerator(calls=recorder_calls, **kwargs)

    db = _FakeDB({}, {}, failure_records=[])
    with caplog.at_level(logging.ERROR, logger="nexus.api.summary_triggers"):
        schedule_summary_generation(
            [SummaryTask(kind="episode", season=7, episode=2)],
            model_candidates=["nousresearch/hermes-4-70b"],
            run_in_thread=False,
            db_manager_factory=lambda: db,
            generator_cls=generator_factory,
        )

    assert recorder_calls == [], "no generator may be constructed for it"
    assert len(db.failure_records) == 1
    marker = db.failure_records[0]
    assert marker["status"] == "error"
    assert "[summaries].model" in marker["error"]
    assert "#481" in marker["error"]


def test_generation_failure_is_durable_visible_and_refireable(caplog):
    """A dropped worker result becomes an error marker, not a log-only loss."""
    db = _FakeDB({}, {}, failure_records=[])

    with caplog.at_level(logging.ERROR, logger="nexus.api.summary_triggers"):
        schedule_summary_generation(
            [SummaryTask(kind="episode", season=5, episode=1)],
            model_candidates=["TEST"],
            run_in_thread=False,
            db_manager_factory=lambda: db,
            generator_cls=_FailingGenerator,
        )

    assert db.failure_records == [
        {
            "status": "error",
            "kind": "episode",
            "season": 5,
            "episode": 1,
            "error": "TEST: mock Responses failure",
            "model_candidates": ["TEST"],
        }
    ]
    assert db.episode_summary_exists(5, 1) is False
    assert "Failed to generate S05E01 summary" in caplog.text


def test_summary_generator_routes_test_model_to_registry_base_url():
    """The TEST provider's Responses client uses its registered endpoint."""
    from nexus.config import load_settings
    from scripts.summarize_narrative import SummaryGenerator

    generator = SummaryGenerator(model="TEST", db_manager=_FakeDB({}, {}))
    expected = load_settings().global_.model.api_models["test"].base_url

    assert str(generator.provider.client.base_url).rstrip("/") == expected


@pytest.mark.requires_postgres
def test_generation_failure_marker_round_trips_and_can_be_replaced_live():
    """The real seasons JSONB surface stores errors and accepts a later summary."""
    from sqlalchemy import text

    from scripts.summarize_narrative import DatabaseManager

    db = DatabaseManager()
    season = -(uuid.uuid4().int % 1_000_000_000) - 1
    try:
        with db.engine.connect() as conn:
            conn.execute(
                text("INSERT INTO public.seasons (id, summary) VALUES (:id, NULL)"),
                {"id": season},
            )
            conn.commit()

        schedule_summary_generation(
            [SummaryTask(kind="season", season=season)],
            model_candidates=["TEST"],
            run_in_thread=False,
            db_manager_factory=lambda: db,
            generator_cls=_FailingGenerator,
        )

        with db.engine.connect() as conn:
            marker = conn.execute(
                text("SELECT summary FROM public.seasons WHERE id = :id"),
                {"id": season},
            ).scalar_one()

        assert marker["status"] == "error"
        assert marker["model_candidates"] == ["TEST"]
        assert db.season_summary_exists(season) is False
        assert db.save_season_summary(
            season,
            {"summary": "retry succeeded"},
            prompt_on_conflict=False,
        )
        assert db.season_summary_exists(season) is True

        # The reverse race: a slower FAILING job must never clobber the real
        # summary a concurrent job already saved — and the recorder must
        # report that it did NOT persist the marker.
        assert (
            db.record_summary_failure(
                kind="season",
                season=season,
                episode=None,
                error="late failure after concurrent success",
                model_candidates=["TEST"],
            )
            is False
        )
        with db.engine.connect() as conn:
            survived = conn.execute(
                text("SELECT summary FROM public.seasons WHERE id = :id"),
                {"id": season},
            ).scalar_one()
        assert (
            survived.get("status") != "error"
        ), "a late failure marker must not overwrite a saved summary"
        assert db.season_summary_exists(season) is True
    finally:
        with db.engine.connect() as conn:
            conn.execute(
                text("DELETE FROM public.seasons WHERE id = :id"), {"id": season}
            )
            conn.commit()

from __future__ import annotations

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
    episode_summaries: Dict[str, bool]
    season_summaries: Dict[int, bool]
    empty_episodes: Optional[List[str]] = None

    def episode_summary_exists(self, season: int, episode: int) -> bool:
        return self.episode_summaries.get(f"{season}-{episode}", False)

    def season_summary_exists(self, season: int) -> bool:
        return self.season_summaries.get(season, False)

    def get_episode_chunk_span(self, season: int, episode: int):
        if self.empty_episodes and f"{season}-{episode}" in self.empty_episodes:
            return None
        return (1, 2)


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


@pytest.mark.parametrize(
    "existing_episode,existing_season,expected_calls",
    [
        (False, False, ["episode-5-1-gpt-5.1", "season-5-gpt-5.1"]),
        (True, False, ["season-5-gpt-5.1"]),  # skip episode summary if present
        (False, True, ["episode-5-1-gpt-5.1"]),  # skip season summary if present
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
        model_candidates=["gpt-5.1"],
        run_in_thread=False,
        db_manager_factory=db_factory,
        generator_cls=generator_factory,
    )

    assert recorder_calls == expected_calls


def test_coalesce_models_resolves_apex_default_when_constants_are_none():
    """Empty candidates resolve to the live apex model, never an empty list.

    M9 gate finding: scripts/summarize_narrative resolves its module
    constants at argparse time (both None on import), so API-triggered
    episode summaries ran with zero model candidates and always failed.
    """

    from nexus.api.summary_triggers import _coalesce_models

    models = _coalesce_models(None)
    assert models, "model candidate list must never be empty"
    assert all(isinstance(model, str) and model for model in models)


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
        model_candidates=["gpt-test"],
        run_in_thread=False,
        db_manager_factory=lambda: _FakeDB({}, {}, empty_episodes=["1-1"]),
        generator_cls=generator_factory,
    )

    assert recorder_calls == []

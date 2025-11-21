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

    def episode_summary_exists(self, season: int, episode: int) -> bool:
        return self.episode_summaries.get(f"{season}-{episode}", False)

    def season_summary_exists(self, season: int) -> bool:
        return self.season_summaries.get(season, False)


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
def test_schedule_summary_generation_skips_existing(existing_episode, existing_season, expected_calls):
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

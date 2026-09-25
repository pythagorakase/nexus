"""Opening chronology must not close a nonexistent episode or season."""

from datetime import timedelta

import pytest

from nexus.agents.logon.apex_schema import ChronologyUpdate
from nexus.api.db_converters import chronology_for_commit, chronology_to_db_values
from nexus.api.summary_triggers import SummaryTask, plan_summary_tasks


@pytest.mark.parametrize("transition", ["continue", "new_episode", "new_season"])
@pytest.mark.parametrize("minutes", [0, 17])
def test_opening_establishes_first_episode_without_a_predecessor(
    transition: str,
    minutes: int,
) -> None:
    """Bootstrap metadata and scheduled work agree without changing the draft."""
    draft = ChronologyUpdate(
        episode_transition=transition,
        time_delta_minutes=minutes,
        time_delta_description="Story begins",
    )
    chronology = chronology_for_commit(draft, parent_chunk_id=0)

    assert chronology_to_db_values(chronology, 1, 1) == {
        "season": 1,
        "episode": 1,
        "time_delta": timedelta(minutes=minutes),
    }
    assert plan_summary_tasks(chronology.episode_transition, 1, 1) == []
    assert chronology.time_delta_description == "Story begins"
    assert draft.episode_transition == transition


@pytest.mark.parametrize(
    "transition,season,episode,tasks",
    [
        ("continue", 3, 7, []),
        ("new_episode", 3, 8, [SummaryTask("episode", 3, 7)]),
        ("new_season", 4, 1, [SummaryTask("episode", 3, 7), SummaryTask("season", 3)]),
    ],
)
def test_existing_parent_keeps_authored_transition(
    transition: str, season: int, episode: int, tasks: list[SummaryTask]
) -> None:
    """Real transitions retain numbering, elapsed time, and predecessor work."""
    draft = ChronologyUpdate(episode_transition=transition, time_delta_hours=2)
    chronology = chronology_for_commit(draft, parent_chunk_id=42)

    assert chronology_to_db_values(chronology, 3, 7) == {
        "season": season,
        "episode": episode,
        "time_delta": timedelta(hours=2),
    }
    assert plan_summary_tasks(chronology.episode_transition, 3, 7) == tasks

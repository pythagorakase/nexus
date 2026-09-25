"""Plan narrative summaries atomically with their accepting transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Literal, Optional, Sequence


@dataclass(frozen=True)
class SummaryTask:
    """Description of a summary to generate."""

    kind: Literal["episode", "season"]
    season: int
    episode: Optional[int] = None


def plan_summary_tasks(
    episode_transition: str,
    parent_season: int,
    parent_episode: int,
) -> List[SummaryTask]:
    """
    Build the list of summaries that should run for a given episode transition.

    Args:
        episode_transition: One of "continue", "new_episode", or "new_season".
        parent_season: Season of the chunk that triggered the transition.
        parent_episode: Episode of the chunk that triggered the transition.

    Returns:
        List of SummaryTask objects describing the required summaries.
    """
    if episode_transition == "new_episode":
        return [
            SummaryTask(
                kind="episode",
                season=parent_season,
                episode=parent_episode,
            )
        ]

    if episode_transition == "new_season":
        return [
            SummaryTask(
                kind="episode",
                season=parent_season,
                episode=parent_episode,
            ),
            SummaryTask(kind="season", season=parent_season),
        ]

    return []


def schedule_summary_generation(
    tasks: Sequence[SummaryTask], *, cur: Any, session_id: str
) -> None:
    """Persist idempotent plans in the caller's accepting transaction."""
    if not tasks:
        return
    from nexus.config.story_model import resolve_enqueued_seat

    resolution = resolve_enqueued_seat("summaries.model", cur)
    for task in tasks:
        cur.execute(
            """INSERT INTO narrative_summary_jobs
            (kind, season, episode, generation_session_id, resolved_model, resolved_source)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (kind, season, episode) DO NOTHING""",
            (
                task.kind,
                task.season,
                task.episode,
                session_id,
                resolution.model,
                resolution.source,
            ),
        )

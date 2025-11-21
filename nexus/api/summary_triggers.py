"""
Helper utilities to trigger narrative summary generation after episode/season transitions.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, List, Literal, Optional, Sequence

from scripts.summarize_narrative import (
    DatabaseManager,
    SummaryGenerator,
    DEFAULT_MODEL,
    FALLBACK_MODEL,
)

logger = logging.getLogger("nexus.api.summary_triggers")


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
    tasks: Sequence[SummaryTask],
    overwrite: bool = False,
    model_candidates: Optional[Sequence[str]] = None,
) -> None:
    """
    Kick off background summary generation for the provided tasks.

    Args:
        tasks: Collection of summaries to generate.
        overwrite: Whether to regenerate existing summaries.
        model_candidates: Preferred models to try (fallback order).
    """
    if not tasks:
        return

    models = _coalesce_models(model_candidates)

    thread = threading.Thread(
        target=_run_summary_generation,
        args=(list(tasks), models, overwrite),
        daemon=True,
    )
    thread.start()


def _run_summary_generation(
    tasks: Sequence[SummaryTask],
    model_candidates: Sequence[str],
    overwrite: bool,
) -> None:
    try:
        db_manager = DatabaseManager()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Unable to start summary generation; database init failed: %s", exc)
        return

    for task in tasks:
        try:
            _run_single_task(task, db_manager, model_candidates, overwrite)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Summary generation failed for %s: %s", task, exc)


def _run_single_task(
    task: SummaryTask,
    db_manager: DatabaseManager,
    model_candidates: Sequence[str],
    overwrite: bool,
) -> None:
    if task.kind == "episode":
        if task.episode is None:
            logger.warning("Episode summary task missing episode value: %s", task)
            return
        if not overwrite and db_manager.episode_summary_exists(task.season, task.episode):
            logger.info(
                "Skipping summary for S%02dE%02d because one already exists",
                task.season,
                task.episode,
            )
            return
        runner: Callable[[SummaryGenerator], Optional[dict]] = (
            lambda gen: gen.generate_episode_summary(task.season, task.episode)
        )
        target_label = f"S{task.season:02d}E{task.episode:02d}"
    else:
        if not overwrite and db_manager.season_summary_exists(task.season):
            logger.info(
                "Skipping season summary for Season %s because one already exists",
                task.season,
            )
            return
        runner = lambda gen: gen.generate_season_summary(task.season)
        target_label = f"Season {task.season}"

    for index, model_name in enumerate(model_candidates):
        generator = SummaryGenerator(
            model=model_name,
            db_manager=db_manager,
            overwrite=overwrite,
            verbose=False,
            save_prompt=False,
            prompt_on_conflict=False,
        )
        summary = runner(generator)
        if summary:
            if index > 0:
                logger.info(
                    "Generated %s summary using fallback model %s", target_label, model_name
                )
            else:
                logger.info("Generated %s summary using model %s", target_label, model_name)
            return

        if index < len(model_candidates) - 1:
            logger.warning(
                "Model %s failed to generate %s summary; trying next candidate",
                model_name,
                target_label,
            )
    logger.error(
        "Failed to generate %s summary after trying %s",
        target_label,
        ", ".join(model_candidates),
    )


def _coalesce_models(model_candidates: Optional[Sequence[str]]) -> List[str]:
    models = (
        list(model_candidates) if model_candidates else [DEFAULT_MODEL, FALLBACK_MODEL]
    )
    deduped: List[str] = []

    for candidate in models:
        if candidate and candidate not in deduped:
            deduped.append(candidate)

    return deduped

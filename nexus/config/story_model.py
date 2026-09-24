"""One precedence and registry boundary for story model seats and budgets."""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
import logging
from typing import Any, Literal, Mapping

from psycopg2 import sql
from pydantic import BaseModel, ConfigDict, Field

from nexus.api.db_pool import get_connection
from nexus.config.loader import load_settings
from nexus.config.preferences import load_preferences, preferences_path
from nexus.config.settings_models import Settings


class StorySettings(BaseModel):
    """Nullable per-story pins stored in the singleton global_variables row."""

    model_config = ConfigDict(extra="forbid")

    slot: int | None = Field(default=None, exclude=True)
    dbname: str | None = Field(default=None, exclude=True)
    skald_model: str | None = None
    gaia_model: str | None = None
    apex_context_window: int | None = Field(default=None, ge=1000, strict=True)


def read_story_settings(dbname: str) -> StorySettings:
    """Read slot or explicitly named evaluation settings; DB errors propagate."""
    if dbname.startswith(("qa640_", "ref_")):
        from scripts.database_targets import evaluation_dbname
        from scripts.migrate import get_connection as get_evaluation_connection

        connection = closing(get_evaluation_connection(evaluation_dbname(dbname)))
    else:
        connection = get_connection(dbname=dbname)
    with connection as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT model, gaia_model, apex_context_window "
            "FROM global_variables WHERE id = TRUE"
        )
        row = cur.fetchone()
    if row is None:
        return StorySettings()
    return StorySettings(
        skald_model=row[0], gaia_model=row[1], apex_context_window=row[2], dbname=dbname
    )


def write_story_settings(cur: Any, patch: StorySettings) -> None:
    """Validate and persist explicit pins on the caller's transaction."""
    updates = patch.model_dump(exclude_unset=True)
    if not updates:
        raise ValueError("No story settings provided")
    settings = load_settings()
    for key in ("skald_model", "gaia_model"):
        if updates.get(key) is not None:
            settings.resolve_model_ref(updates[key])
    columns = {
        "skald_model": "model",
        "gaia_model": "gaia_model",
        "apex_context_window": "apex_context_window",
    }
    assignments = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(columns[key])) for key in updates
    )
    cur.execute(
        sql.SQL("UPDATE global_variables SET {} WHERE id = TRUE").format(assignments),
        tuple(updates.values()),
    )
    if cur.rowcount != 1:
        raise RuntimeError("Story settings row is missing")


SeatPolicy = Literal["fixed", "follow_story"]
SeatSource = Literal[
    "request",
    "story_pin",
    "story_follow",
    "player_preference",
    "seat_default",
    "repository_default",
]
AUXILIARY_SEATS = (
    "orrery.experiences.model",
    "storyteller.correspondence.compaction_model",
    "orrery.retrograde.maturation.model_ref",
    "ir_eval.judgment.model",
    "global.model.default_model",
    "summaries.model",
)


@dataclass(frozen=True)
class SeatResolution:
    """Literal dispatch identity captured before a turn or job can be repinned."""

    seat: str
    model: str
    provider: str
    policy: SeatPolicy
    source: SeatSource
    slot: int | None = None
    dbname: str | None = None


def resolve_seat(
    seat: str,
    *,
    settings: Settings | None = None,
    story: StorySettings | None = None,
    override: str | None = None,
) -> SeatResolution:
    """Resolve one declared seat and validate its registry and provider boundary."""
    settings = settings or load_settings()
    seat = {
        "ir_eval": "ir_eval.judgment.model",
        "experience_renderer": "orrery.experiences.model",
        "summaries": "summaries.model",
    }.get(seat, seat)
    policy: SeatPolicy = "follow_story"
    default = settings.apex.model
    if seat in AUXILIARY_SEATS:
        container: Any = settings
        *parts, field = seat.split(".")
        for part in parts:
            container = getattr(container, "global_" if part == "global" else part)
        policy = getattr(container, field + "_policy")
        default = getattr(container, field)
    elif seat == "gaia":
        default = settings.apex.gaia_model or settings.apex.model
    elif seat not in {"skald", "wizard"}:
        if override is None:
            raise ValueError(f"Unknown model seat {seat!r}")
        policy = "fixed"
    model = override
    source: SeatSource = "request"
    if model is None and story is not None:
        if seat in {"skald", "wizard", "gaia"}:
            model = story.gaia_model if seat == "gaia" else story.skald_model
            source = "story_pin"
            if seat == "gaia" and model is None:
                model = resolve_seat("skald", settings=settings, story=story).model
                source = "story_follow"
        elif policy == "follow_story":
            model = resolve_seat("skald", settings=settings, story=story).model
            source = "story_follow"
    if model is None and seat == "wizard":
        model = load_preferences(settings).wizard_model
        source = (
            "player_preference"
            if preferences_path(settings).exists()
            else "repository_default"
        )
    if model is None:
        model = default
        source = "seat_default" if seat in AUXILIARY_SEATS else "repository_default"
    try:
        if model is None:
            raise ValueError("Seat has no configured model")
        selected = settings.resolve_model_ref(model)
    except ValueError as exc:
        raise ValueError(
            f"Cannot resolve {seat} model {model!r}: absent from the registry. "
            "Clear or replace the story pin with nexus model --slot N --clear."
        ) from exc
    provider = settings.provider_for_model(selected)
    # JudgmentEngine uses the native OpenAI Responses parser directly.
    if (
        seat == "ir_eval.judgment.model"
        and policy == "follow_story"
        and provider != "openai"
    ):
        raise ValueError(f"{seat} requires OpenAI structured output; got {provider!r}")
    entry = settings.model_entry(selected).require_window_capabilities()
    if (
        seat in {"skald", "gaia", "wizard"}
        and story is not None
        and story.apex_context_window is not None
    ):
        from nexus.config.seat_window import resolve_seat_window

        window = resolve_seat_window(
            settings.model_dump(),
            selected,
            seat="gaia" if seat == "gaia" else "skald_writer",
            window=entry.context_window,
        )
        maximum = window.input_ceiling + window.policy_headroom
        if story.apex_context_window > maximum:
            raise ValueError(
                f"Story window {story.apex_context_window} exceeds model {selected!r} max_input_tokens {maximum}"
            )
    return SeatResolution(
        seat,
        selected,
        provider,
        policy,
        source,
        story.slot if story else None,
        story.dbname if story else None,
    )


def resolve_story_model(
    seat: str,
    *,
    settings: Settings | None = None,
    story: StorySettings | None = None,
    override: str | None = None,
) -> str:
    """Compatibility wrapper for callers needing only the literal model ID."""
    return resolve_seat(seat, settings=settings, story=story, override=override).model


def resolve_enqueued_seat(
    seat: str,
    cur: Any,
    *,
    settings: Mapping[str, Any] | None = None,
    slot: int | None = None,
) -> SeatResolution:
    """Capture pins on the accepting transaction, serialized against repinning."""
    if settings is None:
        typed = load_settings()
    elif "global" in settings:
        typed = Settings.model_validate(
            {
                k: v
                for k, v in settings.items()
                if k not in {"Agent Settings", "API Settings"}
            }
        )
    else:
        # Accepting experience callers already hold the Orrery subsection.
        complete = load_settings().model_dump()

        def merge(target: dict[str, Any], updates: Mapping[str, Any]) -> None:
            for key, value in updates.items():
                if isinstance(value, Mapping) and isinstance(target.get(key), dict):
                    merge(target[key], value)
                else:
                    target[key] = value

        merge(complete["orrery"], settings.get("orrery", settings))
        typed = Settings.model_validate(complete)
    cur.execute(
        "SELECT model, gaia_model, apex_context_window FROM global_variables WHERE id = TRUE FOR SHARE"
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Enqueued model resolution requires story settings")
    values = list(row.values()) if isinstance(row, Mapping) else row
    story = StorySettings(
        skald_model=values[0],
        gaia_model=values[1],
        apex_context_window=values[2],
        slot=slot,
        dbname=cur.connection.info.dbname,
    )
    return resolve_seat(seat, settings=typed, story=story)


def persisted_job_model(job: Mapping[str, Any], *, table: str) -> str:
    """Require a durable literal model; legacy jobs need explicit remediation."""
    job_id = job.get("job_id", job.get("id"))
    model, source = job.get("resolved_model"), job.get("resolved_source")
    if not model or not source:
        raise RuntimeError(
            f"{table} job {job_id} has NULL resolved_model/resolved_source"
        )
    logging.getLogger(__name__).info(
        "%s job %s uses persisted model=%s source=%s", table, job_id, model, source
    )
    return str(model)


def story_context_settings(
    settings: dict[str, Any], story: StorySettings, *, override: int | None = None
) -> dict[str, Any]:
    """Copy settings with the per-story window used for sizing and fingerprints."""
    resolved = deepcopy(settings)
    window = override if override is not None else story.apex_context_window
    if window is None:
        return resolved
    StorySettings(apex_context_window=window)
    for lore in (
        resolved.get("lore"),
        resolved.get("Agent Settings", {}).get("LORE"),
    ):
        if lore is not None:
            lore["token_budget"]["apex_context_window"] = window
            # An explicit story window outranks repository resource defaults.
            lore["token_budget"]["provider_overrides"] = {}
    return resolved

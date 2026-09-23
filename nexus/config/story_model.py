"""One precedence and registry boundary for story model seats and budgets."""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nexus.api.db_pool import get_connection
from nexus.config.loader import load_settings
from nexus.config.preferences import load_preferences
from nexus.config.settings_models import Settings


class StorySettings(BaseModel):
    """Nullable per-story pins stored in the singleton global_variables row."""

    model_config = ConfigDict(extra="forbid")

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
        skald_model=row[0], gaia_model=row[1], apex_context_window=row[2]
    )


def resolve_story_model(
    seat: str,
    *,
    settings: Settings | None = None,
    story: StorySettings | None = None,
    override: str | None = None,
) -> str:
    """Resolve request > story > player preference > repository default.

    Only the wizard has a player preference. A story's null Gaia pin follows
    its resolved Skald; without a story, the repository Gaia default applies.
    Every selected ID is validated before a provider can be constructed.
    """
    settings = settings or load_settings()
    if seat not in {"skald", "gaia", "wizard"} and (
        story is not None or override is None
    ):
        raise ValueError(
            f"Developer seat {seat!r} requires an explicit configured model"
        )
    model = override
    if model is None and story is not None:
        model = story.gaia_model if seat == "gaia" else story.skald_model
        if seat == "gaia" and model is None:
            model = resolve_story_model("skald", settings=settings, story=story)
    if model is None:
        if seat == "wizard":
            model = load_preferences(settings).wizard_model
        elif seat == "gaia":
            model = settings.apex.gaia_model or settings.apex.model
        else:
            model = settings.apex.model
    try:
        return settings.resolve_model_ref(model)
    except ValueError as exc:
        raise ValueError(
            f"Cannot resolve {seat} model {model!r}: absent from the registry. "
            "Clear or replace the story pin with nexus model --slot N --clear."
        ) from exc


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

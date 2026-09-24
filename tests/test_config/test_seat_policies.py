"""Policy/source contracts against the actual repository model registry."""

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from nexus.config import load_settings
from nexus.config.preferences import save_preferences
from nexus.config.settings_models import Settings
from nexus.config.story_model import (
    AUXILIARY_SEATS,
    StorySettings,
    persisted_job_model,
    resolve_seat,
)


def seat_container(settings, seat):
    """Return the real Pydantic container and model field for a declared seat."""
    *parts, field = seat.split(".")
    for part in parts:
        settings = getattr(settings, "global_" if part == "global" else part)
    return settings, field


@pytest.mark.parametrize("seat", AUXILIARY_SEATS)
@pytest.mark.parametrize("policy", ["fixed", "follow_story"])
@pytest.mark.parametrize("has_story", [False, True])
def test_auxiliary_policy_sources(seat, policy, has_story):
    """Fixed seats ignore pins; following seats capture the literal story ID."""
    settings = load_settings().model_copy(deep=True)
    container, field = seat_container(settings, seat)
    setattr(container, field + "_policy", policy)
    # Judgment's existing native OpenAI parser requires an OpenAI story pin.
    pin = settings.apex.model if seat == "ir_eval.judgment.model" else "TEST"
    story = StorySettings(skald_model=pin, slot=4, dbname="qa640_policy")
    result = resolve_seat(seat, settings=settings, story=story if has_story else None)
    follows = has_story and policy == "follow_story"
    assert result.model == (pin if follows else getattr(container, field))
    assert result.source == ("story_follow" if follows else "seat_default")
    assert result.policy == policy
    assert result.provider == settings.provider_for_model(result.model)
    assert result.slot == (4 if has_story else None)
    assert result.dbname == ("qa640_policy" if has_story else None)
    with pytest.raises(FrozenInstanceError):
        result.model = "invalid"
    override = settings.apex.model
    requested = resolve_seat(seat, settings=settings, story=story, override=override)
    assert (requested.model, requested.source) == (override, "request")


def test_story_sources_and_player_preference(tmp_path):
    """Cover request, pins, following, preferences, and repository defaults."""
    settings = load_settings().model_copy(deep=True)
    settings.runtime.state_dir = str(tmp_path)
    assert resolve_seat("wizard", settings=settings).source == "repository_default"
    save_preferences({"wizard_model": "TEST"}, settings)
    assert resolve_seat("wizard", settings=settings).source == "player_preference"
    assert resolve_seat("skald", settings=settings).source == "repository_default"
    assert resolve_seat("gaia", settings=settings).source == "repository_default"
    story = StorySettings(skald_model="TEST")
    assert resolve_seat("skald", settings=settings, story=story).source == "story_pin"
    assert resolve_seat("wizard", settings=settings, story=story).source == "story_pin"
    assert resolve_seat("gaia", settings=settings, story=story).source == "story_follow"
    story.gaia_model = settings.apex.model
    assert resolve_seat("gaia", settings=settings, story=story).source == "story_pin"
    assert resolve_seat("skald", story=story, override="TEST").source == "request"


@pytest.mark.parametrize(
    "seat",
    [
        "orrery.experiences.model",
        "storyteller.correspondence.compaction_model",
        "summaries.model",
    ],
)
def test_following_seat_rejects_unregistered_pin(seat):
    """A bad pin fails before enqueue or provider construction."""
    with pytest.raises(ValueError, match="absent from the registry"):
        resolve_seat(seat, story=StorySettings(skald_model="unregistered-pin"))


def test_judgment_follow_policy_rejects_incompatible_story():
    """The native Responses parser is the one restricted auxiliary path."""
    settings = load_settings().model_copy(deep=True)
    settings.ir_eval.judgment.model_policy = "follow_story"
    with pytest.raises(ValueError, match="requires OpenAI structured output"):
        resolve_seat(
            "ir_eval.judgment.model",
            settings=settings,
            story=StorySettings(skald_model="TEST"),
        )
    settings.apex.model = "TEST"
    with pytest.raises(ValidationError, match="requires OpenAI structured output"):
        Settings.model_validate(settings.model_dump())


def test_policy_typing_rejects_undeclared_value():
    """Policy typos fail configuration loading rather than selecting a model."""
    settings = load_settings().model_dump()
    settings["orrery"]["experiences"]["model_policy"] = "automatic"
    with pytest.raises(ValidationError, match="fixed.*follow_story"):
        Settings.model_validate(settings)


@pytest.mark.parametrize(
    "table",
    [
        "character_experience_jobs",
        "orrery_maturation_jobs",
        "correspondence_compaction_jobs",
        "narrative_summary_jobs",
    ],
)
def test_legacy_job_requires_literal_resolution(table):
    """Nullable migration columns never imply a runtime fallback."""
    with pytest.raises(RuntimeError, match=f"{table} job 42 has NULL"):
        persisted_job_model(
            {"id": 42, "resolved_model": None, "resolved_source": None}, table=table
        )


def test_developer_judgment_without_story_uses_seat_default():
    """Developer calls need no artificial request override to select their seat."""
    from ir_eval.engine.judge import JudgmentEngine

    engine = JudgmentEngine()
    assert engine.resolution.source == "seat_default"
    assert engine.model == load_settings().ir_eval.judgment.model
    assert engine._provider is None


def test_compaction_route_uses_persisted_model_without_resolving_story():
    """A changed or retired pin cannot affect a previously resolved job route."""
    from nexus.agents.lore.logon_utility import LogonUtility
    from nexus.config import load_settings_as_dict

    utility = LogonUtility(
        load_settings_as_dict(),
        persisted_model="TEST",
        story_settings=StorySettings(skald_model="unregistered-after-enqueue"),
    )
    assert utility.resolve_storyteller_route() == ("TEST", "local", "test")
    with pytest.raises(ValueError, match="persisted model"):
        LogonUtility(
            load_settings_as_dict(), persisted_model="TEST", model_override="TEST"
        )

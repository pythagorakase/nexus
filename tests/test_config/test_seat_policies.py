"""Policy/source contracts against the actual repository model registry."""

from dataclasses import FrozenInstanceError
import re
from typing import Any

import pytest
from pydantic import ValidationError

from nexus.config import load_settings
from nexus.config.preferences import save_preferences
from nexus.config.settings_models import GaiaSeatPolicy, Settings
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


def _registry_entry(raw: dict[str, Any], model: str) -> dict[str, Any]:
    """Return one raw roster entry from a dumped settings document."""
    return next(
        entry
        for provider in raw["global"]["model"]["api_models"].values()
        for entry in provider["models"]
        if entry["id"] == model
    )


def _other_openai_model(settings: Settings) -> str:
    """Pick a registered OpenAI model that is not the configured Skald default."""
    return next(
        entry.id
        for entry in settings.global_.model.api_models["openai"].models
        if entry.id != settings.apex.model
    )


def test_gaia_profile_requires_a_declared_reasoning_effort():
    """[apex.gaia] carries its own validated effort, never an inherited one."""
    assert isinstance(load_settings().apex.gaia, GaiaSeatPolicy)
    raw = load_settings().model_dump()
    raw["apex"]["gaia"]["reasoning_effort"] = "extreme"
    with pytest.raises(ValidationError, match="apex.gaia.reasoning_effort"):
        Settings.model_validate(raw)
    del raw["apex"]["gaia"]["reasoning_effort"]
    with pytest.raises(ValidationError, match="apex.gaia.reasoning_effort"):
        Settings.model_validate(raw)


@pytest.mark.parametrize("param", ["reasoning_effort", "reasoning"])
def test_gaia_default_model_rejecting_effort_fails_settings_load(param):
    """A Gaia model that rejects or strips effort fails at load, not at a turn."""
    raw = load_settings().model_dump()
    gaia_model = raw["apex"]["gaia_model"] or raw["apex"]["model"]
    _registry_entry(raw, gaia_model)["unsupported_params"].append(param)
    message = f"[apex.gaia] configures reasoning_effort, but model '{gaia_model}' "
    with pytest.raises(ValidationError, match=re.escape(message) + ".*" + param):
        Settings.model_validate(raw)


def test_gaia_default_model_without_reasoning_fails_settings_load():
    """A declared non-reasoning Gaia model cannot silently drop the effort."""
    raw = load_settings().model_dump()
    gaia_model = raw["apex"]["gaia_model"] or raw["apex"]["model"]
    _registry_entry(raw, gaia_model)["reasoning_accounting"] = "none"
    with pytest.raises(ValidationError, match="reasoning_accounting = 'none'"):
        Settings.model_validate(raw)


def test_pinned_gaia_model_is_checked_in_place_of_the_skald_default():
    """With apex.gaia_model set, load validates that pin against the profile."""
    settings = load_settings()
    raw = settings.model_dump()
    pinned = _other_openai_model(settings)
    raw["apex"]["gaia_model"] = pinned
    assert Settings.model_validate(raw).apex.gaia_model == pinned
    _registry_entry(raw, pinned)["unsupported_params"].append("reasoning_effort")
    with pytest.raises(ValidationError, match=re.escape(f"model '{pinned}'")):
        Settings.model_validate(raw)


def test_test_provider_gaia_stays_self_contained():
    """The TEST mock declares no reasoning and remains a valid Gaia default."""
    raw = load_settings().model_dump()
    raw["apex"]["model"] = "TEST"
    assert Settings.model_validate(raw).apex.model == "TEST"
    story = StorySettings(skald_model="TEST")
    assert resolve_seat("gaia", story=story).model == "TEST"


@pytest.mark.parametrize("route", ["story_pin", "story_follow"])
def test_gaia_story_route_rejecting_effort_fails_seat_resolution(route):
    """Pins and slot following are checked where the Gaia model is resolved."""
    settings = load_settings().model_copy(deep=True)
    rejecting = _other_openai_model(settings)
    settings.model_entry(rejecting).unsupported_params.append("reasoning_effort")
    story = (
        StorySettings(skald_model=settings.apex.model, gaia_model=rejecting)
        if route == "story_pin"
        else StorySettings(skald_model=rejecting)
    )
    message = f"[apex.gaia] ({route}) configures reasoning_effort"
    with pytest.raises(ValueError, match=re.escape(message)):
        resolve_seat("gaia", settings=settings, story=story)

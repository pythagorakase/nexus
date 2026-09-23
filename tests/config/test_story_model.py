"""Exercise scoped resolution with real settings and explicit story snapshots."""

from pathlib import Path

import pytest

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.config import load_settings, load_settings_as_dict
from nexus.config.preferences import save_preferences
from nexus.config.story_model import (
    StorySettings,
    resolve_story_model,
    story_context_settings,
)
from nexus.memory.manager import resolve_storyteller_context_window


def test_story_model_precedence_without_database(tmp_path: Path) -> None:
    """Only the next-story seat consumes player preferences."""
    settings = load_settings().model_copy(deep=True)
    settings.runtime.state_dir = str(tmp_path)
    save_preferences({"wizard_model": "TEST"}, settings)
    story = StorySettings(skald_model=settings.apex.model)
    assert resolve_story_model("wizard", settings=settings) == "TEST"
    assert (
        resolve_story_model("wizard", settings=settings, story=story)
        == story.skald_model
    )
    assert resolve_story_model("skald", settings=settings) == settings.apex.model
    assert (
        resolve_story_model("gaia", settings=settings, story=story) == story.skald_model
    )
    assert (
        resolve_story_model("skald", settings=settings, story=story, override="TEST")
        == "TEST"
    )
    story.gaia_model = "TEST"
    assert resolve_story_model("gaia", settings=settings, story=story) == "TEST"


@pytest.mark.parametrize(
    "seat,pin",
    [("skald", "skald_model"), ("wizard", "skald_model"), ("gaia", "gaia_model")],
)
def test_retired_model_pin_never_resolves(seat: str, pin: str) -> None:
    """A registry miss is an error at the common boundary."""
    story = StorySettings(**{pin: "retired-fixture-id"})
    with pytest.raises(ValueError, match="absent from the registry"):
        resolve_story_model(seat, story=story)
    assert resolve_story_model(seat, story=story, override="TEST") == "TEST"


def test_logon_route_accepts_explicit_story_snapshot() -> None:
    """Resolve the real TEST route without consulting a live slot or constructing a client."""
    utility = LogonUtility(
        load_settings_as_dict(), story_settings=StorySettings(skald_model="TEST")
    )
    model, wire, provider = utility.resolve_storyteller_route()
    assert (model, wire, provider) == ("TEST", "local", "test")
    assert utility.provider is None


def test_story_context_window_outranks_repository_resource_profile() -> None:
    """A story's explicit budget wins for each seat without changing shared defaults."""
    defaults = load_settings_as_dict()
    before = resolve_storyteller_context_window(defaults, "local", "local")
    scoped = story_context_settings(
        defaults, StorySettings(apex_context_window=100_000)
    )
    assert resolve_storyteller_context_window(scoped, "local", "local") == 100_000
    assert resolve_storyteller_context_window(scoped, "openai", "openai") == 100_000
    assert resolve_storyteller_context_window(defaults, "local", "local") == before


@pytest.mark.parametrize("model", ["retired-evaluation-id", None])
def test_ir_evaluation_model_fails_at_registry_boundary(model: str | None) -> None:
    """Invalid developer seats fail before a provider or API credential is needed."""
    from ir_eval.engine.judge import JudgmentEngine

    with pytest.raises(
        ValueError, match="absent from the registry|explicit configured model"
    ):
        JudgmentEngine(model=model)


def test_ir_evaluation_model_resolves_configured_developer_seat() -> None:
    """The configured evaluation model crosses the same registry boundary."""
    from ir_eval.engine.judge import JudgmentEngine

    model = load_settings().ir_eval.judgment.model
    engine = JudgmentEngine(model=model)
    assert engine.model == model
    assert engine._provider is None

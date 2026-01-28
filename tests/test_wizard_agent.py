"""Unit tests for wizard agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from pydantic_ai import CallDeferred, ModelRetry

from nexus.api import wizard_agent as wizard_module
from nexus.api.new_story_schemas import (
    CharacterConceptSubmission,
    CharacterCreationState,
    Genre,
    LayerDefinition,
    LayerType,
    PlaceProfile,
    SettingCard,
    StartingScenario,
    StorySeed,
    StorySeedType,
    StoryTimestamp,
    TechLevel,
    TraitRationales,
    TraitSelection,
    TraitSuggestion,
    WildcardTrait,
    ZoneDefinition,
)
from nexus.api.wizard_agent import (
    ACCEPT_FATE_SIGNAL,
    WizardContext,
    build_wizard_prompt,
    submit_character_concept,
    submit_starting_scenario,
    submit_trait_selection,
    submit_wildcard_trait,
    submit_world_document,
)


@dataclass
class DummyTrait:
    id: int
    name: str
    description: str
    is_selected: bool = False
    rationale: str = ""


class DummyRunContext:
    def __init__(self, deps: WizardContext, retry: int = 0):
        self.deps = deps
        self.retry = retry


def make_context(phase: str, context_data=None) -> WizardContext:
    return WizardContext(
        slot=1,
        cache=object(),
        phase=phase,
        thread_id="thread-1",
        model="gpt-5.1",
        context_data=context_data,
    )


def sample_setting() -> SettingCard:
    return SettingCard(
        genre=Genre.FANTASY,
        secondary_genres=[],
        world_name="Test Realm",
        time_period="Late medieval",
        tech_level=TechLevel.MEDIEVAL,
        magic_exists=True,
        magic_description="Leyline sorcery",
        political_structure="City-states",
        major_conflict="A succession crisis",
        tone="balanced",
        themes=["duty", "betrayal"],
        cultural_notes="Guild politics dominate daily life.",
        geographic_scope="regional",
        diegetic_artifact=(
            "Excerpt from the Guild Ledger: The council convenes nightly to weigh the "
            "rumors of rebellion among the northern vassals."
        ),
    )


def sample_concept_submission() -> CharacterConceptSubmission:
    return CharacterConceptSubmission(
        archetype="Reluctant heir",
        background=(
            "Raised in exile after the fall of their house, trained in secret by loyal "
            "retainers who still dream of restoration."
        ),
        name="Seren Vale",
        appearance=(
            "Lean and sharp-eyed, with windburned skin, braided dark hair, and a scar "
            "cutting across their left brow."
        ),
        suggested_traits=[
            TraitSuggestion(
                name="allies",
                rationale="Their survival depends on a scattered network of loyalists.",
            ),
            TraitSuggestion(
                name="obligations",
                rationale="They carry a vow to reclaim the throne for their people.",
            ),
        ],
    )


def sample_trait_selection() -> TraitSelection:
    return TraitSelection(
        selected_traits=["allies", "contacts", "patron"],
        trait_rationales=TraitRationales(
            allies="Trusted scouts keep them informed.",
            contacts="Black-market couriers relay messages.",
            patron="A hidden noble bankrolls their cause.",
        ),
        suggested_by_llm=["allies", "obligations"],
    )


def sample_wildcard() -> WildcardTrait:
    return WildcardTrait(
        wildcard_name="Moon-silver Blade",
        wildcard_description=(
            "An ancestral weapon that resonates with forgotten oaths, responding to "
            "acts of courage and sacrifice."
        ),
    )


def sample_starting_scenario() -> StartingScenario:
    seed = StorySeed(
        seed_type=StorySeedType.CRISIS,
        title="Ashes of the Regency",
        situation=(
            "On the eve of a coronation, the regent disappears, leaving the capital "
            "in chaos as rival factions scramble for control."
        ),
        hook="A sealed letter names you as the regent's final envoy.",
        immediate_goal="Reach the regent's hidden sanctum before the coup begins.",
        stakes="Civil war will erupt if the regent's plans remain lost.",
        tension_source="Assassins are already hunting the regent's confidants.",
        base_timestamp=StoryTimestamp(year=1382, month=10, day=3, hour=18, minute=15),
        weather="Cold rain and distant thunder",
        key_npcs=["Captain Orrin", "Archivist Lysa"],
        secrets=(
            "The regent staged the disappearance to expose traitors. The captain is "
            "a double agent, while the archivist holds the true seal of succession."
        ),
    )
    layer = LayerDefinition(
        name="Aetheris",
        type=LayerType.PLANET,
        description="A storm-swept world where city-states cling to ancient ley lines.",
    )
    zone = ZoneDefinition(
        name="Regent's Reach",
        summary="A fog-laced delta packed with trade hubs and rival guild houses.",
    )
    place = PlaceProfile(
        name="The Glass Arsenal",
        place_type="fixed_location",
        summary=(
            "A crystalline armory perched above the docks, echoing with the hum of "
            "stored enchantments and the clang of restless smiths."
        ),
        history="Built after the last succession war to secure the regalia.",
        current_status="Under lockdown as rumors of treason spread.",
        secrets="Hidden chambers below hold the regent's emergency vault.",
        inhabitants=["Armorer Nyx", "Dock guard patrol"],
        latitude=48.8566,
        longitude=2.3522,
    )
    return StartingScenario(seed=seed, layer=layer, zone=zone, location=place)


def test_build_wizard_prompt_includes_trait_menu_and_accept_fate(monkeypatch):
    monkeypatch.setattr(wizard_module, "_load_base_prompt", lambda: "BASE")
    monkeypatch.setattr(wizard_module, "_load_trait_menu", lambda: "TRAIT MENU")

    context = make_context(phase="character")
    context.accept_fate = True

    prompt = build_wizard_prompt(SimpleNamespace(deps=context))

    assert "BASE" in prompt
    assert "Trait Reference" in prompt
    assert "TRAIT MENU" in prompt
    assert ACCEPT_FATE_SIGNAL in prompt


@pytest.mark.asyncio
async def test_submit_world_document_rejects_wrong_phase():
    ctx = DummyRunContext(make_context(phase="character"))
    with pytest.raises(ModelRetry):
        await submit_world_document(ctx, sample_setting())


@pytest.mark.asyncio
async def test_submit_world_document_sets_tool_result(monkeypatch):
    monkeypatch.setattr(wizard_module, "record_drafts", lambda *args, **kwargs: None)

    ctx = DummyRunContext(make_context(phase="setting"))
    with pytest.raises(CallDeferred):
        await submit_world_document(ctx, sample_setting())

    result = ctx.deps.last_tool_result
    assert result["artifact_type"] == "submit_world_document"
    assert result["phase_complete"] is True


@pytest.mark.asyncio
async def test_submit_character_concept_sets_trait_menu(monkeypatch):
    monkeypatch.setattr(wizard_module, "record_drafts", lambda *args, **kwargs: None)
    monkeypatch.setattr(wizard_module, "write_suggested_traits", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        wizard_module,
        "get_trait_menu",
        lambda _dbname: [
            DummyTrait(1, "allies", "Trusted supporters"),
            DummyTrait(2, "contacts", "Information network"),
            DummyTrait(3, "patron", "Secret benefactor"),
        ],
    )
    monkeypatch.setattr(wizard_module, "get_selected_trait_count", lambda _dbname: 0)
    monkeypatch.setattr(wizard_module, "slot_dbname", lambda _slot: "save_01")

    ctx = DummyRunContext(make_context(phase="character"))
    with pytest.raises(CallDeferred):
        await submit_character_concept(ctx, sample_concept_submission())

    result = ctx.deps.last_tool_result
    assert result["artifact_type"] == "submit_character_concept"
    assert result["subphase"] == "traits"
    assert result["trait_menu"]
    assert result["can_confirm"] is False


@pytest.mark.asyncio
async def test_submit_trait_selection_advances_state(monkeypatch):
    monkeypatch.setattr(wizard_module, "record_drafts", lambda *args, **kwargs: None)
    monkeypatch.setattr(wizard_module, "clear_suggested_traits", lambda *args, **kwargs: None)
    monkeypatch.setattr(wizard_module, "slot_dbname", lambda _slot: "save_01")

    concept = sample_concept_submission().to_character_concept()
    state = CharacterCreationState(concept=concept)
    ctx = DummyRunContext(
        make_context(phase="character", context_data={"character_state": state.model_dump()})
    )

    with pytest.raises(CallDeferred):
        await submit_trait_selection(ctx, sample_trait_selection())

    result = ctx.deps.last_tool_result
    assert result["artifact_type"] == "submit_trait_selection"
    assert result["phase_complete"] is False


@pytest.mark.asyncio
async def test_submit_wildcard_trait_completes_character(monkeypatch):
    monkeypatch.setattr(wizard_module, "record_drafts", lambda *args, **kwargs: None)
    monkeypatch.setattr(wizard_module, "slot_dbname", lambda _slot: "save_01")

    concept = sample_concept_submission().to_character_concept()
    state = CharacterCreationState(
        concept=concept,
        trait_selection=sample_trait_selection(),
        summary="A determined heir reclaiming a lost realm.",
    )
    ctx = DummyRunContext(
        make_context(phase="character", context_data={"character_state": state.model_dump()})
    )

    with pytest.raises(CallDeferred):
        await submit_wildcard_trait(ctx, sample_wildcard())

    result = ctx.deps.last_tool_result
    assert result["artifact_type"] == "submit_wildcard_trait"
    assert result["phase_complete"] is True


@pytest.mark.asyncio
async def test_submit_starting_scenario_sets_tool_result(monkeypatch):
    monkeypatch.setattr(wizard_module, "record_drafts", lambda *args, **kwargs: None)

    ctx = DummyRunContext(make_context(phase="seed"))
    with pytest.raises(CallDeferred):
        await submit_starting_scenario(ctx, sample_starting_scenario())

    result = ctx.deps.last_tool_result
    assert result["artifact_type"] == "submit_starting_scenario"
    assert result["phase_complete"] is True

"""Tests for wizard-time Retrograde orchestration."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from nexus.agents.orrery.retrograde_expansion import (
    RetrogradeExpansionValidationError,
    validate_expansion_plan,
)
from nexus.agents.orrery.retrograde_orchestrator import (
    RetrogradeGenerationBundle,
    RetrogradePersistenceBlockedError,
    RetrogradeStageTiming,
    build_wizard_history_surface,
    generate_retrograde_history,
    get_retrograde_progress,
    persist_retrograde_history,
    record_retrograde_progress,
    reset_retrograde_progress,
)
from nexus.agents.orrery.retrograde_packet import build_retrograde_dry_run_packet
from nexus.api.trait_compiler_schemas import TraitCompileInputs
from nexus.config import load_settings
from nexus.config.settings_models import Settings
from test_orrery.test_retrograde_packet import FakeRetrogradeCache
from test_orrery.test_retrograde_persistence import (
    FakeRetrogradePersistenceCursor,
    _packet,
    _persistence_test_vocabulary,
    _seed_response,
    _seed_response_base,
    _valid_expansion,
)


def test_progress_registry_round_trip() -> None:
    """Progress entries accumulate per slot and reset cleanly."""

    reset_retrograde_progress(4)
    assert get_retrograde_progress(4) is None

    record_retrograde_progress(4, "packet", {})
    record_retrograde_progress(4, "seed_candidates", {"weird": "medium"})
    progress = get_retrograde_progress(4)
    assert progress is not None
    assert progress["stage"] == "seed_candidates"
    assert progress["detail"] == {"weird": "medium"}
    assert [item["stage"] for item in progress["stages"]] == [
        "packet",
        "seed_candidates",
    ]

    reset_retrograde_progress(4)
    assert get_retrograde_progress(4) is None


def test_transition_run_reports_idle_before_its_first_fallible_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A retry never re-reports the previous attempt's terminal stage.

    Stage pollers stop on "failed", so a stale record read while the new run
    derives trait inputs (or fails before its first stage) would freeze the
    waiter on the old failure.
    """

    from nexus.api.new_story_flow import perform_transition_with_retrograde
    from nexus.api.new_story_schemas import TransitionData

    record_retrograde_progress(5, "failed", {"stage": "persistence"})
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(tmp_path / "unreadable.toml"))
    try:
        with pytest.raises(FileNotFoundError, match="unreadable.toml"):
            perform_transition_with_retrograde(5, TransitionData.model_construct())
        assert get_retrograde_progress(5) is None
    finally:
        reset_retrograde_progress(5)


def test_progress_registry_rejects_unknown_stage() -> None:
    """Stage names outside the published vocabulary fail loudly."""

    with pytest.raises(ValueError, match="Unknown Retrograde wizard stage"):
        record_retrograde_progress(4, "weaving_intensifies", {})


def test_generate_retrograde_history_composes_stage_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generation pass composes packet, seed, and expansion stages."""

    vocabulary = _persistence_test_vocabulary()
    packet = {
        **_packet(vocabulary),
        "weird": {"level": "medium", "genre": "cyberpunk", "raw_midpoint": 0.5},
    }
    seed_response = _seed_response(vocabulary)
    expansion = _valid_expansion(vocabulary)

    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_vocabulary.enumerate_seed_eligible_vocabulary",
        lambda dbname=None: vocabulary,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_packet.build_retrograde_dry_run_packet",
        lambda **kwargs: packet,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_seed_candidates.run_seed_stage",
        lambda **kwargs: {
            "model": "test-model",
            "selection_model": "test-model",
            "prompt_chars": 100,
            "selection_prompt_chars": 50,
            "seed_candidate_response": seed_response,
        },
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_expansion.generate_expansion_with_skald",
        lambda **kwargs: {
            "model": "test-model",
            "prompt_chars": 100,
            "retrograde_expansion_plan": expansion,
        },
    )

    stages: list[str] = []
    bundle = generate_retrograde_history(
        slot=5,
        dbname="save_05",
        cache=object(),
        settings=load_settings(),
        model_name="test-model",
        progress=lambda stage, detail: stages.append(stage),
    )

    assert stages == ["packet", "seed_candidates", "expansion"]
    assert bundle.slot == 5
    assert bundle.model == "test-model"
    assert bundle.weird["level"] == "medium"
    assert bundle.seed_candidate_response == seed_response
    assert bundle.expansion_plan == expansion
    assert [timing.stage for timing in bundle.timings] == [
        "packet",
        "seed_candidates",
        "expansion",
    ]


def test_persist_retrograde_history_executes_when_clear() -> None:
    """A clear plan executes canonical writes and returns the manifest."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    bundle = _bundle(vocabulary)

    manifest = persist_retrograde_history(
        cur,
        bundle=bundle,
        settings=load_settings(),
    )

    assert manifest["dry_run"] is False
    assert manifest["counters"]["events_inserted"] == 1
    assert manifest["counters"]["entity_tags_inserted"] == 2
    assert manifest["counters"]["pair_tags_inserted"] == 1
    assert manifest["counters"]["relationships_inserted"] == 1
    assert manifest["retrieval"]["embedding_pending_summary_ids"]


def test_persist_retrograde_history_raises_on_blockers() -> None:
    """Execute blockers abort persistence before any canonical write."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        include_retrograde_sources=False,
    )
    bundle = _bundle(vocabulary)

    with pytest.raises(RetrogradePersistenceBlockedError) as exc_info:
        persist_retrograde_history(
            cur,
            bundle=bundle,
            settings=load_settings(),
        )

    assert exc_info.value.blockers
    assert not any("insert_world_event" in sql for sql in cur.statements)


def test_persist_retrograde_history_enforces_stub_cap() -> None:
    """The Decision 8 stub cap blocks over-budget expansions loudly."""

    vocabulary = _persistence_test_vocabulary()
    # Without Shutter Hall in the entity catalog, the place ref becomes a
    # minimum-viable stub candidate, which the zero cap then rejects.
    cur = FakeRetrogradePersistenceCursor(vocabulary, omit_place=True)
    bundle = _bundle(vocabulary)
    settings = load_settings().model_copy(deep=True)
    assert settings.orrery is not None
    settings.orrery.retrograde.wizard.max_new_entity_stubs = 0

    with pytest.raises(RetrogradePersistenceBlockedError) as exc_info:
        persist_retrograde_history(
            cur,
            bundle=bundle,
            settings=settings,
        )

    assert exc_info.value.blockers[0]["id"] == "entity_stub_budget_exceeded"
    assert not any("insert_world_event" in sql for sql in cur.statements)


# Issue #907 capture: the player confirmed Allies, Obligations, and Status.
# The trait compiler creates no row for an ally without a character id or for
# a status scope faction, so both starting trait targets reach Retrograde
# persistence as ``would_insert`` stubs next to five genuinely new entities.
ISSUE_907_STARTING_TRAIT_TARGETS = (
    ("character", "Ilya Sorn"),
    ("faction", "Veyr Canal Crews"),
)
ISSUE_907_NEW_ENTITIES = (
    ("character", "Tamsin Rook"),
    ("character", "Oren Vask"),
    ("character", "Dela Marsh"),
    ("character", "Corin Pell"),
    ("faction", "Well Wardens"),
)
ISSUE_907_CAPTURED_CAP = 6


def test_stub_budget_skips_starting_trait_targets_like_r6_validation() -> None:
    """#907: five new entities plus two starting trait targets persist.

    R6 validation charges five entities against the cap of six. The
    persistence gate must apply the same rule to the same starting set
    instead of charging seven ``would_insert`` stubs and rolling back.
    """

    vocabulary = _persistence_test_vocabulary()
    settings = _settings_with_stub_cap(ISSUE_907_CAPTURED_CAP)
    bundle = _issue_907_bundle(vocabulary, settings=settings)
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    # R6 validation (rerun inside the persistence plan) reads the same cap.
    budget = bundle.packet["seed_generation_request"]["budget"]
    assert budget["max_new_entity_stubs"] == ISSUE_907_CAPTURED_CAP

    manifest = persist_retrograde_history(cur, bundle=bundle, settings=settings)

    new_labels = sorted(f"{kind}:{name}" for kind, name in ISSUE_907_NEW_ENTITIES)
    starting_labels = sorted(
        f"{kind}:{name}" for kind, name in ISSUE_907_STARTING_TRAIT_TARGETS
    )
    assert manifest["entity_stub_budget"] == {
        "max_new_entity_stubs": ISSUE_907_CAPTURED_CAP,
        "charged_stubs": new_labels,
        "first_class_stubs": starting_labels,
    }
    # Every missing entity still gets a canonical row: the starting trait
    # targets are stubbed, just not charged against the cap.
    assert manifest["counters"]["entity_stubs_inserted"] == 7
    assert sorted(cur.inserted_character_stubs) == sorted(
        name
        for kind, name in (*ISSUE_907_NEW_ENTITIES, *ISSUE_907_STARTING_TRAIT_TARGETS)
        if kind == "character"
    )
    assert sorted(cur.inserted_faction_stubs) == ["Veyr Canal Crews", "Well Wardens"]
    assert manifest["counters"]["events_inserted"] == 1
    assert manifest["genesis_checkpoint"]["label"] == "genesis"


def test_stub_budget_still_blocks_new_entities_over_cap() -> None:
    """The persistence gate still enforces the configured cap on new stubs.

    With a persistence cap below the five genuinely new entities, the gate
    blocks before any canonical write. The two starting trait targets are
    not listed as charged stubs.
    """

    vocabulary = _persistence_test_vocabulary()
    bundle = _issue_907_bundle(
        vocabulary,
        settings=_settings_with_stub_cap(ISSUE_907_CAPTURED_CAP),
    )
    cur = FakeRetrogradePersistenceCursor(vocabulary)

    with pytest.raises(RetrogradePersistenceBlockedError) as exc_info:
        persist_retrograde_history(
            cur,
            bundle=bundle,
            settings=_settings_with_stub_cap(len(ISSUE_907_NEW_ENTITIES) - 1),
        )

    assert exc_info.value.blockers[0]["id"] == "entity_stub_budget_exceeded"
    message = str(exc_info.value)
    assert "would create 5 new entity stubs" in message
    for kind, name in ISSUE_907_NEW_ENTITIES:
        assert f"{kind}:{name}" in message
    for kind, name in ISSUE_907_STARTING_TRAIT_TARGETS:
        assert f"{kind}:{name}" not in message
    assert not cur.inserted_character_stubs
    assert not cur.inserted_faction_stubs
    assert not any("insert_world_event" in sql for sql in cur.statements)


def test_stub_budget_skips_named_seed_npcs_without_rows() -> None:
    """Named seed NPCs follow the same rule as starting trait targets.

    The transition writes no rows for seed NPCs. A referenced seed NPC is
    stubbed at persistence but charged on neither side.
    """

    vocabulary = _persistence_test_vocabulary()
    settings = _settings_with_stub_cap(ISSUE_907_CAPTURED_CAP)
    bundle = _issue_907_bundle(
        vocabulary,
        settings=settings,
        extra_seed_npcs=("Brisa Hale",),
    )
    cur = FakeRetrogradePersistenceCursor(vocabulary)

    manifest = persist_retrograde_history(cur, bundle=bundle, settings=settings)

    assert len(manifest["entity_stub_budget"]["charged_stubs"]) == 5
    assert "character:Brisa Hale" in manifest["entity_stub_budget"]["first_class_stubs"]
    assert "Brisa Hale" in cur.inserted_character_stubs
    assert manifest["counters"]["entity_stubs_inserted"] == 8


def test_issue_907_expansion_charges_same_five_entities_in_r6_validation() -> None:
    """R6 validation charges exactly the five new entities, never the targets."""

    vocabulary = _persistence_test_vocabulary()
    bundle = _issue_907_bundle(
        vocabulary,
        settings=_settings_with_stub_cap(ISSUE_907_CAPTURED_CAP),
    )
    packet = copy.deepcopy(bundle.packet)
    packet["seed_generation_request"]["budget"]["max_new_entity_stubs"] = (
        len(ISSUE_907_NEW_ENTITIES) - 1
    )

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="expansion introduces 5 entities beyond the first-class",
    ) as exc_info:
        validate_expansion_plan(
            payload=bundle.expansion_plan,
            packet=packet,
            seed_candidate_response=bundle.seed_candidate_response,
        )

    message = str(exc_info.value)
    for kind, name in ISSUE_907_NEW_ENTITIES:
        assert f"{kind}:{name.casefold()}" in message
    for kind, name in ISSUE_907_STARTING_TRAIT_TARGETS:
        assert f"{kind}:{name.casefold()}" not in message


def _settings_with_stub_cap(cap: int) -> Settings:
    """Return a settings copy with an explicit wizard stub cap."""

    settings = load_settings().model_copy(deep=True)
    assert settings.orrery is not None
    settings.orrery.retrograde.wizard.max_new_entity_stubs = cap
    return settings


class _Issue907Cache(FakeRetrogradeCache):
    """Wizard cache for the #907 capture: Allies, Obligations, and Status."""

    def __init__(self, *, extra_seed_npcs: tuple[str, ...] = ()) -> None:
        self.extra_seed_npcs = extra_seed_npcs

    def get_seed_dict(self) -> dict[str, object] | None:
        seed = super().get_seed_dict()
        assert seed is not None
        key_npcs = seed["key_npcs"]
        assert isinstance(key_npcs, list)
        seed["key_npcs"] = [*key_npcs, *self.extra_seed_npcs]
        return seed

    def get_character_dict(self) -> dict[str, object]:
        character = super().get_character_dict()
        character["trait_selection"] = {
            "selected_traits": ["allies", "obligations", "status"],
            "trait_rationales": {
                "allies": "Neighbors she carries water for.",
                "obligations": "Debts owed along the canal.",
                "status": "Standing among the canal crews.",
            },
        }
        return character


def _issue_907_bundle(
    vocabulary: Any,
    *,
    settings: Settings,
    extra_seed_npcs: tuple[str, ...] = (),
) -> RetrogradeGenerationBundle:
    """Build the #907 bundle from a real packet with starting trait targets.

    ``extra_seed_npcs`` adds named seed NPCs that the expansion also
    references. The fake cursor's catalog has no rows for them.
    """

    # Validated through the real trait-input schema, then serialized exactly
    # as perform_transition_with_retrograde hands it to the packet builder.
    trait_compile_inputs = TraitCompileInputs.model_validate(
        {
            "allies": {
                "targets": [
                    {"name": "Ilya Sorn", "dynamic": "Shares the dawn water run."}
                ]
            },
            "status": {
                "level": "respected",
                "scope_faction_name": "Veyr Canal Crews",
            },
        }
    ).model_dump(mode="json", exclude_none=True)
    packet = build_retrograde_dry_run_packet(
        slot=5,
        dbname="save_05",
        cache=_Issue907Cache(extra_seed_npcs=extra_seed_npcs),
        vocabulary=vocabulary,
        settings=settings,
        weird_level="low",
        trait_compile_inputs=trait_compile_inputs,
    )
    assert set(ISSUE_907_STARTING_TRAIT_TARGETS) <= {
        (card["kind"], card["name"])
        for card in packet["candidate_scaffolds"]["core_entities"]
    }

    seed_response = _seed_response_base(vocabulary)
    edge = packet["seed_generation_request"]["candidate_graph"]["dangling_edges"][0]
    seed_response["candidates"][0]["claimed_edges"] = [
        {
            "edge_id": edge["edge_id"],
            "open_endpoint_name": "The Salt Ledger",
            "open_endpoint_kind": edge["open_endpoint_kind"],
        }
    ]

    expansion = _valid_expansion(vocabulary)
    participants = expansion["event_plan"][0]["participants"]
    for kind, name in (
        *ISSUE_907_STARTING_TRAIT_TARGETS,
        *ISSUE_907_NEW_ENTITIES,
        *(("character", npc) for npc in extra_seed_npcs),
    ):
        participants.append(
            {"entity_ref": name, "entity_kind": kind, "role": "witness"}
        )

    return RetrogradeGenerationBundle(
        slot=5,
        dbname="save_05",
        model="test-model",
        weird=dict(packet["weird"]),
        packet=packet,
        seed_candidate_response=seed_response,
        expansion_plan=expansion,
        timings=[RetrogradeStageTiming(stage="packet", seconds=0.0)],
    )


def test_build_wizard_history_surface_splits_visible_and_hidden() -> None:
    """Decision 6: entities/relationships visible, event prose held back."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    bundle = _bundle(vocabulary)
    manifest = persist_retrograde_history(
        cur,
        bundle=bundle,
        settings=load_settings(),
    )

    surface = build_wizard_history_surface(bundle=bundle, manifest=manifest)

    visible = surface["visible"]
    assert {entity["name"] for entity in visible["entities"]} == {
        "Mara",
        "Vale",
        "Shutter Hall",
    }
    assert visible["relationships"] == [
        {
            "subject": "Mara",
            "object": "Vale",
            "relationship_type": bundle.expansion_plan["relationship_plan"][0][
                "relationship_type"
            ],
        }
    ]
    hidden = surface["hidden_counts"]
    assert hidden["world_events"] == 1
    assert hidden["entity_tags"] == 2
    assert hidden["pair_tags"] == 1
    assert hidden["woven_seeds"] == 1
    # The high-entropy long tail must not leak: no event prose in the surface.
    event_summary = bundle.expansion_plan["event_plan"][0]["summary"]
    assert event_summary not in repr(surface)


def _bundle(vocabulary: Any) -> RetrogradeGenerationBundle:
    packet = {
        **_packet(vocabulary),
        "weird": {"level": "medium", "genre": "cyberpunk", "raw_midpoint": 0.5},
    }
    return RetrogradeGenerationBundle(
        slot=5,
        dbname="save_05",
        model="test-model",
        weird=dict(packet["weird"]),
        packet=packet,
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan=_valid_expansion(vocabulary),
        timings=[RetrogradeStageTiming(stage="packet", seconds=0.0)],
    )

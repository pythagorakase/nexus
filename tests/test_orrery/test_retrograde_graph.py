"""R3 candidate-graph builder: seeded dice the LLM cannot un-roll.

The graph is the entropy-injection point (issue #442): identical inputs
must rebuild the identical graph (replay/dry-run parity), the weird band
must do numeric work, and every edge must be legal against the vocabulary
it was sampled from.
"""

from __future__ import annotations

import pytest

from nexus.agents.orrery.retrograde_graph import build_candidate_graph

SCAFFOLDS = {
    "core_entities": [
        {
            "kind": "character",
            "role": "protagonist",
            "name": "Mara",
            "summary": "Debt tracker.",
        },
        {
            "kind": "place",
            "role": "starting_location",
            "name": "Shutter Hall",
            "summary": "A counting house.",
        },
    ]
}

VOCABULARY = {
    "relationship_types": ["rival", "family", "comrade"],
    "multi_entity_tag_definitions": [
        {
            "tag": "obligation",
            "subject_kinds": ["character"],
            "object_kinds": ["character", "faction"],
            "is_ephemeral": False,
        },
        {
            "tag": "resides_at",
            "subject_kinds": ["character"],
            "object_kinds": ["place"],
            "is_ephemeral": False,
        },
    ],
    "event_types": [
        "threat_issued",
        "contact_made",
        "mourning_act",
        "upkeep_done",
        "slept",
    ],
    # Registry categories: bookkeeping categories (routine, physiological,
    # orrery_resolution by default) are barred from the event edge pool.
    "event_type_categories": {
        "threat_issued": "interpersonal",
        "contact_made": "interpersonal",
        "mourning_act": "emotional",
        "upkeep_done": "routine",
        "slept": "physiological",
    },
    # Keys the request builder touches beyond the edge pools.
    "entity_kinds": ["character", "place", "faction"],
    "slots": ["actor", "target"],
    "single_entity_tag_anchors": [],
    "registered_single_entity_tags": [],
    "registered_tag_categories": [],
    "registered_tags_by_category": {},
    "registered_tags_by_entity_kind": {},
    "registered_category_seed_policies": [],
    "registered_tags_by_seed_policy": {},
    "multi_entity_tag_families": ["obligation", "resides_at"],
    "place_classes": [],
    "durable_tags": [],
    "ephemeral_tags": [],
    "current_tags": [],
    "applied_tags": [],
}

WEIRD = {"level": "medium", "raw_min": 0.28, "raw_max": 0.55}


def _build(
    seed: str = "test:mara",
    generate: int = 6,
    junction_count: int = 0,
) -> dict:
    return build_candidate_graph(
        candidate_scaffolds=SCAFFOLDS,
        vocabulary=VOCABULARY,
        weird=WEIRD,
        generate_candidates=generate,
        rng_seed_material=seed,
        junction_count=junction_count,
    )


def test_graph_is_deterministic_for_identical_inputs() -> None:
    assert _build() == _build()


def test_shared_entity_junction_is_deterministic_and_kind_compatible() -> None:
    """R3 rolls two distinct edge legs around one shared unknown entity."""

    graph = _build(junction_count=1)
    assert graph == _build(junction_count=1)
    assert graph["schema_version"] == 2
    assert len(graph["junctions"]) == 1

    junction = graph["junctions"][0]
    assert junction["junction_id"] == "junction_01"
    assert junction["resolution"] == "shared_entity"
    assert len(junction["edge_ids"]) == 2
    assert len(set(junction["edge_ids"])) == 2

    edges_by_id = {edge["edge_id"]: edge for edge in graph["dangling_edges"]}
    legs = [edges_by_id[edge_id] for edge_id in junction["edge_ids"]]
    assert all(
        leg["open_endpoint_kind"] == junction["open_endpoint_kind"] for leg in legs
    )
    assert len({(leg["kind"], leg["edge_type"]) for leg in legs}) == 2


def test_different_seed_material_rolls_a_different_graph() -> None:
    first = _build("test:mara")
    second = _build("test:sela")
    assert first["dangling_edges"] != second["dangling_edges"]


def test_weird_roll_lands_inside_the_resolved_band() -> None:
    graph = _build()
    roll = graph["weird_roll"]["raw"]
    assert WEIRD["raw_min"] <= roll <= WEIRD["raw_max"]


def test_raw_override_bypasses_the_band_roll() -> None:
    graph = build_candidate_graph(
        candidate_scaffolds=SCAFFOLDS,
        vocabulary=VOCABULARY,
        weird={"level": "high", "raw": 0.9, "raw_min": 0.55, "raw_max": 0.82},
        generate_candidates=4,
        rng_seed_material="test:override",
    )
    assert graph["weird_roll"]["raw"] == 0.9


def test_edges_are_vocabulary_legal_and_kind_consistent() -> None:
    graph = _build(generate=8)
    node_refs = {node["ref"] for node in graph["nodes"]}
    pair_defs = {d["tag"]: d for d in VOCABULARY["multi_entity_tag_definitions"]}

    assert graph["dangling_edges"], "sampler must produce edges"
    for edge in graph["dangling_edges"]:
        assert edge["anchor_ref"] in node_refs
        assert edge["orthogonality"] in ("adjacent", "far")
        if edge["kind"] == "relationship":
            assert edge["edge_type"] in VOCABULARY["relationship_types"]
            # Persistence accepts character-character rows only.
            assert edge["anchor_ref"].startswith("character:")
            assert edge["open_endpoint_kind"] == "character"
        elif edge["kind"] == "pair_tag":
            definition = pair_defs[edge["edge_type"]]
            anchor_kind = edge["anchor_ref"].split(":", 1)[0]
            if edge["anchor_role"] == "subject":
                assert anchor_kind in definition["subject_kinds"]
                assert edge["open_endpoint_kind"] in definition["object_kinds"]
            else:
                assert anchor_kind in definition["object_kinds"]
                assert edge["open_endpoint_kind"] in definition["subject_kinds"]
        else:
            assert edge["kind"] == "event"
            assert edge["edge_type"] in VOCABULARY["event_types"]
            assert edge["open_endpoint_kind"] in ("character", "faction", "place")


def test_edge_types_are_deduplicated_within_a_kind() -> None:
    graph = _build(generate=8)
    seen = [(edge["kind"], edge["edge_type"]) for edge in graph["dangling_edges"]]
    assert len(seen) == len(set(seen))


def test_empty_core_raises_loudly() -> None:
    with pytest.raises(ValueError, match="core entity node"):
        build_candidate_graph(
            candidate_scaffolds={"core_entities": []},
            vocabulary=VOCABULARY,
            weird=WEIRD,
            generate_candidates=4,
            rng_seed_material="test:empty",
        )


def test_empty_vocabulary_raises_loudly() -> None:
    with pytest.raises(ValueError, match="vocabulary"):
        build_candidate_graph(
            candidate_scaffolds=SCAFFOLDS,
            vocabulary={
                "relationship_types": [],
                "multi_entity_tag_definitions": [],
                "event_types": [],
            },
            weird=WEIRD,
            generate_candidates=4,
            rng_seed_material="test:novocab",
        )


def test_graph_settings_are_configurable() -> None:
    """Calibration comes from [orrery.retrograde.graph], not module constants."""

    graph = build_candidate_graph(
        candidate_scaffolds=SCAFFOLDS,
        vocabulary=VOCABULARY,
        weird=WEIRD,
        generate_candidates=4,
        rng_seed_material="test:config",
        graph_settings={
            "edges_per_candidate": 3.0,
            "edge_kind_weights": {"event": 1.0},
        },
    )
    assert len(graph["dangling_edges"]) <= 12
    assert all(edge["kind"] == "event" for edge in graph["dangling_edges"])


def test_mundane_event_categories_never_enter_the_event_pool() -> None:
    """Bookkeeping events are excluded from the backstory dice (issue #442)."""

    graph = build_candidate_graph(
        candidate_scaffolds=SCAFFOLDS,
        vocabulary=VOCABULARY,
        weird=WEIRD,
        generate_candidates=8,
        rng_seed_material="test:mundane",
        graph_settings={
            "edge_kind_weights": {"event": 1.0},
            "edges_per_candidate": 3.0,
        },
    )
    rolled = {edge["edge_type"] for edge in graph["dangling_edges"]}
    assert rolled <= {"threat_issued", "contact_made", "mourning_act"}
    assert graph["event_pool"] == {
        "registered": 5,
        "eligible": 3,
        "excluded_categories": ["orrery_resolution", "physiological", "routine"],
    }


def test_uncategorized_event_types_cannot_be_excluded() -> None:
    """Template-only vocabulary carries no categories; the filter is a no-op."""

    vocabulary = {**VOCABULARY, "event_type_categories": {}}
    graph = build_candidate_graph(
        candidate_scaffolds=SCAFFOLDS,
        vocabulary=vocabulary,
        weird=WEIRD,
        generate_candidates=8,
        rng_seed_material="test:uncategorized",
        graph_settings={
            "edge_kind_weights": {"event": 1.0},
            "edges_per_candidate": 3.0,
        },
    )
    rolled = {edge["edge_type"] for edge in graph["dangling_edges"]}
    assert rolled == set(VOCABULARY["event_types"])
    assert graph["event_pool"]["eligible"] == 5


def test_exclusion_that_empties_the_event_pool_raises_loudly() -> None:
    """Excluding every registered category is a misconfiguration, not a state."""

    with pytest.raises(ValueError, match="excluded_event_categories"):
        build_candidate_graph(
            candidate_scaffolds=SCAFFOLDS,
            vocabulary=VOCABULARY,
            weird=WEIRD,
            generate_candidates=4,
            rng_seed_material="test:allmundane",
            graph_settings={
                "excluded_event_categories": [
                    "interpersonal",
                    "emotional",
                    "physiological",
                    "routine",
                ],
            },
        )


def test_excluded_event_categories_come_from_settings() -> None:
    """nexus.toml owns the exclusion list, not module constants."""

    from nexus.config import load_settings

    cfg = load_settings().orrery.retrograde.graph
    assert cfg.excluded_event_categories == [
        "orrery_resolution",
        "physiological",
        "routine",
    ]
    assert cfg.junction_counts_by_weird.model_dump() == {
        "low": 0,
        "medium": 1,
        "high": 1,
    }


def test_impossible_junction_vocabulary_fails_loudly() -> None:
    """A required braid cannot silently degrade into a star-shaped graph."""

    vocabulary = {
        **VOCABULARY,
        "relationship_types": ["rival"],
        "multi_entity_tag_definitions": [],
        "event_types": [],
    }
    with pytest.raises(ValueError, match="junction 1"):
        build_candidate_graph(
            candidate_scaffolds=SCAFFOLDS,
            vocabulary=vocabulary,
            weird=WEIRD,
            generate_candidates=4,
            rng_seed_material="test:impossible-junction",
            graph_settings={"edge_kind_weights": {"relationship": 1.0}},
            junction_count=1,
        )


def test_runtime_maturation_packet_sizes_graph_from_its_own_budget() -> None:
    """The maturation graph is sized for 4 candidates, not the wizard 9."""

    from math import ceil

    from nexus.agents.orrery.retrograde_maturation import (
        build_runtime_maturation_packet,
    )
    from nexus.config import load_settings

    settings = load_settings()
    cfg = settings.orrery.retrograde.maturation
    packet = build_runtime_maturation_packet(
        vocabulary=VOCABULARY,
        row={
            "entity_kind": "character",
            "entity_name": "Test Subject",
            "entity_id": 999,
            "requesting_chunk_id": 1,
            "declaration": {"summary": "A test entity."},
        },
        context={
            "entity_summary": "A test entity.",
            "scene_entities": SCAFFOLDS["core_entities"],
            "chunk_excerpt": "The subject appeared.",
        },
        cfg=cfg,
        dbname="save_05",
        setting={"genre": "fantasy"},
    )
    request = packet["seed_generation_request"]
    assert request["budget"]["generate_candidates"] == cfg.generate_candidates
    assert request["project_intent_policy"]["rarity"] == (
        "The maturation target may propose at most one project."
    )
    assert "Test Subject" in request["project_intent_policy"]["actor_rule"]
    assert "AT MOST ONE project" in packet["seed_generation_prompt"]
    assert "MUST be the maturation target" in packet["seed_generation_prompt"]
    edges = request["candidate_graph"]["dangling_edges"]
    expected_max = max(2, ceil(cfg.generate_candidates * 1.5))
    assert len(edges) <= expected_max
    assert request["candidate_graph"]["junctions"] == []

    # entropy(cold_start) > entropy(maturation): the roll happens inside
    # the genre band contracted by weird_band_fraction from its floor.
    band = getattr(
        settings.orrery.retrograde.weird.bands_by_genre["fantasy"],
        cfg.weird_level,
    )
    roll = request["candidate_graph"]["weird_roll"]
    expected_max_raw = band.min + (band.max - band.min) * cfg.weird_band_fraction
    assert roll["raw_min"] == pytest.approx(band.min)
    assert roll["raw_max"] == pytest.approx(expected_max_raw)
    assert roll["raw_min"] <= roll["raw"] <= roll["raw_max"]

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
    "event_types": ["threat_issued", "contact_made", "mourning_act"],
}

WEIRD = {"level": "medium", "raw_min": 0.28, "raw_max": 0.55}


def _build(seed: str = "test:mara", generate: int = 6) -> dict:
    return build_candidate_graph(
        candidate_scaffolds=SCAFFOLDS,
        vocabulary=VOCABULARY,
        weird=WEIRD,
        generate_candidates=generate,
        rng_seed_material=seed,
    )


def test_graph_is_deterministic_for_identical_inputs() -> None:
    assert _build() == _build()


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

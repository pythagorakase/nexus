"""R3 graph builder: the procedural candidate graph with dangling edges.

The Retrograde spec (docs/orrery_retrograde_spec.md) defines R3 as
"expand the sparse core into a candidate relationship/event graph with
open attachment points (dangling edges where history could connect)" and
R4 as seeds "directionally connected to the graph but NOT implied by it
— this is where surprise is injected." This module is that injection
point (issue #442): a seeded roll the LLM cannot un-roll draws edge
ingredients from the registered vocabulary, and Skald's creativity is
spent reconciling ingredients it did not choose rather than sampling
its own priors.

Determinism contract: the RNG is keyed on stable identity material
(slot/story/entity), the same discipline as branch selection's
``_selection_rng`` — identical inputs rebuild the identical graph, so
dry-run packets and replays agree.
"""

from __future__ import annotations

import random
from hashlib import sha256
from math import ceil
from typing import TYPE_CHECKING, Any, Mapping, Optional, TypedDict

from nexus.agents.orrery.retrograde_vocabulary import SeedEligibleVocabulary

if TYPE_CHECKING:
    from nexus.config.settings_models import OrreryRetrogradeGraphSettings

GRAPH_SCHEMA_VERSION = 1


def _coerce_graph_settings(raw: Any) -> "OrreryRetrogradeGraphSettings":
    """[orrery.retrograde.graph] payload -> validated calibration settings."""

    from nexus.config.settings_models import OrreryRetrogradeGraphSettings

    if raw is None:
        return OrreryRetrogradeGraphSettings()
    if isinstance(raw, OrreryRetrogradeGraphSettings):
        return raw
    if isinstance(raw, Mapping):
        return OrreryRetrogradeGraphSettings.model_validate(dict(raw))
    raise ValueError(f"Unsupported retrograde graph settings: {type(raw)!r}")


class DanglingEdge(TypedDict):
    edge_id: str
    kind: str
    edge_type: str
    anchor_ref: str
    anchor_role: str
    open_endpoint_kind: str
    orthogonality: str
    guidance: str


def _graph_rng(seed_material: str) -> random.Random:
    return random.Random(int(sha256(seed_material.encode("utf-8")).hexdigest(), 16))


def _weighted_choice(rng: random.Random, options: tuple[tuple[str, float], ...]) -> str:
    values = [value for value, _weight in options]
    weights = [weight for _value, weight in options]
    return rng.choices(values, weights=weights, k=1)[0]


def _node_ref(card: Mapping[str, Any]) -> Optional[str]:
    kind = card.get("kind")
    name = card.get("name")
    if not kind or not name:
        return None
    return f"{kind}:{name}"


def build_candidate_graph(
    *,
    candidate_scaffolds: Mapping[str, Any],
    vocabulary: SeedEligibleVocabulary,
    weird: Mapping[str, Any],
    generate_candidates: int,
    rng_seed_material: str,
    graph_settings: Any = None,
) -> dict[str, Any]:
    """Build the R3 candidate graph: core nodes plus sampled dangling edges.

    ``weird`` finally does numeric work here: the raw calibration float is
    rolled uniformly inside the resolved genre band and becomes the
    expected share of edges marked ``far`` — ingredients whose connection
    to the premise may be indirect, generational, or mythic. ``adjacent``
    edges ask for direct, recent connections.
    """

    cfg = _coerce_graph_settings(graph_settings)
    edge_kind_weights = tuple(cfg.edge_kind_weights.items())
    event_endpoint_weights = tuple(cfg.event_open_endpoint_weights.items())
    default_anchor_weight = cfg.anchor_role_weights.get("default", 1.0)

    rng = _graph_rng(rng_seed_material)

    raw = weird.get("raw")
    raw_min = float(weird.get("raw_min", 0.0))
    raw_max = float(weird.get("raw_max", raw_min))
    weird_roll = float(raw) if raw is not None else rng.uniform(raw_min, raw_max)

    nodes: list[dict[str, Any]] = []
    cards = candidate_scaffolds.get("core_entities", ())
    for card in cards:  # type: ignore[union-attr]
        ref = _node_ref(card)
        if ref is None:
            continue
        nodes.append(
            {
                "ref": ref,
                "kind": card.get("kind"),
                "role": card.get("role"),
                "name": card.get("name"),
            }
        )
    if not nodes:
        raise ValueError(
            "Retrograde graph requires at least one core entity node; "
            "candidate_scaffolds.core_entities is empty"
        )

    character_nodes = [node for node in nodes if node["kind"] == "character"]

    relationship_types = list(vocabulary.get("relationship_types", ()))
    pair_tag_definitions = list(vocabulary.get("multi_entity_tag_definitions", ()))
    event_types = list(vocabulary.get("event_types", ()))
    if not (relationship_types or pair_tag_definitions or event_types):
        raise ValueError(
            "Retrograde graph requires seed-eligible vocabulary; all three "
            "edge pools (relationships, pair tags, events) are empty"
        )

    edge_count = max(2, ceil(generate_candidates * cfg.edges_per_candidate))
    edges: list[DanglingEdge] = []
    used_edge_types: set[tuple[str, str]] = set()

    def _pick_anchor(kind_filter: Optional[str] = None) -> Optional[dict[str, Any]]:
        pool = (
            nodes
            if kind_filter is None
            else [node for node in nodes if node["kind"] == kind_filter]
        )
        if not pool:
            return None
        weights = [
            cfg.anchor_role_weights.get(str(node.get("role")), default_anchor_weight)
            for node in pool
        ]
        return rng.choices(pool, weights=weights, k=1)[0]

    for index in range(edge_count):
        edge: Optional[DanglingEdge] = None
        for _attempt in range(cfg.max_sample_retries):
            kind = _weighted_choice(rng, edge_kind_weights)

            if kind == "relationship":
                # Persistence accepts character-character rows only
                # (spec decision 15), so both endpoints are characters.
                if not relationship_types or not character_nodes:
                    continue
                anchor = _pick_anchor("character")
                if anchor is None:
                    continue
                edge_type = rng.choice(relationship_types)
                open_kind = "character"
                anchor_role = "subject"
            elif kind == "pair_tag":
                if not pair_tag_definitions:
                    continue
                definition = rng.choice(pair_tag_definitions)
                subject_kinds = list(definition.get("subject_kinds", ()))
                object_kinds = list(definition.get("object_kinds", ()))
                anchor = None
                anchor_role = "subject"
                open_kind = ""
                anchor_as_subject_kinds = [
                    node["kind"] for node in nodes if node["kind"] in subject_kinds
                ]
                if anchor_as_subject_kinds and object_kinds:
                    anchor = _pick_anchor(rng.choice(anchor_as_subject_kinds))
                    open_kind = rng.choice(object_kinds)
                    anchor_role = "subject"
                else:
                    anchor_as_object_kinds = [
                        node["kind"] for node in nodes if node["kind"] in object_kinds
                    ]
                    if anchor_as_object_kinds and subject_kinds:
                        anchor = _pick_anchor(rng.choice(anchor_as_object_kinds))
                        open_kind = rng.choice(subject_kinds)
                        anchor_role = "object"
                if anchor is None or not open_kind:
                    continue
                edge_type = str(definition["tag"])
            else:  # event
                if not event_types:
                    continue
                anchor = _pick_anchor()
                if anchor is None:
                    continue
                edge_type = rng.choice(event_types)
                open_kind = _weighted_choice(rng, event_endpoint_weights)
                anchor_role = "participant"

            if (kind, edge_type) in used_edge_types:
                continue

            far = rng.random() < weird_roll
            edge = {
                "edge_id": f"edge_{index + 1:02d}",
                "kind": kind,
                "edge_type": edge_type,
                "anchor_ref": str(anchor["ref"]),
                "anchor_role": anchor_role,
                "open_endpoint_kind": open_kind,
                "orthogonality": "far" if far else "adjacent",
                "guidance": (
                    "Connection may be indirect, generational, hidden, or "
                    "mythic — but the leaf anchor rule still applies."
                    if far
                    else "Connection should be direct and comparatively recent."
                ),
            }
            break
        if edge is None:
            # Vocabulary too small to keep deduping within the retry
            # budget: under-build the menu rather than emit duplicate
            # ingredient types. Edge capacity already exceeds what
            # candidates can claim, so a short menu costs little.
            continue
        used_edge_types.add((edge["kind"], edge["edge_type"]))
        edges.append(edge)

    if not edges:
        raise ValueError(
            "Retrograde graph sampling produced no dangling edges; "
            "vocabulary pools are too small for the requested edge count"
        )

    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "rng": {
            "seed_material": rng_seed_material,
            "algorithm": "sha256->random.Random",
        },
        "weird_roll": {
            "raw": weird_roll,
            "raw_min": raw_min,
            "raw_max": raw_max,
        },
        "nodes": nodes,
        "dangling_edges": list(edges),
        "attachment_contract": {
            "rule": (
                "Every candidate seed must claim one or two edge_ids from "
                "dangling_edges and resolve each claimed edge's open "
                "endpoint by naming it (a new or existing entity of "
                "open_endpoint_kind). Unclaimed edges are discarded free "
                "of charge. The seed's story must make the claimed "
                "edge_type true."
            ),
            "claims_per_seed_min": 1,
            "claims_per_seed_max": 2,
        },
    }

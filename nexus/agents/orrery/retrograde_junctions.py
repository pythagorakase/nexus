"""Shared resolution for mechanically sampled Retrograde junctions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from nexus.agents.orrery.retrograde_vocabulary import (
    ENTITY_REF_MAX_LENGTH,
    normalize_entity_ref,
)


def resolve_junctions(
    *,
    seed_generation_request: Mapping[str, Any],
    candidates_payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve R3 junction legs against R4 candidate edge claims.

    A valid shared-entity junction has exactly two distinct dangling-edge
    legs. Each leg is claimed exactly once, by a different candidate, using
    the junction's endpoint kind and the same normalized endpoint name.
    Resolved rows are deliberately plain dictionaries so R5, R6, audit, and
    persistence code can share this authority without importing one another's
    Pydantic response models.
    """

    graph = _mapping(seed_generation_request.get("candidate_graph"))
    raw_junctions = graph.get("junctions", [])
    if not isinstance(raw_junctions, list):
        return [], ["candidate_graph.junctions must be a list"]
    if not raw_junctions:
        return [], []

    graph_edges = {
        str(edge.get("edge_id")): edge
        for edge in graph.get("dangling_edges") or []
        if isinstance(edge, Mapping) and edge.get("edge_id")
    }
    claims_by_edge: dict[str, list[dict[str, str]]] = defaultdict(list)
    for candidate in candidates_payload.get("candidates") or []:
        if not isinstance(candidate, Mapping):
            continue
        seed_id = str(candidate.get("seed_id") or "")
        for claim in candidate.get("claimed_edges") or []:
            if not isinstance(claim, Mapping) or not claim.get("edge_id"):
                continue
            edge_id = str(claim["edge_id"])
            claims_by_edge[edge_id].append(
                {
                    "seed_id": seed_id,
                    "entity_ref": str(claim.get("open_endpoint_name") or "").strip(),
                    "entity_kind": str(claim.get("open_endpoint_kind") or ""),
                }
            )

    resolved: list[dict[str, Any]] = []
    issues: list[str] = []
    seen_junction_ids: set[str] = set()
    seen_junction_edge_ids: set[str] = set()
    for raw_junction in raw_junctions:
        if not isinstance(raw_junction, Mapping):
            issues.append("candidate_graph.junctions entries must be objects")
            continue

        junction_id = str(raw_junction.get("junction_id") or "")
        prefix = f"junction {junction_id!r}"
        junction_issues: list[str] = []
        if not junction_id:
            junction_issues.append("junction_id must be non-empty")
        elif junction_id in seen_junction_ids:
            junction_issues.append(f"duplicate junction_id {junction_id!r}")
        seen_junction_ids.add(junction_id)

        raw_edge_ids = raw_junction.get("edge_ids")
        edge_ids = (
            [str(edge_id) for edge_id in raw_edge_ids]
            if isinstance(raw_edge_ids, list)
            else []
        )
        if len(edge_ids) != 2 or any(not edge_id for edge_id in edge_ids):
            junction_issues.append(
                f"{prefix} must define exactly two non-empty edge_ids"
            )
        elif len(set(edge_ids)) != 2:
            junction_issues.append(f"{prefix} edge_ids must be distinct")
        else:
            reused_edge_ids = sorted(set(edge_ids) & seen_junction_edge_ids)
            if reused_edge_ids:
                junction_issues.append(
                    f"{prefix} reuses edge_ids already assigned to another "
                    f"junction: {reused_edge_ids}"
                )
            seen_junction_edge_ids.update(edge_ids)

        entity_kind = str(raw_junction.get("open_endpoint_kind") or "")
        if not entity_kind:
            junction_issues.append(f"{prefix} open_endpoint_kind must be non-empty")
        if raw_junction.get("resolution") != "shared_entity":
            junction_issues.append(f"{prefix} resolution must be 'shared_entity'")

        leg_claims: list[dict[str, str]] = []
        for edge_id in edge_ids:
            graph_edge = graph_edges.get(edge_id)
            if graph_edge is None:
                junction_issues.append(
                    f"{prefix} references unknown dangling edge {edge_id!r}"
                )
            elif str(graph_edge.get("open_endpoint_kind") or "") != entity_kind:
                junction_issues.append(
                    f"{prefix} edge {edge_id!r} requires endpoint kind "
                    f"{graph_edge.get('open_endpoint_kind')!r}, not {entity_kind!r}"
                )

            claims = claims_by_edge.get(edge_id, [])
            if len(claims) != 1:
                junction_issues.append(
                    f"{prefix} leg {edge_id!r} must be claimed exactly once; "
                    f"found {len(claims)} claims"
                )
                continue
            leg_claims.append(claims[0])

        if len(leg_claims) == 2:
            seed_ids = [claim["seed_id"] for claim in leg_claims]
            if any(not seed_id for seed_id in seed_ids):
                junction_issues.append(
                    f"{prefix} legs must be claimed by candidates with seed_id values"
                )
            elif len(set(seed_ids)) != 2:
                junction_issues.append(
                    f"{prefix} legs must be claimed by two distinct candidates"
                )

            for edge_id, claim in zip(edge_ids, leg_claims):
                if claim["entity_kind"] != entity_kind:
                    junction_issues.append(
                        f"{prefix} leg {edge_id!r} resolves kind "
                        f"{claim['entity_kind']!r}; expected {entity_kind!r}"
                    )
                entity_ref = claim["entity_ref"]
                if not entity_ref:
                    junction_issues.append(
                        f"{prefix} leg {edge_id!r} requires an endpoint name"
                    )
                elif len(entity_ref) > ENTITY_REF_MAX_LENGTH:
                    junction_issues.append(
                        f"{prefix} leg {edge_id!r} endpoint name exceeds "
                        f"{ENTITY_REF_MAX_LENGTH} characters"
                    )

            normalized_refs = [
                normalize_entity_ref(claim["entity_ref"]) for claim in leg_claims
            ]
            if all(normalized_refs) and len(set(normalized_refs)) != 1:
                junction_issues.append(
                    f"{prefix} legs must resolve to the same normalized entity name"
                )

        if junction_issues:
            issues.extend(junction_issues)
            continue

        resolved.append(
            {
                "junction_id": junction_id,
                "edge_ids": edge_ids,
                "seed_ids": [claim["seed_id"] for claim in leg_claims],
                "entity_ref": leg_claims[0]["entity_ref"],
                "normalized_entity_ref": normalize_entity_ref(
                    leg_claims[0]["entity_ref"]
                ),
                "entity_kind": entity_kind,
            }
        )

    return resolved, issues


def _mapping(value: Any) -> Mapping[str, Any]:
    """Return ``value`` as a mapping, or an empty mapping otherwise."""

    return value if isinstance(value, Mapping) else {}

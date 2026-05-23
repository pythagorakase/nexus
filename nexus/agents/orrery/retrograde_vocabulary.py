"""Seed-eligible Orrery vocabulary enumeration for Retrograde generation."""

from __future__ import annotations

from typing import TypedDict

from nexus.agents.orrery.catalog import collect_template_vocabulary
from nexus.agents.orrery.pair_tag_registry import PAIR_TAG_SEED
from nexus.agents.orrery.substrate import EntityKind, Slot
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES


class PairTagPrimitive(TypedDict):
    """One registered multi-entity tag family with kind constraints."""

    tag: str
    subject_kinds: list[str]
    object_kinds: list[str]
    is_ephemeral: bool


class SeedEligibleVocabulary(TypedDict):
    """Primitive vocabulary Retrograde may use for substrate-legal seeds."""

    entity_kinds: list[str]
    slots: list[str]
    single_entity_tag_anchors: list[str]
    durable_tags: list[str]
    ephemeral_tags: list[str]
    current_tags: list[str]
    applied_tags: list[str]
    multi_entity_tag_families: list[str]
    multi_entity_tag_definitions: list[PairTagPrimitive]
    event_types: list[str]
    place_affordances: list[str]
    relationship_types: list[str]


def enumerate_seed_eligible_vocabulary() -> SeedEligibleVocabulary:
    """Return the current substrate-legal primitive set for Retrograde seeds.

    The enumeration is read from the same Python sources the forward Orrery
    already uses: built-in templates for package-facing tags/events/relations,
    substrate enums for typed entities and slots, and the shared pair-tag
    registry for directed multi-entity tag families.
    """

    template_vocab = collect_template_vocabulary(BUILTIN_TEMPLATES)
    single_entity_tags = sorted(
        set(template_vocab["durable_tags"])
        | set(template_vocab["ephemeral_tags"])
        | set(template_vocab["current_tags"])
        | set(template_vocab["applied_tags"])
    )
    pair_tag_definitions = _load_pair_tag_definitions()

    return {
        "entity_kinds": sorted(kind.value for kind in EntityKind),
        "slots": sorted(slot.value for slot in Slot),
        "single_entity_tag_anchors": single_entity_tags,
        "durable_tags": _sorted_strings(template_vocab["durable_tags"]),
        "ephemeral_tags": _sorted_strings(template_vocab["ephemeral_tags"]),
        "current_tags": _sorted_strings(template_vocab["current_tags"]),
        "applied_tags": _sorted_strings(template_vocab["applied_tags"]),
        "multi_entity_tag_families": [item["tag"] for item in pair_tag_definitions],
        "multi_entity_tag_definitions": pair_tag_definitions,
        "event_types": _sorted_strings(template_vocab["event_types"]),
        "place_affordances": _sorted_strings(template_vocab["place_affordances"]),
        "relationship_types": _sorted_strings(template_vocab["relationship_types"]),
    }


def _load_pair_tag_definitions() -> list[PairTagPrimitive]:
    """Load pair-tag seed definitions from the shared built-in registry."""

    definitions: list[PairTagPrimitive] = []
    for tag, subject_kinds, object_kinds, is_ephemeral, _description in PAIR_TAG_SEED:
        definitions.append(
            {
                "tag": str(tag),
                "subject_kinds": [str(kind) for kind in subject_kinds],
                "object_kinds": [str(kind) for kind in object_kinds],
                "is_ephemeral": bool(is_ephemeral),
            }
        )
    return sorted(definitions, key=lambda item: item["tag"])


def _sorted_strings(values: object) -> list[str]:
    """Return stable string ordering for a vocabulary bucket."""

    return sorted(str(value) for value in values)

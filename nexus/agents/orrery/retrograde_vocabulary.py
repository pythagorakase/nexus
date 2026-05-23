"""Seed-eligible Orrery vocabulary enumeration for Retrograde generation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import TypedDict

from nexus.agents.orrery.catalog import _collect_vocabulary
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
    substrate enums for typed entities and slots, and the pair-tag migration's
    seed registry for directed multi-entity tag families.
    """

    template_vocab = _collect_vocabulary(BUILTIN_TEMPLATES)
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
        "durable_tags": list(template_vocab["durable_tags"]),
        "ephemeral_tags": list(template_vocab["ephemeral_tags"]),
        "current_tags": list(template_vocab["current_tags"]),
        "applied_tags": list(template_vocab["applied_tags"]),
        "multi_entity_tag_families": [item["tag"] for item in pair_tag_definitions],
        "multi_entity_tag_definitions": pair_tag_definitions,
        "event_types": list(template_vocab["event_types"]),
        "place_affordances": list(template_vocab["place_affordances"]),
        "relationship_types": list(template_vocab["relationship_types"]),
    }


def _load_pair_tag_definitions() -> list[PairTagPrimitive]:
    """Load pair-tag seed definitions from their existing migration registry."""

    migration = _load_python_module(
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "042_orrery_entity_pair_tags.py"
    )
    seed_rows = getattr(migration, "PAIR_TAG_SEED")
    definitions: list[PairTagPrimitive] = []
    for tag, subject_kinds, object_kinds, is_ephemeral, _description in seed_rows:
        definitions.append(
            {
                "tag": str(tag),
                "subject_kinds": [str(kind) for kind in subject_kinds],
                "object_kinds": [str(kind) for kind in object_kinds],
                "is_ephemeral": bool(is_ephemeral),
            }
        )
    return sorted(definitions, key=lambda item: item["tag"])


def _load_python_module(path: Path) -> ModuleType:
    """Load a Python file by path without requiring importable package names."""

    spec = importlib.util.spec_from_file_location(
        f"nexus_orrery_retrograde_{path.stem}",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Orrery registry module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

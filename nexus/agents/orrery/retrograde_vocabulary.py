"""Seed-eligible Orrery vocabulary enumeration for Retrograde generation."""

from __future__ import annotations

from typing import Iterable, Literal, TypedDict

from nexus.agents.orrery.catalog import collect_template_vocabulary
from nexus.agents.orrery.pair_tag_registry import PAIR_TAG_SEED
from nexus.agents.orrery.substrate import EntityKind, Slot
from nexus.agents.orrery.tag_library import read_event_types, read_tag_library
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES


class PairTagPrimitive(TypedDict):
    """One registered multi-entity tag family with kind constraints."""

    tag: str
    subject_kinds: list[str]
    object_kinds: list[str]
    is_ephemeral: bool


SeedTagPolicy = Literal["stable_seed", "event_anchored", "prompt_visible_only"]


class CategorySeedPolicy(TypedDict):
    """Retrograde policy for one prompt-visible registered tag category."""

    category: str
    entity_kind: str
    policy: SeedTagPolicy
    reason: str


class SeedEligibleVocabulary(TypedDict):
    """Primitive vocabulary Retrograde may use for substrate-legal seeds."""

    entity_kinds: list[str]
    slots: list[str]
    single_entity_tag_anchors: list[str]
    durable_tags: list[str]
    ephemeral_tags: list[str]
    current_tags: list[str]
    applied_tags: list[str]
    registered_single_entity_tags: list[str]
    registered_tag_categories: list[str]
    registered_tags_by_category: dict[str, list[str]]
    registered_tags_by_entity_kind: dict[str, list[str]]
    registered_category_seed_policies: list[CategorySeedPolicy]
    registered_tags_by_seed_policy: dict[str, list[str]]
    multi_entity_tag_families: list[str]
    multi_entity_tag_definitions: list[PairTagPrimitive]
    event_types: list[str]
    place_classes: list[str]
    relationship_types: list[str]


# Seed-eligible vs prompt-visible category split (issue #300, settled in M4).
# Every category registered in the live tag registry is classified explicitly
# below; categories absent from both seed-eligible sets are prompt-visible
# only, which is the conservative direction (prose context, never mechanical
# Retrograde writes). New categories therefore ship locked until a deliberate
# edit promotes them.
STABLE_SEED_TAG_CATEGORIES: frozenset[str] = frozenset(
    {
        # Character identity, role, and capability (stable present-state).
        "bodyform",
        "bodyform.lineage",
        "bodyform.condition",
        "disposition",
        "capacity",
        "profession_lite",
        "role",
        "role.function",
        "role.resources",
        "role.fame",
        # Place affordances and stable place character.
        "place_function",
        "place_affordance",
        "place_visibility",
        "place_access",
        "place_environment",
        # Faction identity, economy, posture, and standing.
        "ideology",
        "ideology_axis",
        "resource_base",
        "resource_class",
        "legitimacy",
        "legitimacy_status",
        "operational_mode",
        "operational_secrecy",
        "power_posture",
        "history_class",
    }
)
EVENT_ANCHORED_TAG_CATEGORIES: frozenset[str] = frozenset(
    {
        "state",
        "place_threat",
        "power_status",
        "agenda",
        "hidden_agenda_class",
        "relationship_risk",
    }
)
# Forward-runtime Orrery bookkeeping (needs, schedules, signals, cover, and
# intimacy machinery). Pinned prompt-visible-only: the tick loop owns these
# writes; Retrograde history generation must never seed them mechanically.
RUNTIME_ONLY_TAG_CATEGORY_PREFIX = "orrery_"


def enumerate_seed_eligible_vocabulary(
    dbname: str | None = None,
) -> SeedEligibleVocabulary:
    """Return the current substrate-legal primitive set for Retrograde seeds.

    The enumeration is read from the same Python sources the forward Orrery
    already uses: built-in templates for package-facing tags/events/relations,
    substrate enums for typed entities and slots, and the shared pair-tag
    registry for directed multi-entity tag families. When ``dbname`` is passed,
    the live slot tag registry is included so Retrograde seed prompts can see
    post-migration categories that are not yet referenced by templates.
    """

    template_vocab = collect_template_vocabulary(BUILTIN_TEMPLATES)
    registry_vocab = _collect_registry_vocabulary(dbname)
    event_types = (
        read_event_types(dbname)
        if dbname is not None
        else _sorted_strings(template_vocab["event_types"])
    )
    single_entity_tags = sorted(
        set(template_vocab["durable_tags"])
        | set(template_vocab["ephemeral_tags"])
        | set(template_vocab["current_tags"])
        | set(template_vocab["applied_tags"])
        | set(registry_vocab["registered_single_entity_tags"])
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
        "registered_single_entity_tags": registry_vocab[
            "registered_single_entity_tags"
        ],
        "registered_tag_categories": registry_vocab["registered_tag_categories"],
        "registered_tags_by_category": registry_vocab["registered_tags_by_category"],
        "registered_tags_by_entity_kind": registry_vocab[
            "registered_tags_by_entity_kind"
        ],
        "registered_category_seed_policies": registry_vocab[
            "registered_category_seed_policies"
        ],
        "registered_tags_by_seed_policy": registry_vocab[
            "registered_tags_by_seed_policy"
        ],
        "multi_entity_tag_families": [item["tag"] for item in pair_tag_definitions],
        "multi_entity_tag_definitions": pair_tag_definitions,
        "event_types": event_types,
        "place_classes": _sorted_strings(template_vocab["place_classes"]),
        "relationship_types": _sorted_strings(template_vocab["relationship_types"]),
    }


class _RegistryVocabulary(TypedDict):
    """Live tag registry projection for Retrograde seed prompts."""

    registered_single_entity_tags: list[str]
    registered_tag_categories: list[str]
    registered_tags_by_category: dict[str, list[str]]
    registered_tags_by_entity_kind: dict[str, list[str]]
    registered_category_seed_policies: list[CategorySeedPolicy]
    registered_tags_by_seed_policy: dict[str, list[str]]


def _collect_registry_vocabulary(dbname: str | None) -> _RegistryVocabulary:
    """Read active slot tag rows when a concrete slot database is supplied."""

    if dbname is None:
        return {
            "registered_single_entity_tags": [],
            "registered_tag_categories": [],
            "registered_tags_by_category": {},
            "registered_tags_by_entity_kind": {},
            "registered_category_seed_policies": [],
            "registered_tags_by_seed_policy": {},
        }

    entries = read_tag_library(dbname)
    tags_by_category: dict[str, set[str]] = {}
    tags_by_entity_kind: dict[str, set[str]] = {}
    tags_by_seed_policy: dict[str, set[str]] = {}
    category_entity_kinds: set[tuple[str, str]] = set()
    for entry in entries:
        _add_registry_entry(tags_by_category, entry.category, entry.tag)
        _add_registry_entry(tags_by_entity_kind, entry.entity_kind, entry.tag)
        seed_policy = category_seed_policy(entry.category, entry.entity_kind)
        _add_registry_entry(tags_by_seed_policy, seed_policy["policy"], entry.tag)
        category_entity_kinds.add((entry.category, entry.entity_kind))
    registered_tags = {entry.tag for entry in entries}
    registered_categories = {entry.category for entry in entries}

    return {
        "registered_single_entity_tags": _sorted_strings(registered_tags),
        "registered_tag_categories": _sorted_strings(registered_categories),
        "registered_tags_by_category": _sort_registry_mapping(tags_by_category),
        "registered_tags_by_entity_kind": _sort_registry_mapping(tags_by_entity_kind),
        "registered_category_seed_policies": [
            category_seed_policy(category, entity_kind)
            for category, entity_kind in sorted(category_entity_kinds)
        ],
        "registered_tags_by_seed_policy": _sort_registry_mapping(tags_by_seed_policy),
    }


def _add_registry_entry(
    target: dict[str, set[str]],
    key: str,
    tag: str,
) -> None:
    """Add one tag to a registry grouping."""

    target.setdefault(key, set()).add(tag)


def _sort_registry_mapping(values: dict[str, set[str]]) -> dict[str, list[str]]:
    """Return a deterministic registry grouping for JSON/prompt consumers."""

    return {
        key: _sorted_strings(tags)
        for key, tags in sorted(values.items(), key=lambda item: item[0])
    }


def category_seed_policy(category: str, entity_kind: str) -> CategorySeedPolicy:
    """Return the Retrograde generation policy for one registered category."""

    normalized = str(category)
    normalized_kind = str(entity_kind)
    if normalized.startswith(RUNTIME_ONLY_TAG_CATEGORY_PREFIX):
        return {
            "category": normalized,
            "entity_kind": normalized_kind,
            "policy": "prompt_visible_only",
            "reason": (
                "Forward-runtime Orrery bookkeeping category; the tick loop "
                "owns these writes and Retrograde must never seed them."
            ),
        }
    if normalized in STABLE_SEED_TAG_CATEGORIES:
        return {
            "category": normalized,
            "entity_kind": normalized_kind,
            "policy": "stable_seed",
            "reason": (
                "Stable identity, role, faction, or place affordance tags may "
                "be proposed as present-state seed outcomes."
            ),
        }
    if normalized in EVENT_ANCHORED_TAG_CATEGORIES:
        return {
            "category": normalized,
            "entity_kind": normalized_kind,
            "policy": "event_anchored",
            "reason": (
                "Current pressure tags in this category require an explicit "
                "retrograde event that caused or recently refreshed them."
            ),
        }
    return {
        "category": normalized,
        "entity_kind": normalized_kind,
        "policy": "prompt_visible_only",
        "reason": (
            "Category is prompt-visible but not yet approved for mechanical "
            "Retrograde seed writes; use as prose context only."
        ),
    }


def _load_pair_tag_definitions() -> list[PairTagPrimitive]:
    """Load pair-tag seed definitions from the shared built-in registry."""

    definitions: list[PairTagPrimitive] = []
    for (
        tag,
        subject_kinds,
        object_kinds,
        is_ephemeral,
        _description,
    ) in PAIR_TAG_SEED:
        definitions.append(
            {
                "tag": str(tag),
                "subject_kinds": [str(kind) for kind in subject_kinds],
                "object_kinds": [str(kind) for kind in object_kinds],
                "is_ephemeral": bool(is_ephemeral),
            }
        )
    return sorted(definitions, key=lambda item: item["tag"])


def _sorted_strings(values: Iterable[object]) -> list[str]:
    """Return stable string ordering for a vocabulary bucket."""

    return sorted(str(value) for value in values)

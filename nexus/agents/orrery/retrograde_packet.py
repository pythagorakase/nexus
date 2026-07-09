"""Dry-run Retrograde review packet assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from nexus.agents.orrery.retrograde_seed_candidates import (
    render_seed_generation_prompt,
    seed_candidate_response_schema,
)
from nexus.agents.orrery.retrograde_graph import build_candidate_graph
from nexus.agents.orrery.retrograde_vocabulary import SeedEligibleVocabulary
from nexus.config.settings_models import Settings

PACKET_SCHEMA_VERSION = "orrery_retrograde_dry_run_packet.v0"
SEED_REQUEST_SCHEMA_VERSION = "orrery_retrograde_seed_request.v0"
WEIRD_LEVELS = frozenset({"low", "medium", "high"})
# Prompt-section headings that carry first-class entity cards. The R6 entity
# budget check (retrograde_expansion._packet_known_entity_keys) matches these
# strings to rebuild the known-entity set, so they must be shared constants:
# silent heading drift would empty that set and hard-block valid expansions.
CORE_ENTITIES_HEADING = "Core entities"
NAMED_SEED_NPCS_HEADING = "Named seed NPCs"
SEED_BUDGETS: Mapping[str, Mapping[str, int]] = {
    "low": {"generate_candidates": 6, "select_target": 3, "deferred_secret_cap": 1},
    "medium": {"generate_candidates": 9, "select_target": 4, "deferred_secret_cap": 2},
    "high": {"generate_candidates": 12, "select_target": 5, "deferred_secret_cap": 3},
}
RETROGRADE_COVERAGE_FUNCTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "foundational_wound",
        "question": "What past harm, loss, bargain, or mistake still pressures now?",
    },
    {
        "id": "current_power_arrangement",
        "question": "Who benefits from the current order, and who is excluded?",
    },
    {
        "id": "hidden_truth",
        "question": "What consequential fact is concealed, misunderstood, or misfiled?",
    },
    {
        "id": "trait_bound_hook",
        "question": "Which selected trait becomes historically load-bearing?",
    },
    {
        "id": "opening_pressure",
        "question": "What old event makes the starting scenario urgent now?",
    },
    {
        "id": "optional_mythic_layer",
        "question": "What symbol, omen, legend, or myth can echo without dominating?",
    },
    {
        "id": "unresolved_ledger",
        "question": "What debt, oath, grudge, promise, or claim remains unpaid?",
    },
)


def build_retrograde_dry_run_packet(
    *,
    slot: int,
    dbname: str,
    cache: Any,
    vocabulary: SeedEligibleVocabulary,
    settings: Settings,
    weird_level: Optional[str] = None,
    weird_raw: Optional[float] = None,
    trait_compile_inputs: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build a non-mutating Retrograde packet from wizard cache and vocabulary.

    ``trait_compile_inputs`` carries the typed trait-compiler inputs (derived
    or wizard-collected) so trait-declared people, places, and factions become
    first-class core entities: Skald must reuse their exact names, keeping
    Retrograde refs aligned with the canonical rows the trait compiler creates
    in the same transition transaction.
    """

    setting = _require_cache_section(cache, "get_setting_dict", "setting")
    character = _require_cache_section(cache, "get_character_dict", "character")
    seed = _require_cache_section(cache, "get_seed_dict", "seed")
    layer = _optional_cache_section(cache, "get_layer_dict")
    zone = _optional_cache_section(cache, "get_zone_dict")
    initial_location = _optional_cache_section(cache, "get_initial_location")
    weird = resolve_weird_profile(
        settings=settings,
        setting=setting,
        weird_level=weird_level,
        weird_raw=weird_raw,
    )

    candidate_scaffolds = _candidate_scaffolds(
        character=character,
        seed=seed,
        layer=layer,
        zone=zone,
        initial_location=initial_location,
        trait_compile_inputs=trait_compile_inputs,
    )
    if settings.orrery is None:
        raise ValueError("settings.orrery is required for Retrograde budgets")
    seed_generation_request = build_seed_generation_request(
        candidate_scaffolds=candidate_scaffolds,
        vocabulary=vocabulary,
        weird=weird,
        max_new_entity_stubs=settings.orrery.retrograde.wizard.max_new_entity_stubs,
        graph_settings=settings.orrery.retrograde.graph,
    )

    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "dry_run": True,
        "mutation_policy": {
            "writes": "none",
            "review_contract": (
                "Retrograde A0 only assembles candidate prompt material. No "
                "world_events, entity_tags, relationships, or wizard cache rows "
                "are written. A later Skald-as-weaver pass must select, reject, "
                "or connect candidate seeds before any bootstrap persistence."
            ),
        },
        "slot": slot,
        "dbname": dbname,
        "wizard_phase": (
            cache.current_phase() if hasattr(cache, "current_phase") else "unknown"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "setting": setting,
            "character": character,
            "seed": seed,
            "layer": layer,
            "zone": zone,
            "initial_location": initial_location,
        },
        "weird": weird,
        "vocabulary_summary": _vocabulary_summary(vocabulary),
        "seed_eligible_vocabulary": vocabulary,
        "candidate_scaffolds": candidate_scaffolds,
        "seed_generation_request": seed_generation_request,
        "seed_generation_prompt": render_seed_generation_prompt(
            seed_generation_request=seed_generation_request,
            vocabulary=vocabulary,
        ),
        "skald_weaver_instructions": _skald_weaver_instructions(),
    }


def build_seed_generation_request(
    *,
    candidate_scaffolds: Mapping[str, Any],
    vocabulary: SeedEligibleVocabulary,
    weird: Mapping[str, Any],
    max_new_entity_stubs: Optional[int] = None,
    rng_seed_material: Optional[str] = None,
    budget_override: Optional[Mapping[str, int]] = None,
    graph_settings: Any = None,
) -> dict[str, Any]:
    """Build the non-mutating R4/R5 request contract for Skald-as-weaver.

    ``budget_override`` replaces the level-derived generate/select counts —
    the runtime maturation path passes its tighter budget here so the R3
    candidate graph is sized for the budget that will actually run, not
    the wizard default.
    """

    level = str(weird.get("level") or "medium")
    budget = dict(SEED_BUDGETS.get(level, SEED_BUDGETS["medium"]))
    if budget_override is not None:
        budget.update({key: int(value) for key, value in budget_override.items()})
    # This is a coarse review hint, not an extra tuning knob; the explicit
    # generate/select counts carry the meaningful level-specific budget.
    budget["overgenerate_multiplier"] = max(
        1,
        round(budget["generate_candidates"] / budget["select_target"]),
    )
    if max_new_entity_stubs is not None:
        # Decision 8 entity-coverage cap: how many entities beyond the
        # first-class starting set the eventual R6 expansion may introduce
        # as minimum-viable stubs.
        budget["max_new_entity_stubs"] = int(max_new_entity_stubs)

    # R3: the procedural candidate graph. The seed material defaults to a
    # stable identity derived from the intentional core, so a re-run of the
    # same wizard artifacts rebuilds the identical graph (dry-run == live).
    if rng_seed_material is None:
        core_names = ",".join(
            str(card.get("name"))
            for card in candidate_scaffolds.get("core_entities", ())
            if card.get("name")
        )
        rng_seed_material = f"retrograde_graph_v1:{core_names}"
    candidate_graph = build_candidate_graph(
        candidate_scaffolds=candidate_scaffolds,
        vocabulary=vocabulary,
        weird=weird,
        generate_candidates=int(budget["generate_candidates"]),
        rng_seed_material=rng_seed_material,
        graph_settings=graph_settings,
    )

    return {
        "schema_version": SEED_REQUEST_SCHEMA_VERSION,
        "stage": "R4/R5 seed generation and selection input",
        "mutation_policy": {
            "writes": "none",
            "selection_required_before_persistence": True,
            "discarded_seed_cost": "inference only",
        },
        "budget": budget,
        "weird_policy": _weird_generation_policy(weird),
        "mechanical_tag_policy": _mechanical_tag_policy(vocabulary),
        "coverage_functions": list(RETROGRADE_COVERAGE_FUNCTIONS),
        "candidate_graph": candidate_graph,
        "selection_rubric": _selection_rubric(level),
        "prompt_sections": _seed_prompt_sections(candidate_scaffolds),
        "candidate_response_schema": seed_candidate_response_schema(),
        "candidate_output_schema": {
            "type": "object",
            "required_fields": [
                "seed_id",
                "summary",
                "origin_friction",
                "present_leaf_anchor",
                "coverage_functions",
                "mechanical_hints",
                "defer_or_reject_if",
            ],
            "mechanical_hints": {
                "event_types": "Use only seed_eligible_vocabulary.event_types.",
                "single_entity_tags": (
                    "Use only seed_eligible_vocabulary.registered_* tags and "
                    "respect mechanical_tag_policy."
                ),
                "pair_tags": (
                    "Use only seed_eligible_vocabulary.multi_entity_tag_definitions "
                    "with matching subject/object kinds."
                ),
                "relationships": (
                    "Use only seed_eligible_vocabulary.relationship_types."
                ),
            },
        },
    }


def resolve_weird_profile(
    *,
    settings: Settings,
    setting: Mapping[str, Any],
    weird_level: Optional[str] = None,
    weird_raw: Optional[float] = None,
) -> dict[str, Any]:
    """Resolve player-facing weirdness into the configured raw calibration band."""

    if settings.orrery is None:
        raise ValueError("settings.orrery is required for Retrograde weirdness")
    weird_settings = settings.orrery.retrograde.weird
    level = weird_level or weird_settings.default_level
    if level not in WEIRD_LEVELS:
        raise ValueError("Retrograde weird level must be low, medium, or high")

    selected_genre = _select_genre(setting, weird_settings.bands_by_genre)
    if weird_raw is not None:
        if not weird_settings.dev.min <= weird_raw <= weird_settings.dev.max:
            raise ValueError(
                "Retrograde raw weirdness must be within "
                f"{weird_settings.dev.min:g}..{weird_settings.dev.max:g}"
            )
        return {
            "source": "raw_override",
            "level": level,
            "genre": selected_genre["genre"],
            "genre_input": selected_genre["input"],
            "raw": float(weird_raw),
            "raw_min": float(weird_raw),
            "raw_max": float(weird_raw),
        }

    bands = weird_settings.bands_by_genre.get(selected_genre["genre"])
    if bands is None:
        raise ValueError(
            "No Retrograde weirdness bands configured for genre "
            f"{selected_genre['input']!r}"
        )
    band = getattr(bands, level)
    return {
        "source": "configured_band",
        "level": level,
        "genre": selected_genre["genre"],
        "genre_input": selected_genre["input"],
        "raw_min": band.min,
        "raw_max": band.max,
        "raw_midpoint": (band.min + band.max) / 2.0,
    }


def _weird_generation_policy(weird: Mapping[str, Any]) -> dict[str, Any]:
    """Describe how the resolved weird profile should affect seed generation."""

    level = str(weird.get("level") or "medium")
    raw = weird.get("raw")
    if raw is None:
        raw = weird.get("raw_midpoint")
    return {
        "level": level,
        "raw": raw,
        "genre": weird.get("genre"),
        "rubric_bias": {
            "low": "favor seeds that serve one or more coverage functions directly",
            "medium": "mix coverage-serving seeds with stranger connective tissue",
            "high": "admit orthogonal seeds if the leaf anchor is strong",
        }.get(level, "mix coverage-serving seeds with stranger connective tissue"),
        "friction_guidance": {
            "low": "low origin friction; surprise should feel latent in the premise",
            "medium": "moderate origin friction; preserve genre coherence",
            "high": "high origin friction; coherence is enforced at the leaf anchor",
        }.get(level, "moderate origin friction; preserve genre coherence"),
    }


def _mechanical_tag_policy(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    """Summarize how registered vocabulary may be used in seed candidates."""

    policies = vocabulary.get("registered_category_seed_policies", [])
    categories_by_policy: dict[str, list[str]] = {}
    for policy in policies:
        categories_by_policy.setdefault(policy["policy"], []).append(policy["category"])

    return {
        "stable_seed_categories": sorted(
            set(categories_by_policy.get("stable_seed", []))
        ),
        "event_anchored_categories": sorted(
            set(categories_by_policy.get("event_anchored", []))
        ),
        "prompt_visible_only_categories": sorted(
            set(categories_by_policy.get("prompt_visible_only", []))
        ),
        "registered_tags_by_seed_policy": vocabulary.get(
            "registered_tags_by_seed_policy", {}
        ),
        "rules": [
            (
                "Stable seed categories may be proposed as present-state tags "
                "when supported by the seed."
            ),
            (
                "Event-anchored categories may be proposed only with an explicit "
                "event that caused or recently refreshed the current state."
            ),
            (
                "Prompt-visible-only categories may guide prose but must not be "
                "proposed as mechanical writes in this stage."
            ),
            "Unknown tag names are invalid; omit marginal mechanics instead.",
        ],
    }


def _selection_rubric(level: str) -> dict[str, Any]:
    """Return R5 selection instructions for the generated seed pool."""

    return {
        "coverage_is_checklist_not_scaffold": True,
        "priorities": [
            "Keep seeds with strong leaf anchors to core entities.",
            "Keep seeds that can be made substrate-legal with registered vocabulary.",
            (
                "Reject seeds that require unregistered tags, recursive entity "
                "expansion, or timeline contortions."
            ),
            "Prefer fewer, sharper surviving seeds over a busy history web.",
        ],
        "weird_level_adjustment": {
            "low": "coverage function service is a strong positive prior",
            "medium": "coverage service and origin surprise should be balanced",
            "high": "coverage service is optional when the present anchor is strong",
        }.get(level, "coverage service and origin surprise should be balanced"),
    }


def _seed_prompt_sections(
    candidate_scaffolds: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return deterministic prompt sections for R4 seed generation."""

    return [
        {
            "heading": CORE_ENTITIES_HEADING,
            "items": _present_items(candidate_scaffolds.get("core_entities")),
        },
        {
            "heading": NAMED_SEED_NPCS_HEADING,
            "items": _present_items(candidate_scaffolds.get("named_seed_npcs")),
        },
        {
            "heading": "Pressure axes",
            "items": _present_items(candidate_scaffolds.get("pressure_axes")),
        },
        {
            "heading": "Trait hooks",
            "items": _trait_prompt_items(candidate_scaffolds.get("trait_hooks")),
        },
    ]


def _trait_target_cards(
    trait_compile_inputs: Optional[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return core-entity cards for trait-declared people, places, factions.

    The trait compiler creates canonical rows for these names inside the same
    transition transaction, before Retrograde persistence resolves expansion
    refs. Exposing them as core entities makes Skald reuse the exact names,
    so refs resolve as already_present instead of minting duplicate stubs.
    """

    if not trait_compile_inputs:
        return []

    cards: list[dict[str, Any]] = []
    ref_rule = "Canonical name: refer to this entity with exactly this name."

    def add(kind: str, role: str, target: Mapping[str, Any]) -> None:
        name = target.get("name")
        if not name:
            return
        summary = (
            target.get("history")
            or target.get("dynamic")
            or f"Trait-declared {role} of the protagonist."
        )
        cards.append(
            _compact_card(
                kind=kind,
                role=f"trait_target:{role}",
                name=name,
                summary=summary,
                details={"ref_rule": ref_rule},
            )
        )

    patron = _mapping(trait_compile_inputs.get("patron"))
    if patron:
        add("character", "patron", patron)
    for target in _mapping(trait_compile_inputs.get("dependents")).get("targets") or []:
        add("character", "dependent", _mapping(target))
    for target in (
        _mapping(trait_compile_inputs.get("obligations")).get("targets") or []
    ):
        target_map = _mapping(target)
        kind = (
            "faction"
            if target_map.get("counterparty_kind") == "faction"
            else "character"
        )
        add(kind, "obligation_counterparty", target_map)
    relationship_roles = {"allies": "ally", "contacts": "contact", "enemies": "enemy"}
    for trait_name, role in relationship_roles.items():
        for target in (
            _mapping(trait_compile_inputs.get(trait_name)).get("targets") or []
        ):
            add("character", role, _mapping(target))
    domain = _mapping(trait_compile_inputs.get("domain"))
    if domain:
        add("place", "domain", domain)
    status = _mapping(trait_compile_inputs.get("status"))
    if status and status.get("scope_faction_name"):
        add(
            "faction",
            "status_scope",
            {"name": status.get("scope_faction_name")},
        )
    return cards


def _candidate_scaffolds(
    *,
    character: Mapping[str, Any],
    seed: Mapping[str, Any],
    layer: Optional[Mapping[str, Any]],
    zone: Optional[Mapping[str, Any]],
    initial_location: Optional[Mapping[str, Any]],
    trait_compile_inputs: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return deterministic R2/R3 scaffold cards for later seed generation."""

    concept = _mapping(character.get("concept"))
    trait_selection = _mapping(character.get("trait_selection"))
    wildcard = _mapping(character.get("wildcard"))
    selected_traits = list(trait_selection.get("selected_traits") or ())

    return {
        "core_entities": [
            _compact_card(
                kind="character",
                role="protagonist",
                name=concept.get("name"),
                summary=concept.get("background") or concept.get("archetype"),
                details={
                    "archetype": concept.get("archetype"),
                    "appearance": concept.get("appearance"),
                },
            ),
            _compact_card(
                kind="place",
                role="starting_location",
                name=_mapping(initial_location).get("name"),
                summary=_mapping(initial_location).get("description")
                or _mapping(initial_location).get("summary"),
                details=_mapping(initial_location),
            ),
            _compact_card(
                kind="zone",
                role="starting_zone",
                name=_mapping(zone).get("name"),
                summary=_mapping(zone).get("summary"),
                details=_mapping(zone),
            ),
            _compact_card(
                kind="layer",
                role="starting_layer",
                name=_mapping(layer).get("name"),
                summary=_mapping(layer).get("description"),
                details=_mapping(layer),
            ),
            *_trait_target_cards(trait_compile_inputs),
        ],
        "named_seed_npcs": [
            {"kind": "character", "role": "seed_npc", "name": name}
            for name in seed.get("key_npcs", [])
            if name
        ],
        "pressure_axes": [
            _axis("stakes", seed.get("stakes")),
            _axis("tension_source", seed.get("tension_source")),
            _axis("hook", seed.get("hook")),
            _axis("immediate_goal", seed.get("immediate_goal")),
            _axis("seed_secrets", seed.get("secrets")),
        ],
        "trait_hooks": {
            "selected_traits": selected_traits,
            "rationales": trait_selection.get("trait_rationales") or {},
            "wildcard": {
                "name": wildcard.get("wildcard_name"),
                "description": wildcard.get("wildcard_description"),
                "orrery_tags": wildcard.get("orrery_tags"),
            },
        },
        "candidate_seed_contract": {
            "stage": "R4 seed generation input",
            "target_output": "candidate seeds only",
            "selection_required": True,
            "discard_cost": "inference only",
            "anchor_rule": "Every surviving thread must connect back to a core entity.",
        },
    }


def _vocabulary_summary(vocabulary: SeedEligibleVocabulary) -> dict[str, int]:
    """Return compact counts for CLI and review-packet scanning."""

    return {
        "entity_kinds": len(vocabulary["entity_kinds"]),
        "single_entity_tag_anchors": len(vocabulary["single_entity_tag_anchors"]),
        "registered_tag_categories": len(vocabulary["registered_tag_categories"]),
        "multi_entity_tag_families": len(vocabulary["multi_entity_tag_families"]),
        "event_types": len(vocabulary["event_types"]),
        "place_classes": len(vocabulary["place_classes"]),
        "relationship_types": len(vocabulary["relationship_types"]),
    }


def _skald_weaver_instructions() -> list[str]:
    """Return the non-mutating prompt contract for the next Retrograde stage."""

    return [
        "Generate candidate deep-history seeds, not canonical history.",
        "Use only seed_eligible_vocabulary primitives for mechanical tags/events.",
        "Over-generate; later selection must be allowed to discard weak seeds.",
        (
            "Prefer surprise at the seed origin, but require leaf anchoring "
            "to present canon."
        ),
        "Do not write rows. Persistence belongs to a later reviewed expansion pass.",
    ]


def _select_genre(
    setting: Mapping[str, Any],
    configured_bands: Mapping[str, Any],
) -> dict[str, str]:
    candidates = [setting.get("genre"), *(setting.get("secondary_genres") or ())]
    for candidate in candidates:
        normalized = _normalize_genre(candidate)
        if normalized in configured_bands:
            return {"input": str(candidate), "genre": normalized}
    primary = candidates[0] if candidates else None
    normalized_primary = _normalize_genre(primary)
    return {"input": str(primary or ""), "genre": normalized_primary}


def _normalize_genre(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "science_fiction": "scifi",
        "sci_fi": "scifi",
        "post_apocalyptic": "postapocalyptic",
        "post_apocalypse": "postapocalyptic",
    }
    return aliases.get(normalized, normalized)


def _require_cache_section(
    cache: Any, method_name: str, label: str
) -> Mapping[str, Any]:
    section = _optional_cache_section(cache, method_name)
    if section is None:
        raise ValueError(f"Retrograde packet requires complete wizard {label} data")
    return section


def _optional_cache_section(
    cache: Any, method_name: str
) -> Optional[Mapping[str, Any]]:
    method = getattr(cache, method_name, None)
    if method is None:
        return None
    section = method()
    if section is None:
        return None
    if not isinstance(section, Mapping):
        raise ValueError(f"{method_name} must return a mapping or None")
    return section


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _present_items(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [item for item in value if item]


def _trait_prompt_items(value: Any) -> list[dict[str, Any]]:
    hooks = _mapping(value)
    selected_traits = hooks.get("selected_traits") or []
    rationales = _mapping(hooks.get("rationales"))
    wildcard = _mapping(hooks.get("wildcard"))

    items: list[dict[str, Any]] = [
        {"kind": "trait", "name": trait, "rationale": rationales.get(str(trait))}
        for trait in selected_traits
        if trait
    ]
    if wildcard:
        items.append({"kind": "wildcard", **dict(wildcard)})
    return items


def _axis(kind: str, text: Any) -> dict[str, Any]:
    return {"kind": kind, "text": text}


def _compact_card(
    *,
    kind: str,
    role: str,
    name: Any,
    summary: Any,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "role": role,
        "name": name,
        "summary": summary,
        "details": {key: value for key, value in details.items() if value is not None},
    }

"""Dry-run Retrograde review packet assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from nexus.agents.orrery.retrograde_vocabulary import SeedEligibleVocabulary
from nexus.config.settings_models import Settings

PACKET_SCHEMA_VERSION = "orrery_retrograde_dry_run_packet.v0"
WEIRD_LEVELS = frozenset({"low", "medium", "high"})


def build_retrograde_dry_run_packet(
    *,
    slot: int,
    dbname: str,
    cache: Any,
    vocabulary: SeedEligibleVocabulary,
    settings: Settings,
    weird_level: Optional[str] = None,
    weird_raw: Optional[float] = None,
) -> dict[str, Any]:
    """Build a non-mutating Retrograde packet from wizard cache and vocabulary."""

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
        "skald_weaver_instructions": _skald_weaver_instructions(),
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


def _candidate_scaffolds(
    *,
    character: Mapping[str, Any],
    seed: Mapping[str, Any],
    layer: Optional[Mapping[str, Any]],
    zone: Optional[Mapping[str, Any]],
    initial_location: Optional[Mapping[str, Any]],
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

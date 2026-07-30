"""Registry-keyed strict-schema models for the OpenAI Gaia seat.

The static Skald models remain the application contract.  This module builds a
request-time subclass whose closed-vocabulary fields reference named
``Literal`` aliases, then coerces accepted output back to the static wire at the
provider boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Annotated, Any, Literal, Mapping, Optional, Union, cast

from pydantic import Field, create_model
from typing_extensions import TypeAliasType

from nexus.agents.logon.apex_schema import (
    NewEntityDeclaration,
    NewEntityPairTagHint,
    OrreryAdjudication,
)
from nexus.agents.logon.orrery_tag_validation import (
    StorytellerVocabulary,
    read_storyteller_vocabulary,
)
from nexus.agents.logon.skald_wire import (
    CharacterUpdateDelta,
    FactionUpdateDelta,
    PlaceUpdateDelta,
    SkaldGaiaWire,
    UpdatesBlock,
)
from nexus.agents.orrery.tag_library import _registry_digest


class GaiaRegistrySchemaError(RuntimeError):
    """Base error for registry-backed Gaia strict-schema construction."""


class GaiaRegistryReadError(GaiaRegistrySchemaError):
    """Raised when the live closed vocabulary cannot be read."""


class GaiaRegistryVocabularyError(GaiaRegistrySchemaError):
    """Raised when a seeded slot has an unusable closed vocabulary."""


@dataclass(frozen=True)
class GaiaRegistryVocabulary:
    """Normalized, deterministic vocabulary used as a model-cache key."""

    character_tags: tuple[str, ...]
    place_tags: tuple[str, ...]
    faction_tags: tuple[str, ...]
    pair_tags: tuple[str, ...]
    event_types: tuple[str, ...]


@dataclass(frozen=True)
class GaiaRegistryWireSpec:
    """One loaded registry snapshot and its cached provider model."""

    model: type[SkaldGaiaWire]
    registry_digest: str
    vocabulary: StorytellerVocabulary


_MODEL_CACHE: dict[
    tuple[str, GaiaRegistryVocabulary],
    type[SkaldGaiaWire],
] = {}
_MODEL_CACHE_LOCK = Lock()


def load_gaia_registry_wire_spec(dbname: str) -> GaiaRegistryWireSpec:
    """Read one slot registry and return its digest-keyed Gaia wire model."""

    if not dbname:
        raise GaiaRegistryReadError(
            "Gaia registry enum schema requires a non-empty slot database name"
        )
    try:
        vocabulary = read_storyteller_vocabulary(dbname)
    except Exception as exc:
        raise GaiaRegistryReadError(
            f"Failed to read Gaia strict-schema vocabulary from {dbname!r}"
        ) from exc

    normalized = _normalize_vocabulary(vocabulary.tag_names_by_kind, vocabulary)
    digest = _registry_digest(
        tag_names=[
            *normalized.character_tags,
            *normalized.place_tags,
            *normalized.faction_tags,
        ],
        pair_tag_names=normalized.pair_tags,
        event_types=normalized.event_types,
    )
    return GaiaRegistryWireSpec(
        model=gaia_registry_wire_model(
            registry_digest=digest,
            vocabulary=normalized,
        ),
        registry_digest=digest,
        vocabulary=vocabulary,
    )


def gaia_registry_wire_model(
    *,
    registry_digest: str,
    vocabulary: GaiaRegistryVocabulary,
) -> type[SkaldGaiaWire]:
    """Return one cached request model for a normalized registry snapshot."""

    if not registry_digest:
        raise GaiaRegistryVocabularyError(
            "Gaia registry enum schema requires a non-empty registry digest"
        )
    _validate_normalized_vocabulary(vocabulary)
    cache_key = (registry_digest, vocabulary)
    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached
        model = _build_gaia_registry_wire_model(
            registry_digest=registry_digest,
            vocabulary=vocabulary,
        )
        _MODEL_CACHE[cache_key] = model
        return model


def gaia_wire_registry_digest(
    schema_model: type[SkaldGaiaWire],
) -> Optional[str]:
    """Return the registry digest attached to a dynamic Gaia subclass."""

    digest = getattr(schema_model, "__registry_digest__", None)
    return cast(Optional[str], digest)


def coerce_gaia_registry_wire(wire: SkaldGaiaWire) -> SkaldGaiaWire:
    """Coerce a request-time Gaia subclass into the static app contract."""

    if wire.__class__ is SkaldGaiaWire:
        return wire
    if not isinstance(wire, SkaldGaiaWire):
        raise TypeError("Gaia wire coercion requires a SkaldGaiaWire instance")
    return SkaldGaiaWire.model_validate(wire.model_dump(mode="python"))


def _normalize_vocabulary(
    tag_names_by_kind: Mapping[str, object],
    vocabulary: StorytellerVocabulary,
) -> GaiaRegistryVocabulary:
    normalized = GaiaRegistryVocabulary(
        character_tags=_normalize_names(
            "character tag", tag_names_by_kind.get("character")
        ),
        place_tags=_normalize_names("place tag", tag_names_by_kind.get("place")),
        faction_tags=_normalize_names("faction tag", tag_names_by_kind.get("faction")),
        pair_tags=_normalize_names("pair tag", vocabulary.pair_tag_names),
        event_types=_normalize_names("event type", vocabulary.event_types),
    )
    return normalized


def _normalize_names(label: str, values: object) -> tuple[str, ...]:
    if values is None:
        normalized: tuple[str, ...] = ()
    else:
        try:
            normalized = tuple(sorted({str(value) for value in cast(Any, values)}))
        except TypeError as exc:
            raise GaiaRegistryVocabularyError(
                f"Gaia registry enum schema received invalid {label} vocabulary"
            ) from exc
    if not normalized or any(not value for value in normalized):
        raise GaiaRegistryVocabularyError(
            f"Gaia registry enum schema requires a non-empty {label} vocabulary"
        )
    return normalized


def _validate_normalized_vocabulary(vocabulary: GaiaRegistryVocabulary) -> None:
    for label, values in (
        ("character tag", vocabulary.character_tags),
        ("place tag", vocabulary.place_tags),
        ("faction tag", vocabulary.faction_tags),
        ("pair tag", vocabulary.pair_tags),
        ("event type", vocabulary.event_types),
    ):
        if not values or any(not value for value in values):
            raise GaiaRegistryVocabularyError(
                f"Gaia registry enum schema requires a non-empty {label} vocabulary"
            )


def _literal_alias(
    name: str,
    values: tuple[str, ...],
    *,
    description: Optional[str] = None,
) -> Any:
    """Build one named runtime Literal so JSON Schema emits a shared $def."""

    literal = Literal.__getitem__(values)
    if description is not None:
        literal = Annotated[literal, Field(description=description)]
    return TypeAliasType(name, literal)


def _list_type(item_type: Any) -> Any:
    return list[item_type]


def _optional_type(item_type: Any) -> Any:
    return Union.__getitem__((item_type, type(None)))


def _union_type(*item_types: Any) -> Any:
    return Union.__getitem__(item_types)


def _empty_runtime_list() -> list[Any]:
    """Return an empty list for dynamically typed Pydantic fields."""

    return []


def _build_gaia_registry_wire_model(
    *,
    registry_digest: str,
    vocabulary: GaiaRegistryVocabulary,
) -> type[SkaldGaiaWire]:
    character_tag_name = _literal_alias("CharacterTagName", vocabulary.character_tags)
    place_tag_name = _literal_alias("PlaceTagName", vocabulary.place_tags)
    faction_tag_name = _literal_alias("FactionTagName", vocabulary.faction_tags)
    pair_tag_name = _literal_alias(
        "PairTagName",
        vocabulary.pair_tags,
        description="Registered pair-tag name (e.g., protects, obligation).",
    )
    event_type_name = _literal_alias("EventTypeName", vocabulary.event_types)

    pair_hint_model = create_model(
        "NewEntityPairTagHintRegistry",
        __base__=NewEntityPairTagHint,
        __module__=__name__,
        tag=(pair_tag_name, ...),
    )

    def declaration_model(
        name: str,
        kind: str,
        tag_name_type: Any,
    ) -> type[NewEntityDeclaration]:
        return create_model(
            name,
            __base__=NewEntityDeclaration,
            __module__=__name__,
            kind=(
                Literal.__getitem__((kind,)),
                Field(description="Entity kind for the new declaration."),
            ),
            tag_hints=(
                _list_type(tag_name_type),
                Field(
                    default_factory=_empty_runtime_list,
                    description="Registered single-entity tag names for the new stub.",
                ),
            ),
            pair_tag_hints=(
                _list_type(pair_hint_model),
                Field(
                    default_factory=_empty_runtime_list,
                    description=(
                        "Registered pair-tag hints connecting the declared entity."
                    ),
                ),
            ),
        )

    character_declaration_model = declaration_model(
        "CharacterNewEntityDeclarationRegistry",
        "character",
        character_tag_name,
    )
    place_declaration_model = declaration_model(
        "PlaceNewEntityDeclarationRegistry",
        "place",
        place_tag_name,
    )
    faction_declaration_model = declaration_model(
        "FactionNewEntityDeclarationRegistry",
        "faction",
        faction_tag_name,
    )

    def update_model(
        name: str,
        base: (
            type[CharacterUpdateDelta]
            | type[PlaceUpdateDelta]
            | type[FactionUpdateDelta]
        ),
        tag_name_type: Any,
    ) -> Any:
        optional_tag_list = _optional_type(_list_type(tag_name_type))
        return create_model(
            name,
            __base__=base,
            __module__=__name__,
            tags_add=(
                optional_tag_list,
                Field(default=None, description="Registered tags to add."),
            ),
            tags_clear=(
                optional_tag_list,
                Field(default=None, description="Registered tags to clear."),
            ),
        )

    character_update_model = update_model(
        "CharacterUpdateDeltaRegistry",
        CharacterUpdateDelta,
        character_tag_name,
    )
    place_update_model = update_model(
        "PlaceUpdateDeltaRegistry",
        PlaceUpdateDelta,
        place_tag_name,
    )
    faction_update_model = update_model(
        "FactionUpdateDeltaRegistry",
        FactionUpdateDelta,
        faction_tag_name,
    )
    updates_model = create_model(
        "UpdatesBlockRegistry",
        __base__=UpdatesBlock,
        __module__=__name__,
        characters=(
            _list_type(character_update_model),
            Field(description="Character state changes."),
        ),
        places=(
            _list_type(place_update_model),
            Field(description="Place state changes."),
        ),
        factions=(
            _list_type(faction_update_model),
            Field(description="Faction state changes."),
        ),
    )
    adjudication_model = create_model(
        "OrreryAdjudicationRegistry",
        __base__=OrreryAdjudication,
        __module__=__name__,
        replacement_event_type=(
            _optional_type(event_type_name),
            Field(
                default=None,
                description=(
                    "Registered event type for a replacement_state_delta world_event."
                ),
            ),
        ),
    )
    declaration_union = _union_type(
        character_declaration_model,
        place_declaration_model,
        faction_declaration_model,
    )
    gaia_model = create_model(
        "SkaldGaiaRegistryWire",
        __base__=SkaldGaiaWire,
        __module__=__name__,
        updates=(
            _optional_type(updates_model),
            Field(default=None, description="Durable semantic state changes."),
        ),
        orrery_adjudications=(
            _list_type(adjudication_model),
            Field(
                default_factory=_empty_runtime_list,
                description="Rulings on current Orrery proposals.",
            ),
        ),
        new_entities=(
            _list_type(declaration_union),
            Field(
                default_factory=_empty_runtime_list,
                description="New persistent entities introduced by this turn.",
            ),
        ),
    )
    setattr(gaia_model, "__registry_digest__", registry_digest)
    return cast(type[SkaldGaiaWire], gaia_model)

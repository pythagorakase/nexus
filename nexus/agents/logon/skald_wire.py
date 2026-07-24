"""Sparse semantic-delta wire contract for extended Skald turns.

Presence is a character concept and setting is a place concept. Factions are
per-chunk mentions, never members of the carried scene roster.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus.agents.logon.apex_enums import (
    EmotionalValence,
    PlaceReferenceType,
    ReferenceType,
    RelationshipType,
    WorldLayerType,
)
from nexus.agents.logon.apex_schema import (
    CharacterReference,
    CharacterStateUpdate,
    ChronologyUpdate,
    ChunkMetadataUpdate,
    FactionReference,
    FactionStanceChange,
    FactionStateUpdate,
    LocationStateUpdate,
    NamedObservation,
    NewEntityDeclaration,
    Operations,
    OrreryAdjudication,
    PlaceReference,
    ReferencedEntities,
    RelationshipUpdate,
    StateUpdates,
    StorytellerResponseExtended,
)
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.api.native_structured_output import (
    de_null_schema,
    openai_response_text_format,
    strict_json_schema,
)


class SceneDelta(BaseModel):
    """Changed chronology or scene attributes."""

    elapsed_minutes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Total elapsed minutes.",
    )
    transition: Optional[Literal["new_episode", "new_season"]] = Field(
        default=None,
        description="Episode or season transition.",
    )
    world_layer: Optional[Literal["flashback", "atemporal", "extradiegetic"]] = Field(
        default=None,
        description="Non-primary narrative layer.",
    )
    weather: Optional[Literal["clear", "rain", "fog", "snow", "warm"]] = Field(
        default=None,
        description="Deliberate scene weather override.",
    )

    model_config = ConfigDict(extra="forbid")


class PresenceRef(BaseModel):
    """Small provider-facing entity reference."""

    kind: Literal["character", "place", "faction"] = Field(
        description="Referenced entity kind."
    )
    name: str = Field(min_length=1, description="Canonical entity name.")
    id: Optional[int] = Field(default=None, description="Canonical ID when known.")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class SceneReset(BaseModel):
    """Fresh character roster and setting after a scene cut."""

    place: PresenceRef = Field(description="New setting place.")
    present: List[PresenceRef] = Field(
        default_factory=list,
        description="Complete present-character roster.",
    )

    @model_validator(mode="after")
    def validate_presence_kinds(self) -> "SceneReset":
        """Reject ontology-invalid reset references."""

        if self.place.kind != "place":
            raise ValueError("scene_reset.place must be a place")
        if any(reference.kind != "character" for reference in self.present):
            raise ValueError("scene_reset.present accepts characters only")
        return self

    model_config = ConfigDict(extra="forbid")


class PresenceDelta(BaseModel):
    """Sparse changes to scene presence and references."""

    enter: List[PresenceRef] = Field(
        default_factory=list,
        description="Characters entering the scene.",
    )
    exit: List[PresenceRef] = Field(
        default_factory=list,
        description="Characters leaving the scene.",
    )
    mentions: List[PresenceRef] = Field(
        default_factory=list,
        description="Absent entities referenced this chunk.",
    )
    transit: List[PresenceRef] = Field(
        default_factory=list,
        description="Places passed through this chunk.",
    )
    scene_reset: Optional[SceneReset] = Field(
        default=None,
        description="Fresh roster and setting after relocation.",
    )

    @model_validator(mode="after")
    def validate_presence_kinds(self) -> "PresenceDelta":
        """Reject ontology-invalid presence references."""

        if any(reference.kind != "character" for reference in self.enter):
            raise ValueError("presence.enter accepts characters only")
        if any(reference.kind != "character" for reference in self.exit):
            raise ValueError("presence.exit accepts characters only")
        if any(reference.kind != "place" for reference in self.transit):
            raise ValueError("presence.transit accepts places only")
        if self.scene_reset is not None and (self.enter or self.exit):
            raise ValueError("scene_reset cannot be combined with enter or exit")
        enter_names = {reference.name.casefold() for reference in self.enter}
        exit_names = {reference.name.casefold() for reference in self.exit}
        overlap = enter_names & exit_names
        if overlap:
            raise ValueError(
                "presence cannot enter and exit the same character: "
                + ", ".join(sorted(overlap))
            )
        return self

    model_config = ConfigDict(extra="forbid")


class PresenceBaseline(BaseModel):
    """Parent chunk's present characters and setting place."""

    present: List[PresenceRef] = Field(
        default_factory=list,
        description="Parent present-character roster.",
    )
    setting: Optional[PresenceRef] = Field(
        default=None,
        description="Parent setting place.",
    )

    @model_validator(mode="after")
    def validate_presence_kinds(self) -> "PresenceBaseline":
        """Reject ontology-invalid baseline references."""

        if any(reference.kind != "character" for reference in self.present):
            raise ValueError("presence baseline accepts characters only")
        if self.setting is not None and self.setting.kind != "place":
            raise ValueError("presence baseline setting must be a place")
        return self

    model_config = ConfigDict(extra="forbid")


class CharacterUpdateDelta(BaseModel):
    """Sparse character state changes."""

    name: str = Field(min_length=1, description="Canonical character name.")
    id: Optional[int] = Field(default=None, description="Canonical ID when known.")
    activity: Optional[str] = Field(default=None, description="Current activity.")
    location: Optional[int] = Field(default=None, description="Current place ID.")
    emotional_state: Optional[str] = Field(
        default=None,
        description="Current emotional state.",
    )
    observations: Optional[List[NamedObservation]] = Field(
        default=None,
        description="New named observations.",
    )
    tags_add: Optional[List[str]] = Field(
        default=None,
        description="Registered tags to add.",
    )
    tags_clear: Optional[List[str]] = Field(
        default=None,
        description="Registered tags to clear.",
    )

    @model_validator(mode="after")
    def validate_substantive_update(self) -> "CharacterUpdateDelta":
        """Reject identity-only character update arms."""

        if not any(
            (
                self.activity,
                self.location is not None,
                self.emotional_state,
                self.observations,
                self.tags_add,
                self.tags_clear,
            )
        ):
            raise ValueError("character update requires a substantive field")
        return self

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class PlaceUpdateDelta(BaseModel):
    """Sparse place state changes."""

    name: str = Field(min_length=1, description="Canonical place name.")
    id: Optional[int] = Field(default=None, description="Canonical ID when known.")
    condition: Optional[str] = Field(default=None, description="Current conditions.")
    notable_change: Optional[str] = Field(
        default=None,
        description="One notable change.",
    )
    tags_add: Optional[List[str]] = Field(
        default=None,
        description="Registered tags to add.",
    )
    tags_clear: Optional[List[str]] = Field(
        default=None,
        description="Registered tags to clear.",
    )

    @model_validator(mode="after")
    def validate_substantive_update(self) -> "PlaceUpdateDelta":
        """Reject identity-only place update arms."""

        if not any(
            (
                self.condition,
                self.notable_change,
                self.tags_add,
                self.tags_clear,
            )
        ):
            raise ValueError("place update requires a substantive field")
        return self

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class FactionUpdateDelta(BaseModel):
    """Sparse faction state changes."""

    name: str = Field(min_length=1, description="Canonical faction name.")
    id: Optional[int] = Field(default=None, description="Canonical ID when known.")
    action: Optional[str] = Field(default=None, description="One recent action.")
    stance_toward: Optional[str] = Field(
        default=None,
        description="Target of a changed stance.",
    )
    stance: Optional[str] = Field(default=None, description="Updated stance.")
    tags_add: Optional[List[str]] = Field(
        default=None,
        description="Registered tags to add.",
    )
    tags_clear: Optional[List[str]] = Field(
        default=None,
        description="Registered tags to clear.",
    )

    @model_validator(mode="after")
    def validate_stance_pair(self) -> "FactionUpdateDelta":
        """Require both halves of a stance change."""

        if (self.stance_toward is None) != (self.stance is None):
            raise ValueError("stance_toward and stance must travel together")
        if not any(
            (
                self.action,
                self.stance_toward and self.stance,
                self.tags_add,
                self.tags_clear,
            )
        ):
            raise ValueError("faction update requires a substantive field")
        return self

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RelationshipUpdateDelta(BaseModel):
    """Sparse relationship state changes."""

    name: str = Field(min_length=1, description="First character name.")
    other_name: str = Field(min_length=1, description="Second character name.")
    id: Optional[int] = Field(default=None, description="First character ID.")
    other_id: Optional[int] = Field(default=None, description="Second character ID.")
    type: Optional[RelationshipType] = Field(
        default=None,
        description="Canonical relationship type.",
    )
    valence: Optional[EmotionalValence] = Field(
        default=None,
        description="Canonical emotional valence.",
    )
    dynamic: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Current relationship dynamic.",
    )
    recent_events: Optional[str] = Field(
        default=None,
        description="Recent relationship events.",
    )

    @model_validator(mode="after")
    def validate_substantive_update(self) -> "RelationshipUpdateDelta":
        """Reject identity-only relationship update arms."""

        if not any(
            (
                self.type is not None,
                self.valence is not None,
                self.dynamic,
                self.recent_events,
            )
        ):
            raise ValueError("relationship update requires a substantive field")
        return self

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class UpdatesBlock(BaseModel):
    """Namespaced semantic state changes."""

    characters: List[CharacterUpdateDelta] = Field(
        description="Character state changes."
    )
    places: List[PlaceUpdateDelta] = Field(description="Place state changes.")
    factions: List[FactionUpdateDelta] = Field(description="Faction state changes.")
    relationships: List[RelationshipUpdateDelta] = Field(
        description="Relationship state changes."
    )

    model_config = ConfigDict(extra="forbid")


class SkaldTurnWire(BaseModel):
    """Provider-facing semantic deltas for a non-bootstrap turn."""

    narrative: str = Field(description="Narrative prose.")
    choices: List[str] = Field(
        min_length=2,
        max_length=4,
        description="Two to four actionable player choices.",
    )
    scene: Optional[SceneDelta] = Field(
        default=None,
        description="Changed chronology or scene attributes.",
    )
    presence: Optional[PresenceDelta] = Field(
        default=None,
        description="Scene presence and reference changes.",
    )
    updates: Optional[UpdatesBlock] = Field(
        default=None,
        description="Durable semantic state changes.",
    )
    operations: Optional[Operations] = Field(
        default=None,
        description="Special runtime requests, when needed.",
    )
    orrery_adjudications: List[OrreryAdjudication] = Field(
        default_factory=list,
        description="Rulings on current Orrery proposals.",
    )
    new_entities: List[NewEntityDeclaration] = Field(
        default_factory=list,
        description="New persistent entities introduced by this turn.",
    )

    model_config = ConfigDict(extra="forbid")


def _hydrate_scene(scene: Optional[SceneDelta]) -> ChunkMetadataUpdate:
    """Map a scene delta to canonical chunk metadata."""

    if scene is None:
        return ChunkMetadataUpdate()

    chronology: Optional[ChronologyUpdate] = None
    if scene.elapsed_minutes is not None or scene.transition is not None:
        days: Optional[int] = None
        hours: Optional[int] = None
        minutes: Optional[int] = None
        if scene.elapsed_minutes is not None:
            day_count, remainder = divmod(scene.elapsed_minutes, 24 * 60)
            hour_count, minute_count = divmod(remainder, 60)
            days = day_count or None
            hours = hour_count or None
            minutes = (
                minute_count if minute_count or scene.elapsed_minutes == 0 else None
            )
        chronology = ChronologyUpdate(
            episode_transition=scene.transition or "continue",
            time_delta_minutes=minutes,
            time_delta_hours=hours,
            time_delta_days=days,
            time_delta_description=None,
        )

    return ChunkMetadataUpdate(
        chronology=chronology,
        world_layer=(
            WorldLayerType(scene.world_layer)
            if scene.world_layer is not None
            else WorldLayerType.PRIMARY
        ),
        scene_weather=scene.weather,
    )


def _presence_key(reference: PresenceRef) -> tuple[str, str]:
    """Return the stable set key used by roster math."""

    return reference.kind, reference.name.casefold()


def _deduplicate_presence(
    references: List[PresenceRef],
) -> List[PresenceRef]:
    """Keep the first occurrence of each semantic entity reference."""

    seen: set[tuple[str, str]] = set()
    result: List[PresenceRef] = []
    for reference in references:
        key = _presence_key(reference)
        if key not in seen:
            seen.add(key)
            result.append(reference)
    return result


def _hydrate_references(
    presence: Optional[PresenceDelta],
    baseline: Optional[PresenceBaseline],
) -> ReferencedEntities:
    """Apply presence deltas and build canonical reference models."""

    if presence is not None and baseline is None:
        raise ValueError("presence_baseline is required when presence is present")
    if presence is None and baseline is None:
        return ReferencedEntities()

    assert baseline is not None
    setting: Optional[PresenceRef]
    if presence is not None and presence.scene_reset is not None:
        roster = _deduplicate_presence(presence.scene_reset.present)
        setting = presence.scene_reset.place
    else:
        enter = presence.enter if presence is not None else []
        exit_references = presence.exit if presence is not None else []
        roster = _deduplicate_presence([*baseline.present, *enter])
        exit_keys = {_presence_key(reference) for reference in exit_references}
        roster = [
            reference
            for reference in roster
            if _presence_key(reference) not in exit_keys
        ]
        setting = baseline.setting

    mentions = presence.mentions if presence is not None else []
    transit = presence.transit if presence is not None else []

    characters = [
        CharacterReference(
            character_id=reference.id,
            character_name=reference.name,
            reference_type=ReferenceType.PRESENT,
        )
        for reference in roster
    ]
    characters.extend(
        CharacterReference(
            character_id=reference.id,
            character_name=reference.name,
            reference_type=ReferenceType.MENTIONED,
        )
        for reference in mentions
        if reference.kind == "character"
    )

    places: List[PlaceReference] = []
    if setting is not None:
        places.append(
            PlaceReference(
                place_id=setting.id,
                place_name=setting.name,
                reference_type=PlaceReferenceType.SETTING,
            )
        )
    places.extend(
        PlaceReference(
            place_id=reference.id,
            place_name=reference.name,
            reference_type=PlaceReferenceType.TRANSIT,
        )
        for reference in transit
    )
    places.extend(
        PlaceReference(
            place_id=reference.id,
            place_name=reference.name,
            reference_type=PlaceReferenceType.MENTIONED,
        )
        for reference in mentions
        if reference.kind == "place"
    )

    factions = [
        FactionReference(
            faction_id=reference.id,
            faction_name=reference.name,
            reference_type=ReferenceType.MENTIONED,
        )
        for reference in mentions
        if reference.kind == "faction"
    ]
    return ReferencedEntities(
        characters=characters,
        places=places,
        factions=factions,
    )


def _hydrate_tags(
    tags_add: Optional[List[str]],
    tags_clear: Optional[List[str]],
) -> Optional[OrreryTagBestowal]:
    """Map optional wire tag lists to one canonical bestowal."""

    if tags_add is None and tags_clear is None:
        return None
    return OrreryTagBestowal(
        applied_tags=tags_add or [],
        tags_to_clear=tags_clear or [],
    )


def _hydrate_updates(updates: Optional[UpdatesBlock]) -> StateUpdates:
    """Map namespaced semantic updates to canonical nested state lists."""

    if updates is None:
        return StateUpdates()

    characters: List[CharacterStateUpdate] = []
    locations: List[LocationStateUpdate] = []
    factions: List[FactionStateUpdate] = []
    relationships: List[RelationshipUpdate] = []

    for character_update in updates.characters:
        characters.append(
            CharacterStateUpdate(
                character_id=character_update.id,
                character_name=character_update.name,
                current_location=character_update.location,
                current_activity=character_update.activity,
                emotional_state=character_update.emotional_state,
                extra_observations=character_update.observations or [],
                orrery_tags=_hydrate_tags(
                    character_update.tags_add,
                    character_update.tags_clear,
                ),
            )
        )
    for place_update in updates.places:
        locations.append(
            LocationStateUpdate(
                place_id=place_update.id,
                place_name=place_update.name,
                current_conditions=place_update.condition,
                notable_changes=(
                    [place_update.notable_change]
                    if place_update.notable_change is not None
                    else []
                ),
                orrery_tags=_hydrate_tags(
                    place_update.tags_add,
                    place_update.tags_clear,
                ),
            )
        )
    for faction_update in updates.factions:
        factions.append(
            FactionStateUpdate(
                faction_id=faction_update.id,
                faction_name=faction_update.name,
                recent_actions=(
                    [faction_update.action] if faction_update.action is not None else []
                ),
                stance_changes=(
                    [
                        FactionStanceChange(
                            target=faction_update.stance_toward,
                            stance=faction_update.stance,
                        )
                    ]
                    if faction_update.stance_toward is not None
                    and faction_update.stance is not None
                    else []
                ),
                orrery_tags=_hydrate_tags(
                    faction_update.tags_add,
                    faction_update.tags_clear,
                ),
            )
        )
    for relationship_update in updates.relationships:
        relationships.append(
            RelationshipUpdate(
                character1_id=relationship_update.id,
                character1_name=relationship_update.name,
                character2_id=relationship_update.other_id,
                character2_name=relationship_update.other_name,
                relationship_type=relationship_update.type,
                emotional_valence=relationship_update.valence,
                dynamic=relationship_update.dynamic,
                recent_events=relationship_update.recent_events,
            )
        )

    return StateUpdates(
        characters=characters,
        relationships=relationships,
        locations=locations,
        factions=factions,
    )


def hydrate_skald_turn(
    wire: SkaldTurnWire,
    *,
    presence_baseline: Optional[PresenceBaseline] = None,
) -> StorytellerResponseExtended:
    """Hydrate one wire turn into the canonical application response.

    The mapper is pure: parent presence arrives as explicit input. Roster math
    is set-idempotent, so re-entering a present character or exiting an absent
    one is a tolerated no-op. A present ``presence`` block without a baseline
    raises instead of inventing an empty prior scene.
    """

    return StorytellerResponseExtended(
        narrative=wire.narrative,
        choices=wire.choices,
        chunk_metadata=_hydrate_scene(wire.scene),
        referenced_entities=_hydrate_references(
            wire.presence,
            presence_baseline,
        ),
        state_updates=_hydrate_updates(wire.updates),
        operations=wire.operations,
        orrery_adjudications=wire.orrery_adjudications,
        new_entities=wire.new_entities,
        reasoning=None,
    )


def skald_wire_strict_text_format() -> Dict[str, Any]:
    """Build the strict OpenAI Responses text format for Skald turns."""

    schema = strict_json_schema(SkaldTurnWire)
    return openai_response_text_format(SkaldTurnWire, schema=schema)


def skald_wire_lenient_schema() -> Dict[str, Any]:
    """Build the omittable-field schema for Anthropic and local endpoints."""

    return de_null_schema(SkaldTurnWire.model_json_schema())


def _prompt_guide_ref_name(ref: str) -> str:
    """Return a local definition name from a JSON Schema reference."""

    prefix = "#/$defs/"
    if not ref.startswith(prefix) or not ref[len(prefix) :]:
        raise ValueError(f"Unsupported Skald wire schema reference: {ref!r}")
    return ref[len(prefix) :]


def _prompt_guide_type(
    schema_node: Dict[str, Any],
    definitions: Dict[str, Any],
) -> str:
    """Render one compact type expression from a JSON Schema node."""

    ref = schema_node.get("$ref")
    if ref is not None:
        ref_name = _prompt_guide_ref_name(ref)
        target = definitions[ref_name]
        if target.get("type") == "object":
            return ref_name
        return _prompt_guide_type(target, definitions)

    schema_type = schema_node.get("type")
    if schema_type == "array":
        items = schema_node.get("items")
        if not isinstance(items, dict):
            raise ValueError("Skald wire array schema is missing an items schema")
        return f"{_prompt_guide_type(items, definitions)}[]"
    if schema_type == "object":
        raise ValueError(
            "Skald wire prompt guide does not support inline object schemas; "
            "use a named $defs model"
        )
    if isinstance(schema_type, str):
        return schema_type

    for union_key in ("anyOf", "oneOf"):
        members = schema_node.get(union_key)
        if isinstance(members, list) and members:
            return "|".join(
                _prompt_guide_type(member, definitions) for member in members
            )
    raise ValueError(f"Unsupported Skald wire schema node: {schema_node!r}")


def _prompt_guide_enum(
    schema_node: Dict[str, Any],
    definitions: Dict[str, Any],
) -> Optional[List[Any]]:
    """Return the enum governing a field, following local references."""

    ref = schema_node.get("$ref")
    if ref is not None:
        return _prompt_guide_enum(
            definitions[_prompt_guide_ref_name(ref)],
            definitions,
        )
    enum_values = schema_node.get("enum")
    if enum_values is not None:
        if not isinstance(enum_values, list):
            raise ValueError("Skald wire enum schema must contain a list")
        return enum_values
    items = schema_node.get("items")
    if isinstance(items, dict):
        return _prompt_guide_enum(items, definitions)
    return None


def _prompt_guide_object_refs(
    schema_node: Dict[str, Any],
    definitions: Dict[str, Any],
) -> List[str]:
    """Collect directly referenced object definitions in declaration order."""

    refs: List[str] = []
    ref = schema_node.get("$ref")
    if ref is not None:
        ref_name = _prompt_guide_ref_name(ref)
        target = definitions[ref_name]
        if target.get("type") == "object":
            refs.append(ref_name)
        return refs

    items = schema_node.get("items")
    if isinstance(items, dict):
        refs.extend(_prompt_guide_object_refs(items, definitions))
    for union_key in ("anyOf", "oneOf", "allOf"):
        members = schema_node.get(union_key)
        if isinstance(members, list):
            for member in members:
                refs.extend(_prompt_guide_object_refs(member, definitions))
    return refs


def skald_wire_prompt_guide() -> str:
    """Render a compact prompted-output guide from the lenient wire schema."""

    schema = skald_wire_lenient_schema()
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        raise ValueError("Skald wire schema definitions must be an object")

    root_name = schema.get("title")
    if not isinstance(root_name, str) or not root_name:
        raise ValueError("Skald wire schema must have a title")

    lines = [
        "=== OUTPUT FORMAT ===",
        (
            "Respond with a single JSON object matching this structure. "
            "Omit optional fields that have no value. No prose outside the JSON."
        ),
        "Legend: ! required; ? optional; named types are objects; T[] is an array.",
        "```text",
    ]
    object_queue: List[tuple[str, Dict[str, Any]]] = [(root_name, schema)]
    queued_names = {root_name}

    for object_name, object_schema in object_queue:
        properties = object_schema.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(
                f"Skald wire object {object_name!r} has no property mapping"
            )
        required = object_schema.get("required", [])
        if not isinstance(required, list):
            raise ValueError(
                f"Skald wire object {object_name!r} has an invalid required list"
            )
        required_names = set(required)

        lines.append(f"{object_name}{{")
        for property_name, property_schema in properties.items():
            if not isinstance(property_schema, dict):
                raise ValueError(
                    f"Skald wire property {object_name}.{property_name} is invalid"
                )
            field_type = _prompt_guide_type(property_schema, definitions)
            status = "!" if property_name in required_names else "?"
            enum_values = _prompt_guide_enum(property_schema, definitions)
            enum_text = (
                "|enum="
                + json.dumps(
                    enum_values,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                if enum_values is not None
                else ""
            )
            description = property_schema.get("description", "")
            if not isinstance(description, str):
                raise ValueError(
                    f"Skald wire property {object_name}.{property_name} "
                    "has a non-string description"
                )
            description_text = json.dumps(description, ensure_ascii=False)
            lines.append(
                f"{property_name}{status}:{field_type}{enum_text}|{description_text}"
            )

            for ref_name in _prompt_guide_object_refs(
                property_schema,
                definitions,
            ):
                if ref_name not in queued_names:
                    object_queue.append((ref_name, definitions[ref_name]))
                    queued_names.add(ref_name)
        lines.append("}")

    lines.append("```")
    return "\n".join(lines)

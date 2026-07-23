"""Sparse semantic-delta wire contract for extended Skald turns.

Presence is a character concept and setting is a place concept. Factions are
per-chunk mentions, never members of the carried scene roster.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

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

    kind: Literal["character"] = Field(description="Character update.")
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

    kind: Literal["place"] = Field(description="Place update.")
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

    kind: Literal["faction"] = Field(description="Faction update.")
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

    kind: Literal["relationship"] = Field(description="Relationship update.")
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


UpdateDelta = Annotated[
    Union[
        CharacterUpdateDelta,
        PlaceUpdateDelta,
        FactionUpdateDelta,
        RelationshipUpdateDelta,
    ],
    Field(discriminator="kind"),
]


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
    updates: List[UpdateDelta] = Field(
        default_factory=list,
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


def _hydrate_updates(updates: List[UpdateDelta]) -> StateUpdates:
    """Map semantic update arms to canonical nested state lists."""

    characters: List[CharacterStateUpdate] = []
    locations: List[LocationStateUpdate] = []
    factions: List[FactionStateUpdate] = []
    relationships: List[RelationshipUpdate] = []

    for update in updates:
        if isinstance(update, CharacterUpdateDelta):
            characters.append(
                CharacterStateUpdate(
                    character_id=update.id,
                    character_name=update.name,
                    current_location=update.location,
                    current_activity=update.activity,
                    emotional_state=update.emotional_state,
                    extra_observations=update.observations or [],
                    orrery_tags=_hydrate_tags(
                        update.tags_add,
                        update.tags_clear,
                    ),
                )
            )
        elif isinstance(update, PlaceUpdateDelta):
            locations.append(
                LocationStateUpdate(
                    place_id=update.id,
                    place_name=update.name,
                    current_conditions=update.condition,
                    notable_changes=(
                        [update.notable_change]
                        if update.notable_change is not None
                        else []
                    ),
                    orrery_tags=_hydrate_tags(
                        update.tags_add,
                        update.tags_clear,
                    ),
                )
            )
        elif isinstance(update, FactionUpdateDelta):
            factions.append(
                FactionStateUpdate(
                    faction_id=update.id,
                    faction_name=update.name,
                    recent_actions=[update.action] if update.action is not None else [],
                    stance_changes=(
                        [
                            FactionStanceChange(
                                target=update.stance_toward,
                                stance=update.stance,
                            )
                        ]
                        if update.stance_toward is not None
                        and update.stance is not None
                        else []
                    ),
                    orrery_tags=_hydrate_tags(
                        update.tags_add,
                        update.tags_clear,
                    ),
                )
            )
        else:
            relationships.append(
                RelationshipUpdate(
                    character1_id=update.id,
                    character1_name=update.name,
                    character2_id=update.other_id,
                    character2_name=update.other_name,
                    relationship_type=update.type,
                    emotional_valence=update.valence,
                    dynamic=update.dynamic,
                    recent_events=update.recent_events,
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

    return SkaldTurnWire.model_json_schema()

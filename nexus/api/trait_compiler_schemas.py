"""Schemas for compiling new-story traits into Orrery substrate facts."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from nexus.agents.orrery.substrate import ContactKind


ResourceLevel = Literal["destitute", "poor", "comfortable", "wealthy", "magnate"]
FameLevel = Literal["obscure", "known", "renowned", "legendary"]
PairTagDirection = Literal["protagonist_to_target", "target_to_protagonist"]


def canonical_trait_name(trait_name: str) -> str:
    """Return the canonical storage name for accepted trait aliases."""

    if trait_name == "reputation":
        return "fame"
    return trait_name


class TraitCompileReasonCode(str, Enum):
    """Reason a selected trait did not produce mechanical writes."""

    MISSING_STRUCTURED_TRAIT_INPUT = "missing_structured_trait_input"
    AMBIGUOUS_TARGET = "ambiguous_target"
    UNKNOWN_SCOPE_FACTION = "unknown_scope_faction"
    UNKNOWN_STATUS_LEVEL = "unknown_status_level"
    UNSUPPORTED_WILDCARD_DECOMPOSITION = "unsupported_wildcard_decomposition"
    REGISTRY_MISSING_TAG = "registry_missing_tag"
    REGISTRY_MISSING_PAIR_TAG = "registry_missing_pair_tag"


class SingleEntityTraitInput(BaseModel):
    """Typed input for a single-entity trait level."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    level: str = Field(..., description="Closed-vocabulary level anchor.")


class StatusTraitInput(BaseModel):
    """Typed input for scope-bound status compilation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    level: str = Field(..., description="Closed status level, e.g. senior.")
    scope_faction_entity_id: Optional[int] = Field(
        None, description="Existing faction entity_id for the status scope."
    )
    scope_faction_name: Optional[str] = Field(
        None, description="Existing faction name if entity_id is not known."
    )


class RelationshipTargetInput(BaseModel):
    """Typed input for one trait-declared character relationship."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    character_id: Optional[int] = Field(
        None, description="Existing target character row id."
    )
    character_entity_id: Optional[int] = Field(
        None, description="Existing target character entity_id."
    )
    name: Optional[str] = Field(None, description="Human-readable target name.")
    relationship_type: Optional[str] = Field(
        None, description="character_relationships.relationship_type override."
    )
    emotional_valence: Optional[str] = Field(
        None, description="character_relationships.emotional_valence override."
    )
    dynamic: str = Field(
        "",
        description="Current relationship state written to character_relationships.",
    )
    recent_events: str = Field(
        "",
        description="Recent events summary written to character_relationships.",
    )
    history: str = Field(
        "",
        description="History summary written to character_relationships.",
    )
    apply_pair_tag: bool = Field(
        False,
        description="Whether this relationship also needs a binary pair-tag gate.",
    )
    pair_tag: Optional[str] = Field(
        None, description="Pair-tag to apply when apply_pair_tag is true."
    )
    pair_tag_direction: PairTagDirection = Field(
        "protagonist_to_target",
        description="Direction for the pair-tag edge when apply_pair_tag is true.",
    )
    contact_kind: Optional[ContactKind] = Field(
        None,
        description=(
            "Kind qualifier for Contacts pair-tags: lodging, social, or intimate."
        ),
    )


class RelationshipTraitInput(BaseModel):
    """Typed input for a relationship-bearing trait."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    targets: List[RelationshipTargetInput] = Field(default_factory=list)


class TraitCompileInputs(BaseModel):
    """Optional typed mechanical inputs collected during the wizard."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    resources: Optional[SingleEntityTraitInput] = None
    fame: Optional[SingleEntityTraitInput] = None
    reputation: Optional[SingleEntityTraitInput] = Field(
        default=None,
        description="Backward-compatible alias for fame during transition.",
    )
    status: Optional[StatusTraitInput] = None
    allies: Optional[RelationshipTraitInput] = None
    contacts: Optional[RelationshipTraitInput] = None
    enemies: Optional[RelationshipTraitInput] = None


class AppliedTag(BaseModel):
    """Single-entity tag that was or would be applied."""

    trait: str
    entity_id: int
    tag: str
    category: str
    inserted: Optional[bool] = None
    dry_run: bool = False


class AppliedPairTag(BaseModel):
    """Pair-tag that was or would be applied."""

    trait: str
    subject_entity_id: int
    object_entity_id: int
    tag: str
    inserted: Optional[bool] = None
    dry_run: bool = False


class CreatedEntity(BaseModel):
    """Entity created by trait compilation."""

    trait: str
    entity_kind: str
    entity_id: int
    row_id: Optional[int] = None
    name: Optional[str] = None
    dry_run: bool = False


class CreatedRelationship(BaseModel):
    """character_relationships row that was or would be written."""

    trait: str
    character1_id: int
    character2_id: int
    relationship_type: str
    emotional_valence: str
    pair_tag: Optional[str] = None
    contact_kind: Optional[ContactKind] = None
    dry_run: bool = False


class UnresolvedTrait(BaseModel):
    """Selected trait that remains prose-only for a structured reason."""

    trait: str
    reason_code: TraitCompileReasonCode
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class TraitCompileCounters(BaseModel):
    """Summary counts for logs/UI."""

    applied_single_entity_tags: int = 0
    applied_pair_tags: int = 0
    created_entities: int = 0
    created_relationships: int = 0
    prose_only_remainders: int = 0


class TraitCompileResult(BaseModel):
    """Complete result of compiling selected traits for one character."""

    character_id: int
    character_entity_id: int
    dry_run: bool
    applied_single_entity_tags: List[AppliedTag] = Field(default_factory=list)
    applied_pair_tags: List[AppliedPairTag] = Field(default_factory=list)
    created_entities: List[CreatedEntity] = Field(default_factory=list)
    created_relationships: List[CreatedRelationship] = Field(default_factory=list)
    prose_only_remainders: List[UnresolvedTrait] = Field(default_factory=list)
    counters: TraitCompileCounters = Field(default_factory=TraitCompileCounters)


class TraitRelationshipDrift(BaseModel):
    """Detected drift between pair-tag and character_relationships layers."""

    drift_kind: Literal["missing_relationship", "missing_pair_tag"]
    subject_entity_id: int
    object_entity_id: int
    pair_tag: str
    character1_id: Optional[int] = None
    character2_id: Optional[int] = None

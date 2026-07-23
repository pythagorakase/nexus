"""Universal provider wire contract for extended Skald turns."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from nexus.agents.logon.apex_schema import (
    ChunkMetadataUpdate,
    NewEntityDeclaration,
    Operations,
    OrreryAdjudication,
    ReferencedEntities,
    StateUpdates,
    StorytellerResponseExtended,
)
from nexus.api.native_structured_output import (
    openai_response_text_format,
    strict_json_schema,
)


class SkaldTurnWire(BaseModel):
    """Provider-facing envelope for a non-bootstrap storyteller turn."""

    narrative: str = Field(description="Narrative prose.")
    choices: List[str] = Field(
        min_length=2,
        max_length=4,
        description="Two to four actionable player choices.",
    )
    chunk_metadata: Optional[ChunkMetadataUpdate] = Field(
        default=None,
        description="Chronology and scene metadata, when changed.",
    )
    referenced_entities: Optional[ReferencedEntities] = Field(
        default=None,
        description="Existing entities referenced in the narrative.",
    )
    state_updates: Optional[StateUpdates] = Field(
        default=None,
        description="Durable state changes caused by this turn.",
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


def hydrate_skald_turn(wire: SkaldTurnWire) -> StorytellerResponseExtended:
    """Hydrate one wire turn into the canonical application response.

    Version 1 has no ambiguous cases: absent component sections map to their
    canonical empty models, absent lists stay empty, and provider-owned fields
    remain unset. Each field is mapped explicitly so adding an ambiguous wire
    field requires a deliberate hydration rule rather than silent inference.
    """

    return StorytellerResponseExtended(
        narrative=wire.narrative,
        choices=wire.choices,
        chunk_metadata=(
            wire.chunk_metadata
            if wire.chunk_metadata is not None
            else ChunkMetadataUpdate()
        ),
        referenced_entities=(
            wire.referenced_entities
            if wire.referenced_entities is not None
            else ReferencedEntities()
        ),
        state_updates=(
            wire.state_updates if wire.state_updates is not None else StateUpdates()
        ),
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

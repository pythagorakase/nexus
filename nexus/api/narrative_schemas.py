"""
Pydantic schemas for narrative API request/response models.

These schemas are used by the narrative endpoints for validation and
serialization of API requests and responses.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Literal

from pydantic import BaseModel, Field, field_validator

# Re-export ChoiceSelection from shared module for backward compatibility
from nexus.api.choice_handling import ChoiceSelection


# =============================================================================
# Core Narrative Schemas
# =============================================================================


class ContinueNarrativeRequest(BaseModel):
    """Request to continue narrative from a chunk, or bootstrap a new story"""

    chunk_id: Optional[int] = Field(
        default=None,
        description="Parent chunk ID to continue from. None or 0 for bootstrap (first chunk).",
    )
    user_text: str = Field(default="", description="User's completion text")
    choice: Optional[int] = Field(
        default=None, description="Structured choice number (1-indexed)"
    )
    accept_fate: bool = Field(
        default=False, description="Auto-advance by selecting the first choice"
    )
    slot: Optional[int] = Field(default=None, description="Active save slot")
    model: Optional[str] = Field(
        default=None, description="Override model for this request"
    )

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: Optional[str]) -> Optional[str]:
        """Validate model against available models from nexus.toml."""
        if v is None:
            return v
        from nexus.config import get_available_api_models

        available = get_available_api_models()
        if v not in available:
            raise ValueError(f"Invalid model '{v}'. Available: {', '.join(available)}")
        return v


class ContinueNarrativeResponse(BaseModel):
    """Response from narrative continuation"""

    session_id: str = Field(description="Session ID for tracking this generation")
    status: str = Field(description="Status of the operation")
    message: str = Field(description="Status message")


class RegenerateNarrativeRequest(BaseModel):
    """Request to regenerate the storyteller turn currently in the incubator."""

    slot: Optional[int] = Field(default=None, description="Active save slot")
    note: Optional[str] = Field(
        default=None,
        description=(
            "Optional out-of-character note to the storyteller for this regen — a soft "
            "suggestion, not a directive. Examples: 'darker, plz', 'I want to win the fight "
            "despite my poor choices', 'continuity correction: the artifact was found in "
            "Vienna, not Prague'. Does NOT replace user_text (that's what undo is for); it's "
            "an author's aside that nudges tone, fixes errors, or signals preferences."
        ),
    )


class ApproveNarrativeRequest(BaseModel):
    """Request to approve and commit narrative"""

    session_id: Optional[str] = Field(
        default=None, description="Session ID of the narrative to approve"
    )
    slot: Optional[int] = Field(
        default=None, description="Slot to resolve session from"
    )
    commit: bool = Field(default=True, description="Whether to commit to database")


class NarrativeStatus(BaseModel):
    """Status of a narrative generation session"""

    session_id: str
    status: str  # provisional, approved, committed, error
    chunk_id: Optional[int]
    parent_chunk_id: Optional[int]
    created_at: Optional[datetime]
    error: Optional[str]


class SelectChoiceRequest(BaseModel):
    """Request to record user's choice selection for a chunk"""

    chunk_id: int = Field(description="The narrative chunk ID")
    selection: ChoiceSelection = Field(description="The user's choice selection")
    slot: Optional[int] = Field(default=None, description="Active save slot")


class SelectChoiceResponse(BaseModel):
    """Response after recording choice selection"""

    status: str = Field(description="Status of the operation")
    chunk_id: int = Field(description="The updated chunk ID")
    raw_text: str = Field(description="The finalized raw_text for embeddings")


# =============================================================================
# Setup/New Story Request Schemas
# =============================================================================


class StartSetupRequest(BaseModel):
    slot: int
    model: Optional[str] = None


class RecordDraftRequest(BaseModel):
    slot: int
    setting: Optional[Dict] = None
    character: Optional[Dict] = None
    seed: Optional[Dict] = None
    location: Optional[Dict] = None
    base_timestamp: Optional[str] = None


class ResetSetupRequest(BaseModel):
    slot: int


class SelectSlotRequest(BaseModel):
    slot: int


# =============================================================================
# Slot State Schemas
# =============================================================================


class TraitMenuItemResponse(BaseModel):
    """A trait in the selection menu."""

    id: int
    name: str
    description: List[str]
    is_selected: bool
    rationale: Optional[str] = None


class SlotStateResponse(BaseModel):
    """Response model for slot state endpoint."""

    slot: int
    is_empty: bool
    is_wizard_mode: bool
    phase: Optional[str] = None  # Wizard phase if in wizard mode
    subphase: Optional[str] = None  # Character subphase (concept/traits/wildcard)
    thread_id: Optional[str] = None  # Wizard thread ID
    current_chunk_id: Optional[int] = None  # Narrative chunk ID
    has_pending: bool = False  # True if incubator has pending content
    storyteller_text: Optional[str] = None
    choices: List[str] = []
    session_id: Optional[str] = None  # Live session ID while incubator pending; basis for regenerate
    model: Optional[str] = None
    # Trait selection menu (character phase, traits subphase)
    trait_menu: Optional[List[TraitMenuItemResponse]] = None
    can_confirm: bool = False  # True when exactly 3 traits selected


# =============================================================================
# Slot Continue Schemas (Deprecated)
# =============================================================================


class SlotContinueRequest(BaseModel):
    """Request model for unified continue endpoint."""

    choice: Optional[int] = Field(
        default=None, description="Structured choice number (1-indexed)"
    )
    user_text: Optional[str] = Field(default=None, description="Freeform user input")
    accept_fate: bool = Field(
        default=False,
        description="Auto-advance (select first choice or trigger auto-generate)",
    )
    model: Optional[str] = Field(
        default=None, description="Override model for this request"
    )


class SlotContinueResponse(BaseModel):
    """Response from unified continue endpoint."""

    success: bool
    action: str  # "wizard_chat", "narrative_continue", "initialize"
    session_id: Optional[str] = None
    message: Optional[str] = None  # Assistant response or status
    choices: List[str] = []  # Available choices for next turn
    phase: Optional[str] = None  # Wizard phase if applicable
    chunk_id: Optional[int] = None  # Narrative chunk ID if applicable
    error: Optional[str] = None


# =============================================================================
# Slot Operation Schemas
# =============================================================================


class SlotUndoResponse(BaseModel):
    """Response from undo endpoint."""

    success: bool
    message: str
    previous_state: Optional[str] = None  # "setting", "character", "seed", or chunk ID


class SlotModelRequest(BaseModel):
    """Request model for setting slot model."""

    model: str = Field(
        description="Model to set (a registry ID; see /api/config/models)"
    )


class SlotModelResponse(BaseModel):
    """Response from model endpoints."""

    slot: int
    model: Optional[str]
    available_models: List[str] = []


class SlotLockResponse(BaseModel):
    """Response for slot lock/unlock operations."""

    slot: int
    is_locked: bool
    message: str


# =============================================================================
# Wizard Chat Schemas
# =============================================================================


def _wizard_default_model_factory() -> str:
    """Return the resolved wizard default model from nexus.toml.

    Used as the field default when an HTTP client doesn't specify a model.
    Reading at request time keeps the value in sync with config edits.
    """
    from nexus.config import load_settings

    return load_settings().wizard.default_model


class ChatRequest(BaseModel):
    slot: int
    message: str
    # thread_id and current_phase are optional - resolved from slot state if not provided
    thread_id: Optional[str] = None
    current_phase: Optional[Literal["setting", "character", "seed"]] = None
    # Defaults to the resolved wizard.default_model from nexus.toml
    model: str = Field(default_factory=_wizard_default_model_factory)
    context_data: Optional[Dict[str, Any]] = None  # Accumulated wizard state
    accept_fate: bool = False  # Force tool call without adding user message
    dev: bool = Field(
        default=False,
        description="Allow a freeform response for this turn (no tools/structured output).",
    )
    # Trait selection operations (character phase, traits subphase)
    # 0 = confirm selection, 1-10 = toggle trait by ID
    trait_choice: Optional[int] = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate model against available models from nexus.toml."""
        from nexus.config import get_available_api_models

        available = get_available_api_models()
        if v not in available:
            raise ValueError(f"Invalid model '{v}'. Available: {', '.join(available)}")
        return v


# =============================================================================
# Transition Schemas
# =============================================================================


class TransitionRequest(BaseModel):
    """Request to transition from wizard setup to narrative mode."""

    slot: int = Field(..., ge=1, le=5, description="Save slot number (1-5)")


class TransitionResponse(BaseModel):
    """Response from successful transition."""

    status: str
    character_id: int
    place_id: int
    layer_id: int
    zone_id: int
    message: str

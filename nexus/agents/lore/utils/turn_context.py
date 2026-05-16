"""
Turn Context Management for LORE

Manages the state and context of a single turn cycle.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from nexus.agents.orrery.resolver import OrreryTickProposal


class TurnPhase(Enum):
    """Phases of the turn cycle"""

    USER_INPUT = "user_input"
    WARM_ANALYSIS = "warm_analysis"
    ENTITY_STATE = "entity_state"
    DEEP_QUERIES = "deep_queries"
    ORRERY_RESOLVE = "orrery_resolve"
    PAYLOAD_ASSEMBLY = "payload_assembly"
    APEX_GENERATION = "apex_generation"
    INTEGRATION = "integration"
    IDLE = "idle"


@dataclass
class TurnContext:
    """Context for a single turn cycle"""

    turn_id: str
    user_input: str
    start_time: float
    phase_states: Dict[str, Any] = field(default_factory=dict)
    warm_slice: List[Dict] = field(default_factory=list)
    entity_data: Dict[str, Any] = field(default_factory=dict)
    retrieved_passages: List[Dict] = field(default_factory=list)
    context_payload: Dict[str, Any] = field(default_factory=dict)
    apex_response: Optional[str] = None
    error_log: List[str] = field(default_factory=list)
    token_counts: Dict[str, int] = field(default_factory=dict)
    memory_state: Dict[str, Any] = field(default_factory=dict)
    authorial_directives: List[str] = field(default_factory=list)
    target_chunk_id: Optional[int] = None
    # Soft author's note / suggestion for the storyteller.
    note: Optional[str] = None
    orrery_proposal: Optional["OrreryTickProposal"] = None
    bleed_menu: List[Any] = field(default_factory=list)

"""
Turn Context Management for LORE

Manages the state and context of a single turn cycle.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum


class TurnPhase(Enum):
    """Phases of the turn cycle"""
    USER_INPUT = "user_input"
    WARM_ANALYSIS = "warm_analysis"
    ENTITY_STATE = "entity_state"
    DEEP_QUERIES = "deep_queries"
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

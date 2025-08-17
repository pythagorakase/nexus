"""
Session Store for Two-Pass Context Assembly

Manages persistent state between the Storyteller pass (75% tokens) 
and the User pass (25% tokens). Handles session checkpointing,
restoration, and cross-session learning.
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("nexus.lore.session_store")


@dataclass
class LoreState:
    """LORE's understanding and expectations after Pass 1"""
    understanding: str  # Brief summary of narrative state
    expectations: List[str] = field(default_factory=list)  # Predicted user directions
    context_gaps: List[str] = field(default_factory=list)  # Known missing info
    query_strategies: List[str] = field(default_factory=list)  # Successful strategies


@dataclass
class SessionContext:
    """Complete context from Pass 1 (Storyteller pass)"""
    session_id: str
    turn_number: int
    storyteller_hash: str  # Hash of Storyteller output for validation
    timestamp: str
    
    # Assembled context
    chunk_ids: List[int] = field(default_factory=list)
    included_chunks: List[Dict[str, Any]] = field(default_factory=list)  # Full chunk data
    excluded_chunks: List[Dict[str, Any]] = field(default_factory=list)  # Flagged as excluded
    
    # Entity data
    present_characters: Dict[int, Dict] = field(default_factory=dict)
    mentioned_characters: Dict[int, Dict] = field(default_factory=dict)
    setting_places: Dict[int, Dict] = field(default_factory=dict)
    mentioned_places: Dict[int, Dict] = field(default_factory=dict)
    relationships: List[Dict] = field(default_factory=list)
    
    # Narrative elements
    narrative_threads: List[str] = field(default_factory=list)
    warm_slice_range: Optional[Dict[str, int]] = None  # Start/end chunk IDs
    
    # Token accounting
    token_usage: Dict[str, int] = field(default_factory=dict)
    tokens_reserved_for_user: int = 0  # 25% reserved
    
    # LORE's state
    lore_state: Optional[LoreState] = None
    
    # Follow-up queries executed
    executed_queries: Set[str] = field(default_factory=set)
    follow_up_budget_used: int = 0


class SessionStore:
    """
    Manages persistent storage of context between passes.
    
    Initially JSON-based, designed to migrate to PostgreSQL.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize SessionStore.
        
        Args:
            storage_dir: Directory for storing session files (default: ./sessions)
        """
        self.storage_dir = storage_dir or Path("./sessions")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache of active sessions
        self.active_sessions: Dict[str, SessionContext] = {}
        
        logger.info(f"SessionStore initialized with storage at {self.storage_dir}")
    
    def create_session(
        self,
        session_id: str,
        turn_number: int,
        storyteller_output: str
    ) -> SessionContext:
        """
        Create a new session for Pass 1.
        
        Args:
            session_id: Unique session identifier
            turn_number: Current turn in the narrative
            storyteller_output: The Storyteller's generated text
            
        Returns:
            New SessionContext instance
        """
        # Generate hash of Storyteller output for validation
        storyteller_hash = hashlib.sha256(storyteller_output.encode()).hexdigest()
        
        session = SessionContext(
            session_id=session_id,
            turn_number=turn_number,
            storyteller_hash=storyteller_hash,
            timestamp=datetime.now().isoformat()
        )
        
        # Cache in memory
        self.active_sessions[session_id] = session
        
        logger.info(f"Created session {session_id} for turn {turn_number}")
        return session
    
    def save_session(self, session: SessionContext) -> Path:
        """
        Persist session to disk.
        
        Args:
            session: SessionContext to save
            
        Returns:
            Path to saved session file
        """
        # Create filename with session ID and turn number
        filename = f"session_{session.session_id}_turn_{session.turn_number}.json"
        filepath = self.storage_dir / filename
        
        # Convert to dict for JSON serialization
        session_dict = self._session_to_dict(session)
        
        # Save to JSON
        with open(filepath, 'w') as f:
            json.dump(session_dict, f, indent=2, default=str)
        
        logger.info(f"Saved session to {filepath}")
        return filepath
    
    def load_session(
        self, 
        session_id: str, 
        turn_number: Optional[int] = None
    ) -> Optional[SessionContext]:
        """
        Load session from disk.
        
        Args:
            session_id: Session identifier
            turn_number: Specific turn to load (default: latest)
            
        Returns:
            SessionContext or None if not found
        """
        # Check memory cache first
        if session_id in self.active_sessions and turn_number is None:
            return self.active_sessions[session_id]
        
        # Find session file
        if turn_number is not None:
            filename = f"session_{session_id}_turn_{turn_number}.json"
            filepath = self.storage_dir / filename
        else:
            # Find latest turn for this session
            pattern = f"session_{session_id}_turn_*.json"
            files = list(self.storage_dir.glob(pattern))
            if not files:
                logger.warning(f"No session files found for {session_id}")
                return None
            # Sort by turn number and get latest
            files.sort(key=lambda p: int(p.stem.split('_')[-1]))
            filepath = files[-1]
        
        if not filepath.exists():
            logger.warning(f"Session file not found: {filepath}")
            return None
        
        # Load from JSON
        with open(filepath, 'r') as f:
            session_dict = json.load(f)
        
        # Convert back to SessionContext
        session = self._dict_to_session(session_dict)
        
        # Cache in memory
        self.active_sessions[session_id] = session
        
        logger.info(f"Loaded session from {filepath}")
        return session
    
    def update_with_lore_analysis(
        self,
        session_id: str,
        understanding: str,
        expectations: List[str],
        context_gaps: List[str],
        query_strategies: List[str]
    ):
        """
        Update session with LORE's analysis after Pass 1.
        
        Args:
            session_id: Session to update
            understanding: LORE's narrative understanding
            expectations: Predicted user directions
            context_gaps: Known missing information
            query_strategies: Successful query patterns
        """
        session = self.active_sessions.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found in active sessions")
            return
        
        session.lore_state = LoreState(
            understanding=understanding,
            expectations=expectations,
            context_gaps=context_gaps,
            query_strategies=query_strategies
        )
        
        # Auto-save after updating LORE state
        self.save_session(session)
        
        logger.info(f"Updated session {session_id} with LORE analysis")
    
    def get_token_budget_remaining(self, session_id: str) -> int:
        """
        Get remaining token budget for Pass 2.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Number of tokens available for user pass
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return 0
        
        return session.tokens_reserved_for_user
    
    def checkpoint(self, session_id: str) -> Dict[str, Any]:
        """
        Create a checkpoint of current session state.
        
        Args:
            session_id: Session to checkpoint
            
        Returns:
            Checkpoint data
        """
        session = self.active_sessions.get(session_id)
        if not session:
            logger.error(f"Cannot checkpoint - session {session_id} not found")
            return {}
        
        # Save to disk
        filepath = self.save_session(session)
        
        # Return checkpoint info
        return {
            "session_id": session_id,
            "turn_number": session.turn_number,
            "filepath": str(filepath),
            "timestamp": datetime.now().isoformat(),
            "storyteller_hash": session.storyteller_hash,
            "tokens_used": sum(session.token_usage.values()),
            "tokens_reserved": session.tokens_reserved_for_user
        }
    
    def restore(self, checkpoint: Dict[str, Any]) -> Optional[SessionContext]:
        """
        Restore from a checkpoint.
        
        Args:
            checkpoint: Checkpoint data from checkpoint()
            
        Returns:
            Restored SessionContext or None
        """
        session_id = checkpoint.get("session_id")
        turn_number = checkpoint.get("turn_number")
        
        if not session_id:
            logger.error("Invalid checkpoint - missing session_id")
            return None
        
        # Load from disk
        session = self.load_session(session_id, turn_number)
        
        # Validate storyteller hash if provided
        if session and checkpoint.get("storyteller_hash"):
            if session.storyteller_hash != checkpoint["storyteller_hash"]:
                logger.warning("Storyteller hash mismatch - content may have changed")
        
        return session
    
    def cleanup_old_sessions(self, days: int = 7):
        """
        Remove session files older than specified days.
        
        Args:
            days: Number of days to keep sessions
        """
        cutoff = datetime.now().timestamp() - (days * 86400)
        
        for filepath in self.storage_dir.glob("session_*.json"):
            if filepath.stat().st_mtime < cutoff:
                filepath.unlink()
                logger.info(f"Removed old session file: {filepath}")
    
    def _session_to_dict(self, session: SessionContext) -> Dict:
        """Convert SessionContext to dict for JSON serialization."""
        data = asdict(session)
        
        # Convert sets to lists for JSON
        if 'executed_queries' in data:
            data['executed_queries'] = list(session.executed_queries)
        
        return data
    
    def _dict_to_session(self, data: Dict) -> SessionContext:
        """Convert dict from JSON back to SessionContext."""
        # Convert lists back to sets where needed
        if 'executed_queries' in data:
            data['executed_queries'] = set(data['executed_queries'])
        
        # Handle nested LoreState
        if data.get('lore_state'):
            data['lore_state'] = LoreState(**data['lore_state'])
        
        return SessionContext(**data)
    
    def get_cross_session_patterns(self, limit: int = 10) -> Dict[str, Any]:
        """
        Analyze patterns across multiple sessions for learning.
        
        Args:
            limit: Number of recent sessions to analyze
            
        Returns:
            Dict of learned patterns
        """
        patterns = {
            "common_gaps": {},
            "successful_strategies": {},
            "user_divergence_types": [],
            "token_usage_stats": {
                "mean": 0,
                "max": 0,
                "min": float('inf')
            }
        }
        
        # Load recent sessions
        session_files = sorted(
            self.storage_dir.glob("session_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]
        
        total_tokens = []
        
        for filepath in session_files:
            with open(filepath, 'r') as f:
                session_dict = json.load(f)
            
            # Analyze gaps
            if session_dict.get('lore_state', {}).get('context_gaps'):
                for gap in session_dict['lore_state']['context_gaps']:
                    patterns['common_gaps'][gap] = patterns['common_gaps'].get(gap, 0) + 1
            
            # Analyze strategies
            if session_dict.get('lore_state', {}).get('query_strategies'):
                for strategy in session_dict['lore_state']['query_strategies']:
                    patterns['successful_strategies'][strategy] = \
                        patterns['successful_strategies'].get(strategy, 0) + 1
            
            # Token usage
            if session_dict.get('token_usage'):
                total = sum(session_dict['token_usage'].values())
                total_tokens.append(total)
        
        # Calculate token stats
        if total_tokens:
            patterns['token_usage_stats']['mean'] = sum(total_tokens) / len(total_tokens)
            patterns['token_usage_stats']['max'] = max(total_tokens)
            patterns['token_usage_stats']['min'] = min(total_tokens)
        
        return patterns
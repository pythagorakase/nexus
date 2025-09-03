"""
Memory Adapter for LORE

Provides a unified interface for LORE to use either SessionStore (JSON-based)
or MemoryProvider (Letta-based) for managing context between passes.

This adapter bridges the gap between the existing SessionStore API and the
new MemoryProvider interface, allowing gradual migration.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Any, Union
from pathlib import Path

from nexus.memory.memory_provider import MemoryProvider
from nexus.agents.lore.utils.session_store import SessionStore, SessionContext

logger = logging.getLogger("nexus.lore.memory_adapter")


class MemoryAdapter:
    """
    Adapter that provides a unified interface for memory management.
    
    Can use either SessionStore (legacy JSON) or MemoryProvider (Letta) backend.
    """
    
    def __init__(self, provider: Optional[Union[MemoryProvider, SessionStore]] = None):
        """
        Initialize memory adapter with specified provider.
        
        Args:
            provider: Either a MemoryProvider (Letta) or SessionStore (JSON).
                     If None, defaults to SessionStore for backward compatibility.
        """
        self.provider = provider or SessionStore()
        self.is_memory_provider = isinstance(self.provider, MemoryProvider)
        
        if self.is_memory_provider:
            logger.info("Using MemoryProvider (Letta) for memory management")
        else:
            logger.info("Using SessionStore (JSON) for memory management")
        
        # Track current session for MemoryProvider
        self.current_session_id = None
    
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
            SessionContext or equivalent
        """
        if self.is_memory_provider:
            # Initialize MemoryProvider for this session
            self.provider.initialize(session_id)
            self.current_session_id = session_id
            
            # Generate hash for validation
            storyteller_hash = hashlib.sha256(storyteller_output.encode()).hexdigest()
            
            # Store in core memory
            self.provider.set_core('project_state', json.dumps({
                'session_id': session_id,
                'turn_number': turn_number,
                'storyteller_hash': storyteller_hash,
                'timestamp': datetime.now().isoformat()
            }))
            
            # Create SessionContext for compatibility
            session = SessionContext(
                session_id=session_id,
                turn_number=turn_number,
                storyteller_hash=storyteller_hash,
                timestamp=datetime.now().isoformat()
            )
            
            # Add to recall memory for searchability
            self.provider.recall_append(
                f"Session {session_id} Turn {turn_number} created with Storyteller output",
                metadata={'type': 'session_creation', 'turn': turn_number}
            )
            
            logger.info(f"Created session {session_id} in MemoryProvider")
            return session
        else:
            # Use legacy SessionStore
            return self.provider.create_session(session_id, turn_number, storyteller_output)
    
    def update_pass1_context(
        self,
        session_id: str,
        extracted_info: Dict[str, Any]
    ):
        """
        Update session with Pass 1 extracted information.
        
        Args:
            session_id: Session to update
            extracted_info: Information extracted during Pass 1
        """
        if self.is_memory_provider:
            # Get current project state
            project_state = json.loads(self.provider.get_core('project_state'))
            
            # Add Pass 1 info
            project_state['pass1_context'] = extracted_info
            
            # Update core memory
            self.provider.set_core('project_state', json.dumps(project_state))
            
            # Log significant extractions to recall
            if extracted_info.get('chunk_ids'):
                self.provider.recall_append(
                    f"Pass 1 extracted chunks: {extracted_info['chunk_ids']}",
                    metadata={'type': 'pass1_extraction', 'chunk_count': len(extracted_info['chunk_ids'])}
                )
            
            if extracted_info.get('entity_ids'):
                self.provider.recall_append(
                    f"Pass 1 found entities: {list(extracted_info['entity_ids'].keys())}",
                    metadata={'type': 'pass1_entities'}
                )
        else:
            # Use legacy SessionStore
            session = self.provider.active_sessions.get(session_id)
            if session:
                session.pass1_context.extracted_info = extracted_info
                session.pass1_context.timestamp = datetime.now().isoformat()
    
    def update_lore_analysis(
        self,
        session_id: str,
        understanding: str,
        gaps: list,
        critical_needs: list
    ):
        """
        Update session with LORE's analysis after Pass 1.
        
        Args:
            session_id: Session to update
            understanding: LORE's understanding of the narrative
            gaps: Identified gaps in context
            critical_needs: Critical information needed for Pass 2
        """
        if self.is_memory_provider:
            # Get current project state
            project_state = json.loads(self.provider.get_core('project_state'))
            
            # Add LORE's analysis
            project_state['lore_analysis'] = {
                'understanding': understanding,
                'gaps': gaps,
                'critical_needs': critical_needs,
                'timestamp': datetime.now().isoformat()
            }
            
            # Update core memory
            self.provider.set_core('project_state', json.dumps(project_state))
            
            # Record analysis in recall for future reference
            self.provider.recall_append(
                f"LORE analysis complete. Gaps: {len(gaps)}, Critical needs: {len(critical_needs)}",
                metadata={'type': 'lore_analysis', 'has_gaps': len(gaps) > 0}
            )
        else:
            # Use legacy SessionStore method
            if hasattr(self.provider, 'update_lore_analysis'):
                self.provider.update_lore_analysis(
                    session_id, understanding, gaps, critical_needs
                )
            else:
                # Manual update for older SessionStore
                session = self.provider.active_sessions.get(session_id)
                if session:
                    session.lore_analysis.understanding = understanding
                    session.lore_analysis.gaps = gaps
                    session.lore_analysis.critical_needs = critical_needs
    
    def load_session(
        self, 
        session_id: str, 
        turn_number: Optional[int] = None
    ) -> Optional[SessionContext]:
        """
        Load session from storage.
        
        Args:
            session_id: Session identifier
            turn_number: Specific turn to load (default: latest)
            
        Returns:
            SessionContext or None if not found
        """
        if self.is_memory_provider:
            # Re-initialize provider for this session
            self.provider.initialize(session_id)
            self.current_session_id = session_id
            
            try:
                # Load from core memory
                project_state = json.loads(self.provider.get_core('project_state'))
                
                # Reconstruct SessionContext
                session = SessionContext(
                    session_id=project_state['session_id'],
                    turn_number=project_state['turn_number'],
                    storyteller_hash=project_state.get('storyteller_hash', ''),
                    timestamp=project_state.get('timestamp', '')
                )
                
                # Restore Pass 1 context if available
                if 'pass1_context' in project_state:
                    session.pass1_context.extracted_info = project_state['pass1_context']
                
                # Restore LORE analysis if available
                if 'lore_analysis' in project_state:
                    analysis = project_state['lore_analysis']
                    session.lore_analysis.understanding = analysis.get('understanding', '')
                    session.lore_analysis.gaps = analysis.get('gaps', [])
                    session.lore_analysis.critical_needs = analysis.get('critical_needs', [])
                
                return session
            except Exception as e:
                logger.error(f"Failed to load session {session_id}: {e}")
                return None
        else:
            # Use legacy SessionStore
            return self.provider.load_session(session_id, turn_number)
    
    def save_session(self, session: SessionContext):
        """
        Save current session state.
        
        Args:
            session: SessionContext to save
        """
        if self.is_memory_provider:
            # Already persisted in core memory with each update
            # Just log the save for consistency
            logger.info(f"Session {session.session_id} auto-saved in MemoryProvider")
            
            # Optionally create an archival card for significant sessions
            if session.lore_analysis.critical_needs:
                # This is where LORE might decide to create archival cards
                # But we leave it to LORE to decide what's worth archiving
                pass
        else:
            # Use legacy SessionStore
            return self.provider.save_session(session)
    
    def search_recall(self, query: str, k: int = 5) -> list:
        """
        Search recall memory for relevant entries.
        
        Args:
            query: Search query
            k: Number of results
            
        Returns:
            List of relevant entries
        """
        if self.is_memory_provider:
            return self.provider.recall_search(query, k)
        else:
            # SessionStore doesn't have recall search
            return []
    
    def cleanup(self):
        """Clean up resources."""
        if self.is_memory_provider:
            # MemoryProvider handles its own cleanup
            pass
        else:
            # Clear active sessions from memory
            if hasattr(self.provider, 'active_sessions'):
                self.provider.active_sessions.clear()
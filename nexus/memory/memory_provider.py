"""
Memory Provider Interface for NEXUS

Abstract interface that allows LORE to interact with different memory backends
without being coupled to a specific implementation. This enables swapping between
Letta, custom implementations, or future memory systems without modifying LORE.

Following GPT-5's architecture guidance for LORE/NEXUS integration.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any


class MemoryProvider(ABC):
    """
    Abstract interface for memory operations in NEXUS.
    
    Provides three tiers of memory:
    1. Core Memory - Always in context, limited size (~5k chars total)
    2. Recall Memory - Searchable conversation/decision history
    3. Archival Memory - Long-term storage with pointers (future)
    """
    
    @abstractmethod
    def initialize(self, session_id: str, **kwargs) -> None:
        """
        Initialize memory provider for a new session.
        
        Args:
            session_id: Unique identifier for this session
            **kwargs: Provider-specific configuration
        """
        pass
    
    # Core Memory Operations
    
    @abstractmethod
    def get_core(self, label: str) -> str:
        """
        Retrieve a core memory block by label.
        
        Args:
            label: The label of the memory block (e.g., 'persona', 'human', 'project_state')
            
        Returns:
            The current value of the memory block
            
        Raises:
            KeyError: If the label doesn't exist
        """
        pass
    
    @abstractmethod
    def set_core(self, label: str, value: str) -> None:
        """
        Set the entire value of a core memory block.
        
        Args:
            label: The label of the memory block
            value: The new value to set
            
        Raises:
            ValueError: If value exceeds block size limit
        """
        pass
    
    @abstractmethod
    def append_core(self, label: str, delta: str) -> None:
        """
        Append to a core memory block.
        
        Args:
            label: The label of the memory block
            delta: The text to append
            
        Raises:
            ValueError: If appending would exceed block size limit
        """
        pass
    
    @abstractmethod
    def list_core_blocks(self) -> List[str]:
        """
        List all available core memory block labels.
        
        Returns:
            List of block labels
        """
        pass
    
    @abstractmethod
    def get_core_usage(self) -> Dict[str, Dict[str, int]]:
        """
        Get usage statistics for core memory blocks.
        
        Returns:
            Dict mapping labels to {'current': int, 'limit': int}
        """
        pass
    
    # Recall Memory Operations
    
    @abstractmethod
    def recall_append(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add an entry to recall memory.
        
        Args:
            content: The content to store
            metadata: Optional metadata (timestamps, tags, etc.)
            
        Returns:
            ID of the stored entry
        """
        pass
    
    @abstractmethod
    def recall_search(self, query: str, k: int = 8) -> List[Dict[str, Any]]:
        """
        Search recall memory for relevant entries.
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            List of dictionaries with 'content', 'metadata', 'relevance' keys
        """
        pass
    
    # Archival Memory Operations (Future)
    
    @abstractmethod
    def archival_insert(self, card: Dict[str, Any]) -> str:
        """
        Insert an index card into archival memory.
        
        Args:
            card: Dictionary containing:
                - text: Short description (max 320 chars)
                - kind: Type of card (commitment/identity/world_anchor/etc)
                - source: Source type (narrative_chunks/entities)
                - chunk_id or entity_id: Pointer to source
                - tags: Optional list of tags
                - ttl_days: Time to live in days
                
        Returns:
            ID of the inserted card
            
        Raises:
            ValueError: If card fails validation
        """
        pass
    
    @abstractmethod
    def archival_search(self, query: str, k: int = 8, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search archival memory for relevant cards.
        
        Args:
            query: Search query
            k: Number of results to return
            tags: Optional tag filters
            
        Returns:
            List of card dictionaries
        """
        pass
    
    # Session Management
    
    @abstractmethod
    def save_state(self) -> Dict[str, Any]:
        """
        Save current memory state for persistence.
        
        Returns:
            Serializable dictionary of current state
        """
        pass
    
    @abstractmethod
    def load_state(self, state: Dict[str, Any]) -> None:
        """
        Restore memory state from saved data.
        
        Args:
            state: Previously saved state dictionary
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """
        Clear all memory for current session.
        """
        pass


class MemoryProviderError(Exception):
    """Base exception for memory provider errors."""
    pass


class MemoryLimitExceeded(MemoryProviderError):
    """Raised when a memory operation would exceed size limits."""
    pass


class InvalidMemoryCard(MemoryProviderError):
    """Raised when an archival card fails validation."""
    pass
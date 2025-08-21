"""
Letta Memory Bridge Implementation

Implements the MemoryProvider interface using Letta's in-process client.
Provides Core and Recall memory functionality with optional Archival support.

This bridge allows LORE to use Letta's proven memory patterns while
maintaining clean separation from Letta's agent/tool infrastructure.
"""

import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path

from nexus.memory.memory_provider import (
    MemoryProvider,
    MemoryLimitExceeded,
    InvalidMemoryCard
)

# Import Letta components
try:
    from letta_client import Letta, CreateBlock
    from letta.schemas.block import Block
    from letta.schemas.memory import Memory, BasicBlockMemory
    LETTA_AVAILABLE = True
except ImportError:
    LETTA_AVAILABLE = False
    logging.warning("Letta not available. LettaMemoryBridge will not function.")

logger = logging.getLogger("nexus.memory.letta_bridge")


class LettaMemoryBridge(MemoryProvider):
    """
    Memory provider implementation using Letta's in-process client.
    
    Uses Letta agents as stateful memory containers without utilizing
    their reasoning or tool capabilities. Each session gets one agent
    that persists memory between LORE's two passes.
    """
    
    # Core memory block configuration
    CORE_BLOCKS = {
        'persona': {
            'limit': 1000,
            'initial': "LORE (Lore Operations & Retrieval Engine) - Narrative intelligence system for NEXUS.",
            'read_only': True
        },
        'human': {
            'limit': 1000, 
            'initial': "User preferences and session configuration.",
            'read_only': False
        },
        'project_state': {
            'limit': 3000,
            'initial': "Active narrative state and entity tracking.",
            'read_only': False
        }
    }
    
    def __init__(self, letta_base_url: str = "http://localhost:8283"):
        """
        Initialize Letta memory bridge.
        
        Args:
            letta_base_url: URL of Letta server (if running separately)
                           For in-process mode, this is ignored.
        """
        if not LETTA_AVAILABLE:
            raise ImportError("Letta is not installed. Cannot use LettaMemoryBridge.")
        
        self.client = None
        self.agent = None
        self.agent_id = None
        self.session_id = None
        self.recall_entries = []  # In-memory recall for now
        self.archival_cards = []  # In-memory archival for now
        
        # Initialize Letta client
        try:
            self.client = Letta(base_url=letta_base_url)
            logger.info(f"Connected to Letta at {letta_base_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Letta: {e}")
            raise
    
    def initialize(self, session_id: str, **kwargs) -> None:
        """
        Initialize memory for a new session by creating a Letta agent.
        
        Args:
            session_id: Unique session identifier
            **kwargs: Additional configuration (model, embedding, etc.)
        """
        self.session_id = session_id
        
        # Check if agent already exists
        existing_agents = self.client.agents.list(name=f"lore_session_{session_id}")
        if existing_agents:
            # Load existing agent
            self.agent = existing_agents[0]
            self.agent_id = self.agent.id
            logger.info(f"Loaded existing agent for session {session_id}")
        else:
            # Create new agent with core memory blocks
            memory_blocks = []
            for label, config in self.CORE_BLOCKS.items():
                memory_blocks.append(CreateBlock(
                    label=label,
                    value=config['initial'],
                    limit=config['limit']
                ))
            
            # Create agent (no tools needed, just memory)
            self.agent = self.client.agents.create(
                name=f"lore_session_{session_id}",
                memory_blocks=memory_blocks,
                include_base_tools=False,  # No Letta tools needed
                model=kwargs.get('model', 'openai/gpt-4o-mini'),
                embedding=kwargs.get('embedding', 'openai/text-embedding-3-small')
            )
            self.agent_id = self.agent.id
            logger.info(f"Created new agent for session {session_id}")
    
    # Core Memory Operations
    
    def get_core(self, label: str) -> str:
        """Retrieve a core memory block value."""
        if not self.agent:
            raise RuntimeError("Memory not initialized. Call initialize() first.")
        
        # Get block from agent's memory
        try:
            block = self.agent.memory.get_block(label)
            return block.value
        except KeyError:
            raise KeyError(f"Core memory block '{label}' not found")
    
    def set_core(self, label: str, value: str) -> None:
        """Set the entire value of a core memory block."""
        if not self.agent:
            raise RuntimeError("Memory not initialized. Call initialize() first.")
        
        # Check if block is read-only
        if label in self.CORE_BLOCKS and self.CORE_BLOCKS[label].get('read_only'):
            raise ValueError(f"Core memory block '{label}' is read-only")
        
        # Check size limit
        limit = self.CORE_BLOCKS.get(label, {}).get('limit', 5000)
        if len(value) > limit:
            raise MemoryLimitExceeded(f"Value exceeds limit of {limit} chars for block '{label}'")
        
        # Update block
        try:
            # Update local agent state
            self.agent.memory.update_block_value(label, value)
            
            # Persist to Letta server
            self.client.agents.blocks.update(
                agent_id=self.agent_id,
                block_id=label,
                value=value
            )
            logger.debug(f"Updated core block '{label}' with {len(value)} chars")
        except Exception as e:
            logger.error(f"Failed to update core block '{label}': {e}")
            raise
    
    def append_core(self, label: str, delta: str) -> None:
        """Append to a core memory block."""
        if not self.agent:
            raise RuntimeError("Memory not initialized. Call initialize() first.")
        
        # Check if block is read-only
        if label in self.CORE_BLOCKS and self.CORE_BLOCKS[label].get('read_only'):
            raise ValueError(f"Core memory block '{label}' is read-only")
        
        # Get current value
        try:
            block = next(b for b in self.agent.memory.blocks if b.label == label)
            current = block.value
        except StopIteration:
            raise KeyError(f"Core memory block '{label}' not found")
        
        new_value = current + "\n" + delta if current else delta
        
        # Check size limit
        limit = self.CORE_BLOCKS.get(label, {}).get('limit', 5000)
        if len(new_value) > limit:
            raise MemoryLimitExceeded(f"Value exceeds limit of {limit} chars for block '{label}'")
        
        # Update directly on the block object to maintain consistency
        block.value = new_value
        
        # Persist to Letta server if connected
        if self.client:
            try:
                self.client.agents.blocks.update(
                    agent_id=self.agent_id,
                    block_id=label,
                    value=new_value
                )
            except Exception as e:
                logger.error(f"Failed to persist block update: {e}")
    
    def list_core_blocks(self) -> List[str]:
        """List all core memory block labels."""
        if not self.agent:
            return list(self.CORE_BLOCKS.keys())
        return [block.label for block in self.agent.memory.blocks]
    
    def get_core_usage(self) -> Dict[str, Dict[str, int]]:
        """Get usage statistics for core memory blocks."""
        if not self.agent:
            raise RuntimeError("Memory not initialized. Call initialize() first.")
        
        usage = {}
        for block in self.agent.memory.blocks:
            usage[block.label] = {
                'current': len(block.value),
                'limit': block.limit
            }
        return usage
    
    # Recall Memory Operations
    
    def recall_append(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add entry to recall memory."""
        entry_id = f"recall_{self.session_id}_{len(self.recall_entries)}"
        entry = {
            'id': entry_id,
            'content': content,
            'metadata': metadata or {},
            'timestamp': datetime.now().isoformat()
        }
        self.recall_entries.append(entry)
        logger.debug(f"Added recall entry {entry_id}")
        return entry_id
    
    def recall_search(self, query: str, k: int = 8) -> List[Dict[str, Any]]:
        """
        Search recall memory.
        
        For now, this is a simple text search. In production, this would
        use Letta's conversation_search or a vector database.
        """
        results = []
        query_lower = query.lower()
        
        for entry in self.recall_entries:
            if query_lower in entry['content'].lower():
                results.append({
                    'content': entry['content'],
                    'metadata': entry['metadata'],
                    'relevance': 1.0  # Simple binary relevance for now
                })
        
        # Return top k results
        return results[:k]
    
    # Archival Memory Operations
    
    def archival_insert(self, card: Dict[str, Any]) -> str:
        """Insert an index card into archival memory."""
        # Validate card
        self._validate_archival_card(card)
        
        card_id = f"arch_{self.session_id}_{len(self.archival_cards)}"
        card['id'] = card_id
        card['created_at'] = datetime.now().isoformat()
        
        self.archival_cards.append(card)
        logger.debug(f"Added archival card {card_id}: {card.get('text', '')[:50]}...")
        return card_id
    
    def archival_search(self, query: str, k: int = 8, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search archival memory for relevant cards.
        
        For now, this is a simple text/tag search. In production,
        this would use vector similarity.
        """
        results = []
        query_lower = query.lower()
        
        for card in self.archival_cards:
            # Check text match
            text_match = query_lower in card.get('text', '').lower()
            
            # Check tag match
            tag_match = False
            if tags:
                card_tags = card.get('tags', [])
                tag_match = any(tag in card_tags for tag in tags)
            
            if text_match or (tags and tag_match):
                results.append(card)
        
        # Return top k results
        return results[:k]
    
    def _validate_archival_card(self, card: Dict[str, Any]) -> None:
        """Validate an archival card against GPT-5's rules."""
        # Check required fields
        if 'text' not in card:
            raise InvalidMemoryCard("Card missing required 'text' field")
        
        # Check text length (max 320 chars)
        if len(card['text']) > 320:
            raise InvalidMemoryCard(f"Card text exceeds 320 char limit: {len(card['text'])}")
        
        # Check for source pointer
        if 'source' not in card:
            raise InvalidMemoryCard("Card missing required 'source' field")
        
        if card['source'] == 'narrative_chunks' and 'chunk_id' not in card:
            raise InvalidMemoryCard("Card with source 'narrative_chunks' missing 'chunk_id'")
        
        if card['source'] == 'entities' and 'entity_id' not in card:
            raise InvalidMemoryCard("Card with source 'entities' missing 'entity_id'")
        
        # Check kind
        valid_kinds = {'commitment', 'identity', 'world_anchor', 'canon_link', 'unresolved_question'}
        if 'kind' in card and card['kind'] not in valid_kinds:
            raise InvalidMemoryCard(f"Invalid card kind: {card['kind']}")
        
        # Check for raw narrative (simple heuristic: >25 consecutive words)
        if self._looks_like_raw_narrative(card['text']):
            raise InvalidMemoryCard("Card appears to contain raw narrative text")
    
    def _looks_like_raw_narrative(self, text: str, max_run: int = 25) -> bool:
        """Check if text looks like raw pasted narrative."""
        words = text.split()
        if len(words) > max_run:
            # If more than max_run words and looks like prose (has punctuation)
            if any(char in text for char in ['.', ',', '!', '?', ';']):
                return True
        return False
    
    # Session Management
    
    def save_state(self) -> Dict[str, Any]:
        """Save current memory state."""
        if not self.agent:
            raise RuntimeError("Memory not initialized. Call initialize() first.")
        
        # Get current core memory values
        core_state = {}
        for block in self.agent.memory.blocks:
            core_state[block.label] = block.value
        
        return {
            'session_id': self.session_id,
            'agent_id': self.agent_id,
            'core_memory': core_state,
            'recall_entries': self.recall_entries,
            'archival_cards': self.archival_cards
        }
    
    def load_state(self, state: Dict[str, Any]) -> None:
        """Restore memory state from saved data."""
        self.session_id = state.get('session_id')
        self.agent_id = state.get('agent_id')
        
        # Load agent if we have an ID
        if self.agent_id and self.client:
            try:
                self.agent = self.client.agents.retrieve(self.agent_id)
                
                # Restore core memory values (skip read-only blocks)
                if 'core_memory' in state:
                    for label, value in state['core_memory'].items():
                        # Skip read-only blocks when loading
                        if label in self.CORE_BLOCKS and self.CORE_BLOCKS[label].get('read_only'):
                            continue
                        self.set_core(label, value)
                
                logger.info(f"Loaded state for session {self.session_id}")
            except Exception as e:
                logger.error(f"Failed to load agent {self.agent_id}: {e}")
                raise
        
        # Restore recall and archival
        self.recall_entries = state.get('recall_entries', [])
        self.archival_cards = state.get('archival_cards', [])
    
    def clear(self) -> None:
        """Clear all memory for current session."""
        # Reset core memory to initial values
        for label, config in self.CORE_BLOCKS.items():
            if not config.get('read_only'):
                self.set_core(label, config['initial'])
        
        # Clear recall and archival
        self.recall_entries = []
        self.archival_cards = []
        
        logger.info(f"Cleared memory for session {self.session_id}")
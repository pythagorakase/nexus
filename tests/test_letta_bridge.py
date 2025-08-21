"""
Test suite for LettaMemoryBridge implementation.

Tests the integration between NEXUS and Letta's memory system.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch

# Mock the Letta imports if not available
try:
    from nexus.memory.letta_bridge import LettaMemoryBridge, LETTA_AVAILABLE
except ImportError:
    LETTA_AVAILABLE = False
    LettaMemoryBridge = None

from nexus.memory.memory_provider import (
    MemoryLimitExceeded,
    InvalidMemoryCard
)


@pytest.mark.skipif(not LETTA_AVAILABLE, reason="Letta not available")
class TestLettaMemoryBridge:
    """Test suite for LettaMemoryBridge."""
    
    @pytest.fixture
    def mock_letta_client(self):
        """Create a mock Letta client."""
        with patch('nexus.memory.letta_bridge.Letta') as mock_letta:
            # Setup mock client
            mock_client = Mock()
            mock_letta.return_value = mock_client
            
            # Setup mock agent
            mock_agent = Mock()
            mock_agent.id = "test_agent_id"
            mock_agent.name = "lore_session_test123"
            
            # Setup mock memory with blocks
            mock_memory = Mock()
            mock_blocks = []
            
            for label, config in LettaMemoryBridge.CORE_BLOCKS.items():
                mock_block = Mock()
                mock_block.label = label
                mock_block.value = config['initial']
                mock_block.limit = config['limit']
                mock_blocks.append(mock_block)
            
            mock_memory.blocks = mock_blocks
            mock_memory.get_block = lambda l: next((b for b in mock_blocks if b.label == l), None)
            mock_memory.update_block_value = Mock()
            
            mock_agent.memory = mock_memory
            
            # Setup client methods
            mock_client.agents.list.return_value = []
            mock_client.agents.create.return_value = mock_agent
            mock_client.agents.retrieve.return_value = mock_agent
            mock_client.agents.blocks.update = Mock()
            
            yield mock_client, mock_agent
    
    def test_initialization(self, mock_letta_client):
        """Test LettaMemoryBridge initialization."""
        mock_client, mock_agent = mock_letta_client
        
        bridge = LettaMemoryBridge()
        assert bridge.client is not None
        
        # Initialize session
        bridge.initialize("test123")
        assert bridge.session_id == "test123"
        assert bridge.agent_id == "test_agent_id"
        
        # Verify agent was created with correct configuration
        mock_client.agents.create.assert_called_once()
        call_args = mock_client.agents.create.call_args
        assert call_args.kwargs['name'] == "lore_session_test123"
        assert call_args.kwargs['include_base_tools'] is False
    
    def test_core_memory_operations(self, mock_letta_client):
        """Test core memory get/set/append operations."""
        mock_client, mock_agent = mock_letta_client
        
        bridge = LettaMemoryBridge()
        bridge.initialize("test123")
        
        # Test get_core
        assert bridge.get_core('persona').startswith("LORE")
        assert bridge.get_core('human').startswith("User preferences")
        
        # Test set_core
        bridge.set_core('project_state', "New narrative state")
        mock_agent.memory.update_block_value.assert_called_with('project_state', "New narrative state")
        
        # Test append_core
        # First, update the mock block to have our new value for get_core to work
        project_block = next(b for b in mock_agent.memory.blocks if b.label == 'project_state')
        project_block.value = "Initial state"
        
        bridge.append_core('project_state', "Additional info")
        # Check that the block's value was updated directly
        assert project_block.value == "Initial state\nAdditional info"
        
        # Test read-only protection
        with pytest.raises(ValueError, match="read-only"):
            bridge.set_core('persona', "New persona")
    
    def test_memory_limits(self, mock_letta_client):
        """Test memory size limit enforcement."""
        mock_client, mock_agent = mock_letta_client
        
        bridge = LettaMemoryBridge()
        bridge.initialize("test123")
        
        # Try to exceed limit
        huge_text = "x" * 5000  # Exceeds 3000 char limit for project_state
        with pytest.raises(MemoryLimitExceeded):
            bridge.set_core('project_state', huge_text)
    
    def test_recall_memory(self, mock_letta_client):
        """Test recall memory append and search."""
        mock_client, mock_agent = mock_letta_client
        
        bridge = LettaMemoryBridge()
        bridge.initialize("test123")
        
        # Add recall entries
        id1 = bridge.recall_append("User requested karaoke scene")
        id2 = bridge.recall_append("Retrieved chunks 741-763")
        id3 = bridge.recall_append("Gap detected in context")
        
        # Search recall
        results = bridge.recall_search("karaoke")
        assert len(results) == 1
        assert results[0]['content'] == "User requested karaoke scene"
        
        results = bridge.recall_search("chunks")
        assert len(results) == 1
        assert results[0]['content'] == "Retrieved chunks 741-763"
    
    def test_archival_card_validation(self, mock_letta_client):
        """Test archival memory card validation."""
        mock_client, mock_agent = mock_letta_client
        
        bridge = LettaMemoryBridge()
        bridge.initialize("test123")
        
        # Valid card
        valid_card = {
            'text': 'Alex promised not to contact Pete',
            'kind': 'commitment',
            'source': 'narrative_chunks',
            'chunk_id': 4821,
            'tags': ['Alex', 'Pete']
        }
        card_id = bridge.archival_insert(valid_card)
        assert card_id.startswith("arch_")
        
        # Card with text too long
        invalid_card = {
            'text': 'x' * 400,  # Exceeds 320 char limit
            'source': 'narrative_chunks',
            'chunk_id': 123
        }
        with pytest.raises(InvalidMemoryCard, match="exceeds 320 char"):
            bridge.archival_insert(invalid_card)
        
        # Card missing source pointer
        invalid_card = {
            'text': 'Some text',
            'source': 'narrative_chunks'
            # Missing chunk_id
        }
        with pytest.raises(InvalidMemoryCard, match="missing 'chunk_id'"):
            bridge.archival_insert(invalid_card)
        
        # Card with invalid kind
        invalid_card = {
            'text': 'Some text',
            'kind': 'invalid_kind',
            'source': 'entities',
            'entity_id': 42
        }
        with pytest.raises(InvalidMemoryCard, match="Invalid card kind"):
            bridge.archival_insert(invalid_card)
    
    def test_raw_narrative_detection(self, mock_letta_client):
        """Test detection of raw narrative text in cards."""
        mock_client, mock_agent = mock_letta_client
        
        bridge = LettaMemoryBridge()
        bridge.initialize("test123")
        
        # Card with raw narrative (too many words with punctuation)
        raw_narrative = (
            "The team sat around the table at Boudreaux's, the warm glow of the "
            "restaurant's amber lights casting long shadows across their faces. Alex "
            "raised his glass, a wry smile playing at the corners of his mouth."
        )
        invalid_card = {
            'text': raw_narrative,
            'source': 'narrative_chunks',
            'chunk_id': 123
        }
        with pytest.raises(InvalidMemoryCard, match="raw narrative"):
            bridge.archival_insert(invalid_card)
        
        # Card with acceptable summary
        valid_card = {
            'text': 'Team dinner at Boudreaux\'s discussing next steps',
            'source': 'narrative_chunks',
            'chunk_id': 123
        }
        card_id = bridge.archival_insert(valid_card)
        assert card_id is not None
    
    def test_state_persistence(self, mock_letta_client):
        """Test saving and loading memory state."""
        mock_client, mock_agent = mock_letta_client
        
        bridge = LettaMemoryBridge()
        bridge.initialize("test123")
        
        # Modify state
        bridge.set_core('project_state', "Modified state")
        bridge.recall_append("Test recall entry")
        bridge.archival_insert({
            'text': 'Test card',
            'source': 'entities',
            'entity_id': 1
        })
        
        # Save state
        state = bridge.save_state()
        assert state['session_id'] == "test123"
        assert state['agent_id'] == "test_agent_id"
        assert len(state['recall_entries']) == 1
        assert len(state['archival_cards']) == 1
        
        # Create new bridge and load state
        bridge2 = LettaMemoryBridge()
        bridge2.load_state(state)
        
        assert bridge2.session_id == "test123"
        assert bridge2.agent_id == "test_agent_id"
        assert len(bridge2.recall_entries) == 1
        assert len(bridge2.archival_cards) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
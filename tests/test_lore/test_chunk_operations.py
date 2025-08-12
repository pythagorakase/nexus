"""
Unit tests for chunk_operations.py

Tests deterministic chunk selection, assembly, and chronological sorting.
"""

import pytest
from pathlib import Path
import sys

# Add nexus module to path
nexus_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(nexus_root))

from nexus.agents.lore.utils.chunk_operations import (
    calculate_chunk_tokens,
    select_warm_slice,
    assemble_chronological_context,
    format_chunk_with_metadata,
    merge_deduplicate_chunks,
    filter_by_world_layer,
    get_chunk_time_range,
    get_apex_model_encoding
)


class TestTokenCalculation:
    """Test token counting functionality."""
    
    def test_calculate_chunk_tokens_basic(self):
        """Test basic token calculation."""
        text = "This is a simple test of token counting."
        token_count = calculate_chunk_tokens(text)
        assert token_count > 0
        assert token_count < 20  # Simple sentence should be under 20 tokens
    
    def test_calculate_chunk_tokens_empty(self):
        """Test empty string token count."""
        assert calculate_chunk_tokens("") == 0
    
    def test_calculate_chunk_tokens_narrative(self, sample_chunks):
        """Test token counting on real narrative text."""
        # Use a dialogue scene
        chunk = sample_chunks.get('dialogue_offer')
        if chunk and 'raw_text' in chunk:
            token_count = calculate_chunk_tokens(chunk['raw_text'])
            assert token_count > 50  # Real narrative should have substantial tokens
            assert token_count < 5000  # Single chunk shouldn't be huge
    
    def test_apex_model_encoding(self):
        """Test that encoding uses correct model from settings."""
        encoding = get_apex_model_encoding()
        assert encoding is not None
        # Should use gpt-4o encoding as fallback/proxy for newer models
        test_text = "Test encoding"
        tokens = encoding.encode(test_text)
        assert len(tokens) > 0


class TestWarmSliceSelection:
    """Test warm slice selection logic."""
    
    def test_select_warm_slice_basic(self):
        """Test basic warm slice selection."""
        all_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        warm = select_warm_slice(all_ids, 3)
        assert warm == [8, 9, 10]  # Most recent 3
    
    def test_select_warm_slice_exceed_available(self):
        """Test when requesting more chunks than available."""
        all_ids = [1, 2, 3]
        warm = select_warm_slice(all_ids, 10)
        assert warm == [1, 2, 3]  # Return all available
    
    def test_select_warm_slice_empty(self):
        """Test with empty chunk list."""
        assert select_warm_slice([], 5) == []
    
    def test_select_warm_slice_zero_span(self):
        """Test with zero span requested."""
        assert select_warm_slice([1, 2, 3], 0) == []
    
    def test_select_warm_slice_unsorted(self):
        """Test with unsorted input IDs."""
        all_ids = [5, 1, 9, 3, 7, 2]
        warm = select_warm_slice(all_ids, 2)
        assert warm == [7, 9]  # Should sort and take highest


class TestChronologicalAssembly:
    """Test chronological context assembly."""
    
    def test_assemble_chronological_basic(self):
        """Test basic chronological assembly."""
        warm_chunks = [
            {'id': 5, 'text': 'chunk5'},
            {'id': 10, 'text': 'chunk10'}
        ]
        augment_chunks = [
            {'id': 3, 'text': 'chunk3'},
            {'id': 7, 'text': 'chunk7'}
        ]
        
        result = assemble_chronological_context(warm_chunks, augment_chunks)
        
        # Should be sorted by ID
        assert [c['id'] for c in result] == [3, 5, 7, 10]
        
        # Should have source tags
        assert result[0]['source'] == 'augmentation'  # id=3
        assert result[1]['source'] == 'warm_slice'     # id=5
        assert result[2]['source'] == 'augmentation'   # id=7
        assert result[3]['source'] == 'warm_slice'     # id=10
    
    def test_assemble_chronological_duplicates(self):
        """Test deduplication during assembly."""
        warm_chunks = [
            {'id': 5, 'text': 'chunk5'},
            {'id': 10, 'text': 'chunk10'}
        ]
        augment_chunks = [
            {'id': 5, 'text': 'chunk5_dup'},  # Duplicate ID
            {'id': 7, 'text': 'chunk7'}
        ]
        
        result = assemble_chronological_context(warm_chunks, augment_chunks)
        
        # Should deduplicate, keeping warm slice version
        assert [c['id'] for c in result] == [5, 7, 10]
        assert result[0]['text'] == 'chunk5'  # Not chunk5_dup
    
    def test_assemble_chronological_empty(self):
        """Test with empty chunk lists."""
        assert assemble_chronological_context([], []) == []
        
        # Only warm chunks
        warm = [{'id': 1, 'text': 'test'}]
        result = assemble_chronological_context(warm, [])
        assert len(result) == 1
        assert result[0]['source'] == 'warm_slice'


class TestChunkFormatting:
    """Test chunk formatting with metadata."""
    
    def test_format_chunk_basic(self):
        """Test basic chunk formatting."""
        chunk = {
            'season': 1,
            'episode': 2,
            'scene': 3,
            'raw_text': 'This is the narrative text.'
        }
        
        formatted = format_chunk_with_metadata(chunk)
        assert formatted.startswith('[S01E02 Scene 3]')
        assert 'This is the narrative text.' in formatted
    
    def test_format_chunk_with_world_time(self):
        """Test formatting with world time."""
        chunk = {
            'season': 2,
            'episode': 4,
            'world_time': '2073-10-13 17:30:00',
            'raw_text': 'Test text'
        }
        
        formatted = format_chunk_with_metadata(chunk, include_world_time=True)
        assert '2073-10-13 17:30:00' in formatted
    
    def test_format_chunk_non_primary_layer(self):
        """Test formatting for non-primary world layers."""
        chunk = {
            'world_layer': 'flashback',
            'raw_text': 'Flashback scene'
        }
        
        formatted = format_chunk_with_metadata(chunk, include_world_time=False)
        assert '[FLASHBACK]' in formatted
    
    def test_format_chunk_minimal(self):
        """Test formatting with minimal metadata."""
        chunk = {'text': 'Just text'}
        formatted = format_chunk_with_metadata(chunk)
        assert formatted == 'Just text'


class TestChunkMerging:
    """Test chunk merging and deduplication."""
    
    def test_merge_deduplicate_basic(self):
        """Test basic merge and deduplication."""
        chunks1 = [
            {'id': 1, 'text': 'chunk1'},
            {'id': 3, 'text': 'chunk3'}
        ]
        chunks2 = [
            {'id': 2, 'text': 'chunk2'},
            {'id': 3, 'text': 'chunk3_dup'}  # Duplicate
        ]
        
        result = merge_deduplicate_chunks(chunks1, chunks2)
        
        # Should have 3 unique chunks
        assert len(result) == 3
        ids = [c['id'] for c in result]
        assert sorted(ids) == [1, 2, 3]
        
        # First occurrence wins
        chunk3 = next(c for c in result if c['id'] == 3)
        assert chunk3['text'] == 'chunk3'  # Not chunk3_dup
    
    def test_merge_deduplicate_empty(self):
        """Test merging empty lists."""
        assert merge_deduplicate_chunks([], []) == []
        
        chunks = [{'id': 1, 'text': 'test'}]
        assert merge_deduplicate_chunks(chunks, []) == chunks
        assert merge_deduplicate_chunks([], chunks) == chunks


class TestWorldLayerFiltering:
    """Test filtering by world layer."""
    
    def test_filter_world_layer_default(self):
        """Test default filtering (primary only)."""
        chunks = [
            {'id': 1, 'world_layer': 'primary'},
            {'id': 2, 'world_layer': 'flashback'},
            {'id': 3, 'world_layer': 'primary'},
            {'id': 4, 'world_layer': 'dream'}
        ]
        
        filtered = filter_by_world_layer(chunks)
        assert len(filtered) == 2
        assert all(c['world_layer'] == 'primary' for c in filtered)
    
    def test_filter_world_layer_multiple(self):
        """Test filtering with multiple allowed layers."""
        chunks = [
            {'id': 1, 'world_layer': 'primary'},
            {'id': 2, 'world_layer': 'flashback'},
            {'id': 3, 'world_layer': 'dream'},
            {'id': 4, 'world_layer': 'extradiegetic'}
        ]
        
        filtered = filter_by_world_layer(chunks, ['primary', 'flashback'])
        assert len(filtered) == 2
        assert filtered[0]['id'] == 1
        assert filtered[1]['id'] == 2
    
    def test_filter_world_layer_missing_field(self):
        """Test filtering when world_layer field is missing."""
        chunks = [
            {'id': 1, 'world_layer': 'flashback'},
            {'id': 2},  # Missing world_layer
            {'id': 3, 'world_layer': 'primary'}
        ]
        
        # Missing world_layer defaults to 'primary'
        filtered = filter_by_world_layer(chunks)
        assert len(filtered) == 2
        assert 2 in [c['id'] for c in filtered]
        assert 3 in [c['id'] for c in filtered]


class TestTimeRange:
    """Test time range calculation."""
    
    def test_get_chunk_time_range_basic(self):
        """Test basic time range calculation."""
        chunks = [
            {'world_layer': 'primary', 'world_time': '2073-10-13 16:00:00'},
            {'world_layer': 'primary', 'world_time': '2073-10-13 17:30:00'},
            {'world_layer': 'primary', 'world_time': '2073-10-13 16:45:00'}
        ]
        
        time_range = get_chunk_time_range(chunks)
        assert time_range['start_time'] == '2073-10-13 16:00:00'
        assert time_range['end_time'] == '2073-10-13 17:30:00'
    
    def test_get_chunk_time_range_non_primary(self):
        """Test that non-primary layers are excluded."""
        chunks = [
            {'world_layer': 'primary', 'world_time': '2073-10-13 16:00:00'},
            {'world_layer': 'flashback', 'world_time': '2070-01-01 12:00:00'},
            {'world_layer': 'primary', 'world_time': '2073-10-13 17:00:00'}
        ]
        
        time_range = get_chunk_time_range(chunks)
        # Should ignore flashback
        assert time_range['start_time'] == '2073-10-13 16:00:00'
        assert time_range['end_time'] == '2073-10-13 17:00:00'
    
    def test_get_chunk_time_range_empty(self):
        """Test with no valid time data."""
        chunks = [
            {'world_layer': 'flashback'},
            {'world_layer': 'primary'}  # No world_time
        ]
        
        time_range = get_chunk_time_range(chunks)
        assert time_range['start_time'] is None
        assert time_range['end_time'] is None
        assert time_range['duration'] is None
"""
Unit tests for context_validation.py

Tests validation of context payloads against percentage-based constraints.
"""

import pytest
from pathlib import Path
import sys

# Add nexus module to path
nexus_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(nexus_root))

from nexus.agents.lore.utils.context_validation import (
    validate_context,
    validate_token_allocation,
    check_utilization,
    validate_phase_completion
)


class TestContextValidation:
    """Test context payload validation."""
    
    def test_validate_context_complete(self, settings):
        """Test validation of a complete, valid context."""
        context = {
            'user_input': 'Test input',
            'narrative_context': {
                'warm_slice': [{'id': 1, 'text': 'chunk1'}]
            },
            'metadata': {
                'token_counts': {
                    'warm_slice': 10000,      # 50% of 20k
                    'structured': 3000,        # 15% of 20k
                    'augmentation': 6000,      # 30% of 20k
                    'user_input': 1000         # 5% of 20k
                }
            }
        }
        
        is_valid, errors = validate_context(context, settings)
        assert is_valid
        assert len(errors) == 0
    
    def test_validate_context_missing_fields(self, settings):
        """Test validation catches missing required fields."""
        context = {
            # Missing user_input
            'narrative_context': {
                'warm_slice': []
            }
        }
        
        is_valid, errors = validate_context(context, settings)
        assert not is_valid
        assert 'Missing user_input' in errors
    
    def test_validate_context_empty_warm_slice(self, settings):
        """Test validation catches empty warm slice."""
        context = {
            'user_input': 'Test',
            'narrative_context': {
                'warm_slice': []  # Empty
            }
        }
        
        is_valid, errors = validate_context(context, settings)
        assert not is_valid
        assert any('warm_slice' in e for e in errors)
    
    def test_validate_context_token_limit_exceeded(self, settings):
        """Test validation catches token limit violations."""
        context = {
            'user_input': 'Test',
            'narrative_context': {
                'warm_slice': [{'id': 1}]
            },
            'metadata': {
                'token_counts': {
                    'warm_slice': 100000,
                    'structured': 50000,
                    'augmentation': 60000
                }
            }
        }
        
        is_valid, errors = validate_context(context, settings)
        assert not is_valid
        assert any('Token limit exceeded' in e for e in errors)
    
    def test_validate_context_percentage_violations(self, settings):
        """Test validation catches percentage constraint violations."""
        context = {
            'user_input': 'Test',
            'narrative_context': {
                'warm_slice': [{'id': 1}]
            },
            'metadata': {
                'token_counts': {
                    'warm_slice': 2000,       # 10% - below 40% minimum
                    'structured': 8000,        # 40% - above 25% maximum  
                    'augmentation': 10000      # 50% - above 40% maximum
                }
            }
        }
        
        is_valid, errors = validate_context(context, settings)
        assert not is_valid
        # Should have errors for all three components
        assert any('Warm slice below minimum' in e for e in errors)
        assert any('Structured data above maximum' in e for e in errors)
        assert any('Augmentation above maximum' in e for e in errors)


class TestTokenAllocation:
    """Test token allocation validation."""
    
    def test_validate_allocation_valid(self, settings):
        """Test validation of valid token allocations."""
        allocations = {
            'warm_slice': 10000,           # 50% of 20k
            'structured_data': 3000,        # 15% of 20k
            'contextual_augmentation': 6000 # 30% of 20k
        }
        
        is_valid, errors = validate_token_allocation(allocations, 20000, settings)
        assert is_valid
        assert len(errors) == 0
    
    def test_validate_allocation_exceeds_budget(self, settings):
        """Test validation catches over-budget allocations."""
        allocations = {
            'warm_slice': 10000,
            'structured_data': 5000,
            'contextual_augmentation': 8000  # Total = 23k > 20k budget
        }
        
        is_valid, errors = validate_token_allocation(allocations, 20000, settings)
        assert not is_valid
        assert any('exceeds budget' in e for e in errors)
    
    def test_validate_allocation_warm_slice_bounds(self, settings):
        """Test warm slice percentage boundaries (40-70%)."""
        # Too low (30%)
        allocations = {
            'warm_slice': 6000,  # 30% of 20k
            'structured_data': 3000,
            'contextual_augmentation': 6000
        }
        
        is_valid, errors = validate_token_allocation(allocations, 20000, settings)
        assert not is_valid
        assert any('Warm slice' in e and 'outside bounds' in e for e in errors)
        
        # Too high (80%)
        allocations['warm_slice'] = 16000  # 80% of 20k
        allocations['structured_data'] = 2000
        allocations['contextual_augmentation'] = 2000
        
        is_valid, errors = validate_token_allocation(allocations, 20000, settings)
        assert not is_valid
        assert any('Warm slice' in e and 'outside bounds' in e for e in errors)
    
    def test_validate_allocation_structured_bounds(self, settings):
        """Test structured data percentage boundaries (10-25%)."""
        # Too low (5%)
        allocations = {
            'warm_slice': 10000,
            'structured_data': 1000,  # 5% of 20k
            'contextual_augmentation': 7000
        }
        
        is_valid, errors = validate_token_allocation(allocations, 20000, settings)
        assert not is_valid
        assert any('Structured data' in e and 'outside bounds' in e for e in errors)
    
    def test_validate_allocation_augmentation_bounds(self, settings):
        """Test augmentation percentage boundaries (25-40%)."""
        # Too low (20%)
        allocations = {
            'warm_slice': 12000,
            'structured_data': 3000,
            'contextual_augmentation': 4000  # 20% of 20k
        }
        
        is_valid, errors = validate_token_allocation(allocations, 20000, settings)
        assert not is_valid
        assert any('Augmentation' in e and 'outside bounds' in e for e in errors)


class TestUtilizationCheck:
    """Test token utilization checking."""
    
    def test_utilization_optimal(self, settings):
        """Test optimal utilization (95% target)."""
        token_counts = {
            'total_available': 20000,
            'user_input': 500,
            'warm_slice': 9500,
            'structured': 3000,
            'augmentation': 6000
        }
        # Total used: 19000 = 95%
        
        utilization, is_within_target, message = check_utilization(token_counts, settings)
        assert utilization == 95.0
        assert is_within_target
        assert 'Optimal' in message
    
    def test_utilization_acceptable(self, settings):
        """Test acceptable utilization (90-98% range)."""
        token_counts = {
            'total_available': 20000,
            'user_input': 500,
            'warm_slice': 8500,
            'structured': 3000,
            'augmentation': 6000
        }
        # Total used: 18000 = 90%
        
        utilization, is_within_target, message = check_utilization(token_counts, settings)
        assert utilization == 90.0
        assert is_within_target
        assert 'Acceptable' in message
    
    def test_utilization_underutilized(self, settings):
        """Test underutilization detection (<90%)."""
        token_counts = {
            'total_available': 20000,
            'user_input': 500,
            'warm_slice': 7000,
            'structured': 2500,
            'augmentation': 5000
        }
        # Total used: 15000 = 75%
        
        utilization, is_within_target, message = check_utilization(token_counts, settings)
        assert utilization == 75.0
        assert not is_within_target
        assert 'Underutilized' in message
    
    def test_utilization_overutilized(self, settings):
        """Test overutilization detection (>98%)."""
        token_counts = {
            'total_available': 20000,
            'user_input': 500,
            'warm_slice': 10000,
            'structured': 3500,
            'augmentation': 6200
        }
        # Total used: 20200 = 101% (shouldn't happen but test the check)
        
        utilization, is_within_target, message = check_utilization(token_counts, settings)
        assert utilization > 98
        assert not is_within_target
        assert 'Overutilized' in message
    
    def test_utilization_zero_available(self, settings):
        """Test handling of zero available tokens."""
        token_counts = {
            'total_available': 0,
            'user_input': 100,
            'warm_slice': 100
        }
        
        utilization, is_within_target, message = check_utilization(token_counts, settings)
        assert utilization == 0
        assert not is_within_target


class TestPhaseCompletion:
    """Test phase completion validation."""
    
    def test_phase_completion_all_complete(self, mock_turn_context):
        """Test when all required phases are complete."""
        mock_turn_context.phase_states = {
            'user_input': 'completed',
            'warm_analysis': 'completed',
            'entity_state': 'completed',
            'deep_queries': 'completed',
            'payload_assembly': 'completed'
        }
        
        all_complete, incomplete = validate_phase_completion(mock_turn_context)
        assert all_complete
        assert len(incomplete) == 0
    
    def test_phase_completion_missing_phases(self, mock_turn_context):
        """Test detection of missing phases."""
        mock_turn_context.phase_states = {
            'user_input': 'completed',
            'warm_analysis': 'completed'
            # Missing: entity_state, deep_queries, payload_assembly
        }
        
        all_complete, incomplete = validate_phase_completion(mock_turn_context)
        assert not all_complete
        assert len(incomplete) == 3
        assert 'entity_state' in incomplete
        assert 'deep_queries' in incomplete
        assert 'payload_assembly' in incomplete
    
    def test_phase_completion_empty(self, mock_turn_context):
        """Test with no completed phases."""
        mock_turn_context.phase_states = {}
        
        all_complete, incomplete = validate_phase_completion(mock_turn_context)
        assert not all_complete
        assert len(incomplete) == 5  # All 5 required phases missing
"""
Unit tests for token_budget.py

Tests token budget allocation and management with 20k limit for testing.
"""

import pytest
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock

# Add nexus module to path
nexus_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(nexus_root))

from nexus.agents.lore.utils.token_budget import TokenBudgetManager


class TestTokenBudgetManager:
    """Test the TokenBudgetManager class."""
    
    def test_manager_initialization(self, settings):
        """Test manager initializes with correct settings."""
        manager = TokenBudgetManager(settings)
        
        assert manager.settings == settings
        assert manager.token_budget_config is not None
        assert 'apex_context_window' in manager.token_budget_config
    
    def test_calculate_budget_basic(self, settings):
        """Test basic budget calculation."""
        manager = TokenBudgetManager(settings)
        
        user_input = "Test user input"
        budget = manager.calculate_budget(user_input)
        
        # Should return dictionary with allocations
        assert isinstance(budget, dict)
        assert 'total_available' in budget
        assert 'warm_slice' in budget
        assert 'structured' in budget
        assert 'augmentation' in budget
    
    def test_calculate_budget_with_reasoning_model(self, settings):
        """Test budget calculation with reasoning model (o1, gpt-5)."""
        manager = TokenBudgetManager(settings)
        
        user_input = "Test input"
        
        # Test with o1 model (reasoning)
        budget = manager.calculate_budget(user_input, apex_model="o1-preview")
        
        # Should have reasoning reserve
        assert 'reasoning_reserve' in budget or budget['total_available'] < 200000
    
    def test_calculate_budget_respects_window(self, settings):
        """Test that budget doesn't exceed context window."""
        manager = TokenBudgetManager(settings)
        
        user_input = "Test input"
        budget = manager.calculate_budget(user_input)
        
        # Total allocations shouldn't exceed apex window
        apex_window = manager.token_budget_config.get('apex_context_window', 200000)
        total_allocated = sum([
            budget.get('warm_slice', 0),
            budget.get('structured', 0),
            budget.get('augmentation', 0),
            budget.get('user_input', 0),
            budget.get('system_prompt', 0)
        ])
        
        assert total_allocated <= apex_window
    
    def test_calculate_budget_with_long_input(self, settings):
        """Test budget calculation with very long user input."""
        manager = TokenBudgetManager(settings)
        
        # Create a very long input
        long_input = "This is a test. " * 1000  # ~4000 tokens
        budget = manager.calculate_budget(long_input)
        
        # Should account for the long input
        assert budget['user_input'] > 3000
        
        # Should reduce other allocations accordingly
        assert budget['warm_slice'] < budget['total_available'] * 0.7
    
    @patch('nexus.agents.lore.utils.token_budget.calculate_chunk_tokens')
    def test_calculate_budget_token_counting(self, mock_calc_tokens, settings):
        """Test that token counting is called correctly."""
        mock_calc_tokens.return_value = 100
        
        manager = TokenBudgetManager(settings)
        user_input = "Test input"
        budget = manager.calculate_budget(user_input)
        
        # Should have called token calculation
        mock_calc_tokens.assert_called_with(user_input)
        assert budget['user_input'] == 100


class TestBudgetAllocation:
    """Test budget allocation logic."""
    
    def test_allocation_percentages(self, settings):
        """Test that allocations follow percentage constraints."""
        manager = TokenBudgetManager(settings)
        
        user_input = "Test"
        budget = manager.calculate_budget(user_input)
        
        # Get percentage constraints from settings
        percent_config = settings['Agent Settings']['LORE']['payload_percent_budget']
        
        # Calculate actual percentages
        total_context = budget['warm_slice'] + budget['structured'] + budget['augmentation']
        
        if total_context > 0:
            warm_percent = (budget['warm_slice'] / total_context) * 100
            struct_percent = (budget['structured'] / total_context) * 100
            augment_percent = (budget['augmentation'] / total_context) * 100
            
            # Check warm slice (40-70%)
            assert percent_config['warm_slice']['min'] <= warm_percent <= percent_config['warm_slice']['max']
            
            # Check structured (10-25%)
            assert percent_config['structured_summaries']['min'] <= struct_percent <= percent_config['structured_summaries']['max']
            
            # Check augmentation (25-40%)
            assert percent_config['contextual_augmentation']['min'] <= augment_percent <= percent_config['contextual_augmentation']['max']
    
    def test_allocation_with_test_limit(self, settings):
        """Test allocation with reduced context window."""
        # Modify settings to use smaller window for testing
        test_settings = settings.copy()
        test_settings['Agent Settings']['LORE']['token_budget']['apex_context_window'] = 20000
        
        manager = TokenBudgetManager(test_settings)
        user_input = "Test"
        budget = manager.calculate_budget(user_input)
        
        # With 20k window, allocations should be smaller
        total = sum([
            budget.get('warm_slice', 0),
            budget.get('structured', 0),
            budget.get('augmentation', 0),
            budget.get('user_input', 0),
            budget.get('system_prompt', 0)
        ])
        
        # Should respect the 20k window
        assert total <= 20000
        assert budget['apex_window'] == 20000


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_user_input(self, settings):
        """Test with empty user input."""
        manager = TokenBudgetManager(settings)
        
        budget = manager.calculate_budget("")
        
        # Should still allocate budget
        assert budget['total_available'] > 0
        assert budget['user_input'] == 0
    
    def test_missing_settings(self):
        """Test with missing/minimal settings."""
        minimal_settings = {
            'Agent Settings': {
                'LORE': {
                    'token_budget': {},
                    'payload_percent_budget': {
                        'warm_slice': {'min': 40, 'max': 70},
                        'structured_summaries': {'min': 10, 'max': 25},
                        'contextual_augmentation': {'min': 25, 'max': 40}
                    }
                }
            }
        }
        
        manager = TokenBudgetManager(minimal_settings)
        budget = manager.calculate_budget("Test")
        
        # Should use defaults
        assert budget['total_available'] > 0
    
    def test_extreme_percentages(self, settings):
        """Test with extreme percentage configurations."""
        # Modify settings to have extreme percentages
        extreme_settings = settings.copy()
        extreme_settings['Agent Settings']['LORE']['payload_percent_budget'] = {
            'warm_slice': {'min': 80, 'max': 90},  # Very high
            'structured_summaries': {'min': 5, 'max': 10},  # Very low
            'contextual_augmentation': {'min': 5, 'max': 10}  # Very low
        }
        
        manager = TokenBudgetManager(extreme_settings)
        budget = manager.calculate_budget("Test")
        
        # Should still produce valid budget
        assert budget['warm_slice'] > 0
        assert budget['structured'] > 0
        assert budget['augmentation'] > 0
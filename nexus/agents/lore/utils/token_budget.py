"""
Token Budget Management for LORE

Handles dynamic token budget calculation and allocation.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("nexus.lore.token_budget")


class TokenBudgetManager:
    """Manages token budget allocation for context assembly"""
    
    def __init__(self, settings: Dict[str, Any]):
        """Initialize with LORE settings"""
        self.settings = settings
        lore_settings = settings.get("Agent Settings", {}).get("LORE", {})
        self.token_budget_config = lore_settings.get("token_budget", {})
        self.allocation_config = lore_settings.get("component_allocation", {})
    
    def calculate_budget(self, user_input: str, apex_model: str = None) -> Dict[str, int]:
        """
        Calculate dynamic token budget for current turn.
        
        Args:
            user_input: The user's input text
            apex_model: Optional model name to check for reasoning models
            
        Returns:
            Dictionary with token allocations
        """
        # Get base values
        apex_window = self.token_budget_config.get("apex_context_window", 200000)
        system_prompt = self.token_budget_config.get("system_prompt_tokens", 5000)
        
        # Calculate user input tokens (rough estimate: 1 token per 4 chars)
        user_input_tokens = len(user_input) // 4
        
        # Check if we're using a reasoning model
        if not apex_model:
            apex_settings = self.settings.get("API Settings", {}).get("apex", {})
            apex_model = apex_settings.get("model", "gpt-4o")
        
        using_reasoning_model = apex_model.startswith("o") or "gpt-5" in apex_model
        
        # Reserve tokens for reasoning if needed (up to 30k for high-effort reasoning)
        reasoning_reserve = 30000 if using_reasoning_model else 0
        response_reserve = 4000
        
        # Calculate available context
        available_context = apex_window - system_prompt - user_input_tokens - reasoning_reserve - response_reserve
        
        # Calculate component allocations using minimum percentages initially
        warm_slice_min = self.allocation_config.get("warm_slice", {}).get("min", 40)
        structured_min = self.allocation_config.get("structured_summaries", {}).get("min", 10)
        augmentation_min = self.allocation_config.get("contextual_augmentation", {}).get("min", 25)
        
        # Start with minimum allocations
        warm_slice_tokens = int(available_context * warm_slice_min / 100)
        structured_tokens = int(available_context * structured_min / 100)
        augmentation_tokens = int(available_context * augmentation_min / 100)
        
        budget = {
            "total_available": available_context,
            "user_input": user_input_tokens,
            "warm_slice": warm_slice_tokens,
            "structured": structured_tokens,
            "augmentation": augmentation_tokens,
            "reasoning_reserve": reasoning_reserve,
            "response_reserve": response_reserve,
            "using_reasoning_model": using_reasoning_model,
            "apex_window": apex_window,
            "system_prompt": system_prompt
        }
        
        logger.debug(f"Token budget calculated: {budget}")
        return budget
    
    def calculate_utilization(self, token_counts: Dict[str, int]) -> float:
        """
        Calculate the utilization percentage of the token budget.
        
        Args:
            token_counts: Dictionary with actual token usage
            
        Returns:
            Utilization percentage (0-100)
        """
        total_used = sum([
            token_counts.get("user_input", 0),
            token_counts.get("warm_slice", 0),
            token_counts.get("structured", 0),
            token_counts.get("augmentation", 0)
        ])
        
        total_available = token_counts.get("total_available", 1)
        utilization = (total_used / total_available) * 100 if total_available > 0 else 0
        
        return utilization
    
    def optimize_allocation(self, 
                           current_counts: Dict[str, int],
                           available_content: Dict[str, int]) -> Dict[str, int]:
        """
        Optimize token allocation to reach target utilization.
        
        Args:
            current_counts: Current token usage
            available_content: Available content that could be added
            
        Returns:
            Optimized token allocation
        """
        current_utilization = self.calculate_utilization(current_counts)
        target_utilization = self.token_budget_config.get("utilization", {}).get("target", 95)
        
        if current_utilization >= target_utilization:
            return current_counts
        
        # Calculate remaining tokens
        total_available = current_counts.get("total_available", 0)
        current_used = sum([
            current_counts.get("user_input", 0),
            current_counts.get("warm_slice", 0),
            current_counts.get("structured", 0),
            current_counts.get("augmentation", 0)
        ])
        
        remaining = total_available - current_used
        target_additional = int((target_utilization / 100) * total_available - current_used)
        
        # Get max allocation percentages
        warm_slice_max = self.allocation_config.get("warm_slice", {}).get("max", 70)
        structured_max = self.allocation_config.get("structured_summaries", {}).get("max", 25)
        augmentation_max = self.allocation_config.get("contextual_augmentation", {}).get("max", 40)
        
        # Calculate max tokens for each component
        max_warm = int(total_available * warm_slice_max / 100)
        max_structured = int(total_available * structured_max / 100)
        max_augmentation = int(total_available * augmentation_max / 100)
        
        # Distribute remaining tokens proportionally
        optimized = current_counts.copy()
        
        # Priority order: warm slice, augmentation, structured
        if available_content.get("warm_slice", 0) > 0:
            additional_warm = min(
                target_additional // 2,
                max_warm - current_counts.get("warm_slice", 0),
                available_content.get("warm_slice", 0)
            )
            optimized["warm_slice"] += additional_warm
            target_additional -= additional_warm
        
        if available_content.get("augmentation", 0) > 0 and target_additional > 0:
            additional_aug = min(
                target_additional,
                max_augmentation - current_counts.get("augmentation", 0),
                available_content.get("augmentation", 0)
            )
            optimized["augmentation"] += additional_aug
            target_additional -= additional_aug
        
        if available_content.get("structured", 0) > 0 and target_additional > 0:
            additional_struct = min(
                target_additional,
                max_structured - current_counts.get("structured", 0),
                available_content.get("structured", 0)
            )
            optimized["structured"] += additional_struct
        
        logger.debug(f"Optimized allocation from {current_utilization:.1f}% to {self.calculate_utilization(optimized):.1f}%")
        return optimized
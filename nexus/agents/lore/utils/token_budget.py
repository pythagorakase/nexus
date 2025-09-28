"""
Token Budget Management for LORE

Handles dynamic token budget calculation and allocation.
"""

import logging
from typing import Dict, Any, Optional
from .chunk_operations import calculate_chunk_tokens

logger = logging.getLogger("nexus.lore.token_budget")


class TokenBudgetManager:
    """Manages token budget allocation for context assembly"""
    
    def __init__(self, settings: Dict[str, Any]):
        """Initialize with LORE settings"""
        self.settings = settings
        lore_settings = settings.get("Agent Settings", {}).get("LORE", {})
        self.token_budget_config = lore_settings.get("token_budget", {})
        allocation = lore_settings.get("component_allocation")
        if not allocation:
            allocation = lore_settings.get("payload_percent_budget", {})
        self.allocation_config = allocation or {}
    
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
        
        # Calculate user input tokens using tiktoken
        user_input_tokens = calculate_chunk_tokens(user_input)
        
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
    
    def calculate_token_budget(self, tpm: int, system_tokens: int, user_tokens: int) -> int:
        """
        Simple arithmetic: Calculate available tokens for context.
        NO LLM NEEDED - just subtraction!
        
        Args:
            tpm: Total tokens per message (model context window)
            system_tokens: Tokens used by system prompt
            user_tokens: Tokens used by user input
            
        Returns:
            Available tokens for context
        """
        return tpm - system_tokens - user_tokens
    
    def allocate_percentages(self, narrative_state: str, budget: int) -> Dict[str, int]:
        """
        Programmatic percentage allocation based on narrative state.
        NO LLM NEEDED - just a lookup table!
        
        Args:
            narrative_state: Type of narrative moment (dialogue_heavy, action_sequence, etc.)
            budget: Total token budget available
            
        Returns:
            Token allocations for each component
        """
        # Predefined allocation strategies based on narrative state
        allocations = {
            "dialogue_heavy": {"warm": 60, "augment": 30, "structured": 10},
            "dialogue_intensive": {"warm": 65, "augment": 25, "structured": 10},
            "action_sequence": {"warm": 70, "augment": 20, "structured": 10},
            "action_focused": {"warm": 70, "augment": 20, "structured": 10},
            "world_building": {"warm": 40, "augment": 40, "structured": 20},
            "character_focus": {"warm": 45, "augment": 35, "structured": 20},
            "character_development": {"warm": 45, "augment": 35, "structured": 20},
            "exploration": {"warm": 35, "augment": 45, "structured": 20},
            "flashback": {"warm": 30, "augment": 50, "structured": 20},
            "planning": {"warm": 50, "augment": 30, "structured": 20},
            "investigation": {"warm": 40, "augment": 45, "structured": 15},
            "combat": {"warm": 75, "augment": 15, "structured": 10},
            "default": {"warm": 50, "augment": 30, "structured": 20}
        }
        
        # Get percentages for the narrative state (with fallback to default)
        percentages = allocations.get(narrative_state.lower(), allocations["default"])
        
        # Calculate actual token amounts
        result = {
            "warm_slice": int(budget * percentages["warm"] / 100),
            "contextual_augmentation": int(budget * percentages["augment"] / 100),
            "structured_data": int(budget * percentages["structured"] / 100)
        }
        
        # Log the allocation for debugging
        logger.debug(f"Allocated tokens for '{narrative_state}' state: warm={result['warm_slice']}, augment={result['contextual_augmentation']}, structured={result['structured_data']}")
        
        return result
    
    def validate_budget_constraints(self, allocations: Dict[str, int], constraints: Optional[Dict[str, Dict[str, int]]] = None) -> bool:
        """
        Validate that allocations meet min/max constraints.
        NO LLM NEEDED - just comparison operators!
        
        Args:
            allocations: Proposed token allocations
            constraints: Optional override constraints (defaults to config)
            
        Returns:
            True if allocations are valid, False otherwise
        """
        if not constraints:
            constraints = self.allocation_config
        
        total = sum(allocations.values())
        
        # Check warm slice constraints
        warm_tokens = allocations.get("warm_slice", 0)
        warm_min = int(total * constraints.get("warm_slice", {}).get("min", 40) / 100)
        warm_max = int(total * constraints.get("warm_slice", {}).get("max", 70) / 100)
        
        if not (warm_min <= warm_tokens <= warm_max):
            logger.warning(f"Warm slice allocation {warm_tokens} outside bounds [{warm_min}, {warm_max}]")
            return False
        
        # Check structured data constraints
        structured_tokens = allocations.get("structured_data", 0)
        structured_min = int(total * constraints.get("structured_summaries", {}).get("min", 10) / 100)
        structured_max = int(total * constraints.get("structured_summaries", {}).get("max", 25) / 100)
        
        if not (structured_min <= structured_tokens <= structured_max):
            logger.warning(f"Structured data allocation {structured_tokens} outside bounds [{structured_min}, {structured_max}]")
            return False
        
        # Check augmentation constraints  
        augment_tokens = allocations.get("contextual_augmentation", 0)
        augment_min = int(total * constraints.get("contextual_augmentation", {}).get("min", 25) / 100)
        augment_max = int(total * constraints.get("contextual_augmentation", {}).get("max", 40) / 100)
        
        if not (augment_min <= augment_tokens <= augment_max):
            logger.warning(f"Augmentation allocation {augment_tokens} outside bounds [{augment_min}, {augment_max}]")
            return False
        
        return True

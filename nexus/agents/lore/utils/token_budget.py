"""
Token Budget Management for LORE

Handles dynamic token budget calculation and allocation.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
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
        # Get base values - apex_context_window is required
        if "apex_context_window" not in self.token_budget_config:
            raise ValueError(
                "apex_context_window must be configured in the configuration file under "
                "Agent Settings > LORE > token_budget > apex_context_window"
            )
        apex_window = self.token_budget_config["apex_context_window"]
        logger.debug(f"Using apex_context_window: {apex_window} tokens")

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

    def estimate_entity_tokens(self, entity: Dict[str, Any]) -> int:
        """
        Estimate token count for an entity dictionary.

        Args:
            entity: Entity dictionary with various text fields

        Returns:
            Estimated token count
        """
        # Check if already calculated
        if "token_count" in entity and isinstance(entity["token_count"], int):
            return entity["token_count"]

        # Collect all text content from entity
        text_candidates = []
        for key in ("summary", "details", "text", "content", "description", "background", "personality"):
            value = entity.get(key)
            if isinstance(value, str) and value.strip():
                text_candidates.append(value)

        # If no text found, create minimal representation
        if not text_candidates:
            name = entity.get("name", "Unknown")
            summary = entity.get("summary", "")
            text_candidates.append(f"{name}: {summary}")

        tokens = calculate_chunk_tokens("\n".join(text_candidates))
        entity["token_count"] = tokens
        return tokens

    def calculate_structured_tokens_by_tier(
        self,
        entity_data: Dict[str, Any]
    ) -> Tuple[int, int]:
        """
        Calculate token counts separately for baseline and featured entities.

        Args:
            entity_data: Hierarchical entity data with baseline/featured structure

        Returns:
            Tuple of (baseline_tokens, featured_tokens)
        """
        baseline_tokens = 0
        featured_tokens = 0

        # Count baseline entity tokens (CANNOT be trimmed - protected)
        for entity_type in ("characters", "locations", "factions"):
            entities = entity_data.get(entity_type, {})
            if isinstance(entities, dict):
                # Hierarchical structure
                for entity in entities.get("baseline", []):
                    baseline_tokens += self.estimate_entity_tokens(entity)
                for entity in entities.get("featured", []):
                    featured_tokens += self.estimate_entity_tokens(entity)
            else:
                # Flat structure (backward compatibility)
                for entity in entities:
                    baseline_tokens += self.estimate_entity_tokens(entity)

        # Count relationships as featured
        for rel in entity_data.get("relationships", []):
            featured_tokens += self.estimate_entity_tokens(rel)

        # Count events and threats as featured
        for event in entity_data.get("events", []):
            featured_tokens += self.estimate_entity_tokens(event)

        for threat in entity_data.get("threats", []):
            featured_tokens += self.estimate_entity_tokens(threat)

        logger.debug(f"Structured tokens: {baseline_tokens} baseline (protected), {featured_tokens} featured (trimmable)")
        return baseline_tokens, featured_tokens

    def trim_structured_with_baseline_protection(
        self,
        entity_data: Dict[str, Any],
        max_tokens: int
    ) -> Dict[str, Any]:
        """
        Trim structured entity data to fit budget while PROTECTING baseline entities.

        Baseline entities (minimal tracking fields for ALL entities) are never trimmed.
        Featured entities are trimmed by priority:
        - Priority 0: Season/episode summaries (if present)
        - Priority 1: Characters with "present" reference
        - Priority 2: Places with "setting" reference
        - Priority 3: Characters with other references
        - Priority 4: Other places
        - Priority 5: Factions
        - Priority 6: Relationships
        - Priority 7: Events
        - Priority 8: Threats

        Args:
            entity_data: Hierarchical entity data to trim
            max_tokens: Maximum tokens allowed for structured data

        Returns:
            Trimmed entity data
        """
        baseline_tokens, featured_tokens = self.calculate_structured_tokens_by_tier(entity_data)
        total_tokens = baseline_tokens + featured_tokens

        if total_tokens <= max_tokens:
            logger.debug(f"No trimming needed: {total_tokens} <= {max_tokens}")
            return entity_data

        logger.info(
            f"Structured data ({total_tokens} tokens) exceeds budget ({max_tokens} tokens). "
            f"Baseline: {baseline_tokens} tokens (protected), Featured: {featured_tokens} tokens (trimmable)"
        )

        # Calculate available budget for featured entities
        available_for_featured = max_tokens - baseline_tokens

        if available_for_featured <= 0:
            logger.warning(
                f"Baseline entities ({baseline_tokens} tokens) exceed structured budget ({max_tokens} tokens)! "
                f"Consider increasing apex_context_window or structured_summaries max%. "
                f"Removing ALL featured entities to stay within budget."
            )
            # Keep baseline, remove all featured
            trimmed_data = {
                "characters": {
                    "baseline": entity_data.get("characters", {}).get("baseline", []),
                    "featured": []
                },
                "locations": {
                    "baseline": entity_data.get("locations", {}).get("baseline", []),
                    "featured": []
                },
                "factions": {
                    "baseline": entity_data.get("factions", {}).get("baseline", []),
                    "featured": []
                },
                "relationships": [],
                "events": [],
                "threats": []
            }
            return trimmed_data

        # Collect all trimmable items with priorities
        trimmable_items: List[Tuple[str, str, Any, int, int]] = []  # (category, type, entity, tokens, priority)

        # Characters
        for char in entity_data.get("characters", {}).get("featured", []):
            tokens = self.estimate_entity_tokens(char)
            ref_type = char.get("reference_type", "unknown")
            priority = 1 if ref_type == "present" else 3
            trimmable_items.append(("characters", "featured", char, tokens, priority))

        # Places
        for place in entity_data.get("locations", {}).get("featured", []):
            tokens = self.estimate_entity_tokens(place)
            ref_type = place.get("reference_type", "unknown")
            priority = 2 if ref_type == "setting" else 4
            trimmable_items.append(("locations", "featured", place, tokens, priority))

        # Factions
        for faction in entity_data.get("factions", {}).get("featured", []):
            tokens = self.estimate_entity_tokens(faction)
            trimmable_items.append(("factions", "featured", faction, tokens, 5))

        # Relationships
        for rel in entity_data.get("relationships", []):
            tokens = self.estimate_entity_tokens(rel)
            trimmable_items.append(("relationships", "relationship", rel, tokens, 6))

        # Events
        for event in entity_data.get("events", []):
            tokens = self.estimate_entity_tokens(event)
            trimmable_items.append(("events", "event", event, tokens, 7))

        # Threats
        for threat in entity_data.get("threats", []):
            tokens = self.estimate_entity_tokens(threat)
            trimmable_items.append(("threats", "threat", threat, tokens, 8))

        # Sort by priority (lower is better), then by token count (larger first to maximize utilization)
        trimmable_items.sort(key=lambda x: (x[4], -x[3]))

        # Keep items until budget exhausted
        current_tokens = 0
        kept_items = {
            "characters": [],
            "locations": [],
            "factions": [],
            "relationships": [],
            "events": [],
            "threats": []
        }

        for category, item_type, entity, tokens, priority in trimmable_items:
            if current_tokens + tokens <= available_for_featured:
                current_tokens += tokens
                kept_items[category].append(entity)

        # Build trimmed entity data
        trimmed_data = {
            "characters": {
                "baseline": entity_data.get("characters", {}).get("baseline", []),
                "featured": kept_items["characters"]
            },
            "locations": {
                "baseline": entity_data.get("locations", {}).get("baseline", []),
                "featured": kept_items["locations"]
            },
            "factions": {
                "baseline": entity_data.get("factions", {}).get("baseline", []),
                "featured": kept_items["factions"]
            },
            "relationships": kept_items["relationships"],
            "events": kept_items["events"],
            "threats": kept_items["threats"]
        }

        trimmed_count = len(trimmable_items) - sum(len(items) for items in kept_items.values())
        trimmed_tokens = featured_tokens - current_tokens
        logger.info(
            f"Trimmed {trimmed_count} featured items ({trimmed_tokens} tokens). "
            f"Kept {sum(len(items) for items in kept_items.values())} items ({current_tokens} tokens)"
        )

        return trimmed_data

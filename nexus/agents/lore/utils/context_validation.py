"""
Context Validation for LORE

Validates context payloads against settings-defined constraints.
All validation is done in tokens and percentages, not chunk counts.
"""

import logging
from typing import Dict, Any, Tuple, List

logger = logging.getLogger("nexus.lore.context_validation")


def validate_context(context: Dict[str, Any], settings: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate context payload against constraints from settings.
    
    Args:
        context: Context payload to validate
        settings: Settings dictionary
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Get LORE settings
    lore_settings = settings.get("Agent Settings", {}).get("LORE", {})
    
    # Get token budget settings - apex_context_window is required
    token_budget = lore_settings.get("token_budget", {})
    if "apex_context_window" not in token_budget:
        raise ValueError(
            "apex_context_window must be configured in settings.json under "
            "Agent Settings > LORE > token_budget > apex_context_window"
        )
    apex_window = token_budget["apex_context_window"]
    logger.debug(f"Context validation using apex_context_window: {apex_window} tokens")
    
    # Get the percentage ranges
    ranges = lore_settings.get("payload_percent_budget", {})
    warm_range = ranges.get("warm_slice", {"min": 40, "max": 70})
    struct_range = ranges.get("structured_summaries", {"min": 10, "max": 25})
    augment_range = ranges.get("contextual_augmentation", {"min": 25, "max": 40})
    
    # Check token limits and allocations
    metadata = context.get("metadata", {})
    token_counts = metadata.get("token_counts", {})
    
    if token_counts:
        total_tokens = sum(token_counts.values())
        if total_tokens > apex_window:
            errors.append(f"Token limit exceeded: {total_tokens:,} > {apex_window:,}")
        
        # Check if each component meets its percentage requirements
        total_context_tokens = (
            token_counts.get("warm_slice", 0) +
            token_counts.get("structured", 0) +
            token_counts.get("augmentation", 0)
        )
        
        if total_context_tokens > 0:
            # Calculate actual percentages
            warm_pct = (token_counts.get("warm_slice", 0) / total_context_tokens) * 100
            struct_pct = (token_counts.get("structured", 0) / total_context_tokens) * 100
            augment_pct = (token_counts.get("augmentation", 0) / total_context_tokens) * 100
            
            # Validate warm slice percentage
            if warm_pct < warm_range["min"]:
                errors.append(f"Warm slice below minimum: {warm_pct:.1f}% < {warm_range['min']}%")
            elif warm_pct > warm_range["max"]:
                errors.append(f"Warm slice above maximum: {warm_pct:.1f}% > {warm_range['max']}%")
            
            # Validate structured data percentage
            if struct_pct < struct_range["min"]:
                errors.append(f"Structured data below minimum: {struct_pct:.1f}% < {struct_range['min']}%")
            elif struct_pct > struct_range["max"]:
                errors.append(f"Structured data above maximum: {struct_pct:.1f}% > {struct_range['max']}%")
            
            # Validate augmentation percentage
            if augment_pct < augment_range["min"]:
                errors.append(f"Augmentation below minimum: {augment_pct:.1f}% < {augment_range['min']}%")
            elif augment_pct > augment_range["max"]:
                errors.append(f"Augmentation above maximum: {augment_pct:.1f}% > {augment_range['max']}%")
    
    # Check required fields exist
    if not context.get("user_input"):
        errors.append("Missing user_input")
    
    if not context.get("narrative_context"):
        errors.append("Missing narrative_context")
    
    # Validate warm slice exists and has content
    warm_slice = context.get("narrative_context", {}).get("warm_slice", [])
    if not warm_slice:
        errors.append("Empty or missing warm_slice in narrative_context")
    
    return (len(errors) == 0, errors)


def validate_token_allocation(allocations: Dict[str, int], total_budget: int, settings: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that token allocations meet percentage constraints from settings.
    
    Args:
        allocations: Proposed token allocations
        total_budget: Total available token budget
        settings: Settings dictionary
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Get allocation ranges from settings
    lore_settings = settings.get("Agent Settings", {}).get("LORE", {})
    ranges = lore_settings.get("payload_percent_budget", {})
    
    # Check warm slice constraints
    warm_tokens = allocations.get("warm_slice", 0)
    warm_range = ranges.get("warm_slice", {"min": 40, "max": 70})
    warm_min_tokens = int(total_budget * warm_range["min"] / 100)
    warm_max_tokens = int(total_budget * warm_range["max"] / 100)
    
    if not (warm_min_tokens <= warm_tokens <= warm_max_tokens):
        errors.append(f"Warm slice allocation {warm_tokens:,} tokens outside bounds [{warm_min_tokens:,}, {warm_max_tokens:,}]")
    
    # Check structured data constraints
    structured_tokens = allocations.get("structured_data", 0)
    struct_range = ranges.get("structured_summaries", {"min": 10, "max": 25})
    struct_min_tokens = int(total_budget * struct_range["min"] / 100)
    struct_max_tokens = int(total_budget * struct_range["max"] / 100)
    
    if not (struct_min_tokens <= structured_tokens <= struct_max_tokens):
        errors.append(f"Structured data allocation {structured_tokens:,} tokens outside bounds [{struct_min_tokens:,}, {struct_max_tokens:,}]")
    
    # Check augmentation constraints
    augment_tokens = allocations.get("contextual_augmentation", 0)
    augment_range = ranges.get("contextual_augmentation", {"min": 25, "max": 40})
    augment_min_tokens = int(total_budget * augment_range["min"] / 100)
    augment_max_tokens = int(total_budget * augment_range["max"] / 100)
    
    if not (augment_min_tokens <= augment_tokens <= augment_max_tokens):
        errors.append(f"Augmentation allocation {augment_tokens:,} tokens outside bounds [{augment_min_tokens:,}, {augment_max_tokens:,}]")
    
    # Check that total doesn't exceed budget
    total_allocated = warm_tokens + structured_tokens + augment_tokens
    if total_allocated > total_budget:
        errors.append(f"Total allocation {total_allocated:,} exceeds budget {total_budget:,}")
    
    return (len(errors) == 0, errors)


def check_utilization(token_counts: Dict[str, int], settings: Dict[str, Any]) -> Tuple[float, bool, str]:
    """
    Check token utilization against target thresholds.
    
    Args:
        token_counts: Dictionary with actual token usage
        settings: Settings dictionary
        
    Returns:
        Tuple of (utilization_percentage, is_within_target, message)
    """
    # Get utilization targets from settings
    lore_settings = settings.get("Agent Settings", {}).get("LORE", {})
    token_budget = lore_settings.get("token_budget", {})
    utilization_config = token_budget.get("utilization", {})
    
    target = utilization_config.get("target", 95)
    minimum = utilization_config.get("minimum", 90)
    maximum = utilization_config.get("maximum", 98)
    
    # Calculate actual utilization
    total_available = token_counts.get("total_available", 1)
    total_used = sum([
        token_counts.get("user_input", 0),
        token_counts.get("warm_slice", 0),
        token_counts.get("structured", 0),
        token_counts.get("augmentation", 0)
    ])
    
    utilization = (total_used / total_available * 100) if total_available > 0 else 0
    
    # Check against thresholds
    if utilization < minimum:
        return (utilization, False, f"Underutilized: {utilization:.1f}% < {minimum}% minimum")
    elif utilization > maximum:
        return (utilization, False, f"Overutilized: {utilization:.1f}% > {maximum}% maximum")
    else:
        distance_from_target = abs(utilization - target)
        if distance_from_target < 5:
            return (utilization, True, f"Optimal: {utilization:.1f}% (target: {target}%)")
        else:
            return (utilization, True, f"Acceptable: {utilization:.1f}% (target: {target}%)")


def validate_phase_completion(turn_context: Any) -> Tuple[bool, List[str]]:
    """
    Validate that all required phases have been completed.
    
    Args:
        turn_context: TurnContext object
        
    Returns:
        Tuple of (all_completed, list_of_incomplete_phases)
    """
    required_phases = [
        "user_input",
        "warm_analysis", 
        "entity_state",
        "deep_queries",
        "payload_assembly"
    ]
    
    incomplete = []
    for phase in required_phases:
        if phase not in turn_context.phase_states:
            incomplete.append(phase)
    
    return (len(incomplete) == 0, incomplete)
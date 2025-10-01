"""
Comparison pairing logic for audition system.

Generates round-robin comparison pairs and manages comparison queue.
"""
import random
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ComparisonPair:
    """A pair of condition IDs to compare."""
    condition_a_id: int
    condition_b_id: int
    prompt_id: int


def generate_round_robin_pairs(
    condition_ids: List[int],
    prompt_ids: List[int],
    randomize_order: bool = True
) -> List[ComparisonPair]:
    """
    Generate all possible comparison pairs for round-robin evaluation.

    Args:
        condition_ids: List of condition IDs to compare
        prompt_ids: List of prompt IDs to use
        randomize_order: If True, randomize A/B positions for each pair

    Returns:
        List of ComparisonPair objects

    Examples:
        >>> pairs = generate_round_robin_pairs([1, 2, 3], [100, 101])
        >>> len(pairs)  # 3 choose 2 = 3 pairs × 2 prompts = 6 total
        6
    """
    pairs = []

    for prompt_id in prompt_ids:
        # Generate all unique pairs of conditions
        for i in range(len(condition_ids)):
            for j in range(i + 1, len(condition_ids)):
                a_id = condition_ids[i]
                b_id = condition_ids[j]

                # Randomly swap A/B position to avoid bias
                if randomize_order and random.random() < 0.5:
                    a_id, b_id = b_id, a_id

                pairs.append(ComparisonPair(
                    condition_a_id=a_id,
                    condition_b_id=b_id,
                    prompt_id=prompt_id
                ))

    return pairs


def filter_already_judged(
    pairs: List[ComparisonPair],
    judged_pairs: set[Tuple[int, int, int]]
) -> List[ComparisonPair]:
    """
    Remove pairs that have already been judged.

    Args:
        pairs: List of comparison pairs
        judged_pairs: Set of (prompt_id, condition_a_id, condition_b_id) tuples

    Returns:
        Filtered list of ComparisonPair objects
    """
    pending = []
    for pair in pairs:
        # Check both orderings (A,B) and (B,A) since order doesn't matter for judged status
        key1 = (pair.prompt_id, pair.condition_a_id, pair.condition_b_id)
        key2 = (pair.prompt_id, pair.condition_b_id, pair.condition_a_id)

        if key1 not in judged_pairs and key2 not in judged_pairs:
            pending.append(pair)

    return pending

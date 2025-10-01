"""
ELO rating system for model comparison.

Implements standard ELO algorithm with support for ties.
"""
from typing import Tuple


def calculate_elo_update(
    rating_a: float,
    rating_b: float,
    outcome: float,
    k_factor: float = 32.0
) -> Tuple[float, float]:
    """
    Calculate new ELO ratings after a comparison.

    Args:
        rating_a: Current ELO rating for condition A
        rating_b: Current ELO rating for condition B
        outcome: Result of comparison
            - 1.0 = A wins
            - 0.5 = Tie
            - 0.0 = B wins
        k_factor: ELO K-factor (higher = more volatile ratings)

    Returns:
        Tuple of (new_rating_a, new_rating_b)

    Examples:
        >>> calculate_elo_update(1500, 1500, 1.0)  # A wins, equal ratings
        (1516.0, 1484.0)

        >>> calculate_elo_update(1500, 1500, 0.5)  # Tie
        (1500.0, 1500.0)

        >>> calculate_elo_update(1600, 1400, 0.0)  # B wins (upset)
        (1571.2, 1428.8)
    """
    # Calculate expected scores
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    expected_b = 1 - expected_a

    # Calculate new ratings
    new_rating_a = rating_a + k_factor * (outcome - expected_a)
    new_rating_b = rating_b + k_factor * ((1 - outcome) - expected_b)

    return (new_rating_a, new_rating_b)


def outcome_from_winner(
    winner_id: int | None,
    condition_a_id: int,
    condition_b_id: int
) -> float:
    """
    Convert winner condition ID to ELO outcome value.

    Args:
        winner_id: ID of winning condition, or None for tie
        condition_a_id: ID of condition A
        condition_b_id: ID of condition B

    Returns:
        - 1.0 if A wins
        - 0.5 if tie
        - 0.0 if B wins

    Raises:
        ValueError: If winner_id is not None, condition_a_id, or condition_b_id
    """
    if winner_id is None:
        return 0.5
    elif winner_id == condition_a_id:
        return 1.0
    elif winner_id == condition_b_id:
        return 0.0
    else:
        raise ValueError(
            f"winner_id ({winner_id}) must be None or match condition_a_id "
            f"({condition_a_id}) or condition_b_id ({condition_b_id})"
        )

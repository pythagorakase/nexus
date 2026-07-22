"""Centralized helpers for the scope-bound ``status:<level>`` pair-tag family."""

from __future__ import annotations

from typing import Any, Iterable, Optional


STATUS_TAG_PREFIX = "status:"

STATUS_LEVEL_RANKS: dict[str, int] = {
    "enslaved": -3,
    "pariah": -2,
    "outcast": -1,
    "junior": 1,
    "respected": 2,
    "senior": 3,
    "elite": 4,
    "executive": 5,
    "sovereign": 6,
}

NEGATIVE_STATUS_LEVELS = frozenset({"outcast", "pariah", "enslaved"})
STATUS_LEVELS = frozenset(STATUS_LEVEL_RANKS)
STATUS_TAGS = frozenset(f"{STATUS_TAG_PREFIX}{level}" for level in STATUS_LEVELS)


def normalize_status_level(level_or_tag: str) -> str:
    """Return the canonical status level from either ``level`` or ``status:level``."""

    value = str(level_or_tag).strip()
    if value.startswith(STATUS_TAG_PREFIX):
        value = value.removeprefix(STATUS_TAG_PREFIX)
    if value not in STATUS_LEVEL_RANKS:
        raise ValueError(
            f"Unknown status level {level_or_tag!r}; expected one of "
            f"{sorted(STATUS_LEVELS)}"
        )
    return value


def status_tag_for_level(level: str) -> str:
    """Return the registered pair-tag name for a status level."""

    return f"{STATUS_TAG_PREFIX}{normalize_status_level(level)}"


def level_from_status_tag(tag: str) -> str:
    """Return the level encoded by a ``status:<level>`` pair-tag name."""

    value = str(tag).strip()
    if not value.startswith(STATUS_TAG_PREFIX):
        raise ValueError(f"Not a status pair-tag: {tag!r}")
    return normalize_status_level(value)


def is_negative_status(level: str) -> bool:
    """Return whether a status level is socially negative."""

    return normalize_status_level(level) in NEGATIVE_STATUS_LEVELS


def status_at_or_above_level(level: str, threshold: str) -> bool:
    """Return whether ``level`` has rank greater than or equal to ``threshold``."""

    return (
        STATUS_LEVEL_RANKS[normalize_status_level(level)]
        >= STATUS_LEVEL_RANKS[normalize_status_level(threshold)]
    )


def has_any_status(
    cur: Any,
    *,
    subject_entity_id: int,
    scope_faction_entity_id: int,
) -> Optional[str]:
    """Return the highest active status level for one subject→scope edge."""

    return _highest_status_level(
        _fetch_status_levels(
            cur,
            subject_entity_id=subject_entity_id,
            scope_faction_entity_id=scope_faction_entity_id,
        )
    )


def status_at_or_above(
    cur: Any,
    *,
    subject_entity_id: int,
    scope_faction_entity_id: int,
    threshold: str,
) -> bool:
    """Return whether one subject→scope edge has status at ``threshold`` or above."""

    level = has_any_status(
        cur,
        subject_entity_id=subject_entity_id,
        scope_faction_entity_id=scope_faction_entity_id,
    )
    return level is not None and status_at_or_above_level(level, threshold)


def enumerate_status_above(
    cur: Any,
    *,
    subject_entity_id: int,
    threshold: str,
) -> list[tuple[int, str]]:
    """List scope factions where the subject has status at ``threshold`` or above."""

    threshold_level = normalize_status_level(threshold)
    cur.execute(
        """
        SELECT ept.object_entity_id AS scope_faction_entity_id,
               pt.tag
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        WHERE ept.subject_entity_id = %s
          AND ept.cleared_at IS NULL
          AND NOT pt.deprecated
          AND pt.tag = ANY(%s)
        """,
        (subject_entity_id, sorted(STATUS_TAGS)),
    )

    by_scope: dict[int, list[str]] = {}
    for row in cur.fetchall():
        scope_id = int(_row_value(row, "scope_faction_entity_id", 0))
        level = level_from_status_tag(str(_row_value(row, "tag", 1)))
        by_scope.setdefault(scope_id, []).append(level)

    results: list[tuple[int, str]] = []
    for scope_id, levels in by_scope.items():
        highest_level = _highest_status_level(levels)
        if highest_level is not None and status_at_or_above_level(
            highest_level, threshold_level
        ):
            results.append((scope_id, highest_level))
    return sorted(results)


def _fetch_status_levels(
    cur: Any,
    *,
    subject_entity_id: int,
    scope_faction_entity_id: int,
) -> list[str]:
    cur.execute(
        """
        SELECT pt.tag
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        WHERE ept.subject_entity_id = %s
          AND ept.object_entity_id = %s
          AND ept.cleared_at IS NULL
          AND NOT pt.deprecated
          AND pt.tag = ANY(%s)
        """,
        (subject_entity_id, scope_faction_entity_id, sorted(STATUS_TAGS)),
    )
    return [
        level_from_status_tag(str(_row_value(row, "tag", 0))) for row in cur.fetchall()
    ]


def _highest_status_level(levels: Iterable[str]) -> Optional[str]:
    normalized = [normalize_status_level(level) for level in levels]
    if not normalized:
        return None
    return max(normalized, key=lambda level: STATUS_LEVEL_RANKS[level])


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "get"):
        return row[key]
    return row[index]

"""Shared effective-activity predicate for expiring entity tags."""

from __future__ import annotations


def active_entity_tag_at_world_time_sql(
    *,
    entity_tag_alias: str,
    world_time_sql: str,
) -> str:
    """Render the canonical read-side activity predicate.

    Callers supply SQL identifiers or parameter expressions owned by their
    static query. This helper deliberately performs no quoting and must never
    receive provider-authored or other runtime text.
    """

    if not entity_tag_alias or not world_time_sql:
        raise ValueError("Entity-tag activity SQL requires both expressions")
    return (
        f"({world_time_sql} IS NULL "
        f"OR {entity_tag_alias}.expires_at_world_time IS NULL "
        f"OR {entity_tag_alias}.expires_at_world_time > {world_time_sql})"
    )

"""Apply reviewed entity-tag manifest operations safely."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping as MappingABC
from typing import Any, Mapping, Optional, Sequence


ENTITY_TAG_MANIFEST_APPLY_SCHEMA_VERSION = "orrery_entity_tag_manifest_apply.v1"
ENTITY_TAG_MANIFEST_SOURCE_KIND = "system"
ENTITY_TAG_OPERATION_TYPES = frozenset({"insert_entity_tag", "review_entity_tag"})


def apply_entity_tag_manifest(
    cur: Any,
    manifest: Mapping[str, Any],
    *,
    manifest_schema_version: str,
    entity_kind: str,
    allowed_categories: Sequence[str],
    exclusive_categories: Sequence[str],
    dry_run: bool = True,
    source_kind: str = ENTITY_TAG_MANIFEST_SOURCE_KIND,
) -> dict[str, Any]:
    """Apply reviewed ready entity-tag operations from a manifest.

    This deliberately consumes only operations that have been promoted to
    ``status=ready`` with ``review_required=false``. Review-required rows,
    non-entity-tag rows, pair-tag candidates, prose preservation, and destructive
    cleanup remain outside this command.
    """

    if manifest.get("schema_version") != manifest_schema_version:
        raise ValueError(
            f"{entity_kind} apply requires {manifest_schema_version}; got "
            f"{manifest.get('schema_version')!r}"
        )

    _validate_entity_tag_source_kind(cur, source_kind)
    allowed_category_set = set(allowed_categories)
    exclusive_category_set = set(exclusive_categories)
    registered_categories = _load_allowed_categories(cur, entity_kind)
    missing_categories = allowed_category_set - registered_categories
    if missing_categories:
        raise ValueError(
            f"Categories are not registered for {entity_kind}: "
            f"{', '.join(sorted(missing_categories))}"
        )

    world_time = _load_current_world_time(cur)
    operations = list(manifest.get("operations") or [])
    counters: Counter[str] = Counter()
    counters["operation_items"] = len(operations)
    applied_operations: list[dict[str, Any]] = []
    planned_entity_tags: set[tuple[int, int]] = set()
    planned_exclusive_tags: dict[tuple[int, str], list[str]] = {}

    for operation in operations:
        operation_type = str(operation.get("operation_type") or "")
        status = str(operation.get("status") or "")
        if status != "ready" or bool(operation.get("review_required", True)):
            counters["review_required_operations_skipped"] += 1
            applied_operations.append(
                _apply_operation_result(
                    operation,
                    entity_kind=entity_kind,
                    status="skipped_review_required",
                )
            )
            continue

        if operation_type not in ENTITY_TAG_OPERATION_TYPES:
            counters["non_entity_tag_operations_skipped"] += 1
            applied_operations.append(
                _apply_operation_result(
                    operation,
                    entity_kind=entity_kind,
                    status="skipped_non_entity_tag_operation",
                )
            )
            continue

        counters["ready_entity_tag_operations"] += 1
        target = _coerce_entity_tag_target(operation, entity_kind=entity_kind)
        if target["category"] not in allowed_category_set:
            raise ValueError(
                f"Operation {operation.get('operation_id')!r} targets category "
                f"{target['category']!r}, which is not allowed for {entity_kind}"
            )

        tag_row = _lookup_apply_tag(
            cur,
            tag=target["tag"],
            category=target["category"],
        )
        tag_id = int(_row_value(tag_row, "id"))
        entity_id = int(target["entity_id"])
        _validate_entity(cur, entity_id=entity_id, entity_kind=entity_kind)

        base_result = _apply_operation_result(
            operation,
            entity_kind=entity_kind,
            entity_id=entity_id,
            tag_id=tag_id,
            category=str(_row_value(tag_row, "category")),
            tag=target["tag"],
        )
        entity_tag_key = (entity_id, tag_id)
        if entity_tag_key in planned_entity_tags:
            counters["duplicate_ready_operations_skipped"] += 1
            applied_operations.append(
                {
                    **base_result,
                    "status": "skipped_duplicate_ready_operation",
                }
            )
            continue

        existing_entity_tag_id = _active_entity_tag_id(
            cur,
            entity_id=entity_id,
            tag_id=tag_id,
        )
        if existing_entity_tag_id is not None:
            counters["entity_tags_already_present"] += 1
            planned_entity_tags.add(entity_tag_key)
            applied_operations.append(
                {
                    **base_result,
                    "status": "already_present",
                    "entity_tag_id": existing_entity_tag_id,
                }
            )
            continue

        planned_sibling_tags = _planned_exclusive_sibling_tags(
            planned_exclusive_tags,
            entity_id=entity_id,
            category=target["category"],
            exclusive_categories=exclusive_category_set,
        )
        if planned_sibling_tags:
            counters["blocked_planned_sibling_operations"] += 1
            applied_operations.append(
                {
                    **base_result,
                    "status": "blocked_planned_sibling",
                    "planned_sibling_tags": planned_sibling_tags,
                }
            )
            continue

        sibling_tags = _active_exclusive_sibling_tags(
            cur,
            entity_id=entity_id,
            category=target["category"],
            tag_id=tag_id,
            exclusive_categories=exclusive_category_set,
        )
        if sibling_tags:
            counters["blocked_existing_sibling_operations"] += 1
            applied_operations.append(
                {
                    **base_result,
                    "status": "blocked_existing_sibling",
                    "existing_sibling_tags": sibling_tags,
                }
            )
            continue

        planned_entity_tags.add(entity_tag_key)
        if dry_run:
            _plan_exclusive_tag(
                planned_exclusive_tags,
                entity_id=entity_id,
                category=target["category"],
                tag=target["tag"],
                exclusive_categories=exclusive_category_set,
            )
            counters["entity_tags_would_insert"] += 1
            applied_operations.append({**base_result, "status": "would_insert"})
            continue

        inserted_id = _insert_entity_tag_operation(
            cur,
            entity_id=entity_id,
            tag_id=tag_id,
            world_time=world_time,
            source_kind=source_kind,
        )
        if inserted_id is None:
            counters["entity_tags_already_present"] += 1
            applied_operations.append({**base_result, "status": "already_present"})
            continue
        _plan_exclusive_tag(
            planned_exclusive_tags,
            entity_id=entity_id,
            category=target["category"],
            tag=target["tag"],
            exclusive_categories=exclusive_category_set,
        )
        counters["entity_tags_inserted"] += 1
        applied_operations.append(
            {
                **base_result,
                "status": "inserted",
                "entity_tag_id": inserted_id,
            }
        )

    for key in (
        "ready_entity_tag_operations",
        "entity_tags_would_insert",
        "entity_tags_inserted",
        "entity_tags_already_present",
        "duplicate_ready_operations_skipped",
        "blocked_existing_sibling_operations",
        "blocked_planned_sibling_operations",
        "review_required_operations_skipped",
        "non_entity_tag_operations_skipped",
    ):
        counters.setdefault(key, 0)

    return {
        "schema_version": ENTITY_TAG_MANIFEST_APPLY_SCHEMA_VERSION,
        "manifest_schema_version": manifest.get("schema_version"),
        "entity_kind": entity_kind,
        "dry_run": dry_run,
        "source_kind": source_kind,
        "source": manifest.get("source") or {},
        "policy": {
            "scope": (
                "Only reviewed ready entity-tag operations are eligible for writes."
            ),
            "eligible_operation_types": sorted(ENTITY_TAG_OPERATION_TYPES),
            "exclusive_categories": sorted(exclusive_category_set),
            "destructive_mutations": (
                "This command never clears legacy tags, rewrites pair-tags, "
                "edits prose columns, drops columns, or removes resolver shims."
            ),
        },
        "counters": dict(counters),
        "operations": applied_operations,
    }


def _apply_operation_result(
    operation: Mapping[str, Any],
    *,
    entity_kind: str,
    status: str = "",
    entity_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
) -> dict[str, Any]:
    result = {
        "operation_id": operation.get("operation_id"),
        "operation_type": operation.get("operation_type"),
        "status": status,
        "entity_kind": entity_kind,
        "source": operation.get("source") or {},
        "target": operation.get("target") or {},
    }
    for key in ("character_id", "character_name", "place_id", "place_name"):
        if operation.get(key) is not None:
            result[key] = operation.get(key)
    if entity_id is not None:
        result["entity_id"] = entity_id
    if tag_id is not None:
        result["tag_id"] = tag_id
    if category is not None:
        result["category"] = category
    if tag is not None:
        result["tag"] = tag
    return result


def _planned_exclusive_sibling_tags(
    planned_exclusive_tags: Mapping[tuple[int, str], list[str]],
    *,
    entity_id: int,
    category: str,
    exclusive_categories: set[str],
) -> list[str]:
    if category not in exclusive_categories:
        return []
    return list(planned_exclusive_tags.get((entity_id, category), ()))


def _plan_exclusive_tag(
    planned_exclusive_tags: dict[tuple[int, str], list[str]],
    *,
    entity_id: int,
    category: str,
    tag: str,
    exclusive_categories: set[str],
) -> None:
    if category not in exclusive_categories:
        return
    planned_exclusive_tags.setdefault((entity_id, category), []).append(tag)


def _coerce_entity_tag_target(
    operation: Mapping[str, Any],
    *,
    entity_kind: str,
) -> dict[str, Any]:
    target = operation.get("target")
    if not isinstance(target, MappingABC):
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} has no target mapping"
        )
    if target.get("entity_kind") != entity_kind:
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} targets "
            f"entity_kind={target.get('entity_kind')!r}, expected {entity_kind!r}"
        )
    if target.get("target_registered") is False:
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} is marked ready with "
            "target_registered=false"
        )

    entity_id = target.get("entity_id")
    category = target.get("category")
    tag = target.get("tag")
    if entity_id is None:
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} has no target entity_id"
        )
    if not category or not tag:
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} must name category and tag"
        )
    return {
        "entity_id": int(entity_id),
        "category": str(category),
        "tag": str(tag),
    }


def _validate_entity_tag_source_kind(cur: Any, source_kind: str) -> None:
    cur.execute(
        """
        SELECT 1
        FROM pg_enum
        JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
        WHERE pg_type.typname = 'entity_tag_source_kind'
          AND pg_enum.enumlabel = %s
        """,
        (source_kind,),
    )
    if cur.fetchone() is None:
        raise ValueError(f"Unknown entity_tag_source_kind {source_kind!r}")


def _load_allowed_categories(cur: Any, entity_kind: str) -> set[str]:
    cur.execute(
        """
        SELECT category
        FROM tag_category_registry
        WHERE entity_kind = %s::entity_kind
        """,
        (entity_kind,),
    )
    return {str(_row_value(row, "category")) for row in cur.fetchall()}


def _load_current_world_time(cur: Any) -> Any:
    cur.execute("SELECT max(world_time) AS world_time FROM chunk_metadata")
    row = cur.fetchone()
    if row is None:
        return None
    return _row_value(row, "world_time")


def _lookup_apply_tag(cur: Any, *, tag: str, category: str) -> Mapping[str, Any]:
    cur.execute(
        """
        SELECT id, tag, category
        FROM tags
        WHERE tag = %s
          AND category = %s
          AND NOT deprecated
          AND synonym_for IS NULL
        """,
        (tag, category),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Unknown or deprecated tag {category}:{tag} in manifest")
    return row


def _validate_entity(cur: Any, *, entity_id: int, entity_kind: str) -> None:
    cur.execute(
        """
        SELECT id, kind::text AS kind
        FROM entities
        WHERE id = %s
        """,
        (entity_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Manifest targets missing entity_id={entity_id}")
    actual_kind = str(_row_value(row, "kind"))
    if actual_kind != entity_kind:
        raise ValueError(
            f"Manifest targets entity_id={entity_id} with kind={actual_kind!r}; "
            f"expected {entity_kind!r}"
        )


def _active_entity_tag_id(cur: Any, *, entity_id: int, tag_id: int) -> Optional[int]:
    cur.execute(
        """
        SELECT id
        FROM entity_tags
        WHERE entity_id = %s
          AND tag_id = %s
          AND cleared_at IS NULL
        """,
        (entity_id, tag_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id"))


def _active_exclusive_sibling_tags(
    cur: Any,
    *,
    entity_id: int,
    category: str,
    tag_id: int,
    exclusive_categories: set[str],
) -> list[str]:
    if category not in exclusive_categories:
        return []
    cur.execute(
        """
        SELECT t.tag
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        WHERE et.entity_id = %s
          AND et.cleared_at IS NULL
          AND t.category = %s
          AND t.id <> %s
          AND NOT t.deprecated
        ORDER BY t.tag
        """,
        (entity_id, category, tag_id),
    )
    return [str(_row_value(row, "tag")) for row in cur.fetchall()]


def _insert_entity_tag_operation(
    cur: Any,
    *,
    entity_id: int,
    tag_id: int,
    world_time: Any,
    source_kind: str,
) -> Optional[int]:
    cur.execute(
        """
        INSERT INTO entity_tags (
            entity_id,
            tag_id,
            applied_at_world_time,
            source_kind
        )
        VALUES (%s, %s, %s, %s::entity_tag_source_kind)
        ON CONFLICT (entity_id, tag_id)
        WHERE cleared_at IS NULL
        DO NOTHING
        RETURNING id
        """,
        (entity_id, tag_id, world_time, source_kind),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id"))


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, MappingABC):
        return row[key]
    return getattr(row, key)
